import os
import asyncio
from typing import Dict, Set, List, Any, Optional
from syncnode.common.types import AssetSymbol, AccountType
from syncnode.common.logger import Logger

logger = Logger("Database")


class Database:
    _instance = None

    def __init__(self):
        self.users: Dict[str, Any] = {}
        self.users_by_email: Dict[str, str] = {}
        self.users_by_referral_code: Dict[str, str] = {}

        # Product Pricing, Orders, Payments, Crypto & Referral Systems
        self.products: Dict[str, Dict[str, Any]] = {}
        self.referral_clicks: Dict[str, Dict[str, Any]] = {}
        self.referral_relationships: Dict[str, Dict[str, Any]] = {}  # keyed by referred_user_id
        self.referral_commission_config: Dict[str, Any] = {}
        self.referral_commissions: Dict[str, Dict[str, Any]] = {}  # keyed by id
        self.referral_commissions_by_order: Dict[str, str] = {}    # order_id -> commission_id
        self.referral_payouts: Dict[str, Dict[str, Any]] = {}

        self.product_orders: Dict[str, Dict[str, Any]] = {}        # keyed by order_id
        self.product_orders_by_ref: Dict[str, str] = {}            # order_reference -> order_id
        self.product_orders_by_idempotency: Dict[str, str] = {}    # idempotency_key -> order_id
        self.payment_records: Dict[str, Dict[str, Any]] = {}       # keyed by payment_id
        self.payment_records_by_provider_ref: Dict[str, str] = {}  # provider_reference -> payment_id
        self.payment_verification_events: List[Dict[str, Any]] = []
        self.processed_webhook_events: Set[str] = set()

        self.crypto_wallet_config: Dict[str, Any] = {}
        self.crypto_transactions: Dict[str, Dict[str, Any]] = {}   # keyed by id
        self.crypto_tx_by_hash: Dict[str, str] = {}                # normalized tx_hash -> id

        self.download_entitlements: Dict[str, Dict[str, Any]] = {} # keyed by entitlement_id
        self.download_logs: List[Dict[str, Any]] = []

        self.api_keys: Dict[str, Any] = {}
        self.api_keys_by_key: Dict[str, str] = {}

        self.accounts: Dict[str, Dict[str, Any]] = {}
        self.journal_entries: Dict[str, Any] = {}
        self.ledger_transactions: Dict[str, Any] = {}
        self.idempotency_keys: Set[str] = set()

        self.orders: Dict[str, Any] = {}
        self.trades: Dict[str, Any] = {}
        self.deposits: Dict[str, Any] = {}
        self.withdrawals: Dict[str, Any] = {}
        self.transfers: Dict[str, Any] = {}

        self.p2p_ads: Dict[str, Any] = {}
        self.p2p_trades: Dict[str, Any] = {}

        self.deposit_addresses: Dict[str, Any] = {}
        self.investment_plans: Dict[str, Any] = {}
        self.user_investments: Dict[str, Any] = {}
        self.payment_history: List[Any] = []

        self.audit_logs: List[Any] = []
        self.outbox: List[Any] = []

        self.circuit_breakers = {
            "is_global_trading_halted": False,
            "halted_markets": {},
            "is_withdrawals_paused": False,
            "is_deposits_paused": False,
            "emergency_maintenance": False
        }

        self.mongo_client = None
        self.mongo_db = None
        self._is_connected = False
        self._is_supabase_connected = False

    def bootstrap_admin(self):
        from syncnode.security.crypto import hash_password
        from syncnode.common.types import KycTier, KycStatus, AdminRole
        import time

        admin_email = os.environ.get("ADMIN_BOOTSTRAP_EMAIL", "admin@novextrade.exchange").strip().lower()
        admin_pass = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD", "NovexTrade2026!Secure")
        admin_id = "admin_super_exec_1"
        now_ms = int(time.time() * 1000)
        user = {
            "id": admin_id,
            "email": admin_email,
            "full_name": "Executive Admin",
            "password_hash": hash_password(admin_pass),
            "is_totp_enabled": False,
            "kyc_tier": KycTier.TIER_3_INSTITUTIONAL.value,
            "kyc_status": KycStatus.APPROVED.value,
            "admin_roles": [AdminRole.SUPER_ADMIN.value],
            "is_suspended": False,
            "is_withdrawal_suspended": False,
            "referral_code": "NVXADMIN01",
            "referred_by": None,
            "created_at": now_ms,
            "updated_at": now_ms
        }
        self.users[admin_id] = user
        self.users_by_email[admin_email] = admin_id
        self.users_by_referral_code["NVXADMIN01"] = admin_id

        # Authoritative Server-Side Product Catalog & Pricing (USD)
        self.products = {
            "individual_pdf": {
                "id": "individual_pdf",
                "name": "Individual Strategy PDF Download",
                "description": "Single institutional strategy PDF playbook with lifetime verified access.",
                "product_type": "INDIVIDUAL_PDF",
                "price_usd": "99.00",
                "currency": "USD",
                "is_active": True,
                "created_at": now_ms,
                "updated_at": now_ms,
            },
            "combo_bundle": {
                "id": "combo_bundle",
                "name": "Complete Institutional Strategy Combo",
                "description": "Unlocks all 5 institutional strategy PDFs individually plus a bundled ZIP download.",
                "product_type": "COMBO_BUNDLE",
                "price_usd": "699.00",
                "currency": "USD",
                "is_active": True,
                "created_at": now_ms,
                "updated_at": now_ms,
            },
        }

        # Admin-Controlled Referral Commission Configuration (0% default until admin configures)
        self.referral_commission_config = {
            "id": "default",
            "is_enabled": True,
            "individual_pdf_commission_percent": "0.00",
            "combo_commission_percent": "0.00",
            "min_payout_threshold_usd": "50.00",
            "approval_mode": "MANUAL",  # MANUAL | AUTO_AFTER_HOLD
            "holding_period_days": 14,
            "auto_payout_enabled": False,
            "terms_and_conditions": (
                "Referral commissions are calculated strictly on verified net USD purchases. "
                "Self-referrals are prohibited. Refunded, cancelled, or disputed orders automatically reverse associated commissions."
            ),
            "updated_by": admin_id,
            "updated_at": now_ms,
        }

        # Single Global Administrator-Configured Cryptocurrency Receiving Wallet
        # Every registered user sees this exact receiving wallet address.
        self.crypto_wallet_config = {
            "id": "global_default",
            "is_enabled": True,
            "receiving_address": os.environ.get(
                "GLOBAL_CRYPTO_RECEIVING_ADDRESS",
                "0x71C8366420A092679b5436194448873305370caD"
            ),
            "primary_asset": os.environ.get("GLOBAL_CRYPTO_ASSET", "USDT"),
            "primary_network": os.environ.get("GLOBAL_CRYPTO_NETWORK", "ERC20"),
            "supported_tokens": ["USDT", "USDC", "ETH"],
            "required_confirmations": int(os.environ.get("GLOBAL_CRYPTO_CONFIRMATIONS", "12")),
            "memo_tag": os.environ.get("GLOBAL_CRYPTO_MEMO_TAG") or None,
            "updated_by": admin_id,
            "updated_at": now_ms,
        }

        # Seed Default Admin-Managed Deposit Wallets
        self.deposit_addresses = {
            "BTC": {
                "asset": "BTC",
                "network": "BTC",
                "address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
                "memo": None,
                "qr_code_url": "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=1A1zP1eP5QGefi2DMPTfTL5SLmv7DivfNa",
                "min_deposit": "0.0005",
                "confirmations_required": 1,
                "updated_at": int(time.time() * 1000)
            },
            "ETH": {
                "asset": "ETH",
                "network": "ERC20",
                "address": "0x71C8366420A092679b5436194448873305370caD",
                "memo": None,
                "qr_code_url": "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=0x71C8366420A092679b5436194448873305370caD",
                "min_deposit": "0.01",
                "confirmations_required": 12,
                "updated_at": int(time.time() * 1000)
            },
            "USDT_TRC20": {
                "asset": "USDT",
                "network": "TRC20",
                "address": "TYDzsYUEpvnYmQk4zGP9sWWcTEd3ZiPULj",
                "memo": None,
                "qr_code_url": "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=TYDzsYUEpvnYmQk4zGP9sWWcTEd3ZiPULj",
                "min_deposit": "10.00",
                "confirmations_required": 1,
                "updated_at": int(time.time() * 1000)
            },
            "USDT_ERC20": {
                "asset": "USDT",
                "network": "ERC20",
                "address": "0x71C8366420A092679b5436194448873305370caD",
                "memo": None,
                "qr_code_url": "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=0x71C8366420A092679b5436194448873305370caD",
                "min_deposit": "10.00",
                "confirmations_required": 12,
                "updated_at": int(time.time() * 1000)
            },
            "BNB": {
                "asset": "BNB",
                "network": "BEP20",
                "address": "0x71C8366420A092679b5436194448873305370caD",
                "memo": None,
                "qr_code_url": "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=0x71C8366420A092679b5436194448873305370caD",
                "min_deposit": "0.05",
                "confirmations_required": 15,
                "updated_at": int(time.time() * 1000)
            },
            "SOL": {
                "asset": "SOL",
                "network": "SOL",
                "address": "8J9bXwV6hKqZ7K9Z8gGZ9e7kK9Z8gGZ9e7kK9Z8gGZ9e",
                "memo": None,
                "qr_code_url": "https://api.qrserver.com/v1/create-qr-code/?size=200x200&data=8J9bXwV6hKqZ7K9Z8gGZ9e7kK9Z8gGZ9e7kK9Z8gGZ9e",
                "min_deposit": "0.10",
                "confirmations_required": 32,
                "updated_at": int(time.time() * 1000)
            }
        }

        # Seed Default High-Yield Investment Plans
        self.investment_plans = {
            "plan_starter": {
                "id": "plan_starter",
                "name": "Starter Yield Staking",
                "badge": "POPULAR",
                "min_deposit_usd": "500.00",
                "max_deposit_usd": "2499.00",
                "return_rate_percent": "140",
                "duration_days": 7,
                "daily_yield_percent": "20.00",
                "description": "Short-term high-yield liquidity pool with automated daily compounding payouts.",
                "is_active": True,
                "total_staked_usd": "148200.00",
                "investors_count": 86
            },
            "plan_growth": {
                "id": "plan_growth",
                "name": "Growth Matrix Pool",
                "badge": "HIGH YIELD",
                "min_deposit_usd": "2500.00",
                "max_deposit_usd": "9999.00",
                "return_rate_percent": "180",
                "duration_days": 14,
                "daily_yield_percent": "12.85",
                "description": "Algorithmic market-making & arbitrage yield fund with guaranteed capital protection.",
                "is_active": True,
                "total_staked_usd": "485600.00",
                "investors_count": 52
            },
            "plan_whale": {
                "id": "plan_whale",
                "name": "Whale Capital Strategy",
                "badge": "VIP CHOICE",
                "min_deposit_usd": "10000.00",
                "max_deposit_usd": "49999.00",
                "return_rate_percent": "250",
                "duration_days": 30,
                "daily_yield_percent": "8.33",
                "description": "Institutional HFT liquidity allocation with private execution desk and 250% target maturity (e.g. $10k -> $25k).",
                "is_active": True,
                "total_staked_usd": "1850000.00",
                "investors_count": 34
            },
            "plan_vip_elite": {
                "id": "plan_vip_elite",
                "name": "Executive Institutional Club",
                "badge": "MAX ROI",
                "min_deposit_usd": "50000.00",
                "max_deposit_usd": "500000.00",
                "return_rate_percent": "300",
                "duration_days": 45,
                "daily_yield_percent": "6.67",
                "description": "Private equity cross-market arbitrage vault with principal preservation warranty.",
                "is_active": True,
                "total_staked_usd": "3400000.00",
                "investors_count": 14
            }
        }

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = Database()
            cls._instance.bootstrap_admin()
        return cls._instance

    def reset(self):
        self.users.clear()
        self.users_by_email.clear()
        self.users_by_referral_code.clear()
        self.products.clear()
        self.referral_clicks.clear()
        self.referral_relationships.clear()
        self.referral_commission_config.clear()
        self.referral_commissions.clear()
        self.referral_commissions_by_order.clear()
        self.referral_payouts.clear()
        self.product_orders.clear()
        self.product_orders_by_ref.clear()
        self.product_orders_by_idempotency.clear()
        self.payment_records.clear()
        self.payment_records_by_provider_ref.clear()
        self.payment_verification_events.clear()
        self.processed_webhook_events.clear()
        self.crypto_wallet_config.clear()
        self.crypto_transactions.clear()
        self.crypto_tx_by_hash.clear()
        self.download_entitlements.clear()
        self.download_logs.clear()
        self.api_keys.clear()
        self.api_keys_by_key.clear()
        self.accounts.clear()
        self.journal_entries.clear()
        self.ledger_transactions.clear()
        self.idempotency_keys.clear()
        self.orders.clear()
        self.trades.clear()
        self.deposits.clear()
        self.withdrawals.clear()
        self.transfers.clear()
        self.p2p_ads.clear()
        self.p2p_trades.clear()
        self.audit_logs.clear()
        self.outbox.clear()
        self.circuit_breakers = {
            "is_global_trading_halted": False,
            "halted_markets": {},
            "is_withdrawals_paused": False,
            "is_deposits_paused": False,
            "emergency_maintenance": False
        }
        self.bootstrap_admin()

    async def connect_mongo(self, uri: str = None):
        uri = uri or os.environ.get("MONGODB_URI", "mongodb://localhost:27017/novextrade")
        try:
            from motor.motor_asyncio import AsyncIOMotorClient
            self.mongo_client = AsyncIOMotorClient(uri, serverSelectionTimeoutMS=2000)
            self.mongo_db = self.mongo_client.get_default_database()
            # Verify connection
            await self.mongo_db.command("ping")
            self._is_connected = True
            logger.info(f"Connected to MongoDB via Motor at {uri}")
        except Exception as e:
            logger.warn(f"MongoDB connection optional fallback (in-memory mode active): {str(e)}")
            self._is_connected = False

    async def connect_supabase(self, url: str = None, key: str = None):
        """Initializes Supabase connection and hydrates engine memory state from PostgreSQL tables."""
        from syncnode.database.supabase_client import supabase_client
        if supabase_client.initialize(url=url, key=key):
            is_alive = await supabase_client.test_connection()
            if is_alive:
                self._is_supabase_connected = True
                await supabase_client.hydrate_all(self)
                logger.info("Supabase PostgreSQL cloud storage active and synchronized.")
            else:
                self._is_supabase_connected = False
                logger.warning("Supabase configured but ping check failed. Falling back to local memory persistence.")
        else:
            self._is_supabase_connected = False


db = Database.get_instance()
