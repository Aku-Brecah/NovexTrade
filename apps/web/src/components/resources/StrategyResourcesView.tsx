import React, { useState, useEffect, useMemo } from 'react';
import {
  FileText,
  Download,
  Lock,
  Search,
  BookOpen,
  TrendingUp,
  BarChart2,
  ShieldCheck,
  Layers,
  Sparkles,
  Clock,
  ChevronRight,
  AlertCircle,
  CheckCircle2,
  ExternalLink,
  RefreshCw,
  FolderDown,
  X
} from 'lucide-react';
import { Footer } from '../Footer';
import { CheckoutModal, CheckoutTarget } from './CheckoutModal';

export interface StrategyResource {
  id: string;
  title: string;
  category: string;
  difficulty: string;
  summary: string;
  targetSharpe: string;
  recommendedHorizon: string;
  assetSuitability: string;
  filename: string;
  fileSize: string;
  pages: number;
  author: string;
  publishedDate: string;
  tags: string[];
  downloadUrl?: string;
  priceUsd?: string;
  isUnlocked?: boolean;
  sections?: [string, string[]][];
}

interface StrategyResourcesViewProps {
  user: any;
  onOpenAuth: () => void;
  onNavigateToTrade?: (symbol?: string) => void;
}

export const StrategyResourcesView: React.FC<StrategyResourcesViewProps> = ({
  user,
  onOpenAuth,
  onNavigateToTrade
}) => {
  const [resources, setResources] = useState<StrategyResource[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & Search
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedCategory, setSelectedCategory] = useState<string>('All');
  const [selectedDifficulty, setSelectedDifficulty] = useState<string>('All');

  // Download & Checkout states
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [hasComboAccess, setHasComboAccess] = useState<boolean>(false);
  const [pricing, setPricing] = useState<{ individualPdfUsd: string; comboBundleUsd: string }>({
    individualPdfUsd: '99.00',
    comboBundleUsd: '699.00',
  });
  const [checkoutTarget, setCheckoutTarget] = useState<CheckoutTarget | null>(null);
  const [toastMessage, setToastMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  const getToken = () => localStorage.getItem('novextrade_token') || localStorage.getItem('syncnode_token');

  // Fetch catalog & entitlement state on mount / user change
  const fetchResources = async () => {
    setLoading(true);
    setError(null);
    try {
      const token = getToken();
      const headers: Record<string, string> = {};
      if (token) headers.Authorization = `Bearer ${token}`;
      const res = await fetch('/api/v1/resources', { headers });
      if (!res.ok) {
        throw new Error(`Failed to load resources (Status ${res.status})`);
      }
      const data = await res.json();
      if (data.success && Array.isArray(data.resources)) {
        setResources(data.resources);
        setHasComboAccess(Boolean(data.hasComboAccess));
        if (data.pricing) {
          setPricing({
            individualPdfUsd: data.pricing.individualPdfUsd || '99.00',
            comboBundleUsd: data.pricing.comboBundleUsd || '699.00',
          });
        }
      } else {
        throw new Error(data.message || 'Malformed strategy catalog response');
      }
    } catch (err: any) {
      console.error('Error fetching strategy catalog:', err);
      setError(err.message || 'Unable to connect to NovexTrade research library.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchResources();
  }, [user]);

  const openCheckout = (target: CheckoutTarget) => {
    const token = getToken();
    if (!user || !token) {
      showToast('error', 'Please sign in to purchase and unlock strategy downloads.');
      onOpenAuth();
      return;
    }
    setCheckoutTarget(target);
  };

  const handleDownloadCombo = async () => {
    const token = getToken();
    if (!user || !token) {
      onOpenAuth();
      return;
    }
    setDownloadingId('COMBO_ZIP');
    try {
      const res = await fetch('/api/v1/resources/combo/download', {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) {
        if (res.status === 403) {
          openCheckout({
            productId: 'combo_bundle',
            productName: 'Complete Institutional Strategy Combo',
            priceUsd: pricing.comboBundleUsd,
          });
          return;
        }
        throw new Error(`Combo download failed (Status ${res.status})`);
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'novextrade-complete-strategy-combo.zip');
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(url);
      showToast('success', 'Downloaded Complete Strategy Combo (ZIP).');
    } catch (err: any) {
      showToast('error', err.message || 'Unable to download combo archive.');
    } finally {
      setDownloadingId(null);
    }
  };

  // Show auto-dismiss toast
  const showToast = (type: 'success' | 'error', text: string) => {
    setToastMessage({ type, text });
    setTimeout(() => {
      setToastMessage((prev) => (prev?.text === text ? null : prev));
    }, 4500);
  };

  // Secure download handler
  const handleDownload = async (resource: StrategyResource) => {
    if (!user) {
      showToast('error', 'Authentication required. Please sign in to download strategy playbooks.');
      onOpenAuth();
      return;
    }

    const token = localStorage.getItem('novextrade_token') || localStorage.getItem('syncnode_token');
    if (!token) {
      showToast('error', 'Active session token not found. Please log in again.');
      onOpenAuth();
      return;
    }

    setDownloadingId(resource.id);
    try {
      const downloadEndpoint = resource.downloadUrl || `/api/v1/resources/download/${resource.id}`;
      const res = await fetch(downloadEndpoint, {
        method: 'GET',
        headers: {
          Authorization: `Bearer ${token}`
        }
      });

      if (!res.ok) {
        if (res.status === 401 || res.status === 403) {
          throw new Error('Access denied: Active institutional membership required.');
        } else if (res.status === 404) {
          throw new Error('Requested strategy document is temporarily unavailable.');
        } else {
          throw new Error(`Download failed with status ${res.status}`);
        }
      }

      // Read blob and trigger native browser save
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = resource.filename || `${resource.id}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      window.URL.revokeObjectURL(url);

      showToast('success', `"${resource.title}" downloaded successfully.`);
    } catch (err: any) {
      console.error('Download error:', err);
      showToast('error', err.message || 'Failed to download strategy PDF.');
    } finally {
      setDownloadingId(null);
    }
  };

  // Extract unique categories & difficulties
  const categories = useMemo(() => {
    const set = new Set<string>();
    resources.forEach((r) => set.add(r.category));
    return ['All', ...Array.from(set)];
  }, [resources]);

  // Filtered resources
  const filteredResources = useMemo(() => {
    return resources.filter((item) => {
      const matchesCategory = selectedCategory === 'All' || item.category === selectedCategory;
      const matchesDifficulty = selectedDifficulty === 'All' || item.difficulty === selectedDifficulty;
      const q = searchQuery.toLowerCase().trim();
      const matchesSearch =
        !q ||
        item.title.toLowerCase().includes(q) ||
        item.summary.toLowerCase().includes(q) ||
        item.category.toLowerCase().includes(q) ||
        item.tags.some((t) => t.toLowerCase().includes(q)) ||
        item.assetSuitability.toLowerCase().includes(q);

      return matchesCategory && matchesDifficulty && matchesSearch;
    });
  }, [resources, selectedCategory, selectedDifficulty, searchQuery]);

  return (
    <div className="strategy-page-container">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="strategy-toast">
          {toastMessage.type === 'success' ? (
            <CheckCircle2 size={18} color="#0ecb81" style={{ flexShrink: 0 }} />
          ) : (
            <AlertCircle size={18} color="#f6465d" style={{ flexShrink: 0 }} />
          )}
          <span style={{ fontSize: '13px', fontWeight: 600, color: '#eaecef' }}>{toastMessage.text}</span>
          <button
            type="button"
            onClick={() => setToastMessage(null)}
            style={{ background: 'none', border: 'none', color: '#848e9c', cursor: 'pointer', padding: '0 2px' }}
          >
            <X size={14} />
          </button>
        </div>
      )}

      {/* Main Container */}
      <div className="strategy-page-wrapper">
        {/* Hero Header */}
        <div className="strategy-hero-card">
          <div className="strategy-hero-content">
            <div style={{ maxWidth: '720px' }}>
              <div className="strategy-hero-badge">
                <Sparkles size={13} color="#f0b90b" />
                <span>NovexTrade Quantitative Research Institute</span>
              </div>
              <h1 className="strategy-hero-title">
                Institutional Strategy &amp; Research Playbooks
              </h1>
              <p className="strategy-hero-desc">
                Direct access to proprietary trading models, high-frequency microstructure algorithms,
                cross-venue arbitrage blueprints, and formal risk governance playbooks. Authored and backtested
                by the NovexTrade quantitative engineering desk.
              </p>
            </div>

            {/* Quick Metrics KPI Badge Grid */}
            <div className="strategy-metrics-kpi-grid">
              <div>
                <span className="strategy-kpi-label">Verified Playbooks</span>
                <span className="strategy-kpi-val">{resources.length || 5}</span>
              </div>
              <div>
                <span className="strategy-kpi-label">Avg Target Sharpe</span>
                <span className="strategy-kpi-val" style={{ color: '#0ecb81' }}>2.55</span>
              </div>
              <div>
                <span className="strategy-kpi-label">Audited Integrity</span>
                <span style={{ fontSize: '13px', fontWeight: 700, color: '#f0b90b', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '4px' }}>
                  <ShieldCheck size={14} /> 100% Math
                </span>
              </div>
              <div>
                <span className="strategy-kpi-label">Access Tier</span>
                <span style={{ fontSize: '12px', fontWeight: 700, color: user ? '#0ecb81' : '#eaecef', marginTop: '4px', display: 'block' }}>
                  {user ? 'Verified Member' : 'Members Only'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Filter & Search Bar */}
        <div className="strategy-filter-bar">
          <div className="strategy-filter-top">
            {/* Search Input */}
            <div className="strategy-search-wrap">
              <Search size={15} color="#848e9c" style={{ position: 'absolute', left: '12px', top: '50%', transform: 'translateY(-50%)' }} />
              <input
                type="text"
                placeholder="Search strategies, assets, models, tags..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="strategy-search-input"
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={() => setSearchQuery('')}
                  style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', background: 'none', border: 'none', color: '#848e9c', cursor: 'pointer', fontSize: '11px' }}
                >
                  Clear
                </button>
              )}
            </div>

            {/* Difficulty Selector */}
            <div className="strategy-diff-group">
              <span style={{ fontWeight: 600 }}>Difficulty:</span>
              {['All', 'Intermediate', 'Advanced', 'Institutional', 'Expert'].map((diff) => (
                <button
                  key={diff}
                  type="button"
                  onClick={() => setSelectedDifficulty(diff)}
                  className={`strategy-diff-btn ${selectedDifficulty === diff ? 'active' : ''}`}
                >
                  {diff}
                </button>
              ))}
            </div>
          </div>

          {/* Category Tabs */}
          <div className="strategy-cat-tabs">
            {categories.map((cat) => {
              const count = cat === 'All' ? resources.length : resources.filter((r) => r.category === cat).length;
              return (
                <button
                  key={cat}
                  type="button"
                  onClick={() => setSelectedCategory(cat)}
                  className={`strategy-cat-btn ${selectedCategory === cat ? 'active' : ''}`}
                >
                  <span>{cat}</span>
                  <span
                    style={{
                      background: selectedCategory === cat ? 'rgba(11, 14, 17, 0.2)' : '#2b313a',
                      color: selectedCategory === cat ? '#0b0e11' : '#848e9c',
                      padding: '1px 6px',
                      borderRadius: '10px',
                      fontSize: '10px',
                      fontWeight: 800
                    }}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Content Section */}
        {loading ? (
          /* Skeleton Loader */
          <div className="strategy-cards-grid">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div
                key={i}
                className="strategy-card"
                style={{ opacity: 0.6 }}
              >
                <div style={{ height: '20px', width: '35%', background: '#2b313a', borderRadius: '4px', marginBottom: '14px' }} />
                <div style={{ height: '24px', width: '80%', background: '#2b313a', borderRadius: '4px', marginBottom: '10px' }} />
                <div style={{ height: '48px', width: '100%', background: '#202630', borderRadius: '6px', marginBottom: '16px' }} />
                <div style={{ height: '64px', width: '100%', background: '#0b0e11', borderRadius: '8px', marginBottom: '16px' }} />
                <div style={{ height: '40px', width: '100%', background: '#2b313a', borderRadius: '8px' }} />
              </div>
            ))}
          </div>
        ) : error ? (
          /* Error State */
          <div style={{ background: '#181a20', border: '1px solid rgba(246, 70, 93, 0.4)', borderRadius: '14px', padding: '40px 24px', textAlign: 'center' }}>
            <AlertCircle size={44} color="#f6465d" style={{ margin: '0 auto 14px' }} />
            <h3 style={{ fontSize: '18px', fontWeight: 800, color: '#ffffff', margin: '0 0 6px' }}>Unable to Load Research Playbooks</h3>
            <p style={{ fontSize: '13px', color: '#848e9c', maxWidth: '440px', margin: '0 auto 20px', lineHeight: 1.5 }}>{error}</p>
            <button
              type="button"
              onClick={fetchResources}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '10px 20px', background: '#f0b90b', color: '#0b0e11', fontWeight: 800, borderRadius: '8px', border: 'none', cursor: 'pointer' }}
            >
              <RefreshCw size={15} /> Retry Connection
            </button>
          </div>
        ) : filteredResources.length === 0 ? (
          /* Empty State */
          <div style={{ background: '#181a20', border: '1px solid #2b313a', borderRadius: '14px', padding: '48px 24px', textAlign: 'center' }}>
            <BookOpen size={48} color="#848e9c" style={{ margin: '0 auto 16px', opacity: 0.6 }} />
            <h3 style={{ fontSize: '18px', fontWeight: 800, color: '#ffffff', margin: '0 0 6px' }}>No Research Playbooks Found</h3>
            <p style={{ fontSize: '13px', color: '#848e9c', maxWidth: '440px', margin: '0 auto 20px', lineHeight: 1.5 }}>
              No strategies matched your current filter criteria. Try adjusting your search query or selecting &quot;All&quot; categories.
            </p>
            <button
              type="button"
              onClick={() => {
                setSearchQuery('');
                setSelectedCategory('All');
                setSelectedDifficulty('All');
              }}
              style={{ display: 'inline-flex', alignItems: 'center', gap: '8px', padding: '10px 20px', background: '#202630', border: '1px solid #2b313a', color: '#eaecef', fontWeight: 700, borderRadius: '8px', cursor: 'pointer' }}
            >
              Reset Filters
            </button>
          </div>
        ) : (
          /* Strategy Cards Grid */
          <div className="strategy-cards-grid">
            {filteredResources.map((res) => {
              const isDownloading = downloadingId === res.id;
              const diffClass =
                res.difficulty.toLowerCase() === 'institutional'
                  ? 'institutional'
                  : res.difficulty.toLowerCase() === 'expert'
                  ? 'expert'
                  : res.difficulty.toLowerCase() === 'advanced'
                  ? 'advanced'
                  : 'intermediate';

              return (
                <div key={res.id} className="strategy-card">
                  {/* Card Content Top */}
                  <div>
                    <div className="strategy-card-header">
                      <span className="strategy-cat-tag">{res.category}</span>
                      <span className={`strategy-diff-tag ${diffClass}`}>{res.difficulty}</span>
                    </div>

                    <h3 className="strategy-card-title">{res.title}</h3>
                    <p className="strategy-card-summary">{res.summary}</p>

                    {/* Quantitative Metrics Box */}
                    <div className="strategy-metrics-box">
                      <div className="strategy-metric-item">
                        <span className="strategy-metric-label">Target Sharpe</span>
                        <span className="strategy-metric-val" style={{ color: '#0ecb81', fontFamily: 'monospace', display: 'flex', alignItems: 'center', gap: '4px' }}>
                          <TrendingUp size={12} /> {res.targetSharpe}
                        </span>
                      </div>
                      <div className="strategy-metric-item">
                        <span className="strategy-metric-label">Time Horizon</span>
                        <span className="strategy-metric-val">{res.recommendedHorizon}</span>
                      </div>
                      <div className="strategy-metric-item" style={{ gridColumn: 'span 2', paddingTop: '6px', borderTop: '1px solid #1f2535' }}>
                        <span className="strategy-metric-label">Asset Suitability</span>
                        <span className="strategy-metric-val">{res.assetSuitability}</span>
                      </div>
                    </div>

                    {/* Tag Pills */}
                    <div className="strategy-tags-wrap">
                      {res.tags.map((tag) => (
                        <span key={tag} className="strategy-tag">
                          #{tag}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Card Footer Actions */}
                  <div className="strategy-card-footer">
                    <div className="strategy-doc-meta">
                      <span style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
                        <FileText size={13} color="#f0b90b" />
                        PDF Document ({res.fileSize})
                      </span>
                      <span>{res.pages} Pages</span>
                    </div>

                    {/* Download or Purchase CTA Button */}
                    {user && res.isUnlocked ? (
                      <button
                        type="button"
                        onClick={() => handleDownload(res)}
                        disabled={isDownloading}
                        className="strategy-download-btn"
                        style={{ background: '#0ecb81', color: '#0b0e11', borderColor: '#0ecb81' }}
                      >
                        {isDownloading ? (
                          <>
                            <RefreshCw size={14} style={{ animation: 'spin 0.8s linear infinite' }} />
                            <span>Streaming PDF...</span>
                          </>
                        ) : (
                          <>
                            <FolderDown size={14} />
                            <span>Unlocked — Download PDF</span>
                          </>
                        )}
                      </button>
                    ) : (
                      <button
                        type="button"
                        onClick={() =>
                          openCheckout({
                            productId: 'individual_pdf',
                            productName: 'Individual Strategy PDF Download',
                            priceUsd: res.priceUsd || pricing.individualPdfUsd,
                            resourceId: res.id,
                            resourceTitle: res.title,
                          })
                        }
                        className="strategy-download-btn"
                      >
                        <Lock size={14} />
                        <span>Unlock PDF — ${res.priceUsd || pricing.individualPdfUsd} USD</span>
                      </button>
                    )}

                    {onNavigateToTrade && (
                      <button
                        type="button"
                        onClick={() => onNavigateToTrade('BTC/USDT')}
                        className="strategy-terminal-link"
                      >
                        Trade Pair on Terminal →
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {/* Complete Combo Bundle Banner ($699 USD) */}
        <div className="nvx-combo-banner">
          <div>
            <div className="nvx-modal-kicker">ALL-ACCESS INSTITUTIONAL BUNDLE</div>
            <h3 style={{ margin: '4px 0 6px', fontSize: '20px', fontWeight: 800, color: '#ffffff' }}>
              Complete Strategy Combo Download — ${pricing.comboBundleUsd} USD
            </h3>
            <p style={{ margin: 0, fontSize: '13px', color: '#848e9c', maxWidth: '640px', lineHeight: 1.5 }}>
              Unlock all 5 institutional strategy playbooks individually plus a single bundled ZIP archive. Pay securely by Card (Visa/Mastercard) or verified on-chain Cryptocurrency.
            </p>
          </div>
          <div>
            {hasComboAccess ? (
              <button
                type="button"
                className="nvx-btn-gold"
                style={{ background: '#0ecb81', borderColor: '#0ecb81' }}
                disabled={downloadingId === 'COMBO_ZIP'}
                onClick={handleDownloadCombo}
              >
                <Download size={16} />
                {downloadingId === 'COMBO_ZIP' ? 'Preparing ZIP...' : 'Download Complete Combo (ZIP)'}
              </button>
            ) : (
              <button
                type="button"
                className="nvx-btn-gold"
                onClick={() =>
                  openCheckout({
                    productId: 'combo_bundle',
                    productName: 'Complete Institutional Strategy Combo',
                    priceUsd: pricing.comboBundleUsd,
                  })
                }
              >
                <Sparkles size={16} /> Buy Complete Combo — ${pricing.comboBundleUsd} USD
              </button>
            )}
          </div>
        </div>

        {/* Security & Mathematical Rigor Notice */}
        <div className="strategy-authenticity-card">
          <div style={{ display: 'flex', alignItems: 'center', gap: '14px' }}>
            <div style={{ width: '42px', height: '42px', borderRadius: '10px', background: 'rgba(14, 203, 129, 0.12)', border: '1px solid rgba(14, 203, 129, 0.25)', display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#0ecb81', flexShrink: 0 }}>
              <ShieldCheck size={22} />
            </div>
            <div>
              <h4 style={{ fontSize: '14px', fontWeight: 800, color: '#ffffff', margin: '0 0 3px' }}>Mathematical Rigor &amp; Continuous Backtesting</h4>
              <p style={{ fontSize: '12px', color: '#848e9c', margin: 0, lineHeight: 1.5 }}>
                All NovexTrade strategy playbooks undergo continuous execution backtesting and double-entry ledger accounting audit. Never risk more capital than defined in your institutional mandate.
              </p>
            </div>
          </div>
          {!user && (
            <button
              type="button"
              onClick={onOpenAuth}
              style={{
                padding: '9px 18px',
                borderRadius: '8px',
                background: '#f0b90b',
                color: '#0b0e11',
                fontWeight: 800,
                fontSize: '12px',
                border: '1px solid #f0b90b',
                cursor: 'pointer',
                whiteSpace: 'nowrap'
              }}
            >
              Create Free Account
            </button>
          )}
        </div>

        {/* Footer */}
        <Footer onNavigateToTrade={onNavigateToTrade} />
      </div>

      {checkoutTarget && getToken() && (
        <CheckoutModal
          target={checkoutTarget}
          token={getToken()!}
          onClose={() => setCheckoutTarget(null)}
          onPaymentSuccess={() => {
            fetchResources();
            showToast('success', 'Payment verified! Your download entitlement is now active.');
          }}
          onDownloadUnlocked={(resourceId, isCombo) => {
            setCheckoutTarget(null);
            if (isCombo) {
              handleDownloadCombo();
            } else if (resourceId) {
              const found = resources.find((r) => r.id === resourceId);
              if (found) handleDownload(found);
            }
          }}
        />
      )}
    </div>
  );
};

export default StrategyResourcesView;
