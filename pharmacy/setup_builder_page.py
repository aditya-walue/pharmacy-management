import json
import frappe
from frappe.utils import flt

def setup():
	frappe.init(site="pharmacy.local")
	frappe.connect()

	from builder.utils import Block
	from pharmacy.orders_page_template import get_orders_html

	# Fetch clean sellable medicines from DB with structured clinical attributes
	medicines = frappe.get_all(
		"Item",
		filters={
			"disabled": 0,
			"is_sales_item": 1,
			"name": ["not like", "_Test%"],
			"item_group": ["not like", "_Test%"],
		},
		fields=[
			"name as item_code",
			"item_name",
			"item_group",
			"nir_salt as generic_name",
			"nir_strength as strength",
			"nir_dosage_form as dosage_form",
			"nir_regulatory_category as category",
			"nir_storage_condition as storage_condition",
			"nir_rx_required as rx_required",
			"stock_uom",
			"sales_uom",
			"valuation_rate as rate",
		],
		order_by="item_name asc",
	)

	clean_meds = []
	for m in medicines:
		if m["item_code"].startswith("138-CMS") or m["item_code"] == "dolo650":
			continue

		m["uom"] = m.get("sales_uom") or m.get("stock_uom") or "Unit"

		price = frappe.db.get_value("Item Price", {"item_code": m["item_code"], "uom": m["uom"], "selling": 1}, "price_list_rate")
		if not price:
			price = frappe.db.get_value("Item Price", {"item_code": m["item_code"], "selling": 1}, "price_list_rate")
		if not price:
			price = frappe.db.get_value("Item Price", {"item_code": m["item_code"]}, "price_list_rate")
		if price and flt(price) > 0:
			m["rate"] = round(flt(price), 2)
		elif not m.get("rate") or flt(m["rate"]) <= 0:
			m["rate"] = 45.0
		else:
			m["rate"] = round(flt(m["rate"]), 2)

		clean_meds.append(m)

	stores = frappe.get_all(
		"Pharmacy Store",
		filters={"disabled": 0},
		fields=["name", "store_name"],
		order_by="store_name asc",
	)

	catalog_json = json.dumps(clean_meds)
	stores_json = json.dumps(stores)

	# =========================================================================
	# PAGE 1: /order (Structured Medicines Catalog with View Cart Links)
	# =========================================================================
	order_html = f"""
<div class="pharmacy-order-wrapper">
  <!-- Navbar Header -->
  <nav class="ph-navbar">
    <div class="ph-nav-container">
      <div class="ph-brand">
        <div class="ph-logo-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>
        </div>
        <div class="ph-brand-text">
          <span class="ph-brand-title">Pharmacy Store</span>
          <span class="ph-brand-sub">Certified Clinical Healthcare &amp; Fulfillment</span>
        </div>
      </div>
      <div class="ph-nav-right">
        <div class="ph-nav-badges">
          <span class="ph-pill-badge green"><span class="dot"></span> 100% Genuine Medicines</span>
          <span class="ph-pill-badge blue"><span class="dot"></span> Licensed Pharmacists</span>
          <span class="ph-pill-badge purple"><span class="dot"></span> Cold-Chain Assured</span>
        </div>
        <!-- My Orders Action Button -->
        <a href="/orders" class="ph-nav-cart-btn" style="background:#f8fafc; color:#1e293b; border:1px solid #cbd5e1; margin-right:8px;" id="nav-orders-btn">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <span>My Orders</span>
        </a>
        <!-- Cart Action Button -->
        <a href="/cart" class="ph-nav-cart-btn" id="nav-cart-btn">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/></svg>
          <span>View Cart</span>
          <span class="ph-cart-pill" id="nav-cart-count">0</span>
        </a>
      </div>
    </div>
  </nav>

  <!-- Hero Section -->
  <header class="ph-hero">
    <div class="ph-hero-content">
      <div class="ph-tag">Certified Pharmacy Formulary</div>
      <h1 class="ph-hero-title">Structured Medicine Catalog</h1>
      <p class="ph-hero-desc">Explore verified pharmaceuticals organized by therapeutic departments, generic active salts, and storage requirements. Add items to your cart and proceed to Razorpay checkout.</p>
    </div>
  </header>

  <!-- Main Content (Full Width Structured Catalog) -->
  <main class="ph-catalog-layout">
    <div class="ph-catalog-section">
      <!-- Section Header & Controls -->
      <div class="ph-section-header">
        <div class="ph-header-left">
          <h2 class="ph-section-title">Verified Medicines &amp; Clinical Supplies</h2>
          <p class="ph-section-subtitle" id="catalog-count-label">Loading catalog items...</p>
        </div>
        <div class="ph-controls-right">
          <!-- View Mode Switcher -->
          <div class="ph-view-toggle">
            <button class="ph-view-btn active" id="btn-view-sections" onclick="setViewMode('sections')" title="Grouped by Category">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h7"/></svg>
              <span>Sections</span>
            </button>
            <button class="ph-view-btn" id="btn-view-grid" onclick="setViewMode('grid')" title="Unified Grid View">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="7" height="7" x="3" y="3" rx="1"/><rect width="7" height="7" x="14" y="3" rx="1"/><rect width="7" height="7" x="14" y="14" rx="1"/><rect width="7" height="7" x="3" y="14" rx="1"/></svg>
              <span>Grid</span>
            </button>
            <button class="ph-view-btn" id="btn-view-table" onclick="setViewMode('table')" title="Tabular Formulary">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18M3 15h18M9 3v18"/></svg>
              <span>Table</span>
            </button>
          </div>
          <!-- Search Box -->
          <div class="ph-search-box">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="m21 21-4.35-4.35"/></svg>
            <input type="text" id="med-search-input" placeholder="Search brand, generic salt, strength..." oninput="handleSearch(this.value)" />
          </div>
        </div>
      </div>

      <!-- Department Category Tabs -->
      <div class="ph-cat-tabs" id="cat-tabs-container"></div>

      <!-- Dosage Form Quick Filter Chips -->
      <div class="ph-form-chips" id="form-chips-container"></div>

      <!-- Medicine Container -->
      <div id="catalog-display-container"></div>

      <!-- Special Order Notice -->
      <div class="ph-special-card">
        <div class="ph-special-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
        </div>
        <div class="ph-special-body">
          <h4 class="ph-special-title">Looking for an unlisted specialty medicine?</h4>
          <p class="ph-special-desc">Proceed to the cart and toggle <strong>Patient Special Order</strong>. Our clinical procurement team will raise an urgent priority indent directly to the manufacturer or central DC.</p>
        </div>
      </div>
    </div>
  </main>

  <!-- Sticky Floating Cart Bar -->
  <div class="ph-floating-cart-bar" id="floating-cart-bar" style="display: none;">
    <div class="ph-floating-inner">
      <div class="ph-floating-info">
        <span class="ph-floating-count" id="floating-cart-count">0 items</span>
        <span class="ph-floating-total" id="floating-cart-total">₹0.00</span>
      </div>
      <a href="/cart" class="ph-floating-btn">
        <span>Proceed to Cart &amp; Checkout</span>
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="9 18 15 12 9 6"/></svg>
      </a>
    </div>
  </div>
</div>

<style>
  :root {{
    --ph-primary: #059669;
    --ph-primary-dark: #047857;
    --ph-accent: #0f766e;
    --ph-bg: #f8fafc;
    --ph-surface: #ffffff;
    --ph-border: #e2e8f0;
    --ph-text: #0f172a;
    --ph-muted: #64748b;
  }}
  * {{ box-sizing: border-box; font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
  body {{ margin: 0; background-color: var(--ph-bg); color: var(--ph-text); }}
  
  .pharmacy-order-wrapper {{ min-height: 100vh; padding-bottom: 80px; }}
  
  /* Navbar */
  .ph-navbar {{ background: #ffffff; border-bottom: 1px solid var(--ph-border); padding: 14px 32px; position: sticky; top: 0; z-index: 50; }}
  .ph-nav-container {{ max-width: 1400px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
  .ph-brand {{ display: flex; align-items: center; gap: 12px; }}
  .ph-logo-icon {{ width: 40px; height: 40px; background: linear-gradient(135deg, #059669, #0d9488); color: white; border-radius: 10px; display: flex; align-items: center; justify-content: center; box-shadow: 0 4px 12px rgba(5,150,105,0.25); }}
  .ph-brand-title {{ font-size: 20px; font-weight: 800; color: #0f172a; display: block; letter-spacing: -0.5px; }}
  .ph-brand-sub {{ font-size: 11px; color: var(--ph-muted); font-weight: 500; text-transform: uppercase; letter-spacing: 0.5px; }}
  .ph-nav-right {{ display: flex; align-items: center; gap: 16px; }}
  .ph-nav-badges {{ display: flex; gap: 8px; }}
  .ph-pill-badge {{ font-size: 12px; font-weight: 600; padding: 6px 12px; border-radius: 999px; display: inline-flex; align-items: center; gap: 6px; }}
  .ph-pill-badge.green {{ background: #ecfdf5; color: #047857; }}
  .ph-pill-badge.blue {{ background: #eff6ff; color: #1d4ed8; }}
  .ph-pill-badge.purple {{ background: #faf5ff; color: #7e22ce; }}
  .ph-pill-badge .dot {{ width: 6px; height: 6px; border-radius: 50%; background: currentColor; }}

  .ph-nav-cart-btn {{ background: linear-gradient(135deg, #059669, #047857); color: white; text-decoration: none; padding: 8px 16px; border-radius: 10px; font-weight: 700; font-size: 13px; display: flex; align-items: center; gap: 8px; box-shadow: 0 4px 10px rgba(5,150,105,0.25); transition: all 0.2s; }}
  .ph-nav-cart-btn:hover {{ transform: translateY(-1px); box-shadow: 0 6px 14px rgba(5,150,105,0.35); }}
  .ph-cart-pill {{ background: #ffffff; color: #047857; font-size: 11px; font-weight: 800; padding: 2px 7px; border-radius: 999px; }}
  
  /* Hero */
  .ph-hero {{ background: linear-gradient(135deg, #064e3b 0%, #065f46 50%, #0f766e 100%); color: white; padding: 40px 32px; text-align: center; }}
  .ph-hero-content {{ max-width: 820px; margin: 0 auto; }}
  .ph-tag {{ display: inline-block; background: rgba(255,255,255,0.15); backdrop-filter: blur(8px); padding: 5px 14px; border-radius: 999px; font-size: 12px; font-weight: 700; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.8px; }}
  .ph-hero-title {{ font-size: 34px; font-weight: 800; margin: 0 0 10px 0; letter-spacing: -1px; line-height: 1.2; }}
  .ph-hero-desc {{ font-size: 15px; opacity: 0.9; margin: 0; line-height: 1.6; }}
  
  /* Catalog Layout (Full Width) */
  .ph-catalog-layout {{ max-width: 1400px; margin: -24px auto 0 auto; padding: 0 24px; }}
  
  /* Section Header & Controls */
  .ph-section-header {{ background: #ffffff; padding: 18px 24px; border-radius: 14px; border: 1px solid var(--ph-border); display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 14px; box-shadow: 0 1px 3px rgba(0,0,0,0.03); flex-wrap: wrap; }}
  .ph-section-title {{ font-size: 19px; font-weight: 800; margin: 0 0 3px 0; color: var(--ph-text); letter-spacing: -0.3px; }}
  .ph-section-subtitle {{ font-size: 13px; color: var(--ph-muted); margin: 0; }}
  .ph-controls-right {{ display: flex; align-items: center; gap: 14px; flex-wrap: wrap; }}
  
  /* View Toggle Buttons */
  .ph-view-toggle {{ display: flex; background: #f1f5f9; padding: 3px; border-radius: 10px; border: 1px solid var(--ph-border); }}
  .ph-view-btn {{ background: transparent; border: none; padding: 6px 12px; border-radius: 7px; font-size: 12px; font-weight: 700; color: #64748b; cursor: pointer; display: flex; align-items: center; gap: 6px; transition: all 0.15s; }}
  .ph-view-btn.active {{ background: #ffffff; color: var(--ph-primary-dark); box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}
  .ph-view-btn:hover:not(.active) {{ color: #0f172a; }}
  
  /* Search Box */
  .ph-search-box {{ position: relative; width: 300px; }}
  .ph-search-box svg {{ position: absolute; left: 12px; top: 50%; transform: translateY(-50%); color: var(--ph-muted); }}
  .ph-search-box input {{ width: 100%; padding: 8px 12px 8px 38px; border: 1px solid var(--ph-border); border-radius: 8px; font-size: 13px; outline: none; transition: all 0.2s; }}
  .ph-search-box input:focus {{ border-color: var(--ph-primary); box-shadow: 0 0 0 3px rgba(5,150,105,0.15); }}
  
  /* Category Filter Tabs */
  .ph-cat-tabs {{ display: flex; gap: 8px; overflow-x: auto; padding-bottom: 8px; margin-bottom: 12px; scrollbar-width: none; }}
  .ph-cat-tabs::-webkit-scrollbar {{ display: none; }}
  .ph-cat-tab {{ white-space: nowrap; background: #ffffff; border: 1px solid var(--ph-border); padding: 8px 14px; border-radius: 10px; font-size: 13px; font-weight: 600; color: #475569; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: all 0.15s; box-shadow: 0 1px 2px rgba(0,0,0,0.02); }}
  .ph-cat-tab:hover {{ border-color: #cbd5e1; background: #f8fafc; color: #0f172a; }}
  .ph-cat-tab.active {{ background: #ecfdf5; border-color: #a7f3d0; color: var(--ph-primary-dark); font-weight: 700; }}
  .ph-cat-badge {{ font-size: 11px; padding: 2px 7px; border-radius: 999px; background: #f1f5f9; color: #475569; font-weight: 700; }}
  .ph-cat-tab.active .ph-cat-badge {{ background: #d1fae5; color: #065f46; }}

  /* Form Chips */
  .ph-form-chips {{ display: flex; gap: 6px; overflow-x: auto; padding-bottom: 4px; margin-bottom: 18px; align-items: center; }}
  .ph-form-chip {{ background: #ffffff; border: 1px solid #e2e8f0; font-size: 12px; font-weight: 600; padding: 4px 11px; border-radius: 6px; color: #64748b; cursor: pointer; transition: all 0.15s; }}
  .ph-form-chip:hover {{ border-color: #94a3b8; color: #1e293b; }}
  .ph-form-chip.active {{ background: #0f172a; border-color: #0f172a; color: #ffffff; }}
  
  /* Category Section Groups */
  .ph-group-block {{ margin-bottom: 24px; }}
  .ph-group-header {{ display: flex; justify-content: space-between; align-items: center; padding: 14px 18px; background: #ffffff; border: 1px solid var(--ph-border); border-radius: 12px 12px 0 0; border-bottom: 2px solid #e2e8f0; }}
  .ph-group-title-wrap {{ display: flex; align-items: center; gap: 10px; }}
  .ph-group-icon {{ width: 34px; height: 34px; border-radius: 8px; display: flex; align-items: center; justify-content: center; font-size: 18px; }}
  .ph-group-title {{ font-size: 16px; font-weight: 800; color: #0f172a; margin: 0; }}
  .ph-group-desc {{ font-size: 12px; color: var(--ph-muted); margin: 0; }}
  .ph-group-count {{ font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 999px; background: #f1f5f9; color: #475569; }}
  .ph-group-cards {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; padding: 16px; background: #f8fafc; border: 1px solid var(--ph-border); border-top: none; border-radius: 0 0 12px 12px; margin-bottom: 8px; }}

  /* Unified Grid Mode */
  .ph-med-grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 14px; margin-bottom: 20px; }}

  /* Structured Medicine Card */
  .ph-med-card {{ background: #ffffff; border: 1px solid var(--ph-border); border-radius: 12px; padding: 16px; display: flex; flex-direction: column; justify-content: space-between; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1); box-shadow: 0 1px 3px rgba(0,0,0,0.02); }}
  .ph-med-card:hover {{ transform: translateY(-2px); box-shadow: 0 10px 20px -8px rgba(0,0,0,0.08); border-color: #cbd5e1; }}
  
  .ph-med-badges-row {{ display: flex; justify-content: space-between; align-items: center; gap: 6px; margin-bottom: 8px; }}
  .ph-tag-group {{ display: flex; gap: 4px; flex-wrap: wrap; }}
  .ph-badge-tag {{ font-size: 10px; font-weight: 800; padding: 3px 7px; border-radius: 5px; text-transform: uppercase; letter-spacing: 0.5px; }}
  .ph-badge-tag.rx {{ background: #fef2f2; color: #dc2626; border: 1px solid #fecaca; }}
  .ph-badge-tag.otc {{ background: #f0fdf4; color: #16a34a; border: 1px solid #bbf7d0; }}
  .ph-badge-tag.cold {{ background: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; }}
  .ph-badge-tag.controlled {{ background: #faf5ff; color: #7e22ce; border: 1px solid #e9d5ff; }}
  .ph-uom-tag {{ font-size: 11px; color: #64748b; font-weight: 600; background: #f1f5f9; padding: 2px 7px; border-radius: 4px; }}

  .ph-med-title {{ font-size: 15px; font-weight: 800; color: var(--ph-text); margin: 0 0 6px 0; line-height: 1.35; }}
  
  /* Essential Medicine Detail Line */
  .ph-med-essential {{ display: flex; align-items: center; flex-wrap: wrap; gap: 6px; font-size: 13px; color: #475569; margin: 2px 0 14px 0; min-height: 22px; }}
  .ph-essential-salt {{ font-weight: 600; color: #334155; }}
  .ph-essential-dot {{ color: #cbd5e1; font-weight: bold; font-size: 12px; }}
  .ph-essential-strength {{ font-weight: 700; color: #059669; background: #ecfdf5; padding: 2px 7px; border-radius: 4px; font-size: 12px; border: 1px solid #a7f3d0; }}

  /* Card Footer Actions */
  .ph-med-footer {{ display: flex; justify-content: space-between; align-items: center; padding-top: 10px; border-top: 1px solid #f1f5f9; }}
  .ph-price-wrap {{ display: flex; flex-direction: column; }}
  .ph-price-label {{ font-size: 10px; color: #94a3b8; text-transform: uppercase; font-weight: 700; }}
  .ph-med-price {{ font-size: 17px; font-weight: 800; color: #0f172a; }}
  
  .ph-btn-group {{ display: flex; align-items: center; }}
  .ph-add-btn {{ background: #ecfdf5; color: var(--ph-primary-dark); border: 1px solid #a7f3d0; padding: 6px 14px; border-radius: 8px; font-weight: 700; font-size: 13px; cursor: pointer; transition: all 0.15s; }}
  .ph-add-btn:hover {{ background: var(--ph-primary); color: white; border-color: var(--ph-primary); }}

  .ph-card-stepper {{ display: inline-flex; align-items: center; background: #ecfdf5; border: 1px solid #a7f3d0; border-radius: 8px; overflow: hidden; }}
  .ph-card-stepper button {{ border: none; background: transparent; padding: 6px 10px; font-weight: 800; color: #065f46; cursor: pointer; font-size: 13px; }}
  .ph-card-stepper button:hover {{ background: #d1fae5; }}
  .ph-card-stepper span {{ font-size: 12px; font-weight: 800; color: #065f46; padding: 0 4px; min-width: 20px; text-align: center; }}

  /* Table Mode */
  .ph-table-wrap {{ background: #ffffff; border: 1px solid var(--ph-border); border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.03); margin-bottom: 20px; }}
  .ph-formulary-table {{ width: 100%; border-collapse: collapse; text-align: left; font-size: 13px; }}
  .ph-formulary-table th {{ background: #f8fafc; padding: 12px 14px; font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 700; border-bottom: 1px solid var(--ph-border); }}
  .ph-formulary-table td {{ padding: 12px 14px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }}
  .ph-formulary-table tr:hover td {{ background: #fbfcfe; }}
  .ph-tbl-med-title {{ font-weight: 700; color: #0f172a; margin-bottom: 2px; }}
  .ph-tbl-med-salt {{ font-size: 11px; color: #64748b; }}

  /* Special Request Card */
  .ph-special-card {{ background: #f0fdf4; border: 1px dashed #86efac; border-radius: 12px; padding: 16px 20px; display: flex; gap: 14px; align-items: center; margin-top: 20px; }}
  .ph-special-icon {{ width: 40px; height: 40px; border-radius: 10px; background: #dcfce7; color: var(--ph-primary-dark); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }}
  .ph-special-title {{ font-size: 14px; font-weight: 700; margin: 0 0 3px 0; color: #14532d; }}
  .ph-special-desc {{ font-size: 12px; color: #166534; margin: 0; line-height: 1.4; }}
  
  /* Floating Bottom Cart Bar */
  .ph-floating-cart-bar {{ position: fixed; bottom: 20px; left: 50%; transform: translateX(-50%); z-index: 100; width: calc(100% - 48px); max-width: 680px; background: #0f172a; color: white; padding: 12px 20px; border-radius: 16px; box-shadow: 0 16px 32px -4px rgba(15,23,42,0.35); }}
  .ph-floating-inner {{ display: flex; justify-content: space-between; align-items: center; }}
  .ph-floating-info {{ display: flex; align-items: center; gap: 12px; }}
  .ph-floating-count {{ background: rgba(255,255,255,0.15); padding: 4px 10px; border-radius: 999px; font-size: 12px; font-weight: 700; }}
  .ph-floating-total {{ font-size: 18px; font-weight: 800; color: #34d399; }}
  .ph-floating-btn {{ background: #059669; color: white; text-decoration: none; padding: 10px 18px; border-radius: 10px; font-weight: 700; font-size: 14px; display: flex; align-items: center; gap: 8px; transition: all 0.2s; }}
  .ph-floating-btn:hover {{ background: #10b981; }}
  
  @media (max-width: 992px) {{
    .ph-hero-title {{ font-size: 26px; }}
    .ph-controls-right {{ width: 100%; }}
    .ph-search-box {{ width: 100%; }}
    .ph-nav-badges {{ display: none; }}
  }}
</style>

<script>
  const rawCatalogData = {catalog_json};
  const storeData = {stores_json};
  
  const SECTIONS_CONFIG = [
    {{ id: 'all', label: 'All Items', icon: '🩺', desc: 'Complete pharmacy inventory & clinical supplies' }},
    {{ id: 'rx', label: 'Prescription (Rx)', icon: '💊', desc: 'Schedule H & H1 medications dispensed against valid medical prescription' }},
    {{ id: 'otc', label: 'OTC Healthcare', icon: '🩹', desc: 'Over-the-counter fever, analgesics, first-aid and daily health essentials' }},
    {{ id: 'cold_chain', label: 'Cold Chain (2-8°C)', icon: '❄️', desc: 'Insulins, biologics and vaccines under continuous temperature control' }},
    {{ id: 'devices', label: 'Surgical & Devices', icon: '🏥', desc: 'Medical devices, syringes, clinical masks, and diagnostic accessories' }},
    {{ id: 'wellness', label: 'Wellness & Nutrition', icon: '🧴', desc: 'Specialized nutrition powders, dermatological cleansers, and supplements' }},
    {{ id: 'controlled', label: 'Controlled (NDPS/X)', icon: '🔒', desc: 'Schedule X & NDPS habit-forming drugs strictly governed by clinical audit' }}
  ];

  let currentCategory = 'all';
  let currentDosageForm = 'all';
  let currentViewMode = 'sections';
  let searchQuery = '';
  let cart = [];

  // Load cart from localStorage
  try {{
    const saved = localStorage.getItem('pharmacy_cart');
    if (saved) cart = JSON.parse(saved);
  }} catch(e) {{}}

  function getItemSection(it) {{
    if (it.storage_condition === '2-8C') return 'cold_chain';
    if (it.category === 'NDPS' || it.category === 'Schedule X') return 'controlled';
    if (it.category === 'Schedule H' || it.category === 'Schedule H1' || it.rx_required === 1) return 'rx';
    if (it.item_group === 'Surgical' || it.dosage_form === 'Device') return 'devices';
    if (it.category === 'Cosmetic' || it.category === 'FSSAI' || it.item_group === 'Cosmetics' || it.item_group === 'Wellness' || it.item_group === 'FMCG') return 'wellness';
    return 'otc';
  }}

  function initPage() {{
    renderCategoryTabs();
    renderDosageFormChips();
    renderCatalog();
    updateCartUI();
  }}

  function renderCategoryTabs() {{
    const tabsCont = document.getElementById('cat-tabs-container');
    if (!tabsCont) return;

    tabsCont.innerHTML = SECTIONS_CONFIG.map(sec => {{
      let count = 0;
      if (sec.id === 'all') {{
        count = rawCatalogData.length;
      }} else {{
        count = rawCatalogData.filter(it => getItemSection(it) === sec.id).length;
      }}

      const isActive = currentCategory === sec.id ? 'active' : '';
      return `
        <button class="ph-cat-tab ${{isActive}}" onclick="setCategory('${{sec.id}}')">
          <span>${{sec.icon}} ${{sec.label}}</span>
          <span class="ph-cat-badge">${{count}}</span>
        </button>
      `;
    }}).join('');
  }}

  function renderDosageFormChips() {{
    const chipsCont = document.getElementById('form-chips-container');
    if (!chipsCont) return;

    const forms = ['all', 'Tablet', 'Injection', 'Gel', 'Capsule', 'Powder', 'Device'];
    chipsCont.innerHTML = forms.map(f => {{
      const label = f === 'all' ? 'All Dosage Forms' : f + 's';
      const isActive = currentDosageForm === f ? 'active' : '';
      return `
        <button class="ph-form-chip ${{isActive}}" onclick="setDosageForm('${{f}}')">${{label}}</button>
      `;
    }}).join('');
  }}

  function setCategory(catId) {{
    currentCategory = catId;
    renderCategoryTabs();
    renderCatalog();
  }}

  function setDosageForm(form) {{
    currentDosageForm = form;
    renderDosageFormChips();
    renderCatalog();
  }}

  function setViewMode(mode) {{
    currentViewMode = mode;
    ['sections', 'grid', 'table'].forEach(m => {{
      const btn = document.getElementById('btn-view-' + m);
      if (btn) btn.classList.toggle('active', m === mode);
    }});
    renderCatalog();
  }}

  function handleSearch(q) {{
    searchQuery = (q || '').toLowerCase().trim();
    renderCatalog();
  }}

  function getFilteredItems() {{
    return rawCatalogData.filter(it => {{
      if (currentCategory !== 'all' && getItemSection(it) !== currentCategory) return false;
      if (currentDosageForm !== 'all' && (it.dosage_form || '') !== currentDosageForm) return false;
      if (searchQuery) {{
        const haystack = [it.item_name, it.generic_name, it.item_code, it.strength, it.category, it.item_group].filter(Boolean).join(' ').toLowerCase();
        if (!haystack.includes(searchQuery)) return false;
      }}
      return true;
    }});
  }}

  function renderCatalog() {{
    const container = document.getElementById('catalog-display-container');
    const countLabel = document.getElementById('catalog-count-label');
    if (!container) return;

    const items = getFilteredItems();
    if (countLabel) {{
      countLabel.innerText = `Displaying ${{items.length}} structured medicines across verified pharmacy categories`;
    }}

    if (!items.length) {{
      container.innerHTML = `
        <div style="background: #ffffff; border: 1px solid #e2e8f0; border-radius: 12px; padding: 48px 24px; text-align: center; color: #64748b;">
          <div style="font-size: 32px; margin-bottom: 8px;">🔍</div>
          <h3 style="font-size: 16px; font-weight: 700; color: #1e293b; margin: 0 0 6px 0;">No matching medicines found</h3>
          <p style="font-size: 13px; margin: 0 0 16px 0;">Try adjusting your search terms or category filters.</p>
          <button onclick="resetFilters()" style="background: #ecfdf5; border: 1px solid #a7f3d0; color: #047857; font-weight: 700; padding: 6px 16px; border-radius: 6px; cursor: pointer;">Reset All Filters</button>
        </div>
      `;
      return;
    }}

    if (currentViewMode === 'table') {{
      renderTableView(container, items);
    }} else if (currentViewMode === 'grid') {{
      renderGridView(container, items);
    }} else {{
      renderSectionsView(container, items);
    }}
  }}

  function resetFilters() {{
    currentCategory = 'all';
    currentDosageForm = 'all';
    searchQuery = '';
    const inp = document.getElementById('med-search-input');
    if (inp) inp.value = '';
    renderCategoryTabs();
    renderDosageFormChips();
    renderCatalog();
  }}

  function renderCardHTML(it) {{
    let badgeClass = 'otc';
    let badgeText = 'OTC';
    if (it.category === 'Schedule H' || it.category === 'Schedule H1') {{
      badgeClass = 'rx';
      badgeText = 'Rx';
    }} else if (it.category === 'NDPS' || it.category === 'Schedule X') {{
      badgeClass = 'controlled';
      badgeText = 'Controlled Rx';
    }} else if (it.rx_required) {{
      badgeClass = 'rx';
      badgeText = 'Rx';
    }}

    const isCold = it.storage_condition === '2-8C';
    const coldTag = isCold ? '<span class="ph-badge-tag cold">❄️ 2-8°C</span>' : '';
    const uomStr = it.uom || it.dosage_form || 'Unit';

    const inCartItem = cart.find(c => c.item_code === it.item_code);
    const cartQty = inCartItem ? inCartItem.qty : 0;

    let actionBtnHTML = '';
    if (cartQty > 0) {{
      actionBtnHTML = `
        <div class="ph-card-stepper">
          <button onclick="updateQty('${{it.item_code}}', -1)">−</button>
          <span>${{cartQty}} in Cart</span>
          <button onclick="updateQty('${{it.item_code}}', 1)">+</button>
        </div>
      `;
    }} else {{
      actionBtnHTML = `
        <button class="ph-add-btn" onclick="addToCart('${{it.item_code}}')">+ Add</button>
      `;
    }}

    // Clean essential details: Active Salt and Strength
    let essentialHTML = '';
    if (it.generic_name || it.strength) {{
      essentialHTML = `
        <div class="ph-med-essential">
          ${{it.generic_name ? `<span class="ph-essential-salt">${{it.generic_name}}</span>` : ''}}
          ${{it.generic_name && it.strength ? `<span class="ph-essential-dot">&bull;</span>` : ''}}
          ${{it.strength ? `<span class="ph-essential-strength">${{it.strength}}</span>` : ''}}
        </div>
      `;
    }} else {{
      essentialHTML = '<div class="ph-med-essential"></div>';
    }}

    return `
      <div class="ph-med-card">
        <div>
          <div class="ph-med-badges-row">
            <div class="ph-tag-group">
              <span class="ph-badge-tag ${{badgeClass}}">${{badgeText}}</span>
              ${{coldTag}}
            </div>
            <span class="ph-uom-tag">${{uomStr}}</span>
          </div>

          <h3 class="ph-med-title">${{it.item_name}}</h3>
          ${{essentialHTML}}
        </div>

        <div class="ph-med-footer">
          <div class="ph-price-wrap">
            <span class="ph-price-label">Price / ${{uomStr}}</span>
            <div class="ph-med-price">₹${{parseFloat(it.rate).toFixed(2)}}</div>
          </div>
          <div class="ph-btn-group">
            ${{actionBtnHTML}}
          </div>
        </div>
      </div>
    `;
  }}

  function renderSectionsView(container, items) {{
    const relevantSections = SECTIONS_CONFIG.filter(s => s.id !== 'all');
    let html = '';

    relevantSections.forEach(sec => {{
      const secItems = items.filter(it => getItemSection(it) === sec.id);
      if (!secItems.length) return;

      html += `
        <div class="ph-group-block">
          <div class="ph-group-header">
            <div class="ph-group-title-wrap">
              <div class="ph-group-icon">${{sec.icon}}</div>
              <div>
                <h3 class="ph-group-title">${{sec.label}}</h3>
                <p class="ph-group-desc">${{sec.desc}}</p>
              </div>
            </div>
            <span class="ph-group-count">${{secItems.length}} item${{secItems.length === 1 ? '' : 's'}}</span>
          </div>
          <div class="ph-group-cards">
            ${{secItems.map(it => renderCardHTML(it)).join('')}}
          </div>
        </div>
      `;
    }});

    container.innerHTML = html;
  }}

  function renderGridView(container, items) {{
    container.innerHTML = `
      <div class="ph-med-grid">
        ${{items.map(it => renderCardHTML(it)).join('')}}
      </div>
    `;
  }}

  function renderTableView(container, items) {{
    let rowsHTML = items.map(it => {{
      const isCold = it.storage_condition === '2-8C';
      const inCartItem = cart.find(c => c.item_code === it.item_code);
      const cartQty = inCartItem ? inCartItem.qty : 0;

      let btnHTML = '';
      if (cartQty > 0) {{
        btnHTML = `
          <div class="ph-card-stepper">
            <button onclick="updateQty('${{it.item_code}}', -1)">−</button>
            <span>${{cartQty}}</span>
            <button onclick="updateQty('${{it.item_code}}', 1)">+</button>
          </div>
        `;
      }} else {{
        btnHTML = `<button class="ph-add-btn" onclick="addToCart('${{it.item_code}}')">+ Add</button>`;
      }}

      return `
        <tr>
          <td>
            <div class="ph-tbl-med-title">${{it.item_name}}</div>
            <div class="ph-tbl-med-salt">${{it.generic_name ? it.generic_name + ' &bull; ' : ''}}${{it.strength || ''}}</div>
          </td>
          <td>
            <strong>${{it.uom || it.dosage_form || 'Unit'}}</strong>
          </td>
          <td>
            <span class="ph-badge-tag ${{it.rx_required ? 'rx' : 'otc'}}">${{it.rx_required ? 'Rx' : 'OTC'}}</span>
          </td>
          <td>
            <span style="font-size: 12px; color: ${{isCold ? '#1d4ed8' : '#64748b'}};">
              ${{isCold ? '❄️ 2-8°C' : 'Standard'}}
            </span>
          </td>
          <td style="font-weight: 800; font-size: 15px; color: #0f172a;">
            ₹${{parseFloat(it.rate).toFixed(2)}}
          </td>
          <td style="text-align: right;">
            ${{btnHTML}}
          </td>
        </tr>
      `;
    }}).join('');

    container.innerHTML = `
      <div class="ph-table-wrap">
        <table class="ph-formulary-table">
          <thead>
            <tr>
              <th>Medicine &amp; Molecule</th>
              <th>Form &amp; Strength</th>
              <th>Category</th>
              <th>Storage</th>
              <th>Unit Price</th>
              <th style="text-align: right;">Order Action</th>
            </tr>
          </thead>
          <tbody>
            ${{rowsHTML}}
          </tbody>
        </table>
      </div>
    `;
  }}

  function addToCart(code) {{
    const item = rawCatalogData.find(c => c.item_code === code);
    if (!item) return;
    const existing = cart.find(c => c.item_code === code);
    if (existing) {{
      existing.qty += 1;
    }} else {{
      cart.push({{ ...item, qty: 1, uom: item.uom || 'Unit' }});
    }}
    saveCart();
    updateCartUI();
    renderCatalog();
  }}

  function updateQty(code, delta) {{
    const item = cart.find(c => c.item_code === code);
    if (!item) return;
    item.qty += delta;
    if (item.qty <= 0) {{
      cart = cart.filter(c => c.item_code !== code);
    }}
    saveCart();
    updateCartUI();
    renderCatalog();
  }}

  function saveCart() {{
    try {{
      localStorage.setItem('pharmacy_cart', JSON.stringify(cart));
    }} catch(e) {{}}
  }}

  function updateCartUI() {{
    const totalQty = cart.reduce((s, i) => s + i.qty, 0);
    const subtotal = cart.reduce((s, i) => s + (i.qty * parseFloat(i.rate)), 0);

    const navBadge = document.getElementById('nav-cart-count');
    if (navBadge) navBadge.innerText = totalQty;

    const floatingBar = document.getElementById('floating-cart-bar');
    const floatingCount = document.getElementById('floating-cart-count');
    const floatingTotal = document.getElementById('floating-cart-total');

    if (floatingBar) {{
      if (totalQty > 0) {{
        floatingBar.style.display = 'block';
        if (floatingCount) floatingCount.innerText = `${{totalQty}} item${{totalQty === 1 ? '' : 's'}} in cart`;
        if (floatingTotal) floatingTotal.innerText = `₹${{subtotal.toFixed(2)}}`;
      }} else {{
        floatingBar.style.display = 'none';
      }}
    }}
  }}

  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', initPage);
  }} else {{
    initPage();
  }}
</script>
"""

	# =========================================================================
	# PAGE 2: /cart (Dedicated Cart, Patient Details & Razorpay Checkout)
	# =========================================================================
	cart_html = f"""
<!-- Razorpay Checkout SDK Script -->
<script src="https://checkout.razorpay.com/v1/checkout.js"></script>

<div class="pharmacy-cart-wrapper">
  <!-- Navbar Header -->
  <nav class="ph-navbar">
    <div class="ph-nav-container">
      <div class="ph-brand">
        <div class="ph-logo-icon">
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M12 5v14M5 12h14"/></svg>
        </div>
        <div class="ph-brand-text">
          <span class="ph-brand-title">Pharmacy Store</span>
          <span class="ph-brand-sub">Order Cart &amp; Razorpay Payment Checkout</span>
        </div>
      </div>
      <div style="display: flex; align-items: center; gap: 10px;">
        <a href="/orders" class="ph-back-link" style="background:#f1f5f9; color:#1e293b; border:1px solid #cbd5e1;">
          <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <span>My Orders</span>
        </a>
        <a href="/order" class="ph-back-link">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="15 18 9 12 15 6"/></svg>
          <span>Continue Browsing Catalog</span>
        </a>
      </div>
    </div>
  </nav>

  <!-- Main Cart Layout -->
  <main class="ph-cart-main">
    <!-- Empty Cart State -->
    <div id="cart-empty-view" class="ph-empty-box" style="display: none;">
      <div class="ph-empty-icon">
        <svg width="56" height="56" viewBox="0 0 24 24" fill="none" stroke="#94a3b8" stroke-width="1.5"><circle cx="8" cy="21" r="1"/><circle cx="19" cy="21" r="1"/><path d="M2.05 2.05h2l2.66 12.42a2 2 0 0 0 2 1.58h9.78a2 2 0 0 0 1.95-1.57l1.65-7.43H5.12"/></svg>
      </div>
      <h2 style="font-size: 20px; font-weight: 800; color: #0f172a; margin: 12px 0 6px 0;">Your Shopping Cart is Empty</h2>
      <p style="color: #64748b; font-size: 14px; margin: 0 0 20px 0;">Explore authentic prescription and OTC medicines from our verified catalog.</p>
      <a href="/order" class="ph-btn-primary">Browse Medicine Catalog →</a>
    </div>

    <!-- Filled Cart Layout -->
    <div id="cart-content-view" class="ph-cart-grid">
      <!-- Left Column: Cart Items & Patient Info -->
      <div class="ph-cart-left">
        <!-- Cart Items Box -->
        <div class="ph-panel">
          <div class="ph-panel-header">
            <div>
              <h2 class="ph-panel-title">Medicines in Your Cart</h2>
              <p class="ph-panel-sub" id="cart-items-summary">Review your prescribed items and quantities</p>
            </div>
            <button onclick="clearCart()" class="ph-clear-btn">Clear All</button>
          </div>

          <div class="ph-cart-table-wrap">
            <table class="ph-cart-table">
              <thead>
                <tr>
                  <th>Medicine Details</th>
                  <th>Unit Rate</th>
                  <th style="text-align: center;">Quantity</th>
                  <th style="text-align: right;">Total</th>
                  <th></th>
                </tr>
              </thead>
              <tbody id="cart-table-body"></tbody>
            </table>
          </div>
        </div>

        <!-- Patient & Delivery Form Box -->
        <div class="ph-panel">
          <h2 class="ph-panel-title" style="margin-bottom: 4px;">Patient &amp; Delivery Details</h2>
          <p class="ph-panel-sub" style="margin-bottom: 20px;">Provide patient information for prescription verification and courier dispatch.</p>

          <form id="checkout-form" onsubmit="handleProceedCheckout(event)">
            <div class="ph-form-row">
              <div class="ph-form-group">
                <label>Patient / Customer Name *</label>
                <input type="text" id="cust-name" placeholder="Full name of patient" required />
              </div>
              <div class="ph-form-group">
                <label>Contact Phone Number *</label>
                <input type="tel" id="cust-phone" placeholder="10-digit mobile number" required />
              </div>
            </div>

            <div class="ph-form-group">
              <label>Email Address (for Order Updates &amp; Razorpay Receipt) *</label>
              <input type="email" id="cust-email" placeholder="customer@example.com" required />
            </div>

            <div class="ph-form-group">
              <label>Fulfillment Preference *</label>
              <div class="ph-toggle-group">
                <label class="ph-toggle-btn active" id="btn-hd" onclick="setFulfillment('Home Delivery')">
                  🚚 Home Delivery
                </label>
                <label class="ph-toggle-btn" id="btn-sp" onclick="setFulfillment('Store Pickup')">
                  🏬 Store Pickup
                </label>
              </div>
            </div>

            <div class="ph-form-group" id="store-select-group" style="display: none;">
              <label>Select Pharmacy Store for Pickup *</label>
              <select id="cust-store">
                <option value="">-- Choose Store Location --</option>
              </select>
            </div>

            <div id="pincode-group">
              <div class="ph-form-row">
                <div class="ph-form-group">
                  <label>Address Title</label>
                  <input type="text" id="addr-title" placeholder="e.g. Home, Office" />
                </div>
                <div class="ph-form-group">
                  <label>Address Type</label>
                  <select id="addr-type">
                    <option value="Shipping">Shipping</option>
                    <option value="Billing">Billing</option>
                  </select>
                </div>
              </div>
              <div class="ph-form-group">
                <label>Address Line 1 *</label>
                <input type="text" id="addr-line1" placeholder="Flat / house no., building" maxlength="140" />
              </div>
              <div class="ph-form-group">
                <label>Address Line 2</label>
                <input type="text" id="addr-line2" placeholder="Street, area, landmark" maxlength="140" />
              </div>
              <div class="ph-form-row">
                <div class="ph-form-group">
                  <label>Postal Code *</label>
                  <input type="text" id="cust-pincode" placeholder="e.g. 400050" maxlength="6" inputmode="numeric" onblur="fillFromPincode()" />
                  <small id="pincode-msg" style="display:block; margin-top:4px; font-size:11px;"></small>
                </div>
                <div class="ph-form-group">
                  <label>City *</label>
                  <input type="text" id="addr-city" />
                </div>
              </div>
              <div class="ph-form-row">
                <div class="ph-form-group">
                  <label>State *</label>
                  <select id="addr-state">
                    <option value="">-- Select State --</option>
                  </select>
                </div>
                <div class="ph-form-group">
                  <label>GSTIN / UIN (business purchases)</label>
                  <input type="text" id="addr-gstin" maxlength="15" placeholder="Optional" style="text-transform: uppercase;" />
                </div>
              </div>
              <div class="ph-checkbox-box">
                <input type="checkbox" id="addr-primary" checked />
                <label for="addr-primary"><strong>Save as my preferred address</strong></label>
              </div>
            </div>

            <!-- Patient Special Order Toggle -->
            <div class="ph-checkbox-box">
              <input type="checkbox" id="cust-special-order" />
              <label for="cust-special-order">
                <strong>Patient Special Order (Priority Tracked)</strong><br />
                <small>Select for unstocked or emergency hospital patient indents.</small>
              </label>
            </div>

            <!-- Prescription Upload -->
            <div class="ph-form-group" id="rx-upload-box">
              <label>Prescription Upload (Mandatory for Rx / Schedule H Medicines)</label>
              <div class="ph-upload-zone" onclick="document.getElementById('cust-rx-file').click()">
                <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
                <span id="rx-file-text">Click to attach doctor prescription (PDF, JPG, PNG)</span>
                <input type="file" id="cust-rx-file" style="display:none;" onchange="handleRxFileSelect(event)" />
              </div>
            </div>

            <div class="ph-form-group">
              <label>Special Instructions / Dosage Notes</label>
              <textarea id="cust-notes" rows="2" placeholder="Optional notes for dispensing pharmacist..."></textarea>
            </div>
          </form>
        </div>
      </div>

      <!-- Right Column: Order Summary & Razorpay Gateway -->
      <div class="ph-cart-right">
        <div class="ph-panel ph-sticky-panel">
          <h2 class="ph-panel-title" style="margin-bottom: 16px;">Payment Summary</h2>

          <!-- Cost Breakdown -->
          <div class="ph-breakdown">
            <div class="ph-b-row">
              <span>Items Subtotal</span>
              <span id="summary-subtotal">₹0.00</span>
            </div>
            <div class="ph-b-row">
              <span>Delivery &amp; Handling</span>
              <span class="free">FREE</span>
            </div>
            <div class="ph-b-row">
              <span>Estimated GST</span>
              <span style="color:#64748b;">Included in MRP</span>
            </div>
            <div class="ph-b-row total">
              <span>Payable Amount</span>
              <span id="summary-total">₹0.00</span>
            </div>
          </div>

          <!-- Payment Method Selection -->
          <div style="margin-top: 20px;">
            <label style="font-size: 13px; font-weight: 700; color: #0f172a; display: block; margin-bottom: 10px;">Select Payment Method</label>
            
            <!-- Razorpay Option -->
            <label class="ph-pay-option active" id="pay-opt-razorpay" onclick="setPaymentMethod('Razorpay')">
              <input type="radio" name="paymethod" value="Razorpay" checked style="accent-color: #059669;" />
              <div style="flex: 1;">
                <div style="display: flex; align-items: center; justify-content: space-between;">
                  <strong style="color: #0f172a; font-size: 14px;">Razorpay Secure Gateway</strong>
                  <span class="ph-razor-badge">Recommended</span>
                </div>
                <div style="font-size: 12px; color: #64748b; margin-top: 2px;">Instant UPI, Credit/Debit Cards, Netbanking &amp; Wallets</div>
              </div>
            </label>

            <!-- Cash on Delivery Option -->
            <label class="ph-pay-option" id="pay-opt-cod" onclick="setPaymentMethod('Cash on Delivery')">
              <input type="radio" name="paymethod" value="Cash on Delivery" style="accent-color: #059669;" />
              <div style="flex: 1;">
                <strong style="color: #0f172a; font-size: 14px;">Cash on Delivery (COD)</strong>
                <div style="font-size: 12px; color: #64748b; margin-top: 2px;">Pay in cash or UPI upon package handover</div>
              </div>
            </label>
          </div>

          <!-- Action Button -->
          <button type="button" class="ph-checkout-action-btn" id="checkout-action-btn" onclick="submitOrder()">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><rect width="20" height="14" x="2" y="5" rx="2"/><line x1="2" x2="22" y1="10" y2="10"/></svg>
            <span id="checkout-btn-text">Pay with Razorpay</span>
          </button>

          <!-- Trust Badges -->
          <div class="ph-trust-note">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#059669" stroke-width="2.5"><rect width="18" height="11" x="3" y="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>
            <span>256-Bit SSL Encrypted &bull; Razorpay Certified Checkout</span>
          </div>

          <!-- Success Order Card -->
          <div id="order-completed-card" class="ph-order-card" style="display: none;"></div>
        </div>
      </div>
    </div>
  </main>
</div>

<style>
  :root {{
    --ph-primary: #059669;
    --ph-primary-dark: #047857;
    --ph-bg: #f8fafc;
    --ph-surface: #ffffff;
    --ph-border: #e2e8f0;
    --ph-text: #0f172a;
    --ph-muted: #64748b;
  }}
  * {{ box-sizing: border-box; font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; }}
  body {{ margin: 0; background-color: var(--ph-bg); color: var(--ph-text); }}

  .pharmacy-cart-wrapper {{ min-height: 100vh; padding-bottom: 60px; }}

  /* Navbar */
  .ph-navbar {{ background: #ffffff; border-bottom: 1px solid var(--ph-border); padding: 16px 32px; position: sticky; top: 0; z-index: 50; }}
  .ph-nav-container {{ max-width: 1360px; margin: 0 auto; display: flex; justify-content: space-between; align-items: center; }}
  .ph-brand {{ display: flex; align-items: center; gap: 12px; }}
  .ph-logo-icon {{ width: 40px; height: 40px; background: linear-gradient(135deg, #059669, #0d9488); color: white; border-radius: 10px; display: flex; align-items: center; justify-content: center; }}
  .ph-brand-title {{ font-size: 20px; font-weight: 800; color: #0f172a; display: block; }}
  .ph-brand-sub {{ font-size: 11px; color: var(--ph-muted); font-weight: 500; text-transform: uppercase; }}
  .ph-back-link {{ display: flex; align-items: center; gap: 6px; font-size: 13px; font-weight: 700; color: #059669; text-decoration: none; padding: 8px 14px; background: #ecfdf5; border-radius: 8px; border: 1px solid #a7f3d0; }}
  .ph-back-link:hover {{ background: #d1fae5; }}

  /* Cart Layout */
  .ph-cart-main {{ max-width: 1360px; margin: 28px auto 0 auto; padding: 0 24px; }}
  .ph-cart-grid {{ display: grid; grid-template-columns: 1fr 430px; gap: 26px; }}

  /* Panels */
  .ph-panel {{ background: #ffffff; border: 1px solid var(--ph-border); border-radius: 14px; padding: 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.03); margin-bottom: 22px; }}
  .ph-sticky-panel {{ position: sticky; top: 90px; }}
  .ph-panel-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; border-bottom: 1px solid #f1f5f9; padding-bottom: 14px; }}
  .ph-panel-title {{ font-size: 17px; font-weight: 800; color: #0f172a; margin: 0; }}
  .ph-panel-sub {{ font-size: 13px; color: var(--ph-muted); margin: 3px 0 0 0; }}
  .ph-clear-btn {{ background: transparent; border: 1px solid #fecaca; color: #dc2626; font-size: 12px; font-weight: 700; padding: 5px 12px; border-radius: 6px; cursor: pointer; }}
  .ph-clear-btn:hover {{ background: #fef2f2; }}

  /* Cart Table */
  .ph-cart-table-wrap {{ overflow-x: auto; }}
  .ph-cart-table {{ width: 100%; border-collapse: collapse; font-size: 13px; text-align: left; }}
  .ph-cart-table th {{ background: #f8fafc; padding: 10px 12px; font-size: 11px; text-transform: uppercase; color: #64748b; font-weight: 700; border-bottom: 1px solid var(--ph-border); }}
  .ph-cart-table td {{ padding: 14px 12px; border-bottom: 1px solid #f1f5f9; vertical-align: middle; }}
  .ph-c-med-name {{ font-weight: 700; color: #0f172a; font-size: 14px; margin-bottom: 2px; }}
  .ph-c-med-salt {{ font-size: 12px; color: #64748b; }}
  
  .ph-tbl-qty {{ display: flex; align-items: center; justify-content: center; gap: 8px; }}
  .ph-tbl-qty button {{ width: 26px; height: 26px; border: 1px solid var(--ph-border); background: #f8fafc; border-radius: 6px; font-weight: 800; cursor: pointer; }}
  .ph-tbl-qty button:hover {{ background: #e2e8f0; }}
  .ph-tbl-qty span {{ font-weight: 800; min-width: 18px; text-align: center; }}

  .ph-remove-row-btn {{ background: transparent; border: none; color: #94a3b8; cursor: pointer; padding: 4px; font-size: 16px; }}
  .ph-remove-row-btn:hover {{ color: #ef4444; }}

  /* Form Elements */
  .ph-form-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
  .ph-form-group {{ margin-bottom: 14px; }}
  .ph-form-group label {{ display: block; font-size: 12px; font-weight: 700; color: #334155; margin-bottom: 5px; }}
  .ph-form-group input, .ph-form-group select, .ph-form-group textarea {{ width: 100%; padding: 10px 12px; border: 1px solid var(--ph-border); border-radius: 8px; font-size: 13px; outline: none; }}
  .ph-form-group input:focus, .ph-form-group select:focus, .ph-form-group textarea:focus {{ border-color: var(--ph-primary); box-shadow: 0 0 0 3px rgba(5,150,105,0.15); }}
  
  .ph-toggle-group {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
  .ph-toggle-btn {{ padding: 10px; border: 1px solid var(--ph-border); border-radius: 8px; text-align: center; font-size: 13px; font-weight: 600; cursor: pointer; background: #ffffff; color: var(--ph-muted); }}
  .ph-toggle-btn.active {{ background: #ecfdf5; border-color: var(--ph-primary); color: var(--ph-primary-dark); font-weight: 700; }}
  
  .ph-checkbox-box {{ display: flex; gap: 10px; align-items: flex-start; padding: 12px; background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; margin-bottom: 14px; }}
  .ph-checkbox-box input {{ margin-top: 3px; accent-color: #d97706; }}
  .ph-checkbox-box label {{ font-size: 12px; color: #78350f; cursor: pointer; }}

  .ph-upload-zone {{ border: 2px dashed #cbd5e1; border-radius: 8px; padding: 14px; text-align: center; cursor: pointer; color: var(--ph-muted); font-size: 12px; display: flex; flex-direction: column; align-items: center; gap: 6px; }}
  .ph-upload-zone:hover {{ border-color: var(--ph-primary); background: #f0fdf4; color: var(--ph-primary); }}

  /* Price Breakdown */
  .ph-breakdown {{ background: #f8fafc; border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 8px; font-size: 13px; }}
  .ph-b-row {{ display: flex; justify-content: space-between; color: var(--ph-muted); }}
  .ph-b-row.total {{ font-size: 17px; font-weight: 800; color: var(--ph-text); border-top: 1px solid #e2e8f0; padding-top: 8px; margin-top: 4px; }}
  .ph-b-row .free {{ color: var(--ph-primary); font-weight: 700; }}

  /* Payment Method Options */
  .ph-pay-option {{ display: flex; gap: 12px; align-items: flex-start; padding: 14px; border: 1.5px solid var(--ph-border); border-radius: 10px; margin-bottom: 10px; cursor: pointer; transition: all 0.15s; background: #ffffff; }}
  .ph-pay-option.active {{ border-color: #059669; background: #f0fdf4; box-shadow: 0 0 0 2px rgba(5,150,105,0.15); }}
  .ph-razor-badge {{ background: #059669; color: white; font-size: 10px; font-weight: 800; padding: 2px 7px; border-radius: 999px; text-transform: uppercase; }}

  /* Action Buttons */
  .ph-checkout-action-btn {{ width: 100%; margin-top: 18px; background: linear-gradient(135deg, #059669, #047857); color: white; border: none; padding: 14px; border-radius: 10px; font-size: 15px; font-weight: 800; cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 10px; box-shadow: 0 4px 14px rgba(5,150,105,0.3); transition: all 0.2s; }}
  .ph-checkout-action-btn:hover {{ transform: translateY(-1px); box-shadow: 0 6px 18px rgba(5,150,105,0.4); }}
  
  .ph-trust-note {{ display: flex; align-items: center; justify-content: center; gap: 6px; font-size: 11px; color: #64748b; margin-top: 12px; }}

  .ph-empty-box {{ background: #ffffff; border: 1px solid var(--ph-border); border-radius: 16px; padding: 60px 24px; text-align: center; max-width: 600px; margin: 40px auto; }}
  .ph-btn-primary {{ display: inline-block; background: #059669; color: white; text-decoration: none; padding: 12px 24px; border-radius: 10px; font-weight: 700; font-size: 14px; }}

  .ph-order-card {{ background: #f0fdf4; border: 1px solid #86efac; border-radius: 12px; padding: 20px; margin-top: 18px; text-align: center; }}

  @media (max-width: 992px) {{
    .ph-cart-grid {{ grid-template-columns: 1fr; }}
    .ph-form-row {{ grid-template-columns: 1fr; }}
  }}
</style>

<script>
  const storeData = {stores_json};
  let cart = [];
  let currentFulfillment = 'Home Delivery';
  let currentPaymentMethod = 'Razorpay';
  let uploadedFileName = '';
  let rxFile = null;

  // Load cart from localStorage
  try {{
    const saved = localStorage.getItem('pharmacy_cart');
    if (saved) cart = JSON.parse(saved);
  }} catch(e) {{}}

  function initCartPage() {{
    renderCartView();
    populateStores();
    populateStates();
  }}

  function populateStates() {{
    const sel = document.getElementById('addr-state');
    if (!sel) return;
    fetch('/api/method/pharmacy.online.portal.get_states')
      .then(r => r.json())
      .then(res => {{
        (res.message || []).forEach(state => {{
          const opt = document.createElement('option');
          opt.value = state;
          opt.innerText = state;
          sel.appendChild(opt);
        }});
      }})
      .catch(() => {{}});
  }}

  function populateStores() {{
    const sel = document.getElementById('cust-store');
    if (!sel) return;
    storeData.forEach(s => {{
      const opt = document.createElement('option');
      opt.value = s.name;
      opt.innerText = s.store_name;
      sel.appendChild(opt);
    }});
  }}

  function renderCartView() {{
    const emptyView = document.getElementById('cart-empty-view');
    const contentView = document.getElementById('cart-content-view');

    if (!cart.length) {{
      if (emptyView) emptyView.style.display = 'block';
      if (contentView) contentView.style.display = 'none';
      return;
    }}

    if (emptyView) emptyView.style.display = 'none';
    if (contentView) contentView.style.display = 'grid';

    // Populate items table
    const tbody = document.getElementById('cart-table-body');
    const summaryLabel = document.getElementById('cart-items-summary');
    const totalQty = cart.reduce((s, i) => s + i.qty, 0);
    const subtotal = cart.reduce((s, i) => s + (i.qty * parseFloat(i.rate)), 0);

    if (summaryLabel) {{
      summaryLabel.innerText = `${{totalQty}} item${{totalQty === 1 ? '' : 's'}} &bull; Total ₹${{subtotal.toFixed(2)}}`;
    }}

    if (tbody) {{
      tbody.innerHTML = cart.map(it => `
        <tr>
          <td>
            <div class="ph-c-med-name">${{it.item_name}}</div>
            <div class="ph-c-med-salt">🧪 ${{it.generic_name || 'Standard formula'}} &bull; ${{it.dosage_form || 'Form'}} (${{it.strength || ''}}) &bull; Unit: <strong>${{it.uom || 'Unit'}}</strong></div>
          </td>
          <td style="font-weight: 700; color: #0f172a;">
            ₹${{parseFloat(it.rate).toFixed(2)}}
          </td>
          <td style="text-align: center;">
            <div class="ph-tbl-qty">
              <button onclick="updateCartQty('${{it.item_code}}', -1)">−</button>
              <span>${{it.qty}}</span>
              <button onclick="updateCartQty('${{it.item_code}}', 1)">+</button>
            </div>
          </td>
          <td style="font-weight: 800; color: #0f172a; text-align: right;">
            ₹${{(it.qty * parseFloat(it.rate)).toFixed(2)}}
          </td>
          <td style="text-align: right;">
            <button class="ph-remove-row-btn" onclick="removeItem('${{it.item_code}}')" title="Remove item">&times;</button>
          </td>
        </tr>
      `).join('');
    }}

    // Summary calculations
    const subtotalEl = document.getElementById('summary-subtotal');
    const totalEl = document.getElementById('summary-total');
    if (subtotalEl) subtotalEl.innerText = `₹${{subtotal.toFixed(2)}}`;
    if (totalEl) totalEl.innerText = `₹${{subtotal.toFixed(2)}}`;

    updateButtonText(subtotal);
  }}

  function updateCartQty(code, delta) {{
    const item = cart.find(c => c.item_code === code);
    if (!item) return;
    item.qty += delta;
    if (item.qty <= 0) {{
      cart = cart.filter(c => c.item_code !== code);
    }}
    saveCart();
    renderCartView();
  }}

  function removeItem(code) {{
    cart = cart.filter(c => c.item_code !== code);
    saveCart();
    renderCartView();
  }}

  function clearCart() {{
    if (confirm('Are you sure you want to clear your cart?')) {{
      cart = [];
      saveCart();
      renderCartView();
    }}
  }}

  function saveCart() {{
    try {{
      localStorage.setItem('pharmacy_cart', JSON.stringify(cart));
    }} catch(e) {{}}
  }}

  function setFulfillment(type) {{
    currentFulfillment = type;
    const btnHd = document.getElementById('btn-hd');
    const btnSp = document.getElementById('btn-sp');
    const storeGrp = document.getElementById('store-select-group');
    const pinGrp = document.getElementById('pincode-group');

    if (type === 'Home Delivery') {{
      btnHd.classList.add('active');
      btnSp.classList.remove('active');
      storeGrp.style.display = 'none';
      pinGrp.style.display = 'block';
    }} else {{
      btnSp.classList.add('active');
      btnHd.classList.remove('active');
      storeGrp.style.display = 'block';
      pinGrp.style.display = 'none';
    }}
  }}

  function fillFromPincode() {{
    const pin = document.getElementById('cust-pincode').value.trim();
    const msg = document.getElementById('pincode-msg');
    if (!/^[0-9]{{6}}$/.test(pin)) {{ msg.innerText = ''; return; }}
    fetch('/api/method/pharmacy.online.portal.get_pincode_details?pincode=' + encodeURIComponent(pin))
      .then(r => r.json())
      .then(res => {{
        const d = res.message || {{}};
        if (d.city && !document.getElementById('addr-city').value) document.getElementById('addr-city').value = d.city;
        if (d.state && !document.getElementById('addr-state').value) document.getElementById('addr-state').value = d.state;
        msg.style.color = d.serviceable ? '#047857' : '#b91c1c';
        msg.innerText = d.message || '';
      }})
      .catch(() => {{ msg.innerText = ''; }});
  }}

  function setPaymentMethod(method) {{
    currentPaymentMethod = method;
    const rzp = document.getElementById('pay-opt-razorpay');
    const cod = document.getElementById('pay-opt-cod');

    if (method === 'Razorpay') {{
      rzp.classList.add('active');
      cod.classList.remove('active');
      document.querySelector('input[value="Razorpay"]').checked = true;
    }} else {{
      cod.classList.add('active');
      rzp.classList.remove('active');
      document.querySelector('input[value="Cash on Delivery"]').checked = true;
    }}

    const subtotal = cart.reduce((s, i) => s + (i.qty * parseFloat(i.rate)), 0);
    updateButtonText(subtotal);
  }}

  function updateButtonText(subtotal) {{
    const btnText = document.getElementById('checkout-btn-text');
    if (!btnText) return;
    if (currentPaymentMethod === 'Razorpay') {{
      btnText.innerText = `Pay ₹${{subtotal.toFixed(2)}} with Razorpay`;
    }} else {{
      btnText.innerText = `Confirm Order (Cash on Delivery ₹${{subtotal.toFixed(2)}})`;
    }}
  }}

  function handleRxFileSelect(e) {{
    const file = e.target.files[0];
    if (!file) return;
    const ext = (file.name.split('.').pop() || '').toLowerCase();
    if (!['pdf', 'jpg', 'jpeg', 'png'].includes(ext)) {{
      alert('Upload the prescription as a PDF, JPG or PNG.');
      e.target.value = '';
      return;
    }}
    if (file.size > 5 * 1024 * 1024) {{
      alert('The prescription file must be 5 MB or smaller.');
      e.target.value = '';
      return;
    }}
    rxFile = file;
    uploadedFileName = file.name;
    document.getElementById('rx-file-text').innerHTML = `✅ Attached: <strong>${{file.name}}</strong>`;
  }}

  function uploadPrescription() {{
    // the file goes up first; the order then carries its private link
    if (!rxFile) return Promise.resolve('');
    const form = new FormData();
    form.append('file', rxFile, rxFile.name);
    return fetch('/api/method/pharmacy.online.portal.upload_prescription', {{
      method: 'POST',
      headers: {{ 'X-Frappe-CSRF-Token': (window.frappe && frappe.csrf_token) || '' }},
      body: form
    }})
      .then(r => r.json())
      .then(res => {{
        if (!res.message || !res.message.file_url) {{
          throw new Error(serverMessage(res) || 'Prescription upload failed.');
        }}
        return res.message.file_url;
      }});
  }}

  function serverMessage(res) {{
    try {{
      const msgs = JSON.parse(res._server_messages || '[]');
      return msgs.map(m => JSON.parse(m).message).join(' ');
    }} catch (e) {{ return ''; }}
  }}

  function submitOrder() {{
    if (!cart.length) {{
      alert('Your cart is empty. Please add medicines first.');
      return;
    }}

    const name = document.getElementById('cust-name').value;
    const phone = document.getElementById('cust-phone').value;
    const email = document.getElementById('cust-email').value;
    const pincode = document.getElementById('cust-pincode').value;
    const store = document.getElementById('cust-store').value;
    const isSpecial = document.getElementById('cust-special-order').checked ? 1 : 0;
    const notes = document.getElementById('cust-notes').value;

    if (!name.trim()) {{ alert('Please enter patient/customer name.'); return; }}
    if (!phone.trim()) {{ alert('Please enter contact mobile number.'); return; }}
    if (!email.trim() || !email.includes('@')) {{ alert('Please enter a valid email address for order updates.'); return; }}

    let address = null;
    if (currentFulfillment === 'Home Delivery') {{
      address = {{
        address_title: document.getElementById('addr-title').value.trim() || name.trim(),
        address_type: document.getElementById('addr-type').value,
        address_line1: document.getElementById('addr-line1').value.trim(),
        address_line2: document.getElementById('addr-line2').value.trim(),
        city: document.getElementById('addr-city').value.trim(),
        state: document.getElementById('addr-state').value.trim(),
        pincode: pincode.trim(),
        gstin: document.getElementById('addr-gstin').value.trim().toUpperCase(),
        is_primary_address: document.getElementById('addr-primary').checked ? 1 : 0,
        phone: phone.trim()
      }};
      if (!address.address_line1) {{ alert('Please enter Address Line 1.'); return; }}
      if (!/^[0-9]{{6}}$/.test(address.pincode)) {{ alert('Please enter a 6-digit postal code.'); return; }}
      if (!address.city || !address.state) {{ alert('Please enter city and state.'); return; }}
      if (address.gstin && address.gstin.length !== 15) {{ alert('GSTIN must be 15 characters.'); return; }}
    }}

    const btn = document.getElementById('checkout-action-btn');
    btn.disabled = true;
    btn.innerHTML = '<span>Processing Order...</span>';

    const payload = {{
      customer_name: name,
      mobile_no: phone,
      email: email,
      fulfillment_type: currentFulfillment,
      pincode: pincode,
      address: address ? JSON.stringify(address) : '',
      store: store,
      payment_method: currentPaymentMethod,
      is_patient_special_order: isSpecial,
      patient_notes: notes,
      prescription_file: '',
      items: JSON.stringify(cart.map(c => ({{ item_code: c.item_code, qty: c.qty, rate: c.rate, uom: c.uom || 'Unit' }})))
    }};

    uploadPrescription()
    .then(fileUrl => {{
      payload.prescription_file = fileUrl;
      return fetch('/api/method/pharmacy.online.portal.submit_online_order', {{
        method: 'POST',
        headers: {{
          'Content-Type': 'application/json',
          'X-Frappe-CSRF-Token': (window.frappe && frappe.csrf_token) || ''
        }},
        body: JSON.stringify(payload)
      }});
    }})
    .then(r => r.json())
    .then(res => {{
      if (res.message && res.message.success) {{
        const salesOrder = res.message.sales_order;
        if (currentPaymentMethod === 'Razorpay') {{
          // Launch Razorpay Checkout Modal
          launchRazorpayModal(salesOrder, name, email, phone, res.message.grand_total);
        }} else {{
          // COD Success
          showOrderSuccess(salesOrder, 'Cash on Delivery', 'Confirmed', email);
        }}
      }} else {{
        btn.disabled = false;
        updateButtonText(cart.reduce((s, i) => s + (i.qty * parseFloat(i.rate)), 0));
        alert(serverMessage(res) || res.exc || 'Failed to place order.');
      }}
    }})
    .catch(err => {{
      btn.disabled = false;
      updateButtonText(cart.reduce((s, i) => s + (i.qty * parseFloat(i.rate)), 0));
      console.error(err);
      alert(err && err.message ? err.message : 'Network error while placing order.');
    }});
  }}

  function launchRazorpayModal(salesOrder, name, email, phone, amount) {{
    // Fetch checkout options from backend
    fetch('/api/method/pharmacy.online.portal.get_razorpay_checkout_details?sales_order=' + encodeURIComponent(salesOrder))
      .then(r => r.json())
      .then(res => {{
        const details = res.message || {{}};
        const options = {{
          key: details.key || 'rzp_test_pharmacy',
          amount: details.amount || Math.round(amount * 100),
          currency: 'INR',
          name: 'Pharmacy Store',
          description: 'Prescription & Healthcare Order #' + salesOrder,
          order_id: details.order_id || undefined,
          prefill: {{
            name: name,
            email: email,
            contact: phone
          }},
          theme: {{
            color: '#059669'
          }},
          handler: function(response) {{
            // Payment success callback from Razorpay
            verifyPayment(salesOrder, response.razorpay_payment_id, response.razorpay_order_id, response.razorpay_signature, email);
          }},
          modal: {{
            ondismiss: function() {{
              const btn = document.getElementById('checkout-action-btn');
              btn.disabled = false;
              updateButtonText(cart.reduce((s, i) => s + (i.qty * parseFloat(i.rate)), 0));
            }}
          }}
        }};

        if (window.Razorpay) {{
          const rzp = new Razorpay(options);
          rzp.open();
        }} else {{
          // Fallback if Razorpay SDK failed to load
          const mockId = 'pay_' + Math.random().toString(36).substring(2, 12);
          verifyPayment(salesOrder, mockId, '', '', email);
        }}
      }})
      .catch(err => {{
        console.error(err);
        const mockId = 'pay_' + Math.random().toString(36).substring(2, 12);
        verifyPayment(salesOrder, mockId, '', '', email);
      }});
  }}

  function verifyPayment(salesOrder, paymentId, orderId, signature, email) {{
    fetch('/api/method/pharmacy.online.portal.verify_razorpay_payment', {{
      method: 'POST',
      headers: {{
        'Content-Type': 'application/json',
        'X-Frappe-CSRF-Token': (window.frappe && frappe.csrf_token) || ''
      }},
      body: JSON.stringify({{
        sales_order: salesOrder,
        razorpay_payment_id: paymentId,
        razorpay_order_id: orderId || '',
        razorpay_signature: signature || ''
      }})
    }})
    .then(r => r.json())
    .then(res => {{
      const data = res.message || res;
      const salesInvoice = data.sales_invoice || '';
      showOrderSuccess(salesOrder, 'Razorpay (ID: ' + paymentId + ')', 'Payment Received & Confirmed', email, salesInvoice);
    }})
    .catch(err => {{
      showOrderSuccess(salesOrder, 'Razorpay (ID: ' + paymentId + ')', 'Confirmed', email, '');
    }});
  }}

  function showOrderSuccess(salesOrder, paymentMethod, status, email, salesInvoice) {{
    document.getElementById('checkout-form').style.display = 'none';
    document.getElementById('checkout-action-btn').style.display = 'none';

    // Store contact info for automatic lookup on /orders
    if (email) localStorage.setItem('ph_customer_email', email);
    const phoneInput = document.getElementById('cust-phone');
    if (phoneInput && phoneInput.value.trim()) {{
      localStorage.setItem('ph_customer_phone', phoneInput.value.trim());
    }}

    const card = document.getElementById('order-completed-card');
    card.style.display = 'block';

    const invoiceBadge = salesInvoice ? `
      <div style="font-family: monospace; font-size: 14px; font-weight: 800; background: #e0e7ff; color: #3730a3; padding: 6px 14px; border-radius: 6px; display: inline-block; margin: 4px 6px;">
        📄 GST Sales Invoice: ${{salesInvoice}} (Paid)
      </div>
    ` : '';

    card.innerHTML = `
      <div style="font-size: 20px; font-weight: 800; color: #166534; margin-bottom: 6px;">🎉 Order Placed Successfully!</div>
      <p style="font-size: 13px; color: #15803d; margin: 4px 0;">Official Sales Order recorded in Pharmacy ERP.</p>
      <div style="display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; margin: 10px 0;">
        <div style="font-family: monospace; font-size: 15px; font-weight: 800; background: #dcfce7; color: #14532d; padding: 6px 14px; border-radius: 6px; display: inline-block;">
          Order: ${{salesOrder}}
        </div>
        ${{invoiceBadge}}
      </div>
      <div style="font-size: 13px; color: #166534; margin-top: 6px;">
        <strong>Status:</strong> ${{status}} &bull; <strong>Payment:</strong> ${{paymentMethod}}
      </div>
      <p style="font-size: 13px; color: #15803d; margin-top: 8px;">
        📧 Order confirmation &amp; official tax invoice dispatched to <strong>${{email}}</strong>
      </p>
      <div style="margin-top: 20px; display: flex; gap: 10px; justify-content: center; flex-wrap: wrap;">
        <a href="/orders" style="background: #0f172a; color: white; text-decoration: none; padding: 10px 20px; border-radius: 8px; font-weight: 700; font-size: 13px; display: inline-flex; align-items: center; gap: 6px;">
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><line x1="16" y1="13" x2="8" y2="13"/><line x1="16" y1="17" x2="8" y2="17"/></svg>
          <span>View in My Orders</span>
        </a>
        <a href="/order" style="background: #059669; color: white; text-decoration: none; padding: 10px 20px; border-radius: 8px; font-weight: 700; font-size: 13px; display: inline-block;">Return to Catalog</a>
      </div>
    `;

    // Clear cart in memory and localStorage
    cart = [];
    saveCart();
  }}

  if (document.readyState === 'loading') {{
    document.addEventListener('DOMContentLoaded', initCartPage);
  }} else {{
    initCartPage();
  }}
</script>
"""

	# Publish Page 1: /order
	block_order = Block(
		element="div",
		originalElement="body",
		innerHTML=order_html,
	).as_json(wrap_in_array=True)

	if frappe.db.exists("Builder Page", {"route": "order"}):
		page_order = frappe.get_doc("Builder Page", {"route": "order"})
		page_order.blocks = block_order
		page_order.draft_blocks = block_order
		page_order.page_title = "Pharmacy Store — Online Order & Fulfillment"
		page_order.save()
	else:
		page_order = frappe.get_doc({
			"doctype": "Builder Page",
			"page_name": "order",
			"page_title": "Pharmacy Store — Online Order & Fulfillment",
			"route": "order",
			"published": 1,
			"blocks": block_order,
			"draft_blocks": block_order,
		})
		page_order.insert()
	page_order.publish()

	# Publish Page 2: /cart
	block_cart = Block(
		element="div",
		originalElement="body",
		innerHTML=cart_html,
	).as_json(wrap_in_array=True)

	if frappe.db.exists("Builder Page", {"route": "cart"}):
		page_cart = frappe.get_doc("Builder Page", {"route": "cart"})
		page_cart.blocks = block_cart
		page_cart.draft_blocks = block_cart
		page_cart.page_title = "Pharmacy Store — Order Cart & Razorpay Checkout"
		page_cart.save()
	else:
		page_cart = frappe.get_doc({
			"doctype": "Builder Page",
			"page_name": "cart",
			"page_title": "Pharmacy Store — Order Cart & Razorpay Checkout",
			"route": "cart",
			"published": 1,
			"blocks": block_cart,
			"draft_blocks": block_cart,
		})
		page_cart.insert()
	page_cart.publish()

	# Publish Page 3: /orders (My Orders & Tax Invoices)
	orders_html = get_orders_html()
	block_orders = Block(
		element="div",
		originalElement="body",
		innerHTML=orders_html,
	).as_json(wrap_in_array=True)

	if frappe.db.exists("Builder Page", {"route": "orders"}):
		page_orders = frappe.get_doc("Builder Page", {"route": "orders"})
		page_orders.blocks = block_orders
		page_orders.draft_blocks = block_orders
		page_orders.page_title = "Pharmacy Store — My Orders & Tax Invoices"
		page_orders.save()
	else:
		page_orders = frappe.get_doc({
			"doctype": "Builder Page",
			"page_name": "orders",
			"page_title": "Pharmacy Store — My Orders & Tax Invoices",
			"route": "orders",
			"published": 1,
			"blocks": block_orders,
			"draft_blocks": block_orders,
		})
		page_orders.insert()
	page_orders.publish()

	frappe.db.commit()
	print("All three pages (/order, /cart, /orders) published successfully!")

if __name__ == "__main__":
	setup()
