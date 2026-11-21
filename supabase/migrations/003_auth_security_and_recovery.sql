-- ==============================================================================
-- NOVEXTRADE MIGRATION 003: AUTHENTICATION SECURITY, SESSION REVOCATION & RECOVERY
-- ==============================================================================
-- Non-destructive, idempotent migration preserving all existing user accounts.
-- ==============================================================================

ALTER TABLE public.users
    ADD COLUMN IF NOT EXISTS token_version INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS is_email_verified BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS is_phone_verified BOOLEAN NOT NULL DEFAULT FALSE;

CREATE TABLE IF NOT EXISTS public.password_reset_tokens (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
    token_hash VARCHAR(128) NOT NULL UNIQUE,
    expires_at BIGINT NOT NULL,
    used_at BIGINT,
    request_ip VARCHAR(64),
    created_at BIGINT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_pwd_reset_user ON public.password_reset_tokens(user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_pwd_reset_expires ON public.password_reset_tokens(expires_at);
