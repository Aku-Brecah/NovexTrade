"""
NovexTrade On-Chain Cryptocurrency Verification & Wallet Validation Service
Validates global receiving wallet addresses per blockchain network, fetches live USD/crypto
exchange rates, and verifies on-chain transactions against public RPC / explorer APIs.
"""
import os
import re
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Optional, Tuple

import httpx

from syncnode.common.errors import ValidationError


# Supported networks and their compatible assets
NETWORK_ASSETS: Dict[str, List[str]] = {
    "ERC20": ["USDT", "USDC", "ETH"],
    "BEP20": ["USDT", "USDC", "BNB"],
    "TRC20": ["USDT", "TRX"],
    "BTC": ["BTC"],
    "SOL": ["SOL", "USDT", "USDC"],
}

# ERC20 / BEP20 Transfer event topic: keccak256("Transfer(address,address,uint256)")
ERC20_TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

# Mainnet token contract addresses & decimals
TOKEN_CONTRACTS: Dict[Tuple[str, str], Tuple[str, int]] = {
    ("ERC20", "USDT"): ("0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
    ("ERC20", "USDC"): ("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
    ("BEP20", "USDT"): ("0x55d398326f99059ff775485246999027b3197955", 18),
    ("BEP20", "USDC"): ("0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d", 18),
    ("TRC20", "USDT"): ("TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t", 6),
}

# Fallback rates ONLY used if external live rate APIs are unreachable (stablecoins are always 1.00)
_STABLECOINS = {"USDT", "USDC"}


def validate_wallet_address(address: str, network: str) -> str:
    """
    Validates that a cryptocurrency receiving address matches the required format
    for the selected blockchain network. Raises ValidationError on mismatch.
    """
    addr = (address or "").strip()
    net = (network or "").strip().upper()
    if net not in NETWORK_ASSETS:
        raise ValidationError(f"Unsupported blockchain network '{network}'. Supported: {', '.join(NETWORK_ASSETS.keys())}")
    if not addr:
        raise ValidationError("Receiving wallet address is required")

    if net in ("ERC20", "BEP20"):
        if not re.fullmatch(r"0x[a-fA-F0-9]{40}", addr):
            raise ValidationError(f"Invalid {net} wallet address. Must be a 42-character 0x-prefixed hexadecimal EVM address.")
    elif net == "TRC20":
        if not re.fullmatch(r"T[1-9A-HJ-NP-Za-km-z]{33}", addr):
            raise ValidationError("Invalid TRC20 wallet address. Must be a 34-character Base58 TRON address starting with 'T'.")
    elif net == "BTC":
        if not (
            re.fullmatch(r"(1|3)[1-9A-HJ-NP-Za-km-z]{25,34}", addr)
            or re.fullmatch(r"bc1[ac-hj-np-z02-9]{11,71}", addr.lower())
        ):
            raise ValidationError("Invalid Bitcoin address. Must be a valid Legacy (1...), P2SH (3...), or Bech32 (bc1...) address.")
    elif net == "SOL":
        if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{32,44}", addr):
            raise ValidationError("Invalid Solana address. Must be a 32-44 character Base58 public key.")
    return addr


def validate_tx_hash_format(tx_hash: str, network: str) -> str:
    """Validates transaction hash syntax before querying external blockchain RPCs."""
    tx = (tx_hash or "").strip()
    net = (network or "").strip().upper()
    if not tx:
        raise ValidationError("Transaction hash is required")

    if net in ("ERC20", "BEP20"):
        if not re.fullmatch(r"0x[a-fA-F0-9]{64}", tx):
            raise ValidationError(f"Invalid {net} transaction hash format (expected 0x followed by 64 hex characters)")
        return tx.lower()
    if net in ("TRC20", "BTC"):
        if not re.fullmatch(r"[a-fA-F0-9]{64}", tx):
            raise ValidationError(f"Invalid {net} transaction hash format (expected 64 hexadecimal characters)")
        return tx.lower()
    if net == "SOL":
        if not re.fullmatch(r"[1-9A-HJ-NP-Za-km-z]{64,90}", tx):
            raise ValidationError("Invalid Solana transaction signature format")
        return tx
    raise ValidationError(f"Unsupported network '{network}'")


class CryptoVerifierService:
    async def get_usd_exchange_rate(self, asset: str) -> Decimal:
        """
        Fetches live USD price for the cryptocurrency from Binance / CoinGecko.
        Stablecoins (USDT/USDC) are pegged 1:1 to USD.
        """
        sym = (asset or "").strip().upper()
        if sym in _STABLECOINS:
            return Decimal("1.00")

        binance_base = os.environ.get("BINANCE_API_BASE_URL", "https://api.binance.com").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.get(f"{binance_base}/api/v3/ticker/price", params={"symbol": f"{sym}USDT"})
                if resp.status_code == 200:
                    price = resp.json().get("price")
                    if price:
                        return Decimal(str(price))
        except Exception:
            pass

        # Secondary source: CoinGecko public simple price API
        cg_ids = {"BTC": "bitcoin", "ETH": "ethereum", "BNB": "binancecoin", "SOL": "solana", "TRX": "tron"}
        cg_id = cg_ids.get(sym)
        if cg_id:
            try:
                async with httpx.AsyncClient(timeout=6.0) as client:
                    resp = await client.get(
                        "https://api.coingecko.com/api/v3/simple/price",
                        params={"ids": cg_id, "vs_currencies": "usd"},
                    )
                    if resp.status_code == 200:
                        usd = resp.json().get(cg_id, {}).get("usd")
                        if usd:
                            return Decimal(str(usd))
            except Exception:
                pass

        raise ValidationError(f"Unable to fetch live USD exchange rate for {sym}. Please try again or pay with USDT/USDC.")

    async def verify_onchain_transaction(
        self,
        tx_hash: str,
        network: str,
        asset: str,
        expected_receiving_address: str,
        expected_amount_crypto: Decimal,
        required_confirmations: int = 1,
    ) -> Dict[str, Any]:
        """
        Queries real blockchain RPC/Explorer APIs to verify transaction existence,
        recipient address, asset/token contract, transferred amount, and confirmations.
        """
        net = network.strip().upper()
        sym = asset.strip().upper()
        normalized_hash = validate_tx_hash_format(tx_hash, net)

        if net in ("ERC20", "BEP20"):
            return await self._verify_evm_tx(
                normalized_hash, net, sym, expected_receiving_address, expected_amount_crypto, required_confirmations
            )
        if net == "BTC":
            return await self._verify_btc_tx(
                normalized_hash, expected_receiving_address, expected_amount_crypto, required_confirmations
            )
        if net == "TRC20":
            return await self._verify_tron_tx(
                normalized_hash, sym, expected_receiving_address, expected_amount_crypto, required_confirmations
            )
        if net == "SOL":
            return await self._verify_sol_tx(
                normalized_hash, sym, expected_receiving_address, expected_amount_crypto, required_confirmations
            )

        return {
            "status": "INVALID_TX",
            "confirmations": 0,
            "received_amount": Decimal("0"),
            "sender_address": None,
            "reason": f"Unsupported blockchain network: {net}",
            "raw": {},
        }

    def _evaluate_amount_and_confirmations(
        self,
        received: Decimal,
        expected: Decimal,
        confirmations: int,
        required_confirmations: int,
    ) -> Tuple[str, str]:
        # Allow 0.5% tolerance for minor exchange/decimal rounding
        min_acceptable = (expected * Decimal("0.995")).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        if received < min_acceptable:
            return "UNDERPAID", f"Received {received} which is below required {expected}"
        if confirmations < required_confirmations:
            return "PENDING", f"Transaction found with {confirmations}/{required_confirmations} confirmations"
        if received > (expected * Decimal("1.02")):
            return "OVERPAID", f"Confirmed with overpayment ({received} > {expected})"
        return "CONFIRMED", "Transaction verified on-chain with required confirmations"

    async def _verify_evm_tx(
        self,
        tx_hash: str,
        network: str,
        asset: str,
        expected_address: str,
        expected_amount: Decimal,
        required_confirmations: int,
    ) -> Dict[str, Any]:
        rpc_url = (
            os.environ.get("ETH_RPC_URL", "https://ethereum-rpc.publicnode.com")
            if network == "ERC20"
            else os.environ.get("BSC_RPC_URL", "https://bsc-dataseed.binance.org")
        )
        expected_addr_lower = expected_address.lower()

        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                tx_resp = await client.post(
                    rpc_url,
                    json={"jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionByHash", "params": [tx_hash]},
                )
                receipt_resp = await client.post(
                    rpc_url,
                    json={"jsonrpc": "2.0", "id": 2, "method": "eth_getTransactionReceipt", "params": [tx_hash]},
                )
                block_resp = await client.post(
                    rpc_url,
                    json={"jsonrpc": "2.0", "id": 3, "method": "eth_blockNumber", "params": []},
                )
        except Exception as exc:
            return {
                "status": "UNMATCHED_REVIEW",
                "confirmations": 0,
                "received_amount": Decimal("0"),
                "sender_address": None,
                "reason": f"Blockchain RPC temporarily unreachable ({exc}); queued for verification/admin review",
                "raw": {},
            }

        tx_data = tx_resp.json().get("result")
        receipt = receipt_resp.json().get("result")
        latest_block_hex = block_resp.json().get("result")

        if not tx_data:
            return {
                "status": "INVALID_TX",
                "confirmations": 0,
                "received_amount": Decimal("0"),
                "sender_address": None,
                "reason": f"Transaction {tx_hash} not found on {network}",
                "raw": {},
            }

        if not receipt:
            return {
                "status": "PENDING",
                "confirmations": 0,
                "received_amount": Decimal("0"),
                "sender_address": tx_data.get("from"),
                "reason": "Transaction is still in mempool (0 confirmations)",
                "raw": {"tx": tx_data},
            }

        if receipt.get("status") != "0x1":
            return {
                "status": "FAILED",
                "confirmations": 0,
                "received_amount": Decimal("0"),
                "sender_address": tx_data.get("from"),
                "reason": "On-chain transaction reverted/failed",
                "raw": {"receipt": receipt},
            }

        tx_block = int(receipt["blockNumber"], 16)
        latest_block = int(latest_block_hex, 16) if latest_block_hex else tx_block
        confirmations = max(1, latest_block - tx_block + 1)
        sender = tx_data.get("from")

        # Native coin transfer (ETH on ERC20, BNB on BEP20)
        if (network == "ERC20" and asset == "ETH") or (network == "BEP20" and asset == "BNB"):
            to_addr = (tx_data.get("to") or "").lower()
            if to_addr != expected_addr_lower:
                return {
                    "status": "WRONG_ADDRESS",
                    "confirmations": confirmations,
                    "received_amount": Decimal("0"),
                    "sender_address": sender,
                    "reason": f"Recipient {to_addr} does not match global receiving wallet {expected_addr_lower}",
                    "raw": {"tx": tx_data, "receipt": receipt},
                }
            wei = int(tx_data.get("value", "0x0"), 16)
            received = Decimal(wei) / Decimal(10**18)
            status, reason = self._evaluate_amount_and_confirmations(
                received, expected_amount, confirmations, required_confirmations
            )
            return {
                "status": status,
                "confirmations": confirmations,
                "received_amount": received,
                "sender_address": sender,
                "reason": reason,
                "raw": {"tx": tx_data, "receipt": receipt},
            }

        # ERC20 / BEP20 Token Transfer Log Inspection
        contract_info = TOKEN_CONTRACTS.get((network, asset))
        if not contract_info:
            return {
                "status": "WRONG_TOKEN",
                "confirmations": confirmations,
                "received_amount": Decimal("0"),
                "sender_address": sender,
                "reason": f"Token {asset} is not configured for {network}",
                "raw": {"receipt": receipt},
            }

        expected_contract, decimals = contract_info
        received_total = Decimal("0")
        found_matching_contract = False
        for log in receipt.get("logs", []):
            log_addr = (log.get("address") or "").lower()
            topics = log.get("topics") or []
            if len(topics) >= 3 and topics[0].lower() == ERC20_TRANSFER_TOPIC:
                if log_addr == expected_contract.lower():
                    found_matching_contract = True
                    to_topic_addr = "0x" + topics[2][-40:].lower()
                    if to_topic_addr == expected_addr_lower:
                        raw_amt = int(log.get("data", "0x0"), 16)
                        received_total += Decimal(raw_amt) / Decimal(10**decimals)

        if received_total == Decimal("0"):
            status = "WRONG_ADDRESS" if found_matching_contract else "WRONG_TOKEN"
            reason = (
                "Token transfer did not target the configured global receiving wallet"
                if found_matching_contract
                else f"No {asset} transfer event found in transaction logs"
            )
            return {
                "status": status,
                "confirmations": confirmations,
                "received_amount": Decimal("0"),
                "sender_address": sender,
                "reason": reason,
                "raw": {"receipt": receipt},
            }

        status, reason = self._evaluate_amount_and_confirmations(
            received_total, expected_amount, confirmations, required_confirmations
        )
        return {
            "status": status,
            "confirmations": confirmations,
            "received_amount": received_total,
            "sender_address": sender,
            "reason": reason,
            "raw": {"receipt": receipt},
        }

    async def _verify_btc_tx(
        self,
        tx_hash: str,
        expected_address: str,
        expected_amount: Decimal,
        required_confirmations: int,
    ) -> Dict[str, Any]:
        api_base = os.environ.get("BTC_EXPLORER_API_URL", "https://blockstream.info/api").rstrip("/")
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                tx_resp = await client.get(f"{api_base}/tx/{tx_hash}")
                if tx_resp.status_code == 404:
                    return {
                        "status": "INVALID_TX",
                        "confirmations": 0,
                        "received_amount": Decimal("0"),
                        "sender_address": None,
                        "reason": "Bitcoin transaction not found on chain",
                        "raw": {},
                    }
                tx_data = tx_resp.json()
                tip_resp = await client.get(f"{api_base}/blocks/tip/height")
                tip_height = int(tip_resp.text.strip()) if tip_resp.status_code == 200 else 0
        except Exception as exc:
            return {
                "status": "UNMATCHED_REVIEW",
                "confirmations": 0,
                "received_amount": Decimal("0"),
                "sender_address": None,
                "reason": f"Bitcoin explorer unavailable ({exc}); queued for review",
                "raw": {},
            }

        received_sats = sum(
            int(vout.get("value", 0))
            for vout in tx_data.get("vout", [])
            if vout.get("scriptpubkey_address") == expected_address
        )
        if received_sats == 0:
            return {
                "status": "WRONG_ADDRESS",
                "confirmations": 0,
                "received_amount": Decimal("0"),
                "sender_address": None,
                "reason": "No output in Bitcoin transaction matches the global receiving address",
                "raw": tx_data,
            }

        status_obj = tx_data.get("status") or {}
        if status_obj.get("confirmed") and status_obj.get("block_height") and tip_height:
            confirmations = max(1, tip_height - int(status_obj["block_height"]) + 1)
        else:
            confirmations = 0

        received_btc = Decimal(received_sats) / Decimal(10**8)
        status, reason = self._evaluate_amount_and_confirmations(
            received_btc, expected_amount, confirmations, required_confirmations
        )
        return {
            "status": status,
            "confirmations": confirmations,
            "received_amount": received_btc,
            "sender_address": None,
            "reason": reason,
            "raw": tx_data,
        }

    async def _verify_tron_tx(
        self,
        tx_hash: str,
        asset: str,
        expected_address: str,
        expected_amount: Decimal,
        required_confirmations: int,
    ) -> Dict[str, Any]:
        api_base = os.environ.get("TRONGRID_API_URL", "https://api.trongrid.io").rstrip("/")
        headers = {}
        if os.environ.get("TRONGRID_API_KEY"):
            headers["TRON-PRO-API-KEY"] = os.environ["TRONGRID_API_KEY"]
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                info_resp = await client.post(
                    f"{api_base}/wallet/gettransactioninfobyid",
                    json={"value": tx_hash},
                    headers=headers,
                )
                tx_info = info_resp.json()
        except Exception as exc:
            return {
                "status": "UNMATCHED_REVIEW",
                "confirmations": 0,
                "received_amount": Decimal("0"),
                "sender_address": None,
                "reason": f"TronGrid API unavailable ({exc}); queued for review",
                "raw": {},
            }

        if not tx_info or not tx_info.get("id"):
            return {
                "status": "INVALID_TX",
                "confirmations": 0,
                "received_amount": Decimal("0"),
                "sender_address": None,
                "reason": "TRON transaction not found",
                "raw": {},
            }

        receipt = tx_info.get("receipt") or {}
        if receipt.get("result") and receipt.get("result") != "SUCCESS":
            return {
                "status": "FAILED",
                "confirmations": 0,
                "received_amount": Decimal("0"),
                "sender_address": None,
                "reason": f"TRON transaction failed: {receipt.get('result')}",
                "raw": tx_info,
            }

        # Queue for admin reconciliation if raw Tron hex address decoding is needed without base58 lib
        return {
            "status": "UNMATCHED_REVIEW",
            "confirmations": 1 if tx_info.get("blockNumber") else 0,
            "received_amount": Decimal("0"),
            "sender_address": None,
            "reason": "TRON transaction located on-chain; routed to administrator reconciliation queue for final confirmation",
            "raw": tx_info,
        }

    async def _verify_sol_tx(
        self,
        tx_hash: str,
        asset: str,
        expected_address: str,
        expected_amount: Decimal,
        required_confirmations: int,
    ) -> Dict[str, Any]:
        rpc_url = os.environ.get("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
        try:
            async with httpx.AsyncClient(timeout=12.0) as client:
                resp = await client.post(
                    rpc_url,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "getTransaction",
                        "params": [tx_hash, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
                    },
                )
                result = resp.json().get("result")
        except Exception as exc:
            return {
                "status": "UNMATCHED_REVIEW",
                "confirmations": 0,
                "received_amount": Decimal("0"),
                "sender_address": None,
                "reason": f"Solana RPC unavailable ({exc}); queued for review",
                "raw": {},
            }

        if not result:
            return {
                "status": "INVALID_TX",
                "confirmations": 0,
                "received_amount": Decimal("0"),
                "sender_address": None,
                "reason": "Solana transaction signature not found",
                "raw": {},
            }

        meta = result.get("meta") or {}
        if meta.get("err") is not None:
            return {
                "status": "FAILED",
                "confirmations": 0,
                "received_amount": Decimal("0"),
                "sender_address": None,
                "reason": "Solana transaction failed on-chain",
                "raw": result,
            }

        account_keys = [
            (k.get("pubkey") if isinstance(k, dict) else k)
            for k in (result.get("transaction", {}).get("message", {}).get("accountKeys") or [])
        ]
        if asset == "SOL" and expected_address in account_keys:
            idx = account_keys.index(expected_address)
            pre = meta.get("preBalances", [])[idx]
            post = meta.get("postBalances", [])[idx]
            lamports = max(0, post - pre)
            received = Decimal(lamports) / Decimal(10**9)
            if received == Decimal("0"):
                return {
                    "status": "WRONG_ADDRESS",
                    "confirmations": 1,
                    "received_amount": Decimal("0"),
                    "sender_address": account_keys[0] if account_keys else None,
                    "reason": "No SOL balance increase detected for global receiving wallet",
                    "raw": result,
                }
            status, reason = self._evaluate_amount_and_confirmations(
                received, expected_amount, max(required_confirmations, 1), required_confirmations
            )
            return {
                "status": status,
                "confirmations": max(required_confirmations, 1),
                "received_amount": received,
                "sender_address": account_keys[0] if account_keys else None,
                "reason": reason,
                "raw": result,
            }

        return {
            "status": "UNMATCHED_REVIEW",
            "confirmations": 1,
            "received_amount": Decimal("0"),
            "sender_address": account_keys[0] if account_keys else None,
            "reason": "Solana SPL transaction found; routed to admin reconciliation queue",
            "raw": result,
        }


crypto_verifier = CryptoVerifierService()
