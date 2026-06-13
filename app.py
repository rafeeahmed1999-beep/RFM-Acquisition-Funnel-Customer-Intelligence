import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
import io
import json
import requests
from datetime import datetime, timezone
from pathlib import Path

st.set_page_config(
    page_title="RFM & Acquisition Funnel Customer Intelligence",
    page_icon="◈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Serif+Display:ital@0;1&family=DM+Mono:wght@300;400;500&family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp { background-color: #0a0a0f; color: #e8e4dc; }

section[data-testid="stSidebar"] {
    background-color: #0f0f18;
    border-right: 1px solid #1e1e2e;
}
section[data-testid="stSidebar"] .stMarkdown p {
    color: #888; font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase;
}

h1 {
    font-family: 'DM Serif Display', serif !important;
    font-size: 2.4rem !important; color: #e8e4dc !important;
    letter-spacing: -0.02em; line-height: 1.1; margin-bottom: 4px !important;
}
h2 {
    font-family: 'DM Serif Display', serif !important;
    font-size: 1.6rem !important; color: #e8e4dc !important;
}
h3 {
    font-family: 'DM Sans', sans-serif !important;
    font-size: 0.75rem !important; color: #666 !important;
    letter-spacing: 0.12em !important; text-transform: uppercase !important;
    font-weight: 500 !important;
}

.stDownloadButton button {
    background: #e8e4dc !important; color: #0a0a0f !important;
    border: none !important; border-radius: 2px !important;
    font-family: 'DM Mono', monospace !important; font-size: 11px !important;
    letter-spacing: 0.08em !important; text-transform: uppercase !important;
    font-weight: 500 !important; padding: 8px 20px !important;
}
.stDownloadButton button:hover { background: #c8c4bc !important; }

hr { border-color: #1e1e2e !important; margin: 32px 0 !important; }

.stSelectbox label, .stMultiSelect label, .stTextInput label {
    color: #666 !important; font-size: 11px !important;
    letter-spacing: 0.08em !important; text-transform: uppercase !important;
    font-family: 'DM Mono', monospace !important;
}

.insight-box {
    background: #12121c; border-left: 2px solid #c8b87a;
    padding: 16px 20px; margin: 16px 0; border-radius: 0 4px 4px 0;
}
.insight-box p {
    color: #aaa; font-size: 13px; line-height: 1.6;
    margin: 0; font-family: 'DM Sans', sans-serif;
}
.insight-box strong {
    color: #c8b87a; font-family: 'DM Mono', monospace;
    font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase;
    display: block; margin-bottom: 6px;
}

.stTabs [data-baseweb="tab-list"] {
    background: transparent; border-bottom: 1px solid #1e1e2e; gap: 0;
}
.stTabs [data-baseweb="tab"] {
    background: transparent; color: #444;
    font-family: 'DM Mono', monospace; font-size: 11px;
    letter-spacing: 0.08em; text-transform: uppercase;
    padding: 12px 24px; border: none; border-bottom: 2px solid transparent;
}
.stTabs [aria-selected="true"] {
    color: #e8e4dc !important; border-bottom: 2px solid #c8b87a !important;
    background: transparent !important;
}
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
SEGMENT_COLOURS = {
    "Champions":           "#f0c040",
    "Loyal Customers":     "#8db87a",
    "Potential Loyalists": "#7ab8a8",
    "At Risk":             "#b87a7a",
    "Cannot Lose Them":    "#d4624a",
    "Hibernating":         "#666680",
    "New Customers":       "#7a8db8",
    "Promising":           "#9a7ab8",
    "Need Attention":      "#e8630a",
    "Lost":                "#444455",
}

SEGMENT_DESCRIPTIONS = {
    "Champions":           "Bought recently, buy often, spend the most. Reward them.",
    "Loyal Customers":     "Buy regularly with good frequency. Upsell higher-value products.",
    "Potential Loyalists": "Recent customers with above-average frequency. Nurture them.",
    "At Risk":             "Once-valuable customers who haven't returned. Re-engage urgently.",
    "Cannot Lose Them":    "Made big purchases but haven't been back. Win them back now.",
    "Hibernating":         "Low recency, low frequency, low spend. Low-cost re-engagement only.",
    "New Customers":       "Bought recently but only once. Onboard them well.",
    "Promising":           "Recent buyers with moderate spend. Build the relationship.",
    "Need Attention":      "Above average recency and frequency but haven't bought recently.",
    "Lost":                "Lowest scores across all three dimensions. May not be worth pursuing.",
}

SEGMENT_MIGRATION = {
    "Champions":           ("Loyal Customers", "90 days"),
    "Loyal Customers":     ("Need Attention",  "60 days"),
    "Potential Loyalists": ("Promising",        "45 days"),
    "At Risk":             ("Lost",             "30 days"),
    "Cannot Lose Them":    ("Lost",             "60 days"),
    "Hibernating":         ("Lost",             "90 days"),
    "New Customers":       ("Promising",        "30 days"),
    "Promising":           ("Hibernating",      "60 days"),
    "Need Attention":      ("At Risk",          "30 days"),
    "Lost":                (None,               None),
}

# ─────────────────────────────────────────────
# AUTOMATION HUB CONFIG — segment-triggered alert routing
# ─────────────────────────────────────────────
ALERT_ROUTING = {
    "Cannot Lose Them": {"priority": "Critical", "channel": "#customer-success-urgent", "action": "Personal outreach — phone or account manager"},
    "At Risk":          {"priority": "High",     "channel": "#customer-success",        "action": "Re-engagement email with time-limited incentive"},
    "Need Attention":   {"priority": "Medium",   "channel": "#lifecycle-marketing",      "action": "Nurture sequence before they slip to At Risk"},
    "New Customers":    {"priority": "Medium",   "channel": "#onboarding",               "action": "Onboarding sequence to drive second purchase"},
    "Promising":        {"priority": "Low",      "channel": "#lifecycle-marketing",      "action": "Add to nurture campaign"},
}

# ─────────────────────────────────────────────
# METRIC CARD HELPER
# ─────────────────────────────────────────────
def metric(label: str, value: str):
    st.markdown(
        f'''<div style="background:#12121c;border:1px solid #1e1e2e;border-radius:4px;
                    padding:20px 24px;margin-bottom:4px;">
          <div style="font-family:DM Mono,monospace;font-size:11px;color:#e8e4dc;
                      letter-spacing:0.1em;text-transform:uppercase;margin-bottom:6px;">
            {label}</div>
          <div style="font-family:DM Serif Display,serif;font-size:2rem;
                      color:#f0c040;line-height:1.1;">
            {value}</div>
        </div>''',
        unsafe_allow_html=True,
    )

# ─────────────────────────────────────────────
# PLOTLY HELPERS
# ─────────────────────────────────────────────
def base_layout(title_text=None, title_size=16):
    layout = dict(
        paper_bgcolor="#0a0a0f",
        plot_bgcolor="#0a0a0f",
        font=dict(family="DM Sans", color="#888", size=11),
        margin=dict(l=20, r=20, t=40, b=20),
        legend=dict(
            bgcolor="#12121c", bordercolor="#1e1e2e", borderwidth=1,
            font=dict(size=11, color="#888"),
        ),
    )
    if title_text:
        layout["title"] = dict(
            text=title_text,
            font=dict(family="DM Serif Display", size=title_size, color="#e8e4dc"),
        )
    return layout

# ─────────────────────────────────────────────
# DATASET METADATA
# ─────────────────────────────────────────────
DATASET_META = {
    "UK Gift Retailer — UCI Online Retail II": {
        "short_name": "UK Gift Retailer — UCI Online Retail II",
        "heading":    "UK Gift Retailer",
        "description": (
            "Transactional data from a UK-based online gift and homeware retailer, "
            "covering December 2009 to December 2011. Customers are predominantly "
            "wholesale buyers — small businesses and gift shops across the UK and Europe "
            "— purchasing decorative homewares, seasonal gifts, and novelty products."
        ),
        "loader":   "default",
        "currency": "£",
    },
    "Instacart — US Grocery Delivery": {
        "short_name": "Instacart",
        "heading":    "US Grocery Delivery",
        "description": (
            "Simulated grocery delivery behaviour modelled on Instacart's published "
            "platform statistics. Represents 8,000 customers with high purchase frequency "
            "and basket sizes of $15–$120. Recency and frequency dominate the segment "
            "distribution here — typical of subscription-style grocery services where "
            "customers shop weekly but monetary value per order is modest."
        ),
        "loader":   "instacart",
        "currency": "$",
    },
    "SaaS Platform — B2B Subscriptions": {
        "short_name": "SaaS Subscriptions — B2B Software",
        "heading":    "SaaS Subscriptions",
        "description": (
            "Simulated B2B SaaS subscription data modelled on mid-market software "
            "platform benchmarks. Customers represent businesses on monthly or annual "
            "plans across SMB, Mid-Market, and Enterprise tiers. Characterised by high "
            "annual contract values, low purchase frequency, and polarised recency — "
            "active accounts renew regularly while churned accounts show long gaps. "
            "The Cannot Lose Them segment is disproportionately valuable here."
        ),
        "loader":   "saas",
        "currency": "$",
    },
}

# ─────────────────────────────────────────────
# DATA LOADERS
# ─────────────────────────────────────────────
def clean_raw(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    rename = {
        "invoiceno":   "invoice",
        "customerid":  "customer_id",
        "unitprice":   "price",
        "invoicedate": "invoicedate",
    }
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    df = df[~df["invoice"].astype(str).str.startswith(("C", "A"))].copy()
    df = df.dropna(subset=["customer_id"])
    df["customer_id"] = df["customer_id"].astype(float).astype(int).astype(str)
    df = df[(df["price"] > 0) & (df["quantity"] > 0)].copy()
    df["invoicedate"] = pd.to_datetime(df["invoicedate"])
    df["revenue"]     = df["quantity"] * df["price"]
    return df


@st.cache_data(show_spinner=False)
def load_default() -> pd.DataFrame:
    path = Path(__file__).parent / "online_retail_II.csv"
    df   = pd.read_csv(str(path), encoding="latin-1")
    return clean_raw(df)


@st.cache_data(show_spinner=False)
def load_uploaded(file_bytes: bytes, filename: str) -> pd.DataFrame:
    if filename.endswith((".xlsx", ".xls")):
        try:
            df1 = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Year 2009-2010", engine="openpyxl")
            df2 = pd.read_excel(io.BytesIO(file_bytes), sheet_name="Year 2010-2011", engine="openpyxl")
            df  = pd.concat([df1, df2], ignore_index=True)
        except Exception:
            df = pd.read_excel(io.BytesIO(file_bytes), engine="openpyxl")
    else:
        df = pd.read_csv(io.BytesIO(file_bytes), encoding="latin-1")
    return clean_raw(df)


@st.cache_data(show_spinner=False)
def load_instacart() -> pd.DataFrame:
    rng         = np.random.default_rng(42)
    n_customers = 8000
    records     = []
    snapshot    = pd.Timestamp("2017-05-01")
    for cust_id in range(1, n_customers + 1):
        n_orders   = int(rng.integers(1, 30))
        days_since = int(rng.integers(0, 365))
        last_order = snapshot - pd.Timedelta(days=days_since)
        for o in range(n_orders):
            order_date = last_order - pd.Timedelta(days=int(rng.integers(0, 300)))
            n_items    = int(rng.integers(3, 25))
            basket_val = round(float(rng.uniform(15, 120)), 2)
            records.append({
                "customer_id": str(cust_id),
                "invoice":     f"ORD-{cust_id}-{o}",
                "invoicedate": order_date,
                "quantity":    n_items,
                "price":       round(basket_val / n_items, 2),
                "revenue":     basket_val,
            })
    df = pd.DataFrame(records)
    df["invoicedate"] = pd.to_datetime(df["invoicedate"])
    return df


@st.cache_data(show_spinner=False)
def load_saas() -> pd.DataFrame:
    rng         = np.random.default_rng(99)
    n_customers = 3000
    records     = []
    snapshot    = pd.Timestamp("2024-01-01")
    tiers = {
        "smb":        {"weight": 0.6, "mrr": (200,  800),  "tenure": (1, 18),  "churn_prob": 0.35},
        "midmarket":  {"weight": 0.3, "mrr": (800,  2500), "tenure": (6, 36),  "churn_prob": 0.20},
        "enterprise": {"weight": 0.1, "mrr": (2500, 8000), "tenure": (12, 60), "churn_prob": 0.08},
    }
    for cust_id in range(1, n_customers + 1):
        tier_name = rng.choice(list(tiers.keys()), p=[tiers[t]["weight"] for t in tiers])
        tier      = tiers[tier_name]
        mrr       = round(float(rng.uniform(*tier["mrr"])), 2)
        tenure    = int(rng.integers(*tier["tenure"]))
        churned   = rng.random() < tier["churn_prob"]
        if churned:
            months_since_churn = int(rng.integers(2, 18))
            last_payment  = snapshot - pd.DateOffset(months=months_since_churn)
            active_months = max(1, tenure - months_since_churn)
        else:
            last_payment  = snapshot - pd.DateOffset(months=int(rng.integers(0, 2)))
            active_months = tenure
        for m in range(active_months):
            payment_date = last_payment - pd.DateOffset(months=m)
            if tier_name == "enterprise" and m % 12 != 0:
                continue
            records.append({
                "customer_id": f"CUST-{cust_id:04d}",
                "invoice":     f"INV-{cust_id}-{m}",
                "invoicedate": payment_date,
                "quantity":    1,
                "price":       mrr if tier_name != "enterprise" else mrr * 12,
                "revenue":     mrr if tier_name != "enterprise" else mrr * 12,
            })
    df = pd.DataFrame(records)
    df["invoicedate"] = pd.to_datetime(df["invoicedate"])
    return df


@st.cache_data(show_spinner=False)
def compute_rfm(df: pd.DataFrame) -> pd.DataFrame:
    snapshot = df["invoicedate"].max() + pd.Timedelta(days=1)
    rfm = df.groupby("customer_id").agg(
        last_purchase=("invoicedate", "max"),
        frequency    =("invoice",     "nunique"),
        monetary     =("revenue",     "sum"),
    ).reset_index()
    rfm["recency"] = (snapshot - rfm["last_purchase"]).dt.days
    def safe_score(series, ascending=True):
        """Rank-based 1-5 scoring that always produces 5 distinct values."""
        ranked = series.rank(method="first", ascending=ascending)
        return (pd.qcut(ranked, q=5, labels=[1, 2, 3, 4, 5], duplicates="drop")
                  .cat.codes.add(1).clip(1, 5))

    rfm["r_score"] = safe_score(rfm["recency"],   ascending=False)  # lower recency = better
    rfm["f_score"] = safe_score(rfm["frequency"],  ascending=True)
    rfm["m_score"] = safe_score(rfm["monetary"],   ascending=True)
    rfm["rfm_score"]   = (rfm["r_score"].astype(str)
                          + rfm["f_score"].astype(str)
                          + rfm["m_score"].astype(str))
    rfm["rfm_numeric"] = rfm["r_score"] + rfm["f_score"] + rfm["m_score"]

    def segment(row):
        r, f, m = row["r_score"], row["f_score"], row["m_score"]
        if r >= 4 and f >= 4 and m >= 4:  return "Champions"
        if r >= 3 and f >= 3 and m >= 3:  return "Loyal Customers"
        if r >= 4 and f <= 2:             return "New Customers"
        if r >= 3 and f >= 2 and m >= 2:  return "Potential Loyalists"
        if r >= 3 and f <= 2 and m <= 2:  return "Promising"
        if r == 2 and f >= 3 and m >= 3:  return "Need Attention"
        if r <= 2 and f >= 4 and m >= 4:  return "Cannot Lose Them"
        if r <= 2 and f >= 2 and m >= 2:  return "At Risk"
        if r >= 2 and f <= 2 and m <= 2:  return "Hibernating"
        return "Lost"

    rfm["segment"] = rfm.apply(segment, axis=1)
    return rfm.sort_values("monetary", ascending=False).reset_index(drop=True)


def make_targeting_list(rfm: pd.DataFrame, segments: list, currency: str) -> pd.DataFrame:
    cols = ["customer_id", "segment", "recency", "frequency", "monetary",
            "r_score", "f_score", "m_score", "rfm_score"]
    out = rfm[rfm["segment"].isin(segments)][cols].copy()
    out["monetary"] = out["monetary"].round(2)
    return out.rename(columns={
        "customer_id": "Customer ID",   "segment":   "Segment",
        "recency":     "Days Since Last Purchase",
        "frequency":   "Number of Orders",
        "monetary":    f"Total Spend ({currency})",
        "r_score": "R Score", "f_score": "F Score",
        "m_score": "M Score", "rfm_score": "RFM Score",
    }).reset_index(drop=True)


# ─────────────────────────────────────────────
# SIDEBAR
# ─────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ◈ RFM & Acquisition Funnel")
    st.markdown("---")
    st.markdown("**Demo Dataset**")
    dataset_choice = st.selectbox(
        "Select a dataset",
        options=list(DATASET_META.keys()),
        help="Switch datasets to see how RFM segments shift across industries.",
    )
    st.markdown(
        "<p>Switch datasets above to see RFM segmentation applied "
        "across retail, grocery, and SaaS industries.</p>",
        unsafe_allow_html=True,
    )
    st.markdown("---")
    st.markdown("**Custom Dataset**")
    uploaded = st.file_uploader(
        "Upload your own retail data",
        type=["xlsx", "csv"],
        help="Optional — overrides the demo dataset above.",
    )
    st.markdown("---")
    st.markdown("**Targeting Export**")
    all_segments = list(SEGMENT_COLOURS.keys())
    selected_segments = st.multiselect(
        "Segments to export",
        options=all_segments,
        default=["Champions", "At Risk", "Cannot Lose Them"],
    )

# ─────────────────────────────────────────────
# LOAD DATA
# ─────────────────────────────────────────────
meta       = DATASET_META[dataset_choice]
currency   = meta["currency"] if uploaded is None else "£"
short_name = uploaded.name if uploaded else meta["short_name"]
heading    = (uploaded.name) if uploaded else meta["heading"]
desc_text  = "Custom uploaded dataset." if uploaded else meta["description"]

with st.spinner("Loading dataset..."):
    try:
        if uploaded is not None:
            df_raw = load_uploaded(uploaded.read(), uploaded.name)
        elif meta["loader"] == "default":
            df_raw = load_default()
        elif meta["loader"] == "instacart":
            df_raw = load_instacart()
        else:
            df_raw = load_saas()
    except Exception as e:
        st.error(f"Failed to load data: {e}")
        st.stop()

if df_raw.empty:
    st.warning("No data after applying filters.")
    st.stop()

with st.spinner("Computing RFM scores..."):
    rfm = compute_rfm(df_raw)

# ── Page heading ──
st.markdown(f"<h1>{heading}</h1>", unsafe_allow_html=True)

# ── Subheading: dataset stats line ──
st.markdown(
    f"<p style='font-family:DM Mono,monospace;font-size:12px;color:#555;"
    f"letter-spacing:0.06em;margin-top:2px;margin-bottom:10px;'>"
    f"{short_name} &nbsp;·&nbsp; {len(df_raw):,} transactions &nbsp;·&nbsp; "
    f"{len(rfm):,} customers &nbsp;·&nbsp; "
    f"{df_raw['invoicedate'].min().strftime('%d %b %Y')} – "
    f"{df_raw['invoicedate'].max().strftime('%d %b %Y')}</p>",
    unsafe_allow_html=True,
)

# ── Description body ──
st.markdown(
    f"<p style='font-family:DM Sans,sans-serif;font-size:14px;color:#888;"
    f"max-width:860px;line-height:1.7;margin-bottom:20px;'>{desc_text}</p>",
    unsafe_allow_html=True,
)

st.markdown("---")

# ─────────────────────────────────────────────
# REVENUE AT RISK BANNER
# ─────────────────────────────────────────────
at_risk_rev   = rfm[rfm["segment"].isin(["At Risk", "Cannot Lose Them"])]["monetary"].sum()
at_risk_count = rfm[rfm["segment"].isin(["At Risk", "Cannot Lose Them"])]["customer_id"].count()
pct_of_total  = at_risk_rev / rfm["monetary"].sum() * 100

st.markdown(f"""
<div style="background:#1a0a0a;border:1px solid #d4624a;border-left:4px solid #d4624a;
            border-radius:6px;padding:16px 24px;margin-bottom:24px;
            display:flex;align-items:center;gap:32px;">
  <div>
    <div style="font-family:'DM Mono',monospace;font-size:10px;color:#d4624a;
                letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px;">
      Revenue at Risk</div>
    <div style="font-family:'DM Serif Display',serif;font-size:2rem;color:#e8e4dc;">
      {currency}{at_risk_rev:,.0f}</div>
  </div>
  <div>
    <div style="font-family:'DM Mono',monospace;font-size:10px;color:#d4624a;
                letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px;">
      At-Risk Customers</div>
    <div style="font-family:'DM Serif Display',serif;font-size:2rem;color:#e8e4dc;">
      {at_risk_count:,}</div>
  </div>
  <div>
    <div style="font-family:'DM Mono',monospace;font-size:10px;color:#d4624a;
                letter-spacing:.1em;text-transform:uppercase;margin-bottom:4px;">
      % of Total Revenue</div>
    <div style="font-family:'DM Serif Display',serif;font-size:2rem;color:#e8e4dc;">
      {pct_of_total:.1f}%</div>
  </div>
  <div style="flex:1;font-family:'DM Sans',sans-serif;font-size:13px;color:#666;
              line-height:1.6;border-left:1px solid #2a1a1a;padding-left:24px;">
    Combined revenue from <b style="color:#aaa;">At Risk</b> and
    <b style="color:#aaa;">Cannot Lose Them</b> segments.
    These customers have lapsed but retain high lifetime value.
    Immediate re-engagement is recommended.
  </div>
</div>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────
# TOP METRICS
# ─────────────────────────────────────────────
m1, m2, m3, m4, m5 = st.columns(5)
with m1: metric("Customers",            f"{len(rfm):,}")
with m2: metric("Total Revenue",        f"{currency}{df_raw['revenue'].sum():,.0f}")
with m3: metric("Avg Order Value",      f"{currency}{df_raw.groupby('invoice')['revenue'].sum().mean():,.2f}")
with m4: metric("Avg Orders/Customer",  f"{rfm['frequency'].mean():.1f}x")
with m5: metric("Avg Days Since Order", f"{rfm['recency'].mean():.0f}d")

st.markdown("---")

# ─────────────────────────────────────────────
# TABS
# ─────────────────────────────────────────────
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "Segment Overview",
    "RFM Distribution",
    "Cohort Retention",
    "Acquisition Funnel",
    "Customer Explorer",
    "Targeting Export",
    "Automation Hub",
])

# ══════════════════════════════════════════
# TAB 1 — SEGMENT OVERVIEW
# ══════════════════════════════════════════
with tab1:
    st.markdown("## Segment Overview")

    seg = rfm.groupby("segment").agg(
        customers    =("customer_id", "count"),
        avg_recency  =("recency",     "mean"),
        avg_frequency=("frequency",   "mean"),
        avg_monetary =("monetary",    "mean"),
        total_revenue=("monetary",    "sum"),
    ).reset_index()
    seg["pct_customers"] = (seg["customers"]     / len(rfm)              * 100).round(1)
    seg["pct_revenue"]   = (seg["total_revenue"] / rfm["monetary"].sum() * 100).round(1)
    seg = seg.sort_values("total_revenue", ascending=False).reset_index(drop=True)

    c1, c2 = st.columns(2)

    with c1:
        fig_tree = px.treemap(
            seg, path=["segment"], values="customers",
            color="segment", color_discrete_map=SEGMENT_COLOURS,
        )
        fig_tree.update_layout(**base_layout("Customer Distribution by Segment"))
        fig_tree.update_traces(
            textfont=dict(family="DM Sans", size=12),
            marker=dict(line=dict(color="#0a0a0f", width=2)),
        )
        st.plotly_chart(fig_tree, use_container_width=True)

    with c2:
        seg_rev = seg.sort_values("total_revenue")
        fig_rev = go.Figure(go.Bar(
            x=seg_rev["total_revenue"],
            y=seg_rev["segment"],
            orientation="h",
            marker_color=[SEGMENT_COLOURS.get(s, "#888") for s in seg_rev["segment"]],
            text=[f"{currency}{v:,.0f}" for v in seg_rev["total_revenue"]],
            textposition="outside",
            textfont=dict(family="DM Mono", size=10, color="#888"),
        ))
        fig_rev.update_layout(
            **base_layout("Revenue by Segment"),
            showlegend=False,
            xaxis=dict(showticklabels=False,
                       gridcolor="#1a1a25", zerolinecolor="#1a1a25"),
            yaxis=dict(gridcolor="rgba(0,0,0,0)",
                       tickfont=dict(size=11, color="#888")),
        )
        st.plotly_chart(fig_rev, use_container_width=True)

    st.markdown("## Segment Detail")
    for i in range(0, len(seg), 2):
        cols = st.columns(2)
        for j in range(2):
            if i + j >= len(seg):
                break
            row        = seg.iloc[i + j]
            colour     = SEGMENT_COLOURS.get(row["segment"], "#888")
            desc       = SEGMENT_DESCRIPTIONS.get(row["segment"], "")
            mig_seg, mig_days = SEGMENT_MIGRATION.get(row["segment"], (None, None))
            mig_colour = SEGMENT_COLOURS.get(mig_seg, "#888") if mig_seg else "#888"
            migration_html = (
                f"<div style='font-family:DM Mono,monospace;font-size:10px;"
                f"color:#555;margin-top:8px;'>→ Moves to "
                f"<span style='color:{mig_colour}'>{mig_seg}</span> "
                f"without engagement within {mig_days}</div>"
                if mig_seg else ""
            )
            with cols[j]:
                st.markdown(f"""
                <div style="background:#12121c;border:1px solid #1e1e2e;
                            border-top:2px solid {colour};border-radius:4px;
                            padding:20px 24px;margin-bottom:16px;">
                  <div style="font-family:'DM Mono',monospace;font-size:10px;
                              color:{colour};letter-spacing:.1em;
                              text-transform:uppercase;margin-bottom:8px;">
                    {row['segment']}</div>
                  <div style="font-family:'DM Serif Display',serif;
                              font-size:2rem;color:#e8e4dc;margin-bottom:4px;">
                    {row['customers']:,}</div>
                  <div style="font-family:'DM Mono',monospace;font-size:11px;
                              color:#555;margin-bottom:12px;">
                    {row['pct_customers']}% of customers
                    · {row['pct_revenue']}% of revenue</div>
                  <div style="display:grid;grid-template-columns:1fr 1fr 1fr;
                              gap:8px;margin-bottom:12px;">
                    <div>
                      <div style="font-family:'DM Mono',monospace;font-size:9px;
                                  color:#444;text-transform:uppercase;">Avg Recency</div>
                      <div style="font-family:'DM Serif Display',serif;
                                  font-size:1.1rem;color:#aaa;">{row['avg_recency']:.0f}d</div>
                    </div>
                    <div>
                      <div style="font-family:'DM Mono',monospace;font-size:9px;
                                  color:#444;text-transform:uppercase;">Avg Orders</div>
                      <div style="font-family:'DM Serif Display',serif;
                                  font-size:1.1rem;color:#aaa;">{row['avg_frequency']:.1f}x</div>
                    </div>
                    <div>
                      <div style="font-family:'DM Mono',monospace;font-size:9px;
                                  color:#444;text-transform:uppercase;">Avg Spend</div>
                      <div style="font-family:'DM Serif Display',serif;
                                  font-size:1.1rem;color:#aaa;">{currency}{row['avg_monetary']:,.0f}</div>
                    </div>
                  </div>
                  <div style="font-family:'DM Sans',sans-serif;font-size:12px;
                              color:#555;line-height:1.5;
                              border-top:1px solid #1e1e2e;padding-top:12px;">
                    {desc}{migration_html}
                  </div>
                </div>
                """, unsafe_allow_html=True)

# ══════════════════════════════════════════
# TAB 2 — RFM DISTRIBUTION
# ══════════════════════════════════════════
with tab2:
    st.markdown("## RFM Score Distributions")

    d1, d2 = st.columns(2)

    with d1:
        pivot = (rfm.groupby(["r_score", "f_score"])["monetary"]
                    .mean().reset_index()
                    .pivot(index="r_score", columns="f_score", values="monetary")
                    .fillna(0))
        fig_heat = go.Figure(go.Heatmap(
            z=pivot.values,
            x=[f"F={c}" for c in pivot.columns],
            y=[f"R={r}" for r in pivot.index],
            colorscale=[[0, "#12121c"], [0.5, "#8b6914"], [1, "#f0c040"]],
            text=[[f"{currency}{v:,.0f}" for v in row] for row in pivot.values],
            texttemplate="%{text}",
            textfont=dict(family="DM Mono", size=10),
            showscale=True,
            colorbar=dict(tickfont=dict(family="DM Mono", size=10, color="#888")),
        ))
        fig_heat.update_layout(
            **base_layout("Avg Spend by Recency × Frequency Score"),
            xaxis=dict(tickfont=dict(family="DM Mono", size=11),
                       gridcolor="rgba(0,0,0,0)"),
            yaxis=dict(tickfont=dict(family="DM Mono", size=11),
                       gridcolor="rgba(0,0,0,0)"),
        )
        st.plotly_chart(fig_heat, use_container_width=True)
        st.markdown("""
        <div class="insight-box">
          <strong>Reading this chart</strong>
          <p>Each cell shows average total lifetime spend at that R×F score combination.
          Gold = high value. Top-right (R=5, F=5) represents your most recent and most
          frequent buyers — but this is not always the highest-spend cell, and that is
          expected. A customer who ordered 3 times but spent £800 each time will score
          lower on frequency than one who orders 20 times at £15 each, but their monetary
          value is far higher. High M at low F typically indicates bulk or wholesale buyers.
          This is why RFM uses three dimensions separately rather than combining them.</p>
        </div>""", unsafe_allow_html=True)

    with d2:
        fig_scatter = px.scatter(
            rfm.sample(min(2000, len(rfm)), random_state=42),
            x="recency", y="monetary",
            color="segment", color_discrete_map=SEGMENT_COLOURS,
            opacity=0.75, size="frequency", size_max=14,
        )
        fig_scatter.update_layout(
            **base_layout("Recency vs Monetary Value"),
            xaxis=dict(title="Days Since Last Purchase",
                       title_font=dict(family="DM Mono", size=11, color="#666"),
                       gridcolor="#1a1a25", zerolinecolor="#1a1a25"),
            yaxis=dict(title=f"Total Spend ({currency})",
                       title_font=dict(family="DM Mono", size=11, color="#666"),
                       gridcolor="#1a1a25", zerolinecolor="#1a1a25"),
        )
        st.plotly_chart(fig_scatter, use_container_width=True)
        st.markdown("""
        <div class="insight-box">
          <strong>Reading this chart</strong>
          <p>Bubble size = purchase frequency. High-spend customers clustering
          right are lapsing — At Risk and Cannot Lose Them segments.</p>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    h1, h2, h3 = st.columns(3)
    for series, label, ylabel, col in [
        (rfm["recency"],   "Recency — Days Since Last Purchase",   "Number of Customers",   h1),
        (rfm["frequency"], "Frequency — Number of Orders",          "Number of Customers",   h2),
        (rfm["monetary"],  f"Monetary — Total Spend ({currency})",  "Number of Customers",   h3),
    ]:
        with col:
            fig_hist = px.histogram(rfm, x=series, nbins=40,
                                    color_discrete_sequence=["#c8b87a"])
            fig_hist.update_layout(
                **base_layout(label, title_size=13),
                showlegend=False,
                bargap=0.05,
                xaxis=dict(gridcolor="#1a1a25", zerolinecolor="#1a1a25"),
                yaxis=dict(
                    title=ylabel,
                    title_font=dict(family="DM Mono", size=11, color="#666"),
                    gridcolor="#1a1a25", zerolinecolor="#1a1a25",
                ),
            )
            fig_hist.update_traces(
                marker_line_color="#0a0a0f", marker_line_width=0.5)
            st.plotly_chart(fig_hist, use_container_width=True)

# ══════════════════════════════════════════
# TAB 3 — COHORT RETENTION
# ══════════════════════════════════════════
with tab3:
    st.markdown("## Cohort Retention Analysis")
    st.markdown("""
    <div class="insight-box">
      <strong>What this shows</strong>
      <p>Each row is a cohort of customers acquired in a given month.
      Each column shows what percentage of that cohort made another purchase
      1, 2, 3… months later. Strong retention shows as colour persisting
      across rows. Drop-off shows where customers stop returning.</p>
    </div>""", unsafe_allow_html=True)

    cohort_df = df_raw[["customer_id", "invoicedate", "invoice"]].copy()
    cohort_df["order_month"]  = cohort_df["invoicedate"].dt.to_period("M")
    cohort_df["cohort_month"] = (cohort_df
                                  .groupby("customer_id")["invoicedate"]
                                  .transform("min")
                                  .dt.to_period("M"))
    cohort_df["cohort_index"] = (
        (cohort_df["order_month"] - cohort_df["cohort_month"])
        .apply(lambda x: x.n)
    )
    cohort_counts = (cohort_df
                     .groupby(["cohort_month", "cohort_index"])["customer_id"]
                     .nunique().reset_index())
    cohort_pivot  = cohort_counts.pivot(
        index="cohort_month", columns="cohort_index", values="customer_id"
    )
    cohort_pivot  = cohort_pivot.iloc[-18:, :13]
    cohort_sizes  = cohort_pivot[0]
    retention     = cohort_pivot.divide(cohort_sizes, axis=0).round(3)

    fig_cohort = go.Figure(go.Heatmap(
        z=retention.values * 100,
        x=[f"Month {i}" for i in retention.columns],
        y=[str(c) for c in retention.index],
        colorscale=[[0, "#0a0a0f"], [0.3, "#1a2a1a"], [0.6, "#4a8a4a"], [1, "#f0c040"]],
        text=[[f"{v:.0f}%" if not np.isnan(v) else "" for v in row]
              for row in retention.values * 100],
        texttemplate="%{text}",
        textfont=dict(family="DM Mono", size=9),
        showscale=True,
        zmin=0, zmax=100,
        colorbar=dict(
            title=dict(text="Retention %",
                       font=dict(family="DM Mono", size=10, color="#888")),
            tickfont=dict(family="DM Mono", size=10, color="#888"),
        ),
    ))
    fig_cohort.update_layout(
        **base_layout("Monthly Cohort Retention — % Still Active"),
        height=520,
        xaxis=dict(tickfont=dict(family="DM Mono", size=10),
                   gridcolor="rgba(0,0,0,0)"),
        yaxis=dict(tickfont=dict(family="DM Mono", size=10),
                   gridcolor="rgba(0,0,0,0)", autorange="reversed"),
    )
    st.plotly_chart(fig_cohort, use_container_width=True)

    avg_retention = retention.mean(axis=0).dropna() * 100
    fig_curve = go.Figure(go.Scatter(
        x=[f"Month {i}" for i in avg_retention.index],
        y=avg_retention.values,
        mode="lines+markers",
        line=dict(color="#f0c040", width=2),
        marker=dict(color="#f0c040", size=6),
        fill="tozeroy",
        fillcolor="rgba(240,192,64,0.08)",
    ))
    fig_curve.update_layout(
        **base_layout("Average Retention Curve Across All Cohorts"),
        xaxis=dict(gridcolor="#1a1a25", zerolinecolor="#1a1a25"),
        yaxis=dict(
            title="Retention %",
            title_font=dict(family="DM Mono", size=11, color="#666"),
            gridcolor="#1a1a25", zerolinecolor="#1a1a25",
            range=[0, 100],
        ),
        showlegend=False,
    )
    st.plotly_chart(fig_curve, use_container_width=True)

    if len(avg_retention) >= 2:
        m1_ret = avg_retention.iloc[1] if len(avg_retention) > 1 else 0
        m3_ret = avg_retention.iloc[3] if len(avg_retention) > 3 else 0
        st.markdown(f"""
        <div class="insight-box">
          <strong>Key Retention Figures</strong>
          <p>Month 1 retention: <b style="color:#e8e4dc;">{m1_ret:.1f}%</b> of customers
          return the following month.
          Month 3 retention: <b style="color:#e8e4dc;">{m3_ret:.1f}%</b>.
          {'Strong early retention — focus on converting Month-1 returners into Loyal Customers.' if m1_ret > 30
           else 'Low Month-1 retention — onboarding improvement would have the highest impact.'}</p>
        </div>""", unsafe_allow_html=True)


# ══════════════════════════════════════════
# TAB 4 — ACQUISITION FUNNEL (SQL)
# ══════════════════════════════════════════
with tab4:
    st.markdown("## Acquisition Funnel — Time to Second Purchase")
    st.markdown("""
    <div class="insight-box">
      <strong>What this shows</strong>
      <p>The time between a customer's first and second purchase is one of the
      strongest predictors of long-term retention. Customers who return quickly
      after their first order are far more likely to become loyal. This analysis
      uses SQL CTEs to identify each customer's first and second purchase date,
      compute the gap in days, and distribute that gap across RFM segments.
      Customers with only one order are classified as single-purchase and tracked
      separately — they represent the top of your re-engagement funnel.</p>
    </div>""", unsafe_allow_html=True)

    import sqlite3

    # ── Run SQL to compute first and second purchase per customer ──
    conn = sqlite3.connect(":memory:")
    tx = df_raw[["customer_id", "invoicedate", "invoice"]].copy()
    tx["invoicedate_str"] = tx["invoicedate"].dt.strftime("%Y-%m-%d")
    tx.to_sql("transactions", conn, index=False, if_exists="replace")

    funnel_sql = """
    WITH ranked_orders AS (
        SELECT
            customer_id,
            invoicedate_str                         AS order_date,
            ROW_NUMBER() OVER (
                PARTITION BY customer_id
                ORDER BY invoicedate_str ASC
            )                                       AS order_rank
        FROM (
            SELECT DISTINCT customer_id, invoicedate_str
            FROM transactions
        ) AS distinct_dates
    ),
    first_purchase AS (
        SELECT customer_id, order_date AS first_date
        FROM ranked_orders
        WHERE order_rank = 1
    ),
    second_purchase AS (
        SELECT customer_id, order_date AS second_date
        FROM ranked_orders
        WHERE order_rank = 2
    )
    SELECT
        f.customer_id,
        f.first_date,
        s.second_date,
        CAST(
            (julianday(s.second_date) - julianday(f.first_date))
            AS INTEGER
        )                                           AS days_to_second_purchase
    FROM first_purchase f
    LEFT JOIN second_purchase s
        ON f.customer_id = s.customer_id
    """

    funnel_df = pd.read_sql_query(funnel_sql, conn)
    conn.close()

    converted   = funnel_df.dropna(subset=["second_date"]).copy()
    single_only = funnel_df[funnel_df["second_date"].isna()].copy()

    conversion_rate = len(converted) / len(funnel_df) * 100
    median_days     = converted["days_to_second_purchase"].median()
    pct_within_30   = (converted["days_to_second_purchase"] <= 30).mean() * 100

    fa, fb, fc, fd = st.columns(4)
    with fa: metric("Total Customers",           f"{len(funnel_df):,}")
    with fb: metric("Made a 2nd Purchase",       f"{len(converted):,}")
    with fc: metric("Single-Purchase Only",      f"{len(single_only):,}")
    with fd: metric("Conversion Rate",           f"{conversion_rate:.1f}%")

    st.markdown("---")

    f1, f2 = st.columns(2)

    with f1:
        # Distribution of days to second purchase (capped at 365 for readability)
        plot_data = converted[converted["days_to_second_purchase"] <= 365].copy()
        fig_funnel = px.histogram(
            plot_data, x="days_to_second_purchase", nbins=50,
            color_discrete_sequence=["#c8b87a"],
        )
        fig_funnel.add_vline(
            x=30, line=dict(color="#d4624a", width=1.5, dash="dash"),
            annotation_text="30 days",
            annotation_font=dict(family="DM Mono", size=10, color="#d4624a"),
        )
        fig_funnel.add_vline(
            x=float(median_days), line=dict(color="#f0c040", width=1.5, dash="dot"),
            annotation_text=f"Median: {median_days:.0f}d",
            annotation_font=dict(family="DM Mono", size=10, color="#f0c040"),
        )
        fig_funnel.update_layout(
            **base_layout("Days Between First and Second Purchase"),
            showlegend=False,
            bargap=0.05,
            xaxis=dict(
                title="Days to Second Purchase",
                title_font=dict(family="DM Mono", size=11, color="#666"),
                gridcolor="#1a1a25", zerolinecolor="#1a1a25",
            ),
            yaxis=dict(
                title="Number of Customers",
                title_font=dict(family="DM Mono", size=11, color="#666"),
                gridcolor="#1a1a25", zerolinecolor="#1a1a25",
            ),
        )
        fig_funnel.update_traces(marker_line_color="#0a0a0f", marker_line_width=0.5)
        st.plotly_chart(fig_funnel, use_container_width=True)
        st.markdown(f"""
        <div class="insight-box">
          <strong>Conversion speed</strong>
          <p>Median time to second purchase: <b style="color:#e8e4dc;">{median_days:.0f} days</b>.
          <b style="color:#e8e4dc;">{pct_within_30:.1f}%</b> of returning customers come back
          within 30 days. Customers who return within 30 days are your highest-probability
          Loyal Customer candidates — they are the primary target for onboarding sequences.</p>
        </div>""", unsafe_allow_html=True)

    with f2:
        # Funnel by RFM segment: what % of each segment made a 2nd purchase
        seg_funnel = (
            funnel_df
            .merge(rfm[["customer_id", "segment"]], on="customer_id", how="left")
            .groupby("segment")
            .agg(
                total        =("customer_id", "count"),
                converted    =("second_date", lambda x: x.notna().sum()),
                median_days  =("days_to_second_purchase", "median"),
            )
            .reset_index()
        )
        seg_funnel["pct_converted"] = (
            seg_funnel["converted"] / seg_funnel["total"] * 100
        ).round(1)
        seg_funnel = seg_funnel.sort_values("pct_converted", ascending=True)

        fig_seg = go.Figure(go.Bar(
            x=seg_funnel["pct_converted"],
            y=seg_funnel["segment"],
            orientation="h",
            marker_color=[SEGMENT_COLOURS.get(s, "#888") for s in seg_funnel["segment"]],
            text=[f"{v:.0f}%" for v in seg_funnel["pct_converted"]],
            textposition="outside",
            textfont=dict(family="DM Mono", size=10, color="#888"),
        ))
        fig_seg.update_layout(
            **base_layout("% of Segment That Made a Second Purchase"),
            showlegend=False,
            xaxis=dict(
                title="% Who Returned",
                title_font=dict(family="DM Mono", size=11, color="#666"),
                range=[0, 110],
                gridcolor="#1a1a25", zerolinecolor="#1a1a25",
            ),
            yaxis=dict(gridcolor="rgba(0,0,0,0)",
                       tickfont=dict(size=11, color="#888")),
        )
        st.plotly_chart(fig_seg, use_container_width=True)
        st.markdown("""
        <div class="insight-box">
          <strong>Segment re-purchase rates</strong>
          <p>Champions and Loyal Customers show near-100% second purchase rates by
          definition. The insight here is in the middle segments: Promising and
          Potential Loyalists with high conversion rates are candidates for loyalty
          nurture campaigns. Low conversion in New Customers signals an onboarding gap.</p>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### SQL Query")
    with st.expander("View the CTE query used to compute this analysis"):
        st.code(funnel_sql, language="sql")
    st.markdown("""
    <div class="insight-box">
      <strong>Methodology note</strong>
      <p>First and second purchase dates are identified using ROW_NUMBER() partitioned
      by customer, ordered by date ascending. The gap is computed using SQLite's
      julianday() function. Customers with only one distinct purchase date are retained
      in the dataset as single-purchase customers and excluded from the days distribution
      chart, but included in the conversion rate metric.</p>
    </div>""", unsafe_allow_html=True)

# ══════════════════════════════════════════
# TAB 5 — CUSTOMER EXPLORER
# ══════════════════════════════════════════
with tab5:
    st.markdown("## Customer Explorer")

    s1, s2, s3 = st.columns([1, 2, 1])
    with s1:
        search_id = st.text_input("Search by Customer ID", placeholder="e.g. 12345")
    with s2:
        seg_filter = st.multiselect(
            "Filter by segment", options=all_segments, default=all_segments)
    with s3:
        sort_col = st.selectbox(
            "Sort by", ["monetary", "frequency", "recency", "rfm_numeric"])

    view = rfm[rfm["segment"].isin(seg_filter)].copy()
    if search_id.strip():
        view = view[view["customer_id"].str.contains(search_id.strip(), case=False)]
    view = view.sort_values(sort_col, ascending=(sort_col == "recency"))

    disp = view[["customer_id", "segment", "recency", "frequency",
                 "monetary", "r_score", "f_score", "m_score", "rfm_score"]].copy()
    disp["monetary"] = disp["monetary"].round(2)
    st.dataframe(
        disp.rename(columns={
            "customer_id": "Customer ID", "segment": "Segment",
            "recency":     "Days Since Last Order",
            "frequency":   "Orders",
            "monetary":    f"Total Spend ({currency})",
            "r_score": "R", "f_score": "F", "m_score": "M", "rfm_score": "RFM",
        }),
        use_container_width=True, height=500,
    )

    if search_id.strip() and len(view) == 1:
        row        = view.iloc[0]
        colour     = SEGMENT_COLOURS.get(row["segment"], "#888")
        desc       = SEGMENT_DESCRIPTIONS.get(row["segment"], "")
        mig_seg, mig_days = SEGMENT_MIGRATION.get(row["segment"], (None, None))
        mig_colour = SEGMENT_COLOURS.get(mig_seg, "#888") if mig_seg else "#888"
        st.markdown(f"""
        <div style="background:#12121c;border:1px solid {colour};
                    border-left:4px solid {colour};border-radius:6px;
                    padding:24px 28px;margin-top:16px;">
          <div style="font-family:'DM Mono',monospace;font-size:10px;
                      color:{colour};letter-spacing:.12em;
                      text-transform:uppercase;margin-bottom:12px;">
            Customer Profile — {row['customer_id']}</div>
          <div style="display:grid;grid-template-columns:repeat(5,1fr);
                      gap:16px;margin-bottom:16px;">
            {''.join([
                f"<div><div style='font-family:DM Mono,monospace;font-size:9px;"
                f"color:#444;text-transform:uppercase;'>{lbl}</div>"
                f"<div style='font-family:DM Serif Display,serif;"
                f"font-size:1.4rem;color:#e8e4dc;'>{val}</div></div>"
                for lbl, val in [
                    ("Segment",         row["segment"]),
                    ("RFM Score",       row["rfm_score"]),
                    ("Days Since Order",f"{row['recency']}d"),
                    ("Orders",          f"{row['frequency']}x"),
                    ("Total Spend",     f"{currency}{row['monetary']:,.0f}"),
                ]
            ])}
          </div>
          <div style="font-family:'DM Sans',sans-serif;font-size:13px;
                      color:#666;border-top:1px solid #1e1e2e;padding-top:12px;">
            {desc}
            {f"<br><span style='color:#555;font-size:12px;'>→ At risk of moving to <span style='color:{mig_colour}'>{mig_seg}</span> without engagement within {mig_days}.</span>" if mig_seg else ""}
          </div>
        </div>
        """, unsafe_allow_html=True)
    elif search_id.strip() and len(view) == 0:
        st.warning(f"No customer found matching '{search_id}'.")

    st.caption(f"{len(view):,} customers shown")

# ══════════════════════════════════════════
# TAB 6 — TARGETING EXPORT
# ══════════════════════════════════════════
with tab6:
    st.markdown("## Targeting List Export")
    st.markdown("""
    <div class="insight-box">
      <strong>How to use this</strong>
      <p>Select segments in the sidebar, then export as CSV.
      Each row is one customer with RFM scores and behavioural metrics —
      ready to upload to your CRM or email platform.</p>
    </div>""", unsafe_allow_html=True)

    if not selected_segments:
        st.warning("Select at least one segment in the sidebar.")
    else:
        tgt = make_targeting_list(rfm, selected_segments, currency)
        spend_col = f"Total Spend ({currency})"

        e1, e2, e3 = st.columns(3)
        with e1: metric("Customers in Export",    f"{len(tgt):,}")
        with e2: metric("Segments Selected",      f"{len(selected_segments)}")
        with e3: metric("Combined Lifetime Value", f"{currency}{tgt[spend_col].sum():,.0f}")

        st.markdown("---")

        breakdown = (tgt.groupby("Segment")
                       .agg(Customers=("Customer ID", "count"))
                       .reset_index()
                       .sort_values("Customers"))
        fig_exp = px.bar(
            breakdown, x="Customers", y="Segment", orientation="h",
            color="Segment", color_discrete_map=SEGMENT_COLOURS,
        )
        fig_exp.update_layout(
            **base_layout("Export Breakdown by Segment"),
            showlegend=False,
            xaxis=dict(gridcolor="#1a1a25", zerolinecolor="#1a1a25"),
            yaxis=dict(gridcolor="rgba(0,0,0,0)",
                       tickfont=dict(size=11, color="#888")),
        )
        st.plotly_chart(fig_exp, use_container_width=True)

        st.markdown("**Preview**")
        st.dataframe(tgt.head(20), use_container_width=True)

        st.download_button(
            label=f"↓ Export {len(tgt):,} customers as CSV",
            data=tgt.to_csv(index=False).encode("utf-8"),
            file_name=(
                "rfm_targeting_"
                + "_".join(selected_segments[:3]).lower().replace(" ", "_")
                + ".csv"
            ),
            mime="text/csv",
        )

        st.markdown("---")
        st.markdown("""
        <div style="background:#12121c;border:1px solid #c8b87a;
                    border-left:4px solid #c8b87a;border-radius:6px;
                    padding:28px 32px;margin-top:8px;">
          <div style="font-family:'DM Mono',monospace;font-size:11px;
                      color:#c8b87a;letter-spacing:0.12em;
                      text-transform:uppercase;margin-bottom:16px;">
            ◈ Recommended Actions for Selected Segments</div>
          <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;">
            <div style="background:#1a1a2a;border-radius:4px;padding:16px;">
              <div style="font-family:'DM Mono',monospace;font-size:10px;
                          color:#f0c040;text-transform:uppercase;
                          letter-spacing:0.08em;margin-bottom:6px;">Champions</div>
              <div style="font-family:'DM Sans',sans-serif;font-size:13px;
                          color:#aaa;line-height:1.6;">
                Personalised loyalty rewards. Early access to new products.
                Referral programme — they are your best advocates.</div>
            </div>
            <div style="background:#1a1a2a;border-radius:4px;padding:16px;">
              <div style="font-family:'DM Mono',monospace;font-size:10px;
                          color:#b87a7a;text-transform:uppercase;
                          letter-spacing:0.08em;margin-bottom:6px;">At Risk</div>
              <div style="font-family:'DM Sans',sans-serif;font-size:13px;
                          color:#aaa;line-height:1.6;">
                Re-engagement email with time-limited incentive.
                Personalise using last purchase category.
                Act within 30 days or they become Lost.</div>
            </div>
            <div style="background:#1a1a2a;border-radius:4px;padding:16px;">
              <div style="font-family:'DM Mono',monospace;font-size:10px;
                          color:#d4624a;text-transform:uppercase;
                          letter-spacing:0.08em;margin-bottom:6px;">Cannot Lose Them</div>
              <div style="font-family:'DM Sans',sans-serif;font-size:13px;
                          color:#aaa;line-height:1.6;">
                Highest commercial priority. Personal outreach — phone or
                account manager if B2B. Meaningful win-back offer.
                Do not rely on email alone.</div>
            </div>
            <div style="background:#1a1a2a;border-radius:4px;padding:16px;">
              <div style="font-family:'DM Mono',monospace;font-size:10px;
                          color:#666680;text-transform:uppercase;
                          letter-spacing:0.08em;margin-bottom:6px;">Hibernating</div>
              <div style="font-family:'DM Sans',sans-serif;font-size:13px;
                          color:#aaa;line-height:1.6;">
                Low-cost automated email only. Suppress from paid media
                and retargeting. A single win-back attempt, then move on.</div>
            </div>
          </div>
          <div style="margin-top:16px;font-family:'DM Sans',sans-serif;
                      font-size:12px;color:#555;border-top:1px solid #1e1e2e;
                      padding-top:12px;">
            Export the targeting list above and upload directly to your
            CRM, email platform, or ad audience manager.
          </div>
        </div>
        """, unsafe_allow_html=True)

# ══════════════════════════════════════════
# TAB 7 — AUTOMATION HUB (n8n / Zapier / Make webhook integration)
# ══════════════════════════════════════════
with tab7:
    st.markdown("## Automation Hub")
    st.markdown("""
    <div class="insight-box">
      <strong>What this does</strong>
      <p>Every segment in this dashboard implies an action — re-engage, nurture, escalate.
      Doing that manually means exporting a CSV, opening a CRM, and uploading a list every
      time segments shift. This tab closes that loop: it converts live RFM output into
      structured alert payloads and pushes them straight to a workflow automation platform
      — n8n, Zapier, Make, or Power Automate — via webhook, so the right team is notified
      the moment a customer crosses into an actionable segment. No manual export step,
      no stale lists.</p>
    </div>""", unsafe_allow_html=True)

    # ── Build alert queue from segments with a defined routing rule ──
    alert_segments = list(ALERT_ROUTING.keys())
    alerts = rfm[rfm["segment"].isin(alert_segments)].copy()
    alerts["priority"] = alerts["segment"].map(lambda s: ALERT_ROUTING[s]["priority"])
    alerts["channel"]  = alerts["segment"].map(lambda s: ALERT_ROUTING[s]["channel"])
    alerts["action"]   = alerts["segment"].map(lambda s: ALERT_ROUTING[s]["action"])
    priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    alerts = alerts.sort_values(by="priority", key=lambda s: s.map(priority_order))

    au1, au2, au3, au4 = st.columns(4)
    with au1: metric("Active Alerts",        f"{len(alerts):,}")
    with au2: metric("Critical Priority",    f"{(alerts['priority'] == 'Critical').sum():,}")
    with au3: metric("Revenue Behind Alerts", f"{currency}{alerts['monetary'].sum():,.0f}")
    with au4: metric("Routing Channels",     f"{alerts['channel'].nunique()}")

    st.markdown("---")

    au_c1, au_c2 = st.columns([1, 1])

    with au_c1:
        by_priority = (alerts.groupby("priority")
                              .agg(customers=("customer_id", "count"),
                                   revenue=("monetary", "sum"))
                              .reindex(["Critical", "High", "Medium", "Low"])
                              .dropna(how="all").fillna(0).reset_index())
        priority_colours = {"Critical": "#d4624a", "High": "#e8630a",
                             "Medium": "#f0c040", "Low": "#7a8db8"}
        fig_alert = go.Figure(go.Bar(
            x=by_priority["customers"],
            y=by_priority["priority"],
            orientation="h",
            marker_color=[priority_colours.get(p, "#888") for p in by_priority["priority"]],
            text=[f"{int(v):,}" for v in by_priority["customers"]],
            textposition="outside",
            textfont=dict(family="DM Mono", size=10, color="#888"),
        ))
        fig_alert.update_layout(
            **base_layout("Alerts by Priority"),
            showlegend=False,
            xaxis=dict(showticklabels=False, gridcolor="#1a1a25", zerolinecolor="#1a1a25"),
            yaxis=dict(gridcolor="rgba(0,0,0,0)", tickfont=dict(size=11, color="#888")),
        )
        st.plotly_chart(fig_alert, use_container_width=True)

    with au_c2:
        st.markdown("**Routing table**")
        routing_tbl = pd.DataFrame([
            {"Segment": seg, "Priority": cfg["priority"], "Channel": cfg["channel"], "Action": cfg["action"]}
            for seg, cfg in ALERT_ROUTING.items()
        ])
        st.dataframe(routing_tbl, use_container_width=True, hide_index=True, height=210)
        st.caption(
            "Each segment maps to a priority, a routing channel, and a recommended "
            "action — this is the logic encoded in the n8n workflow below."
        )

    st.markdown("---")
    st.markdown("### Send alerts to your automation platform")

    cfg1, cfg2 = st.columns([2, 1])
    with cfg1:
        webhook_url = st.text_input(
            "Webhook URL",
            placeholder="https://your-instance.app.n8n.cloud/webhook/rfm-alerts",
            help="Paste an n8n, Zapier, or Make webhook URL. Leave blank to preview the payload only.",
        )
    with cfg2:
        send_priorities = st.multiselect(
            "Priorities to send",
            options=["Critical", "High", "Medium", "Low"],
            default=["Critical", "High"],
        )

    queue = alerts[alerts["priority"].isin(send_priorities)]

    payload = {
        "source":       "rfm-customer-intelligence",
        "dataset":      short_name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "alert_count":  len(queue),
        "alerts": [
            {
                "customer_id": row["customer_id"],
                "segment":     row["segment"],
                "priority":    row["priority"],
                "channel":     row["channel"],
                "action":      row["action"],
                "recency_days": int(row["recency"]),
                "frequency":    int(row["frequency"]),
                "monetary":     round(float(row["monetary"]), 2),
                "rfm_score":    row["rfm_score"],
            }
            for _, row in queue.head(200).iterrows()
        ],
    }

    with st.expander(f"Preview payload — {len(queue):,} alert(s) selected (showing up to 200)"):
        st.json(payload if len(queue) else {"alerts": [], "note": "No alerts match the selected priorities."})

    send_col, dl_col = st.columns([1, 1])
    with send_col:
        if st.button("→ Send alerts to webhook", type="primary", disabled=(len(queue) == 0)):
            if not webhook_url.strip():
                st.warning("Add a webhook URL above to send live — showing preview only for now.")
            else:
                try:
                    resp = requests.post(webhook_url.strip(), json=payload, timeout=10)
                    if resp.ok:
                        st.success(f"Sent {len(queue):,} alert(s) to webhook — response {resp.status_code}.")
                    else:
                        st.error(f"Webhook responded with status {resp.status_code}.")
                except requests.RequestException as e:
                    st.error(f"Could not reach webhook: {e}")

    with dl_col:
        st.download_button(
            label="↓ Download alert payload (JSON)",
            data=json.dumps(payload, indent=2).encode("utf-8"),
            file_name="rfm_automation_alerts.json",
            mime="application/json",
        )

    st.markdown("---")
    st.markdown("### n8n workflow template")
    st.markdown("""
    <div class="insight-box">
      <strong>How to use this</strong>
      <p>Download the workflow below and import it directly into n8n
      (Workflows → Import from File). It exposes a webhook that accepts the exact
      payload shape produced above, routes each alert by <code>priority</code>
      using a Switch node, and forwards Critical/High alerts to a Slack channel
      while logging everything to a sheet for weekly review. Swap in your own
      Slack and Sheets credentials and the workflow runs end-to-end against this
      dashboard's live output.</p>
    </div>""", unsafe_allow_html=True)

    n8n_path = Path(__file__).parent / "n8n" / "rfm_segment_alert_router.json"
    try:
        n8n_workflow = n8n_path.read_text(encoding="utf-8")
        st.download_button(
            label="↓ Download n8n workflow (rfm_segment_alert_router.json)",
            data=n8n_workflow.encode("utf-8"),
            file_name="rfm_segment_alert_router.json",
            mime="application/json",
        )
        with st.expander("Preview workflow JSON"):
            st.code(n8n_workflow, language="json")
    except FileNotFoundError:
        st.info("Workflow template not found in /n8n — add rfm_segment_alert_router.json to enable download.")
