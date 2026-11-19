"""
NovexTrade Referral & Commission Engine
Handles permanent referral code generation, click attribution, self-referral prevention,
admin-configured commission calculations, reversals, and analytics.
"""
import hashlib
import os
import secrets
import time
import uuid
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional

from syncnode.common.errors import ValidationError, NotFoundError
from syncnode.database.db import db
from syncnode.database.repository import user_repository
from syncnode.database.supabase_client import supabase_client


_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"


def _now_ms() -> int:
    return int(time.time() * 1000)


def _dec(val: Any) -> Decimal:
    return Decimal(str(val or "0")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _mask_email(email: Optional[str]) -> str:
    if not email or "@" not in email:
        return "user***"
    local, domain = email.split("@", 1)
    if len(local) <= 2:
        masked = local[0] + "***"
    else:
        masked = local[:2] + "***" + local[-1]
    return f"{masked}@{domain}"


class ReferralService:
    def get_app_base_url(self) -> str:
        return os.environ.get("APP_BASE_URL", "https://novextrade.exchange").rstrip("/")

    def build_referral_url(self, referral_code: str) -> str:
        return f"{self.get_app_base_url()}/register?ref={referral_code}"

    def generate_unique_referral_code(self) -> str:
        for _ in range(32):
            suffix = "".join(secrets.choice(_CODE_ALPHABET) for _ in range(7))
            code = f"NVX{suffix}"
            if code not in db.users_by_referral_code:
                return code
        # Fallback with longer entropy
        return f"NVX{uuid.uuid4().hex[:9].upper()}"

    def ensure_user_referral_code(self, user: Dict[str, Any]) -> str:
        code = user.get("referral_code")
        if code:
            normalized = code.strip().upper()
            db.users_by_referral_code[normalized] = user["id"]
            return normalized
        code = self.generate_unique_referral_code()
        user["referral_code"] = code
        user["updated_at"] = _now_ms()
        user_repository.save(user)
        return code

    def validate_referral_code(self, referral_code: str) -> Optional[Dict[str, Any]]:
        if not referral_code or not referral_code.strip():
            return None
        return user_repository.find_by_referral_code(referral_code.strip().upper())

    def track_click(
        self,
        referral_code: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        landing_path: str = "/register",
    ) -> Dict[str, Any]:
        code = (referral_code or "").strip().upper()
        referrer = self.validate_referral_code(code)
        if not referrer:
            raise NotFoundError("Invalid referral code")

        raw_fp = f"{ip_address or 'unknown'}|{user_agent or 'unknown'}|{code}"
        visitor_hash = hashlib.sha256(raw_fp.encode("utf-8")).hexdigest()[:32]

        click_id = f"rclk_{uuid.uuid4().hex[:12]}"
        click = {
            "id": click_id,
            "referral_code": code,
            "referrer_user_id": referrer["id"],
            "visitor_hash": visitor_hash,
            "ip_address": ip_address,
            "user_agent": (user_agent or "")[:256],
            "landing_path": (landing_path or "/register")[:256],
            "converted_user_id": None,
            "created_at": _now_ms(),
        }
        db.referral_clicks[click_id] = click
        supabase_client.queue_upsert("referral_clicks", click)
        return {
            "clickId": click_id,
            "referralCode": code,
            "referrerName": referrer.get("full_name") or "NovexTrade Partner",
        }

    def attribute_registration(
        self,
        new_user: Dict[str, Any],
        referral_code: Optional[str],
        click_id: Optional[str] = None,
        ip_address: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        if not referral_code or not referral_code.strip():
            return None

        code = referral_code.strip().upper()
        referrer = self.validate_referral_code(code)
        if not referrer:
            return None

        new_user_id = new_user["id"]
        referrer_id = referrer["id"]

        # 1. Prevent self-referral
        if referrer_id == new_user_id or (
            referrer.get("email", "").lower() == new_user.get("email", "").lower()
        ):
            raise ValidationError("Self-referrals are not permitted")

        # 2. Prevent duplicate referral for the same account
        if new_user_id in db.referral_relationships:
            return db.referral_relationships[new_user_id]

        # Basic fraud check: flag if referrer's own recent click IP matches heavily
        status = "ACTIVE"
        if ip_address:
            same_ip_count = sum(
                1
                for rel in db.referral_relationships.values()
                if rel.get("referrer_user_id") == referrer_id
                and rel.get("registration_ip") == ip_address
            )
            if same_ip_count >= 3:
                status = "FLAGGED"

        now = _now_ms()
        rel = {
            "id": f"rrel_{uuid.uuid4().hex[:12]}",
            "referrer_user_id": referrer_id,
            "referred_user_id": new_user_id,
            "referral_code": code,
            "source_click_id": click_id if (click_id and click_id in db.referral_clicks) else None,
            "registration_ip": ip_address,
            "status": status,
            "override_by_admin_id": None,
            "created_at": now,
            "updated_at": now,
        }
        db.referral_relationships[new_user_id] = rel
        supabase_client.queue_upsert("referral_relationships", rel)

        new_user["referred_by"] = referrer_id
        new_user["updated_at"] = now
        user_repository.save(new_user)

        if click_id and click_id in db.referral_clicks:
            db.referral_clicks[click_id]["converted_user_id"] = new_user_id
            supabase_client.queue_upsert("referral_clicks", db.referral_clicks[click_id])

        return rel

    def resolve_referrer_for_order(
        self,
        user_id: str,
        checkout_referral_code: Optional[str] = None,
    ) -> Optional[str]:
        """
        Returns authoritative referrer_user_id for a purchase.
        Permanent relationship cannot be overwritten by a user at checkout.
        """
        existing = db.referral_relationships.get(user_id)
        if existing:
            if existing.get("status") == "REVOKED":
                return None
            return existing["referrer_user_id"]

        # If user had no referrer on signup, allow first-time attribution at checkout (except self-referral)
        if checkout_referral_code and checkout_referral_code.strip():
            code = checkout_referral_code.strip().upper()
            referrer = self.validate_referral_code(code)
            if referrer:
                if referrer["id"] == user_id:
                    raise ValidationError("You cannot use your own referral code")
                user = user_repository.find_by_id(user_id)
                if user:
                    rel = self.attribute_registration(user, code)
                    return rel["referrer_user_id"] if rel else None
        return None

    def create_commission_for_paid_order(self, order: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Calculates and persists an idempotent referral commission strictly from
        verified order amount and admin-configured commission rates.
        """
        order_id = order["id"]
        if order_id in db.referral_commissions_by_order:
            return db.referral_commissions[db.referral_commissions_by_order[order_id]]

        referrer_id = order.get("referrer_user_id")
        referred_user_id = order.get("user_id")
        if not referrer_id or referrer_id == referred_user_id:
            return None

        rel = db.referral_relationships.get(referred_user_id)
        if rel and rel.get("status") == "REVOKED":
            return None

        cfg = db.referral_commission_config
        if not cfg.get("is_enabled", False):
            return None

        product_id = order.get("product_id")
        if product_id == "individual_pdf":
            rate = _dec(cfg.get("individual_pdf_commission_percent", "0.00"))
        elif product_id == "combo_bundle":
            rate = _dec(cfg.get("combo_commission_percent", "0.00"))
        else:
            rate = Decimal("0.00")

        if rate <= Decimal("0.00"):
            return None

        purchase_amount = _dec(order.get("amount_usd", "0.00"))
        commission_amount = (purchase_amount * rate / Decimal("100")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        if commission_amount <= Decimal("0.00"):
            return None

        now = _now_ms()
        holding_days = int(cfg.get("holding_period_days", 14))
        hold_until = now + (holding_days * 86_400_000)

        comm_id = f"rcom_{uuid.uuid4().hex[:12]}"
        commission = {
            "id": comm_id,
            "order_id": order_id,
            "order_reference": order.get("order_reference"),
            "referrer_user_id": referrer_id,
            "referred_user_id": referred_user_id,
            "product_id": product_id,
            "purchase_amount_usd": f"{purchase_amount:.2f}",
            "commission_rate_percent": f"{rate:.2f}",
            "commission_amount_usd": f"{commission_amount:.2f}",
            "status": "PENDING",
            "hold_until": hold_until,
            "approved_by": None,
            "approved_at": None,
            "payout_id": None,
            "reversal_reason": None,
            "created_at": now,
            "updated_at": now,
        }
        db.referral_commissions[comm_id] = commission
        db.referral_commissions_by_order[order_id] = comm_id
        supabase_client.queue_upsert("referral_commissions", commission)
        return commission

    def reverse_commission_for_order(self, order_id: str, reason: str) -> Optional[Dict[str, Any]]:
        comm_id = db.referral_commissions_by_order.get(order_id)
        if not comm_id:
            return None
        comm = db.referral_commissions.get(comm_id)
        if not comm:
            return None
        if comm["status"] in ("REVERSED", "CANCELLED"):
            return comm
        comm["status"] = "REVERSED"
        comm["reversal_reason"] = reason
        comm["updated_at"] = _now_ms()
        supabase_client.queue_upsert("referral_commissions", comm)
        return comm

    def get_user_referral_dashboard(self, user_id: str) -> Dict[str, Any]:
        user = user_repository.find_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        code = self.ensure_user_referral_code(user)
        url = self.build_referral_url(code)

        clicks = [c for c in db.referral_clicks.values() if c.get("referrer_user_id") == user_id]
        relationships = [
            r for r in db.referral_relationships.values() if r.get("referrer_user_id") == user_id
        ]
        referred_orders = [
            o
            for o in db.product_orders.values()
            if o.get("referrer_user_id") == user_id and o.get("status") == "PAID"
        ]
        commissions = [
            c for c in db.referral_commissions.values() if c.get("referrer_user_id") == user_id
        ]

        total_clicks = len(clicks)
        total_registrations = len(relationships)
        paying_customers = {o["user_id"] for o in referred_orders}
        total_referred_customers = len(paying_customers)
        total_referred_purchases = len(referred_orders)

        pending_usd = sum((_dec(c["commission_amount_usd"]) for c in commissions if c["status"] == "PENDING"), Decimal("0.00"))
        approved_usd = sum((_dec(c["commission_amount_usd"]) for c in commissions if c["status"] == "APPROVED"), Decimal("0.00"))
        paid_usd = sum((_dec(c["commission_amount_usd"]) for c in commissions if c["status"] == "PAID"), Decimal("0.00"))
        reversed_usd = sum((_dec(c["commission_amount_usd"]) for c in commissions if c["status"] in ("CANCELLED", "REVERSED")), Decimal("0.00"))

        conversion_rate = (
            (Decimal(total_registrations) / Decimal(total_clicks) * Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            if total_clicks > 0
            else Decimal("0.00")
        )

        # Build unified activity table (commissions + registrations)
        activity: List[Dict[str, Any]] = []
        for c in commissions:
            ref_user = user_repository.find_by_id(c["referred_user_id"])
            product = db.products.get(c["product_id"], {})
            activity.append({
                "id": c["id"],
                "type": "COMMISSION",
                "referredUser": _mask_email(ref_user.get("email") if ref_user else None),
                "productName": product.get("name", c["product_id"]),
                "orderReference": c.get("order_reference", c["order_id"]),
                "purchaseAmountUsd": c["purchase_amount_usd"],
                "commissionRatePercent": c["commission_rate_percent"],
                "commissionAmountUsd": c["commission_amount_usd"],
                "status": c["status"],
                "reversalReason": c.get("reversal_reason"),
                "createdAt": c["created_at"],
            })

        for r in relationships:
            ref_user = user_repository.find_by_id(r["referred_user_id"])
            activity.append({
                "id": r["id"],
                "type": "REGISTRATION",
                "referredUser": _mask_email(ref_user.get("email") if ref_user else None),
                "productName": "Account Registration",
                "orderReference": None,
                "purchaseAmountUsd": "0.00",
                "commissionRatePercent": "0.00",
                "commissionAmountUsd": "0.00",
                "status": r["status"],
                "reversalReason": None,
                "createdAt": r["created_at"],
            })

        activity.sort(key=lambda item: item["createdAt"], reverse=True)

        cfg = db.referral_commission_config
        return {
            "referralCode": code,
            "referralUrl": url,
            "stats": {
                "totalClicks": total_clicks,
                "totalRegistrations": total_registrations,
                "totalReferredCustomers": total_referred_customers,
                "totalReferredPurchases": total_referred_purchases,
                "pendingCommissionsUsd": f"{pending_usd:.2f}",
                "approvedCommissionsUsd": f"{approved_usd:.2f}",
                "paidCommissionsUsd": f"{paid_usd:.2f}",
                "cancelledOrReversedCommissionsUsd": f"{reversed_usd:.2f}",
                "conversionRatePercent": f"{conversion_rate:.2f}",
            },
            "programConfig": {
                "isEnabled": bool(cfg.get("is_enabled", False)),
                "individualPdfCommissionPercent": str(cfg.get("individual_pdf_commission_percent", "0.00")),
                "comboCommissionPercent": str(cfg.get("combo_commission_percent", "0.00")),
                "minPayoutThresholdUsd": str(cfg.get("min_payout_threshold_usd", "50.00")),
                "holdingPeriodDays": int(cfg.get("holding_period_days", 14)),
                "approvalMode": cfg.get("approval_mode", "MANUAL"),
                "termsAndConditions": cfg.get("terms_and_conditions", ""),
            },
            "activity": activity[:100],
        }

    # -------------------------------------------------------------------------
    # ADMIN CONTROLS
    # -------------------------------------------------------------------------

    def update_commission_config(self, admin_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        cfg = db.referral_commission_config
        if "is_enabled" in payload:
            cfg["is_enabled"] = bool(payload["is_enabled"])
        if "individual_pdf_commission_percent" in payload:
            val = _dec(payload["individual_pdf_commission_percent"])
            if val < Decimal("0.00") or val > Decimal("100.00"):
                raise ValidationError("Individual PDF commission percent must be between 0 and 100")
            cfg["individual_pdf_commission_percent"] = f"{val:.2f}"
        if "combo_commission_percent" in payload:
            val = _dec(payload["combo_commission_percent"])
            if val < Decimal("0.00") or val > Decimal("100.00"):
                raise ValidationError("Combo commission percent must be between 0 and 100")
            cfg["combo_commission_percent"] = f"{val:.2f}"
        if "min_payout_threshold_usd" in payload:
            val = _dec(payload["min_payout_threshold_usd"])
            if val < Decimal("0.00"):
                raise ValidationError("Minimum payout threshold cannot be negative")
            cfg["min_payout_threshold_usd"] = f"{val:.2f}"
        if "holding_period_days" in payload:
            days = int(payload["holding_period_days"])
            if days < 0 or days > 365:
                raise ValidationError("Holding period must be between 0 and 365 days")
            cfg["holding_period_days"] = days
        if "approval_mode" in payload:
            mode = str(payload["approval_mode"]).upper()
            if mode not in ("MANUAL", "AUTO_AFTER_HOLD"):
                raise ValidationError("approval_mode must be MANUAL or AUTO_AFTER_HOLD")
            cfg["approval_mode"] = mode
        if "auto_payout_enabled" in payload:
            cfg["auto_payout_enabled"] = bool(payload["auto_payout_enabled"])
        if "terms_and_conditions" in payload:
            cfg["terms_and_conditions"] = str(payload["terms_and_conditions"]).strip()

        cfg["updated_by"] = admin_id
        cfg["updated_at"] = _now_ms()
        supabase_client.queue_upsert("referral_commission_config", cfg)
        self._audit(admin_id, "ADMIN_REFERRAL_CONFIG_UPDATED", cfg)
        return cfg

    def update_commission_status(
        self,
        commission_id: str,
        action: str,
        admin_id: str,
        reason: Optional[str] = None,
        payout_reference: Optional[str] = None,
    ) -> Dict[str, Any]:
        comm = db.referral_commissions.get(commission_id)
        if not comm:
            raise NotFoundError(f"Commission '{commission_id}' not found")

        act = action.upper()
        now = _now_ms()
        if act == "APPROVE":
            if comm["status"] != "PENDING":
                raise ValidationError(f"Cannot approve commission in status {comm['status']}")
            comm["status"] = "APPROVED"
            comm["approved_by"] = admin_id
            comm["approved_at"] = now
        elif act == "REJECT":
            if comm["status"] in ("PAID", "REVERSED", "CANCELLED"):
                raise ValidationError(f"Cannot reject commission in status {comm['status']}")
            comm["status"] = "CANCELLED"
            comm["reversal_reason"] = reason or "Rejected by administrator"
        elif act == "MARK_PAID":
            if comm["status"] != "APPROVED":
                raise ValidationError("Commission must be APPROVED before marking as PAID")
            payout_id = f"rpay_{uuid.uuid4().hex[:10]}"
            payout = {
                "id": payout_id,
                "referrer_user_id": comm["referrer_user_id"],
                "amount_usd": comm["commission_amount_usd"],
                "payout_method": "ADMIN_MANUAL",
                "payout_destination": "Configured Payout Channel",
                "status": "PAID",
                "reference": payout_reference or f"MANUAL-{now}",
                "processed_by": admin_id,
                "processed_at": now,
                "created_at": now,
            }
            db.referral_payouts[payout_id] = payout
            supabase_client.queue_upsert("referral_payouts", payout)
            comm["status"] = "PAID"
            comm["payout_id"] = payout_id
        else:
            raise ValidationError("Invalid action. Use APPROVE, REJECT, or MARK_PAID.")

        comm["updated_at"] = now
        supabase_client.queue_upsert("referral_commissions", comm)
        self._audit(admin_id, f"ADMIN_COMMISSION_{act}", {"commission_id": commission_id, "reason": reason})
        return comm

    def get_admin_referral_overview(self, search: Optional[str] = None) -> Dict[str, Any]:
        q = (search or "").strip().lower()
        all_users = list(db.users.values())
        users_with_codes = [u for u in all_users if u.get("referral_code")]

        commissions = list(db.referral_commissions.values())
        total_comm_usd = sum((_dec(c["commission_amount_usd"]) for c in commissions if c["status"] != "CANCELLED" and c["status"] != "REVERSED"), Decimal("0.00"))
        pending_usd = sum((_dec(c["commission_amount_usd"]) for c in commissions if c["status"] == "PENDING"), Decimal("0.00"))
        approved_usd = sum((_dec(c["commission_amount_usd"]) for c in commissions if c["status"] == "APPROVED"), Decimal("0.00"))
        paid_usd = sum((_dec(c["commission_amount_usd"]) for c in commissions if c["status"] == "PAID"), Decimal("0.00"))

        paid_referred_orders = [
            o for o in db.product_orders.values()
            if o.get("referrer_user_id") and o.get("status") == "PAID"
        ]

        enriched_relationships = []
        for rel in db.referral_relationships.values():
            referrer = user_repository.find_by_id(rel["referrer_user_id"]) or {}
            referred = user_repository.find_by_id(rel["referred_user_id"]) or {}
            row = {
                **rel,
                "referrer_email": referrer.get("email"),
                "referred_email": referred.get("email"),
            }
            if not q or (
                q in (row.get("referral_code") or "").lower()
                or q in (row.get("referrer_email") or "").lower()
                or q in (row.get("referred_email") or "").lower()
            ):
                enriched_relationships.append(row)
        enriched_relationships.sort(key=lambda r: r["created_at"], reverse=True)

        enriched_commissions = []
        for c in commissions:
            referrer = user_repository.find_by_id(c["referrer_user_id"]) or {}
            referred = user_repository.find_by_id(c["referred_user_id"]) or {}
            row = {
                **c,
                "referrer_email": referrer.get("email"),
                "referred_email": referred.get("email"),
                "product_name": db.products.get(c["product_id"], {}).get("name", c["product_id"]),
            }
            if not q or (
                q in (row.get("referrer_email") or "").lower()
                or q in (row.get("referred_email") or "").lower()
                or q in (row.get("order_reference") or "").lower()
            ):
                enriched_commissions.append(row)
        enriched_commissions.sort(key=lambda c: c["created_at"], reverse=True)

        return {
            "summary": {
                "totalRegisteredUsers": len(all_users),
                "totalReferralLinks": len(users_with_codes),
                "totalReferralClicks": len(db.referral_clicks),
                "successfulRegistrations": len(db.referral_relationships),
                "referredPurchases": len(paid_referred_orders),
                "totalCommissionsUsd": f"{total_comm_usd:.2f}",
                "pendingCommissionsUsd": f"{pending_usd:.2f}",
                "approvedCommissionsUsd": f"{approved_usd:.2f}",
                "paidCommissionsUsd": f"{paid_usd:.2f}",
                "flaggedRelationships": sum(1 for r in db.referral_relationships.values() if r.get("status") == "FLAGGED"),
            },
            "config": db.referral_commission_config,
            "relationships": enriched_relationships[:100],
            "commissions": enriched_commissions[:100],
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


referral_service = ReferralService()
