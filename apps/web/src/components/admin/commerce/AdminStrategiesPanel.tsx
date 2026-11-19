import React, { useEffect, useRef, useState } from 'react';
import {
  FileText,
  Upload,
  Save,
  Trash2,
  Edit3,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  X,
} from 'lucide-react';

interface StrategyItem {
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
  fileExists?: boolean;
}

const EMPTY_FORM = {
  title: '',
  category: 'Momentum & Order Flow',
  difficulty: 'Intermediate',
  summary: '',
  targetSharpe: '2.20',
  recommendedHorizon: 'Intraday / Swing',
  assetSuitability: 'BTC, ETH, SOL',
  author: 'NovexTrade Quantitative Research',
  pages: 12,
  tags: 'Strategy, PDF, Institutional',
};

export const AdminStrategiesPanel: React.FC = () => {
  const [strategies, setStrategies] = useState<StrategyItem[]>([]);
  const [pricing, setPricing] = useState({ individualPdfUsd: '99.00', comboBundleUsd: '699.00' });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);

  const [editingId, setEditingId] = useState<string | null>(null);
  const [form, setForm] = useState(EMPTY_FORM);
  const [pdfBase64, setPdfBase64] = useState<string | null>(null);
  const [pdfFilename, setPdfFilename] = useState<string>('');
  const [pdfSizeLabel, setPdfSizeLabel] = useState<string>('');
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const getToken = () =>
    localStorage.getItem('novextrade_token') || localStorage.getItem('syncnode_token') || '';

  const loadStrategies = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch('/api/v1/admin/resources/strategies', {
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        throw new Error(json.error || json.detail || 'Failed to load PDF strategies');
      }
      setStrategies(json.strategies || []);
      if (json.pricing) setPricing(json.pricing);
    } catch (err: any) {
      setError(err.message || 'Unable to load strategy catalog');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadStrategies();
  }, []);

  const resetForm = () => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setPdfBase64(null);
    setPdfFilename('');
    setPdfSizeLabel('');
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const handleFileSelected = (e: React.ChangeEvent<HTMLInputElement>) => {
    setError(null);
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      setError('Only genuine PDF (.pdf) files are allowed.');
      e.target.value = '';
      return;
    }
    if (file.size > 25 * 1024 * 1024) {
      setError('PDF file exceeds maximum size of 25 MB.');
      e.target.value = '';
      return;
    }

    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === 'string' ? reader.result : '';
      setPdfBase64(result);
      setPdfFilename(file.name);
      setPdfSizeLabel(
        file.size >= 1024 * 1024
          ? `${(file.size / (1024 * 1024)).toFixed(2)} MB`
          : `${Math.max(1, Math.round(file.size / 1024))} KB`
      );
      if (!form.title.trim()) {
        const cleanTitle = file.name.replace(/\.pdf$/i, '').replace(/[-_]+/g, ' ').trim();
        setForm((prev) => ({ ...prev, title: cleanTitle }));
      }
    };
    reader.onerror = () => setError('Failed to read selected PDF file.');
    reader.readAsDataURL(file);
  };

  const handleEdit = (item: StrategyItem) => {
    setError(null);
    setSuccess(null);
    setEditingId(item.id);
    setForm({
      title: item.title,
      category: item.category,
      difficulty: item.difficulty,
      summary: item.summary,
      targetSharpe: item.targetSharpe,
      recommendedHorizon: item.recommendedHorizon,
      assetSuitability: item.assetSuitability,
      author: item.author,
      pages: item.pages || 1,
      tags: (item.tags || []).join(', '),
    });
    setPdfBase64(null);
    setPdfFilename('');
    setPdfSizeLabel('');
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setSuccess(null);

    if (!editingId && !pdfBase64) {
      setError('Please select a PDF file to upload before saving a new strategy.');
      return;
    }

    setSaving(true);
    try {
      const endpoint = editingId
        ? `/api/v1/admin/resources/strategies/${editingId}`
        : '/api/v1/admin/resources/strategies';
      const method = editingId ? 'PUT' : 'POST';

      const payload: Record<string, any> = {
        ...form,
        pages: Number(form.pages) || 1,
        tags: form.tags
          .split(',')
          .map((t) => t.trim())
          .filter(Boolean),
      };
      if (pdfBase64) {
        payload.pdfBase64 = pdfBase64;
        payload.pdfFilename = pdfFilename;
      }

      const res = await fetch(endpoint, {
        method,
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${getToken()}`,
        },
        body: JSON.stringify(payload),
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        throw new Error(json.error || json.detail || 'Failed to save strategy PDF');
      }

      setSuccess(
        editingId
          ? `Strategy "${json.strategy.title}" updated successfully.`
          : `Strategy "${json.strategy.title}" uploaded and published at $${pricing.individualPdfUsd} USD (also included in the $${pricing.comboBundleUsd} Combo).`
      );
      resetForm();
      await loadStrategies();
    } catch (err: any) {
      setError(err.message || 'Unable to save PDF strategy');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (item: StrategyItem) => {
    if (!window.confirm(`Remove strategy "${item.title}" from the catalog?`)) return;
    setBusyId(item.id);
    setError(null);
    setSuccess(null);
    try {
      const res = await fetch(`/api/v1/admin/resources/strategies/${item.id}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${getToken()}` },
      });
      const json = await res.json();
      if (!res.ok || !json.success) {
        throw new Error(json.error || 'Failed to delete strategy');
      }
      if (editingId === item.id) resetForm();
      setSuccess(`Deleted strategy "${item.title}".`);
      await loadStrategies();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px' }}>
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: '12px',
        }}
      >
        <div>
          <h2 style={{ margin: 0, fontSize: '20px', fontWeight: 800, color: '#ffffff' }}>
            Strategy PDFs &amp; Catalog Management
          </h2>
          <p style={{ margin: '4px 0 0', fontSize: '13px', color: '#848e9c' }}>
            Upload, edit, and publish institutional strategy PDF playbooks. Every strategy is automatically priced at{' '}
            <strong className="nvx-gold-text">${pricing.individualPdfUsd} USD</strong> individually and included in the{' '}
            <strong className="nvx-gold-text">${pricing.comboBundleUsd} USD</strong> Complete Combo ZIP.
          </p>
        </div>
        <button type="button" className="nvx-btn-outline" onClick={loadStrategies}>
          <RefreshCw size={14} /> Refresh
        </button>
      </div>

      {error && (
        <div className="nvx-alert nvx-alert-error">
          <AlertCircle size={16} />
          <span>{error}</span>
        </div>
      )}
      {success && (
        <div className="nvx-alert nvx-alert-success">
          <CheckCircle2 size={16} />
          <span>{success}</span>
        </div>
      )}

      {/* Upload / Edit Form */}
      <form
        onSubmit={handleSubmit}
        className="nvx-panel-card"
        style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}
      >
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: '12px',
          }}
        >
          <div className="nvx-panel-title" style={{ margin: 0 }}>
            <Upload size={16} color="#f0b90b" />
            {editingId ? 'Edit Strategy PDF' : 'Add New Strategy PDF'}
          </div>
          {editingId && (
            <button type="button" className="nvx-btn-outline" onClick={resetForm}>
              <X size={14} /> Cancel Edit
            </button>
          )}
        </div>

        {/* File Upload Dropzone */}
        <div className="nvx-wallet-address-box" style={{ marginBottom: 0 }}>
          <label className="nvx-section-label" htmlFor="nvx-pdf-upload">
            <FileText size={14} color="#f0b90b" />
            {editingId ? 'Replace PDF File (Optional)' : 'Select PDF File (Required, max 25 MB)'}
          </label>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexWrap: 'wrap' }}>
            <input
              ref={fileInputRef}
              id="nvx-pdf-upload"
              type="file"
              accept="application/pdf,.pdf"
              onChange={handleFileSelected}
              style={{ color: '#eaecef', fontSize: '13px' }}
            />
            {pdfFilename && (
              <span className="nvx-status-pill nvx-status-confirmed">
                Ready: {pdfFilename} ({pdfSizeLabel})
              </span>
            )}
          </div>
        </div>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))',
            gap: '12px',
          }}
        >
          <div>
            <label className="nvx-section-label">Strategy Title *</label>
            <input
              type="text"
              className="nvx-input"
              placeholder="e.g. Institutional Liquidity Sweep Playbook"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              required
            />
          </div>
          <div>
            <label className="nvx-section-label">Category</label>
            <input
              type="text"
              className="nvx-input"
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
            />
          </div>
          <div>
            <label className="nvx-section-label">Difficulty</label>
            <select
              className="nvx-input"
              value={form.difficulty}
              onChange={(e) => setForm({ ...form, difficulty: e.target.value })}
            >
              <option value="Beginner">Beginner</option>
              <option value="Intermediate">Intermediate</option>
              <option value="Advanced">Advanced</option>
              <option value="Institutional">Institutional</option>
            </select>
          </div>
          <div>
            <label className="nvx-section-label">Target Sharpe Ratio</label>
            <input
              type="text"
              className="nvx-input"
              value={form.targetSharpe}
              onChange={(e) => setForm({ ...form, targetSharpe: e.target.value })}
            />
          </div>
          <div>
            <label className="nvx-section-label">Recommended Horizon</label>
            <input
              type="text"
              className="nvx-input"
              value={form.recommendedHorizon}
              onChange={(e) => setForm({ ...form, recommendedHorizon: e.target.value })}
            />
          </div>
          <div>
            <label className="nvx-section-label">Asset Suitability</label>
            <input
              type="text"
              className="nvx-input"
              value={form.assetSuitability}
              onChange={(e) => setForm({ ...form, assetSuitability: e.target.value })}
            />
          </div>
          <div>
            <label className="nvx-section-label">Author / Desk</label>
            <input
              type="text"
              className="nvx-input"
              value={form.author}
              onChange={(e) => setForm({ ...form, author: e.target.value })}
            />
          </div>
          <div>
            <label className="nvx-section-label">Page Count</label>
            <input
              type="number"
              min={1}
              max={1000}
              className="nvx-input"
              value={form.pages}
              onChange={(e) => setForm({ ...form, pages: Number(e.target.value) })}
            />
          </div>
        </div>

        <div>
          <label className="nvx-section-label">Executive Summary *</label>
          <textarea
            className="nvx-input"
            rows={2}
            placeholder="Describe what traders learn and how this strategy operates..."
            value={form.summary}
            onChange={(e) => setForm({ ...form, summary: e.target.value })}
            required
          />
        </div>

        <div>
          <label className="nvx-section-label">Tags (comma-separated)</label>
          <input
            type="text"
            className="nvx-input"
            value={form.tags}
            onChange={(e) => setForm({ ...form, tags: e.target.value })}
          />
        </div>

        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          <button type="submit" className="nvx-btn-gold" disabled={saving}>
            <Save size={15} />
            {saving
              ? 'Uploading & Saving...'
              : editingId
              ? 'Save Strategy Changes'
              : 'Upload & Publish Strategy PDF'}
          </button>
          {editingId && (
            <button type="button" className="nvx-btn-outline" onClick={resetForm}>
              Cancel
            </button>
          )}
        </div>
      </form>

      {/* Catalog Table */}
      <div className="nvx-panel-card">
        <div className="nvx-panel-title">
          Published Strategy PDFs ({strategies.length})
        </div>
        {loading ? (
          <div className="nvx-empty-inline">Loading strategy PDFs...</div>
        ) : strategies.length === 0 ? (
          <div className="nvx-empty-inline">
            No PDF strategies published yet. Use the form above to upload your first strategy PDF.
          </div>
        ) : (
          <div className="nvx-table-scroll">
            <table className="nvx-table">
              <thead>
                <tr>
                  <th>Title</th>
                  <th>Category</th>
                  <th>Difficulty</th>
                  <th>PDF File</th>
                  <th>Size / Pages</th>
                  <th>Price</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {strategies.map((item) => (
                  <tr key={item.id}>
                    <td style={{ fontWeight: 700, color: '#ffffff' }}>{item.title}</td>
                    <td>{item.category}</td>
                    <td>
                      <span className="nvx-badge-subtle">{item.difficulty}</span>
                    </td>
                    <td className="nvx-mono-code">
                      {item.filename}{' '}
                      {item.fileExists && (
                        <span className="nvx-status-pill nvx-status-confirmed" style={{ marginLeft: '6px' }}>
                          OK
                        </span>
                      )}
                    </td>
                    <td>
                      {item.fileSize} · {item.pages}p
                    </td>
                    <td className="nvx-gold-text">${pricing.individualPdfUsd}</td>
                    <td>
                      <div style={{ display: 'flex', gap: '6px' }}>
                        <button
                          type="button"
                          className="nvx-btn-outline"
                          onClick={() => handleEdit(item)}
                        >
                          <Edit3 size={12} /> Edit
                        </button>
                        <button
                          type="button"
                          className="nvx-btn-outline"
                          style={{ borderColor: '#f6465d', color: '#f6465d' }}
                          disabled={busyId === item.id}
                          onClick={() => handleDelete(item)}
                        >
                          <Trash2 size={12} /> Delete
                        </button>
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
