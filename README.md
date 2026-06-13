# RFM Customer Intelligence Dashboard

A production-grade customer segmentation tool built on the UCI Online Retail II dataset, with support for additional preloaded industry datasets and custom data uploads.

**[Live demo](https://your-app-name.streamlit.app)**

---

## What it does

- Loads and cleans transactional data, resolving returns, cancellations, and stock adjustments
- Computes RFM (Recency, Frequency, Monetary) scores per customer using quantile-based scoring
- Assigns customers to 10 behavioural segments using a rule-based matrix
- Visualises segment distribution, revenue concentration, score distributions, and migration risk
- Exports targeting lists per segment as CSV, ready for CRM or email platform upload

---

## Preloaded datasets

Three datasets are available from the sidebar with no upload required, each representing a different commercial context:

**UCI Online Retail II — UK Gift Retailer**
Transactional data from a UK-based online gift and homeware retailer covering December 2009 to December 2011. Customers are predominantly wholesale buyers — small businesses and gift shops across the UK and Europe. This is the primary dataset the project was built around and is the only one using real transaction records. Available from the [UCI ML Repository](https://archive.ics.uci.edu/dataset/502/online+retail+ii).

**Instacart — US Grocery Delivery**
Simulated grocery delivery behaviour modelled on Instacart's published platform statistics, representing 8,000 customers. Recency and frequency dominate the segment distribution here, which is typical of subscription-style grocery services where customers shop weekly but monetary value per order is modest.

**SaaS Platform — B2B Subscriptions**
Simulated B2B SaaS subscription data modelled on mid-market software platform benchmarks, representing 3,000 businesses across SMB, Mid-Market, and Enterprise tiers. Characterised by high annual contract values and polarised recency: active accounts renew regularly while churned accounts show long gaps. The Cannot Lose Them segment is disproportionately valuable in this context.

The Instacart and SaaS datasets are synthetically generated to illustrate how RFM segmentation logic behaves differently across industries.

---

## Custom dataset upload

The sidebar accepts any Excel (.xlsx) or CSV file that follows the UCI Online Retail II column format. The app expects: `Invoice`, `CustomerID`, `InvoiceDate`, `Quantity`, `UnitPrice`. Returns invoices (prefixed with C) and stock adjustments (prefixed with A) are automatically excluded. The uploaded dataset replaces the selected preloaded dataset for the duration of the session.

---

## Automation Hub

The **Automation Hub** tab turns segment membership into action. Every customer in a segment with a defined routing rule (Cannot Lose Them, At Risk, Need Attention, New Customers, Promising) is built into an alert with a priority (Critical/High/Medium/Low), a target channel, and a recommended action — all visible in an editable routing table.

From this tab you can:

- Review alert volume and revenue at risk by priority
- Preview the exact JSON payload that would be sent for the selected priorities
- Send that payload directly to a webhook (n8n, Zapier, Make, or Power Automate) via `requests`, or download it as a JSON file
- Download a ready-to-import **n8n workflow** (`n8n/rfm_segment_alert_router.json`)

### Using the n8n workflow

1. In n8n, go to **Workflows → Import from File** and select `n8n/rfm_segment_alert_router.json` (or download it from the Automation Hub tab)
2. The workflow exposes a webhook at `/webhook/rfm-alerts` that accepts the payload shape produced by the app: `{ source, dataset, generated_at, alert_count, alerts: [...] }`
3. It splits the `alerts` array, routes `Critical` and `High` priority alerts to a Slack channel (per the `channel` field on each alert), and logs every alert to a Google Sheet for weekly review
4. Add your own Slack and Google Sheets credentials in n8n before activating — the template ships with placeholder credential IDs
5. Paste your n8n webhook URL into the **Webhook URL** field in the Automation Hub tab to send alerts live

---

## RFM methodology

**Recency:** days since last purchase (lower is better)
**Frequency:** number of distinct invoices (higher is better)
**Monetary:** total revenue generated (higher is better)

Each dimension is scored 1-5 using quantile ranking. Where tied values would collapse quantile boundaries, rank-based scoring is used to ensure five distinct score levels are always produced.

Segments are assigned using a rule matrix applied to the three scores:

| Segment | R | F | M | Description |
|---|---|---|---|---|
| Champions | ≥4 | ≥4 | ≥4 | Bought recently, buy often, spend the most |
| Loyal Customers | ≥3 | ≥3 | ≥3 | Buy regularly with good frequency |
| Potential Loyalists | ≥3 | ≥2 | ≥2 | Recent with above-average frequency |
| New Customers | ≥4 | ≤2 | any | Bought recently but only once |
| Promising | ≥3 | ≤2 | ≤2 | Recent buyers with moderate spend |
| Need Attention | =2 | ≥3 | ≥3 | Above average scores but not buying recently |
| Cannot Lose Them | ≤2 | ≥4 | ≥4 | Made large purchases but not returned |
| At Risk | ≤2 | ≥2 | ≥2 | Once-valuable customers who have lapsed |
| Hibernating | ≥2 | ≤2 | ≤2 | Low across all three dimensions |
| Lost | all low | all low | all low | Lowest scores, low recovery probability |

Each segment also carries a migration risk indicator: the segment a customer is likely to fall into without engagement, and the timeframe within which action is needed.

---

## Tech stack

| Tool | Use |
|---|---|
| Python 3.10+ | Core language |
| Streamlit | Web app framework |
| Plotly | Interactive charts |
| pandas / numpy | Data processing and RFM computation |

---

## Author

Built by Rafee Ahmed as part of a Marketing Data Analyst portfolio.
