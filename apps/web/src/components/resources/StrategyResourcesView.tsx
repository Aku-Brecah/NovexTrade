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
  FolderDown
} from 'lucide-react';

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

  // Download feedback states
  const [downloadingId, setDownloadingId] = useState<string | null>(null);
  const [toastMessage, setToastMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null);

  // Fetch catalog on mount
  const fetchResources = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/v1/resources');
      if (!res.ok) {
        throw new Error(`Failed to load resources (Status ${res.status})`);
      }
      const data = await res.json();
      if (data.success && Array.isArray(data.resources)) {
        setResources(data.resources);
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
  }, []);

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
    <div className="min-h-screen bg-[#0b0e11] text-[#eaecef] pb-24 pt-6 px-4 sm:px-6 lg:px-8">
      {/* Toast Notification */}
      {toastMessage && (
        <div className="fixed top-20 right-6 z-50 flex items-center gap-3 px-4 py-3 rounded-lg shadow-xl border animate-in fade-in slide-in-from-top-4 duration-200 backdrop-blur-md bg-[#181a20]/95 border-[#2b313a]">
          {toastMessage.type === 'success' ? (
            <CheckCircle2 className="w-5 h-5 text-[#0ecb81] shrink-0" />
          ) : (
            <AlertCircle className="w-5 h-5 text-[#f6465d] shrink-0" />
          )}
          <span className="text-sm font-medium text-[#eaecef]">{toastMessage.text}</span>
        </div>
      )}

      {/* Main Container */}
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Hero Header */}
        <div className="relative overflow-hidden rounded-2xl bg-gradient-to-r from-[#181a20] via-[#12161c] to-[#181a20] border border-[#2b313a] p-8 md:p-12 shadow-2xl">
          <div className="absolute -top-24 -right-24 w-96 h-96 bg-[#f0b90b]/5 rounded-full blur-3xl pointer-events-none" />
          <div className="absolute -bottom-24 -left-24 w-96 h-96 bg-[#0ecb81]/5 rounded-full blur-3xl pointer-events-none" />

          <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-6">
            <div className="space-y-3 max-w-3xl">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full bg-[#f0b90b]/10 border border-[#f0b90b]/30 text-[#f0b90b] text-xs font-semibold tracking-wide uppercase">
                <Sparkles className="w-3.5 h-3.5" />
                NovexTrade Quantitative Research Institute
              </div>
              <h1 className="text-3xl md:text-5xl font-extrabold tracking-tight text-[#ffffff]">
                Institutional Strategy & Research Playbooks
              </h1>
              <p className="text-sm md:text-base text-[#848e9c] leading-relaxed">
                Direct access to proprietary trading models, high-frequency microstructure algorithms,
                cross-venue arbitrage blueprints, and formal risk governance playbooks. Authored and backtested
                by NovexTrade quantitative engineering desk.
              </p>
            </div>

            {/* Quick Metrics Badge */}
            <div className="grid grid-cols-2 gap-3 shrink-0 bg-[#0b0e11]/70 border border-[#2b313a] p-4 rounded-xl">
              <div className="text-left">
                <span className="text-xs text-[#848e9c] block font-medium">Verified Playbooks</span>
                <span className="text-2xl font-bold text-[#ffffff] font-mono">{resources.length || 5}</span>
              </div>
              <div className="text-left">
                <span className="text-xs text-[#848e9c] block font-medium">Avg Target Sharpe</span>
                <span className="text-2xl font-bold text-[#0ecb81] font-mono">2.55</span>
              </div>
              <div className="text-left">
                <span className="text-xs text-[#848e9c] block font-medium">Audited Integrity</span>
                <span className="text-sm font-semibold text-[#f0b90b] flex items-center gap-1 mt-1">
                  <ShieldCheck className="w-4 h-4" /> 100% Math
                </span>
              </div>
              <div className="text-left">
                <span className="text-xs text-[#848e9c] block font-medium">Access Tier</span>
                <span className="text-sm font-semibold text-[#eaecef] mt-1 block">
                  {user ? 'Verified Member' : 'Members Only'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Filter & Search Bar */}
        <div className="bg-[#181a20] border border-[#2b313a] rounded-xl p-4 space-y-4">
          <div className="flex flex-col md:flex-row gap-4 justify-between items-center">
            {/* Search Input */}
            <div className="relative w-full md:w-96">
              <Search className="w-4 h-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-[#848e9c]" />
              <input
                type="text"
                placeholder="Search strategies, assets, models, tags..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="w-full pl-10 pr-4 py-2 bg-[#0b0e11] border border-[#2b313a] rounded-lg text-sm text-[#eaecef] placeholder-[#848e9c] focus:outline-none focus:border-[#f0b90b] transition-colors"
              />
              {searchQuery && (
                <button
                  onClick={() => setSearchQuery('')}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-xs text-[#848e9c] hover:text-[#eaecef]"
                >
                  Clear
                </button>
              )}
            </div>

            {/* Difficulty Selector */}
            <div className="flex items-center gap-2 self-start md:self-auto text-xs text-[#848e9c]">
              <span>Difficulty:</span>
              {['All', 'Intermediate', 'Advanced', 'Institutional', 'Expert'].map((diff) => (
                <button
                  key={diff}
                  onClick={() => setSelectedDifficulty(diff)}
                  className={`px-2.5 py-1 rounded-md transition-colors ${
                    selectedDifficulty === diff
                      ? 'bg-[#2b313a] text-[#ffffff] font-semibold'
                      : 'hover:bg-[#2b313a]/50 text-[#848e9c]'
                  }`}
                >
                  {diff}
                </button>
              ))}
            </div>
          </div>

          {/* Category Tabs */}
          <div className="flex items-center gap-2 overflow-x-auto no-scrollbar pt-2 border-t border-[#2b313a]/60">
            {categories.map((cat) => {
              const count = cat === 'All' ? resources.length : resources.filter((r) => r.category === cat).length;
              return (
                <button
                  key={cat}
                  onClick={() => setSelectedCategory(cat)}
                  className={`px-3.5 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap transition-all flex items-center gap-1.5 ${
                    selectedCategory === cat
                      ? 'bg-[#f0b90b] text-[#0b0e11] font-bold shadow-md'
                      : 'bg-[#0b0e11] text-[#848e9c] hover:text-[#eaecef] hover:bg-[#2b313a]/60 border border-[#2b313a]'
                  }`}
                >
                  {cat}
                  <span
                    className={`px-1.5 py-0.2 rounded-full text-[10px] ${
                      selectedCategory === cat ? 'bg-[#0b0e11]/20 text-[#0b0e11]' : 'bg-[#2b313a] text-[#848e9c]'
                    }`}
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
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {[1, 2, 3, 4, 5, 6].map((i) => (
              <div
                key={i}
                className="bg-[#181a20] border border-[#2b313a] rounded-xl p-6 space-y-4 animate-pulse"
              >
                <div className="flex justify-between items-center">
                  <div className="h-5 w-24 bg-[#2b313a] rounded" />
                  <div className="h-5 w-16 bg-[#2b313a] rounded" />
                </div>
                <div className="h-7 w-3/4 bg-[#2b313a] rounded" />
                <div className="h-14 w-full bg-[#2b313a]/50 rounded" />
                <div className="grid grid-cols-2 gap-2 pt-2">
                  <div className="h-10 bg-[#2b313a]/40 rounded" />
                  <div className="h-10 bg-[#2b313a]/40 rounded" />
                </div>
                <div className="h-10 w-full bg-[#2b313a] rounded mt-4" />
              </div>
            ))}
          </div>
        ) : error ? (
          /* Error State */
          <div className="bg-[#181a20] border border-[#f6465d]/40 rounded-xl p-8 text-center space-y-4">
            <AlertCircle className="w-12 h-12 text-[#f6465d] mx-auto" />
            <h3 className="text-lg font-bold text-[#ffffff]">Unable to Load Research Playbooks</h3>
            <p className="text-sm text-[#848e9c] max-w-md mx-auto">{error}</p>
            <button
              onClick={fetchResources}
              className="inline-flex items-center gap-2 px-4 py-2 bg-[#f0b90b] text-[#0b0e11] font-bold rounded-lg text-sm hover:brightness-110 transition-all"
            >
              <RefreshCw className="w-4 h-4" /> Retry Connection
            </button>
          </div>
        ) : filteredResources.length === 0 ? (
          /* Empty State */
          <div className="bg-[#181a20] border border-[#2b313a] rounded-xl p-12 text-center space-y-4">
            <BookOpen className="w-12 h-12 text-[#848e9c] mx-auto stroke-1" />
            <h3 className="text-lg font-bold text-[#ffffff]">No Research Playbooks Found</h3>
            <p className="text-sm text-[#848e9c] max-w-md mx-auto">
              No strategies matched your current filter criteria. Try adjusting your search query or selecting "All"
              categories.
            </p>
            <button
              onClick={() => {
                setSearchQuery('');
                setSelectedCategory('All');
                setSelectedDifficulty('All');
              }}
              className="inline-flex items-center gap-2 px-4 py-2 bg-[#2b313a] text-[#eaecef] font-medium rounded-lg text-sm hover:bg-[#363d47] transition-all"
            >
              Reset Filters
            </button>
          </div>
        ) : (
          /* Strategy Cards Grid */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredResources.map((res) => {
              const isDownloading = downloadingId === res.id;
              const difficultyColor =
                res.difficulty === 'Institutional'
                  ? 'bg-[#f0b90b]/10 text-[#f0b90b] border-[#f0b90b]/30'
                  : res.difficulty === 'Expert'
                  ? 'bg-[#f6465d]/10 text-[#f6465d] border-[#f6465d]/30'
                  : res.difficulty === 'Advanced'
                  ? 'bg-[#0ecb81]/10 text-[#0ecb81] border-[#0ecb81]/30'
                  : 'bg-[#2b313a] text-[#848e9c] border-[#2b313a]';

              return (
                <div
                  key={res.id}
                  className="group bg-[#181a20] border border-[#2b313a] hover:border-[#f0b90b]/50 rounded-xl flex flex-col justify-between p-6 transition-all duration-200 hover:shadow-xl hover:shadow-[#0b0e11]"
                >
                  {/* Card Header */}
                  <div className="space-y-4">
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-[11px] font-semibold text-[#848e9c] uppercase tracking-wider">
                        {res.category}
                      </span>
                      <span
                        className={`text-[10px] font-bold px-2 py-0.5 rounded border uppercase tracking-wider ${difficultyColor}`}
                      >
                        {res.difficulty}
                      </span>
                    </div>

                    <div className="space-y-2">
                      <h3 className="text-lg font-bold text-[#ffffff] group-hover:text-[#f0b90b] transition-colors leading-snug">
                        {res.title}
                      </h3>
                      <p className="text-xs text-[#848e9c] line-clamp-3 leading-relaxed">
                        {res.summary}
                      </p>
                    </div>

                    {/* Metrics Grid */}
                    <div className="grid grid-cols-2 gap-2 bg-[#0b0e11] border border-[#2b313a] rounded-lg p-3 text-xs">
                      <div>
                        <span className="text-[#848e9c] block text-[10px] uppercase font-medium">Target Sharpe</span>
                        <span className="font-mono font-bold text-[#0ecb81] flex items-center gap-1 mt-0.5">
                          <TrendingUp className="w-3 h-3" /> {res.targetSharpe}
                        </span>
                      </div>
                      <div>
                        <span className="text-[#848e9c] block text-[10px] uppercase font-medium">Time Horizon</span>
                        <span className="font-medium text-[#eaecef] truncate block mt-0.5">
                          {res.recommendedHorizon}
                        </span>
                      </div>
                      <div className="col-span-2 pt-1 border-t border-[#2b313a]/60">
                        <span className="text-[#848e9c] block text-[10px] uppercase font-medium">Asset Suitability</span>
                        <span className="font-medium text-[#eaecef] truncate block mt-0.5">
                          {res.assetSuitability}
                        </span>
                      </div>
                    </div>

                    {/* Tags */}
                    <div className="flex flex-wrap gap-1.5 pt-1">
                      {res.tags.map((tag) => (
                        <span
                          key={tag}
                          className="px-2 py-0.5 rounded bg-[#0b0e11] border border-[#2b313a] text-[10px] text-[#848e9c]"
                        >
                          #{tag}
                        </span>
                      ))}
                    </div>
                  </div>

                  {/* Card Footer & Action */}
                  <div className="pt-6 mt-6 border-t border-[#2b313a]/60 space-y-3">
                    <div className="flex items-center justify-between text-[11px] text-[#848e9c]">
                      <span className="flex items-center gap-1">
                        <FileText className="w-3.5 h-3.5 text-[#f0b90b]" />
                        PDF Document ({res.fileSize})
                      </span>
                      <span>{res.pages} Pages</span>
                    </div>

                    {/* Download CTA Button */}
                    {user ? (
                      <button
                        onClick={() => handleDownload(res)}
                        disabled={isDownloading}
                        className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-[#f0b90b] text-[#0b0e11] font-bold text-xs uppercase tracking-wider hover:brightness-110 active:scale-[0.99] transition-all disabled:opacity-60 disabled:cursor-not-allowed shadow-md shadow-[#f0b90b]/10"
                      >
                        {isDownloading ? (
                          <>
                            <RefreshCw className="w-4 h-4 animate-spin" />
                            Streaming PDF...
                          </>
                        ) : (
                          <>
                            <FolderDown className="w-4 h-4" />
                            Download Playbook (.pdf)
                          </>
                        )}
                      </button>
                    ) : (
                      <button
                        onClick={onOpenAuth}
                        className="w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg bg-[#2b313a] hover:bg-[#363d47] text-[#ffffff] font-semibold text-xs tracking-wide transition-all border border-[#2b313a]"
                      >
                        <Lock className="w-3.5 h-3.5 text-[#f0b90b]" />
                        Members Only — Sign In to Download
                      </button>
                    )}

                    {onNavigateToTrade && (
                      <button
                        onClick={() => onNavigateToTrade('BTC/USDT')}
                        className="w-full text-center text-[11px] text-[#848e9c] hover:text-[#f0b90b] transition-colors pt-1"
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

        {/* Security & Authenticity Notice */}
        <div className="bg-[#181a20]/60 border border-[#2b313a] rounded-xl p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-[#0ecb81]/10 text-[#0ecb81] border border-[#0ecb81]/20">
              <ShieldCheck className="w-6 h-6" />
            </div>
            <div>
              <h4 className="text-sm font-bold text-[#ffffff]">Mathematical Rigor & Verification</h4>
              <p className="text-xs text-[#848e9c]">
                All NovexTrade strategy playbooks undergo continuous execution backtesting and double-entry
                ledger accounting audit. Never risk more capital than defined in your institutional mandate.
              </p>
            </div>
          </div>
          {!user && (
            <button
              onClick={onOpenAuth}
              className="shrink-0 px-4 py-2 bg-[#f0b90b] text-[#0b0e11] font-bold rounded-lg text-xs hover:brightness-110 transition-all uppercase tracking-wide"
            >
              Create Free Account
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
export default StrategyResourcesView;
