"""
NovexTrade Card Payment Gateway Adapter (Flutterwave v3 & Paystack)
Implements hosted checkout initialization, server-side transaction verification,
and cryptographically verified webhook handling. Never touches or stores raw card details.
"""
import hashlib
import hmac
import os
from decimal import Decimal
from typing import Any, Dict, Optional

import httpx

from syncnode.common.errors import ValidationError, UnauthorizedError


class CardPaymentGateway:
    """
    Production adapter for Flutterwave v3 (primary) and Paystack (secondary).
    Controlled via environment variables; secrets are never exposed to the client.
    """

    def get_active_provider(self) -> str:
        explicit = (os.environ.get("CARD_PAYMENT_PROVIDER") or "").strip().lower()
        if explicit in ("flutterwave", "paystack"):
            return explicit
        if os.environ.get("FLUTTERWAVE_SECRET_KEY"):
            return "flutterwave"
        if os.environ.get("PAYSTACK_SECRET_KEY"):
            return "paystack"
        return "flutterwave"

    def is_configured(self, provider: Optional[str] = None) -> bool:
        prov = (provider or self.get_active_provider()).lower()
        if prov == "flutterwave":
            return bool(os.environ.get("FLUTTERWAVE_SECRET_KEY"))
        if prov == "paystack":
            return bool(os.environ.get("PAYSTACK_SECRET_KEY"))
        return False

    async def initialize_checkout(
        self,
        order: Dict[str, Any],
        user: Dict[str, Any],
        redirect_url: str,
        provider: Optional[str] = None,
    ) -> Dict[str, Any]:
        prov = (provider or self.get_active_provider()).lower()
        amount_usd = Decimal(str(order["amount_usd"]))
        reference = order["order_reference"]

        if prov == "flutterwave":
            secret = os.environ.get("FLUTTERWAVE_SECRET_KEY")
            if not secret:
                raise ValidationError(
                    "Card payments (Flutterwave) are not yet configured on this server. "
                    "Set FLUTTERWAVE_SECRET_KEY and FLUTTERWAVE_WEBHOOK_HASH in environment variables."
                )
            payload = {
                "tx_ref": reference,
                "amount": float(amount_usd),
                "currency": "USD",
                "redirect_url": redirect_url,
                "payment_options": "card",
                "customer": {
                    "email": user["email"],
                    "name": user.get("full_name") or user["email"],
                },
                "customizations": {
                    "title": "NovexTrade Institutional Research",
                    "description": f"Order {reference}",
                },
                "meta": {
                    "order_id": order["id"],
                    "user_id": user["id"],
                    "product_id": order["product_id"],
                },
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.flutterwave.com/v3/payments",
                    json=payload,
                    headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
                )
            data = resp.json()
            if resp.status_code != 200 or data.get("status") != "success":
                raise ValidationError(
                    f"Flutterwave checkout initialization failed: {data.get('message', 'Gateway error')}"
                )
            return {
                "provider": "FLUTTERWAVE",
                "provider_reference": reference,
                "checkout_url": data["data"]["link"],
                "raw": data,
            }

        if prov == "paystack":
            secret = os.environ.get("PAYSTACK_SECRET_KEY")
            if not secret:
                raise ValidationError(
                    "Card payments (Paystack) are not yet configured on this server. "
                    "Set PAYSTACK_SECRET_KEY in environment variables."
                )
            amount_cents = int((amount_usd * Decimal("100")).to_integral_value())
            payload = {
                "email": user["email"],
                "amount": amount_cents,
                "currency": "USD",
                "reference": reference,
                "callback_url": redirect_url,
                "channels": ["card"],
                "metadata": {
                    "order_id": order["id"],
                    "user_id": user["id"],
                    "product_id": order["product_id"],
                },
            }
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.post(
                    "https://api.paystack.co/transaction/initialize",
                    json=payload,
                    headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"},
                )
            data = resp.json()
            if resp.status_code != 200 or not data.get("status"):
                raise ValidationError(
                    f"Paystack checkout initialization failed: {data.get('message', 'Gateway error')}"
                )
            return {
                "provider": "PAYSTACK",
                "provider_reference": reference,
                "checkout_url": data["data"]["authorization_url"],
                "raw": data,
            }

        raise ValidationError(f"Unsupported card payment provider: {prov}")

    async def verify_transaction(
        self,
        provider: str,
        reference: str,
        provider_tx_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        prov = provider.lower()
        if prov == "flutterwave":
            secret = os.environ.get("FLUTTERWAVE_SECRET_KEY")
            if not secret:
                raise ValidationError("FLUTTERWAVE_SECRET_KEY is not configured")
            url = (
                f"https://api.flutterwave.com/v3/transactions/{provider_tx_id}/verify"
                if provider_tx_id
                else f"https://api.flutterwave.com/v3/transactions/verify_by_reference?tx_ref={reference}"
            )
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={"Authorization": f"Bearer {secret}"})
            data = resp.json()
            tx = data.get("data") or {}
            status_str = str(tx.get("status", "")).lower()
            return {
                "verified": resp.status_code == 200 and data.get("status") == "success" and status_str == "successful",
                "status": "PAID" if status_str == "successful" else ("FAILED" if status_str in ("failed", "cancelled") else "PENDING"),
                "amount_usd": Decimal(str(tx.get("amount", "0"))),
                "currency": str(tx.get("currency", "")).upper(),
                "provider_tx_id": str(tx.get("id") or provider_tx_id or ""),
                "reference": str(tx.get("tx_ref") or reference),
                "raw": data,
            }

        if prov == "paystack":
            secret = os.environ.get("PAYSTACK_SECRET_KEY")
            if not secret:
                raise ValidationError("PAYSTACK_SECRET_KEY is not configured")
            url = f"https://api.paystack.co/transaction/verify/{reference}"
            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url, headers={"Authorization": f"Bearer {secret}"})
            data = resp.json()
            tx = data.get("data") or {}
            status_str = str(tx.get("status", "")).lower()
            amount_usd = Decimal(str(tx.get("amount", 0))) / Decimal("100")
            return {
                "verified": resp.status_code == 200 and bool(data.get("status")) and status_str == "success",
                "status": "PAID" if status_str == "success" else ("FAILED" if status_str in ("failed", "abandoned") else "PENDING"),
                "amount_usd": amount_usd,
                "currency": str(tx.get("currency", "")).upper(),
                "provider_tx_id": str(tx.get("id") or ""),
                "reference": str(tx.get("reference") or reference),
                "raw": data,
            }

        raise ValidationError(f"Unsupported card payment provider: {provider}")

    def verify_flutterwave_webhook(self, verif_hash_header: Optional[str]) -> None:
        expected = os.environ.get("FLUTTERWAVE_WEBHOOK_HASH", "")
        if not expected:
            raise UnauthorizedError("FLUTTERWAVE_WEBHOOK_HASH is not configured on server")
        if not verif_hash_header or not hmac.compare_digest(verif_hash_header, expected):
            raise UnauthorizedError("Invalid Flutterwave webhook signature")

    def verify_paystack_webhook(self, raw_body: bytes, signature_header: Optional[str]) -> None:
        secret = os.environ.get("PAYSTACK_SECRET_KEY", "")
        if not secret:
            raise UnauthorizedError("PAYSTACK_SECRET_KEY is not configured on server")
        if not signature_header:
            raise UnauthorizedError("Missing Paystack webhook signature")
        computed = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha512).hexdigest()
        if not hmac.compare_digest(computed, signature_header):
            raise UnauthorizedError("Invalid Paystack webhook signature")


card_gateway = CardPaymentGateway()
