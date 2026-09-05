import React, { useState, useCallback, useEffect, useMemo } from 'react';
import { Package, Search, Plus, Edit2, X, CheckCircle2, AlertTriangle, Filter, Check, Layers } from 'lucide-react';
import { productsApi } from '../api/products';
import LoadingSpinner from '../components/LoadingSpinner';
import ErrorBanner from '../components/ErrorBanner';
import EmptyState from '../components/EmptyState';

/* ── Add / Edit Product Modal ─────────────────────────────────── */
function ProductModal({ product, merchantId, onSave, onClose }) {
  const isEdit = Boolean(product);
  const [form, setForm] = useState({
    name: product?.name || '',
    category: product?.category || '',
    price: product?.price || '',
    inventory_quantity: product?.inventory_quantity ?? 10,
    is_negotiable: product?.is_negotiable ?? true,
    description: product?.description || '',
  });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSave = async () => {
    if (!form.name.trim() || !form.price) {
      setError('Product name and list price are required.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      if (isEdit) {
        await productsApi.updateProduct(product.id, {
          name: form.name.trim(),
          category: form.category.trim(),
          price: form.price,
          inventory_quantity: Number(form.inventory_quantity),
          is_negotiable: Boolean(form.is_negotiable),
          description: form.description.trim(),
        });
      } else {
        await productsApi.createProduct({
          ...form,
          merchant: merchantId,
          name: form.name.trim(),
          category: form.category.trim(),
          price: form.price,
          inventory_quantity: Number(form.inventory_quantity),
          is_negotiable: Boolean(form.is_negotiable),
          description: form.description.trim(),
        });
      }
      onSave();
      onClose();
    } catch (err) {
      setError(err.message || 'Failed to save product.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()} style={{ maxWidth: 520 }}>
        <div className="modal-header">
          <div className="modal-title">
            <Package size={18} color="var(--indigo)" style={{ marginRight: 8 }} />
            {isEdit ? `Edit: ${product.name}` : 'Add Product to Catalog'}
          </div>
          <button className="btn btn-ghost btn-sm" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <ErrorBanner message={error} onDismiss={() => setError(null)} />

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
          <div className="field">
            <label className="field-label">Product Name *</label>
            <input
              className="input"
              value={form.name}
              onChange={(e) => setForm(f => ({ ...f, name: e.target.value }))}
              placeholder="e.g. Mechanical Gaming Keyboard"
            />
          </div>

          <div className="grid-2">
            <div className="field">
              <label className="field-label">Category</label>
              <input
                className="input"
                value={form.category}
                onChange={(e) => setForm(f => ({ ...f, category: e.target.value }))}
                placeholder="Gaming, Audio, Accessories…"
              />
            </div>
            <div className="field">
              <label className="field-label">List Price (₹) *</label>
              <input
                className="input"
                type="number"
                value={form.price}
                onChange={(e) => setForm(f => ({ ...f, price: e.target.value }))}
                placeholder="3999"
              />
            </div>
          </div>

          <div className="grid-2">
            <div className="field">
              <label className="field-label">Inventory Quantity</label>
              <input
                className="input"
                type="number"
                value={form.inventory_quantity}
                onChange={(e) => setForm(f => ({ ...f, inventory_quantity: e.target.value }))}
              />
            </div>
            <div className="field">
              <label className="field-label">AI Negotiation Mode</label>
              <select
                className="select"
                value={String(form.is_negotiable)}
                onChange={(e) => setForm(f => ({ ...f, is_negotiable: e.target.value === 'true' }))}
              >
                <option value="true">AI Negotiable (Active)</option>
                <option value="false">Fixed Price Only</option>
              </select>
            </div>
          </div>

          <div className="field">
            <label className="field-label">Description (optional)</label>
            <textarea
              className="textarea"
              rows={2}
              value={form.description}
              onChange={(e) => setForm(f => ({ ...f, description: e.target.value }))}
              placeholder="Product features, specifications, and details…"
            />
          </div>

          <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end', marginTop: 8 }}>
            <button className="btn btn-secondary" onClick={onClose}>Cancel</button>
            <button className="btn btn-primary" onClick={handleSave} disabled={loading}>
              <CheckCircle2 size={14} /> {loading ? 'Saving…' : isEdit ? 'Update Product' : 'Add to Catalog'}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Main Products Page ───────────────────────────────────────── */
export default function ProductsPage({ merchantId }) {
  const [products, setProducts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [modalProduct, setModalProduct] = useState(null);
  const [showModal, setShowModal] = useState(false);
  const [searchQ, setSearchQ] = useState('');
  const [categoryFilter, setCategoryFilter] = useState('ALL');
  const [stockFilter, setStockFilter] = useState('ALL');

  const fetchProducts = useCallback(async () => {
    if (!merchantId) return;
    setLoading(true);
    setError(null);
    try {
      const res = await productsApi.listProducts(merchantId);
      setProducts(Array.isArray(res) ? res : (res?.results || []));
    } catch (err) {
      setError(err.message || 'Failed to load products.');
    } finally {
      setLoading(false);
    }
  }, [merchantId]);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  // Extract unique categories
  const categories = useMemo(() => {
    const set = new Set();
    products.forEach(p => {
      if (p.category && p.category.trim()) set.add(p.category.trim());
    });
    return Array.from(set).sort();
  }, [products]);

  // Filtering
  const filtered = useMemo(() => {
    return products.filter(p => {
      // Stock filter
      if (stockFilter === 'HEALTHY' && p.inventory_quantity <= 5) return false;
      if (stockFilter === 'LOW' && (p.inventory_quantity <= 0 || p.inventory_quantity > 5)) return false;
      if (stockFilter === 'OUT' && p.inventory_quantity > 0) return false;

      // Category filter
      if (categoryFilter !== 'ALL' && p.category !== categoryFilter) return false;

      // Search query
      if (searchQ) {
        const q = searchQ.toLowerCase();
        const matchName = (p.name || '').toLowerCase().includes(q);
        const matchCat = (p.category || '').toLowerCase().includes(q);
        const matchDesc = (p.description || '').toLowerCase().includes(q);
        if (!matchName && !matchCat && !matchDesc) return false;
      }

      return true;
    });
  }, [products, stockFilter, categoryFilter, searchQ]);

  const totalCount = products.length;
  const healthyCount = products.filter(p => p.inventory_quantity > 5).length;
  const lowStockCount = products.filter(p => p.inventory_quantity > 0 && p.inventory_quantity <= 5).length;
  const outOfStockCount = products.filter(p => p.inventory_quantity === 0).length;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }} className="fade-up">
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 16 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 800, color: 'var(--text-primary)', letterSpacing: '-0.4px', margin: 0 }}>
            Product Catalog
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 4, margin: 0 }}>
            Manage merchant inventory, list pricing, and AI autonomous negotiation eligibility
          </p>
        </div>
        <button
          className="btn btn-primary"
          onClick={() => { setModalProduct(null); setShowModal(true); }}
          style={{ padding: '8px 16px' }}
        >
          <Plus size={15} /> Add Product
        </button>
      </div>

      {/* KPI Status Strip */}
      <div className="grid-4">
        <div
          className="kpi-card"
          style={{
            cursor: 'pointer',
            borderColor: stockFilter === 'ALL' ? 'var(--indigo)' : 'var(--border)',
            background: stockFilter === 'ALL' ? '#F8FAFC' : '#fff'
          }}
          onClick={() => setStockFilter('ALL')}
        >
          <div className="kpi-label">Total Catalog</div>
          <div className="kpi-value">{totalCount}</div>
          <div className="kpi-desc">Products under management</div>
        </div>

        <div
          className="kpi-card"
          style={{
            cursor: 'pointer',
            borderColor: stockFilter === 'HEALTHY' ? 'var(--success)' : 'var(--border)',
            background: stockFilter === 'HEALTHY' ? 'var(--success-dim)' : '#fff'
          }}
          onClick={() => setStockFilter('HEALTHY')}
        >
          <div className="kpi-label" style={{ color: 'var(--success)' }}>Healthy Stock</div>
          <div className="kpi-value" style={{ color: 'var(--success)' }}>{healthyCount}</div>
          <div className="kpi-desc">&gt; 5 units available</div>
        </div>

        <div
          className="kpi-card"
          style={{
            cursor: 'pointer',
            borderColor: stockFilter === 'LOW' ? 'var(--warning)' : 'var(--border)',
            background: stockFilter === 'LOW' ? 'var(--warning-dim)' : '#fff'
          }}
          onClick={() => setStockFilter('LOW')}
        >
          <div className="kpi-label" style={{ color: 'var(--warning)' }}>Low Stock</div>
          <div className="kpi-value" style={{ color: lowStockCount > 0 ? 'var(--warning)' : 'var(--text-secondary)' }}>
            {lowStockCount}
          </div>
          <div className="kpi-desc">1 to 5 units remaining</div>
        </div>

        <div
          className="kpi-card"
          style={{
            cursor: 'pointer',
            borderColor: stockFilter === 'OUT' ? 'var(--danger)' : 'var(--border)',
            background: stockFilter === 'OUT' ? 'var(--danger-dim)' : '#fff'
          }}
          onClick={() => setStockFilter('OUT')}
        >
          <div className="kpi-label" style={{ color: 'var(--danger)' }}>Out of Stock</div>
          <div className="kpi-value" style={{ color: outOfStockCount > 0 ? 'var(--danger)' : 'var(--text-secondary)' }}>
            {outOfStockCount}
          </div>
          <div className="kpi-desc">Zero units in warehouse</div>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="card" style={{ padding: '14px 18px', display: 'flex', gap: 14, alignItems: 'center', flexWrap: 'wrap' }}>
        <div style={{ position: 'relative', flex: '1 1 240px' }}>
          <Search size={14} style={{ position: 'absolute', left: 12, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)', pointerEvents: 'none' }} />
          <input
            className="input"
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
            placeholder="Search products by title, category, description…"
            style={{ paddingLeft: 34, height: 38 }}
          />
        </div>

        {/* Category selector */}
        {categories.length > 0 && (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--text-tertiary)', textTransform: 'uppercase' }}>Category:</span>
            <select
              className="select"
              value={categoryFilter}
              onChange={(e) => setCategoryFilter(e.target.value)}
              style={{ height: 38, padding: '0 28px 0 10px', fontSize: 12 }}
            >
              <option value="ALL">All Categories ({categories.length})</option>
              {categories.map(c => (
                <option key={c} value={c}>{c}</option>
              ))}
            </select>
          </div>
        )}

        {/* Stock status tabs */}
        <div style={{ display: 'flex', gap: 4, background: 'var(--bg-root)', padding: 3, borderRadius: 'var(--r-md)', border: '1px solid var(--border)' }}>
          {[
            { key: 'ALL', label: 'All' },
            { key: 'HEALTHY', label: 'Healthy' },
            { key: 'LOW', label: 'Low Stock' },
            { key: 'OUT', label: 'Out of Stock' },
          ].map((tab) => (
            <button
              key={tab.key}
              onClick={() => setStockFilter(tab.key)}
              style={{
                background: stockFilter === tab.key ? '#fff' : 'transparent',
                color: stockFilter === tab.key ? 'var(--text-primary)' : 'var(--text-tertiary)',
                fontWeight: stockFilter === tab.key ? 700 : 500,
                fontSize: 12,
                padding: '6px 12px',
                borderRadius: 'var(--r-sm)',
                border: 'none',
                cursor: 'pointer',
                boxShadow: stockFilter === tab.key ? 'var(--shadow-xs)' : 'none',
                transition: 'all 0.15s ease',
              }}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <ErrorBanner message={error} onDismiss={() => setError(null)} />
      {loading && <LoadingSpinner text="Loading product catalog…" />}

      {/* Catalog Table */}
      {!loading && filtered.length > 0 ? (
        <div className="table-wrap">
          <table className="data-table">
            <thead>
              <tr>
                <th style={{ width: '38%' }}>Product</th>
                <th style={{ width: '16%' }}>Category</th>
                <th style={{ width: '14%', textAlign: 'right' }}>Price</th>
                <th style={{ width: '16%', textAlign: 'right' }}>Inventory</th>
                <th style={{ width: '12%' }}>Status</th>
                <th style={{ width: '4%' }}></th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((p) => {
                const qty = Number(p.inventory_quantity || 0);
                const isLow = qty > 0 && qty <= 5;
                const isOut = qty === 0;
                const isHealthy = qty > 5;

                return (
                  <tr key={p.id}>
                    <td>
                      <div style={{ fontWeight: 600, fontSize: 13, color: 'var(--text-primary)' }}>{p.name}</div>
                      {p.description ? (
                        <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2, lineHeight: 1.4 }}>
                          {p.description.slice(0, 75)}{p.description.length > 75 ? '…' : ''}
                        </div>
                      ) : (
                        <div style={{ fontSize: 11, color: 'var(--text-tertiary)', marginTop: 2, fontStyle: 'italic' }}>
                          SKU ID: {p.id}
                        </div>
                      )}
                    </td>
                    <td>
                      <span style={{
                        fontSize: 11,
                        fontWeight: 600,
                        color: 'var(--text-secondary)',
                        background: 'var(--bg-root)',
                        border: '1px solid var(--border)',
                        padding: '3px 9px',
                        borderRadius: 'var(--r-pill)',
                        display: 'inline-block'
                      }}>
                        {p.category || 'General'}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <span style={{ fontSize: 14, fontWeight: 800, letterSpacing: '-0.3px', color: 'var(--text-primary)' }}>
                        ₹{Number(p.price).toLocaleString()}
                      </span>
                    </td>
                    <td style={{ textAlign: 'right' }}>
                      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 2 }}>
                        <span style={{
                          fontSize: 13,
                          fontWeight: 700,
                          color: isOut ? 'var(--danger)' : isLow ? 'var(--warning)' : 'var(--text-primary)'
                        }}>
                          {qty} units
                        </span>
                        {isHealthy && (
                          <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--success)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            ● Healthy
                          </span>
                        )}
                        {isLow && (
                          <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--warning)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            ▲ Low Stock
                          </span>
                        )}
                        {isOut && (
                          <span style={{ fontSize: 10, fontWeight: 700, color: 'var(--danger)', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                            ✕ Out of Stock
                          </span>
                        )}
                      </div>
                    </td>
                    <td>
                      <span style={{
                        fontSize: 11,
                        fontWeight: 600,
                        padding: '3px 9px',
                        borderRadius: 'var(--r-pill)',
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: 4,
                        background: p.is_negotiable ? 'var(--indigo-dim)' : 'var(--bg-root)',
                        color: p.is_negotiable ? 'var(--indigo)' : 'var(--text-tertiary)',
                        border: `1px solid ${p.is_negotiable ? 'rgba(67,97,238,0.2)' : 'var(--border)'}`,
                      }}>
                        <span style={{
                          width: 5,
                          height: 5,
                          borderRadius: '50%',
                          background: p.is_negotiable ? 'var(--indigo)' : 'var(--text-tertiary)'
                        }} />
                        {p.is_negotiable ? 'AI Enabled' : 'Fixed Price'}
                      </span>
                    </td>
                    <td>
                      <button
                        className="btn btn-ghost btn-sm"
                        onClick={() => { setModalProduct(p); setShowModal(true); }}
                        title="Edit product parameters"
                      >
                        <Edit2 size={13} />
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : !loading && (
        <EmptyState
          icon={Package}
          title="No matching products found"
          description={products.length === 0
            ? "Add products to your catalog to enable autonomous pricing and buyer AI negotiations."
            : "No products matched your search or filter criteria. Try clearing your filters."}
          action={
            <button className="btn btn-primary btn-sm" onClick={() => { setModalProduct(null); setShowModal(true); }}>
              <Plus size={13} /> Add Product
            </button>
          }
        />
      )}

      {showModal && (
        <ProductModal
          product={modalProduct}
          merchantId={merchantId}
          onSave={fetchProducts}
          onClose={() => setShowModal(false)}
        />
      )}
    </div>
  );
}
