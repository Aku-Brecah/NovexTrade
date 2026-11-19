import React, { useEffect, useState } from 'react';
import { Save, ShieldCheck, AlertCircle, CheckCircle2, Coins } from 'lucide-react';

export const AdminGlobalCryptoWalletPanel: React.FC = () => {
  const [availableNetworks, setAvailableNetworks] = useState<Record<string, string[]>>({
    ERC20: ['USDT', 'USDC', 'ETH'],
    BEP20: ['USDT', 'USDC', 'BNB'],
    TRC20: ['USDT', 'TRX'],
    BTC: ['BTC'],
    SOL: ['SOL', 'USDT', 'USDC'],
  });
  const [isEnabled, setIsEnabled] = useState(true);
  const [receivingAddress, setReceivingAddress] = useState('');
  const [primaryNetwork, setPrimaryNetwork] = useState('ERC20');
  const [primaryAsset, setPrimaryAsset] = useState('USDT');
  const [supportedTokens, setSupportedTokens] = useState<string[]>(['USDT']);
  const [requiredConfirmations, setRequiredConfirmations] = useState(12);
  const [memoTag, setMemoTag] = useState('');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const getToken = () => localStorage.getItem('novextrade_token') || localStorage.getItem('syncnode_token') || '';

  useEffect(() => {
    const load = async () => {
      setLoading(true);
      try {
        const res = await fetch('/api/v1/admin/commerce/crypto-wallet', {
          headers: { Authorization: `Bearer ${getToken()}` },
        });
        const json = await res.json();
        if (!res.ok || !json.success) throw new Error(json.error || 'Failed to load wallet config');
        const w = json.wallet;
        setIsEnabled(Boolean(w.isEnabled));
        setReceivingAddress(w.receivingAddress || '');
        setPrimaryNetwork(w.primaryNetwork || 'ERC20');
        setPrimaryAsset(w.primaryAsset || 'USDT');
        setSupportedTokens(w.supportedTokens || ['USDT']);
        setRequiredConfirmations(w.requiredConfirmations || 12);
        setMemoTag(w.memoTag || '');
        if (w.availableNetworks) setAvailableNetworks(w.availableNetworks);
      } catch (err: any) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };
    load();
  }, []);

  const handleNetworkChange = (net: string) => {
    setPrimaryNetwork(net);
    const allowed = availableNetworks[net] || ['USDT'];
    setPrimaryAsset(allowed[0]);
    setSupportedTokens([allowed[0]]);
  };

  const toggleToken = (tok: string) => {
    setSupportedTokens((prev) =>
      prev.includes(tok) ? (prev.length > 1 ? prev.filter((t) => t !== tok) : prev) : [...prev, tok]
    );
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch('/api/v1/admin/commerce/crypto-wallet', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${getToken()}` },
        body: JSON.stringify({
          is_enabled: isEnabled,
          receiving_address: receivingAddress.trim(),
          primary_network: primaryNetwork,
          primary_asset: primaryAsset,
          supported_tokens: supportedTokens,
          required_confirmations: Number(requiredConfirmations),
          memo_tag: memoTag.trim() || null,
        }),
      });
      const json = await res.json();
      if (!res.ok || !json.success) throw new Error(json.error || 'Validation failed');
      setSuccess('Global receiving wallet updated! Every registered user will now see this exact address at checkout.');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const networkTokens = availableNetworks[primaryNetwork] || ['USDT'];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '820px' }}>
      <div>
        <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 800, color: '#ffffff' }}>
          Global Cryptocurrency Receiving Wallet
        </h2>
        <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#848e9c' }}>
          Configure the single global receiving wallet address displayed to <strong>every registered user</strong> during cryptocurrency checkout. Addresses are strictly validated against the selected blockchain network.
        </p>
      </div>

      {error && (
        <div className="nvx-alert nvx-alert-error"><AlertCircle size={16} /><span>{error}</span></div>
      )}
      {success && (
        <div className="nvx-alert nvx-alert-success"><CheckCircle2 size={16} /><span>{success}</span></div>
      )}

      <form onSubmit={handleSave} className="nvx-panel-card" style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
        {loading ? (
          <div className="nvx-empty-inline">Loading global wallet settings...</div>
        ) : (
          <>
            <label style={{ display: 'flex', alignItems: 'center', gap: '10px', cursor: 'pointer', color: '#eaecef', fontWeight: 600 }}>
              <input type="checkbox" checked={isEnabled} onChange={(e) => setIsEnabled(e.target.checked)} />
              Enable Cryptocurrency Checkout Globally
            </label>

            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '14px' }}>
              <div>
                <label className="nvx-section-label">Blockchain Network</label>
                <select className="nvx-input" value={primaryNetwork} onChange={(e) => handleNetworkChange(e.target.value)}>
                  {Object.keys(availableNetworks).map((net) => (
                    <option key={net} value={net}>{net}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="nvx-section-label">Primary Cryptocurrency</label>
                <select className="nvx-input" value={primaryAsset} onChange={(e) => setPrimaryAsset(e.target.value)}>
                  {networkTokens.map((tok) => (
                    <option key={tok} value={tok}>{tok}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="nvx-section-label">Required Confirmations</label>
                <input
                  type="number"
                  min={1}
                  max={100}
                  className="nvx-input"
                  value={requiredConfirmations}
                  onChange={(e) => setRequiredConfirmations(Number(e.target.value))}
                />
              </div>
            </div>

            <div>
              <label className="nvx-section-label">Global Receiving Wallet Address ({primaryNetwork})</label>
              <input
                type="text"
                className="nvx-input nvx-mono-code"
                value={receivingAddress}
                onChange={(e) => setReceivingAddress(e.target.value)}
                placeholder="0x... / T... / bc1... / Solana pubkey"
                required
              />
            </div>

            <div>
              <label className="nvx-section-label">Supported Tokens on {primaryNetwork}</label>
              <div className="nvx-token-pills">
                {networkTokens.map((tok) => (
                  <button
                    key={tok}
                    type="button"
                    className={`nvx-token-pill ${supportedTokens.includes(tok) ? 'active' : ''}`}
                    onClick={() => toggleToken(tok)}
                  >
                    <Coins size={13} /> {tok}
                  </button>
                ))}
              </div>
            </div>

            <div>
              <label className="nvx-section-label">Optional Memo / Tag (leave blank to use Order Reference)</label>
              <input
                type="text"
                className="nvx-input"
                value={memoTag}
                onChange={(e) => setMemoTag(e.target.value)}
                placeholder="Optional memo or tag"
              />
            </div>

            <div className="nvx-wallet-address-box">
              <div className="nvx-section-label"><ShieldCheck size={14} color="#0ecb81" /> Active Public Preview (Shown to All Users)</div>
              <code className="nvx-address-text">{receivingAddress || 'Not configured'}</code>
            </div>

            <button type="submit" className="nvx-btn-gold" disabled={saving} style={{ alignSelf: 'flex-start' }}>
              <Save size={15} /> {saving ? 'Validating & Saving...' : 'Save Global Wallet Configuration'}
            </button>
          </>
        )}
      </form>
    </div>
  );
};
