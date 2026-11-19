"""
NovexTrade Commerce, Checkout, Entitlements & Payment Verification Service
Enforces server-side product pricing ($99 Individual PDF / $699 Combo),
shared global admin crypto wallet checkout & on-chain verification,
Flutterwave/Paystack hosted card checkout & signed webhooks, and entitlement-gated downloads.
"""
import io
import os
import time
import uuid
import zipfile
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from syncnode.common.errors import ValidationError, NotFoundError, UnauthorizedError
from syncnode.database.db import db
from syncnode.database.repository import user_repository
from syncnode.database.supabase_client import supabase_client
from syncnode.services.card_gateway import card_gateway
from syncnode.services.crypto_verifier import (
    crypto_verifier,
    validate_wallet_address,
    validate_tx_hash_format,
    NETWORK_ASSETS,
)
from syncnode.services.referral import referral_service
from syncnode.services.resources import resources_service


ORDER_EXPIRY_MS = 30 * 60 * 1000  # 30 minutes


def _now_ms() -> int:
    return int(time.time() * 1000)


def _dec2(val: Any) -> Decimal:
    return Decimal(str(val or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class CommerceService:
    # -------------------------------------------------------------------------
    # PRODUCTS & PRICING (SERVER-SIDE AUTHORITATIVE)
    # -------------------------------------------------------------------------

    def get_products(self) -> List[Dict[str, Any]]:
        return list(db.products.values())

    def get_product(self, product_id: str) -> Dict[str, Any]:
        product = db.products.get(product_id)
        if not product or not product.get("is_active", True):
            raise NotFoundError(f"Product '{product_id}' not found")
        return product

    # -------------------------------------------------------------------------
    # GLOBAL CRYPTOCURRENCY WALLET CONFIGURATION
    # -------------------------------------------------------------------------

    def get_global_crypto_wallet_config(self) -> Dict[str, Any]:
        """Returns the exact same global admin-configured receiving wallet for every user."""
        cfg = db.crypto_wallet_config
        return {
            "isEnabled": bool(cfg.get("is_enabled", False)),
            "receivingAddress": cfg.get("receiving_address", ""),
            "primaryAsset": cfg.get("primary_asset", "USDT"),
            "primaryNetwork": cfg.get("primary_network", "ERC20"),
            "supportedTokens": list(cfg.get("supported_tokens", ["USDT"])),
            "requiredConfirmations": int(cfg.get("required_confirmations", 12)),
            "memoTag": cfg.get("memo_tag"),
            "updatedAt": cfg.get("updated_at"),
            "availableNetworks": NETWORK_ASSETS,
        }

    def update_global_crypto_wallet_config(self, admin_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        cfg = db.crypto_wallet_config
        network = str(payload.get("primary_network", cfg.get("primary_network", "ERC20"))).strip().upper()
        address = str(payload.get("receiving_address", cfg.get("receiving_address", ""))).strip()

        # Strict network-aware wallet address validation
        validated_addr = validate_wallet_address(address, network)

        allowed_assets = NETWORK_ASSETS[network]
        primary_asset = str(payload.get("primary_asset", cfg.get("primary_asset", allowed_assets[0]))).strip().upper()
        if primary_asset not in allowed_assets:
            raise ValidationError(
                f"Asset '{primary_asset}' is not supported on {network}. Allowed: {', '.join(allowed_assets)}"
            )

        raw_tokens = payload.get("supported_tokens")
        if raw_tokens is not None:
            tokens = [str(t).strip().upper() for t in raw_tokens if str(t).strip()]
            if not tokens:
                raise ValidationError("At least one supported token must be selected")
            invalid = [t for t in tokens if t not in allowed_assets]
            if invalid:
                raise ValidationError(
                    f"Tokens {', '.join(invalid)} are not valid for {network}. Allowed: {', '.join(allowed_assets)}"
                )
            if primary_asset not in tokens:
                tokens.insert(0, primary_asset)
        else:
            tokens = [t for t in cfg.get("supported_tokens", []) if t in allowed_assets] or [primary_asset]

        confirmations = int(payload.get("required_confirmations", cfg.get("required_confirmations", 12)))
        if confirmations < 1 or confirmations > 100:
            raise ValidationError("required_confirmations must be between 1 and 100")

        cfg["receiving_address"] = validated_addr
        cfg["primary_network"] = network
        cfg["primary_asset"] = primary_asset
        cfg["supported_tokens"] = tokens
        cfg["required_confirmations"] = confirmations
        if "is_enabled" in payload:
            cfg["is_enabled"] = bool(payload["is_enabled"])
        if "memo_tag" in payload:
            memo = (payload.get("memo_tag") or "").strip()
            cfg["memo_tag"] = memo if memo else None
        cfg["updated_by"] = admin_id
        cfg["updated_at"] = _now_ms()

        supabase_client.queue_upsert("crypto_wallet_config", cfg)
        self._audit(admin_id, "ADMIN_GLOBAL_CRYPTO_WALLET_UPDATED", {
            "receiving_address": validated_addr,
            "primary_network": network,
            "primary_asset": primary_asset,
            "supported_tokens": tokens,
            "is_enabled": cfg["is_enabled"],
        })
        return self.get_global_crypto_wallet_config()

    # -------------------------------------------------------------------------
    # CHECKOUT ORDER CREATION (CARD & CRYPTO)
    # -------------------------------------------------------------------------

    async def create_checkout_order(
        self,
        user: Dict[str, Any],
        product_id: str,
        payment_method: str,
        resource_id: Optional[str] = None,
        crypto_asset: Optional[str] = None,
        referral_code: Optional[str] = None,
        idempotency_key: Optional[str] = None,
        client_supplied_price: Optional[Any] = None,
        card_provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        # 1. Server-side authoritative product & pricing lookup
        product = self.get_product(product_id)
        authoritative_price = _dec2(product["price_usd"])

        # 2. Reject any client-side price manipulation attempt
        if client_supplied_price is not None:
            try:
                submitted = _dec2(client_supplied_price)
            except Exception:
                raise ValidationError("Invalid price format submitted")
            if submitted != authoritative_price:
                raise ValidationError(
                    f"Price manipulation rejected: expected ${authoritative_price:.2f} USD for {product['name']}"
                )

        # 3. Validate resource_id for individual PDF
        if product["product_type"] == "INDIVIDUAL_PDF":
            if not resource_id or not resources_service.get_resource(resource_id):
                raise ValidationError("A valid strategy PDF resourceId is required for Individual PDF checkout")
        else:
            resource_id = None

        # 4. Prevent duplicate checkout submissions via idempotency key
        if idempotency_key:
            existing_id = db.product_orders_by_idempotency.get(f"{user['id']}:{idempotency_key}")
            if existing_id and existing_id in db.product_orders:
                existing = db.product_orders[existing_id]
                return self._format_order_response(existing)

        method = (payment_method or "").strip().upper()
        if method not in ("CARD", "CRYPTO"):
            raise ValidationError("paymentMethod must be CARD or CRYPTO")

        # 5. Resolve authoritative referrer (cannot be overwritten if permanent relationship exists)
        referrer_user_id = referral_service.resolve_referrer_for_order(user["id"], referral_code)

        now = _now_ms()
        order_id = f"ord_{uuid.uuid4().hex[:12]}"
        order_ref = f"NVX-{uuid.uuid4().hex[:10].upper()}"
        expires_at = now + ORDER_EXPIRY_MS

        if method == "CRYPTO":
            wallet_cfg = db.crypto_wallet_config
            if not wallet_cfg.get("is_enabled", False):
                raise ValidationError("Cryptocurrency payments are currently disabled by the administrator")
            if not wallet_cfg.get("receiving_address"):
                raise ValidationError("Global cryptocurrency receiving wallet is not configured")

            network = wallet_cfg["primary_network"]
            supported_tokens = wallet_cfg.get("supported_tokens", [wallet_cfg["primary_asset"]])
            chosen_asset = (crypto_asset or wallet_cfg["primary_asset"]).strip().upper()
            if chosen_asset not in supported_tokens:
                raise ValidationError(
                    f"Asset '{chosen_asset}' is not enabled for crypto checkout. Supported: {', '.join(supported_tokens)}"
                )

            rate_usd = await crypto_verifier.get_usd_exchange_rate(chosen_asset)
            precision = Decimal("0.01") if chosen_asset in ("USDT", "USDC") else Decimal("0.00000001")
            expected_crypto = (authoritative_price / rate_usd).quantize(precision, rounding=ROUND_HALF_UP)

            order = {
                "id": order_id,
                "order_reference": order_ref,
                "user_id": user["id"],
                "product_id": product["id"],
                "product_name": product["name"],
                "resource_id": resource_id,
                "amount_usd": f"{authoritative_price:.2f}",
                "currency": "USD",
                "payment_method": "CRYPTO",
                "payment_provider": "ONCHAIN_GLOBAL_WALLET",
                "status": "PENDING",
                "referral_code": referral_code.strip().upper() if referral_code else None,
                "referrer_user_id": referrer_user_id,
                "idempotency_key": f"{user['id']}:{idempotency_key}" if idempotency_key else None,
                "expires_at": expires_at,
                "paid_at": None,
                "refunded_at": None,
                "crypto_instructions": {
                    "receivingAddress": wallet_cfg["receiving_address"],
                    "network": network,
                    "asset": chosen_asset,
                    "expectedAmountCrypto": str(expected_crypto),
                    "exchangeRateUsd": str(rate_usd),
                    "requiredConfirmations": int(wallet_cfg.get("required_confirmations", 12)),
                    "memoTag": wallet_cfg.get("memo_tag") or order_ref,
                    "orderReference": order_ref,
                    "expiresAt": expires_at,
                },
                "created_at": now,
                "updated_at": now,
            }
            payment = {
                "id": f"pay_{uuid.uuid4().hex[:12]}",
                "order_id": order_id,
                "user_id": user["id"],
                "payment_method": "CRYPTO",
                "provider": "ONCHAIN_GLOBAL_WALLET",
                "provider_reference": order_ref,
                "provider_tx_id": None,
                "amount_usd": f"{authoritative_price:.2f}",
                "currency": "USD",
                "status": "PENDING",
                "checkout_url": None,
                "raw_metadata": order["crypto_instructions"],
                "created_at": now,
                "updated_at": now,
            }
        else:
            # CARD CHECKOUT (Flutterwave / Paystack Hosted Checkout)
            active_prov = (card_provider or card_gateway.get_active_provider()).lower()
            app_base = os.environ.get("APP_BASE_URL", "https://novextrade.exchange").rstrip("/")
            redirect_url = f"{app_base}/?checkout_ref={order_ref}"

            order = {
                "id": order_id,
                "order_reference": order_ref,
                "user_id": user["id"],
                "product_id": product["id"],
                "product_name": product["name"],
                "resource_id": resource_id,
                "amount_usd": f"{authoritative_price:.2f}",
                "currency": "USD",
                "payment_method": "CARD",
                "payment_provider": active_prov.upper(),
                "status": "PENDING",
                "referral_code": referral_code.strip().upper() if referral_code else None,
                "referrer_user_id": referrer_user_id,
                "idempotency_key": f"{user['id']}:{idempotency_key}" if idempotency_key else None,
                "expires_at": expires_at,
                "paid_at": None,
                "refunded_at": None,
                "crypto_instructions": None,
                "created_at": now,
                "updated_at": now,
            }

            gateway_res = await card_gateway.initialize_checkout(
                order=order, user=user, redirect_url=redirect_url, provider=active_prov
            )
            payment = {
                "id": f"pay_{uuid.uuid4().hex[:12]}",
                "order_id": order_id,
                "user_id": user["id"],
                "payment_method": "CARD",
                "provider": gateway_res["provider"],
                "provider_reference": gateway_res["provider_reference"],
                "provider_tx_id": None,
                "amount_usd": f"{authoritative_price:.2f}",
                "currency": "USD",
                "status": "PENDING",
                "checkout_url": gateway_res["checkout_url"],
                "raw_metadata": gateway_res.get("raw", {}),
                "created_at": now,
                "updated_at": now,
            }

        db.product_orders[order_id] = order
        db.product_orders_by_ref[order_ref] = order_id
        if order["idempotency_key"]:
            db.product_orders_by_idempotency[order["idempotency_key"]] = order_id
        db.payment_records[payment["id"]] = payment
        db.payment_records_by_provider_ref[payment["provider_reference"]] = payment["id"]

        supabase_client.queue_upsert("product_orders", order)
        supabase_client.queue_upsert("payment_records", payment)

        return self._format_order_response(order, payment)

    # -------------------------------------------------------------------------
    # CRYPTOCURRENCY TRANSACTION SUBMISSION & ON-CHAIN VERIFICATION
    # -------------------------------------------------------------------------

    async def submit_and_verify_crypto_tx(
        self,
        user_id: str,
        order_id: str,
        tx_hash: str,
    ) -> Dict[str, Any]:
        order = db.product_orders.get(order_id)
        if not order or order["user_id"] != user_id:
            raise NotFoundError("Order not found")
        if order["payment_method"] != "CRYPTO":
            raise ValidationError("Order is not a cryptocurrency order")
        if order["status"] == "PAID":
            return self._format_order_response(order)
        if order["status"] in ("CANCELLED", "REFUNDED", "EXPIRED"):
            raise ValidationError(f"Cannot submit transaction for order in status {order['status']}")

        now = _now_ms()
        if now > order["expires_at"]:
            order["status"] = "EXPIRED"
            order["updated_at"] = now
            supabase_client.queue_upsert("product_orders", order)
            raise ValidationError("This checkout order has expired. Please create a new order.")

        instr = order.get("crypto_instructions") or {}
        network = instr["network"]
        asset = instr["asset"]
        expected_addr = instr["receivingAddress"]
        expected_amount = Decimal(str(instr["expectedAmountCrypto"]))
        required_confs = int(instr.get("requiredConfirmations", 12))

        normalized_hash = validate_tx_hash_format(tx_hash, network)

        # Duplicate transaction hash detection across orders
        existing_tx_id = db.crypto_tx_by_hash.get(normalized_hash)
        if existing_tx_id:
            existing_tx = db.crypto_transactions.get(existing_tx_id)
            if existing_tx and existing_tx.get("order_id") != order_id:
                raise ValidationError(
                    "Duplicate transaction hash rejected: this blockchain transaction is already linked to another order."
                )

        # Perform real server-side on-chain verification
        verification = await crypto_verifier.verify_onchain_transaction(
            tx_hash=normalized_hash,
            network=network,
            asset=asset,
            expected_receiving_address=expected_addr,
            expected_amount_crypto=expected_amount,
            required_confirmations=required_confs,
        )

        v_status = verification["status"]
        tx_id = existing_tx_id or f"ctx_{uuid.uuid4().hex[:12]}"
        crypto_tx = {
            "id": tx_id,
            "order_id": order_id,
            "order_reference": order["order_reference"],
            "user_id": user_id,
            "tx_hash": normalized_hash,
            "network": network,
            "asset": asset,
            "expected_amount_crypto": str(expected_amount),
            "received_amount_crypto": str(verification["received_amount"]),
            "exchange_rate_usd": str(instr.get("exchangeRateUsd", "1.00")),
            "receiving_address": expected_addr,
            "sender_address": verification.get("sender_address"),
            "confirmations": int(verification.get("confirmations", 0)),
            "required_confirmations": required_confs,
            "verification_status": v_status,
            "reconciliation_notes": verification.get("reason"),
            "verified_by_admin_id": None,
            "raw_tx_data": verification.get("raw", {}),
            "created_at": db.crypto_transactions[tx_id]["created_at"] if tx_id in db.crypto_transactions else now,
            "updated_at": now,
        }
        db.crypto_transactions[tx_id] = crypto_tx
        db.crypto_tx_by_hash[normalized_hash] = tx_id
        supabase_client.queue_upsert("crypto_transactions", crypto_tx)

        payment = self._find_payment_for_order(order_id)
        self._record_verification_event(
            order_id=order_id,
            payment_id=payment["id"] if payment else None,
            event_type="CRYPTO_ONCHAIN_VERIFICATION",
            provider_event_id=None,
            status=v_status,
            details={
                "tx_hash": normalized_hash,
                "network": network,
                "asset": asset,
                "received": str(verification["received_amount"]),
                "expected": str(expected_amount),
                "confirmations": verification["confirmations"],
                "reason": verification["reason"],
            },
        )

        # Only unlock downloads when verified CONFIRMED or OVERPAID
        if v_status in ("CONFIRMED", "OVERPAID"):
            self._finalize_paid_order(order, payment, provider_tx_id=normalized_hash)
        elif v_status in ("PENDING", "UNMATCHED_REVIEW"):
            order["status"] = "AWAITING_VERIFICATION"
            order["updated_at"] = now
            supabase_client.queue_upsert("product_orders", order)
        elif v_status == "UNDERPAID":
            order["status"] = "UNDERPAID"
            order["updated_at"] = now
            supabase_client.queue_upsert("product_orders", order)
        elif v_status == "FAILED":
            order["status"] = "FAILED"
            order["updated_at"] = now
            supabase_client.queue_upsert("product_orders", order)
        # For INVALID_TX / WRONG_ADDRESS / WRONG_TOKEN, keep order PENDING so user can submit the valid hash

        result = self._format_order_response(order, payment)
        result["cryptoVerification"] = {
            "txHash": normalized_hash,
            "status": v_status,
            "confirmations": crypto_tx["confirmations"],
            "requiredConfirmations": required_confs,
            "receivedAmountCrypto": crypto_tx["received_amount_crypto"],
            "expectedAmountCrypto": crypto_tx["expected_amount_crypto"],
            "reason": verification.get("reason"),
        }
        return result

    # -------------------------------------------------------------------------
    # CARD PAYMENT WEBHOOKS & SERVER-SIDE VERIFICATION
    # -------------------------------------------------------------------------

    async def verify_card_order_status(self, user_id: str, order_id: str, provider_tx_id: Optional[str] = None) -> Dict[str, Any]:
        """Server-side poll/verification against Flutterwave/Paystack API (never trusts browser redirect alone)."""
        order = db.product_orders.get(order_id)
        if not order or order["user_id"] != user_id:
            raise NotFoundError("Order not found")
        if order["status"] == "PAID":
            return self._format_order_response(order)
        if order["payment_method"] != "CARD":
            raise ValidationError("Order is not a card order")

        payment = self._find_payment_for_order(order_id)
        res = await card_gateway.verify_transaction(
            provider=order["payment_provider"],
            reference=order["order_reference"],
            provider_tx_id=provider_tx_id,
        )

        self._record_verification_event(
            order_id=order_id,
            payment_id=payment["id"] if payment else None,
            event_type="CARD_API_VERIFY",
            provider_event_id=None,
            status=res["status"],
            details={"reference": res["reference"], "amount": str(res["amount_usd"]), "currency": res["currency"]},
        )

        expected = _dec2(order["amount_usd"])
        if res["verified"] and res["currency"] == "USD" and res["amount_usd"] >= expected:
            self._finalize_paid_order(order, payment, provider_tx_id=res.get("provider_tx_id"))
        elif res["status"] == "FAILED":
            order["status"] = "FAILED"
            order["updated_at"] = _now_ms()
            if payment:
                payment["status"] = "FAILED"
                payment["updated_at"] = _now_ms()
                supabase_client.queue_upsert("payment_records", payment)
            supabase_client.queue_upsert("product_orders", order)

        return self._format_order_response(order, payment)

    def handle_card_webhook(
        self,
        provider: str,
        raw_body: bytes,
        headers: Dict[str, str],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        prov = provider.lower()
        lower_headers = {k.lower(): v for k, v in headers.items()}

        # 1. Cryptographic signature verification
        if prov == "flutterwave":
            card_gateway.verify_flutterwave_webhook(lower_headers.get("verif-hash"))
            event_name = str(payload.get("event", "")).lower()
            data = payload.get("data") or {}
            order_ref = str(data.get("tx_ref") or "")
            provider_tx_id = str(data.get("id") or "")
            provider_event_id = f"flw:{event_name}:{provider_tx_id}:{data.get('status', '')}"
            amount_usd = _dec2(data.get("amount", "0"))
            currency = str(data.get("currency", "")).upper()
            tx_status = str(data.get("status", "")).lower()
        elif prov == "paystack":
            card_gateway.verify_paystack_webhook(raw_body, lower_headers.get("x-paystack-signature"))
            event_name = str(payload.get("event", "")).lower()
            data = payload.get("data") or {}
            order_ref = str(data.get("reference") or "")
            provider_tx_id = str(data.get("id") or "")
            provider_event_id = f"psk:{event_name}:{provider_tx_id}:{order_ref}"
            amount_usd = (Decimal(str(data.get("amount", 0))) / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            currency = str(data.get("currency", "")).upper()
            tx_status = str(data.get("status", "")).lower()
        else:
            raise ValidationError(f"Unsupported webhook provider: {provider}")

        # 2. Idempotent webhook deduplication
        if provider_event_id in db.processed_webhook_events:
            return {"success": True, "duplicate": True, "eventId": provider_event_id}

        order_id = db.product_orders_by_ref.get(order_ref)
        if not order_id or order_id not in db.product_orders:
            # Record unmatched webhook event for auditability without crashing
            db.processed_webhook_events.add(provider_event_id)
            self._record_verification_event(
                order_id=None,
                payment_id=None,
                event_type=f"WEBHOOK_{prov.upper()}_UNMATCHED",
                provider_event_id=provider_event_id,
                status="UNMATCHED",
                details={"event": event_name, "order_ref": order_ref},
            )
            return {"success": True, "matched": False, "orderReference": order_ref}

        order = db.product_orders[order_id]
        payment = self._find_payment_for_order(order_id)
        db.processed_webhook_events.add(provider_event_id)

        # 3. Route by event type
        is_success_event = (
            (prov == "flutterwave" and event_name == "charge.completed" and tx_status == "successful")
            or (prov == "paystack" and event_name == "charge.success" and tx_status == "success")
        )
        is_failed_event = (
            (prov == "flutterwave" and event_name == "charge.completed" and tx_status in ("failed", "cancelled"))
            or (prov == "paystack" and event_name in ("charge.failed", "charge.abandoned"))
        )
        is_refund_event = "refund" in event_name
        is_dispute_event = "dispute" in event_name or "chargeback" in event_name

        if is_success_event:
            expected = _dec2(order["amount_usd"])
            if currency != "USD" or amount_usd < expected:
                self._record_verification_event(
                    order_id=order_id,
                    payment_id=payment["id"] if payment else None,
                    event_type=f"WEBHOOK_{prov.upper()}_AMOUNT_MISMATCH",
                    provider_event_id=provider_event_id,
                    status="REJECTED",
                    details={"expected": str(expected), "received": str(amount_usd), "currency": currency},
                )
                return {"success": False, "error": "Payment amount or currency mismatch"}

            self._record_verification_event(
                order_id=order_id,
                payment_id=payment["id"] if payment else None,
                event_type=f"WEBHOOK_{prov.upper()}_PAID",
                provider_event_id=provider_event_id,
                status="PAID",
                details={"provider_tx_id": provider_tx_id, "amount_usd": str(amount_usd)},
            )
            self._finalize_paid_order(order, payment, provider_tx_id=provider_tx_id)
            return {"success": True, "status": "PAID", "orderId": order_id}

        if is_failed_event:
            now = _now_ms()
            if order["status"] != "PAID":
                order["status"] = "FAILED"
                order["updated_at"] = now
                supabase_client.queue_upsert("product_orders", order)
                if payment:
                    payment["status"] = "FAILED"
                    payment["updated_at"] = now
                    supabase_client.queue_upsert("payment_records", payment)
            self._record_verification_event(
                order_id=order_id,
                payment_id=payment["id"] if payment else None,
                event_type=f"WEBHOOK_{prov.upper()}_FAILED",
                provider_event_id=provider_event_id,
                status="FAILED",
                details={"tx_status": tx_status},
            )
            return {"success": True, "status": "FAILED", "orderId": order_id}

        if is_refund_event:
            self.revoke_order_on_refund_or_dispute(
                order_id=order_id,
                new_status="REFUNDED",
                reason=f"Refund webhook from {prov.upper()} ({event_name})",
                provider_event_id=provider_event_id,
            )
            return {"success": True, "status": "REFUNDED", "orderId": order_id}

        if is_dispute_event:
            self.revoke_order_on_refund_or_dispute(
                order_id=order_id,
                new_status="DISPUTED",
                reason=f"Chargeback/dispute webhook from {prov.upper()} ({event_name})",
                provider_event_id=provider_event_id,
            )
            return {"success": True, "status": "DISPUTED", "orderId": order_id}

        return {"success": True, "ignored": True, "event": event_name}

    # -------------------------------------------------------------------------
    # ORDER FINALIZATION, ENTITLEMENTS, REFUNDS & DOWNLOADS
    # -------------------------------------------------------------------------

    def _finalize_paid_order(
        self,
        order: Dict[str, Any],
        payment: Optional[Dict[str, Any]],
        provider_tx_id: Optional[str] = None,
    ) -> None:
        if order["status"] == "PAID":
            return
        now = _now_ms()
        order["status"] = "PAID"
        order["paid_at"] = now
        order["updated_at"] = now
        supabase_client.queue_upsert("product_orders", order)

        if payment:
            payment["status"] = "PAID"
            if provider_tx_id:
                payment["provider_tx_id"] = provider_tx_id
            payment["updated_at"] = now
            supabase_client.queue_upsert("payment_records", payment)

        # 1. Grant server-side download entitlements
        self._grant_entitlements(order)

        # 2. Calculate & record referral commission (idempotent per order)
        referral_service.create_commission_for_paid_order(order)

    def _grant_entitlements(self, order: Dict[str, Any]) -> Dict[str, Any]:
        target_resource = "ALL_COMBO" if order["product_id"] == "combo_bundle" else order["resource_id"]
        # Prevent duplicate entitlement for same order
        for ent in db.download_entitlements.values():
            if ent["order_id"] == order["id"] and ent["resource_id"] == target_resource:
                return ent

        ent_id = f"ent_{uuid.uuid4().hex[:12]}"
        entitlement = {
            "id": ent_id,
            "user_id": order["user_id"],
            "order_id": order["id"],
            "order_reference": order["order_reference"],
            "product_id": order["product_id"],
            "resource_id": target_resource,
            "status": "ACTIVE",
            "revoked_reason": None,
            "revoked_at": None,
            "granted_at": _now_ms(),
        }
        db.download_entitlements[ent_id] = entitlement
        supabase_client.queue_upsert("download_entitlements", entitlement)
        return entitlement

    def revoke_order_on_refund_or_dispute(
        self,
        order_id: str,
        new_status: str,
        reason: str,
        admin_id: Optional[str] = None,
        provider_event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        order = db.product_orders.get(order_id)
        if not order:
            raise NotFoundError(f"Order '{order_id}' not found")
        if new_status not in ("REFUNDED", "DISPUTED"):
            raise ValidationError("Status must be REFUNDED or DISPUTED")

        now = _now_ms()
        order["status"] = new_status
        order["refunded_at"] = now
        order["updated_at"] = now
        supabase_client.queue_upsert("product_orders", order)

        payment = self._find_payment_for_order(order_id)
        if payment:
            payment["status"] = new_status
            payment["updated_at"] = now
            supabase_client.queue_upsert("payment_records", payment)

        # Revoke all associated download entitlements immediately
        for ent in db.download_entitlements.values():
            if ent["order_id"] == order_id and ent["status"] == "ACTIVE":
                ent["status"] = "REVOKED"
                ent["revoked_reason"] = reason
                ent["revoked_at"] = now
                supabase_client.queue_upsert("download_entitlements", ent)

        # Reverse associated referral commission
        referral_service.reverse_commission_for_order(order_id, reason)

        self._record_verification_event(
            order_id=order_id,
            payment_id=payment["id"] if payment else None,
            event_type=f"ORDER_{new_status}",
            provider_event_id=provider_event_id,
            status=new_status,
            details={"reason": reason, "admin_id": admin_id},
        )
        if admin_id:
            self._audit(admin_id, f"ADMIN_ORDER_{new_status}", {"order_id": order_id, "reason": reason})

        return self._format_order_response(order, payment)

    def check_download_entitlement(self, user_id: str, resource_id: str) -> Optional[Dict[str, Any]]:
        """
        Strictly verifies that `user_id` holds an ACTIVE paid entitlement for `resource_id`
        or an ACTIVE `ALL_COMBO` entitlement.
        """
        for ent in db.download_entitlements.values():
            if ent["user_id"] != user_id or ent["status"] != "ACTIVE":
                continue
            if ent["resource_id"] == "ALL_COMBO" or ent["resource_id"] == resource_id:
                return ent
        return None

    def check_combo_entitlement(self, user_id: str) -> Optional[Dict[str, Any]]:
        for ent in db.download_entitlements.values():
            if ent["user_id"] == user_id and ent["status"] == "ACTIVE" and ent["resource_id"] == "ALL_COMBO":
                return ent
        return None

    def record_download_activity(
        self,
        user_id: str,
        entitlement_id: str,
        resource_id: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
    ) -> Dict[str, Any]:
        entry = {
            "id": f"dl_{uuid.uuid4().hex[:12]}",
            "user_id": user_id,
            "entitlement_id": entitlement_id,
            "resource_id": resource_id,
            "ip_address": ip_address,
            "user_agent": (user_agent or "")[:256],
            "created_at": _now_ms(),
        }
        db.download_logs.append(entry)
        supabase_client.queue_upsert("download_logs", entry)
        return entry

    def build_combo_zip_bytes(self) -> bytes:
        """Packages all existing strategy PDFs unchanged into a single verified ZIP archive."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            for res in resources_service.get_catalog():
                fp = resources_service.get_pdf_filepath(res["id"])
                if fp and fp.exists():
                    zf.write(fp, arcname=res["filename"])
        return buf.getvalue()

    def get_user_orders_and_entitlements(self, user_id: str) -> Dict[str, Any]:
        orders = [
            self._format_order_response(o)
            for o in sorted(
                (o for o in db.product_orders.values() if o["user_id"] == user_id),
                key=lambda x: x["created_at"],
                reverse=True,
            )
        ]
        active_entitlements = [
            ent
            for ent in db.download_entitlements.values()
            if ent["user_id"] == user_id and ent["status"] == "ACTIVE"
        ]
        has_combo = any(e["resource_id"] == "ALL_COMBO" for e in active_entitlements)
        unlocked_resource_ids = (
            [r["id"] for r in resources_service.get_catalog()]
            if has_combo
            else sorted({e["resource_id"] for e in active_entitlements})
        )
        return {
            "orders": orders,
            "entitlements": active_entitlements,
            "hasComboAccess": has_combo,
            "unlockedResourceIds": unlocked_resource_ids,
        }

    # -------------------------------------------------------------------------
    # ADMIN PAYMENT & CRYPTO RECONCILIATION
    # -------------------------------------------------------------------------

    def get_admin_payments_overview(
        self,
        status_filter: Optional[str] = None,
        method_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> Dict[str, Any]:
        all_orders = list(db.product_orders.values())
        paid_orders = [o for o in all_orders if o["status"] == "PAID"]

        total_revenue = sum((_dec2(o["amount_usd"]) for o in paid_orders), Decimal("0.00"))
        individual_sales = sum(1 for o in paid_orders if o["product_id"] == "individual_pdf")
        combo_sales = sum(1 for o in paid_orders if o["product_id"] == "combo_bundle")

        summary = {
            "totalSales": len(paid_orders),
            "totalRevenueUsd": f"{total_revenue:.2f}",
            "individualPdfSales": individual_sales,
            "comboSales": combo_sales,
            "cardTransactions": sum(1 for o in all_orders if o["payment_method"] == "CARD"),
            "cryptoTransactions": sum(1 for o in all_orders if o["payment_method"] == "CRYPTO"),
            "pendingPayments": sum(1 for o in all_orders if o["status"] in ("PENDING", "AWAITING_VERIFICATION", "UNDERPAID")),
            "successfulPayments": len(paid_orders),
            "failedPayments": sum(1 for o in all_orders if o["status"] in ("FAILED", "CANCELLED", "EXPIRED")),
            "refunds": sum(1 for o in all_orders if o["status"] == "REFUNDED"),
            "disputedTransactions": sum(1 for o in all_orders if o["status"] == "DISPUTED"),
        }

        q = (search or "").strip().lower()
        enriched_orders = []
        for o in sorted(all_orders, key=lambda x: x["created_at"], reverse=True):
            if status_filter and o["status"] != status_filter.upper():
                continue
            if method_filter and o["payment_method"] != method_filter.upper():
                continue
            user = user_repository.find_by_id(o["user_id"]) or {}
            payment = self._find_payment_for_order(o["id"])
            events = [e for e in db.payment_verification_events if e.get("order_id") == o["id"]]
            row = {
                **self._format_order_response(o, payment),
                "customerEmail": user.get("email"),
                "customerName": user.get("full_name"),
                "verificationHistory": events,
            }
            if not q or (
                q in (row.get("orderReference") or "").lower()
                or q in (row.get("customerEmail") or "").lower()
                or q in (row.get("productName") or "").lower()
            ):
                enriched_orders.append(row)

        crypto_txs = []
        for tx in sorted(db.crypto_transactions.values(), key=lambda x: x["updated_at"], reverse=True):
            user = user_repository.find_by_id(tx.get("user_id") or "") or {}
            crypto_txs.append({
                **tx,
                "customerEmail": user.get("email"),
            })

        return {
            "summary": summary,
            "orders": enriched_orders[:150],
            "cryptoTransactions": crypto_txs[:150],
            "walletConfig": self.get_global_crypto_wallet_config(),
        }

    def admin_reconcile_crypto_transaction(
        self,
        tx_id: str,
        decision: str,
        admin_id: str,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        tx = db.crypto_transactions.get(tx_id)
        if not tx:
            raise NotFoundError(f"Crypto transaction '{tx_id}' not found")

        dec = decision.strip().upper()
        if dec not in ("APPROVE", "REJECT"):
            raise ValidationError("Decision must be APPROVE or REJECT")

        now = _now_ms()
        order = db.product_orders.get(tx.get("order_id") or "")
        payment = self._find_payment_for_order(order["id"]) if order else None

        tx["verified_by_admin_id"] = admin_id
        tx["reconciliation_notes"] = notes or f"Reconciled as {dec} by administrator"
        tx["updated_at"] = now

        if dec == "APPROVE":
            tx["verification_status"] = "CONFIRMED"
            if order:
                self._finalize_paid_order(order, payment, provider_tx_id=tx["tx_hash"])
        else:
            tx["verification_status"] = "FAILED"
            if order and order["status"] != "PAID":
                order["status"] = "FAILED"
                order["updated_at"] = now
                supabase_client.queue_upsert("product_orders", order)

        supabase_client.queue_upsert("crypto_transactions", tx)
        self._record_verification_event(
            order_id=order["id"] if order else None,
            payment_id=payment["id"] if payment else None,
            event_type=f"ADMIN_CRYPTO_RECONCILE_{dec}",
            provider_event_id=None,
            status=tx["verification_status"],
            details={"tx_id": tx_id, "admin_id": admin_id, "notes": notes},
        )
        self._audit(admin_id, f"ADMIN_CRYPTO_TX_{dec}", {"tx_id": tx_id, "order_id": tx.get("order_id"), "notes": notes})
        return tx

    # -------------------------------------------------------------------------
    # HELPERS
    # -------------------------------------------------------------------------

    def _find_payment_for_order(self, order_id: str) -> Optional[Dict[str, Any]]:
        for p in db.payment_records.values():
            if p.get("order_id") == order_id:
                return p
        return None

    def _record_verification_event(
        self,
        order_id: Optional[str],
        payment_id: Optional[str],
        event_type: str,
        provider_event_id: Optional[str],
        status: str,
        details: Dict[str, Any],
    ) -> Dict[str, Any]:
        evt = {
            "id": f"pevt_{uuid.uuid4().hex[:12]}",
            "order_id": order_id,
            "payment_id": payment_id,
            "event_type": event_type,
            "provider_event_id": provider_event_id,
            "status": status,
            "details": details,
            "created_at": _now_ms(),
        }
        db.payment_verification_events.append(evt)
        supabase_client.queue_upsert("payment_verification_events", evt)
        return evt

    def _format_order_response(
        self,
        order: Dict[str, Any],
        payment: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        pay = payment or self._find_payment_for_order(order["id"])
        return {
            "id": order["id"],
            "orderReference": order["order_reference"],
            "userId": order["user_id"],
            "productId": order["product_id"],
            "productName": order.get("product_name", order["product_id"]),
            "resourceId": order.get("resource_id"),
            "amountUsd": order["amount_usd"],
            "currency": order["currency"],
            "paymentMethod": order["payment_method"],
            "paymentProvider": order["payment_provider"],
            "status": order["status"],
            "checkoutUrl": pay.get("checkout_url") if pay else None,
            "cryptoInstructions": order.get("crypto_instructions"),
            "expiresAt": order["expires_at"],
            "paidAt": order.get("paid_at"),
            "refundedAt": order.get("refunded_at"),
            "createdAt": order["created_at"],
            "updatedAt": order["updated_at"],
        }

    def _audit(self, admin_id: str, action: str, details: Dict[str, Any]):
        log = {
            "id": f"aud_{uuid.uuid4().hex[:12]}",
            "admin_id": admin_id,
            "user_id": None,
            "action": action,
            "details": details,
            "created_at": _now_ms(),
        }
        db.audit_logs.append(log)
        supabase_client.queue_upsert("audit_logs", log)


commerce_service = CommerceService()
