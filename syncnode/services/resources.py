"""
NovexTrade Strategy Resources & Institutional PDF Service
Manages strategy whitepapers, playbooks, and secure authenticated PDF streaming.
"""
import os
from pathlib import Path
from typing import Dict, List, Optional, Any


RESOURCES_DIR = Path(__file__).resolve().parent.parent.parent / "resources" / "pdfs"


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


class ResourcesService:
    def __init__(self):
        ensure_strategy_pdfs_exist()

    def get_catalog(self) -> List[Dict[str, Any]]:
        # Return public metadata without heavy binary stream structures
        catalog = []
        for r in STRATEGY_CATALOG:
            item = {k: v for k, v in r.items() if k != "sections"}
            item["downloadUrl"] = f"/api/v1/resources/download/{r['id']}"
            catalog.append(item)
        return catalog

    def get_resource(self, resource_id: str) -> Optional[Dict[str, Any]]:
        for r in STRATEGY_CATALOG:
            if r["id"] == resource_id:
                return r
        return None

    def get_pdf_filepath(self, resource_id: str) -> Optional[Path]:
        res = self.get_resource(resource_id)
        if not res:
            return None
        filepath = RESOURCES_DIR / res["filename"]
        if not filepath.exists():
            _generate_valid_pdf(filepath, res)
        return filepath


resources_service = ResourcesService()
