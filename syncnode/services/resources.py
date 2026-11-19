"""
NovexTrade Strategy Resources & Institutional PDF Service
Manages strategy whitepapers, playbooks, and secure authenticated PDF streaming.
"""
import base64
import json
import os
import re
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Any

from syncnode.common.errors import ValidationError, NotFoundError


RESOURCES_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "pdfs"
CATALOG_MANIFEST_PATH = RESOURCES_DIR / "catalog.json"
MAX_PDF_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB limit


STRATEGY_CATALOG: List[Dict[str, Any]] = [
    {
        "id": "strat-momentum-playbook",
        "title": "Institutional Momentum & Order Flow Playbook",
        "category": "Momentum & Order Flow",
        "difficulty": "Institutional",
        "summary": "Quantitative framework for exploiting microsecond order book depth imbalances, price-time priority queues, and cross-venue momentum triggers.",
        "targetSharpe": "2.95",
        "recommendedHorizon": "Intraday / Scalping (1m - 15m)",
        "assetSuitability": "BTC, ETH, SOL (High-Depth Pairs)",
        "filename": "novextrade-institutional-momentum-playbook.pdf",
        "fileSize": "1.4 MB",
        "pages": 28,
        "author": "NovexTrade Quantitative Research Group",
        "publishedDate": "November 2026",
        "tags": ["Order Book", "Market Depth", "FIFO", "High Frequency"],
        "sections": [
            ("1. Microstructure Foundations", [
                "Analysis of limit order book (LOB) queuing dynamics under deterministic FIFO.",
                "Order flow toxicity metrics (VPIN) and adverse selection containment.",
                "Liquidity consumption patterns during institutional block executions."
            ]),
            ("2. Momentum Alpha Generation", [
                "Price-time priority execution guarantees eliminating queue front-running.",
                "Depth imbalance ratios across top 20 bid/ask ticks as predictive signals.",
                "VWAP slippage minimization algorithms for multi-asset rebalancing."
            ]),
            ("3. Risk Governance & Drawdown Control", [
                "Hard stop-loss thresholds calibrated to intraday Average True Range (ATR).",
                "Maximum daily portfolio drawdown ceiling of 2.5% of total collateral.",
                "Automated circuit-breaker tripping upon exchange-wide volatility spikes."
            ])
        ]
    },
    {
        "id": "strat-dca-grid-hedging",
        "title": "Algorithmic DCA & Delta-Neutral Grid Hedging Guide",
        "category": "Algorithmic & Grid",
        "difficulty": "Intermediate",
        "summary": "Mathematical architecture for automated grid volatility harvesting, geometric spacing optimization, and delta-neutral downside protection.",
        "targetSharpe": "2.10",
        "recommendedHorizon": "Swing Trading (4h - Daily)",
        "assetSuitability": "BTC, ETH, High-Cap Altcoins",
        "filename": "novextrade-algorithmic-dca-grid-hedging.pdf",
        "fileSize": "1.1 MB",
        "pages": 22,
        "author": "NovexTrade Algorithmic Strategies Desk",
        "publishedDate": "October 2026",
        "tags": ["DCA", "Grid Trading", "Delta Neutral", "Risk Parity"],
        "sections": [
            ("1. Arithmetic vs. Geometric Grids", [
                "Spacing calibration relative to historical volatility and funding rates.",
                "Capital allocation formulas to eliminate liquidation risks during flash crashes.",
                "Fee-adjusted profitability thresholds for high-density limit orders."
            ]),
            ("2. Delta-Neutral Derivative Overlay", [
                "Short perpetual contract offsets to neutralize directional beta exposure.",
                "Funding rate harvesting mechanics across contrasting market regimes.",
                "Dynamic inventory rebalancing models to prevent unilateral capital locking."
            ]),
            ("3. Execution Automation", [
                "Idempotent API order dispatch with sub-10ms round-trip latency.",
                "Self-trade prevention (STP) configuration avoiding maker-taker collisions.",
                "Multi-tiered post-only order placement ensuring 100% maker fee rebates."
            ])
        ]
    },
    {
        "id": "strat-derivatives-tail-risk",
        "title": "Crypto Derivatives & Tail-Risk Management Framework",
        "category": "Derivatives & Options",
        "difficulty": "Advanced",
        "summary": "Institutional risk manual covering volatility skew arbitrage, perpetual funding carry trades, and black-swan options collar hedges.",
        "targetSharpe": "2.40",
        "recommendedHorizon": "Weekly / Structural",
        "assetSuitability": "BTC/USDT, ETH/USDT Perpetuals & Spot",
        "filename": "novextrade-crypto-derivatives-tail-risk.pdf",
        "fileSize": "2.2 MB",
        "pages": 36,
        "author": "NovexTrade Risk & Asset Protection Committee",
        "publishedDate": "November 2026",
        "tags": ["Perpetuals", "Funding Arbitrage", "Options", "VaR"],
        "sections": [
            ("1. Tail-Risk Distribution Modeling", [
                "Fat-tailed crypto asset returns and extreme value theory (EVT).",
                "Conditional Value at Risk (CVaR) computation under leverage stress tests.",
                "Contagion mitigation during systemic decentralized liquidity contractions."
            ]),
            ("2. Basis & Funding Arbitrage", [
                "Perpetual funding rate capture vs spot inventory delta hedging.",
                "Annualized yield optimization using cross-margin collateral efficiency.",
                "Negative funding cycle survival protocols and interest-bearing reserves."
            ]),
            ("3. Institutional Liquidation Insulation", [
                "Isolated margin segregation preventing cascading collateral liquidation.",
                "Dynamic maintenance margin requirements based on position size scaling.",
                "Emergency deleveraging (ADL) mechanics and insurance fund backing."
            ])
        ]
    },
    {
        "id": "strat-p2p-cross-venue-arb",
        "title": "P2P Market Making & Cross-Venue Arbitrage Manual",
        "category": "P2P & Arbitrage",
        "difficulty": "Intermediate",
        "summary": "Operational manual for zero-fee internal transfers, fiat-to-crypto merchant spread capture, and cryptographic escrow dispute mitigation.",
        "targetSharpe": "3.20",
        "recommendedHorizon": "Real-time Settlement",
        "assetSuitability": "USDT, USDC, Local Fiat Rails (100+ Currencies)",
        "filename": "novextrade-p2p-cross-venue-arbitrage.pdf",
        "fileSize": "1.3 MB",
        "pages": 24,
        "author": "NovexTrade Global P2P & Liquidity Desk",
        "publishedDate": "September 2026",
        "tags": ["P2P", "Arbitrage", "Zero Fee", "Escrow"],
        "sections": [
            ("1. Institutional P2P Market Making", [
                "Spread capture strategies between institutional OTC desks and retail rails.",
                "Two-way quote automation with dynamic pricing linked to spot index feeds.",
                "Velocity maximization through verified payment method whitelisting."
            ]),
            ("2. Escrow & Counterparty Security", [
                "Atomic ledger escrow locking guaranteeing zero counterparty default.",
                "Cryptographic proof of fiat transfer verification before asset release.",
                "Compliance dispute handling protocols with 24/7 evidentiary adjudication."
            ]),
            ("3. Zero-Fee Internal Network Arbitrage", [
                "Sub-millisecond internal transfers between NovexTrade institutional nodes.",
                "Triangular arbitrage cycles without on-chain gas or confirmation delays.",
                "Treasury rebalancing across segregated institutional merchant accounts."
            ])
        ]
    },
    {
        "id": "strat-solvency-proof-reserves",
        "title": "Proof of Reserves & Double-Entry Ledger Verification Spec",
        "category": "Institutional Audit",
        "difficulty": "Institutional",
        "summary": "Technical architecture specification detailing Merkle sum tree solvency proofs, non-custodial cold vault segregation, and zero-trust liability auditing.",
        "targetSharpe": "Risk-Free Audit",
        "recommendedHorizon": "Continuous / Automated",
        "assetSuitability": "All NovexTrade Listed Assets & Reserves",
        "filename": "novextrade-proof-of-reserves-spec.pdf",
        "fileSize": "1.6 MB",
        "pages": 30,
        "author": "NovexTrade Cryptographic Auditing Division",
        "publishedDate": "November 2026",
        "tags": ["Solvency", "Proof of Reserves", "Merkle Tree", "Audit"],
        "sections": [
            ("1. Mathematical Solvency Invariants", [
                "Fundamental invariant: Exchange Vault Assets >= Customer Liabilities.",
                "Merkle sum tree construction enabling independent user leaf verification.",
                "Double-entry bookkeeping enforcing debits == credits on every transaction."
            ]),
            ("2. Cold-Storage Custody Architecture", [
                "Segregated multi-signature cold vaults with distributed institutional signers.",
                "On-chain cryptographic public address attestation and balance snapshots.",
                "Zero fractional reserve banking policy mathematically enforced at ledger core."
            ]),
            ("3. Real-Time Public Verification API", [
                "Public cryptographic endpoint for verifying ledger root hashes.",
                "Automated nightly solvency auditing by independent certified auditors.",
                "Emergency proof generation during industry-wide stress and bank-run events."
            ])
        ]
    }
]


def _escape_pdf(text: str) -> str:
    """Escapes parenthesis and backslashes for PDF string literals."""
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _generate_valid_pdf(filepath: Path, resource: Dict[str, Any]):
    """Generates a clean, valid PDF 1.4 document containing the full strategy playbook."""
    title = _escape_pdf(resource["title"])
    subtitle = _escape_pdf(f"{resource['category']} | Level: {resource['difficulty']} | Horizon: {resource['recommendedHorizon']}")
    author = _escape_pdf(f"Publisher: {resource['author']} • Date: {resource['publishedDate']}")

    stream = f"""BT
/F1 18 Tf
50 740 Td
({title}) Tj
ET
BT
/F2 10 Tf
50 715 Td
({subtitle}) Tj
ET
BT
/F2 9 Tf
50 700 Td
({author}) Tj
ET
BT
/F1 11 Tf
50 670 Td
(Executive Summary) Tj
ET
BT
/F2 9 Tf
50 655 Td
({_escape_pdf(resource['summary'])}) Tj
ET
"""
    y = 620
    for section_title, bullets in resource.get("sections", []):
        stream += f"""BT
/F1 12 Tf
50 {y} Td
({_escape_pdf(section_title)}) Tj
ET
"""
        y -= 20
        for bullet in bullets:
            stream += f"""BT
/F2 9 Tf
60 {y} Td
(- {_escape_pdf(bullet)}) Tj
ET
"""
            y -= 16
        y -= 14

    stream += f"""BT
/F2 8 Tf
50 40 Td
(NovexTrade Institutional Exchange  All Rights Reserved  Strictly Confidential  Property of NovexTrade Quantitative Research) Tj
ET
"""

    stream_bytes = stream.encode("latin1", errors="replace")
    stream_len = len(stream_bytes)

    obj1 = b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
    obj2 = b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
    obj3 = (
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>\nendobj\n"
    )
    obj4 = (
        f"4 0 obj\n<< /Length {stream_len} >>\nstream\n".encode("latin1")
        + stream_bytes
        + b"\nendstream\nendobj\n"
    )
    obj5 = b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>\nendobj\n"
    obj6 = b"6 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"

    header = b"%PDF-1.4\n"
    body = obj1 + obj2 + obj3 + obj4 + obj5 + obj6

    o1 = len(header)
    o2 = o1 + len(obj1)
    o3 = o2 + len(obj2)
    o4 = o3 + len(obj3)
    o5 = o4 + len(obj4)
    o6 = o5 + len(obj5)

    xref_offset = len(header) + len(body)
    xref = f"""xref
0 7
0000000000 65535 f 
{o1:010d} 00000 n 
{o2:010d} 00000 n 
{o3:010d} 00000 n 
{o4:010d} 00000 n 
{o5:010d} 00000 n 
{o6:010d} 00000 n 
trailer
<< /Size 7 /Root 1 0 R >>
startxref
{xref_offset}
%%EOF
""".encode("latin1")

    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "wb") as f:
        f.write(header + body + xref)


def ensure_strategy_pdfs_exist():
    """Generates any missing PDF whitepapers on disk."""
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
    for res in STRATEGY_CATALOG:
        filepath = RESOURCES_DIR / res["filename"]
        if not filepath.exists() or filepath.stat().st_size < 100:
            _generate_valid_pdf(filepath, res)


def _format_file_size(num_bytes: int) -> str:
    if num_bytes >= 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{max(1, round(num_bytes / 1024))} KB"


def _sanitize_pdf_filename(raw_name: str, fallback_slug: str) -> str:
    base = Path(raw_name or fallback_slug).name
    stem = re.sub(r"[^a-zA-Z0-9._-]+", "-", base).strip("-.").lower()
    if not stem:
        stem = fallback_slug
    if not stem.endswith(".pdf"):
        stem = f"{stem}.pdf"
    return stem[:120]


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")
    return slug[:48] or f"strategy-{uuid.uuid4().hex[:6]}"


class ResourcesService:
    def __init__(self):
        self._catalog: List[Dict[str, Any]] = []
        self._load_or_seed_catalog()

    def _load_or_seed_catalog(self):
        ensure_strategy_pdfs_exist()
        if CATALOG_MANIFEST_PATH.exists():
            try:
                loaded = json.loads(CATALOG_MANIFEST_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, list) and loaded:
                    self._catalog = loaded
                    return
            except Exception:
                pass
        # Seed from built-in institutional playbooks
        self._catalog = [dict(r) for r in STRATEGY_CATALOG]
        self._persist_catalog()

    def _persist_catalog(self):
        RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
        serializable = [{k: v for k, v in item.items() if k != "sections"} for item in self._catalog]
        tmp_path = CATALOG_MANIFEST_PATH.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(serializable, indent=2), encoding="utf-8")
        tmp_path.replace(CATALOG_MANIFEST_PATH)

    def _decode_and_validate_pdf(self, pdf_base64: str) -> bytes:
        raw = (pdf_base64 or "").strip()
        if not raw:
            raise ValidationError("PDF file content is required")
        if "," in raw and raw.lower().startswith("data:"):
            header_part, raw = raw.split(",", 1)
            if "pdf" not in header_part.lower() and "octet-stream" not in header_part.lower():
                raise ValidationError("Uploaded file must be a valid PDF document (application/pdf)")
        try:
            pdf_bytes = base64.b64decode(raw, validate=True)
        except Exception:
            raise ValidationError("Invalid base64 encoding for PDF file")

        if len(pdf_bytes) < 64:
            raise ValidationError("Uploaded PDF file is empty or corrupted")
        if len(pdf_bytes) > MAX_PDF_UPLOAD_BYTES:
            raise ValidationError("PDF file exceeds the maximum allowed size of 25 MB")
        if not pdf_bytes.startswith(b"%PDF-"):
            raise ValidationError("Invalid file signature: uploaded file must be a genuine PDF (%PDF- header)")
        return pdf_bytes

    def _write_pdf_bytes(self, filename: str, pdf_bytes: bytes) -> Path:
        RESOURCES_DIR.mkdir(parents=True, exist_ok=True)
        target = (RESOURCES_DIR / filename).resolve()
        if RESOURCES_DIR.resolve() not in target.parents:
            raise ValidationError("Invalid PDF filename path")
        tmp = target.with_suffix(".pdf.tmp")
        tmp.write_bytes(pdf_bytes)
        tmp.replace(target)
        return target

    def get_catalog(self) -> List[Dict[str, Any]]:
        catalog = []
        for r in self._catalog:
            item = {k: v for k, v in r.items() if k != "sections"}
            item["downloadUrl"] = f"/api/v1/resources/download/{r['id']}"
            fp = RESOURCES_DIR / r["filename"]
            item["fileExists"] = fp.exists()
            catalog.append(item)
        return catalog

    def get_resource(self, resource_id: str) -> Optional[Dict[str, Any]]:
        for r in self._catalog:
            if r["id"] == resource_id:
                return r
        return None

    def get_pdf_filepath(self, resource_id: str) -> Optional[Path]:
        res = self.get_resource(resource_id)
        if not res:
            return None
        filepath = (RESOURCES_DIR / res["filename"]).resolve()
        if RESOURCES_DIR.resolve() not in filepath.parents:
            return None
        if not filepath.exists():
            # Regenerate only if it is one of the built-in seeded strategies
            builtin = next((b for b in STRATEGY_CATALOG if b["id"] == resource_id), None)
            if builtin:
                _generate_valid_pdf(filepath, builtin)
        return filepath

    def admin_create_strategy(self, payload: Dict[str, Any], admin_id: str) -> Dict[str, Any]:
        title = str(payload.get("title") or "").strip()
        if len(title) < 3:
            raise ValidationError("Strategy title must be at least 3 characters")

        pdf_bytes = self._decode_and_validate_pdf(str(payload.get("pdfBase64") or ""))
        resource_id = f"strat-{_slugify(title)}-{uuid.uuid4().hex[:6]}"
        filename = _sanitize_pdf_filename(str(payload.get("pdfFilename") or f"{resource_id}.pdf"), resource_id)

        # Ensure unique filename on disk
        if (RESOURCES_DIR / filename).exists():
            filename = f"{Path(filename).stem}-{uuid.uuid4().hex[:6]}.pdf"

        self._write_pdf_bytes(filename, pdf_bytes)

        raw_tags = payload.get("tags") or []
        if isinstance(raw_tags, str):
            tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
        else:
            tags = [str(t).strip() for t in raw_tags if str(t).strip()]

        now_month = time.strftime("%B %Y")
        strategy = {
            "id": resource_id,
            "title": title,
            "category": str(payload.get("category") or "Institutional Strategy").strip(),
            "difficulty": str(payload.get("difficulty") or "Intermediate").strip(),
            "summary": str(payload.get("summary") or "").strip() or "Institutional trading strategy playbook.",
            "targetSharpe": str(payload.get("targetSharpe") or "2.00").strip(),
            "recommendedHorizon": str(payload.get("recommendedHorizon") or "Intraday / Swing").strip(),
            "assetSuitability": str(payload.get("assetSuitability") or "BTC, ETH, USDT Pairs").strip(),
            "filename": filename,
            "fileSize": _format_file_size(len(pdf_bytes)),
            "pages": max(1, int(payload.get("pages") or 1)),
            "author": str(payload.get("author") or "NovexTrade Quantitative Research").strip(),
            "publishedDate": str(payload.get("publishedDate") or now_month).strip(),
            "tags": tags or ["Strategy", "PDF"],
            "uploadedBy": admin_id,
            "updatedAt": int(time.time() * 1000),
        }
        self._catalog.insert(0, strategy)
        self._persist_catalog()
        return {**strategy, "downloadUrl": f"/api/v1/resources/download/{resource_id}", "fileExists": True}

    def admin_update_strategy(self, resource_id: str, payload: Dict[str, Any], admin_id: str) -> Dict[str, Any]:
        strategy = self.get_resource(resource_id)
        if not strategy:
            raise NotFoundError(f"Strategy '{resource_id}' not found")

        for field in (
            "title",
            "category",
            "difficulty",
            "summary",
            "targetSharpe",
            "recommendedHorizon",
            "assetSuitability",
            "author",
            "publishedDate",
        ):
            if field in payload and payload[field] is not None:
                val = str(payload[field]).strip()
                if field == "title" and len(val) < 3:
                    raise ValidationError("Strategy title must be at least 3 characters")
                strategy[field] = val

        if "pages" in payload and payload["pages"] is not None:
            strategy["pages"] = max(1, int(payload["pages"]))

        if "tags" in payload and payload["tags"] is not None:
            raw_tags = payload["tags"]
            if isinstance(raw_tags, str):
                strategy["tags"] = [t.strip() for t in raw_tags.split(",") if t.strip()]
            else:
                strategy["tags"] = [str(t).strip() for t in raw_tags if str(t).strip()]

        # Optional PDF replacement
        if payload.get("pdfBase64"):
            pdf_bytes = self._decode_and_validate_pdf(str(payload["pdfBase64"]))
            new_filename = _sanitize_pdf_filename(
                str(payload.get("pdfFilename") or strategy["filename"]), resource_id
            )
            self._write_pdf_bytes(new_filename, pdf_bytes)
            strategy["filename"] = new_filename
            strategy["fileSize"] = _format_file_size(len(pdf_bytes))

        strategy["uploadedBy"] = admin_id
        strategy["updatedAt"] = int(time.time() * 1000)
        self._persist_catalog()
        return {**strategy, "downloadUrl": f"/api/v1/resources/download/{resource_id}", "fileExists": True}

    def admin_delete_strategy(self, resource_id: str) -> Dict[str, Any]:
        strategy = self.get_resource(resource_id)
        if not strategy:
            raise NotFoundError(f"Strategy '{resource_id}' not found")

        self._catalog = [r for r in self._catalog if r["id"] != resource_id]
        self._persist_catalog()

        # Remove uploaded file if not a built-in default
        builtin_ids = {b["id"] for b in STRATEGY_CATALOG}
        if resource_id not in builtin_ids:
            fp = (RESOURCES_DIR / strategy["filename"]).resolve()
            if RESOURCES_DIR.resolve() in fp.parents and fp.exists():
                try:
                    fp.unlink()
                except Exception:
                    pass
        return {"deletedId": resource_id, "title": strategy["title"]}


resources_service = ResourcesService()
