import pytest
from starlette.testclient import TestClient
from syncnode.server import app
from syncnode.security.crypto import sign_token
from syncnode.database.repository import user_repository


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

    first = data["resources"][0]
    assert "title" in first
    assert "category" in first
    assert "difficulty" in first
    assert "downloadUrl" in first
    assert "fileSize" in first


def test_download_strategy_pdf_requires_authentication(client):
    # Members-Only requirement: unauthenticated request MUST return 401
    res = client.get("/api/v1/resources/download/strat-momentum-playbook")
    assert res.status_code == 401


def test_download_strategy_pdf_authenticated_success(client, auth_headers):
    # Authenticated member can stream the PDF
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
