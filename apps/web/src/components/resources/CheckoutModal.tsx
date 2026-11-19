import React, { useEffect, useState } from 'react';
import {
  X,
  CreditCard,
  Coins,
  Copy,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ExternalLink,
  ShieldCheck,
  Clock,
  Download,
  RefreshCw,
} from 'lucide-react';
import { getStoredReferral } from '../../utils/referralAttribution';

export interface CheckoutTarget {
  productId: 'individual_pdf' | 'combo_bundle';
  productName: string;
  priceUsd: string;
  resourceId?: string;
  resourceTitle?: string;
}

interface CryptoWalletInfo {
  isEnabled: boolean;
  receivingAddress: string;
  primaryAsset: string;
  primaryNetwork: string;
  supportedTokens: string[];
  requiredConfirmations: number;
  memoTag?: string | null;
}

interface OrderData {
  id: string;
  orderReference: string;
  productId: string;
  productName: string;
  resourceId?: string | null;
  amountUsd: string;
  currency: string;
  paymentMethod: 'CARD' | 'CRYPTO';
  paymentProvider: string;
  status: string;
  checkoutUrl?: string | null;
  cryptoInstructions?: {
    receivingAddress: string;
    network: string;
    asset: string;
    expectedAmountCrypto: string;
    exchangeRateUsd: string;
    requiredConfirmations: number;
    memoTag?: string | null;
    orderReference: string;
    expiresAt: number;
  } | null;
  cryptoVerification?: {
    txHash: string;
    status: string;
    confirmations: number;
    requiredConfirmations: number;
    receivedAmountCrypto: string;
    expectedAmountCrypto: string;
    reason: string;
  };
  expiresAt: number;
}

interface CheckoutModalProps {
  target: CheckoutTarget;
  token: string;
  onClose: () => void;
  onPaymentSuccess: () => void;
  onDownloadUnlocked: (resourceId?: string, isCombo?: boolean) => void;
}

export const CheckoutModal: React.FC<CheckoutModalProps> = ({
  target,
  token,
  onClose,
  onPaymentSuccess,
  onDownloadUnlocked,
}) => {
  const [paymentMethod, setPaymentMethod] = useState<'CRYPTO' | 'CARD'>('CRYPTO');
  const [walletInfo, setWalletInfo] = useState<CryptoWalletInfo | null>(null);
  const [selectedCryptoAsset, setSelectedCryptoAsset] = useState<string>('USDT');
  const [cardProviderInfo, setCardProviderInfo] = useState<{ provider: string; isConfigured: boolean }>({
    provider: 'FLUTTERWAVE',
    isConfigured: false,
  });

  const [order, setOrder] = useState<OrderData | null>(null);
  const [txHash, setTxHash] = useState('');
  const [loading, setLoading] = useState(false);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [idempotencyKey] = useState<string>(
    () => `chk_${target.productId}_${target.resourceId || 'combo'}_${Date.now()}`
  );

  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [onClose]);

  useEffect(() => {
    const loadConfig = async () => {
      try {
        const res = await fetch('/api/v1/commerce/products');
        const data = await res.json();
        if (data.cryptoWallet) {
          setWalletInfo(data.cryptoWallet);
          setSelectedCryptoAsset(data.cryptoWallet.primaryAsset || 'USDT');
        }
        if (data.cardGateway) {
          setCardProviderInfo(data.cardGateway);
        }
      } catch {
        // fallback silently
      }
    };
    loadConfig();
  }, []);

  const copyText = async (value: string, field: string) => {
    try {
      await navigator.clipboard.writeText(value);
      setCopiedField(field);
      setTimeout(() => setCopiedField(null), 2000);
    } catch {
      // ignore clipboard errors
    }
  };

  const handleCreateOrder = async () => {
    if (loading) return;
    setLoading(true);
    setError(null);
    setStatusMessage(null);
    try {
      const { referralCode } = getStoredReferral();
      const res = await fetch('/api/v1/commerce/checkout', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({
          productId: target.productId,
          resourceId: target.resourceId || null,
          paymentMethod,
          cryptoAsset: paymentMethod === 'CRYPTO' ? selectedCryptoAsset : null,
          referralCode: referralCode || null,
          idempotencyKey: `${idempotencyKey}_${paymentMethod}_${selectedCryptoAsset}`,
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || data.detail || 'Checkout initialization failed');
      }
      setOrder(data.order);
      if (data.order.paymentMethod === 'CARD' && data.order.checkoutUrl) {
        setStatusMessage('Secure hosted checkout session created. Click below to complete your card payment.');
      }
    } catch (err: any) {
      setError(err.message || 'Unable to create checkout order');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmitCryptoTx = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!order || !txHash.trim() || verifying) return;
    setVerifying(true);
    setError(null);
    setStatusMessage(null);
    try {
      const res = await fetch(`/api/v1/commerce/orders/${order.id}/submit-crypto-tx`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ txHash: txHash.trim() }),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || data.detail || 'Transaction verification failed');
      }
      setOrder(data.order);
      const v = data.order.cryptoVerification;
      if (data.order.status === 'PAID') {
        setStatusMessage('Payment confirmed on-chain! Your strategy download is now unlocked.');
        onPaymentSuccess();
      } else if (v?.reason) {
        setStatusMessage(`Status (${v.status}): ${v.reason}`);
      }
    } catch (err: any) {
      setError(err.message || 'Verification request failed');
    } finally {
      setVerifying(false);
    }
  };

  const handleVerifyCardPayment = async () => {
    if (!order || verifying) return;
    setVerifying(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/commerce/orders/${order.id}/verify-card`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({}),
      });
      const data = await res.json();
      if (!res.ok || !data.success) {
        throw new Error(data.error || data.detail || 'Unable to verify card payment');
      }
      setOrder(data.order);
      if (data.order.status === 'PAID') {
        setStatusMessage('Card payment verified! Your download is now unlocked.');
        onPaymentSuccess();
      } else {
        setStatusMessage(`Current payment status: ${data.order.status}`);
      }
    } catch (err: any) {
      setError(err.message || 'Verification check failed');
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div
      className="nvx-modal-backdrop"
      role="dialog"
      aria-modal="true"
      aria-label="Checkout"
      onClick={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div className="nvx-modal-card">
        <div className="nvx-modal-header">
          <div>
            <div className="nvx-modal-kicker">NOVEXTRADE SECURE CHECKOUT</div>
            <h2 className="nvx-modal-title">{target.productName}</h2>
            {target.resourceTitle && (
              <div className="nvx-modal-subtitle">{target.resourceTitle}</div>
            )}
          </div>
          <button type="button" className="nvx-modal-close" onClick={onClose} aria-label="Close">
            <X size={18} />
          </button>
        </div>

        {/* Authoritative Price Summary */}
        <div className="nvx-checkout-summary">
          <div>
            <span className="nvx-label-muted">Authoritative Server Price</span>
            <div className="nvx-price-hero">${target.priceUsd} <span>USD</span></div>
          </div>
          {order && (
            <div style={{ textAlign: 'right' }}>
              <span className="nvx-label-muted">Order Reference</span>
              <div className="nvx-mono-code">{order.orderReference}</div>
              <span className={`nvx-status-pill nvx-status-${order.status.toLowerCase()}`}>
                {order.status}
              </span>
            </div>
          )}
        </div>

        {error && (
          <div className="nvx-alert nvx-alert-error">
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {statusMessage && (
          <div className={`nvx-alert ${order?.status === 'PAID' ? 'nvx-alert-success' : 'nvx-alert-info'}`}>
            {order?.status === 'PAID' ? <CheckCircle2 size={16} /> : <Clock size={16} />}
            <span>{statusMessage}</span>
          </div>
        )}

        {/* STEP 1: Select Payment Method (before order created) */}
        {!order && (
          <div className="nvx-checkout-step">
            <div className="nvx-section-label">Select Payment Method</div>
            <div className="nvx-method-grid">
              <button
                type="button"
                className={`nvx-method-card ${paymentMethod === 'CRYPTO' ? 'active' : ''}`}
                onClick={() => setPaymentMethod('CRYPTO')}
                disabled={walletInfo ? !walletInfo.isEnabled : false}
              >
                <Coins size={20} color="#f0b90b" />
                <div>
                  <div className="nvx-method-title">Cryptocurrency</div>
                  <div className="nvx-method-desc">
                    {walletInfo ? `${walletInfo.primaryNetwork} (${walletInfo.supportedTokens.join(', ')})` : 'On-chain verified'}
                  </div>
                </div>
              </button>

              <button
                type="button"
                className={`nvx-method-card ${paymentMethod === 'CARD' ? 'active' : ''}`}
                onClick={() => setPaymentMethod('CARD')}
              >
                <CreditCard size={20} color="#f0b90b" />
                <div>
                  <div className="nvx-method-title">Card Payment</div>
                  <div className="nvx-method-desc">
                    Visa / Mastercard ({cardProviderInfo.provider})
                  </div>
                </div>
              </button>
            </div>

            {paymentMethod === 'CRYPTO' && walletInfo && (
              <div className="nvx-crypto-token-row">
                <span className="nvx-section-label">Choose Token on {walletInfo.primaryNetwork}</span>
                <div className="nvx-token-pills">
                  {walletInfo.supportedTokens.map((tok) => (
                    <button
                      key={tok}
                      type="button"
                      className={`nvx-token-pill ${selectedCryptoAsset === tok ? 'active' : ''}`}
                      onClick={() => setSelectedCryptoAsset(tok)}
                    >
                      {tok}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <button
              type="button"
              className="nvx-btn-gold nvx-btn-full"
              onClick={handleCreateOrder}
              disabled={loading}
            >
              {loading ? (
                <>
                  <Loader2 size={16} className="nvx-spin" /> Initializing Order...
                </>
              ) : (
                <>Continue to {paymentMethod === 'CRYPTO' ? 'Crypto Payment' : 'Secure Card Checkout'} — ${target.priceUsd} USD</>
              )}
            </button>
          </div>
        )}

        {/* STEP 2A: Crypto Payment Instructions & On-Chain Verification */}
        {order && order.paymentMethod === 'CRYPTO' && order.status !== 'PAID' && order.cryptoInstructions && (
          <div className="nvx-crypto-instructions">
            <div className="nvx-instruction-box">
              <div className="nvx-instr-row">
                <span>Network & Asset</span>
                <strong>{order.cryptoInstructions.asset} ({order.cryptoInstructions.network})</strong>
              </div>
              <div className="nvx-instr-row">
                <span>Exact Amount Due</span>
                <div className="nvx-copy-inline">
                  <strong style={{ color: '#f0b90b' }}>
                    {order.cryptoInstructions.expectedAmountCrypto} {order.cryptoInstructions.asset}
                  </strong>
                  <button
                    type="button"
                    className="nvx-icon-copy"
                    onClick={() => copyText(order.cryptoInstructions!.expectedAmountCrypto, 'amount')}
                  >
                    {copiedField === 'amount' ? <CheckCircle2 size={14} color="#0ecb81" /> : <Copy size={14} />}
                  </button>
                </div>
              </div>
              <div className="nvx-instr-row">
                <span>Live Rate</span>
                <span>1 {order.cryptoInstructions.asset} = ${order.cryptoInstructions.exchangeRateUsd} USD</span>
              </div>
              <div className="nvx-instr-row">
                <span>Required Confirmations</span>
                <span>{order.cryptoInstructions.requiredConfirmations} blocks</span>
              </div>
            </div>

            <div className="nvx-wallet-address-box">
              <div className="nvx-section-label">Official NovexTrade Receiving Wallet Address</div>
              <div className="nvx-address-copy-row">
                <code className="nvx-address-text">{order.cryptoInstructions.receivingAddress}</code>
                <button
                  type="button"
                  className="nvx-btn-outline"
                  onClick={() => copyText(order.cryptoInstructions!.receivingAddress, 'address')}
                >
                  {copiedField === 'address' ? <CheckCircle2 size={14} color="#0ecb81" /> : <Copy size={14} />}
                  {copiedField === 'address' ? 'Copied' : 'Copy'}
                </button>
              </div>
              <p className="nvx-helper-text">
                Send only <strong>{order.cryptoInstructions.asset}</strong> on the{' '}
                <strong>{order.cryptoInstructions.network}</strong> network. After broadcasting, submit your transaction hash below for automated on-chain verification.
              </p>
            </div>

            <form onSubmit={handleSubmitCryptoTx} className="nvx-tx-form">
              <label className="nvx-section-label" htmlFor="nvx-tx-hash">
                Blockchain Transaction Hash (TxID)
              </label>
              <input
                id="nvx-tx-hash"
                type="text"
                className="nvx-input"
                placeholder="Paste your 0x... or blockchain transaction hash"
                value={txHash}
                onChange={(e) => setTxHash(e.target.value)}
                required
              />
              <button type="submit" className="nvx-btn-gold nvx-btn-full" disabled={verifying || !txHash.trim()}>
                {verifying ? (
                  <>
                    <Loader2 size={16} className="nvx-spin" /> Verifying On-Chain...
                  </>
                ) : (
                  <>
                    <ShieldCheck size={16} /> Verify Transaction On-Chain
                  </>
                )}
              </button>
            </form>
          </div>
        )}

        {/* STEP 2B: Hosted Card Payment */}
        {order && order.paymentMethod === 'CARD' && order.status !== 'PAID' && (
          <div className="nvx-card-instructions">
            <p className="nvx-helper-text">
              You will complete payment on {order.paymentProvider}&apos;s PCI-DSS certified hosted checkout page.
              NovexTrade never sees or stores your card number or CVV. Downloads unlock automatically once the payment webhook is verified.
            </p>
            {order.checkoutUrl && (
              <a
                href={order.checkoutUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="nvx-btn-gold nvx-btn-full"
                style={{ textDecoration: 'none' }}
              >
                <ExternalLink size={16} /> Proceed to Hosted Card Checkout (${order.amountUsd} USD)
              </a>
            )}
            <button
              type="button"
              className="nvx-btn-outline nvx-btn-full"
              onClick={handleVerifyCardPayment}
              disabled={verifying}
              style={{ marginTop: '10px' }}
            >
              {verifying ? <Loader2 size={15} className="nvx-spin" /> : <RefreshCw size={15} />}
              Check Server-Side Verification Status
            </button>
          </div>
        )}

        {/* STEP 3: Verified Paid -> Unlock Download */}
        {order && order.status === 'PAID' && (
          <div className="nvx-paid-box">
            <CheckCircle2 size={36} color="#0ecb81" />
            <h3>Payment Verified & Entitlement Active</h3>
            <p className="nvx-helper-text">
              Order <strong>{order.orderReference}</strong> is confirmed. You can now download your institutional research immediately or anytime from your dashboard.
            </p>
            <button
              type="button"
              className="nvx-btn-gold nvx-btn-full"
              onClick={() => onDownloadUnlocked(order.resourceId || undefined, order.productId === 'combo_bundle')}
            >
              <Download size={16} />
              {order.productId === 'combo_bundle' ? 'Download Complete Strategy Combo (ZIP)' : 'Download Strategy PDF Now'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
