import time
import pytest
from syncnode.common.types import AssetSymbol, AccountType, OrderSide, OrderType, OrderStatus, SelfTradePrevention
from syncnode.common.errors import FinancialInvariantError, ValidationError
from syncnode.database.db import db
from syncnode.services.matching_engine import matching_engine
from syncnode.services.wallet import wallet_service
from syncnode.services.ledger import ledger_service
from syncnode.services.investment import investment_service
from syncnode.services.p2p import p2p_service


@pytest.fixture(autouse=True)
def setup_db():
    db.reset()
    matching_engine.reset()


def test_matching_engine_price_improvement_and_taker_settlement():
    buyer = "usr_buyer_pi"
    seller = "usr_seller_pi"

    # Fund accounts
    wallet_service.credit_deposit(buyer, AssetSymbol.USDT, "100000.00")
    wallet_service.credit_deposit(seller, AssetSymbol.BTC, "1.00000000")

    # Seller places ask at 94000
    res_sell = matching_engine.place_order({
        "user_id": seller,
        "market": "BTC/USDT",
        "side": OrderSide.SELL,
        "price": "94000.00",
        "quantity": "1.00000000"
    })
    assert res_sell["order"]["status"] == OrderStatus.NEW

    # Buyer places aggressive limit buy at 96000 for 1 BTC (locks 96000 USDT)
    res_buy = matching_engine.place_order({
        "user_id": buyer,
        "market": "BTC/USDT",
        "side": OrderSide.BUY,
        "price": "96000.00",
        "quantity": "1.00000000"
    })

    assert res_buy["order"]["status"] == OrderStatus.FILLED
    assert len(res_buy["trades"]) == 1
    assert float(res_buy["trades"][0]["price"]) == 94000.0

    # Buyer should have 1 BTC and remaining 6000 USDT (100k - 94k), with 0 locked!
    buyer_usdt = ledger_service.get_user_asset_balance(buyer, AssetSymbol.USDT)
    assert buyer_usdt["available"] == "6000.00000000"
    assert buyer_usdt["locked"] == "0.00000000"

    buyer_btc = ledger_service.get_user_asset_balance(buyer, AssetSymbol.BTC)
    assert buyer_btc["available"] == "1.00000000"
    assert buyer_btc["locked"] == "0.00000000"

    # Seller should have 94000 USDT available and 0 BTC locked
    seller_usdt = ledger_service.get_user_asset_balance(seller, AssetSymbol.USDT)
    assert seller_usdt["available"] == "94000.00000000"
    assert seller_usdt["locked"] == "0.00000000"

    seller_btc = ledger_service.get_user_asset_balance(seller, AssetSymbol.BTC)
    assert seller_btc["available"] == "0.00000000"
    assert seller_btc["locked"] == "0.00000000"


def test_post_only_unlocks_funds_on_rejection():
    buyer = "usr_po_unlock"
    seller = "usr_seller_po_unlock"

    wallet_service.credit_deposit(seller, AssetSymbol.BTC, "1.00000000")
    wallet_service.credit_deposit(buyer, AssetSymbol.USDT, "50000.00")

    matching_engine.place_order({
        "user_id": seller,
        "market": "BTC/USDT",
        "side": OrderSide.SELL,
        "price": "45000.00",
        "quantity": "1.00000000"
    })

    # Buyer places Post-Only buy at 46000 (crosses book -> must be rejected and funds unlocked)
    res = matching_engine.place_order({
        "user_id": buyer,
        "market": "BTC/USDT",
        "side": OrderSide.BUY,
        "type": OrderType.POST_ONLY,
        "price": "46000.00",
        "quantity": "1.00000000"
    })

    assert res["order"]["status"] == OrderStatus.CANCELLED
    buyer_bal = ledger_service.get_user_asset_balance(buyer, AssetSymbol.USDT)
    assert buyer_bal["available"] == "50000.00000000"
    assert buyer_bal["locked"] == "0.00000000"


def test_ledger_rejects_negative_entries_and_zero_lock():
    uid = "usr_neg_test"
    wallet_service.credit_deposit(uid, AssetSymbol.USDT, "1000.00")

    acc_avail = ledger_service.get_or_create_account(
        AccountType.USER_AVAILABLE,
        AssetSymbol.USDT,
        uid
    )

    # Negative debit / credit must be rejected
    with pytest.raises(FinancialInvariantError):
        ledger_service.record_transaction(
            idempotency_key="tx_neg_test",
            description="Negative test",
            entries=[
                {"account_id": acc_avail["id"], "asset": AssetSymbol.USDT, "debit": "-50.00", "credit": "0.00"},
                {"account_id": acc_avail["id"], "asset": AssetSymbol.USDT, "debit": "0.00", "credit": "-50.00"},
            ]
        )

    # Zero or negative lock must be rejected
    with pytest.raises(FinancialInvariantError):
        ledger_service.lock_user_funds(uid, AssetSymbol.USDT, "0.00", "Zero lock")


def test_investment_subscription_and_claim_lifecycle():
    uid = "usr_investor_1"
    wallet_service.credit_deposit(uid, AssetSymbol.USDT, "2000.00")

    # Subscribe to starter plan (500 USDT)
    inv = investment_service.subscribe(uid, "plan_starter", "500.00")
    assert inv["status"] == "ACTIVE"

    # User balance should have 1500 available, 500 locked
    bal = ledger_service.get_user_asset_balance(uid, AssetSymbol.USDT)
    assert bal["available"] == "1500.00000000"
    assert bal["locked"] == "500.00000000"

    # Advance time to 50% duration
    duration_ms = inv["end_at"] - inv["created_at"]
    inv["created_at"] -= duration_ms // 2

    # Claim 50% profit
    claim_res = investment_service.claim_payout(uid, inv["id"])
    assert claim_res["success"] is True
    claimed_amt = float(claim_res["claimed_amount_usd"])
    assert claimed_amt > 0

    # User immediately attempts to claim again without time passing -> MUST fail
    with pytest.raises(ValidationError):
        investment_service.claim_payout(uid, inv["id"])

    # Advance time to maturity (100%): end_at has passed
    now_ms = int(time.time() * 1000)
    inv["end_at"] = now_ms - 1000
    final_res = investment_service.claim_payout(uid, inv["id"])
    assert final_res["status"] == "COMPLETED"

    # Principal 500 USDT is unlocked back to available
    bal_after = ledger_service.get_user_asset_balance(uid, AssetSymbol.USDT)
    assert bal_after["locked"] == "0.00000000"
    assert float(bal_after["available"]) >= 2000.0  # Initial 2000 + profits!


def test_p2p_limits_and_trade_cancellation():
    merchant_id = "usr_p2p_m"
    buyer_id = "usr_p2p_b"

    wallet_service.credit_deposit(merchant_id, AssetSymbol.USDT, "1000.00")

    ad = p2p_service.create_ad(merchant_id, {
        "type": "SELL",
        "asset": "USDT",
        "price": "1.00",
        "available_amount": "500.00",
        "min_limit": "50.00",
        "max_limit": "400.00",
        "payment_methods": ["Bank Transfer"]
    })

    # Below min limit
    with pytest.raises(ValidationError):
        p2p_service.initiate_trade({
            "ad_id": ad["id"],
            "buyer_user_id": buyer_id,
            "crypto_amount": "10.00"
        })

    # Above max limit
    with pytest.raises(ValidationError):
        p2p_service.initiate_trade({
            "ad_id": ad["id"],
            "buyer_user_id": buyer_id,
            "crypto_amount": "450.00"
        })

    # Valid trade
    trade = p2p_service.initiate_trade({
        "ad_id": ad["id"],
        "buyer_user_id": buyer_id,
        "crypto_amount": "200.00"
    })
    assert trade["status"] == "ESCROW_LOCKED"
    assert float(ad["available_amount"]) == 300.0

    # Non-disputed trade cannot be resolved by admin
    with pytest.raises(ValidationError):
        p2p_service.admin_resolve_dispute(trade["id"], "RELEASE", "admin_1", "premature")

    # Cancel trade
    cancelled = p2p_service.cancel_trade(trade["id"], buyer_id)
    assert cancelled["status"] == "CANCELLED"
    assert float(ad["available_amount"]) == 500.0  # restored!
