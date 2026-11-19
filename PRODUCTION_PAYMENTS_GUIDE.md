# NovexTrade Production Guide: Referrals, Product Pricing & Card/Crypto Payments

## 1. Authoritative Product Pricing
Prices are enforced strictly on the server in `syncnode/database/db.py` and `public.products`:
- **Individual Strategy PDF Download (`individual_pdf`)**: `$99.00 USD` — unlocks the specific strategy PDF purchased.
- **Complete Institutional Strategy Combo (`combo_bundle`)**: `$699.00 USD` — unlocks all 5 strategy PDFs individually plus a bundled ZIP download (`/api/v1/resources/combo/download`).

Client-supplied prices are validated and rejected (`400 Bad Request`) on any mismatch.

---

## 2. Database Migration (Supabase / PostgreSQL)
Run the idempotent migration script in your Supabase SQL Editor or via `psql`:
```bash
psql "$SUPABASE_DB_URL" -f supabase/migrations/002_referrals_payments.sql
```
This extends `public.users` with a unique index on `referral_code` and creates:
- `products`, `product_orders`, `payment_records`, `payment_verification_events`
- `crypto_wallet_config`, `crypto_transactions`
- `download_entitlements`, `download_logs`
- `referral_clicks`, `referral_relationships`, `referral_commission_config`, `referral_commissions`, `referral_payouts`

---

## 3. Required Production Environment Variables
Configure these in your hosting environment (never commit secrets to Git):

| Variable | Purpose |
|---|---|
| `APP_BASE_URL` | Production URL (e.g. `https://novextrade.exchange`) used for referral links & card checkout callbacks |
| `CARD_PAYMENT_PROVIDER` | `flutterwave` (default) or `paystack` |
| `FLUTTERWAVE_SECRET_KEY` | Flutterwave v3 secret key (sandbox `FLWSECK_TEST-...` or live `FLWSECK-...`) |
| `FLUTTERWAVE_WEBHOOK_HASH` | Secret hash configured in Flutterwave Dashboard → Webhooks (`verif-hash` header) |
| `PAYSTACK_SECRET_KEY` | Paystack secret key (used for hosted checkout + HMAC-SHA512 webhook verification) |
| `GLOBAL_CRYPTO_RECEIVING_ADDRESS` | Initial global receiving wallet shown to all users (editable in Admin Console) |
| `GLOBAL_CRYPTO_NETWORK` | `ERC20`, `BEP20`, `TRC20`, `BTC`, or `SOL` |
| `GLOBAL_CRYPTO_ASSET` | Primary crypto asset (`USDT`, `USDC`, `ETH`, `BNB`, `TRX`, `BTC`, `SOL`) |
| `GLOBAL_CRYPTO_CONFIRMATIONS` | Minimum on-chain confirmations before unlocking downloads (default `12`) |
| `ETH_RPC_URL`, `BSC_RPC_URL`, `TRONGRID_API_URL`, `TRONGRID_API_KEY`, `BTC_EXPLORER_API_URL`, `SOLANA_RPC_URL` | Blockchain RPC / Explorer endpoints for real server-side on-chain verification |

---

## 4. Webhook Registration
Register these HTTPS endpoints in your payment provider dashboard:
- **Flutterwave**: `POST https://<your-domain>/api/v1/webhooks/flutterwave`
  - Set Secret Hash to match `FLUTTERWAVE_WEBHOOK_HASH`.
  - Subscribe to: `charge.completed`, `charge.refunded`, `charge.dispute.create`.
- **Paystack**: `POST https://<your-domain>/api/v1/webhooks/paystack`
  - Verified automatically using `x-paystack-signature` (HMAC-SHA512 with `PAYSTACK_SECRET_KEY`).
  - Subscribe to: `charge.success`, `charge.failed`, `refund.processed`, `charge.dispute.create`.

---

## 5. Post-Deployment Admin Checklist
1. Log into `/admin` as `SUPER_ADMIN` or `FINANCE_ADMIN`.
2. Open **Commerce & Referrals → Global Crypto Wallet** and set your verified production receiving wallet address, network, and supported tokens.
3. Open **Commerce & Referrals → Referrals & Commissions** and configure your desired commission percentages for Individual PDFs ($99) and Combo Bundles ($699), minimum payout threshold, holding period, and terms.
4. Perform one sandbox card checkout and one testnet/small crypto transaction to verify end-to-end webhook delivery, download unlocking, and commission calculation.
