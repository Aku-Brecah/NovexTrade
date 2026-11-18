# NovexTrade Platform Transformation & Remediation Plan

**Task Slug:** `novextrade-platform-plan`  
**Date:** 2026-11-18  
**Project Type:** Full-Stack Web App + FastAPI Backend (Cryptocurrency & Asset Exchange)  
**Status:** Planning / Awaiting Socratic Gate Clearance  

---

## 1. Overview & Objectives

Transform the legacy Syncnode/CryptoBridge platform into **NovexTrade**, addressing all critical audit vulnerabilities, repairing financial engine invariants, unifying brand identity, and introducing an institutional-grade **Strategy Resources & PDF Downloads Library**.

### Three Core Pillars:
1. **Audit Remediation & Security Hardening**: Eliminate P0/P1 exploits (auth bypasses, open Supabase RLS, hardcoded secrets/admin credentials, matching engine double-charging, infinite investment drain, P2P escrow double-spend, `AdjustBalanceModal` crash, and `EmailTemplatesView` XSS).
2. **Comprehensive Rebranding to "NovexTrade"**: Eradicate fragmented naming (`Syncnode`, `CryptoBridge`, `Signalist`, `NexLink`) across frontend metadata, navbar, auth, emails, backend APIs, templates, database defaults, and documentation.
3. **Institutional Strategy Resources Page (`/resources`)**: A responsive, accessible portal for traders to explore and download institutional strategy playbooks, algorithmic guides, and risk management PDF whitepapers.

---

## 2. Measurable Success Criteria

- [ ] **Typecheck & Build**: `tsc --noEmit` and `npm run build` pass with zero errors in `apps/web/`.
- [ ] **Test Suite**: Backend `pytest` suite passes 100% with newly added regression tests covering auth, ledger invariants, matching engine settlement, and investment math.
- [ ] **Security Scans**: `security_scan.py` returns 0 Critical and 0 High vulnerabilities; all 10 Supabase tables have restrictive RLS; `npm audit` vulnerabilities patched.
- [ ] **Rebranding Uniformity**: 0 references to "Syncnode", "CryptoBridge", or "Signalist" in user-facing UI and API responses; brand identity unified as "NovexTrade".
- [ ] **Strategy PDF Portal**: Live, responsive `/resources` view with category filtering, search, metadata badges, and working PDF download delivery with loading and empty states.
- [ ] **Financial Invariants**: Matching engine balances strictly conserved (`USER_LOCKED` -> settlement, no negative amounts, no taker double-charging); P2P escrow transitions strictly enforced.

---

## 3. Tech Stack & Architectural Decisions

| Layer | Technology | Decision & Rationale |
|---|---|---|
| **Frontend** | React 18, Vite, TypeScript | SPA architecture. Enforce strict typing (eliminate `any`), purge dead code. |
| **Auth** | Clerk (`@clerk/clerk-react` v5) + Native Auth | Remove unused `@clerk/react` v6 and dead Supabase SSR files. Cryptographically verify Clerk session tokens via JWKS. |
| **Backend** | Python 3.10+, FastAPI, Uvicorn | Async API gateway. Call `load_dotenv()` on startup. Add domain routers. |
| **Database & Ledger** | Supabase (PostgreSQL) + in-memory engine | Author canonical SQL migrations matching Python models; enforce `CHECK (balance >= 0)`. |
| **PDF Delivery** | FastApi streaming / Vite public assets | Bundled downloadable institutional trading strategy PDFs with backend verification and metadata registry. |
| **Styling** | Tailwind CSS + Custom Design Tokens | Clean dark-mode institutional aesthetic (#0b0e11 base, #f0b90b gold accent, #0ecb81 green, #f6465d red). Eliminate Binance hotlinks. |

---

## 4. File Structure & Changes

```
syncnode/ (to be rebranded NovexTrade)
├── apps/web/
│   ├── public/
│   │   ├── favicon.ico                         # New NovexTrade branding favicon
│   │   └── resources/                          # Bundled Strategy PDF whitepapers
│   │       ├── novextrade-momentum-playbook.pdf
│   │       ├── algorithmic-dca-hedging.pdf
│   │       ├── crypto-derivatives-risk-mgmt.pdf
│   │       └── p2p-arbitrage-liquidity-guide.pdf
│   ├── src/
│   │   ├── components/
│   │   │   ├── resources/                      # [NEW] Strategy Resource Library
│   │   │   │   ├── StrategyResourcesView.tsx
│   │   │   │   ├── ResourceCard.tsx
│   │   │   │   └── ResourceFilterBar.tsx
│   │   │   ├── admin/users/AdjustBalanceModal.tsx # Fix useEffect crash
│   │   │   ├── EmailTemplatesView.tsx          # Fix iframe srcDoc XSS
│   │   │   ├── DashboardView.tsx               # Fix $0.00 balance (b.available), dynamic deposit addr
│   │   │   └── Navbar.tsx, Footer.tsx          # NovexTrade rebranding & Resources link
│   │   ├── services/
│   │   │   ├── apiClient.ts                    # Centralized typed HTTP client
│   │   │   └── resourcesService.ts             # Strategy resource data & download helper
│   │   └── types/resources.ts                  # Strategy resource interfaces
├── syncnode/ (backend package)
│   ├── server.py                               # Rebrand, load_dotenv, verify Clerk JWKS, mount /api/v1/resources
│   ├── services/
│   │   ├── matching_engine.py                  # Fix taker settlement & unlock traps
│   │   ├── ledger.py                           # Strict debit/credit >= 0 checks
│   │   ├── investment.py                       # Fix claim_payout delta & vault signs
│   │   └── p2p.py                              # Fix cancel_trade status & dispute resolution
│   ├── security/
│   │   ├── crypto.py                           # Fail-closed JWT secret, remove fail-open TOTP
│   │   └── otp_service.py                      # Stop returning plaintext OTP in HTTP response
│   └── database/
│       ├── db.py                               # Rebrand admin defaults, remove hardcoded credentials
│       └── models.py                           # Align models with Supabase schema
└── supabase/
    └── schema.sql                              # Fix RLS (TO service_role), add missing tables & constraints
```

---

## 5. Vertical Slices & Task Breakdown

### Slice 1: Security & Containment Hotfixes (P0)
- [x] **Task 1.1: Fix Supabase RLS & Frontend Secret Hygiene**
  - **Agent:** `security-auditor` | **Skill:** `vulnerability-scanner`
  - **Input:** `supabase/schema.sql`, `apps/web/src/lib/supabase.ts`, `apps/web/src/utils/supabase/client.ts`
  - **Output:** Drop `USING (true)` public policies; restrict RLS to `TO service_role`; remove hardcoded live Supabase/Clerk keys from frontend; remove `CLERK_SECRET_KEY` from `apps/web/.env`.
  - **Verify:** `python .agents/skills/vulnerability-scanner/scripts/security_scan.py .` passes with 0 critical secrets.

- [x] **Task 1.2: Remove Hardcoded Admin Credentials & Fail-Closed Secrets**
  - **Agent:** `security-auditor` | **Skill:** `clean-code`
  - **Input:** `syncnode/database/db.py`, `syncnode/server.py`, `syncnode/admin/router.py`, `syncnode/security/crypto.py`
  - **Output:** Remove `poweldayck@gmail.com` and hardcoded password defaults from backend and unauthenticated HTML login form; raise `RuntimeError` if `JWT_SECRET` is missing in production.
  - **Verify:** Startup fails when `JWT_SECRET` is unset; `/admin` HTML has empty login inputs.

- [x] **Task 1.3: Cryptographic Token Verification on OAuth/Clerk Auth**
  - **Agent:** `backend-specialist` | **Skill:** `clerk`
  - **Input:** `syncnode/server.py:348-595`, `apps/web/src/App.tsx:550-610`
  - **Output:** Send signed Clerk session token via `useAuth().getToken()`; backend verifies Clerk JWKS (`RS256`); remove unauthenticated raw email overrides and demo auto-login bypasses.
  - **Verify:** Submitting arbitrary email to `/api/v1/auth/clerk` without valid Clerk JWT returns HTTP 401.

- [x] **Task 1.4: Fix Frontend Runtime Crash & Email Template XSS**
  - **Agent:** `frontend-specialist` | **Skill:** `clean-code`
  - **Input:** `apps/web/src/components/admin/users/AdjustBalanceModal.tsx`, `apps/web/src/components/EmailTemplatesView.tsx`, `apps/web/src/utils/emailTemplates.ts`
  - **Output:** Add `import { useEffect } from 'react'`; HTML-escape template variables and add `sandbox=""` to preview iframes; update `apps/web/package.json` build script to `tsc --noEmit && vite build`.
  - **Verify:** `apps/web/node_modules/.bin/tsc --noEmit` exits with 0 errors.

---

### Slice 2: Financial Engine & Accounting Repairs (P0)
- [x] **Task 2.1: Matching Engine Settlement & Ledger Integrity**
  - **Agent:** `backend-specialist` | **Skill:** `clean-code`
  - **Input:** `syncnode/services/matching_engine.py`, `syncnode/services/ledger.py`
  - **Output:** Settle taker orders strictly from `USER_LOCKED`; refund price improvement; unlock funds on `POST_ONLY` and `STP` cancels; reject negative/zero debit and credit amounts in `ledger.py`.
  - **Verify:** Add unit test in `tests/test_matching_engine.py` asserting exact-balance taker fill and balanced ledger conservation.

- [x] **Task 2.2: Fix Investment Staking Math & Vault Invariants**
  - **Agent:** `backend-specialist` | **Skill:** `clean-code`
  - **Input:** `syncnode/services/investment.py`, `syncnode/database/db.py`
  - **Output:** Track `claimed_profit_usd` incrementally; calculate payout strictly as `accrued - claimed` using pure `Decimal`; fix vault debit/credit accounting signs; strip commas from plan numbers.
  - **Verify:** Add unit test in `tests/test_investment.py` verifying repeated claims do not drain infinite funds.

- [x] **Task 2.3: P2P Escrow State Transitions**
  - **Agent:** `backend-specialist` | **Skill:** `clean-code`
  - **Input:** `syncnode/services/p2p.py`
  - **Output:** Set `status = CANCELLED` on `cancel_trade()`; restrict `admin_resolve_dispute()` to `status == DISPUTED`; enforce `available_amount` decrements.
  - **Verify:** Add unit test in `tests/test_p2p.py` proving cancelled trade cannot be released or double-refunded.

---

### Slice 3: Global Rebranding to "NovexTrade" (P1)
- [x] **Task 3.1: Frontend Rebranding & Metadata Modernization**
  - **Agent:** `frontend-specialist` | **Skill:** `frontend-design`
  - **Input:** `apps/web/index.html`, `apps/web/src/components/Navbar.tsx`, `apps/web/src/components/Footer.tsx`, `apps/web/src/components/HomeView.tsx`, `apps/web/src/components/SignupView.tsx`, `apps/web/src/components/admin/AdminConsole.tsx`
  - **Output:** Update titles, logos, headers, footers, meta tags, and OpenGraph descriptors to **NovexTrade**; remove all hotlinked Binance fonts/favicons and references to CryptoBridge/Signalist.
  - **Verify:** Grep across `apps/web/` returns zero hits for legacy branding strings in user-facing views.

- [x] **Task 3.2: Backend Rebranding & Configuration Alignment**
  - **Agent:** `backend-specialist` | **Skill:** `clean-code`
  - **Input:** `syncnode/server.py`, `syncnode/admin/router.py`, `syncnode/web/templates.py`, `package.json`, `pyproject.toml`, `README.md`, `DESIGN.md`
  - **Output:** Rename app titles, emails, admin templates, package manifests, and documentation to **NovexTrade**; set default admin bootstrap to `admin@novextrade.exchange`.
  - **Verify:** `curl http://localhost:4000/api/v1/health` and `/` return `name: "NovexTrade"`.

---

### Slice 4: Institutional Strategy Resources & PDF Download Portal (P1)
- [x] **Task 4.1: Strategy PDF Assets & Metadata Model**
  - **Agent:** `frontend-specialist` | **Skill:** `frontend-design`
  - **Input:** `resources/pdfs/`, `syncnode/services/resources.py`
  - **Output:** Create institutional strategy PDF documents covering:
    1. *NovexTrade Institutional Momentum Playbook*
    2. *Algorithmic Dollar-Cost Averaging & Grid Hedging Guide*
    3. *Cryptocurrency Derivatives & Tail-Risk Management*
    4. *P2P Market Making & Cross-Venue Arbitrage Manual*
    5. *Proof of Reserves & Double-Entry Ledger Mathematical Audit*
    Define typed metadata registry, streaming endpoints with members-only authentication gating.
  - **Verify:** Verified via `tests/test_resources.py` (4/4 passed).

- [x] **Task 4.2: Strategy Resources UI View (`StrategyResourcesView.tsx`)**
  - **Agent:** `frontend-specialist` | **Skill:** `frontend-design`
  - **Input:** `apps/web/src/components/resources/StrategyResourcesView.tsx`, `apps/web/src/App.tsx`, `apps/web/src/components/Navbar.tsx`
  - **Output:** Build the `/resources` view featuring:
    - Search input & category pills (All, Momentum & Order Flow, Algorithmic & Grid, Derivatives & Options, P2P & Arbitrage, Institutional Audit).
    - Institutional strategy cards with badges, overview bullets, file size, and primary "Download PDF" action with authenticated session token streaming.
    - Loading skeletons, empty state when filters yield no matches, and error boundaries.
    - Add "Strategies & Resources" link to Navbar and Footer navigation.
  - **Verify:** `npm run build` succeeds cleanly, bundling `StrategyResourcesView-CfAInESK.js`.

---

### Slice 5: Dead Code Removal & Quality Polish (P2)
- [ ] **Task 5.1: Purge Dead Code & Unused Packages**
  - **Agent:** `frontend-specialist` | **Skill:** `clean-code`
  - **Input:** `apps/web/package.json`, `apps/web/src/components/WalletView.tsx`, `apps/web/src/lib/supabase.ts`
  - **Output:** Delete dead `WalletView.tsx` (6,314 LOC), dead `SecurityView.tsx`, dead duplicate Supabase clients; uninstall unused `@clerk/react` v6, `@clerk/themes`, `@supabase/ssr`.
  - **Verify:** Bundle size decreases; `npm run build` succeeds cleanly.

- [ ] **Task 5.2: Fix Polling Storm & Dashboard Balance**
  - **Agent:** `frontend-specialist` | **Skill:** `nextjs-react-expert`
  - **Input:** `apps/web/src/App.tsx:612-626`, `apps/web/src/components/DashboardView.tsx:185`
  - **Output:** Fix `DashboardView` reading `b.available` (resolving `$0.00` bug); pause polling intervals when `document.hidden === true`; stop non-admin polling of `/admin/circuit-breakers`.
  - **Verify:** Network tab shows paused requests on background tabs; dashboard displays actual holdings.

---

## 6. Phase X: Final Verification Checklist

Before marking the project complete, the following commands MUST be executed:
- [ ] `npx tsc --noEmit` in `apps/web` (0 errors)
- [ ] `npm run build` in `apps/web` (Success)
- [ ] `.venv/bin/pytest tests/ -v` (All passing, including new regression tests)
- [ ] `python .agents/skills/vulnerability-scanner/scripts/security_scan.py . --output summary` (0 Critical/High issues)
- [ ] `python .agents/skills/frontend-design/scripts/ux_audit.py .`
- [ ] Manual smoke test on `http://localhost:3000`:
  - Verified NovexTrade branding on Navbar, Footer, and Landing page.
  - Verified `/resources` tab: filters, PDF download links, mobile responsiveness.
  - Verified Clerk login & Dashboard balances.
