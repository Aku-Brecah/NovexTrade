"""
NovexTrade Authentication Security, Password Validation & Account Recovery Service
Handles strict email/password validation, anti-enumeration password reset tokens,
single-use token consumption, and server-side session revocation.
"""
import hashlib
import os
import re
import secrets
import time
import uuid
from typing import Any, Dict, Optional

from syncnode.common.errors import ValidationError, UnauthorizedError
from syncnode.common.logger import Logger
from syncnode.database.db import db
from syncnode.database.repository import user_repository
from syncnode.database.supabase_client import supabase_client
from syncnode.security.crypto import hash_password, verify_password

logger = Logger("AuthRecovery")

EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")
RESET_TOKEN_TTL_MS = 30 * 60 * 1000  # 30 minutes


def _now_ms() -> int:
    return int(time.time() * 1000)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def validate_email_address(email: str) -> str:
    cleaned = (email or "").strip().lower()
    if not cleaned or len(cleaned) > 254 or not EMAIL_REGEX.match(cleaned):
        raise ValidationError("Please provide a valid email address")
    return cleaned


def validate_password_strength(password: str) -> None:
    if not password or len(password) < 8:
        raise ValidationError("Password must be at least 8 characters long")
    if len(password) > 128:
        raise ValidationError("Password must not exceed 128 characters")
    if not re.search(r"[A-Z]", password):
        raise ValidationError("Password must contain at least one uppercase letter")
    if not re.search(r"[a-z]", password):
        raise ValidationError("Password must contain at least one lowercase letter")
    if not re.search(r"[0-9]", password):
        raise ValidationError("Password must contain at least one number")


class AuthRecoveryService:
    async def request_password_reset(
        self,
        email: str,
        request_ip: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Generates a cryptographically secure, single-use password reset token.
        Always returns a generic anti-enumeration response regardless of whether
        the email exists in the database.
        """
        cleaned_email = validate_email_address(email)
        user = user_repository.find_by_email(cleaned_email)
        now = _now_ms()

        generic_response = {
            "success": True,
            "message": "If an account with that email exists, a password reset link has been sent.",
        }

        if not user or user.get("is_suspended"):
            return generic_response

        # Invalidate any prior unused reset tokens for this user
        for tok in db.password_reset_tokens.values():
            if tok["user_id"] == user["id"] and tok["used_at"] is None:
                tok["used_at"] = now

        raw_token = secrets.token_urlsafe(32)
        t_hash = hash_token(raw_token)
        record = {
            "id": f"prst_{uuid.uuid4().hex[:12]}",
            "user_id": user["id"],
            "token_hash": t_hash,
            "expires_at": now + RESET_TOKEN_TTL_MS,
            "used_at": None,
            "request_ip": request_ip,
            "created_at": now,
        }
        db.password_reset_tokens[t_hash] = record
        supabase_client.queue_upsert("password_reset_tokens", record)

        app_base = os.environ.get("APP_BASE_URL", "https://novextrade.exchange").rstrip("/")
        reset_link = f"{app_base}/reset-password?token={raw_token}"

        await self._send_reset_email(cleaned_email, reset_link)
        return generic_response

    async def _send_reset_email(self, recipient: str, reset_link: str) -> None:
        smtp_host = os.environ.get("SMTP_HOST", "").strip()
        smtp_user = os.environ.get("SMTP_USER", "").strip()
        smtp_pass = os.environ.get("SMTP_PASSWORD", "").strip()
        smtp_port = int(os.environ.get("SMTP_PORT", "587"))
        from_addr = os.environ.get("SMTP_FROM", smtp_user or "security@novextrade.exchange")

        if not smtp_host or not smtp_user or not smtp_pass:
            logger.info(f"Password reset requested for {recipient} (SMTP not configured; link generated securely).")
            return

        try:
            import aiosmtplib
            from email.message import EmailMessage

            msg = EmailMessage()
            msg["From"] = from_addr
            msg["To"] = recipient
            msg["Subject"] = "NovexTrade — Password Reset Request"
            msg.set_content(
                f"You requested a password reset for your NovexTrade account.\n\n"
                f"Reset your password (link expires in 30 minutes):\n{reset_link}\n\n"
                f"If you did not request this, you can safely ignore this email."
            )
            await aiosmtplib.send(
                msg,
                hostname=smtp_host,
                port=smtp_port,
                username=smtp_user,
                password=smtp_pass,
                start_tls=True,
                timeout=10.0,
            )
        except Exception as exc:
            logger.warn(f"Failed to send password reset email via SMTP: {exc}")

    def reset_password_with_token(self, raw_token: str, new_password: str, confirm_password: Optional[str] = None) -> Dict[str, Any]:
        if not raw_token or len(raw_token.strip()) < 16:
            raise ValidationError("Invalid or malformed password reset token")
        if confirm_password is not None and new_password != confirm_password:
            raise ValidationError("Passwords do not match")
        validate_password_strength(new_password)

        t_hash = hash_token(raw_token.strip())
        record = db.password_reset_tokens.get(t_hash)
        if not record:
            raise ValidationError("Invalid or expired password reset token")

        now = _now_ms()
        if record.get("used_at") is not None:
            raise ValidationError("This password reset link has already been used")
        if now > int(record.get("expires_at", 0)):
            raise ValidationError("This password reset link has expired. Please request a new one.")

        user = user_repository.find_by_id(record["user_id"])
        if not user:
            raise ValidationError("Account associated with this reset token no longer exists")
        if user.get("is_suspended"):
            raise UnauthorizedError("Account is suspended")

        # Update password and rotate token_version to invalidate all active sessions
        user["password_hash"] = hash_password(new_password)
        user["token_version"] = int(user.get("token_version", 0)) + 1
        user["updated_at"] = now
        user_repository.save(user)

        record["used_at"] = now
        supabase_client.queue_upsert("password_reset_tokens", record)

        return {"success": True, "message": "Password has been reset successfully. Please sign in with your new password."}

    def change_password(
        self,
        user: Dict[str, Any],
        current_password: str,
        new_password: str,
        confirm_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        if not user.get("password_hash") or not verify_password(current_password, user["password_hash"]):
            raise UnauthorizedError("Current password is incorrect")
        if confirm_password is not None and new_password != confirm_password:
            raise ValidationError("New passwords do not match")
        if current_password == new_password:
            raise ValidationError("New password must be different from your current password")
        validate_password_strength(new_password)

        now = _now_ms()
        user["password_hash"] = hash_password(new_password)
        user["token_version"] = int(user.get("token_version", 0)) + 1
        user["updated_at"] = now
        user_repository.save(user)
        return user

    def revoke_token(self, raw_token: Optional[str]) -> None:
        if raw_token and raw_token.strip():
            db.revoked_tokens.add(hash_token(raw_token.strip()))

    def is_token_revoked(self, raw_token: str) -> bool:
        return hash_token(raw_token.strip()) in db.revoked_tokens


auth_recovery_service = AuthRecoveryService()
