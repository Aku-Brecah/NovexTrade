import React, { useEffect, useState } from 'react';
import { RefreshCw, Save, Search, CheckCircle2, XCircle, DollarSign, AlertCircle } from 'lucide-react';

export const AdminReferralsPanel: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(true);
  const [savingCfg, setSavingCfg] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  // Commission Config Form
  const [isEnabled, setIsEnabled] = useState(true);
  const [individualPct, setIndividualPct] = useState('0.00');
  const [comboPct, setComboPct] = useState('0.00');
  const [minPayout, setMinPayout] = useState('50.00');
  const [holdingDays, setHoldingDays] = useState(14);
  const [approvalMode, setApprovalMode] = useState('MANUAL');
  const [terms, setTerms] = useState('');

  const getToken = () => localStorage.getItem('novextrade_token') || localStorage.getItem('syncnode_token') || '';

  const loadData = async () => {
    setLoading(true);
    setError(null);
    try {
      const qs = search.trim() ? `?search=${encodeURIComponent(search.trim())}` : '';
      const res = await fetch(`/api/v1/admin/referrals/overview${qs}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      const json = await res.json();
      if (!res.ok || !json.success) throw new Error(json.error || 'Failed to load referrals overview');
      setData(json);
      if (json.config) {
        setIsEnabled(Boolean(json.config.is_enabled));
        setIndividualPct(String(json.config.individual_pdf_commission_percent ?? '0.00'));
        setComboPct(String(json.config.combo_commission_percent ?? '0.00'));
        setMinPayout(String(json.config.min_payout_threshold_usd ?? '50.00'));
        setHoldingDays(Number(json.config.holding_period_days ?? 14));
        setApprovalMode(json.config.approval_mode || 'MANUAL');
        setTerms(json.config.terms_and_conditions || '');
      }
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, []);

  const handleSaveConfig = async (e: React.FormEvent) => {
    e.preventDefault();
    setSavingCfg(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch('/api/v1/admin/referrals/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({
          is_enabled: isEnabled,
          individual_pdf_commission_percent: individualPct,
          combo_commission_percent: comboPct,
          min_payout_threshold_usd: minPayout,
          holding_period_days: Number(holdingDays),
          approval_mode: approvalMode,
          terms_and_conditions: terms,
        }),
      });
      const json = await res.json();
      if (!res.ok || !json.success) throw new Error(json.error || 'Failed to update commission config');
      setSuccess('Referral commission configuration saved and audit-logged.');
      await loadData();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSavingCfg(false);
    }
  };

  const handleCommissionAction = async (commissionId: string, action: 'APPROVE' | 'REJECT' | 'MARK_PAID') => {
    let reason: string | undefined;
    let payout_reference: string | undefined;
    if (action === 'REJECT') {
      reason = window.prompt('Rejection reason:') || 'Rejected by administrator';
    }
    if (action === 'MARK_PAID') {
      payout_reference = window.prompt('Payout transaction reference:') || `PAYOUT-${Date.now()}`;
    }
    setBusyId(commissionId);
    try {
      const res = await fetch(`/api/v1/admin/referrals/commissions/${commissionId}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ action, reason, payout_reference }),
      });
      const json = await res.json();
      if (!res.ok || !json.success) throw new Error(json.error || 'Commission action failed');
      await loadData();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const s = data?.summary;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '12px' }}>
        <div>
          <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 800, color: '#ffffff' }}>
            Referral Program &amp; Commission Administration
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#848e9c' }}>
            Configure commission rates for $99 Individual PDF and $699 Combo sales, inspect referral links, and approve or audit payouts.
          </p>
        </div>
        <button type="button" className="nvx-btn-outline" onClick={loadData}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {error && <div className="nvx-alert nvx-alert-error"><AlertCircle size={15} /><span>{error}</span></div>}
      {success && <div className="nvx-alert nvx-alert-success"><CheckCircle2 size={15} /><span>{success}</span></div>}

      {s && (
        <div className="nvx-kpi-grid">
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Registered Users</div><div className="nvx-kpi-value">{s.totalRegisteredUsers}</div></div>
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Active Ref Links</div><div className="nvx-kpi-value">{s.totalReferralLinks}</div></div>
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Clicks / Signups</div><div className="nvx-kpi-value">{s.totalReferralClicks} / {s.successfulRegistrations}</div></div>
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Referred Purchases</div><div className="nvx-kpi-value">{s.referredPurchases}</div></div>
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Total Commissions</div><div className="nvx-kpi-value nvx-gold-text">${s.totalCommissionsUsd}</div></div>
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Pending / Approved</div><div className="nvx-kpi-value">${s.pendingCommissionsUsd} / ${s.approvedCommissionsUsd}</div></div>
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Paid / Flagged</div><div className="nvx-kpi-value" style={{ color: '#0ecb81' }}>${s.paidCommissionsUsd} ({s.flaggedRelationships} flagged)</div></div>
        </div>
      )}

      {/* Admin Commission Configuration */}
      <form onSubmit={handleSaveConfig} className="nvx-panel-card" style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
        <div className="nvx-panel-title">Commission Rules &amp; Payout Policy</div>
        <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', color: '#eaecef', fontWeight: 600 }}>
          <input type="checkbox" checked={isEnabled} onChange={(e) => setIsEnabled(e.target.checked)} />
          Enable Referral Commissions
        </label>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))', gap: '12px' }}>
          <div>
            <label className="nvx-section-label">Individual PDF ($99) %</label>
            <input type="number" step="0.01" min={0} max={100} className="nvx-input" value={individualPct} onChange={(e) => setIndividualPct(e.target.value)} />
          </div>
          <div>
            <label className="nvx-section-label">Combo Bundle ($699) %</label>
            <input type="number" step="0.01" min={0} max={100} className="nvx-input" value={comboPct} onChange={(e) => setComboPct(e.target.value)} />
          </div>
          <div>
            <label className="nvx-section-label">Min Payout Threshold (USD)</label>
            <input type="number" step="0.01" min={0} className="nvx-input" value={minPayout} onChange={(e) => setMinPayout(e.target.value)} />
          </div>
          <div>
            <label className="nvx-section-label">Holding Period (Days)</label>
            <input type="number" min={0} max={365} className="nvx-input" value={holdingDays} onChange={(e) => setHoldingDays(Number(e.target.value))} />
          </div>
          <div>
            <label className="nvx-section-label">Approval Mode</label>
            <select className="nvx-input" value={approvalMode} onChange={(e) => setApprovalMode(e.target.value)}>
              <option value="MANUAL">MANUAL</option>
              <option value="AUTO_AFTER_HOLD">AUTO_AFTER_HOLD</option>
            </select>
          </div>
        </div>

        <div>
          <label className="nvx-section-label">Referral Program Terms &amp; Conditions</label>
          <textarea className="nvx-input" rows={2} value={terms} onChange={(e) => setTerms(e.target.value)} />
        </div>

        <button type="submit" className="nvx-btn-gold" disabled={savingCfg} style={{ alignSelf: 'flex-start' }}>
          <Save size={15} /> {savingCfg ? 'Saving...' : 'Save Commission Configuration'}
        </button>
      </form>

      {/* Search */}
      <div className="nvx-panel-card" style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
        <Search size={15} color="#848e9c" />
        <input
          type="text"
          className="nvx-input"
          placeholder="Search referrer email, referred email, referral code, or order ref..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && loadData()}
        />
        <button type="button" className="nvx-btn-gold" onClick={loadData}>Search</button>
      </div>

      {/* Commissions Table */}
      <div className="nvx-panel-card">
        <div className="nvx-panel-title">Referral Commissions Queue</div>
        {loading ? (
          <div className="nvx-empty-inline">Loading commissions...</div>
        ) : !data?.commissions?.length ? (
          <div className="nvx-empty-inline">No referral commissions recorded yet.</div>
        ) : (
          <div className="nvx-table-scroll">
            <table className="nvx-table">
              <thead>
                <tr>
                  <th>Order Ref</th>
                  <th>Referrer</th>
                  <th>Referred Buyer</th>
                  <th>Purchase</th>
                  <th>Commission</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.commissions.map((c: any) => (
                  <tr key={c.id}>
                    <td className="nvx-mono-code">{c.order_reference || c.order_id}</td>
                    <td>{c.referrer_email || c.referrer_user_id}</td>
                    <td>{c.referred_email || c.referred_user_id}</td>
                    <td>${c.purchase_amount_usd}</td>
                    <td className="nvx-gold-text">${c.commission_amount_usd} ({c.commission_rate_percent}%)</td>
                    <td><span className={`nvx-status-pill nvx-status-${c.status.toLowerCase()}`}>{c.status}</span></td>
                    <td>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        {c.status === 'PENDING' && (
                          <>
                            <button type="button" className="nvx-btn-outline" style={{ borderColor: '#0ecb81', color: '#0ecb81' }} disabled={busyId === c.id} onClick={() => handleCommissionAction(c.id, 'APPROVE')}>
                              <CheckCircle2 size={12} /> Approve
                            </button>
                            <button type="button" className="nvx-btn-outline" style={{ borderColor: '#f6465d', color: '#f6465d' }} disabled={busyId === c.id} onClick={() => handleCommissionAction(c.id, 'REJECT')}>
                              <XCircle size={12} /> Reject
                            </button>
                          </>
                        )}
                        {c.status === 'APPROVED' && (
                          <button type="button" className="nvx-btn-gold" disabled={busyId === c.id} onClick={() => handleCommissionAction(c.id, 'MARK_PAID')}>
                            <DollarSign size={12} /> Mark Paid
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
