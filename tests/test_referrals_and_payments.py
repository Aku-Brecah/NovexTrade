import hashlib
import hmac
import json
import os
import zipfile
import io
from decimal import Decimal
from unittest.mock import AsyncMock, patch

import pytest
from starlette.testclient import TestClient

from syncnode.server import app, RATE_LIMIT_STORE
from syncnode.database.db import db
from syncnode.database.repository import user_repository
from syncnode.security.crypto import sign_token
from syncnode.common.types import AdminRole
from syncnode.services.crypto_verifier import crypto_verifier
from syncnode.services.card_gateway import card_gateway


@pytest.fixture(autouse=True)
def clean_db():
    db.reset()
    RATE_LIMIT_STORE.clear()
    yield


@pytest.fixture
def client():
    return TestClient(app)


def _register_user(client, email, password="StrongPassword123!", full_name="Test User", referral_code=None, click_id=None):
    payload = {"email": email, "password": password, "fullName": full_name}
    if referral_code:
        payload["referralCode"] = referral_code
    if click_id:
        payload["referralClickId"] = click_id
    res = client.post("/api/v1/auth/register", json=payload)
    return res


def _admin_headers():
    admin = db.users["admin_super_exec_1"]
    token = sign_token({"userId": admin["id"], "email": admin["email"]})
    return {"Authorization": f"Bearer {token}"}


def _auditor_headers():
    auditor = {
        "id": "auditor_ro_1",
        "email": "auditor@novextrade.exchange",
        "full_name": "Read Only Auditor",
        "admin_roles": [AdminRole.READ_ONLY_AUDITOR.value],
        "is_suspended": False,
    }
    user_repository.save(auditor)
    token = sign_token({"userId": auditor["id"], "email": auditor["email"]})
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# 1-5. REFERRAL SYSTEM TESTS
# ---------------------------------------------------------------------------

def test_new_account_generates_unique_referral_code_and_url(client):
    r1 = _register_user(client, "alice@example.com")
    r2 = _register_user(client, "bob@example.com")
    assert r1.status_code == 200 and r2.status_code == 200
    u1 = r1.json()["user"]
    u2 = r2.json()["user"]

    assert u1["referral_code"].startswith("NVX")
    assert u2["referral_code"].startswith("NVX")
    assert u1["referral_code"] != u2["referral_code"]
    assert f"/register?ref={u1['referral_code']}" in u1["referral_url"]


def test_referral_click_tracking_and_registration_attribution(client):
    r_ref = _register_user(client, "referrer@example.com", full_name="Referrer One")
    ref_token = r_ref.json()["token"]
    ref_code = r_ref.json()["user"]["referral_code"]

    # Validate & track click
    val = client.get(f"/api/v1/referrals/validate/{ref_code}")
    assert val.status_code == 200
    assert val.json()["valid"] is True

    trk = client.post("/api/v1/referrals/track", json={"referralCode": ref_code, "landingPath": f"/register?ref={ref_code}"})
    assert trk.status_code == 200
    click_id = trk.json()["clickId"]

    # New user registers with preserved referral code
    r_new = _register_user(client, "buyer@example.com", referral_code=ref_code, click_id=click_id)
    assert r_new.status_code == 200
    assert r_new.json()["user"]["referred_by"] == r_ref.json()["user"]["id"]

    # Dashboard stats match DB records
    dash = client.get("/api/v1/referrals/dashboard", headers={"Authorization": f"Bearer {ref_token}"})
    assert dash.status_code == 200
    stats = dash.json()["stats"]
    assert stats["totalClicks"] == 1
    assert stats["totalRegistrations"] == 1
    assert stats["conversionRatePercent"] == "100.00"


def test_self_referral_rejected_at_checkout(client):
    r = _register_user(client, "selfref@example.com")
    token = r.json()["token"]
    own_code = r.json()["user"]["referral_code"]

    res = client.post(
        "/api/v1/commerce/checkout",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "productId": "individual_pdf",
            "resourceId": "strat-momentum-playbook",
            "paymentMethod": "CRYPTO",
            "cryptoAsset": "USDT",
            "referralCode": own_code,
        },
    )
    assert res.status_code == 422
    assert "own referral code" in res.json()["error"].lower()


# ---------------------------------------------------------------------------
# 6-8. PRICING & ANTI-MANIPULATION TESTS
# ---------------------------------------------------------------------------

def test_authoritative_pricing_99_and_699_and_reject_client_manipulation(client):
    r = _register_user(client, "pricing@example.com")
    headers = {"Authorization": f"Bearer {r.json()['token']}"}

    # Individual PDF must be $99.00
    ord_ind = client.post(
        "/api/v1/commerce/checkout",
        headers=headers,
        json={
            "productId": "individual_pdf",
            "resourceId": "strat-momentum-playbook",
            "paymentMethod": "CRYPTO",
            "cryptoAsset": "USDT",
        },
    )
    assert ord_ind.status_code == 200
    assert ord_ind.json()["order"]["amountUsd"] == "99.00"

    # Combo must be $699.00
    ord_combo = client.post(
        "/api/v1/commerce/checkout",
        headers=headers,
        json={
            "productId": "combo_bundle",
            "paymentMethod": "CRYPTO",
            "cryptoAsset": "USDT",
        },
    )
    assert ord_combo.status_code == 200
    assert ord_combo.json()["order"]["amountUsd"] == "699.00"

    # Client-side price manipulation rejected
    tampered = client.post(
        "/api/v1/commerce/checkout",
        headers=headers,
        json={
            "productId": "combo_bundle",
            "paymentMethod": "CRYPTO",
            "cryptoAsset": "USDT",
            "priceUsd": "1.00",
        },
    )
    assert tampered.status_code == 422
    assert "manipulation" in tampered.json()["error"].lower()


# ---------------------------------------------------------------------------
# 9-13. GLOBAL CRYPTO WALLET & ON-CHAIN VERIFICATION TESTS
# ---------------------------------------------------------------------------

def test_global_wallet_same_for_all_users_and_reflects_admin_updates(client):
    u1 = _register_user(client, "usera@example.com").json()["token"]
    u2 = _register_user(client, "userb@example.com").json()["token"]
    u3 = _register_user(client, "userc@example.com").json()["token"]

    w1 = client.get("/api/v1/commerce/crypto-wallet", headers={"Authorization": f"Bearer {u1}"}).json()["wallet"]
    w2 = client.get("/api/v1/commerce/crypto-wallet", headers={"Authorization": f"Bearer {u2}"}).json()["wallet"]
    w3 = client.get("/api/v1/commerce/crypto-wallet", headers={"Authorization": f"Bearer {u3}"}).json()["wallet"]
    assert w1["receivingAddress"] == w2["receivingAddress"] == w3["receivingAddress"]

    # Invalid address format for TRC20 rejected
    bad_upd = client.put(
        "/api/v1/admin/commerce/crypto-wallet",
        headers=_admin_headers(),
        json={
            "receiving_address": "0x71C8366420A092679b5436194448873305370caD",
            "primary_network": "TRC20",
            "primary_asset": "USDT",
            "supported_tokens": ["USDT"],
        },
    )
    assert bad_upd.status_code == 422

    # Valid EVM address update reflected immediately to all users
    new_addr = "0x1111111111111111111111111111111111111111"
    good_upd = client.put(
        "/api/v1/admin/commerce/crypto-wallet",
        headers=_admin_headers(),
        json={
            "is_enabled": True,
            "receiving_address": new_addr,
            "primary_network": "ERC20",
            "primary_asset": "USDT",
            "supported_tokens": ["USDT", "USDC"],
            "required_confirmations": 6,
        },
    )
    assert good_upd.status_code == 200
    w1_after = client.get("/api/v1/commerce/crypto-wallet", headers={"Authorization": f"Bearer {u1}"}).json()["wallet"]
    w2_after = client.get("/api/v1/commerce/crypto-wallet", headers={"Authorization": f"Bearer {u2}"}).json()["wallet"]
    assert w1_after["receivingAddress"] == new_addr
    assert w2_after["receivingAddress"] == new_addr


def test_crypto_verification_unlocks_only_on_confirmed_and_blocks_duplicates(client):
    u1_token = _register_user(client, "cryptobuyer1@example.com").json()["token"]
    u2_token = _register_user(client, "cryptobuyer2@example.com").json()["token"]
    h1 = {"Authorization": f"Bearer {u1_token}"}
    h2 = {"Authorization": f"Bearer {u2_token}"}

    order1 = client.post(
        "/api/v1/commerce/checkout",
        headers=h1,
        json={"productId": "individual_pdf", "resourceId": "strat-momentum-playbook", "paymentMethod": "CRYPTO", "cryptoAsset": "USDT"},
    ).json()["order"]

    # Invalid tx hash syntax rejected
    bad_hash = client.post(
        f"/api/v1/commerce/orders/{order1['id']}/submit-crypto-tx",
        headers=h1,
        json={"txHash": "not-a-real-hash"},
    )
    assert bad_hash.status_code == 422

    valid_tx_hash = "0x" + "ab" * 32

    # Underpaid transaction does NOT unlock download
    with patch.object(
        crypto_verifier,
        "verify_onchain_transaction",
        new=AsyncMock(return_value={
            "status": "UNDERPAID",
            "confirmations": 15,
            "received_amount": Decimal("10.00"),
            "sender_address": "0x" + "1" * 40,
            "reason": "Received 10.00 below required 99.00",
            "raw": {},
        }),
    ):
        under_res = client.post(
            f"/api/v1/commerce/orders/{order1['id']}/submit-crypto-tx",
            headers=h1,
            json={"txHash": "0x" + "cd" * 32},
        )
        assert under_res.status_code == 200
        assert under_res.json()["order"]["status"] == "UNDERPAID"
        assert client.get("/api/v1/resources/download/strat-momentum-playbook", headers=h1).status_code == 403

    # Confirmed on-chain transaction unlocks download for buyer 1 ONLY
    with patch.object(
        crypto_verifier,
        "verify_onchain_transaction",
        new=AsyncMock(return_value={
            "status": "CONFIRMED",
            "confirmations": 15,
            "received_amount": Decimal("99.00"),
            "sender_address": "0x" + "1" * 40,
            "reason": "Confirmed on-chain",
            "raw": {},
        }),
    ):
        ok_res = client.post(
            f"/api/v1/commerce/orders/{order1['id']}/submit-crypto-tx",
            headers=h1,
            json={"txHash": valid_tx_hash},
        )
        assert ok_res.status_code == 200
        assert ok_res.json()["order"]["status"] == "PAID"

    # Buyer 1 can download
    dl1 = client.get("/api/v1/resources/download/strat-momentum-playbook", headers=h1)
    assert dl1.status_code == 200
    assert dl1.content.startswith(b"%PDF-1.4")

    # Buyer 2 CANNOT download Buyer 1's PDF
    dl2 = client.get("/api/v1/resources/download/strat-momentum-playbook", headers=h2)
    assert dl2.status_code == 403

    # Buyer 2 CANNOT reuse Buyer 1's transaction hash
    order2 = client.post(
        "/api/v1/commerce/checkout",
        headers=h2,
        json={"productId": "individual_pdf", "resourceId": "strat-momentum-playbook", "paymentMethod": "CRYPTO", "cryptoAsset": "USDT"},
    ).json()["order"]
    dup = client.post(
        f"/api/v1/commerce/orders/{order2['id']}/submit-crypto-tx",
        headers=h2,
        json={"txHash": valid_tx_hash},
    )
    assert dup.status_code == 422
    assert "duplicate" in dup.json()["error"].lower()


# ---------------------------------------------------------------------------
# 14-18. CARD WEBHOOKS, IDEMPOTENCY, COMMISSIONS & REFUNDS
# ---------------------------------------------------------------------------

def test_card_webhooks_idempotency_commissions_combo_zip_and_refund_reversal(client, monkeypatch):
    monkeypatch.setenv("FLUTTERWAVE_WEBHOOK_HASH", "flw_test_webhook_secret")
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", "sk_test_paystack_secret")

    # Admin configures referral commission percentages (15% individual, 20% combo)
    cfg_res = client.put(
        "/api/v1/admin/referrals/config",
        headers=_admin_headers(),
        json={
            "is_enabled": True,
            "individual_pdf_commission_percent": "15.00",
            "combo_commission_percent": "20.00",
            "min_payout_threshold_usd": "50.00",
            "holding_period_days": 14,
            "approval_mode": "MANUAL",
        },
    )
    assert cfg_res.status_code == 200

    # Referrer + Referred buyer
    referrer = _register_user(client, "partner@example.com").json()
    ref_code = referrer["user"]["referral_code"]
    buyer = _register_user(client, "cardbuyer@example.com", referral_code=ref_code).json()
    buyer_headers = {"Authorization": f"Bearer {buyer['token']}"}

    # Mock hosted checkout initialization to avoid live network call
    with patch.object(
        card_gateway,
        "initialize_checkout",
        new=AsyncMock(side_effect=lambda order, user, redirect_url, provider=None: {
            "provider": "FLUTTERWAVE",
            "provider_reference": order["order_reference"],
            "checkout_url": f"https://checkout.flutterwave.com/pay/{order['order_reference']}",
            "raw": {},
        }),
    ):
        combo_order = client.post(
            "/api/v1/commerce/checkout",
            headers=buyer_headers,
            json={"productId": "combo_bundle", "paymentMethod": "CARD"},
        ).json()["order"]

    # 1. Invalid webhook signature rejected
    bad_sig = client.post(
        "/api/v1/webhooks/flutterwave",
        headers={"verif-hash": "wrong_secret"},
        json={"event": "charge.completed", "data": {"tx_ref": combo_order["orderReference"], "status": "successful", "amount": 699, "currency": "USD", "id": 9001}},
    )
    assert bad_sig.status_code == 401

    # 2. Failed card payment webhook does NOT unlock download
    fail_wh = client.post(
        "/api/v1/webhooks/flutterwave",
        headers={"verif-hash": "flw_test_webhook_secret"},
        json={"event": "charge.completed", "data": {"tx_ref": combo_order["orderReference"], "status": "failed", "amount": 699, "currency": "USD", "id": 9002}},
    )
    assert fail_wh.status_code == 200
    assert client.get("/api/v1/resources/combo/download", headers=buyer_headers).status_code == 403

    # 3. Successful signed card webhook unlocks Combo ZIP & calculates 20% of $699 = $139.80
    ok_payload = {
        "event": "charge.completed",
        "data": {"tx_ref": combo_order["orderReference"], "status": "successful", "amount": 699.00, "currency": "USD", "id": 9003},
    }
    ok_wh = client.post("/api/v1/webhooks/flutterwave", headers={"verif-hash": "flw_test_webhook_secret"}, json=ok_payload)
    assert ok_wh.status_code == 200
    assert ok_wh.json()["status"] == "PAID"

    # 4. Duplicate webhook is idempotent (no duplicate commissions)
    dup_wh = client.post("/api/v1/webhooks/flutterwave", headers={"verif-hash": "flw_test_webhook_secret"}, json=ok_payload)
    assert dup_wh.status_code == 200
    assert dup_wh.json()["duplicate"] is True
    assert len(db.referral_commissions) == 1
    comm = next(iter(db.referral_commissions.values()))
    assert comm["commission_amount_usd"] == "139.80"
    assert comm["status"] == "PENDING"

    # 5. Combo ZIP download succeeds and contains all 5 PDFs
    zip_res = client.get("/api/v1/resources/combo/download", headers=buyer_headers)
    assert zip_res.status_code == 200
    with zipfile.ZipFile(io.BytesIO(zip_res.content)) as zf:
        assert len(zf.namelist()) >= 5

    # 6. Refund webhook revokes download access & reverses commission
    refund_wh = client.post(
        "/api/v1/webhooks/flutterwave",
        headers={"verif-hash": "flw_test_webhook_secret"},
        json={"event": "charge.refunded", "data": {"tx_ref": combo_order["orderReference"], "status": "refunded", "amount": 699, "currency": "USD", "id": 9004}},
    )
    assert refund_wh.status_code == 200
    assert refund_wh.json()["status"] == "REFUNDED"
    assert client.get("/api/v1/resources/combo/download", headers=buyer_headers).status_code == 403
    assert db.referral_commissions[comm["id"]]["status"] == "REVERSED"


def test_paystack_hmac_webhook_signature_and_admin_rbac(client, monkeypatch):
    secret = "sk_test_paystack_hmac_key"
    monkeypatch.setenv("PAYSTACK_SECRET_KEY", secret)

    user = _register_user(client, "pskuser@example.com").json()
    user_headers = {"Authorization": f"Bearer {user['token']}"}

    # Non-admin user rejected from admin endpoints
    assert client.get("/api/v1/admin/commerce/payments", headers=user_headers).status_code == 403
    assert client.put(
        "/api/v1/admin/commerce/crypto-wallet",
        headers=user_headers,
        json={"receiving_address": "0x1111111111111111111111111111111111111111", "primary_network": "ERC20", "primary_asset": "USDT"},
    ).status_code == 403

    # Read-only auditor cannot modify global crypto wallet
    assert client.put(
        "/api/v1/admin/commerce/crypto-wallet",
        headers=_auditor_headers(),
        json={"receiving_address": "0x1111111111111111111111111111111111111111", "primary_network": "ERC20", "primary_asset": "USDT"},
    ).status_code == 403

    # Create Paystack card order
    with patch.object(
        card_gateway,
        "initialize_checkout",
        new=AsyncMock(side_effect=lambda order, user, redirect_url, provider=None: {
            "provider": "PAYSTACK",
            "provider_reference": order["order_reference"],
            "checkout_url": f"https://checkout.paystack.com/{order['order_reference']}",
            "raw": {},
        }),
    ):
        ord_res = client.post(
            "/api/v1/commerce/checkout",
            headers=user_headers,
            json={"productId": "individual_pdf", "resourceId": "strat-dca-grid-hedging", "paymentMethod": "CARD", "cardProvider": "paystack"},
        ).json()["order"]

    raw_payload = json.dumps({
        "event": "charge.success",
        "data": {"id": 55501, "reference": ord_res["orderReference"], "status": "success", "amount": 9900, "currency": "USD"},
    }).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw_payload, hashlib.sha512).hexdigest()

    wh = client.post(
        "/api/v1/webhooks/paystack",
        content=raw_payload,
        headers={"Content-Type": "application/json", "x-paystack-signature": sig},
    )
    assert wh.status_code == 200
    assert wh.json()["status"] == "PAID"

    # Admin payments summary matches DB
    adm = client.get("/api/v1/admin/commerce/payments", headers=_admin_headers()).json()
    assert adm["summary"]["totalSales"] == 1
    assert adm["summary"]["totalRevenueUsd"] == "99.00"
    assert adm["summary"]["individualPdfSales"] == 1


# ---------------------------------------------------------------------------
# 19. ADMIN STRATEGY PDF UPLOAD, UPDATE & DELETE MANAGEMENT
# ---------------------------------------------------------------------------

def test_admin_upload_update_and_delete_strategy_pdf(client):
    import base64

    fake_bytes = base64.b64encode(b"<html>not a pdf</html>" * 10).decode("ascii")
    valid_pdf_bytes = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\n" + (b"%" * 120) + b"\n%%EOF\n"
    valid_b64 = "data:application/pdf;base64," + base64.b64encode(valid_pdf_bytes).decode("ascii")

    # 1. Read-only auditor rejected (403)
    ro_res = client.post(
        "/api/v1/admin/resources/strategies",
        headers=_auditor_headers(),
        json={"title": "Unauthorized Strategy", "pdfFilename": "unauth.pdf", "pdfBase64": valid_b64},
    )
    assert ro_res.status_code == 403

    # 2. Fake non-PDF content rejected (422)
    bad_res = client.post(
        "/api/v1/admin/resources/strategies",
        headers=_admin_headers(),
        json={"title": "Fake PDF Strategy", "pdfFilename": "fake.pdf", "pdfBase64": fake_bytes},
    )
    assert bad_res.status_code == 422

    # 3. Admin uploads genuine PDF strategy -> appears in public catalog at $99.00
    create_res = client.post(
        "/api/v1/admin/resources/strategies",
        headers=_admin_headers(),
        json={
            "title": "Admin Liquidity Sweep Playbook",
            "category": "Order Flow",
            "difficulty": "Institutional",
            "summary": "Custom admin-uploaded liquidity sweep strategy.",
            "pages": 18,
            "tags": ["Liquidity", "Sweep"],
            "pdfFilename": "admin-liquidity-sweep.pdf",
            "pdfBase64": valid_b64,
        },
    )
    assert create_res.status_code == 200
    created = create_res.json()["strategy"]
    strat_id = created["id"]
    assert created["fileExists"] is True

    # Appears in public /api/v1/resources catalog at $99.00
    pub_catalog = client.get("/api/v1/resources").json()["resources"]
    match = next((r for r in pub_catalog if r["id"] == strat_id), None)
    assert match is not None
    assert match["priceUsd"] == "99.00"
    assert match["title"] == "Admin Liquidity Sweep Playbook"

    # 4. Admin edits metadata cleanly
    upd_res = client.put(
        f"/api/v1/admin/resources/strategies/{strat_id}",
        headers=_admin_headers(),
        json={"title": "Admin Liquidity Sweep Playbook v2", "pages": 24},
    )
    assert upd_res.status_code == 200
    assert upd_res.json()["strategy"]["title"] == "Admin Liquidity Sweep Playbook v2"
    assert upd_res.json()["strategy"]["pages"] == 24

    # 5. Admin deletes strategy cleanly (cleanup test artifact)
    del_res = client.delete(
        f"/api/v1/admin/resources/strategies/{strat_id}",
        headers=_admin_headers(),
    )
    assert del_res.status_code == 200
    pub_after = client.get("/api/v1/resources").json()["resources"]
    assert all(r["id"] != strat_id for r in pub_after)
