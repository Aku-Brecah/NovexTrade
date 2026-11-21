import time
import pytest
from starlette.testclient import TestClient

from syncnode.server import app, RATE_LIMIT_STORE
from syncnode.database.db import db
from syncnode.database.repository import user_repository
from syncnode.services.auth_recovery import hash_token


@pytest.fixture(autouse=True)
def reset_state():
    db.reset()
    RATE_LIMIT_STORE.clear()
    yield


@pytest.fixture
def client():
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. REGISTRATION TESTS
# ---------------------------------------------------------------------------

def test_registration_validation_and_duplicate_prevention(client):
    # Invalid email
    r_bad_email = client.post(
        "/api/v1/auth/register",
        json={"email": "not-an-email", "password": "StrongPassword1!", "confirmPassword": "StrongPassword1!"},
    )
    assert r_bad_email.status_code == 422

    # Weak password (missing uppercase & digit)
    r_weak = client.post(
        "/api/v1/auth/register",
        json={"email": "weak@example.com", "password": "password", "confirmPassword": "password"},
    )
    assert r_weak.status_code == 422

    # Mismatched passwords
    r_mismatch = client.post(
        "/api/v1/auth/register",
        json={"email": "mismatch@example.com", "password": "StrongPassword1!", "confirmPassword": "OtherPassword1!"},
    )
    assert r_mismatch.status_code == 422

    # Valid registration creates user, referral code, and zero ledger balances
    r_ok = client.post(
        "/api/v1/auth/register",
        json={
            "email": "valid.trader@example.com",
            "password": "StrongPassword1!",
            "confirmPassword": "StrongPassword1!",
            "fullName": "Valid Trader",
        },
    )
    assert r_ok.status_code == 200
    body = r_ok.json()
    assert body["success"] is True
    assert body["token"]
    assert body["refreshToken"]
    assert body["user"]["referral_code"].startswith("NVX")

    # Duplicate email rejected
    r_dup = client.post(
        "/api/v1/auth/register",
        json={
            "email": "VALID.TRADER@example.com",
            "password": "StrongPassword1!",
            "confirmPassword": "StrongPassword1!",
        },
    )
    assert r_dup.status_code == 422


# ---------------------------------------------------------------------------
# 2. LOGIN, SUSPENDED ACCOUNT & TOKEN TYPE ENFORCEMENT TESTS
# ---------------------------------------------------------------------------

def test_login_credentials_suspended_account_and_refresh_token_rejection(client):
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "loginuser@example.com", "password": "StrongPassword1!", "fullName": "Login User"},
    ).json()
    user_id = reg["user"]["id"]
    refresh_tok = reg["refreshToken"]

    # Refresh token MUST NOT be accepted as an access Bearer token
    r_abuse = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {refresh_tok}"})
    assert r_abuse.status_code == 401

    # Wrong password -> 401
    r_wrong = client.post("/api/v1/auth/login", json={"email": "loginuser@example.com", "password": "WrongPassword1!"})
    assert r_wrong.status_code == 401

    # Nonexistent account -> 401 with identical anti-enumeration error
    r_missing = client.post("/api/v1/auth/login", json={"email": "nobody@example.com", "password": "WrongPassword1!"})
    assert r_missing.status_code == 401
    assert r_wrong.json()["error"] == r_missing.json()["error"]

    # Valid login succeeds
    r_ok = client.post("/api/v1/auth/login", json={"email": "loginuser@example.com", "password": "StrongPassword1!"})
    assert r_ok.status_code == 200
    assert r_ok.json()["success"] is True

    # Suspended account rejected on login (403)
    user = user_repository.find_by_id(user_id)
    user["is_suspended"] = True
    user_repository.save(user)

    r_susp = client.post("/api/v1/auth/login", json={"email": "loginuser@example.com", "password": "StrongPassword1!"})
    assert r_susp.status_code == 403


# ---------------------------------------------------------------------------
# 3. PASSWORD RECOVERY (SINGLE-USE, EXPIRY, SESSION INVALIDATION)
# ---------------------------------------------------------------------------

def test_password_recovery_lifecycle_and_session_invalidation(client):
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "recover@example.com", "password": "OldPassword1!", "fullName": "Recover User"},
    ).json()
    old_access = reg["token"]
    old_refresh = reg["refreshToken"]
    user_id = reg["user"]["id"]

    # Anti-enumeration: unknown & known emails produce identical 200 response
    r_unknown = client.post("/api/v1/auth/forgot-password", json={"email": "ghost@example.com"})
    r_known = client.post("/api/v1/auth/forgot-password", json={"email": "recover@example.com"})
    assert r_unknown.status_code == 200 and r_known.status_code == 200
    assert r_unknown.json() == r_known.json()

    # Inject a known raw token hash to verify single-use & expiry deterministically
    raw_token = "valid_single_use_reset_token_1234567890"
    t_hash = hash_token(raw_token)
    now_ms = int(time.time() * 1000)
    db.password_reset_tokens[t_hash] = {
        "id": "prst_test_1",
        "user_id": user_id,
        "token_hash": t_hash,
        "expires_at": now_ms + 600_000,
        "used_at": None,
        "created_at": now_ms,
    }

    # Expired token rejected
    expired_raw = "expired_reset_token_1234567890abcdef"
    exp_hash = hash_token(expired_raw)
    db.password_reset_tokens[exp_hash] = {
        "id": "prst_exp_1",
        "user_id": user_id,
        "token_hash": exp_hash,
        "expires_at": now_ms - 1000,
        "used_at": None,
        "created_at": now_ms - 5000,
    }
    r_exp = client.post(
        "/api/v1/auth/reset-password",
        json={"token": expired_raw, "newPassword": "NewPassword2!", "confirmPassword": "NewPassword2!"},
    )
    assert r_exp.status_code == 422

    # Valid reset succeeds
    r_reset = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "newPassword": "NewPassword2!", "confirmPassword": "NewPassword2!"},
    )
    assert r_reset.status_code == 200

    # Reusing the same reset token fails
    r_reuse = client.post(
        "/api/v1/auth/reset-password",
        json={"token": raw_token, "newPassword": "ThirdPassword3!", "confirmPassword": "ThirdPassword3!"},
    )
    assert r_reuse.status_code == 422

    # Old access & refresh tokens are immediately invalidated
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {old_access}"}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refreshToken": old_refresh}).status_code == 401

    # Old password fails, new password succeeds
    assert client.post("/api/v1/auth/login", json={"email": "recover@example.com", "password": "OldPassword1!"}).status_code == 401
    r_new_login = client.post("/api/v1/auth/login", json={"email": "recover@example.com", "password": "NewPassword2!"})
    assert r_new_login.status_code == 200


# ---------------------------------------------------------------------------
# 4. SESSION LOGOUT, ROTATION & AUTHORIZATION TESTS
# ---------------------------------------------------------------------------

def test_logout_revokes_session_and_refresh_rotates(client):
    reg = client.post(
        "/api/v1/auth/register",
        json={"email": "session@example.com", "password": "StrongPassword1!", "fullName": "Session User"},
    ).json()
    access = reg["token"]
    refresh = reg["refreshToken"]

    # Refresh rotates token; old refresh token cannot be reused
    ref_res = client.post("/api/v1/auth/refresh", json={"refreshToken": refresh})
    assert ref_res.status_code == 200
    new_access = ref_res.json()["token"]
    new_refresh = ref_res.json()["refreshToken"]
    assert client.post("/api/v1/auth/refresh", json={"refreshToken": refresh}).status_code == 401

    # Logout revokes both access and refresh tokens
    out = client.post(
        "/api/v1/auth/logout",
        headers={"Authorization": f"Bearer {new_access}"},
        json={"refreshToken": new_refresh},
    )
    assert out.status_code == 200

    # Subsequent protected call & refresh fail with 401
    assert client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {new_access}"}).status_code == 401
    assert client.post("/api/v1/auth/refresh", json={"refreshToken": new_refresh}).status_code == 401

    # Ordinary user cannot access admin endpoints
    reg2 = client.post(
        "/api/v1/auth/register",
        json={"email": "regular@example.com", "password": "StrongPassword1!"},
    ).json()
    assert client.get("/api/v1/admin/stats", headers={"Authorization": f"Bearer {reg2['token']}"}).status_code == 403
