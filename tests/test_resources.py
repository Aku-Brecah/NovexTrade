import pytest
from starlette.testclient import TestClient
from syncnode.server import app
from syncnode.security.crypto import sign_token
from syncnode.database.db import db
from syncnode.database.repository import user_repository
from syncnode.services.commerce import commerce_service


@pytest.fixture(autouse=True)
def reset_state():
    db.reset()
    yield


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def auth_headers():
    user_repository.save({
        "id": "test_user_res_1",
        "email": "trader@novextrade.exchange",
        "full_name": "Test Strategy Trader",
        "is_suspended": False,
        "is_withdrawal_suspended": False,
    })
    token = sign_token({"userId": "test_user_res_1", "email": "trader@novextrade.exchange"})
    return {"Authorization": f"Bearer {token}"}


def test_get_strategy_resources_public_catalog(client):
    res = client.get("/api/v1/resources")
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert len(data["resources"]) >= 5
    assert data["pricing"]["individualPdfUsd"] == "99.00"
    assert data["pricing"]["comboBundleUsd"] == "699.00"

    first = data["resources"][0]
    assert "title" in first
    assert "category" in first
    assert "difficulty" in first
    assert "downloadUrl" in first
    assert "fileSize" in first
    assert first["priceUsd"] == "99.00"


def test_download_strategy_pdf_requires_authentication(client):
    res = client.get("/api/v1/resources/download/strat-momentum-playbook")
    assert res.status_code == 401


def test_download_strategy_pdf_rejects_unpaid_member(client, auth_headers):
    res = client.get(
        "/api/v1/resources/download/strat-momentum-playbook",
        headers=auth_headers
    )
    assert res.status_code == 403


def test_download_strategy_pdf_authenticated_paid_entitlement_success(client, auth_headers):
    # Grant verified entitlement via order finalization
    order = {
        "id": "ord_test_res_1",
        "order_reference": "NVX-RES-001",
        "user_id": "test_user_res_1",
        "product_id": "individual_pdf",
        "resource_id": "strat-momentum-playbook",
        "amount_usd": "99.00",
        "currency": "USD",
        "payment_method": "CRYPTO",
        "payment_provider": "ONCHAIN_GLOBAL_WALLET",
        "status": "PENDING",
        "expires_at": 9999999999999,
        "created_at": 1,
        "updated_at": 1,
    }
    db.product_orders[order["id"]] = order
    commerce_service._finalize_paid_order(order, None, provider_tx_id="0x" + "a" * 64)

    res = client.get(
        "/api/v1/resources/download/strat-momentum-playbook",
        headers=auth_headers
    )
    assert res.status_code == 200
    assert "application/pdf" in res.headers.get("content-type", "")
    assert 'attachment; filename="novextrade-institutional-momentum-playbook.pdf"' in res.headers.get("content-disposition", "")
    assert res.content.startswith(b"%PDF-1.4")
    assert len(res.content) > 500


def test_download_nonexistent_strategy_pdf(client, auth_headers):
    res = client.get(
        "/api/v1/resources/download/nonexistent-strategy-id",
        headers=auth_headers
    )
    assert res.status_code == 404
