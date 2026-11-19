import React, { useEffect, useState } from 'react';
import {
  Copy,
  CheckCircle2,
  Share2,
  Users,
  MousePointerClick,
  ShoppingBag,
  DollarSign,
  TrendingUp,
  Download,
  Package,
  RefreshCw,
  AlertCircle,
  Lock,
} from 'lucide-react';
import { Footer } from '../Footer';

interface ReferralDashboardData {
  referralCode: string;
  referralUrl: string;
  stats: {
    totalClicks: number;
    totalRegistrations: number;
    totalReferredCustomers: number;
    totalReferredPurchases: number;
    pendingCommissionsUsd: string;
    approvedCommissionsUsd: string;
    paidCommissionsUsd: string;
    cancelledOrReversedCommissionsUsd: string;
    conversionRatePercent: string;
  };
  programConfig: {
    isEnabled: boolean;
    individualPdfCommissionPercent: string;
    comboCommissionPercent: string;
    minPayoutThresholdUsd: string;
    holdingPeriodDays: number;
    approvalMode: string;
    termsAndConditions: string;
  };
  activity: Array<{
    id: string;
    type: string;
    referredUser: string;
    productName: string;
    orderReference?: string | null;
    purchaseAmountUsd: string;
    commissionRatePercent: string;
    commissionAmountUsd: string;
    status: string;
    reversalReason?: string | null;
    createdAt: number;
  }>;
}

interface UserOrder {
  id: string;
  orderReference: string;
  productId: string;
  productName: string;
  resourceId?: string | null;
  amountUsd: string;
  paymentMethod: string;
  paymentProvider: string;
  status: string;
  createdAt: number;
  paidAt?: number | null;
}

interface ReferralDashboardViewProps {
  token: string | null;
  onRequireAuth: () => void;
  onNavigateToResources?: () => void;
  onNavigateToTrade?: (sym?: string) => void;
}

export const ReferralDashboardView: React.FC<ReferralDashboardViewProps> = ({
  token,
  onRequireAuth,
  onNavigateToResources,
  onNavigateToTrade,
}) => {
  const [activeTab, setActiveTab] = useState<'referrals' | 'orders'>('referrals');
  const [refData, setRefData] = useState<ReferralDashboardData | null>(null);
  const [orders, setOrders] = useState<UserOrder[]>([]);
  const [hasComboAccess, setHasComboAccess] = useState(false);
  const [unlockedResourceIds, setUnlockedResourceIds] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<'url' | 'code' | null>(null);
  const [downloadingId, setDownloadingId] = useState<string | null>(null);

  const loadData = async () => {
    if (!token) {
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [refRes, ordRes] = await Promise.all([
        fetch('/api/v1/referrals/dashboard', { headers: { Authorization: `Bearer ${token}` } }),
        fetch('/api/v1/commerce/orders', { headers: { Authorization: `Bearer ${token}` } }),
      ]);
      const refJson = await refRes.json();
      const ordJson = await ordRes.json();
      if (!refRes.ok || !refJson.success) {
        throw new Error(refJson.error || 'Failed to load referral dashboard');
      }
      setRefData(refJson);
      if (ordRes.ok && ordJson.success) {
        setOrders(ordJson.orders || []);
        setHasComboAccess(Boolean(ordJson.hasComboAccess));
        setUnlockedResourceIds(ordJson.unlockedResourceIds || []);
      }
    } catch (err: any) {
      setError(err.message || 'Unable to load dashboard data');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [token]);

  const copyValue = async (val: string, kind: 'url' | 'code') => {
    try {
      await navigator.clipboard.writeText(val);
      setCopied(kind);
      setTimeout(() => setCopied(null), 2000);
    } catch {
      // ignore
    }
  };

  const handleDownload = async (resourceId?: string, isCombo = false) => {
    if (!token) return;
    const key = isCombo ? 'COMBO' : resourceId || '';
    setDownloadingId(key);
    try {
      const url = isCombo
        ? '/api/v1/resources/combo/download'
        : `/api/v1/resources/download/${resourceId}`;
      const res = await fetch(url, { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.error || 'Download authorization failed');
      }
      const blob = await res.blob();
      const objUrl = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objUrl;
      a.download = isCombo ? 'novextrade-complete-strategy-combo.zip' : `${resourceId}.pdf`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      window.URL.revokeObjectURL(objUrl);
    } catch (err: any) {
      setError(err.message || 'Download failed');
    } finally {
      setDownloadingId(null);
    }
  };

  if (!token) {
    return (
      <div className="nvx-page-wrap">
        <div className="nvx-empty-card">
          <Lock size={36} color="#f0b90b" />
          <h2>Sign In to Access Your Referral &amp; Purchases Dashboard</h2>
          <p>
            Every registered NovexTrade account receives a permanent referral link, real-time
            commission analytics, and instant access to verified PDF &amp; Combo downloads.
          </p>
          <button type="button" className="nvx-btn-gold" onClick={onRequireAuth}>
            Sign In / Create Account
          </button>
        </div>
        <Footer onNavigateToTrade={onNavigateToTrade} />
      </div>
    );
  }

  const shareText = encodeURIComponent(
    'Join NovexTrade Institutional Research & Trading Platform using my referral link:'
  );
  const shareUrl = encodeURIComponent(refData?.referralUrl || '');

  return (
    <div className="nvx-page-wrap">
      <div className="nvx-container">
        <div className="nvx-page-header">
          <div>
            <div className="nvx-modal-kicker">PARTNER PROGRAM &amp; ENTITLEMENTS</div>
            <h1>Referral Dashboard &amp; Purchased Downloads</h1>
            <p className="nvx-subtitle">
              Track your permanent referral link, verified conversions, commissions, order history, and unlocked strategy downloads.
            </p>
          </div>
          <div className="nvx-header-actions">
            <button type="button" className="nvx-btn-outline" onClick={loadData}>
              <RefreshCw size={15} /> Refresh
            </button>
            {onNavigateToResources && (
              <button type="button" className="nvx-btn-gold" onClick={onNavigateToResources}>
                <Package size={15} /> Browse Strategy PDFs
              </button>
            )}
          </div>
        </div>

        <div className="nvx-tab-bar">
          <button
            type="button"
            className={`nvx-tab-btn ${activeTab === 'referrals' ? 'active' : ''}`}
            onClick={() => setActiveTab('referrals')}
          >
            <Share2 size={15} /> Referral Program &amp; Commissions
          </button>
          <button
            type="button"
            className={`nvx-tab-btn ${activeTab === 'orders' ? 'active' : ''}`}
            onClick={() => setActiveTab('orders')}
          >
            <ShoppingBag size={15} /> My Orders &amp; Downloads ({orders.length})
          </button>
        </div>

        {error && (
          <div className="nvx-alert nvx-alert-error" style={{ marginBottom: '16px' }}>
            <AlertCircle size={16} />
            <span>{error}</span>
          </div>
        )}

        {loading ? (
          <div className="nvx-loading-grid">
            <div className="nvx-skeleton-card" />
            <div className="nvx-skeleton-card" />
            <div className="nvx-skeleton-card" />
          </div>
        ) : activeTab === 'referrals' && refData ? (
          <>
            {/* Referral Link & Sharing Box */}
            <div className="nvx-panel-card nvx-referral-hero">
              <div className="nvx-ref-link-col">
                <div className="nvx-section-label">Your Permanent Referral Link</div>
                <div className="nvx-address-copy-row">
                  <code className="nvx-address-text">{refData.referralUrl}</code>
                  <button
                    type="button"
                    className="nvx-btn-gold"
                    onClick={() => copyValue(refData.referralUrl, 'url')}
                  >
                    {copied === 'url' ? <CheckCircle2 size={15} /> : <Copy size={15} />}
                    {copied === 'url' ? 'Copied Link' : 'Copy Link'}
                  </button>
                </div>

                <div className="nvx-ref-meta-row">
                  <span>
                    Referral Code:{' '}
                    <strong className="nvx-gold-text">{refData.referralCode}</strong>
                    <button
                      type="button"
                      className="nvx-icon-copy"
                      style={{ marginLeft: '6px' }}
                      onClick={() => copyValue(refData.referralCode, 'code')}
                    >
                      {copied === 'code' ? <CheckCircle2 size={13} color="#0ecb81" /> : <Copy size={13} />}
                    </button>
                  </span>
                  <span>
                    Individual PDF Rate: <strong>{refData.programConfig.individualPdfCommissionPercent}%</strong>
                  </span>
                  <span>
                    Combo Rate: <strong>{refData.programConfig.comboCommissionPercent}%</strong>
                  </span>
                  <span>
                    Min Payout: <strong>${refData.programConfig.minPayoutThresholdUsd} USD</strong>
                  </span>
                </div>
              </div>

              <div className="nvx-share-col">
                <div className="nvx-section-label">Share Referral Link</div>
                <div className="nvx-share-buttons">
                  <a
                    href={`https://twitter.com/intent/tweet?text=${shareText}&url=${shareUrl}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="nvx-share-pill"
                  >
                    X / Twitter
                  </a>
                  <a
                    href={`https://wa.me/?text=${shareText}%20${shareUrl}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="nvx-share-pill"
                  >
                    WhatsApp
                  </a>
                  <a
                    href={`https://t.me/share/url?url=${shareUrl}&text=${shareText}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="nvx-share-pill"
                  >
                    Telegram
                  </a>
                  <a
                    href={`https://www.linkedin.com/sharing/share-offsite/?url=${shareUrl}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="nvx-share-pill"
                  >
                    LinkedIn
                  </a>
                </div>
              </div>
            </div>

            {/* KPI Grid */}
            <div className="nvx-kpi-grid">
              <div className="nvx-kpi-card">
                <div className="nvx-kpi-label"><MousePointerClick size={14} /> Referral Clicks</div>
                <div className="nvx-kpi-value">{refData.stats.totalClicks}</div>
              </div>
              <div className="nvx-kpi-card">
                <div className="nvx-kpi-label"><Users size={14} /> Registrations</div>
                <div className="nvx-kpi-value">{refData.stats.totalRegistrations}</div>
              </div>
              <div className="nvx-kpi-card">
                <div className="nvx-kpi-label"><ShoppingBag size={14} /> Referred Customers</div>
                <div className="nvx-kpi-value">{refData.stats.totalReferredCustomers}</div>
              </div>
              <div className="nvx-kpi-card">
                <div className="nvx-kpi-label"><Package size={14} /> Referred Purchases</div>
                <div className="nvx-kpi-value">{refData.stats.totalReferredPurchases}</div>
              </div>
              <div className="nvx-kpi-card">
                <div className="nvx-kpi-label"><TrendingUp size={14} /> Conversion Rate</div>
                <div className="nvx-kpi-value nvx-gold-text">{refData.stats.conversionRatePercent}%</div>
              </div>
              <div className="nvx-kpi-card">
                <div className="nvx-kpi-label"><DollarSign size={14} /> Pending Commissions</div>
                <div className="nvx-kpi-value">${refData.stats.pendingCommissionsUsd}</div>
              </div>
              <div className="nvx-kpi-card">
                <div className="nvx-kpi-label"><DollarSign size={14} /> Approved Commissions</div>
                <div className="nvx-kpi-value" style={{ color: '#0ecb81' }}>${refData.stats.approvedCommissionsUsd}</div>
              </div>
              <div className="nvx-kpi-card">
                <div className="nvx-kpi-label"><DollarSign size={14} /> Paid Commissions</div>
                <div className="nvx-kpi-value" style={{ color: '#0ecb81' }}>${refData.stats.paidCommissionsUsd}</div>
              </div>
              <div className="nvx-kpi-card">
                <div className="nvx-kpi-label"><DollarSign size={14} /> Cancelled / Reversed</div>
                <div className="nvx-kpi-value" style={{ color: '#f6465d' }}>${refData.stats.cancelledOrReversedCommissionsUsd}</div>
              </div>
            </div>

            {/* Activity Table */}
            <div className="nvx-panel-card">
              <div className="nvx-panel-title">Referral Activity &amp; Commission Ledger</div>
              {refData.activity.length === 0 ? (
                <div className="nvx-empty-inline">
                  No referral registrations or purchases recorded yet. Share your link above to get started.
                </div>
              ) : (
                <div className="nvx-table-scroll">
                  <table className="nvx-table">
                    <thead>
                      <tr>
                        <th>Event</th>
                        <th>Referred Account</th>
                        <th>Product / Action</th>
                        <th>Purchase (USD)</th>
                        <th>Commission</th>
                        <th>Status</th>
                        <th>Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {refData.activity.map((row) => (
                        <tr key={row.id}>
                          <td><span className="nvx-badge-subtle">{row.type}</span></td>
                          <td>{row.referredUser}</td>
                          <td>{row.productName}</td>
                          <td>${row.purchaseAmountUsd}</td>
                          <td className="nvx-gold-text">${row.commissionAmountUsd} ({row.commissionRatePercent}%)</td>
                          <td>
                            <span className={`nvx-status-pill nvx-status-${row.status.toLowerCase()}`}>
                              {row.status}
                            </span>
                          </td>
                          <td>{new Date(row.createdAt).toLocaleDateString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
              {refData.programConfig.termsAndConditions && (
                <div className="nvx-terms-note">
                  <strong>Program Terms ({refData.programConfig.holdingPeriodDays}-day hold, {refData.programConfig.approvalMode}):</strong>{' '}
                  {refData.programConfig.termsAndConditions}
                </div>
              )}
            </div>
          </>
        ) : (
          /* ORDERS & PURCHASED DOWNLOADS TAB */
          <>
            <div className="nvx-panel-card" style={{ marginBottom: '20px' }}>
              <div className="nvx-panel-title">Your Unlocked Downloads</div>
              {unlockedResourceIds.length === 0 && !hasComboAccess ? (
                <div className="nvx-empty-inline">
                  You have not purchased any strategy PDFs yet. Individual PDFs are $99 USD and the Complete Combo (all 5 PDFs + ZIP) is $699 USD.
                </div>
              ) : (
                <div className="nvx-entitlement-list">
                  {hasComboAccess && (
                    <div className="nvx-entitlement-row">
                      <div>
                        <strong>Complete Institutional Strategy Combo (All 5 PDFs ZIP)</strong>
                        <div className="nvx-label-muted">Full bundle entitlement active</div>
                      </div>
                      <button
                        type="button"
                        className="nvx-btn-gold"
                        disabled={downloadingId === 'COMBO'}
                        onClick={() => handleDownload(undefined, true)}
                      >
                        <Download size={15} /> {downloadingId === 'COMBO' ? 'Downloading...' : 'Download Combo ZIP'}
                      </button>
                    </div>
                  )}
                  {unlockedResourceIds.map((rid) => (
                    <div key={rid} className="nvx-entitlement-row">
                      <div>
                        <strong>{rid}</strong>
                        <div className="nvx-label-muted">Verified Individual PDF Entitlement</div>
                      </div>
                      <button
                        type="button"
                        className="nvx-btn-outline"
                        disabled={downloadingId === rid}
                        onClick={() => handleDownload(rid, false)}
                      >
                        <Download size={15} /> {downloadingId === rid ? 'Downloading...' : 'Download PDF'}
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="nvx-panel-card">
              <div className="nvx-panel-title">Order History</div>
              {orders.length === 0 ? (
                <div className="nvx-empty-inline">No checkout orders found for your account.</div>
              ) : (
                <div className="nvx-table-scroll">
                  <table className="nvx-table">
                    <thead>
                      <tr>
                        <th>Reference</th>
                        <th>Product</th>
                        <th>Amount</th>
                        <th>Method</th>
                        <th>Status</th>
                        <th>Date</th>
                      </tr>
                    </thead>
                    <tbody>
                      {orders.map((ord) => (
                        <tr key={ord.id}>
                          <td className="nvx-mono-code">{ord.orderReference}</td>
                          <td>{ord.productName}</td>
                          <td className="nvx-gold-text">${ord.amountUsd} USD</td>
                          <td>{ord.paymentMethod} ({ord.paymentProvider})</td>
                          <td>
                            <span className={`nvx-status-pill nvx-status-${ord.status.toLowerCase()}`}>
                              {ord.status}
                            </span>
                          </td>
                          <td>{new Date(ord.createdAt).toLocaleString()}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </>
        )}
      </div>
      <Footer onNavigateToTrade={onNavigateToTrade} />
    </div>
  );
};
