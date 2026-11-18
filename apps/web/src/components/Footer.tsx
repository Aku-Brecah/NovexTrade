import React from 'react';
import { Layers, ShieldCheck, ArrowUpRight, Lock, Activity } from 'lucide-react';

interface FooterProps {
  onNavigateToTrade?: (sym?: string) => void;
  onNavigateToP2P?: () => void;
  onOpenAuth?: () => void;
}

export const Footer: React.FC<FooterProps> = ({
  onNavigateToTrade,
  onNavigateToP2P,
  onOpenAuth
}) => {
  return (
    <footer
      style={{
        background: '#181a20',
        borderTop: '1px solid #2b313a',
        padding: '50px 24px 30px',
        color: '#848e9c',
        fontSize: '13px'
      }}
    >
      <div style={{ maxWidth: '1440px', margin: '0 auto' }}>
        {/* Main 4-Column Grid */}
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '40px',
            marginBottom: '40px'
          }}
        >
          {/* Column 1: Brand & Solvency */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '14px' }}>
            <div className="brand-logo-badge">
              <div className="brand-logo-icon">
                <Layers size={18} color="#f0b90b" />
              </div>
              <div className="brand-logo-text-wrap">
                <span className="brand-name-novex" style={{ fontSize: '18px' }}>NOVEX</span>
                <span className="brand-name-trade" style={{ fontSize: '18px' }}>TRADE</span>
              </div>
            </div>
            <p style={{ fontSize: '13px', lineHeight: '1.6', margin: 0, color: '#848e9c' }}>
              Institutional-grade digital asset exchange engineered with microsecond deterministic matching, strict double-entry ledger architecture, and 100% verified Proof of Reserves.
            </p>
            <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginTop: '4px' }}>
              <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#0ecb81', fontWeight: 600, background: 'rgba(14, 203, 129, 0.1)', padding: '4px 10px', borderRadius: '20px', border: '1px solid rgba(14, 203, 129, 0.2)' }}>
                <ShieldCheck size={14} />
                100% Proof of Reserves
              </span>
              <span style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#f0b90b', fontWeight: 600, background: 'rgba(240, 185, 11, 0.1)', padding: '4px 10px', borderRadius: '20px', border: '1px solid rgba(240, 185, 11, 0.2)' }}>
                <Lock size={14} />
                $1B SAFU
              </span>
            </div>
          </div>

          {/* Column 2: Products */}
          <div>
            <h4 style={{ fontSize: '15px', fontWeight: 700, color: '#eaecef', margin: '0 0 16px 0' }}>Products</h4>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <li>
                <a
                  href="/trade/BTC-USDT"
                  onClick={(e) => {
                    if (onNavigateToTrade) {
                      e.preventDefault();
                      onNavigateToTrade('BTC/USDT');
                    }
                  }}
                  style={{ color: '#848e9c', textDecoration: 'none', transition: 'color 0.15s' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#f0b90b')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#848e9c')}
                >
                  Spot Trading (350+ Pairs)
                </a>
              </li>
              <li>
                <a
                  href="/invest"
                  style={{ color: '#848e9c', textDecoration: 'none', transition: 'color 0.15s', display: 'flex', alignItems: 'center', gap: '6px' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#f0b90b')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#848e9c')}
                >
                  <span>High-Yield Earn &amp; Staking</span>
                  <span style={{ background: 'rgba(240, 185, 11, 0.15)', color: '#f0b90b', fontSize: '10px', padding: '1px 5px', borderRadius: '3px', fontWeight: 700 }}>250% ROI</span>
                </a>
              </li>
              <li>
                <a
                  href="/wallet"
                  style={{ color: '#848e9c', textDecoration: 'none', transition: 'color 0.15s' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#f0b90b')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#848e9c')}
                >
                  Instant Internal Transfers (0% Fee)
                </a>
              </li>
              <li>
                <a
                  href="/p2p"
                  onClick={(e) => {
                    if (onNavigateToP2P) {
                      e.preventDefault();
                      onNavigateToP2P();
                    }
                  }}
                  style={{ color: '#848e9c', textDecoration: 'none', transition: 'color 0.15s' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#f0b90b')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#848e9c')}
                >
                  P2P Escrow Market
                </a>
              </li>
              <li>
                <a
                  href="/stock/NVDA"
                  style={{ color: '#848e9c', textDecoration: 'none', transition: 'color 0.15s' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#f0b90b')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#848e9c')}
                >
                  Stock &amp; Equity Intelligence
                </a>
              </li>
              <li>
                <a
                  href="/news"
                  style={{ color: '#848e9c', textDecoration: 'none', transition: 'color 0.15s' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#f0b90b')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#848e9c')}
                >
                  Live Financial News &amp; Feeds
                </a>
              </li>
              <li>
                <a
                  href="#/resources"
                  style={{ color: '#848e9c', textDecoration: 'none', transition: 'color 0.15s' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#f0b90b')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#848e9c')}
                >
                  Strategy Playbooks &amp; PDFs
                </a>
              </li>
            </ul>
          </div>

          {/* Column 3: Governance & Security */}
          <div>
            <h4 style={{ fontSize: '15px', fontWeight: 700, color: '#eaecef', margin: '0 0 16px 0' }}>Governance &amp; Security</h4>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <li>
                <a
                  href="/dashboard"
                  style={{ color: '#848e9c', textDecoration: 'none', transition: 'color 0.15s' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#f0b90b')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#848e9c')}
                >
                  Proof of Reserves Audit
                </a>
              </li>
              <li>
                <a
                  href="/security"
                  style={{ color: '#848e9c', textDecoration: 'none', transition: 'color 0.15s' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#f0b90b')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#848e9c')}
                >
                  SAFU Vault Custody
                </a>
              </li>
              <li>
                <a
                  href="/admin"
                  style={{ color: '#f0b90b', textDecoration: 'none', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                >
                  <span>Executive Admin Console</span>
                  <ArrowUpRight size={13} />
                </a>
              </li>
              <li>
                <a
                  href="/dashboard"
                  style={{ color: '#848e9c', textDecoration: 'none', transition: 'color 0.15s' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#f0b90b')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#848e9c')}
                >
                  Identity &amp; KYC Verification
                </a>
              </li>
              <li>
                <a
                  href="/watchlist"
                  style={{ color: '#848e9c', textDecoration: 'none', transition: 'color 0.15s' }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#f0b90b')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#848e9c')}
                >
                  Watchlist &amp; Price Alerts
                </a>
              </li>
            </ul>
          </div>

          {/* Column 4: Support & Legal */}
          <div>
            <h4 style={{ fontSize: '15px', fontWeight: 700, color: '#eaecef', margin: '0 0 16px 0' }}>Support &amp; Compliance</h4>
            <ul style={{ listStyle: 'none', padding: 0, margin: 0, display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <li>
                <span style={{ color: '#848e9c' }}>24/7 Dedicated Support</span>
              </li>
              <li>
                <span style={{ color: '#848e9c' }}>Zero-Fee Crypto Deposits</span>
              </li>
              <li>
                <span style={{ color: '#848e9c' }}>Institutional Fee Schedule (0.08% Maker)</span>
              </li>
              <li>
                <span style={{ color: '#848e9c' }}>Terms of Service &amp; Privacy Policy</span>
              </li>
              <li>
                <span style={{ color: '#848e9c' }}>Risk Warning &amp; Disclosure</span>
              </li>
            </ul>
          </div>
        </div>

        {/* Bottom Bar: Copyright & Security Attestation */}
        <div
          style={{
            borderTop: '1px solid #23272e',
            paddingTop: '24px',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            flexWrap: 'wrap',
            gap: '14px',
            fontSize: '12px',
            color: '#707a8a'
          }}
        >
          <div>
            NovexTrade Exchange &copy; 2026. All rights reserved.
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
            <span>SOC 2 Type II Certified</span>
            <span>&bull;</span>
            <span>ISO 27001 Security Standard</span>
            <span>&bull;</span>
            <span style={{ color: '#0ecb81' }}>100% Solvency Backed</span>
          </div>
        </div>
      </div>
    </footer>
  );
};
