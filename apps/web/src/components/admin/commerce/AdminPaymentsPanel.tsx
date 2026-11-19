import React, { useEffect, useState } from 'react';
import { RefreshCw, Search, CheckCircle2, XCircle, RotateCcw, AlertTriangle, ShieldCheck } from 'lucide-react';

export const AdminPaymentsPanel: React.FC = () => {
  const [data, setData] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [methodFilter, setMethodFilter] = useState('');
  const [search, setSearch] = useState('');
  const [busyId, setBusyId] = useState<string | null>(null);

  const getToken = () => localStorage.getItem('novextrade_token') || localStorage.getItem('syncnode_token') || '';

  const loadPayments = async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams();
      if (statusFilter) params.set('status', statusFilter);
      if (methodFilter) params.set('method', methodFilter);
      if (search.trim()) params.set('search', search.trim());
      const res = await fetch(`/api/v1/admin/commerce/payments?${params.toString()}`, {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      const json = await res.json();
      if (!res.ok || !json.success) throw new Error(json.error || 'Failed to load payment records');
      setData(json);
    } catch (err: any) {
      setError(err.message || 'Unable to load payments');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPayments();
  }, [statusFilter, methodFilter]);

  const handleOrderAction = async (orderId: string, action: 'refund' | 'dispute') => {
    const reason = window.prompt(`Enter audit reason for marking order as ${action.toUpperCase()}:`, `${action} processed by admin`);
    if (!reason) return;
    setBusyId(orderId);
    try {
      const res = await fetch(`/api/v1/admin/commerce/orders/${orderId}/${action}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ reason }),
      });
      const json = await res.json();
      if (!res.ok || !json.success) throw new Error(json.error || 'Action failed');
      await loadPayments();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  const handleReconcileCrypto = async (txId: string, decision: 'APPROVE' | 'REJECT') => {
    const notes = window.prompt(`Reconciliation notes for ${decision}:`, `Manually ${decision.toLowerCase()}d by admin`);
    if (notes === null) return;
    setBusyId(txId);
    try {
      const res = await fetch(`/api/v1/admin/commerce/crypto-transactions/${txId}/reconcile`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({ decision, notes }),
      });
      const json = await res.json();
      if (!res.ok || !json.success) throw new Error(json.error || 'Reconciliation failed');
      await loadPayments();
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
          <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 800, color: '#ffffff' }}>Product Payments &amp; Order Management</h2>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#848e9c' }}>
            Monitor $99 Individual PDF &amp; $699 Combo sales, card webhooks, refunds, disputes, and shared-wallet crypto reconciliation.
          </p>
        </div>
        <button type="button" className="nvx-btn-outline" onClick={loadPayments}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {error && (
        <div className="nvx-alert nvx-alert-error">
          <AlertTriangle size={15} />
          <span>{error}</span>
        </div>
      )}

      {s && (
        <div className="nvx-kpi-grid">
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Total Revenue</div><div className="nvx-kpi-value nvx-gold-text">${s.totalRevenueUsd}</div></div>
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Total Sales</div><div className="nvx-kpi-value">{s.totalSales}</div></div>
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Individual PDFs ($99)</div><div className="nvx-kpi-value">{s.individualPdfSales}</div></div>
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Combo Bundles ($699)</div><div className="nvx-kpi-value">{s.comboSales}</div></div>
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Card / Crypto Txns</div><div className="nvx-kpi-value">{s.cardTransactions} / {s.cryptoTransactions}</div></div>
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Pending / Failed</div><div className="nvx-kpi-value">{s.pendingPayments} / {s.failedPayments}</div></div>
          <div className="nvx-kpi-card"><div className="nvx-kpi-label">Refunds / Disputed</div><div className="nvx-kpi-value" style={{ color: '#f6465d' }}>{s.refunds} / {s.disputedTransactions}</div></div>
        </div>
      )}

      {/* Filters */}
      <div className="nvx-panel-card" style={{ display: 'flex', gap: '10px', flexWrap: 'wrap', alignItems: 'center' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flex: '1 1 220px' }}>
          <Search size={15} color="#848e9c" />
          <input
            type="text"
            className="nvx-input"
            placeholder="Search order ref, email, or product..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && loadPayments()}
          />
        </div>
        <select className="nvx-input" style={{ width: 'auto' }} value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
          <option value="">All Statuses</option>
          <option value="PENDING">PENDING</option>
          <option value="AWAITING_VERIFICATION">AWAITING_VERIFICATION</option>
          <option value="PAID">PAID</option>
          <option value="UNDERPAID">UNDERPAID</option>
          <option value="FAILED">FAILED</option>
          <option value="REFUNDED">REFUNDED</option>
          <option value="DISPUTED">DISPUTED</option>
        </select>
        <select className="nvx-input" style={{ width: 'auto' }} value={methodFilter} onChange={(e) => setMethodFilter(e.target.value)}>
          <option value="">All Methods</option>
          <option value="CARD">CARD</option>
          <option value="CRYPTO">CRYPTO</option>
        </select>
        <button type="button" className="nvx-btn-gold" onClick={loadPayments}>Filter</button>
      </div>

      {/* Orders Table */}
      <div className="nvx-panel-card">
        <div className="nvx-panel-title">Checkout Orders &amp; Payment Verification Log</div>
        {loading ? (
          <div className="nvx-empty-inline">Loading payment records...</div>
        ) : !data?.orders?.length ? (
          <div className="nvx-empty-inline">No product orders recorded yet.</div>
        ) : (
          <div className="nvx-table-scroll">
            <table className="nvx-table">
              <thead>
                <tr>
                  <th>Reference</th>
                  <th>Customer</th>
                  <th>Product</th>
                  <th>Amount</th>
                  <th>Method</th>
                  <th>Status</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.orders.map((o: any) => (
                  <tr key={o.id}>
                    <td className="nvx-mono-code">{o.orderReference}</td>
                    <td>{o.customerEmail || o.userId}</td>
                    <td>{o.productName}</td>
                    <td className="nvx-gold-text">${o.amountUsd} USD</td>
                    <td>{o.paymentMethod} ({o.paymentProvider})</td>
                    <td><span className={`nvx-status-pill nvx-status-${o.status.toLowerCase()}`}>{o.status}</span></td>
                    <td>
                      {o.status === 'PAID' && (
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            type="button"
                            className="nvx-btn-outline"
                            disabled={busyId === o.id}
                            onClick={() => handleOrderAction(o.id, 'refund')}
                          >
                            <RotateCcw size={12} /> Refund
                          </button>
                          <button
                            type="button"
                            className="nvx-btn-outline"
                            style={{ borderColor: '#f6465d', color: '#f6465d' }}
                            disabled={busyId === o.id}
                            onClick={() => handleOrderAction(o.id, 'dispute')}
                          >
                            Dispute
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Crypto Reconciliation Table */}
      <div className="nvx-panel-card">
        <div className="nvx-panel-title"><ShieldCheck size={16} color="#f0b90b" /> Cryptocurrency Transactions &amp; Shared Wallet Reconciliation</div>
        {!data?.cryptoTransactions?.length ? (
          <div className="nvx-empty-inline">No cryptocurrency transactions submitted yet.</div>
        ) : (
          <div className="nvx-table-scroll">
            <table className="nvx-table">
              <thead>
                <tr>
                  <th>Order Ref</th>
                  <th>Customer</th>
                  <th>Tx Hash</th>
                  <th>Asset / Net</th>
                  <th>Expected / Received</th>
                  <th>Confs</th>
                  <th>Status</th>
                  <th>Reconcile</th>
                </tr>
              </thead>
              <tbody>
                {data.cryptoTransactions.map((tx: any) => (
                  <tr key={tx.id}>
                    <td className="nvx-mono-code">{tx.order_reference || tx.order_id}</td>
                    <td>{tx.customerEmail || tx.user_id}</td>
                    <td className="nvx-mono-code" title={tx.tx_hash}>{tx.tx_hash?.slice(0, 14)}...</td>
                    <td>{tx.asset} / {tx.network}</td>
                    <td>{tx.expected_amount_crypto} / {tx.received_amount_crypto}</td>
                    <td>{tx.confirmations}/{tx.required_confirmations}</td>
                    <td><span className={`nvx-status-pill nvx-status-${tx.verification_status.toLowerCase()}`}>{tx.verification_status}</span></td>
                    <td>
                      {tx.verification_status !== 'CONFIRMED' && (
                        <div style={{ display: 'flex', gap: '6px' }}>
                          <button
                            type="button"
                            className="nvx-btn-outline"
                            style={{ borderColor: '#0ecb81', color: '#0ecb81' }}
                            disabled={busyId === tx.id}
                            onClick={() => handleReconcileCrypto(tx.id, 'APPROVE')}
                          >
                            <CheckCircle2 size={12} /> Approve
                          </button>
                          <button
                            type="button"
                            className="nvx-btn-outline"
                            style={{ borderColor: '#f6465d', color: '#f6465d' }}
                            disabled={busyId === tx.id}
                            onClick={() => handleReconcileCrypto(tx.id, 'REJECT')}
                          >
                            <XCircle size={12} /> Reject
                          </button>
                        </div>
                      )}
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
