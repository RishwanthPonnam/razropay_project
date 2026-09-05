import React, { useState, useEffect, useCallback } from 'react';
import './index.css';
import './App.css';

import Sidebar from './components/Sidebar';
import TopBar from './components/TopBar';

import OverviewPage from './pages/OverviewPage';
import RevenueEnginePage from './pages/RevenueEnginePage';
import NegotiationsPage from './pages/NegotiationsPage';
import ProductsPage from './pages/ProductsPage';
import TransactionsPage from './pages/TransactionsPage';
import ConstitutionPage from './pages/ConstitutionPage';
import AuditPage from './pages/AuditPage';
import BuyerPortal from './pages/BuyerPortal';

import { merchantsApi } from './api/merchants';
import { productsApi } from './api/products';
import { aiApi } from './api/ai';
import { paymentsApi } from './api/payments';

/* ── Page metadata map ────────────────────────────────────────── */
const PAGE_META = {
  'overview':        { title: 'Command Center',            subtitle: 'Real-time view of all AI commerce operations' },
  'revenue-engine':  { title: 'AI Revenue Engine',         subtitle: 'Intent → product matching → autonomous pricing decisions' },
  'negotiations':    { title: 'AI Negotiation Arena',       subtitle: 'Autonomous buyer ↔ merchant agent conversations' },
  'products':        { title: 'Product Catalog',            subtitle: 'Manage inventory, pricing, and negotiation eligibility' },
  'transactions':    { title: 'Transactions',               subtitle: 'Razorpay Test Mode payment pipeline' },
  'constitution':    { title: 'Economic Constitution',      subtitle: 'Define AI autonomy bounds and pricing policy' },
  'audit':           { title: 'Activity & Audit Log',       subtitle: 'Complete trace of all AI decisions and payment events' },
};

export default function App() {
  const [portal, setPortal] = useState(() => {
    return window.location.pathname.startsWith('/buyer') ? 'buyer' : 'merchant';
  });
  const [activeTab, setActiveTab] = useState('overview');
  const [merchants, setMerchants] = useState([]);
  const [selectedMerchantId, setSelectedMerchantId] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [products, setProducts] = useState([]);
  const [negotiations, setNegotiations] = useState([]);
  const [transactions, setTransactions] = useState([]);
  const [backendConnected, setBackendConnected] = useState(false);
  const [pendingTxnCount, setPendingTxnCount] = useState(0);
  const [preselectedProduct, setPreselectedProduct] = useState(null);

  // Sync with browser back/forward buttons
  useEffect(() => {
    const handlePopState = () => {
      setPortal(window.location.pathname.startsWith('/buyer') ? 'buyer' : 'merchant');
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  const switchPortal = (targetPortal) => {
    setPortal(targetPortal);
    const targetPath = targetPortal === 'buyer' ? '/buyer' : '/merchant';
    if (window.location.pathname !== targetPath) {
      window.history.pushState({}, '', targetPath);
    }
  };

  // Bootstrap: load merchants
  useEffect(() => {
    merchantsApi.list()
      .then((res) => {
        const list = Array.isArray(res) ? res : (res?.results || []);
        setMerchants(list);
        if (list.length > 0) {
          const demoMerchant = list.find(m => m.business_name === 'NovaTech Store' || m.id === 2);
          setSelectedMerchantId(demoMerchant ? demoMerchant.id : list[0].id);
        }
        setBackendConnected(true);
      })
      .catch(() => setBackendConnected(false));
  }, []);

  // When merchant changes, refresh all data in parallel
  const refreshAll = useCallback(async () => {
    if (!selectedMerchantId) return;
    try {
      const [pol, prods, negs, txns] = await Promise.allSettled([
        merchantsApi.getPolicy(selectedMerchantId),
        productsApi.listProducts(selectedMerchantId),
        aiApi.listNegotiations(selectedMerchantId),
        paymentsApi.listTransactions(selectedMerchantId),
      ]);

      if (pol.status === 'fulfilled') setPolicy(pol.value);
      if (prods.status === 'fulfilled') {
        const list = Array.isArray(prods.value) ? prods.value : (prods.value?.results || []);
        setProducts(list);
      }
      if (negs.status === 'fulfilled') {
        const list = Array.isArray(negs.value) ? negs.value : (negs.value?.results || []);
        setNegotiations(list);
      }
      if (txns.status === 'fulfilled') {
        const list = Array.isArray(txns.value) ? txns.value : (txns.value?.results || []);
        setTransactions(list);
        const pending = list.filter(t => t.status === 'ORDER_CREATED' || t.status === 'PAYMENT_PENDING').length;
        setPendingTxnCount(pending);
      }
    } catch (err) {
      console.warn('Data refresh partial failure:', err);
    }
  }, [selectedMerchantId]);

  useEffect(() => { refreshAll(); }, [refreshAll]);

  const selectedMerchant = merchants.find(m => m.id === selectedMerchantId) || null;
  const meta = PAGE_META[activeTab] || { title: activeTab };

  const handleNavigate = (tab, { productId } = {}) => {
    setActiveTab(tab);
    if (productId) setPreselectedProduct(productId);
  };

  const handleStartNegotiationWithProduct = (product) => {
    setPreselectedProduct(product.id);
    setActiveTab('negotiations');
  };

  // Page rendering — Negotiations and Transactions use full-height (no page-scroll padding)
  const fullHeightTabs = ['negotiations', 'transactions'];
  const isFullHeight = fullHeightTabs.includes(activeTab);

  function renderPage() {
    switch (activeTab) {
      case 'overview':
        return (
          <OverviewPage
            merchant={selectedMerchant}
            policy={policy}
            products={products}
            negotiations={negotiations}
            transactions={transactions}
            onNavigate={(tab) => setActiveTab(tab)}
          />
        );
      case 'revenue-engine':
        return (
          <RevenueEnginePage
            merchantId={selectedMerchantId}
            merchant={selectedMerchant}
            onStartNegotiationWithProduct={handleStartNegotiationWithProduct}
          />
        );
      case 'negotiations':
        return (
          <NegotiationsPage
            merchantId={selectedMerchantId}
            merchant={selectedMerchant}
            products={products}
            negotiations={negotiations}
            onRefresh={refreshAll}
            preselectedProductId={preselectedProduct}
          />
        );
      case 'products':
        return <ProductsPage merchantId={selectedMerchantId} merchant={selectedMerchant} />;
      case 'transactions':
        return <TransactionsPage merchantId={selectedMerchantId} merchant={selectedMerchant} />;
      case 'constitution':
        return <ConstitutionPage merchantId={selectedMerchantId} merchant={selectedMerchant} />;
      case 'audit':
        return <AuditPage merchantId={selectedMerchantId} merchant={selectedMerchant} />;
      default:
        return null;
    }
  }

  // If in Buyer Portal mode, render the consumer-facing AI assistant
  if (portal === 'buyer') {
    return (
      <BuyerPortal
        merchant={selectedMerchant}
        onSwitchToMerchant={() => switchPortal('merchant')}
      />
    );
  }

  return (
    <div className="app-shell">
      <Sidebar
        activeTab={activeTab}
        setActiveTab={(tab) => { setActiveTab(tab); setPreselectedProduct(null); }}
        pendingCount={pendingTxnCount}
      />
      <div className="main-column">
        <TopBar
          merchants={merchants}
          selectedMerchantId={selectedMerchantId}
          onSelectMerchant={(id) => { setSelectedMerchantId(id); }}
          pageTitle={meta.title}
          pageSubtitle={meta.subtitle}
          backendConnected={backendConnected}
          onSwitchToBuyer={() => switchPortal('buyer')}
        />
        {isFullHeight
          ? <div style={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>{renderPage()}</div>
          : <div className="page-scroll">{renderPage()}</div>
        }
      </div>
    </div>
  );
}
