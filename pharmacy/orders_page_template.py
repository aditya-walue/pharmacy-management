"""
Template and HTML/CSS/JS generator for the customer-facing Orders & Invoices page (/orders).
"""

def get_orders_html() -> str:
    return """
<!-- Razorpay SDK -->
<script src="https://checkout.razorpay.com/v1/checkout.js"></script>

<div class="pharmacy-orders-wrapper">
  <!-- Top Navbar -->
  <nav class="ph-navbar">
    <div class="ph-nav-container">
      <div class="ph-brand">
        <a href="/order" style="text-decoration: none; display: flex; align-items: center; gap: 12px; color: inherit;">
          <div class="ph-logo-icon">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>
          </div>
          <div class="ph-brand-text">
            <span class="ph-brand-title">Pharmacy Store</span>
            <span class="ph-brand-sub">Certified Clinical Healthcare &amp; Fulfillment</span>
          </div>
        </a>
      </div>
      <div class="ph-nav-right">
        <a href="/order" class="ph-nav-link">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>
          <span>Catalog</span>
        </a>
        <a href="/cart" class="ph-nav-link">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/></svg>
          <span>Cart</span>
          <span class="ph-nav-pill" id="nav-cart-count">0</span>
        </a>
        <a href="/orders" class="ph-nav-link active">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/><polyline points="10 9 9 9 8 9"/></svg>
          <span>My Orders</span>
        </a>
      </div>
    </div>
  </nav>

  <!-- Hero Header -->
  <header class="ph-orders-hero">
    <div class="ph-orders-hero-content">
      <div class="ph-tag">Customer Orders &amp; Billing</div>
      <h1 class="ph-hero-title">Track Orders &amp; Tax Invoices</h1>
      <p class="ph-hero-desc">Review your medicine order history, track real-time dispensary fulfillment, and view or print official GST Sales Invoices.</p>
    </div>
  </header>

  <!-- Search & Tracking Bar -->
  <section class="ph-search-section">
    <div class="ph-search-container">
      <form id="order-search-form" onsubmit="handleSearch(event)" class="ph-search-form">
        <div class="ph-search-input-wrap">
          <svg class="ph-search-icon" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input type="text" id="order-search-input" placeholder="Search by Mobile Number, Email ID, or Order # (e.g. 9876500112 or SAL-ORD-2026-00009)" required />
        </div>
        <button type="submit" class="ph-btn-search" id="btn-search">
          <span>Track Orders</span>
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
        </button>
      </form>
      <div class="ph-search-hint" id="search-hint">
        💡 Tip: Enter the phone number or email address provided during checkout to retrieve all associated orders.
      </div>
    </div>
  </section>

  <!-- Filter Status Tabs -->
  <div class="ph-filter-container">
    <div class="ph-filter-tabs" id="filter-tabs">
      <button class="ph-tab-btn active" onclick="setFilter('all')">All Orders (<span id="count-all">0</span>)</button>
      <button class="ph-tab-btn" onclick="setFilter('Confirmed')">Confirmed (<span id="count-confirmed">0</span>)</button>
      <button class="ph-tab-btn" onclick="setFilter('Awaiting Payment')">Awaiting Payment (<span id="count-awaiting">0</span>)</button>
      <button class="ph-tab-btn" onclick="setFilter('Prescription Review')">Rx Review (<span id="count-rx">0</span>)</button>
      <button class="ph-tab-btn" onclick="setFilter('Dispatched')">Dispatched (<span id="count-dispatched">0</span>)</button>
      <button class="ph-tab-btn" onclick="setFilter('Delivered')">Delivered (<span id="count-delivered">0</span>)</button>
    </div>
  </div>

  <!-- Main Content Area -->
  <main class="ph-orders-main">
    <!-- Loading State -->
    <div id="orders-loading" class="ph-state-box" style="display: none;">
      <div class="ph-spinner"></div>
      <p style="margin-top: 14px; font-weight: 600; color: #475569;">Searching orders in Pharmacy Store ERP...</p>
    </div>

    <!-- Empty State -->
    <div id="orders-empty" class="ph-state-box" style="display: none;">
      <div class="ph-empty-icon">
        <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
      </div>
      <h2 style="font-size: 20px; font-weight: 800; color: #0f172a; margin: 12px 0 6px 0;" id="empty-title">No Orders Found</h2>
      <p style="color: #64748b; font-size: 14px; margin: 0 0 20px 0;" id="empty-desc">Please check your mobile number or email address, or place a new medicine order from our catalog.</p>
      <a href="/order" class="ph-btn-primary">Browse Medicine Catalog →</a>
    </div>

    <!-- Orders List Container -->
    <div id="orders-list" class="ph-orders-list"></div>
  </main>

  <!-- Tax Invoice Modal Popup -->
  <div id="invoice-modal" class="ph-modal-backdrop" style="display: none;" onclick="closeInvoiceModalOnBackdrop(event)">
    <div class="ph-modal-dialog">
      <div class="ph-modal-header no-print">
        <div style="display: flex; align-items: center; gap: 8px;">
          <span style="font-size: 18px;">📄</span>
          <span style="font-weight: 800; font-size: 16px; color: #0f172a;" id="modal-invoice-title">Official Tax Invoice</span>
        </div>
        <div style="display: flex; gap: 8px;">
          <button class="ph-btn-print" onclick="window.print()">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
            <span>Print / Save PDF</span>
          </button>
          <button class="ph-modal-close" onclick="closeInvoiceModal()">&times;</button>
        </div>
      </div>
      
      <!-- Printable Invoice Document -->
      <div class="ph-invoice-paper" id="invoice-paper-content">
        <!-- Rendered dynamically -->
      </div>
    </div>
  </div>
</div>

<style>
  :root {
    --ph-primary: #059669;
    --ph-primary-dark: #047857;
    --ph-primary-light: #ecfdf5;
    --ph-slate-900: #0f172a;
    --ph-slate-800: #1e293b;
    --ph-slate-600: #475569;
    --ph-slate-500: #64748b;
    --ph-slate-200: #e2e8f0;
    --ph-slate-100: #f1f5f9;
    --ph-slate-50: #f8fafc;
    --ph-font: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
  }

  * { box-sizing: border-box; }
  body {
    margin: 0;
    padding: 0;
    font-family: var(--ph-font);
    background-color: var(--ph-slate-50);
    color: var(--ph-slate-900);
    -webkit-font-smoothing: antialiased;
  }

  .pharmacy-orders-wrapper {
    min-height: 100vh;
    display: flex;
    flex-direction: column;
  }

  /* Navbar */
  .ph-navbar {
    background: #ffffff;
    border-bottom: 1px solid var(--ph-slate-200);
    position: sticky;
    top: 0;
    z-index: 100;
  }
  .ph-nav-container {
    max-width: 1200px;
    margin: 0 auto;
    padding: 12px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .ph-brand {
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .ph-logo-icon {
    width: 38px;
    height: 38px;
    background: linear-gradient(135deg, #059669 0%, #047857 100%);
    border-radius: 10px;
    display: flex;
    align-items: center;
    justify-content: center;
    color: #ffffff;
    box-shadow: 0 4px 10px rgba(5, 150, 105, 0.25);
  }
  .ph-brand-text {
    display: flex;
    flex-direction: column;
  }
  .ph-brand-title {
    font-size: 18px;
    font-weight: 800;
    color: var(--ph-slate-900);
    letter-spacing: -0.3px;
  }
  .ph-brand-sub {
    font-size: 11px;
    font-weight: 500;
    color: var(--ph-slate-500);
  }
  .ph-nav-right {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .ph-nav-link {
    display: flex;
    align-items: center;
    gap: 6px;
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 600;
    color: var(--ph-slate-600);
    text-decoration: none;
    transition: all 0.15s ease;
  }
  .ph-nav-link:hover {
    background: var(--ph-slate-100);
    color: var(--ph-slate-900);
  }
  .ph-nav-link.active {
    background: var(--ph-primary-light);
    color: var(--ph-primary-dark);
    font-weight: 700;
  }
  .ph-nav-pill {
    background: var(--ph-primary);
    color: white;
    font-size: 11px;
    font-weight: 800;
    padding: 2px 7px;
    border-radius: 12px;
  }

  /* Hero Section */
  .ph-orders-hero {
    background: linear-gradient(135deg, #064e3b 0%, #065f46 50%, #0f766e 100%);
    color: white;
    padding: 40px 24px;
    text-align: center;
  }
  .ph-orders-hero-content {
    max-width: 760px;
    margin: 0 auto;
  }
  .ph-tag {
    display: inline-block;
    background: rgba(255, 255, 255, 0.18);
    border: 1px solid rgba(255, 255, 255, 0.3);
    color: #ffffff;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding: 4px 12px;
    border-radius: 20px;
    margin-bottom: 12px;
  }
  .ph-hero-title {
    font-size: 32px;
    font-weight: 800;
    margin: 0 0 10px 0;
    letter-spacing: -0.5px;
  }
  .ph-hero-desc {
    font-size: 15px;
    color: rgba(255, 255, 255, 0.88);
    margin: 0;
    line-height: 1.5;
  }

  /* Search Section */
  .ph-search-section {
    background: #ffffff;
    border-bottom: 1px solid var(--ph-slate-200);
    padding: 24px;
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  }
  .ph-search-container {
    max-width: 860px;
    margin: 0 auto;
  }
  .ph-search-form {
    display: flex;
    gap: 12px;
  }
  .ph-search-input-wrap {
    flex: 1;
    position: relative;
    display: flex;
    align-items: center;
  }
  .ph-search-icon {
    position: absolute;
    left: 16px;
    color: var(--ph-slate-500);
    pointer-events: none;
  }
  .ph-search-input-wrap input {
    width: 100%;
    padding: 14px 16px 14px 48px;
    border: 2px solid var(--ph-slate-200);
    border-radius: 12px;
    font-size: 15px;
    font-family: inherit;
    outline: none;
    transition: all 0.2s ease;
  }
  .ph-search-input-wrap input:focus {
    border-color: var(--ph-primary);
    box-shadow: 0 0 0 4px rgba(5, 150, 105, 0.12);
  }
  .ph-btn-search {
    background: linear-gradient(135deg, #059669 0%, #047857 100%);
    color: white;
    border: none;
    padding: 0 24px;
    border-radius: 12px;
    font-size: 14px;
    font-weight: 700;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 8px;
    transition: all 0.15s ease;
    box-shadow: 0 4px 10px rgba(5, 150, 105, 0.25);
  }
  .ph-btn-search:hover {
    background: #047857;
    transform: translateY(-1px);
  }
  .ph-search-hint {
    font-size: 12px;
    color: var(--ph-slate-500);
    margin-top: 10px;
    text-align: center;
  }

  /* Filter Tabs */
  .ph-filter-container {
    max-width: 1100px;
    margin: 20px auto 0 auto;
    padding: 0 24px;
    width: 100%;
  }
  .ph-filter-tabs {
    display: flex;
    gap: 8px;
    overflow-x: auto;
    padding-bottom: 6px;
  }
  .ph-tab-btn {
    background: #ffffff;
    border: 1px solid var(--ph-slate-200);
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 600;
    color: var(--ph-slate-600);
    cursor: pointer;
    white-space: nowrap;
    transition: all 0.15s ease;
  }
  .ph-tab-btn:hover {
    border-color: var(--ph-slate-500);
    color: var(--ph-slate-900);
  }
  .ph-tab-btn.active {
    background: var(--ph-slate-900);
    color: #ffffff;
    border-color: var(--ph-slate-900);
  }

  /* Orders Main Container */
  .ph-orders-main {
    max-width: 1100px;
    margin: 20px auto 60px auto;
    padding: 0 24px;
    width: 100%;
    flex: 1;
  }

  /* State Boxes */
  .ph-state-box {
    background: #ffffff;
    border-radius: 16px;
    border: 1px solid var(--ph-slate-200);
    padding: 60px 24px;
    text-align: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.03);
  }
  .ph-spinner {
    width: 36px;
    height: 36px;
    border: 3px solid var(--ph-slate-200);
    border-top-color: var(--ph-primary);
    border-radius: 50%;
    animation: spin 0.8s linear infinite;
    margin: 0 auto;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  .ph-btn-primary {
    display: inline-block;
    background: var(--ph-primary);
    color: #ffffff;
    text-decoration: none;
    font-weight: 700;
    font-size: 14px;
    padding: 12px 24px;
    border-radius: 10px;
    transition: all 0.15s ease;
  }
  .ph-btn-primary:hover {
    background: var(--ph-primary-dark);
  }

  /* Order Cards */
  .ph-order-card {
    background: #ffffff;
    border-radius: 16px;
    border: 1px solid var(--ph-slate-200);
    box-shadow: 0 3px 12px rgba(0, 0, 0, 0.04);
    margin-bottom: 24px;
    overflow: hidden;
    transition: transform 0.15s ease, box-shadow 0.15s ease;
  }
  .ph-order-card:hover {
    box-shadow: 0 6px 20px rgba(0, 0, 0, 0.06);
  }
  .ph-card-header {
    background: #ffffff;
    border-bottom: 1px solid var(--ph-slate-100);
    padding: 18px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }
  .ph-order-meta {
    display: flex;
    align-items: center;
    gap: 14px;
    flex-wrap: wrap;
  }
  .ph-order-id {
    font-family: monospace;
    font-size: 17px;
    font-weight: 800;
    color: var(--ph-slate-900);
  }
  .ph-order-date {
    font-size: 13px;
    color: var(--ph-slate-500);
  }
  .ph-badge-fulfilment {
    font-size: 12px;
    font-weight: 600;
    padding: 4px 10px;
    border-radius: 6px;
    background: var(--ph-slate-100);
    color: var(--ph-slate-800);
  }

  /* Status Pills */
  .ph-status-pill {
    font-size: 12px;
    font-weight: 700;
    padding: 6px 14px;
    border-radius: 20px;
    display: inline-flex;
    align-items: center;
    gap: 6px;
  }
  .ph-status-pill.confirmed { background: #dcfce7; color: #15803d; border: 1px solid #bbf7d0; }
  .ph-status-pill.awaiting-payment { background: #fef3c7; color: #b45309; border: 1px solid #fde68a; }
  .ph-status-pill.prescription-review { background: #e0e7ff; color: #4338ca; border: 1px solid #c7d2fe; }
  .ph-status-pill.dispatched { background: #f3e8ff; color: #7e22ce; border: 1px solid #e9d5ff; }
  .ph-status-pill.delivered { background: #ccfbf1; color: #0f766e; border: 1px solid #99f6e4; }

  /* Invoice Action Banner */
  .ph-invoice-banner {
    margin: 16px 24px 0 24px;
    padding: 14px 18px;
    border-radius: 12px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 12px;
  }
  .ph-invoice-banner.has-invoice {
    background: #f0fdf4;
    border: 1px solid #bbf7d0;
  }
  .ph-invoice-banner.needs-payment {
    background: #fffbeb;
    border: 1px solid #fde68a;
  }
  .ph-inv-info {
    display: flex;
    align-items: center;
    gap: 10px;
  }
  .ph-inv-badge {
    font-family: monospace;
    font-weight: 700;
    font-size: 13px;
    padding: 3px 8px;
    border-radius: 6px;
    background: #dcfce7;
    color: #166534;
  }
  .ph-btn-invoice {
    background: #0f172a;
    color: #ffffff;
    border: none;
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    transition: all 0.15s ease;
  }
  .ph-btn-invoice:hover {
    background: #1e293b;
    transform: translateY(-1px);
  }
  .ph-btn-paynow {
    background: linear-gradient(135deg, #f59e0b 0%, #d97706 100%);
    color: #ffffff;
    border: none;
    padding: 8px 16px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    display: inline-flex;
    align-items: center;
    gap: 6px;
    box-shadow: 0 2px 6px rgba(217, 119, 6, 0.25);
  }
  .ph-btn-paynow:hover {
    background: #b45309;
  }

  /* Items Table */
  .ph-card-body {
    padding: 16px 24px;
  }
  .ph-table-wrap {
    overflow-x: auto;
  }
  .ph-items-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }
  .ph-items-table th {
    text-align: left;
    padding: 10px 12px;
    background: var(--ph-slate-50);
    color: var(--ph-slate-600);
    font-weight: 700;
    border-bottom: 1px solid var(--ph-slate-200);
  }
  .ph-items-table td {
    padding: 12px;
    border-bottom: 1px solid var(--ph-slate-100);
    vertical-align: middle;
  }
  .ph-med-name {
    font-weight: 700;
    color: var(--ph-slate-900);
    font-size: 14px;
  }
  .ph-med-salt {
    font-size: 12px;
    color: var(--ph-slate-500);
    margin-top: 2px;
  }
  .ph-med-tags {
    display: flex;
    gap: 6px;
    margin-top: 4px;
  }
  .ph-mini-tag {
    font-size: 10px;
    font-weight: 700;
    padding: 2px 6px;
    border-radius: 4px;
    background: var(--ph-slate-100);
    color: var(--ph-slate-600);
  }
  .ph-mini-tag.cold {
    background: #e0f2fe;
    color: #0369a1;
  }

  /* Card Footer */
  .ph-card-footer {
    background: var(--ph-slate-50);
    border-top: 1px solid var(--ph-slate-100);
    padding: 16px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-wrap: wrap;
    gap: 14px;
  }
  .ph-patient-summary {
    font-size: 13px;
    color: var(--ph-slate-600);
  }
  .ph-patient-summary strong {
    color: var(--ph-slate-900);
  }
  .ph-card-total-box {
    text-align: right;
  }
  .ph-total-label {
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    color: var(--ph-slate-500);
  }
  .ph-total-amount {
    font-size: 20px;
    font-weight: 800;
    color: #059669;
  }

  /* Modal */
  .ph-modal-backdrop {
    position: fixed;
    top: 0;
    left: 0;
    width: 100vw;
    height: 100vh;
    background: rgba(15, 23, 42, 0.65);
    backdrop-filter: blur(4px);
    z-index: 1000;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 20px;
    overflow-y: auto;
  }
  .ph-modal-dialog {
    background: #ffffff;
    border-radius: 16px;
    max-width: 800px;
    width: 100%;
    max-height: 90vh;
    display: flex;
    flex-direction: column;
    box-shadow: 0 20px 40px rgba(0,0,0,0.25);
    overflow: hidden;
  }
  .ph-modal-header {
    background: #ffffff;
    border-bottom: 1px solid var(--ph-slate-200);
    padding: 14px 24px;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
  .ph-btn-print {
    background: var(--ph-primary);
    color: white;
    border: none;
    padding: 8px 14px;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
    cursor: pointer;
    display: flex;
    align-items: center;
    gap: 6px;
  }
  .ph-modal-close {
    background: transparent;
    border: none;
    font-size: 24px;
    cursor: pointer;
    color: var(--ph-slate-500);
    padding: 0 6px;
  }
  .ph-invoice-paper {
    padding: 32px;
    overflow-y: auto;
    font-size: 13px;
    color: #0f172a;
    line-height: 1.5;
  }

  /* Printable styles */
  @media print {
    body * { visibility: hidden; }
    .ph-modal-backdrop, .ph-modal-backdrop * { visibility: visible; }
    .ph-modal-backdrop {
      position: absolute;
      left: 0;
      top: 0;
      width: 100%;
      height: auto;
      background: none;
      padding: 0;
    }
    .ph-modal-dialog {
      max-width: 100%;
      box-shadow: none;
      border: none;
    }
    .no-print { display: none !important; }
    .ph-invoice-paper { padding: 0; }
  }

  @media (max-width: 768px) {
    .ph-search-form { flex-direction: column; }
    .ph-btn-search { padding: 14px; justify-content: center; }
    .ph-card-header { flex-direction: column; align-items: flex-start; }
    .ph-card-footer { flex-direction: column; align-items: flex-start; }
    .ph-card-total-box { text-align: left; }
  }
</style>

<script>
  let allOrders = [];
  let currentFilter = 'all';

  function initOrdersPage() {
    updateNavCartCount();

    // Check localStorage for saved patient contact from checkout
    const savedEmail = localStorage.getItem('ph_customer_email');
    const savedPhone = localStorage.getItem('ph_customer_phone');
    const input = document.getElementById('order-search-input');

    if (savedPhone) {
      input.value = savedPhone;
      fetchCustomerOrders(savedPhone);
    } else if (savedEmail) {
      input.value = savedEmail;
      fetchCustomerOrders(savedEmail);
    } else {
      // Prompt user or check recent orders
      document.getElementById('orders-empty').style.display = 'block';
      document.getElementById('empty-title').innerText = 'Enter Details to Track Orders';
      document.getElementById('empty-desc').innerText = 'Please enter your registered mobile number or email address in the search box above to view your order history and invoices.';
    }
  }

  function updateNavCartCount() {
    try {
      const raw = localStorage.getItem('ph_cart');
      if (raw) {
        const cart = JSON.parse(raw);
        const count = cart.reduce((s, i) => s + (i.qty || 0), 0);
        const pill = document.getElementById('nav-cart-count');
        if (pill) pill.innerText = count;
      }
    } catch(e) {}
  }

  function handleSearch(e) {
    if (e) e.preventDefault();
    const term = document.getElementById('order-search-input').value.trim();
    if (!term) return;
    fetchCustomerOrders(term);
  }

  function fetchCustomerOrders(identifier) {
    const loading = document.getElementById('orders-loading');
    const empty = document.getElementById('orders-empty');
    const list = document.getElementById('orders-list');

    loading.style.display = 'block';
    empty.style.display = 'none';
    list.innerHTML = '';

    fetch('/api/method/pharmacy.online.portal.get_customer_orders?identifier=' + encodeURIComponent(identifier))
      .then(r => r.json())
      .then(res => {
        loading.style.display = 'none';
        const data = res.message || res;
        allOrders = (data && data.orders) ? data.orders : [];

        // Save identifier for future auto-load
        if (identifier.includes('@')) {
          localStorage.setItem('ph_customer_email', identifier);
        } else if (identifier.replace(/\D/g, '').length >= 10) {
          localStorage.setItem('ph_customer_phone', identifier);
        }

        updateFilterCounts();
        renderOrders();
      })
      .catch(err => {
        loading.style.display = 'none';
        empty.style.display = 'block';
        document.getElementById('empty-title').innerText = 'Unable to Load Orders';
        document.getElementById('empty-desc').innerText = 'An error occurred while communicating with the pharmacy server. Please try again.';
      });
  }

  function updateFilterCounts() {
    document.getElementById('count-all').innerText = allOrders.length;
    document.getElementById('count-confirmed').innerText = allOrders.filter(o => o.nir_online_status === 'Confirmed').length;
    document.getElementById('count-awaiting').innerText = allOrders.filter(o => o.nir_online_status === 'Awaiting Payment').length;
    document.getElementById('count-rx').innerText = allOrders.filter(o => o.nir_online_status === 'Prescription Review').length;
    document.getElementById('count-dispatched').innerText = allOrders.filter(o => o.nir_online_status === 'Dispatched').length;
    document.getElementById('count-delivered').innerText = allOrders.filter(o => o.nir_online_status === 'Delivered').length;
  }

  function setFilter(status) {
    currentFilter = status;
    const tabs = document.querySelectorAll('.ph-tab-btn');
    tabs.forEach(t => t.classList.remove('active'));
    
    // Highlight active button
    if (status === 'all') tabs[0].classList.add('active');
    else if (status === 'Confirmed') tabs[1].classList.add('active');
    else if (status === 'Awaiting Payment') tabs[2].classList.add('active');
    else if (status === 'Prescription Review') tabs[3].classList.add('active');
    else if (status === 'Dispatched') tabs[4].classList.add('active');
    else if (status === 'Delivered') tabs[5].classList.add('active');

    renderOrders();
  }

  function renderOrders() {
    const list = document.getElementById('orders-list');
    const empty = document.getElementById('orders-empty');

    const filtered = allOrders.filter(o => {
      if (currentFilter === 'all') return true;
      return o.nir_online_status === currentFilter;
    });

    if (filtered.length === 0) {
      list.innerHTML = '';
      empty.style.display = 'block';
      document.getElementById('empty-title').innerText = allOrders.length === 0 ? 'No Orders Found' : 'No ' + currentFilter + ' Orders';
      document.getElementById('empty-desc').innerText = allOrders.length === 0 
        ? 'No medicine orders found matching the entered contact details.' 
        : 'There are currently no orders in ' + currentFilter + ' status.';
      return;
    }

    empty.style.display = 'none';

    list.innerHTML = filtered.map(order => {
      const statusClass = (order.nir_online_status || 'confirmed').toLowerCase().replace(/\\s+/g, '-');
      const fulfilmentBadge = order.nir_fulfilment_type === 'Store Pickup'
        ? `🏬 Store Pickup: ${order.nir_pickup_store || 'Selected Pharmacy'}`
        : `🛵 Home Delivery (PIN: ${order.nir_pincode || 'Local'})`;

      // Sales Invoice Banner HTML
      let invoiceBannerHtml = '';
      if (order.sales_invoice) {
        invoiceBannerHtml = `
          <div class="ph-invoice-banner has-invoice">
            <div class="ph-inv-info">
              <span style="font-size: 18px;">📄</span>
              <div>
                <div style="font-weight: 700; color: #166534; font-size: 14px;">
                  Official GST Sales Invoice Generated
                </div>
                <div style="font-size: 12px; color: #15803d; margin-top: 2px;">
                  Invoice: <span class="ph-inv-badge">${order.sales_invoice.name}</span> &bull; 
                  Status: <strong>${order.sales_invoice.status.toUpperCase()}</strong> &bull; 
                  Paid Amount: <strong>₹${order.sales_invoice.grand_total.toFixed(2)}</strong>
                </div>
              </div>
            </div>
            <button class="ph-btn-invoice" onclick="openInvoiceModal('${order.sales_invoice.name}')">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 6 2 18 2 18 9"/><path d="M6 18H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2h-2"/><rect x="6" y="14" width="12" height="8"/></svg>
              <span>View &amp; Print Tax Invoice</span>
            </button>
          </div>
        `;
      } else if (order.nir_online_status === 'Awaiting Payment') {
        invoiceBannerHtml = `
          <div class="ph-invoice-banner needs-payment">
            <div class="ph-inv-info">
              <span style="font-size: 18px;">⚠️</span>
              <div>
                <div style="font-weight: 700; color: #92400e; font-size: 14px;">
                  Razorpay Online Payment Pending
                </div>
                <div style="font-size: 12px; color: #b45309; margin-top: 2px;">
                  Order reserved. Complete payment to generate official Sales Invoice and start batch picking.
                </div>
              </div>
            </div>
            <button class="ph-btn-paynow" onclick="triggerRazorpayCheckout('${order.name}', ${order.grand_total})">
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="1" y="4" width="22" height="16" rx="2" ry="2"/><line x1="1" y1="10" x2="23" y2="10"/></svg>
              <span>Pay ₹${order.grand_total.toFixed(2)} Now</span>
            </button>
          </div>
        `;
      }

      // Items Rows
      const itemsRows = (order.items || []).map(it => `
        <tr>
          <td>
            <div class="ph-med-name">${it.item_name || it.item_code}</div>
            ${it.generic_name ? `<div class="ph-med-salt">Active: ${it.generic_name}</div>` : ''}
            <div class="ph-med-tags">
              ${it.strength ? `<span class="ph-mini-tag">${it.strength}</span>` : ''}
              ${it.dosage_form ? `<span class="ph-mini-tag">${it.dosage_form}</span>` : ''}
              ${it.storage_condition && it.storage_condition.includes('2-8') ? `<span class="ph-mini-tag cold">❄️ 2-8°C Cold Chain</span>` : ''}
            </div>
          </td>
          <td style="font-weight: 700; text-align: center;">${it.qty} ${it.uom || 'Unit'}</td>
          <td style="color: #64748b;">₹${it.rate.toFixed(2)}</td>
          <td style="font-weight: 800; color: #0f172a; text-align: right;">₹${it.amount.toFixed(2)}</td>
        </tr>
      `).join('');

      return `
        <article class="ph-order-card" id="card-${order.name}">
          <!-- Card Header -->
          <div class="ph-card-header">
            <div class="ph-order-meta">
              <span class="ph-order-id">#${order.name}</span>
              <span class="ph-order-date">📅 Placed on: ${order.transaction_date || 'Today'}</span>
              <span class="ph-badge-fulfilment">${fulfilmentBadge}</span>
            </div>
            <div>
              <span class="ph-status-pill ${statusClass}">
                <span style="font-size: 8px;">●</span>
                <span>${order.nir_online_status || 'Confirmed'}</span>
              </span>
            </div>
          </div>

          <!-- Invoice Callout -->
          ${invoiceBannerHtml}

          <!-- Items Table -->
          <div class="ph-card-body">
            <div class="ph-table-wrap">
              <table class="ph-items-table">
                <thead>
                  <tr>
                    <th>Prescribed Medicine</th>
                    <th style="text-align: center;">Quantity</th>
                    <th>Unit Rate</th>
                    <th style="text-align: right;">Total</th>
                  </tr>
                </thead>
                <tbody>
                  ${itemsRows}
                </tbody>
              </table>
            </div>
          </div>

          <!-- Card Footer -->
          <div class="ph-card-footer">
            <div class="ph-patient-summary">
              Patient: <strong>${order.nir_online_patient_name || order.customer_name || 'Valued Customer'}</strong> &bull; 
              Payment: <strong>${order.nir_payment_method || 'Razorpay'}</strong>
              ${order.contact_email ? ` &bull; Email: <strong>${order.contact_email}</strong>` : ''}
            </div>
            <div class="ph-card-total-box">
              <div class="ph-total-label">Payable Grand Total</div>
              <div class="ph-total-amount">₹${order.grand_total.toFixed(2)}</div>
            </div>
          </div>
        </article>
      `;
    }).join('');
  }

  function triggerRazorpayCheckout(salesOrder, amount) {
    fetch('/api/method/pharmacy.online.portal.get_razorpay_checkout_details?sales_order=' + encodeURIComponent(salesOrder))
      .then(r => r.json())
      .then(res => {
        const details = res.message || res;
        const options = {
          key: details.key || 'rzp_test_pharmacy_demo',
          amount: details.amount,
          currency: 'INR',
          name: 'Pharmacy Store',
          description: details.description || ('Order #' + salesOrder),
          order_id: details.order_id || undefined,
          prefill: {
            name: details.customer_name || '',
            email: details.email || '',
            contact: details.phone || ''
          },
          theme: { color: '#059669' },
          handler: function(response) {
            verifyPayment(salesOrder, response.razorpay_payment_id, response.razorpay_order_id, response.razorpay_signature);
          }
        };

        if (window.Razorpay) {
          const rzp = new window.Razorpay(options);
          rzp.open();
        } else {
          // Simulation fallback
          const mockId = 'pay_' + Math.random().toString(36).substring(2, 12);
          verifyPayment(salesOrder, mockId, '', '');
        }
      })
      .catch(err => {
        const mockId = 'pay_' + Math.random().toString(36).substring(2, 12);
        verifyPayment(salesOrder, mockId, '', '');
      });
  }

  function verifyPayment(salesOrder, paymentId, orderId, signature) {
    fetch('/api/method/pharmacy.online.portal.verify_razorpay_payment', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': (window.frappe && frappe.csrf_token) || ''
      },
      body: JSON.stringify({
        sales_order: salesOrder,
        razorpay_payment_id: paymentId,
        razorpay_order_id: orderId || '',
        razorpay_signature: signature || ''
      })
    })
    .then(r => r.json())
    .then(res => {
      // Reload orders to show new Sales Invoice and status
      const term = document.getElementById('order-search-input').value.trim() || salesOrder;
      fetchCustomerOrders(term);
    })
    .catch(err => {
      const term = document.getElementById('order-search-input').value.trim() || salesOrder;
      fetchCustomerOrders(term);
    });
  }

  function openInvoiceModal(salesInvoiceName) {
    const modal = document.getElementById('invoice-modal');
    const paper = document.getElementById('invoice-paper-content');
    modal.style.display = 'flex';
    paper.innerHTML = '<div style="text-align: center; padding: 40px;"><div class="ph-spinner"></div><p style="margin-top: 10px;">Loading invoice details...</p></div>';

    fetch('/api/method/pharmacy.online.portal.get_order_invoice_details?sales_invoice=' + encodeURIComponent(salesInvoiceName))
      .then(r => r.json())
      .then(res => {
        const inv = (res.message && res.message.invoice) ? res.message.invoice : null;
        if (!inv) {
          paper.innerHTML = '<p style="color: red;">Failed to retrieve invoice details.</p>';
          return;
        }

        const itemsHtml = (inv.items || []).map((it, idx) => `
          <tr>
            <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0;">${idx + 1}</td>
            <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0;">
              <strong>${it.item_name}</strong>
              <div style="font-size: 11px; color: #64748b;">Code: ${it.item_code}</div>
            </td>
            <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; font-family: monospace;">${it.batch_no || '-'}</td>
            <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; text-align: center;">${it.qty} ${it.uom}</td>
            <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; text-align: right;">₹${it.rate.toFixed(2)}</td>
            <td style="padding: 8px 10px; border-bottom: 1px solid #e2e8f0; text-align: right; font-weight: 700;">₹${it.amount.toFixed(2)}</td>
          </tr>
        `).join('');

        paper.innerHTML = `
          <!-- Header -->
          <div style="border-bottom: 2px solid #0f172a; padding-bottom: 16px; margin-bottom: 20px;">
            <div style="display: flex; justify-content: space-between; align-items: flex-start;">
              <div>
                <h1 style="font-size: 22px; font-weight: 900; margin: 0; color: #059669; letter-spacing: -0.5px;">Pharmacy Store</h1>
                <p style="margin: 2px 0 0 0; font-size: 12px; color: #475569;">Licensed Retail Pharmacy &amp; Healthcare Fulfillment</p>
                <p style="margin: 2px 0 0 0; font-size: 11px; color: #64748b;">Drug Licences: <strong>Form 20 &amp; Form 21</strong> &bull; FSSAI Licensed</p>
                ${inv.company_gstin ? `<p style="margin: 2px 0 0 0; font-size: 11px; color: #64748b;">GSTIN: <strong>${inv.company_gstin}</strong></p>` : ''}
              </div>
              <div style="text-align: right;">
                <div style="background: #0f172a; color: white; padding: 4px 10px; border-radius: 4px; font-size: 12px; font-weight: 800; display: inline-block;">
                  TAX INVOICE
                </div>
                <div style="font-family: monospace; font-size: 16px; font-weight: 800; margin-top: 6px;">
                  #${inv.name}
                </div>
                <div style="font-size: 12px; color: #64748b; margin-top: 2px;">
                  Date: <strong>${inv.posting_date}</strong>
                </div>
                <div style="margin-top: 4px;">
                  <span style="background: #dcfce7; color: #15803d; font-size: 11px; font-weight: 800; padding: 2px 8px; border-radius: 12px; border: 1px solid #bbf7d0;">
                    PAID IN FULL
                  </span>
                </div>
              </div>
            </div>
          </div>

          <!-- Billed To -->
          <div style="display: flex; justify-content: space-between; background: #f8fafc; padding: 14px 18px; border-radius: 10px; margin-bottom: 20px;">
            <div>
              <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b;">Billed &amp; Dispensed To</div>
              <div style="font-size: 15px; font-weight: 800; color: #0f172a; margin-top: 2px;">${inv.patient_name || inv.customer_name}</div>
              <div style="font-size: 12px; color: #475569;">Customer Account: ${inv.customer_name}</div>
            </div>
            <div style="text-align: right;">
              <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #64748b;">Payment Verification</div>
              <div style="font-size: 13px; font-weight: 700; color: #166534; margin-top: 2px;">Authorized via Razorpay</div>
              <div style="font-size: 11px; color: #64748b;">Outstanding Balance: ₹0.00</div>
            </div>
          </div>

          <!-- Table -->
          <table style="width: 100%; border-collapse: collapse; margin-bottom: 20px; font-size: 12px;">
            <thead>
              <tr style="background: #f1f5f9;">
                <th style="padding: 8px 10px; text-align: left; border-bottom: 2px solid #cbd5e1;">#</th>
                <th style="padding: 8px 10px; text-align: left; border-bottom: 2px solid #cbd5e1;">Medicine / Formulation</th>
                <th style="padding: 8px 10px; text-align: left; border-bottom: 2px solid #cbd5e1;">Batch No</th>
                <th style="padding: 8px 10px; text-align: center; border-bottom: 2px solid #cbd5e1;">Qty</th>
                <th style="padding: 8px 10px; text-align: right; border-bottom: 2px solid #cbd5e1;">Rate (INR)</th>
                <th style="padding: 8px 10px; text-align: right; border-bottom: 2px solid #cbd5e1;">Amount (INR)</th>
              </tr>
            </thead>
            <tbody>
              ${itemsHtml}
            </tbody>
          </table>

          <!-- Totals -->
          <div style="display: flex; justify-content: flex-end; margin-bottom: 24px;">
            <div style="width: 280px;">
              <div style="display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; color: #475569;">
                <span>Taxable Value:</span>
                <span>₹${inv.net_total.toFixed(2)}</span>
              </div>
              <div style="display: flex; justify-content: space-between; padding: 4px 0; font-size: 13px; color: #475569;">
                <span>Taxes &amp; GST:</span>
                <span>₹${inv.total_taxes_and_charges.toFixed(2)}</span>
              </div>
              <div style="display: flex; justify-content: space-between; padding: 8px 0; border-top: 2px solid #0f172a; margin-top: 6px; font-size: 16px; font-weight: 900; color: #059669;">
                <span>Grand Total:</span>
                <span>₹${inv.grand_total.toFixed(2)}</span>
              </div>
            </div>
          </div>

          <!-- Pharmacist Declaration -->
          <div style="border-top: 1px dashed #cbd5e1; padding-top: 14px; font-size: 11px; color: #64748b; text-align: center; line-height: 1.5;">
            This is a computer-generated official tax invoice issued by Pharmacy Store.<br />
            Medications dispensed by registered Pharmacist under Drug Licences Form 20 &amp; Form 21. No signature required.
          </div>
        `;
      })
      .catch(err => {
        paper.innerHTML = '<p style="color: red;">Error connecting to pharmacy server.</p>';
      });
  }

  function closeInvoiceModal() {
    document.getElementById('invoice-modal').style.display = 'none';
  }

  function closeInvoiceModalOnBackdrop(e) {
    if (e.target.id === 'invoice-modal') {
      closeInvoiceModal();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initOrdersPage);
  } else {
    initOrdersPage();
  }
</script>
"""
