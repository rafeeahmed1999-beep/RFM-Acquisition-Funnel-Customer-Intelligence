"""
Standalone alert dispatcher for the RFM Customer Intelligence Dashboard.

Recomputes RFM segments from the UCI Online Retail II dataset, builds the
same alert payload shape produced by the Automation Hub tab in app.py, and
posts it to the n8n webhook configured via the WEBHOOK_URL environment
variable. Designed to run headlessly on a schedule via GitHub Actions
(see .github/workflows/dispatch-alerts.yml).

Usage:
    WEBHOOK_URL=https://your-n8n-instance/webhook/rfm-alerts python scripts/dispatch_alerts.py
    python scripts/dispatch_alerts.py --dry-run                 # print payload, don't send
    python scripts/dispatch_alerts.py --priorities Critical     # override default Critical,High
"""

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import requests

# ─────────────────────────────────────────────
# CONSTANTS — kept in sync with app.py
# ─────────────────────────────────────────────
DATASET_NAME = "UK Gift Retailer — UCI Online Retail II"

ALERT_ROUTING = {
    "Cannot Lose Them": {"priority": "Critical", "channel": "#customer-success-urgent", "action": "Personal outreach — phone or account manager"},
    "At Risk":          {"priority": "High",     "channel": "#customer-success",        "action": "Re-engagement email with time-limited incentive"},
    "Need Attention":   {"priority": "Medium",   "channel": "#lifecycle-marketing",      "action": "Nurture sequence before they slip to At Risk"},
    "New Customers":    {"priority": "Medium",   "channel": "#onboarding",               "action": "Onboarding sequence to drive second purchase"},
    "Promising":        {"priority": "Low",      "channel": "#lifecycle-marketing",      "action": "Add to nurture campaign"},
}

DEFAULT_PRIORITIES = ["Critical", "High"]
MAX_ALERTS_IN_PAYLOAD = 200


# ─────────────────────────────────────────────
# DATA LOADING + CLEANING — mirrors app.py
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


def load_default() -> pd.DataFrame:
    path = Path(__file__).resolve().parent.parent / "online_retail_II.csv"
    df   = pd.read_csv(str(path), encoding="latin-1")
    return clean_raw(df)


# ─────────────────────────────────────────────
# RFM + SEGMENTATION — mirrors app.py
# ─────────────────────────────────────────────
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
    rfm["f_score"] = safe_score(rfm["frequency"], ascending=True)
    rfm["m_score"] = safe_score(rfm["monetary"],  ascending=True)
    rfm["rfm_score"] = (rfm["r_score"].astype(str)
                         + rfm["f_score"].astype(str)
                         + rfm["m_score"].astype(str))

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


# ─────────────────────────────────────────────
# ALERT QUEUE + PAYLOAD — mirrors the Automation Hub tab
# ─────────────────────────────────────────────
def build_payload(rfm: pd.DataFrame, priorities: list[str]) -> dict:
    alert_segments = list(ALERT_ROUTING.keys())
    alerts = rfm[rfm["segment"].isin(alert_segments)].copy()
    alerts["priority"] = alerts["segment"].map(lambda s: ALERT_ROUTING[s]["priority"])
    alerts["channel"]  = alerts["segment"].map(lambda s: ALERT_ROUTING[s]["channel"])
    alerts["action"]   = alerts["segment"].map(lambda s: ALERT_ROUTING[s]["action"])

    priority_order = {"Critical": 0, "High": 1, "Medium": 2, "Low": 3}
    alerts = alerts.sort_values(by="priority", key=lambda s: s.map(priority_order))

    queue = alerts[alerts["priority"].isin(priorities)]

    return {
        "source":       "rfm-customer-intelligence",
        "dataset":      DATASET_NAME,
        "generated_at": datetime.now(ZoneInfo("Europe/London")).isoformat(),
        "alert_count":  len(queue),
        "alerts": [
            {
                "customer_id":  row["customer_id"],
                "segment":      row["segment"],
                "priority":     row["priority"],
                "action":       row["action"],
                "recency_days": int(row["recency"]),
                "frequency":    int(row["frequency"]),
                "monetary":     round(float(row["monetary"]), 2),
                "rfm_score":    row["rfm_score"],
            }
            for _, row in queue.head(MAX_ALERTS_IN_PAYLOAD).iterrows()
        ],
    }


# ─────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────
def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--priorities",
        default=",".join(DEFAULT_PRIORITIES),
        help=f"Comma-separated list of priorities to dispatch (default: {','.join(DEFAULT_PRIORITIES)})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Build and print the payload without sending it to the webhook",
    )
    args = parser.parse_args()
    priorities = [p.strip() for p in args.priorities.split(",") if p.strip()]

    print(f"Loading dataset and computing RFM segments ({DATASET_NAME})...")
    df  = load_default()
    rfm = compute_rfm(df)
    payload = build_payload(rfm, priorities)

    print(f"Built payload with {payload['alert_count']} alert(s) for priorities: {', '.join(priorities)}")

    if args.dry_run:
        import json
        print(json.dumps(payload, indent=2))
        return 0

    webhook_url = os.environ.get("WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("ERROR: WEBHOOK_URL environment variable is not set.", file=sys.stderr)
        return 1

    if payload["alert_count"] == 0:
        print("No alerts match the selected priorities — nothing to send.")
        return 0

    try:
        resp = requests.post(webhook_url, json=payload, timeout=30)
    except requests.RequestException as exc:
        print(f"ERROR: could not reach webhook: {exc}", file=sys.stderr)
        return 1

    if not resp.ok:
        print(f"ERROR: webhook responded with status {resp.status_code}: {resp.text[:500]}", file=sys.stderr)
        return 1

    print(f"Sent {payload['alert_count']} alert(s) to webhook.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
