-- ==============================================================================
-- NOVEXTRADE MIGRATION 002: REFERRALS, PRODUCT PRICING, CARD & CRYPTO PAYMENTS
-- ==============================================================================
-- Safe, idempotent PostgreSQL migration for Supabase / PostgreSQL.
-- Preserves all existing tables and extends schema with full commerce,
-- referral attribution, commissions, global crypto wallet config, and entitlements.
-- ==============================================================================

-- 1. Extend existing users table with unique referral code constraints
ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS referral_code VARCHAR(32),
    ADD COLUMN IF NOT EXISTS referred_by VARCHAR(64);

CREATE UNIQUE INDEX IF NOT EXISTS idx_users_referral_code_unique
    ON public.users(referral_code)
    WHERE referral_code IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_users_referred_by
    ON public.users(referred_by);

-- 2. Authoritative Products & Pricing Table
CREATE TABLE IF NOT EXISTS public.products (
    id VARCHAR(64) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    description TEXT,
    product_type VARCHAR(32) NOT NULL, -- INDIVIDUAL_PDF, COMBO_BUNDLE
    price_usd NUMERIC(12, 2) NOT NULL CHECK (price_usd > 0),
    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

INSERT INTO public.products (id, name, description, product_type, price_usd, currency, is_active, created_at, updated_at)
VALUES
    ('individual_pdf', 'Individual Strategy PDF Download', 'Single institutional trading strategy PDF playbook with lifetime verified access.', 'INDIVIDUAL_PDF', 99.00, 'USD', TRUE, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000),
    ('combo_bundle', 'Complete Institutional Strategy Combo', 'Full access to all 5 institutional strategy PDFs individually plus a bundled ZIP download.', 'COMBO_BUNDLE', 699.00, 'USD', TRUE, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000, EXTRACT(EPOCH FROM NOW())::BIGINT * 1000)
ON CONFLICT (id) DO UPDATE SET
    price_usd = EXCLUDED.price_usd,
    updated_at = EXCLUDED.updated_at;

-- 3. Referral Clicks Tracking
CREATE TABLE IF NOT EXISTS public.referral_clicks (
    id VARCHAR(64) PRIMARY KEY,
    referral_code VARCHAR(32) NOT NULL,
    referrer_user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    visitor_hash VARCHAR(128) NOT NULL,
    ip_address VARCHAR(64),
    user_agent TEXT,
    landing_path VARCHAR(512),
    converted_user_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ref_clicks_referrer ON public.referral_clicks(referrer_user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ref_clicks_code ON public.referral_clicks(referral_code);

-- 4. Permanent Referral Relationships
CREATE TABLE IF NOT EXISTS public.referral_relationships (
    id VARCHAR(64) PRIMARY KEY,
    referrer_user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    referred_user_id VARCHAR(64) NOT NULL UNIQUE REFERENCES public.users(id) ON DELETE CASCADE,
    referral_code VARCHAR(32) NOT NULL,
    source_click_id VARCHAR(64) REFERENCES public.referral_clicks(id) ON DELETE SET NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, FLAGGED, REVOKED
    override_by_admin_id VARCHAR(64),
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    CONSTRAINT chk_no_self_referral CHECK (referrer_user_id <> referred_user_id)
);

CREATE INDEX IF NOT EXISTS idx_ref_rel_referrer ON public.referral_relationships(referrer_user_id);

-- 5. Administrator-Controlled Referral Commission Configuration
CREATE TABLE IF NOT EXISTS public.referral_commission_config (
    id VARCHAR(32) PRIMARY KEY DEFAULT 'default',
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    individual_pdf_commission_percent NUMERIC(5, 2) NOT NULL DEFAULT 0.00 CHECK (individual_pdf_commission_percent >= 0 AND individual_pdf_commission_percent <= 100),
    combo_commission_percent NUMERIC(5, 2) NOT NULL DEFAULT 0.00 CHECK (combo_commission_percent >= 0 AND combo_commission_percent <= 100),
    min_payout_threshold_usd NUMERIC(12, 2) NOT NULL DEFAULT 50.00 CHECK (min_payout_threshold_usd >= 0),
    approval_mode VARCHAR(32) NOT NULL DEFAULT 'MANUAL', -- MANUAL, AUTO_AFTER_HOLD
    holding_period_days INTEGER NOT NULL DEFAULT 14 CHECK (holding_period_days >= 0),
    auto_payout_enabled BOOLEAN NOT NULL DEFAULT FALSE,
    terms_and_conditions TEXT NOT NULL DEFAULT 'Commissions are calculated on verified net USD purchases and subject to refund/chargeback reversal.',
    updated_by VARCHAR(64),
    updated_at BIGINT NOT NULL
);

-- 6. Product Checkout Orders
CREATE TABLE IF NOT EXISTS public.product_orders (
    id VARCHAR(64) PRIMARY KEY,
    order_reference VARCHAR(64) NOT NULL UNIQUE,
    user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    product_id VARCHAR(64) NOT NULL REFERENCES public.products(id),
    resource_id VARCHAR(128), -- Specific strategy ID for individual_pdf; NULL for combo_bundle
    amount_usd NUMERIC(12, 2) NOT NULL CHECK (amount_usd > 0),
    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    payment_method VARCHAR(32) NOT NULL, -- CARD, CRYPTO
    payment_provider VARCHAR(32) NOT NULL, -- FLUTTERWAVE, PAYSTACK, ONCHAIN_GLOBAL_WALLET
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING', -- PENDING, AWAITING_VERIFICATION, UNDERPAID, PAID, FAILED, CANCELLED, EXPIRED, REFUNDED, DISPUTED
    referral_code VARCHAR(32),
    referrer_user_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    idempotency_key VARCHAR(128) UNIQUE,
    expires_at BIGINT NOT NULL,
    paid_at BIGINT,
    refunded_at BIGINT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_product_orders_user ON public.product_orders(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_orders_status ON public.product_orders(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_product_orders_referrer ON public.product_orders(referrer_user_id);

-- 7. Payment Records (Card & Crypto Unified)
CREATE TABLE IF NOT EXISTS public.payment_records (
    id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL REFERENCES public.product_orders(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    payment_method VARCHAR(32) NOT NULL, -- CARD, CRYPTO
    provider VARCHAR(32) NOT NULL, -- FLUTTERWAVE, PAYSTACK, ONCHAIN_GLOBAL_WALLET
    provider_reference VARCHAR(128) NOT NULL UNIQUE,
    provider_tx_id VARCHAR(128),
    amount_usd NUMERIC(12, 2) NOT NULL,
    currency VARCHAR(8) NOT NULL DEFAULT 'USD',
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING',
    checkout_url TEXT,
    raw_metadata JSONB DEFAULT '{}'::JSONB,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_payment_records_order ON public.payment_records(order_id);

-- 8. Payment Verification & Webhook Events (Idempotency Ledger)
CREATE TABLE IF NOT EXISTS public.payment_verification_events (
    id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) REFERENCES public.product_orders(id) ON DELETE SET NULL,
    payment_id VARCHAR(64) REFERENCES public.payment_records(id) ON DELETE SET NULL,
    event_type VARCHAR(64) NOT NULL,
    provider_event_id VARCHAR(128) UNIQUE,
    status VARCHAR(32) NOT NULL,
    details JSONB DEFAULT '{}'::JSONB,
    created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_payment_events_order ON public.payment_verification_events(order_id, created_at DESC);

-- 9. Global Administrator Cryptocurrency Wallet Configuration
CREATE TABLE IF NOT EXISTS public.crypto_wallet_config (
    id VARCHAR(32) PRIMARY KEY DEFAULT 'global_default',
    is_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    receiving_address VARCHAR(128) NOT NULL,
    primary_asset VARCHAR(16) NOT NULL DEFAULT 'USDT',
    primary_network VARCHAR(32) NOT NULL DEFAULT 'ERC20',
    supported_tokens JSONB NOT NULL DEFAULT '["USDT","USDC","ETH"]'::JSONB,
    required_confirmations INTEGER NOT NULL DEFAULT 12 CHECK (required_confirmations >= 1),
    memo_tag VARCHAR(64),
    updated_by VARCHAR(64),
    updated_at BIGINT NOT NULL
);

-- 10. Cryptocurrency Transaction Records & Shared Wallet Reconciliation
CREATE TABLE IF NOT EXISTS public.crypto_transactions (
    id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) REFERENCES public.product_orders(id) ON DELETE SET NULL,
    user_id VARCHAR(64) REFERENCES public.users(id) ON DELETE SET NULL,
    tx_hash VARCHAR(128) NOT NULL UNIQUE,
    network VARCHAR(32) NOT NULL,
    asset VARCHAR(16) NOT NULL,
    expected_amount_crypto NUMERIC(36, 18) NOT NULL,
    received_amount_crypto NUMERIC(36, 18) DEFAULT 0,
    exchange_rate_usd NUMERIC(24, 8) NOT NULL,
    receiving_address VARCHAR(128) NOT NULL,
    sender_address VARCHAR(128),
    confirmations INTEGER NOT NULL DEFAULT 0,
    required_confirmations INTEGER NOT NULL DEFAULT 12,
    verification_status VARCHAR(32) NOT NULL DEFAULT 'PENDING', -- PENDING, CONFIRMED, UNDERPAID, OVERPAID, WRONG_NETWORK, WRONG_TOKEN, WRONG_ADDRESS, INVALID_TX, UNMATCHED_REVIEW, FAILED
    reconciliation_notes TEXT,
    verified_by_admin_id VARCHAR(64),
    raw_tx_data JSONB DEFAULT '{}'::JSONB,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_crypto_tx_order ON public.crypto_transactions(order_id);
CREATE INDEX IF NOT EXISTS idx_crypto_tx_status ON public.crypto_transactions(verification_status);

-- 11. Download Entitlements (Server-Side Verified Ownership)
CREATE TABLE IF NOT EXISTS public.download_entitlements (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    order_id VARCHAR(64) NOT NULL REFERENCES public.product_orders(id) ON DELETE CASCADE,
    product_id VARCHAR(64) NOT NULL REFERENCES public.products(id),
    resource_id VARCHAR(128) NOT NULL, -- specific strategy_id OR 'ALL_COMBO'
    status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, REVOKED
    revoked_reason TEXT,
    revoked_at BIGINT,
    granted_at BIGINT NOT NULL,
    UNIQUE(user_id, order_id, resource_id)
);

CREATE INDEX IF NOT EXISTS idx_entitlements_user ON public.download_entitlements(user_id, status);

-- 12. Download Activity Audit Logs
CREATE TABLE IF NOT EXISTS public.download_logs (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    entitlement_id VARCHAR(64) NOT NULL REFERENCES public.download_entitlements(id) ON DELETE CASCADE,
    resource_id VARCHAR(128) NOT NULL,
    ip_address VARCHAR(64),
    user_agent TEXT,
    created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_download_logs_user ON public.download_logs(user_id, created_at DESC);

-- 13. Referral Commissions (1-to-1 with Qualifying Order)
CREATE TABLE IF NOT EXISTS public.referral_commissions (
    id VARCHAR(64) PRIMARY KEY,
    order_id VARCHAR(64) NOT NULL UNIQUE REFERENCES public.product_orders(id) ON DELETE CASCADE,
    referrer_user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    referred_user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    product_id VARCHAR(64) NOT NULL REFERENCES public.products(id),
    purchase_amount_usd NUMERIC(12, 2) NOT NULL,
    commission_rate_percent NUMERIC(5, 2) NOT NULL,
    commission_amount_usd NUMERIC(12, 2) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PENDING', -- PENDING, APPROVED, PAID, CANCELLED, REVERSED
    hold_until BIGINT NOT NULL,
    approved_by VARCHAR(64),
    approved_at BIGINT,
    payout_id VARCHAR(64),
    reversal_reason TEXT,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ref_commissions_referrer ON public.referral_commissions(referrer_user_id, status);

-- 14. Referral Payouts
CREATE TABLE IF NOT EXISTS public.referral_payouts (
    id VARCHAR(64) PRIMARY KEY,
    referrer_user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    amount_usd NUMERIC(12, 2) NOT NULL CHECK (amount_usd > 0),
    payout_method VARCHAR(32) NOT NULL,
    payout_destination VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'REQUESTED', -- REQUESTED, PROCESSING, PAID, REJECTED
    reference VARCHAR(128),
    processed_by VARCHAR(64),
    processed_at BIGINT,
    created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_ref_payouts_referrer ON public.referral_payouts(referrer_user_id, created_at DESC);
