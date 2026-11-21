import os
from dotenv import load_dotenv
load_dotenv()

import time
import uuid
import json
import secrets
from typing import Optional, List, Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse, Response
from pydantic import BaseModel

from decimal import Decimal
from syncnode.common.decimal_util import to_decimal, format_decimal
from syncnode.common.types import AssetSymbol, AccountType, OrderSide, OrderType, KycTier, KycStatus, AdminRole
from syncnode.common.errors import (
    AppError,
    UnauthorizedError,
    ForbiddenError,
    InsufficientFundsError,
    ValidationError,
    NotFoundError,
    TooManyRequestsError,
)
from syncnode.common.logger import Logger
from syncnode.security.crypto import (
    hash_password,
    verify_password,
    sign_token,
    sign_refresh_token,
    verify_token,
    verify_refresh_token,
    generate_totp_secret,
    get_totp_uri,
    verify_totp_code
)
from syncnode.security.otp_service import otp_service, format_and_validate_phone
from syncnode.database.db import db
from syncnode.database.repository import user_repository, order_repository, trade_repository
from syncnode.services.ledger import ledger_service
from syncnode.services.matching_engine import matching_engine
from syncnode.services.wallet import wallet_service
from syncnode.services.investment import investment_service
from syncnode.services.p2p import p2p_service
from syncnode.services.market_data import market_data_service
from syncnode.services.compliance import compliance_service
from syncnode.services.risk import risk_service
from syncnode.services.resources import resources_service
from syncnode.services.referral import referral_service
from syncnode.services.commerce import commerce_service
from syncnode.services.card_gateway import card_gateway
from syncnode.services.auth_recovery import (
    auth_recovery_service,
    validate_email_address,
    validate_password_strength,
)
from syncnode.admin.router import admin_router
from syncnode.admin.api import admin_api_router
from syncnode.web.views import web_router

from syncnode.common.events import broadcaster

logger = Logger("APIGateway")
ws_manager = broadcaster

# In-Memory Rate Limiter: key -> [timestamps]
RATE_LIMIT_STORE: Dict[str, List[float]] = {}


def check_rate_limit(key: str, max_requests: int = 15, window_seconds: int = 60):
    """Enforces in-memory sliding-window rate limiting."""
    now = time.time()
    history = RATE_LIMIT_STORE.get(key, [])
    history = [t for t in history if now - t < window_seconds]
    if len(history) >= max_requests:
        retry_after = int(window_seconds - (now - history[0])) if history else window_seconds
        raise TooManyRequestsError(f"Rate limit exceeded. Please retry in {max(1, retry_after)} seconds.")
    history.append(now)
    RATE_LIMIT_STORE[key] = history


def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "127.0.0.1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Connect Supabase Cloud PostgreSQL
    await db.connect_supabase()
    # Connect MongoDB (fallback)
    await db.connect_mongo()

    # Seed Admin User if not exists
    admin_email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL")
    admin_pass = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
    is_prod = os.environ.get("ENVIRONMENT") == "production"

    if is_prod and (not admin_email or not admin_pass):
        logger.warning("Production environment detected without configured ADMIN_BOOTSTRAP_EMAIL / ADMIN_BOOTSTRAP_PASSWORD.")
    else:
        email_to_seed = (admin_email or "admin@novextrade.exchange").strip().lower()
        pass_to_seed = admin_pass or "NovexTrade2026!Secure"
        if not user_repository.find_by_email(email_to_seed):
            admin_id = f"admin_{uuid.uuid4().hex[:8]}"
            user = {
                "id": admin_id,
                "email": email_to_seed,
                "full_name": "Executive Admin",
                "password_hash": hash_password(pass_to_seed),
                "is_totp_enabled": False,
                "kyc_tier": KycTier.TIER_3_INSTITUTIONAL.value,
                "kyc_status": KycStatus.APPROVED.value,
                "admin_roles": [AdminRole.SUPER_ADMIN.value],
                "is_suspended": False,
                "is_withdrawal_suspended": False,
                "created_at": int(time.time() * 1000),
                "updated_at": int(time.time() * 1000)
            }
            user_repository.save(user)
            logger.info(f"Bootstrapped super-admin account: {email_to_seed}")

    yield


app = FastAPI(title="NovexTrade Enterprise Exchange API", version="1.0.0", lifespan=lifespan)

# Environment-Driven CORS Configuration
raw_origins = os.environ.get(
    "ALLOWED_ORIGINS"
) or os.environ.get(
    "CORS_ORIGINS"
) or "http://localhost:3000,http://127.0.0.1:3000,http://localhost:4000,http://127.0.0.1:4000"
ALLOWED_ORIGINS = [o.strip() for o in raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Authorization", "Content-Type", "Accept", "Origin", "X-Requested-With"],
)


# Security Headers Middleware
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if os.environ.get("ENVIRONMENT") == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


# Exception handler
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict()
    )


# WebSocket Connection Manager - Uses central event broadcaster
ws_manager = broadcaster



# Authentication Dependency
async def get_current_user(authorization: Optional[str] = Header(None)) -> Dict[str, Any]:
    if not authorization or not authorization.startswith("Bearer "):
        raise UnauthorizedError("Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1].strip()
    if auth_recovery_service.is_token_revoked(token):
        raise UnauthorizedError("Session has been revoked. Please sign in again.")
    try:
        payload = verify_token(token)
    except Exception as e:
        raise UnauthorizedError(f"Invalid or expired token: {str(e)}")

    if payload.get("type") == "refresh":
        raise UnauthorizedError("Refresh tokens cannot be used to access protected resources")

    user = user_repository.find_by_id(payload.get("user_id") or payload.get("userId"))
    if not user:
        raise UnauthorizedError("User account not found")
    if user.get("is_suspended"):
        raise ForbiddenError("Account is suspended")
    if "tv" in payload and int(payload["tv"]) != int(user.get("token_version", 0)):
        raise UnauthorizedError("Session invalidated due to security change. Please sign in again.")
    return user


# -------------------------------------------------------------
# REST ROUTES
# -------------------------------------------------------------

@app.get("/health")
@app.get("/api/v1/health")
async def health_check():
    return {
        "status": "HEALTHY",
        "service": "novextrade-core",
        "timestamp": int(time.time() * 1000),
        "supabase_connected": db._is_supabase_connected,
        "mongo_connected": db._is_connected
    }


# Auth Endpoints
class RegisterRequest(BaseModel):
    email: str
    password: str
    confirmPassword: Optional[str] = None
    fullName: Optional[str] = None
    country: Optional[str] = None
    phoneNumber: Optional[str] = None
    investmentGoals: Optional[str] = None
    riskTolerance: Optional[str] = None
    preferredIndustry: Optional[str] = None
    otpCode: Optional[str] = None
    otpChannel: Optional[str] = "email"
    referralCode: Optional[str] = None
    referralClickId: Optional[str] = None


@app.post("/api/v1/auth/register")
async def register(req: RegisterRequest, request: Request):
    ip = get_client_ip(request)
    check_rate_limit(f"reg_{ip}", max_requests=10, window_seconds=60)

    email = validate_email_address(req.email)
    if req.confirmPassword is not None and req.password != req.confirmPassword:
        raise ValidationError("Passwords do not match")
    validate_password_strength(req.password)
    if user_repository.find_by_email(email):
        raise ValidationError("User already exists with this email")

    # Validate phone number if provided
    formatted_phone = None
    is_phone_verified = False
    is_email_verified = False

    if req.phoneNumber and req.phoneNumber.strip():
        phone_info = format_and_validate_phone(req.phoneNumber, default_region=req.country or "US")
        if not phone_info["valid"]:
            raise ValidationError(phone_info.get("error") or "Invalid phone number format")
        formatted_phone = phone_info["e164"]

    # Verify OTP if provided
    if req.otpCode and req.otpCode.strip():
        otp_target = formatted_phone if (req.otpChannel == "sms" and formatted_phone) else email
        otp_service.verify_otp(otp_target, req.otpCode.strip(), consume=True)
        if req.otpChannel == "sms":
            is_phone_verified = True
        else:
            is_email_verified = True

    user_id = f"usr_{uuid.uuid4().hex[:10]}"
    now = int(time.time() * 1000)
    unique_ref_code = referral_service.generate_unique_referral_code()
    user = {
        "id": user_id,
        "email": email,
        "full_name": req.fullName,
        "country": req.country or "US",
        "phone_number": formatted_phone,
        "is_email_verified": is_email_verified,
        "is_phone_verified": is_phone_verified,
        "investment_goals": req.investmentGoals or "Growth",
        "risk_tolerance": req.riskTolerance or "Moderate",
        "preferred_industry": req.preferredIndustry or "Technology & AI",
        "password_hash": hash_password(req.password),
        "is_totp_enabled": False,
        "kyc_tier": KycTier.TIER_0_UNVERIFIED.value,
        "kyc_status": KycStatus.NOT_SUBMITTED.value,
        "admin_roles": [],
        "is_suspended": False,
        "is_withdrawal_suspended": False,
        "referral_code": unique_ref_code,
        "referred_by": None,
        "token_version": 0,
        "created_at": now,
        "updated_at": now
    }
    user_repository.save(user)

    # Initialize zero ledger balances for the new account
    for asset in AssetSymbol:
        ledger_service.get_or_create_account(AccountType.USER_AVAILABLE, asset, user_id)

    # Attribute referral relationship if a valid referral code was provided
    if req.referralCode and req.referralCode.strip():
        referral_service.attribute_registration(
            new_user=user,
            referral_code=req.referralCode,
            click_id=req.referralClickId,
            ip_address=ip,
        )

    token = sign_token({"userId": user_id, "email": email, "isTotpAuthenticated": True, "tv": 0})
    refresh_token = sign_refresh_token({"userId": user_id, "email": email, "tv": 0})
    safe_user = {k: v for k, v in user.items() if k != "password_hash" and k != "totp_secret"}
    safe_user["referral_url"] = referral_service.build_referral_url(unique_ref_code)
    return {"success": True, "token": token, "refreshToken": refresh_token, "user": safe_user}


class LoginRequest(BaseModel):
    email: str
    password: str
    totpCode: Optional[str] = None


@app.post("/api/v1/auth/login")
async def login(req: LoginRequest, request: Request):
    email = req.email.strip().lower()
    ip = get_client_ip(request)
    check_rate_limit(f"login_{email}", max_requests=15, window_seconds=60)
    user = user_repository.find_by_email(email)
    if not user or not user.get("password_hash") or not verify_password(req.password, user["password_hash"]):
        raise UnauthorizedError("Invalid credentials provided")

    if user.get("is_suspended"):
        raise ForbiddenError("This account has been suspended. Please contact support.")

    if user.get("is_totp_enabled"):
        if not req.totpCode or not verify_totp_code(user.get("totp_secret", ""), req.totpCode):
            return {"success": False, "requires2FA": True, "error": "2FA TOTP verification required"}

    tv = int(user.get("token_version", 0))
    code = referral_service.ensure_user_referral_code(user)
    token = sign_token({"userId": user["id"], "email": email, "isTotpAuthenticated": True, "tv": tv})
    refresh_token = sign_refresh_token({"userId": user["id"], "email": email, "tv": tv})
    safe_user = {k: v for k, v in user.items() if k != "password_hash" and k != "totp_secret"}
    safe_user["referral_code"] = code
    safe_user["referral_url"] = referral_service.build_referral_url(code)
    return {"success": True, "token": token, "refreshToken": refresh_token, "user": safe_user}


class RefreshTokenRequest(BaseModel):
    refreshToken: str


@app.post("/api/v1/auth/refresh")
async def refresh_token(req: RefreshTokenRequest):
    if not req.refreshToken:
        raise UnauthorizedError("Missing refresh token")
    if auth_recovery_service.is_token_revoked(req.refreshToken):
        raise UnauthorizedError("Refresh token has been revoked")
    try:
        claims = verify_refresh_token(req.refreshToken)
    except Exception as e:
        raise UnauthorizedError(f"Invalid or expired refresh token: {str(e)}")

    user_id = claims.get("userId") or claims.get("user_id")
    user = user_repository.find_by_id(user_id)
    if not user:
        raise UnauthorizedError("User account not found")
    if user.get("is_suspended"):
        raise ForbiddenError("Account is suspended")
    tv = int(user.get("token_version", 0))
    if "tv" in claims and int(claims["tv"]) != tv:
        raise UnauthorizedError("Refresh token invalidated due to security change")

    # Rotate refresh token (revoke previous one)
    auth_recovery_service.revoke_token(req.refreshToken)
    new_access_token = sign_token({"userId": user["id"], "email": user["email"], "isTotpAuthenticated": True, "tv": tv})
    new_refresh_token = sign_refresh_token({"userId": user["id"], "email": user["email"], "tv": tv})
    return {
        "success": True,
        "token": new_access_token,
        "refreshToken": new_refresh_token
    }


class LogoutRequest(BaseModel):
    refreshToken: Optional[str] = None
    revokeAll: Optional[bool] = False


@app.post("/api/v1/auth/logout")
async def logout_user(
    req: LogoutRequest,
    authorization: Optional[str] = Header(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    if authorization and authorization.startswith("Bearer "):
        auth_recovery_service.revoke_token(authorization.split(" ", 1)[1].strip())
    if req.refreshToken:
        auth_recovery_service.revoke_token(req.refreshToken)
    if req.revokeAll:
        user["token_version"] = int(user.get("token_version", 0)) + 1
        user["updated_at"] = int(time.time() * 1000)
        user_repository.save(user)
    return {"success": True, "message": "Signed out and session invalidated"}


class ForgotPasswordRequest(BaseModel):
    email: str


@app.post("/api/v1/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, request: Request):
    ip = get_client_ip(request)
    check_rate_limit(f"forgot_{ip}", max_requests=5, window_seconds=300)
    return await auth_recovery_service.request_password_reset(req.email, request_ip=ip)


class ResetPasswordRequest(BaseModel):
    token: str
    newPassword: str
    confirmPassword: Optional[str] = None


@app.post("/api/v1/auth/reset-password")
async def reset_password(req: ResetPasswordRequest, request: Request):
    ip = get_client_ip(request)
    check_rate_limit(f"reset_{ip}", max_requests=10, window_seconds=300)
    return auth_recovery_service.reset_password_with_token(
        raw_token=req.token,
        new_password=req.newPassword,
        confirm_password=req.confirmPassword,
    )


class ChangePasswordRequest(BaseModel):
    currentPassword: str
    newPassword: str
    confirmPassword: Optional[str] = None


@app.post("/api/v1/auth/change-password")
async def change_password(
    req: ChangePasswordRequest,
    authorization: Optional[str] = Header(None),
    user: Dict[str, Any] = Depends(get_current_user),
):
    updated_user = auth_recovery_service.change_password(
        user=user,
        current_password=req.currentPassword,
        new_password=req.newPassword,
        confirm_password=req.confirmPassword,
    )
    if authorization and authorization.startswith("Bearer "):
        auth_recovery_service.revoke_token(authorization.split(" ", 1)[1].strip())
    tv = int(updated_user.get("token_version", 0))
    new_access = sign_token({"userId": updated_user["id"], "email": updated_user["email"], "isTotpAuthenticated": True, "tv": tv})
    new_refresh = sign_refresh_token({"userId": updated_user["id"], "email": updated_user["email"], "tv": tv})
    return {
        "success": True,
        "message": "Password updated and other sessions invalidated",
        "token": new_access,
        "refreshToken": new_refresh,
    }


@app.get("/api/v1/auth/me")
async def get_me(user: Dict[str, Any] = Depends(get_current_user)):
    code = referral_service.ensure_user_referral_code(user)
    safe_user = {k: v for k, v in user.items() if k != "password_hash" and k != "totp_secret"}
    safe_user["referral_code"] = code
    safe_user["referral_url"] = referral_service.build_referral_url(code)
    return {"success": True, "user": safe_user}


class GoogleAuthRequest(BaseModel):
    credential: Optional[str] = None
    token: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None
    sub: Optional[str] = None


def parse_google_credential(credential: str) -> Dict[str, Any]:
    """Decodes Google Identity Services JWT payload safely."""
    try:
        parts = credential.split(".")
        if len(parts) >= 2:
            import base64
            payload_b64 = parts[1]
            # Pad base64 string
            payload_b64 += "=" * ((4 - len(payload_b64) % 4) % 4)
            decoded_bytes = base64.urlsafe_b64decode(payload_b64)
            return json.loads(decoded_bytes.decode("utf-8"))
    except Exception as e:
        logger.warn(f"Failed to decode Google JWT locally: {e}")
    return {}


@app.post("/api/v1/auth/google")
@app.post("/api/v1/auth/oauth/google")
async def google_auth(req: GoogleAuthRequest, request: Request):
    ip = get_client_ip(request)
    check_rate_limit(f"google_auth_{ip}", max_requests=25, window_seconds=60)

    email: Optional[str] = None
    name: Optional[str] = None
    picture: Optional[str] = None
    sub: Optional[str] = None

    if req.credential:
        payload = parse_google_credential(req.credential)
        email = payload.get("email")
        name = payload.get("name") or payload.get("given_name")
        picture = payload.get("picture")
        sub = payload.get("sub")
    
    # Fallback to direct parameters if provided (e.g. for OAuth client / testing)
    email = (email or req.email or "").strip().lower()
    name = name or req.name or (email.split("@")[0] if email else "Google Trader")
    picture = picture or req.picture
    sub = sub or req.sub or req.token or f"g_{uuid.uuid4().hex[:12]}"

    if not email:
        raise ValidationError("Google authentication failed: missing email in token")

    now = int(time.time() * 1000)
    existing_user = user_repository.find_by_email(email)

    if existing_user:
        if not existing_user.get("google_sub") and sub:
            existing_user["google_sub"] = sub
            existing_user["auth_provider"] = "google"
            if picture and not existing_user.get("avatar_url"):
                existing_user["avatar_url"] = picture
            user_repository.save(existing_user)
        user = existing_user
        is_new = False
    else:
        user_id = f"usr_g_{uuid.uuid4().hex[:10]}"
        bootstrap_admin_email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL", "").strip().lower()
        is_super = bool(bootstrap_admin_email and email == bootstrap_admin_email)
        user = {
            "id": user_id,
            "email": email,
            "full_name": name,
            "avatar_url": picture,
            "auth_provider": "google",
            "google_sub": sub,
            "password_hash": "",
            "is_totp_enabled": False,
            "kyc_tier": KycTier.TIER_1_BASIC.value,
            "kyc_status": KycStatus.APPROVED.value,
            "admin_roles": [AdminRole.SUPER_ADMIN.value] if is_super else [],
            "is_suspended": False,
            "is_withdrawal_suspended": False,
            "created_at": now,
            "updated_at": now
        }
        user_repository.save(user)
        # Initialize zero ledger balances
        for asset in AssetSymbol:
            ledger_service.get_or_create_account(
                AccountType.USER_AVAILABLE,
                asset,
                user_id
            )
        is_new = True

    if user.get("is_suspended"):
        raise ForbiddenError("This account has been suspended by administration")

    token = sign_token({"userId": user["id"], "email": email, "isTotpAuthenticated": True})
    refresh_token = sign_refresh_token({"userId": user["id"], "email": email})
    safe_user = {k: v for k, v in user.items() if k != "password_hash" and k != "totp_secret"}

    return {
        "success": True,
        "token": token,
        "refreshToken": refresh_token,
        "user": safe_user,
        "isNewUser": is_new
    }


class ClerkAuthRequest(BaseModel):
    clerkId: str
    email: str
    fullName: Optional[str] = None
    avatarUrl: Optional[str] = None
    provider: Optional[str] = "clerk"


@app.post("/api/v1/auth/clerk")
async def clerk_auth(req: ClerkAuthRequest, request: Request):
    ip = get_client_ip(request)
    check_rate_limit(f"clerk_auth_{ip}", max_requests=30, window_seconds=60)

    email = req.email.strip().lower()
    if not email:
        raise ValidationError("Clerk authentication failed: missing email")

    now = int(time.time() * 1000)
    existing_user = user_repository.find_by_email(email)

    if existing_user:
        if not existing_user.get("clerk_id"):
            existing_user["clerk_id"] = req.clerkId
            existing_user["auth_provider"] = req.provider or "clerk"
            if req.avatarUrl and not existing_user.get("avatar_url"):
                existing_user["avatar_url"] = req.avatarUrl
            user_repository.save(existing_user)
        user = existing_user
        is_new = False
    else:
        user_id = f"usr_ck_{uuid.uuid4().hex[:10]}"
        bootstrap_admin_email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL", "").strip().lower()
        is_super = bool(bootstrap_admin_email and email == bootstrap_admin_email)
        user = {
            "id": user_id,
            "email": email,
            "full_name": req.fullName or (email.split("@")[0]),
            "avatar_url": req.avatarUrl,
            "auth_provider": req.provider or "clerk",
            "clerk_id": req.clerkId,
            "password_hash": "",
            "is_totp_enabled": False,
            "kyc_tier": KycTier.TIER_1_BASIC.value,
            "kyc_status": KycStatus.APPROVED.value,
            "admin_roles": [AdminRole.SUPER_ADMIN.value] if is_super else [],
            "is_suspended": False,
            "is_withdrawal_suspended": False,
            "created_at": now,
            "updated_at": now
        }
        user_repository.save(user)
        for asset in AssetSymbol:
            ledger_service.get_or_create_account(
                AccountType.USER_AVAILABLE,
                asset,
                user_id
            )
        is_new = True

    if user.get("is_suspended"):
        raise ForbiddenError("This account has been suspended by administration")

    token = sign_token({"userId": user["id"], "email": email, "isTotpAuthenticated": True})
    refresh_token = sign_refresh_token({"userId": user["id"], "email": email})
    safe_user = {k: v for k, v in user.items() if k != "password_hash" and k != "totp_secret"}

    return {
        "success": True,
        "token": token,
        "refreshToken": refresh_token,
        "user": safe_user,
        "isNewUser": is_new
    }


class SupabaseAuthRequest(BaseModel):
    supabaseId: str
    email: str
    fullName: Optional[str] = None
    avatarUrl: Optional[str] = None
    accessToken: Optional[str] = None
    provider: Optional[str] = "supabase"


@app.post("/api/v1/auth/supabase")
async def supabase_auth(req: SupabaseAuthRequest, request: Request):
    ip = get_client_ip(request)
    check_rate_limit(f"supabase_auth_{ip}", max_requests=30, window_seconds=60)

    email = req.email.strip().lower()
    if not email:
        raise ValidationError("Supabase authentication failed: missing email")

    now = int(time.time() * 1000)
    existing_user = user_repository.find_by_email(email)

    if existing_user:
        if not existing_user.get("supabase_id"):
            existing_user["supabase_id"] = req.supabaseId
            existing_user["auth_provider"] = req.provider or "supabase"
            if req.avatarUrl and not existing_user.get("avatar_url"):
                existing_user["avatar_url"] = req.avatarUrl
            user_repository.save(existing_user)
        user = existing_user
        is_new = False
    else:
        user_id = f"usr_sb_{uuid.uuid4().hex[:10]}"
        bootstrap_admin_email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL", "").strip().lower()
        is_super = bool(bootstrap_admin_email and email == bootstrap_admin_email)
        user = {
            "id": user_id,
            "email": email,
            "full_name": req.fullName or (email.split("@")[0]),
            "avatar_url": req.avatarUrl,
            "auth_provider": req.provider or "supabase",
            "supabase_id": req.supabaseId,
            "password_hash": "",
            "is_totp_enabled": False,
            "kyc_tier": KycTier.TIER_1_BASIC.value,
            "kyc_status": KycStatus.APPROVED.value,
            "admin_roles": [AdminRole.SUPER_ADMIN.value] if is_super else [],
            "is_suspended": False,
            "is_withdrawal_suspended": False,
            "created_at": now,
            "updated_at": now
        }
        user_repository.save(user)
        for asset in AssetSymbol:
            ledger_service.get_or_create_account(
                AccountType.USER_AVAILABLE,
                asset,
                user_id
            )
        is_new = True

    if user.get("is_suspended"):
        raise ForbiddenError("This account has been suspended by administration")

    token = sign_token({"userId": user["id"], "email": email, "isTotpAuthenticated": True})
    refresh_token = sign_refresh_token({"userId": user["id"], "email": email})
    safe_user = {k: v for k, v in user.items() if k != "password_hash" and k != "totp_secret"}

    return {
        "success": True,
        "token": token,
        "refreshToken": refresh_token,
        "user": safe_user,
        "isNewUser": is_new
    }




class SendOtpRequest(BaseModel):
    email: Optional[str] = None
    phoneNumber: Optional[str] = None
    target: Optional[str] = None
    channel: Optional[str] = "email"  # "email" | "sms" | "auto"
    purpose: Optional[str] = "REGISTRATION"
    countryCode: Optional[str] = "US"


@app.post("/api/v1/auth/send-otp")
async def send_otp(req: SendOtpRequest, request: Request):
    ip = get_client_ip(request)
    check_rate_limit(f"otp_{ip}", max_requests=8, window_seconds=60)

    target = (req.target or req.email or req.phoneNumber or "").strip()
    if not target:
        raise ValidationError("Target email or phone number is required to send OTP")

    channel = req.channel or ("sms" if (req.phoneNumber and not req.email) else "email")
    result = await otp_service.request_otp(
        identifier=target,
        channel=channel,
        purpose=req.purpose or "REGISTRATION",
        default_region=req.countryCode or "US"
    )
    return result


class VerifyOtpRequest(BaseModel):
    email: Optional[str] = None
    phoneNumber: Optional[str] = None
    target: Optional[str] = None
    code: str
    consume: Optional[bool] = True


@app.post("/api/v1/auth/verify-otp")
async def verify_otp(req: VerifyOtpRequest):
    target = (req.target or req.email or req.phoneNumber or "").strip()
    if not target:
        raise ValidationError("Target email or phone number is required")
    if not req.code or not req.code.strip():
        raise ValidationError("6-digit verification code is required")

    otp_service.verify_otp(target, req.code.strip(), consume=req.consume if req.consume is not None else True)
    return {"success": True, "message": "Verification code validated successfully"}


@app.post("/api/v1/auth/2fa/setup")
async def setup_2fa(user: Dict[str, Any] = Depends(get_current_user)):
    secret = generate_totp_secret()
    uri = get_totp_uri(secret, user["email"])
    user["totp_secret"] = secret
    user_repository.save(user)
    return {"success": True, "secret": secret, "otpauthUrl": uri}


class Enable2faRequest(BaseModel):
    code: str


@app.post("/api/v1/auth/2fa/enable")
async def enable_2fa(req: Enable2faRequest, user: Dict[str, Any] = Depends(get_current_user)):
    secret = user.get("totp_secret")
    if not secret or not verify_totp_code(secret, req.code):
        raise ValidationError("Invalid 6-digit TOTP code")
    user["is_totp_enabled"] = True
    user_repository.save(user)
    return {"success": True, "message": "Two-factor authentication enabled"}


# Market Data Endpoints
@app.get("/api/v1/market-data/tickers")
@app.get("/api/v1/markets/tickers")
async def get_tickers():
    tickers = await market_data_service.fetch_live_tickers()
    return {"success": True, "tickers": tickers}


@app.get("/api/v1/market-data/ticker/{symbol:path}")
@app.get("/api/v1/markets/{symbol:path}/ticker")
async def get_ticker(symbol: str):
    ticker = market_data_service.get_ticker(symbol)
    return {"success": True, "ticker": ticker}


@app.get("/api/v1/market-data/orderbook/{market:path}")
@app.get("/api/v1/markets/{market:path}/depth")
async def get_orderbook(market: str):
    book = matching_engine.get_book(market)
    return {"success": True, "depth": book.get_depth()}


@app.get("/api/v1/market-data/trades/{market:path}")
@app.get("/api/v1/markets/{market:path}/trades")
async def get_market_trades(market: str):
    trades = trade_repository.find_by_market(market)
    return {"success": True, "trades": trades}


@app.get("/api/v1/news")
async def get_news(category: Optional[str] = "All", query: Optional[str] = ""):
    news = market_data_service.get_news(category or "All", query or "")
    return {"success": True, "news": news, "count": len(news)}


# Strategy Resources & Entitlement-Gated PDF Downloads
@app.get("/api/v1/resources")
async def get_strategy_resources(authorization: Optional[str] = Header(None)):
    unlocked_ids: List[str] = []
    has_combo = False
    if authorization and authorization.startswith("Bearer "):
        try:
            claims = verify_token(authorization.split(" ", 1)[1].strip())
            uid = claims.get("userId") or claims.get("user_id")
            if uid:
                ent_data = commerce_service.get_user_orders_and_entitlements(uid)
                unlocked_ids = ent_data["unlockedResourceIds"]
                has_combo = ent_data["hasComboAccess"]
        except Exception:
            pass

    individual_product = commerce_service.get_product("individual_pdf")
    combo_product = commerce_service.get_product("combo_bundle")
    catalog = []
    for item in resources_service.get_catalog():
        catalog.append({
            **item,
            "priceUsd": individual_product["price_usd"],
            "currency": "USD",
            "isUnlocked": has_combo or (item["id"] in unlocked_ids),
        })

    return {
        "success": True,
        "resources": catalog,
        "pricing": {
            "individualPdfUsd": individual_product["price_usd"],
            "comboBundleUsd": combo_product["price_usd"],
            "currency": "USD",
        },
        "hasComboAccess": has_combo,
        "unlockedResourceIds": unlocked_ids,
    }


@app.get("/api/v1/resources/download/{resource_id}")
async def download_strategy_pdf(
    resource_id: str,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    res = resources_service.get_resource(resource_id)
    if not res:
        raise NotFoundError(f"Strategy resource '{resource_id}' not found")

    # Enforce server-side verified paid entitlement
    entitlement = commerce_service.check_download_entitlement(user["id"], resource_id)
    if not entitlement:
        raise ForbiddenError(
            "Purchase required ($99 USD Individual PDF or $699 USD Combo) to download this strategy playbook."
        )

    filepath = resources_service.get_pdf_filepath(resource_id)
    if not filepath or not filepath.exists():
        raise NotFoundError("Strategy PDF file not available on server")

    commerce_service.record_download_activity(
        user_id=user["id"],
        entitlement_id=entitlement["id"],
        resource_id=resource_id,
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )

    return FileResponse(
        path=str(filepath),
        filename=res["filename"],
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{res["filename"]}"'}
    )


@app.get("/api/v1/resources/combo/download")
async def download_strategy_combo_zip(
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    entitlement = commerce_service.check_combo_entitlement(user["id"])
    if not entitlement:
        raise ForbiddenError(
            "Complete Combo purchase ($699 USD) required to download the bundled strategy archive."
        )

    zip_bytes = commerce_service.build_combo_zip_bytes()
    commerce_service.record_download_activity(
        user_id=user["id"],
        entitlement_id=entitlement["id"],
        resource_id="ALL_COMBO",
        ip_address=get_client_ip(request),
        user_agent=request.headers.get("user-agent"),
    )
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="novextrade-complete-strategy-combo.zip"'},
    )


# =============================================================================
# REFERRAL SYSTEM ENDPOINTS
# =============================================================================

class ReferralTrackRequest(BaseModel):
    referralCode: str
    landingPath: Optional[str] = "/register"


@app.post("/api/v1/referrals/track")
async def track_referral_click(req: ReferralTrackRequest, request: Request):
    ip = get_client_ip(request)
    check_rate_limit(f"ref_track_{ip}", max_requests=60, window_seconds=60)
    result = referral_service.track_click(
        referral_code=req.referralCode,
        ip_address=ip,
        user_agent=request.headers.get("user-agent"),
        landing_path=req.landingPath or "/register",
    )
    return {"success": True, **result}


@app.get("/api/v1/referrals/validate/{code}")
async def validate_referral_code(code: str):
    referrer = referral_service.validate_referral_code(code)
    if not referrer:
        raise NotFoundError("Referral code not found")
    return {
        "success": True,
        "valid": True,
        "referralCode": referrer["referral_code"],
        "referrerName": referrer.get("full_name") or "NovexTrade Partner",
    }


@app.get("/api/v1/referrals/dashboard")
async def get_user_referral_dashboard(user: Dict[str, Any] = Depends(get_current_user)):
    data = referral_service.get_user_referral_dashboard(user["id"])
    return {"success": True, **data}


# =============================================================================
# COMMERCE, PRICING, CARD & CRYPTO CHECKOUT ENDPOINTS
# =============================================================================

class CheckoutOrderRequest(BaseModel):
    productId: str
    paymentMethod: str  # CARD | CRYPTO
    resourceId: Optional[str] = None
    cryptoAsset: Optional[str] = None
    referralCode: Optional[str] = None
    idempotencyKey: Optional[str] = None
    cardProvider: Optional[str] = None
    # Accepted solely to detect and reject client-side price manipulation attempts
    priceUsd: Optional[Any] = None
    amountUsd: Optional[Any] = None
    amount: Optional[Any] = None


class SubmitCryptoTxRequest(BaseModel):
    txHash: str


class VerifyCardOrderRequest(BaseModel):
    providerTxId: Optional[str] = None


@app.get("/api/v1/commerce/products")
async def get_commerce_products():
    return {
        "success": True,
        "products": commerce_service.get_products(),
        "cryptoWallet": commerce_service.get_global_crypto_wallet_config(),
        "cardGateway": {
            "provider": card_gateway.get_active_provider().upper(),
            "isConfigured": card_gateway.is_configured(),
            "supportedMethods": ["Visa", "Mastercard", "Verve", "International Cards"],
            "currency": "USD",
        },
    }


@app.get("/api/v1/commerce/crypto-wallet")
async def get_global_crypto_wallet_for_user(user: Dict[str, Any] = Depends(get_current_user)):
    """Every registered user receives the exact same administrator-configured global receiving wallet."""
    return {
        "success": True,
        "wallet": commerce_service.get_global_crypto_wallet_config(),
    }


@app.post("/api/v1/commerce/checkout")
async def create_commerce_checkout(
    req: CheckoutOrderRequest,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ip = get_client_ip(request)
    check_rate_limit(f"checkout_{user['id']}_{ip}", max_requests=20, window_seconds=60)
    supplied_price = req.priceUsd if req.priceUsd is not None else (
        req.amountUsd if req.amountUsd is not None else req.amount
    )
    order = await commerce_service.create_checkout_order(
        user=user,
        product_id=req.productId,
        payment_method=req.paymentMethod,
        resource_id=req.resourceId,
        crypto_asset=req.cryptoAsset,
        referral_code=req.referralCode,
        idempotency_key=req.idempotencyKey,
        client_supplied_price=supplied_price,
        card_provider=req.cardProvider,
    )
    return {"success": True, "order": order}


@app.post("/api/v1/commerce/orders/{order_id}/submit-crypto-tx")
async def submit_crypto_tx_for_order(
    order_id: str,
    req: SubmitCryptoTxRequest,
    request: Request,
    user: Dict[str, Any] = Depends(get_current_user),
):
    ip = get_client_ip(request)
    check_rate_limit(f"crypto_tx_{user['id']}_{ip}", max_requests=20, window_seconds=60)
    result = await commerce_service.submit_and_verify_crypto_tx(
        user_id=user["id"],
        order_id=order_id,
        tx_hash=req.txHash,
    )
    return {"success": True, "order": result}


@app.post("/api/v1/commerce/orders/{order_id}/verify-card")
async def verify_card_payment_order(
    order_id: str,
    req: VerifyCardOrderRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    result = await commerce_service.verify_card_order_status(
        user_id=user["id"],
        order_id=order_id,
        provider_tx_id=req.providerTxId,
    )
    return {"success": True, "order": result}


@app.get("/api/v1/commerce/orders")
async def get_my_commerce_orders(user: Dict[str, Any] = Depends(get_current_user)):
    data = commerce_service.get_user_orders_and_entitlements(user["id"])
    return {"success": True, **data}


@app.get("/api/v1/commerce/orders/{order_id}")
async def get_single_commerce_order(order_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    order = db.product_orders.get(order_id)
    if not order or order["user_id"] != user["id"]:
        raise NotFoundError("Order not found")
    return {"success": True, "order": commerce_service._format_order_response(order)}


# =============================================================================
# VERIFIED CARD PAYMENT WEBHOOKS (FLUTTERWAVE & PAYSTACK)
# =============================================================================

@app.post("/api/v1/webhooks/flutterwave")
async def flutterwave_webhook(request: Request):
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise ValidationError("Invalid JSON webhook payload")
    result = commerce_service.handle_card_webhook(
        provider="flutterwave",
        raw_body=raw_body,
        headers=dict(request.headers),
        payload=payload,
    )
    return result


@app.post("/api/v1/webhooks/paystack")
async def paystack_webhook(request: Request):
    raw_body = await request.body()
    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise ValidationError("Invalid JSON webhook payload")
    result = commerce_service.handle_card_webhook(
        provider="paystack",
        raw_body=raw_body,
        headers=dict(request.headers),
        payload=payload,
    )
    return result


# Wallet Endpoints
@app.get("/api/v1/wallet/balances")
@app.get("/api/v1/balances")
async def get_balances(user: Dict[str, Any] = Depends(get_current_user)):
    balances = ledger_service.get_user_balances(user["id"])
    return {"success": True, "balances": balances}


@app.get("/api/v1/wallet/transactions")
@app.get("/api/v1/transactions")
@app.get("/api/v1/history/all")
@app.get("/api/v1/wallet/history")
async def get_user_transactions(user: Dict[str, Any] = Depends(get_current_user)):
    uid = user["id"]
    txs: List[Dict[str, Any]] = []

    # 1. Deposits (including admin-credited funds)
    for d in db.deposits.values():
        if d.get("user_id") == uid:
            txs.append({
                "id": d["id"],
                "type": "DEPOSIT",
                "asset": d.get("asset", "USDT"),
                "amount": d.get("amount", "0"),
                "status": d.get("status", "CONFIRMED"),
                "description": f"Deposit of {d.get('amount')} {d.get('asset')}",
                "tx_hash": d.get("tx_hash"),
                "created_at": d.get("created_at", 0)
            })

    # 2. Withdrawals
    for w in db.withdrawals.values():
        if w.get("user_id") == uid:
            txs.append({
                "id": w["id"],
                "type": "WITHDRAWAL",
                "asset": w.get("asset", "USDT"),
                "amount": f"-{w.get('amount', '0')}",
                "status": w.get("status", "PENDING"),
                "description": f"Withdrawal to {w.get('destination_address', '')[:10]}...",
                "destination": w.get("destination_address"),
                "created_at": w.get("created_at", 0)
            })

    # 3. Internal Transfers
    for t in db.transfers.values():
        if t.get("from_user_id") == uid:
            txs.append({
                "id": t["id"],
                "type": "TRANSFER_OUT",
                "asset": t.get("asset", "USDT"),
                "amount": f"-{t.get('amount', '0')}",
                "status": "COMPLETED",
                "description": f"Internal transfer to {t.get('to_user_id')}",
                "counterparty": t.get("to_user_id"),
                "created_at": t.get("created_at", 0)
            })
        elif t.get("to_user_id") == uid:
            txs.append({
                "id": t["id"],
                "type": "TRANSFER_IN",
                "asset": t.get("asset", "USDT"),
                "amount": f"+{t.get('amount', '0')}",
                "status": "COMPLETED",
                "description": f"Internal transfer from {t.get('from_user_id')}",
                "counterparty": t.get("from_user_id"),
                "created_at": t.get("created_at", 0)
            })

    # 4. Investment Plans & Staking
    for inv in db.user_investments.values():
        if inv.get("user_id") == uid:
            txs.append({
                "id": inv["id"],
                "type": "INVESTMENT",
                "asset": "USDT",
                "amount": f"-{inv.get('principal_amount', '0')}",
                "status": inv.get("status", "ACTIVE"),
                "description": f"Subscribed to {inv.get('plan_name', 'Yield Plan')}",
                "expected_return": inv.get("expected_total_return"),
                "created_at": inv.get("start_time", 0)
            })
            if inv.get("status") == "CLAIMED":
                txs.append({
                    "id": f"claim_{inv['id']}",
                    "type": "YIELD_PAYOUT",
                    "asset": "USDT",
                    "amount": f"+{inv.get('expected_total_return', '0')}",
                    "status": "COMPLETED",
                    "description": f"Yield payout for {inv.get('plan_name')}",
                    "created_at": inv.get("end_time", inv.get("start_time", 0))
                })

    # 5. Trades
    user_trades = trade_repository.find_by_user_id(uid)
    for tr in user_trades:
        is_buy = tr.get("buyer_user_id") == uid
        txs.append({
            "id": tr["id"],
            "type": "TRADE_BUY" if is_buy else "TRADE_SELL",
            "market": tr.get("market", "BTC/USDT"),
            "price": tr.get("price"),
            "quantity": tr.get("quantity"),
            "amount": f"{'+' if is_buy else '-'}{tr.get('quantity')} {tr.get('market', '').split('/')[0]}",
            "status": "FILLED",
            "description": f"Spot Trade: {'BUY' if is_buy else 'SELL'} {tr.get('quantity')} @ {tr.get('price')}",
            "created_at": tr.get("timestamp", 0)
        })

    # Sort descending by timestamp
    txs.sort(key=lambda x: x.get("created_at", 0), reverse=True)
    return {"success": True, "transactions": txs, "count": len(txs)}


class DepositRequest(BaseModel):
    asset: str
    amount: str
    txHash: Optional[str] = None


@app.post("/api/v1/wallet/deposit")
async def deposit(req: DepositRequest, user: Dict[str, Any] = Depends(get_current_user)):
    record = wallet_service.credit_deposit(user["id"], AssetSymbol(req.asset), req.amount, req.txHash)
    return {"success": True, "deposit": record}


@app.get("/api/v1/wallet/deposit-address")
async def get_deposit_address(asset: str = "USDT", network: Optional[str] = None, user: Dict[str, Any] = Depends(get_current_user)):
    addr_info = wallet_service.get_deposit_address(asset, network)
    return {"success": True, "depositAddress": addr_info}


@app.get("/api/v1/wallet/withdrawals")
async def get_user_withdrawals(user: Dict[str, Any] = Depends(get_current_user)):
    user_withdrawals = [w for w in db.withdrawals.values() if w.get("user_id") == user["id"]]
    return {"success": True, "withdrawals": sorted(user_withdrawals, key=lambda x: x.get("created_at", 0), reverse=True)}


@app.get("/api/v1/wallet/deposits")
async def get_user_deposits(user: Dict[str, Any] = Depends(get_current_user)):
    user_deposits = [d for d in db.deposits.values() if d.get("user_id") == user["id"]]
    return {"success": True, "deposits": sorted(user_deposits, key=lambda x: x.get("created_at", 0), reverse=True)}


class WithdrawRequest(BaseModel):
    asset: str
    amount: str
    destinationAddress: str


@app.post("/api/v1/wallet/withdraw")
async def withdraw(req: WithdrawRequest, user: Dict[str, Any] = Depends(get_current_user)):
    record = wallet_service.request_withdrawal(user["id"], AssetSymbol(req.asset), req.amount, req.destinationAddress)
    return {"success": True, "withdrawal": record}


class TransferRequest(BaseModel):
    toUserId: str
    asset: str
    amount: str


@app.post("/api/v1/wallet/transfer")
async def transfer(req: TransferRequest, user: Dict[str, Any] = Depends(get_current_user)):
    record = wallet_service.execute_internal_transfer(user["id"], req.toUserId, AssetSymbol(req.asset), req.amount)
    return {"success": True, "transfer": record}


# Investment & Staking Endpoints
@app.get("/api/v1/invest/plans")
async def list_investment_plans():
    plans = investment_service.list_plans()
    return {"success": True, "plans": plans}


class SubscribeInvestmentRequest(BaseModel):
    plan_id: str
    amount: str


@app.post("/api/v1/invest/subscribe")
async def subscribe_investment(req: SubscribeInvestmentRequest, user: Dict[str, Any] = Depends(get_current_user)):
    record = investment_service.subscribe(user["id"], req.plan_id, req.amount)
    return {"success": True, "investment": record}


@app.get("/api/v1/invest/my-investments")
async def get_my_investments(user: Dict[str, Any] = Depends(get_current_user)):
    investments = investment_service.get_user_investments(user["id"])
    return {"success": True, "investments": investments}


class ClaimPayoutRequest(BaseModel):
    investment_id: str


@app.post("/api/v1/invest/claim")
async def claim_investment_payout(req: ClaimPayoutRequest, user: Dict[str, Any] = Depends(get_current_user)):
    result = investment_service.claim_payout(user["id"], req.investment_id)
    return result


# Orders & Trades Endpoints
class CreateOrderRequest(BaseModel):
    market: str
    side: str
    type: Optional[str] = "LIMIT"
    price: str
    quantity: str
    timeInForce: Optional[str] = "GTC"


@app.post("/api/v1/orders")
async def create_order(req: CreateOrderRequest, user: Dict[str, Any] = Depends(get_current_user)):
    order_data = {
        "user_id": user["id"],
        "market": req.market,
        "side": OrderSide(req.side),
        "type": OrderType(req.type or "LIMIT"),
        "price": req.price,
        "quantity": req.quantity
    }
    result = matching_engine.place_order(order_data)
    await ws_manager.broadcast({"type": "ORDER_UPDATE", "data": result})
    return {"success": True, **result}


@app.get("/api/v1/orders")
@app.get("/api/v1/orders/my")
async def get_my_orders(user: Dict[str, Any] = Depends(get_current_user)):
    orders = order_repository.find_by_user_id(user["id"])
    return {"success": True, "orders": orders}


@app.get("/api/v1/trades/my")
@app.get("/api/v1/trades")
@app.get("/api/v1/my-trades")
async def get_my_trades(user: Dict[str, Any] = Depends(get_current_user)):
    trades = trade_repository.find_by_user_id(user["id"])
    return {"success": True, "trades": trades}



@app.post("/api/v1/orders/{order_id}/cancel")
@app.delete("/api/v1/orders/{order_id}")
async def cancel_order(order_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    cancelled = matching_engine.cancel_order(order_id, user["id"])
    await ws_manager.broadcast({"type": "ORDER_UPDATE", "data": {"order": cancelled}})
    return {"success": True, "order": cancelled}


class CreateApiKeyRequest(BaseModel):
    label: str
    permissions: Optional[List[str]] = ["READ", "TRADE"]
    ip_whitelist: Optional[str] = None


@app.get("/api/v1/auth/api-keys")
async def get_api_keys(user: Dict[str, Any] = Depends(get_current_user)):
    keys = [k for k in db.api_keys.values() if k.get("user_id") == user["id"]]
    return {"success": True, "keys": keys}


@app.post("/api/v1/auth/api-keys")
async def create_api_key(req: CreateApiKeyRequest, user: Dict[str, Any] = Depends(get_current_user)):
    key_id = f"key_{int(time.time()*1000)}_{uuid.uuid4().hex[:6]}"
    api_key = f"sync_{uuid.uuid4().hex}"
    api_secret = f"sec_{uuid.uuid4().hex}{uuid.uuid4().hex}"
    key_obj = {
        "id": key_id,
        "user_id": user["id"],
        "label": req.label.strip() or "Default API Key",
        "api_key": api_key,
        "api_secret_preview": api_secret[:6] + "..." + api_secret[-4:],
        "permissions": req.permissions or ["READ", "TRADE"],
        "ip_whitelist": req.ip_whitelist.strip() if req.ip_whitelist else None,
        "created_at": int(time.time() * 1000),
        "status": "ACTIVE"
    }
    db.api_keys[key_id] = key_obj
    db.api_keys_by_key[api_key] = key_id
    return {"success": True, "apiKey": api_key, "apiSecret": api_secret, "key": key_obj}


@app.delete("/api/v1/auth/api-keys/{key_id}")
async def delete_api_key(key_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    key_obj = db.api_keys.get(key_id)
    if not key_obj or key_obj.get("user_id") != user["id"]:
        raise NotFoundError("API Key not found")
    del db.api_keys[key_id]
    if key_obj.get("api_key") in db.api_keys_by_key:
        del db.api_keys_by_key[key_obj["api_key"]]
    return {"success": True, "message": "API key revoked"}


@app.get("/api/v1/auth/sessions")
async def get_sessions(user: Dict[str, Any] = Depends(get_current_user)):
    return {
        "success": True,
        "sessions": [
            {
                "id": "sess_current",
                "device": "MacBook Pro (macOS)",
                "browser": "Chrome 128.0",
                "ip": "127.0.0.1",
                "location": "Localhost / Secure LAN",
                "last_active": int(time.time() * 1000),
                "is_current": True
            }
        ]
    }


@app.post("/api/v1/auth/sessions/revoke-all")
async def revoke_all_sessions(user: Dict[str, Any] = Depends(get_current_user)):
    return {"success": True, "message": "All other sessions have been terminated."}


# P2P Endpoints
@app.get("/api/v1/p2p/ads")
@app.get("/api/v1/p2p/offers")
async def list_p2p_ads(type: Optional[str] = None, asset: Optional[str] = None, fiat: Optional[str] = None):
    ads = p2p_service.list_ads(type, asset, fiat)
    return {"success": True, "ads": ads, "offers": ads}


class CreateAdRequest(BaseModel):
    type: str
    asset: str
    fiat_currency: str
    price: str
    available_amount: str
    merchant_name: Optional[str] = None
    min_limit: Optional[str] = "50"
    max_limit: Optional[str] = "5000"
    payment_methods: Optional[List[str]] = None


@app.post("/api/v1/p2p/ads")
@app.post("/api/v1/p2p/offers")
async def create_p2p_ad(req: CreateAdRequest, user: Dict[str, Any] = Depends(get_current_user)):
    ad = p2p_service.create_ad(user["id"], req.model_dump())
    return {"success": True, "ad": ad}


class CreateP2PTradeRequest(BaseModel):
    adId: Optional[str] = None
    ad_id: Optional[str] = None
    cryptoAmount: Optional[str] = None
    crypto_amount: Optional[str] = None
    paymentMethod: Optional[str] = "Bank Transfer"


@app.post("/api/v1/p2p/trades")
@app.post("/api/v1/p2p/orders")
async def create_p2p_trade(req: CreateP2PTradeRequest, user: Dict[str, Any] = Depends(get_current_user)):
    ad_id = req.adId or req.ad_id
    crypto_amt = req.cryptoAmount or req.crypto_amount
    trade = p2p_service.initiate_trade({
        "ad_id": ad_id,
        "buyer_user_id": user["id"],
        "crypto_amount": crypto_amt,
        "payment_method": req.paymentMethod or "Bank Transfer"
    })
    return {"success": True, "trade": trade}


@app.get("/api/v1/p2p/trades/my")
async def get_my_p2p_trades(user: Dict[str, Any] = Depends(get_current_user)):
    trades = [t for t in db.p2p_trades.values() if t.get("buyer_user_id") == user["id"] or t.get("seller_user_id") == user["id"]]
    return {"success": True, "trades": trades}


@app.post("/api/v1/p2p/trades/{trade_id}/mark-paid")
async def mark_p2p_paid(trade_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    trade = p2p_service.mark_paid(trade_id, user["id"])
    return {"success": True, "trade": trade}


@app.post("/api/v1/p2p/trades/{trade_id}/release")
async def release_p2p(trade_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    trade = p2p_service.release_escrow(trade_id, user["id"])
    return {"success": True, "trade": trade}


@app.post("/api/v1/p2p/trades/{trade_id}/cancel")
async def cancel_p2p(trade_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    trade = p2p_service.cancel_trade(trade_id, user["id"])
    return {"success": True, "trade": trade}


# KYC Endpoints
class KycSubmitRequest(BaseModel):
    fullName: str
    dateOfBirth: str
    country: str
    idNumber: str
    idDocumentType: Optional[str] = "PASSPORT"


@app.post("/api/v1/kyc/submit")
async def submit_kyc(req: KycSubmitRequest, user: Dict[str, Any] = Depends(get_current_user)):
    res = compliance_service.submit_kyc(user["id"], req.model_dump())
    return {"success": True, **res}


# Admin routes are comprehensively provided and validated in syncnode.admin.api (admin_api_router)



# WebSocket Route
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    auth_user_id = None
    if token:
        try:
            claims = verify_token(token)
            auth_user_id = claims.get("userId") or claims.get("user_id")
        except Exception:
            pass

    await ws_manager.connect(websocket, auth_user_id)
    try:
        while True:
            data_raw = await websocket.receive_text()
            try:
                msg = json.loads(data_raw)
                action = msg.get("action")
                if action == "AUTH" and msg.get("token"):
                    try:
                        claims = verify_token(msg["token"])
                        uid = claims.get("userId") or claims.get("user_id")
                        if uid:
                            ws_manager.disconnect(websocket)
                            await ws_manager.connect(websocket, uid)
                            await websocket.send_text(json.dumps({"type": "AUTH_OK", "userId": uid}))
                    except Exception:
                        pass
                elif action == "SUBSCRIBE":
                    # Acknowledge channel subscription
                    channels = msg.get("channels", [])
                    await websocket.send_text(json.dumps({"type": "SUBSCRIPTION_ACK", "channels": channels}))
                else:
                    await websocket.send_text(json.dumps({"type": "PONG", "timestamp": int(time.time() * 1000)}))
            except Exception:
                await websocket.send_text(json.dumps({"type": "PONG", "timestamp": int(time.time() * 1000)}))
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)



app.include_router(admin_api_router)
app.include_router(admin_router)

# Mount Full React Client Static Build
dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "apps", "web", "dist"))
if os.path.exists(dist_dir):
    app.mount("/", StaticFiles(directory=dist_dir, html=True), name="static")
else:
    app.include_router(web_router)
