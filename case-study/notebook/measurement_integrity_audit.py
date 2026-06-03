"""
Measurement Integrity Audit - UK Online Retail ledger
=====================================================

Author : Samandeep Kaur (Arcmedian)
Data    : UCI Online Retail II
          Real transaction ledger from a UK-registered online gift retailer,
          01 Dec 2009 to 09 Dec 2011 (~1.07m line items).
          Source: https://archive.ics.uci.edu/dataset/502/online+retail+ii

Purpose
-------
Reproduce the kind of work Arcmedian does for commerce teams: take a raw
transaction export, audit what can actually be trusted, quantify how far a
naive "sum it all up" revenue number drifts from a defensible one, then build
the clean KPI base (revenue, orders, AOV, retention, customer value) that a
leadership team can make decisions on.

Every number printed and every chart written by this script is computed from
the real file. Nothing is hand-entered.

Run:  python3 measurement_integrity_audit.py
"""

import json
import re
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

# --------------------------------------------------------------------------
# Brand palette (mirrors styles.css so charts sit inside the site cleanly)
# --------------------------------------------------------------------------
INK = "#17202a"
INK_SOFT = "#21303a"
PAPER = "#fffaf1"
PAPER_BG = "#f6f1e7"
MIST = "#dfe6df"
SAGE = "#6d8079"
COPPER = "#8a5a3c"
BRASS = "#d5b98a"
BLUE = "#3c5063"          # refined slate, primary data series
MUTED = "#6b7178"
LINE = "#ded7c8"          # hairline rules / axes
GREY = "#c4bfb2"          # warm neutral for context / secondary
TERRA = "#a8623f"         # deductions / returns (refined terracotta)
GRID = "#e7e1d4"          # very light gridlines

# Editorial sans with graceful fallback (Helvetica Neue is the FT/Economist look)
plt.rcParams.update({
    "font.family": ["Helvetica Neue", "Helvetica", "Arial", "DejaVu Sans"],
    "font.size": 11,
    "figure.dpi": 170,
    "savefig.dpi": 170,
    "axes.edgecolor": LINE,
    "axes.linewidth": 1.0,
    "axes.labelcolor": INK_SOFT,
    "text.color": INK,
    "xtick.color": MUTED,
    "ytick.color": MUTED,
    "xtick.labelsize": 9.5,
    "ytick.labelsize": 9.5,
    "axes.grid": False,
    "svg.fonttype": "path",
})

ROOT = Path(__file__).resolve().parents[1]      # case-study/
CHARTS = ROOT / "charts"
DATA = ROOT / "data" / "online_retail_II.xlsx"
CHARTS.mkdir(exist_ok=True)

GBP = lambda v: f"£{v:,.0f}"
SOURCE = "Source: UCI Online Retail II (real UK retailer, 2009–2011)   ·   Analysis by Arcmedian"


HX = 0.062          # constant header / source x, so every chart aligns
HR = 0.962          # right edge for the header rule


def frame(figsize, title, subtitle, left=0.10, bottom=0.16, right=HR, top=0.80):
    """Create a figure with a consistent editorial layout: a left-aligned bold
    title, a muted subtitle beneath it, a hairline rule, and reserved room for a
    source line. Header elements align across all charts via the constant HX."""
    fig, ax = plt.subplots(figsize=figsize)
    fig.subplots_adjust(left=left, right=right, top=top, bottom=bottom)
    fig.text(HX, 0.95, title, fontsize=14.5, fontweight="bold", color=INK,
             ha="left", va="top")
    fig.text(HX, 0.866, subtitle, fontsize=9.8, color=MUTED, ha="left", va="top")
    fig.add_artist(plt.Line2D([HX, HR], [0.835, 0.835], color=GRID, lw=1.0,
                              transform=fig.transFigure))
    ax.set_facecolor("none")
    return fig, ax


def style_axes(ax, spines=("left", "bottom"), grid=None):
    for side in ("top", "right", "left", "bottom"):
        ax.spines[side].set_visible(side in spines)
        ax.spines[side].set_color(LINE)
    ax.tick_params(length=0)
    if grid == "y":
        ax.set_axisbelow(True)
        ax.yaxis.grid(True, color=GRID, lw=1.0)
    elif grid == "x":
        ax.set_axisbelow(True)
        ax.xaxis.grid(True, color=GRID, lw=1.0)


def save(fig, basename):
    """Stamp the source line once and write both SVG and PNG."""
    fig.text(HX, 0.045, SOURCE, fontsize=7.6, color=MUTED, ha="left", va="center")
    for ext in ("svg", "png"):
        fig.savefig(CHARTS / f"{basename}.{ext}", transparent=True)
    plt.close(fig)
    print(f"  wrote {basename}.svg + .png")


# --------------------------------------------------------------------------
# 1. Load the real ledger (both trading years)
# --------------------------------------------------------------------------
print("Loading real ledger from", DATA.name, "...")
sheets = pd.read_excel(DATA, sheet_name=None)
raw = pd.concat(sheets.values(), ignore_index=True)
raw.columns = [c.strip() for c in raw.columns]
raw = raw.rename(columns={"Customer ID": "CustomerID"})
raw["LineValue"] = raw["Quantity"] * raw["Price"]

n_raw = len(raw)
date_min, date_max = raw["InvoiceDate"].min(), raw["InvoiceDate"].max()
print(f"Loaded {n_raw:,} raw line items, {date_min.date()} -> {date_max.date()}")

# The naive number: what an unaudited dashboard reports if it just sums the file
naive_gross = raw["LineValue"].sum()

# --------------------------------------------------------------------------
# 2. Data-quality audit - tag every integrity issue, do not delete yet
# --------------------------------------------------------------------------
inv = raw["Invoice"].astype(str)
code = raw["StockCode"].astype(str).str.upper()

is_cancellation = inv.str.startswith("C")
is_neg_qty = raw["Quantity"] <= 0
is_bad_price = raw["Price"] <= 0
is_missing_cust = raw["CustomerID"].isna()

# Non-product ledger lines: postage, manual adjustments, fees, samples, debt,
# carriage, bank charges, test rows. These are real money movements but they are
# not product sales and inflate "revenue" if counted as such.
admin_codes = {
    "POST", "DOT", "C2", "M", "BANK CHARGES", "AMAZONFEE", "ADJUST", "ADJUST2",
    "S", "SP1002", "B", "CRUK", "GIFT", "PADS", "TEST001", "TEST002", "D",
}
is_admin = code.isin(admin_codes) | code.str.fullmatch(r"(BANK CHARGES|AMAZONFEE|ADJUST.*|TEST.*|GIFT_.*)")
is_admin = is_admin.fillna(False)

dup_mask = raw.duplicated(keep="first")

audit = {
    "raw_line_items": int(n_raw),
    "naive_gross_revenue": float(naive_gross),
    "cancellations_lines": int(is_cancellation.sum()),
    "cancellations_value": float(raw.loc[is_cancellation, "LineValue"].sum()),
    "negative_or_zero_qty_lines": int(is_neg_qty.sum()),
    "zero_or_negative_price_lines": int(is_bad_price.sum()),
    "missing_customer_lines": int(is_missing_cust.sum()),
    "missing_customer_pct": float(is_missing_cust.mean() * 100),
    "admin_nonproduct_lines": int(is_admin.sum()),
    "admin_nonproduct_value": float(raw.loc[is_admin, "LineValue"].sum()),
    "duplicate_lines": int(dup_mask.sum()),
}

print("\n--- DATA QUALITY AUDIT ---")
for k, v in audit.items():
    print(f"  {k:34s}: {v:,.2f}" if isinstance(v, float) else f"  {k:34s}: {v:,}")

# --------------------------------------------------------------------------
# 3. Apply documented cleaning rules -> defensible "audited net" ledger
# --------------------------------------------------------------------------
# Sales ledger: real product sales only, positive qty and price, de-duplicated.
clean = raw.loc[~dup_mask].copy()
sales = clean[
    (~clean["Invoice"].astype(str).str.startswith("C"))
    & (clean["Quantity"] > 0)
    & (clean["Price"] > 0)
    & (~clean["StockCode"].astype(str).str.upper().isin(admin_codes))
].copy()

# Returns ledger: the cancellation/credit lines, kept so we can measure the
# real return rate rather than silently dropping it.
returns = clean[clean["Invoice"].astype(str).str.startswith("C")].copy()
returns_value = -returns["LineValue"].sum()          # credits are negative

gross_sales = sales["LineValue"].sum()
audited_net = gross_sales - returns_value            # net of returns

# Customer-level work needs identified customers
sales_id = sales.dropna(subset=["CustomerID"]).copy()
sales_id["CustomerID"] = sales_id["CustomerID"].astype(int)

n_orders = sales["Invoice"].nunique()
n_customers = sales_id["CustomerID"].nunique()
aov = gross_sales / n_orders
return_rate = returns_value / gross_sales * 100
trust_gap = (naive_gross - audited_net) / naive_gross * 100

headline = {
    "period": f"{date_min.date()} to {date_max.date()}",
    "raw_line_items": int(n_raw),
    "naive_gross_revenue": float(naive_gross),
    "audited_net_revenue": float(audited_net),
    "gross_product_sales": float(gross_sales),
    "returns_value": float(returns_value),
    "trust_gap_pct": float(trust_gap),
    "orders": int(n_orders),
    "identified_customers": int(n_customers),
    "aov": float(aov),
    "return_rate_pct": float(return_rate),
    "missing_customer_pct": float(audit["missing_customer_pct"]),
}

print("\n--- AUDITED RESULT ---")
print(f"  Naive gross (unaudited file sum) : {GBP(naive_gross)}")
print(f"  Audited net revenue              : {GBP(audited_net)}")
print(f"  Trust gap removed                : {trust_gap:.1f}% of the naive number")
print(f"  Orders                           : {n_orders:,}")
print(f"  Identified customers             : {n_customers:,}")
print(f"  Average order value              : {GBP(aov)}")
print(f"  Return rate (value)              : {return_rate:.1f}%")

# ==========================================================================
# CHART 1 - Revenue assurance waterfall (signature chart)
# Clean, exact three-step bridge: gross product sales less returns = net.
# ==========================================================================
print("\nBuilding charts...")
returns_pct_of_gross = returns_value / gross_sales * 100

fig, ax = frame(
    (8.7, 5.2),
    "Revenue assurance: a net number leadership can defend",
    f"Gross product sales of {GBP(gross_sales)} carry {GBP(returns_value)} of returns "
    f"({returns_pct_of_gross:.1f}% of gross) the raw export hides by netting them in.",
    left=0.105, bottom=0.13)
labels = ["Gross product\nsales", "Returns &\ncancellations", "Audited net\nrevenue"]
ax.bar(0, gross_sales, width=0.58, color=BLUE, zorder=3)
ax.text(0, gross_sales + gross_sales * 0.018, GBP(gross_sales),
        ha="center", va="bottom", fontsize=11, color=INK, fontweight="bold")
top = gross_sales
bot = gross_sales - returns_value
ax.bar(1, returns_value, bottom=bot, width=0.58, color=TERRA, zorder=3)
ax.plot([0.29, 1.71], [top, top], color=GREY, lw=1, ls=(0, (4, 3)), zorder=2)
ax.plot([1.29, 2.29], [bot, bot], color=GREY, lw=1, ls=(0, (4, 3)), zorder=2)
ax.text(1, bot - gross_sales * 0.022, f"−{GBP(returns_value)}",
        ha="center", va="top", fontsize=10.5, color=TERRA, fontweight="bold")
ax.bar(2, audited_net, width=0.58, color=INK, zorder=3)
ax.text(2, audited_net + gross_sales * 0.018, GBP(audited_net),
        ha="center", va="bottom", fontsize=11, color=INK, fontweight="bold")
ax.set_xticks([0, 1, 2])
ax.set_xticklabels(labels, fontsize=9.8, color=INK_SOFT)
ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _: f"£{x/1e6:.0f}m"))
ax.set_ylim(0, gross_sales * 1.16)
ax.margins(x=0.04)
style_axes(ax, spines=("bottom",), grid="y")
save(fig, "01-revenue-assurance")

# ==========================================================================
# CHART 2 - Monthly net revenue trend
# ==========================================================================
sales["Month"] = sales["InvoiceDate"].dt.to_period("M").dt.to_timestamp()
returns["Month"] = returns["InvoiceDate"].dt.to_period("M").dt.to_timestamp()
m_sales = sales.groupby("Month")["LineValue"].sum()
m_ret = returns.groupby("Month")["LineValue"].sum().reindex(m_sales.index).fillna(0)
m_net = (m_sales + m_ret) / 1e6      # returns are negative

fig, ax = frame(
    (8.9, 4.7),
    "Monthly net revenue, audited ledger",
    "A clean seasonal demand curve once the noise is removed. The first and last "
    "months read low only because the data window is cut off.",
    left=0.085, bottom=0.16)
x = list(range(len(m_net)))
ax.fill_between(x, m_net.values, color=BRASS, alpha=0.22, zorder=2)
ax.plot(x, m_net.values, color=BLUE, lw=2.2, zorder=3)
# solid markers for full months, hollow grey for the two partial end months
partial = {0, len(m_net) - 1}
for i, v in enumerate(m_net.values):
    if i in partial:
        ax.plot(i, v, marker="o", ms=6, mfc=PAPER, mec=GREY, mew=1.6, zorder=4)
    else:
        ax.plot(i, v, marker="o", ms=5, mfc=BLUE, mec=PAPER, mew=1.0, zorder=4)
pk = int(np.argmax(m_net.values))
ax.annotate(f"Pre-Christmas peak\n{GBP(m_net.max()*1e6)}",
            xy=(pk, m_net.max()), xytext=(-10, -34), textcoords="offset points",
            fontsize=9, color=INK, ha="right", fontweight="bold",
            arrowprops=dict(arrowstyle="-", color=MUTED, lw=1))
ax.annotate("partial month", xy=(len(m_net) - 1, m_net.values[-1]),
            xytext=(0, 12), textcoords="offset points", fontsize=8,
            color=MUTED, ha="center")
ticks = [i for i in x if m_net.index[i].month in (1, 4, 7, 10)]
ax.set_xticks(ticks)
ax.set_xticklabels([m_net.index[i].strftime("%b %y") for i in ticks], fontsize=9)
ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"£{v:.1f}m"))
ax.set_ylim(0, m_net.max() * 1.18)
ax.margins(x=0.02)
style_axes(ax, spines=("bottom",), grid="y")
save(fig, "02-monthly-revenue")

# ==========================================================================
# CHART 3 - Revenue concentration by market (top 8 + rest)
# ==========================================================================
by_country = sales.groupby("Country")["LineValue"].sum().sort_values(ascending=False)
top8 = by_country.head(8)
rest = by_country.iloc[8:].sum()
plot_c = pd.concat([top8, pd.Series({"All other markets": rest})])
share = plot_c / by_country.sum() * 100
uk_share = share.iloc[0]

fig, ax = frame(
    (8.7, 5.0),
    "Revenue concentration by market",
    f"The United Kingdom alone is {uk_share:.1f}% of audited revenue — a single-market "
    "dependency worth planning around.",
    left=0.165, bottom=0.075, top=0.80)
ypos = np.arange(len(plot_c))[::-1]
colors = [COPPER if i == 0 else GREY for i in range(len(plot_c))]
ax.barh(ypos, plot_c.values / 1e6, color=colors, height=0.62, zorder=3)
xmax = plot_c.max() / 1e6
for y, (name, val), pct in zip(ypos, plot_c.items(), share.values):
    bold = (y == ypos[0])
    ax.text(val / 1e6 + xmax * 0.012, y, f"{pct:.1f}%", va="center",
            fontsize=9.5 if bold else 9, color=INK if bold else MUTED,
            fontweight="bold" if bold else "normal")
ax.set_yticks(ypos)
ax.set_yticklabels(plot_c.index, fontsize=9.6, color=INK_SOFT)
ax.set_xlim(0, xmax * 1.12)
ax.set_xticks([])
style_axes(ax, spines=())
save(fig, "03-market-concentration")

# ==========================================================================
# CHART 4 - Cohort retention heatmap (monthly acquisition cohorts)
# ==========================================================================
df = sales_id.copy()
df["OrderMonth"] = df["InvoiceDate"].dt.to_period("M")
df["CohortMonth"] = df.groupby("CustomerID")["InvoiceDate"].transform("min").dt.to_period("M")
df["CohortIndex"] = (df["OrderMonth"].astype("int64") - df["CohortMonth"].astype("int64"))

cohort = (df.groupby(["CohortMonth", "CohortIndex"])["CustomerID"]
            .nunique().reset_index())
pivot = cohort.pivot(index="CohortMonth", columns="CohortIndex", values="CustomerID")
size = pivot[0]
retention = pivot.divide(size, axis=0) * 100
retention = retention.iloc[:, :13]
m1 = np.nanmean(retention.iloc[:, 1].values)

from matplotlib.colors import LinearSegmentedColormap
cmap = LinearSegmentedColormap.from_list(
    "arc", ["#f4efe4", "#e7d3ac", "#cd9f6f", "#9c7350", "#5e4632"])

fig, ax = frame(
    (8.9, 6.8),
    "Customer retention by monthly cohort",
    f"Each row is a monthly acquisition cohort; cells are the % still buying later. "
    f"Month-one repeat averages ~{m1:.0f}%.",
    left=0.105, bottom=0.125, top=0.80)
data = retention.values.astype(float)
im = ax.imshow(np.ma.masked_invalid(data), cmap=cmap, aspect="auto", vmin=0, vmax=45)
# thin separators for a crisp matrix
ax.set_xticks(np.arange(-0.5, data.shape[1], 1), minor=True)
ax.set_yticks(np.arange(-0.5, data.shape[0], 1), minor=True)
ax.grid(which="minor", color=PAPER, lw=1.4)
ax.tick_params(which="minor", length=0)
for i in range(data.shape[0]):
    for j in range(data.shape[1]):
        v = data[i, j]
        if not np.isnan(v):
            ax.text(j, i, f"{v:.0f}", ha="center", va="center", fontsize=7.4,
                    color=PAPER if v > 30 else INK_SOFT)
ax.set_xticks(range(retention.shape[1]))
ax.set_xticklabels(range(retention.shape[1]), fontsize=8.5)
ax.set_yticks(range(retention.shape[0]))
ax.set_yticklabels([str(p) for p in retention.index], fontsize=8.5)
ax.set_xlabel("Months since first purchase", fontsize=9.5, color=INK_SOFT, labelpad=8)
ax.set_ylabel("Acquisition cohort", fontsize=9.5, color=INK_SOFT, labelpad=8)
for s in ax.spines.values():
    s.set_visible(False)
ax.tick_params(length=0)
save(fig, "04-cohort-retention")

# ==========================================================================
# CHART 5 - RFM customer segmentation
# ==========================================================================
snapshot = sales_id["InvoiceDate"].max() + pd.Timedelta(days=1)
rfm = sales_id.groupby("CustomerID").agg(
    recency=("InvoiceDate", lambda x: (snapshot - x.max()).days),
    frequency=("Invoice", "nunique"),
    monetary=("LineValue", "sum"),
)
r = pd.qcut(rfm["recency"], 4, labels=[4, 3, 2, 1]).astype(int)
f = pd.qcut(rfm["frequency"].rank(method="first"), 4, labels=[1, 2, 3, 4]).astype(int)
m = pd.qcut(rfm["monetary"], 4, labels=[1, 2, 3, 4]).astype(int)
rfm["score"] = r + f + m


def segment(row_r, row_f, row_m):
    if row_r >= 3 and row_f >= 3:
        return "Champions"
    if row_f >= 3:
        return "Loyal"
    if row_r >= 3:
        return "Recent / promising"
    if row_r <= 2 and row_f >= 2:
        return "At risk"
    return "Dormant"


rfm["segment"] = [segment(ri, fi, mi) for ri, fi, mi in zip(r, f, m)]
seg_rev = rfm.groupby("segment")["monetary"].sum().sort_values(ascending=False)
seg_cnt = rfm.groupby("segment").size().reindex(seg_rev.index)
seg_rev_share = seg_rev / seg_rev.sum() * 100
seg_cnt_share = seg_cnt / seg_cnt.sum() * 100

champ_rev = seg_rev_share.get("Champions", 0)
champ_cnt = seg_cnt_share.get("Champions", 0)

fig, ax = frame(
    (8.7, 4.9),
    "Where the value sits: RFM customer segments",
    f"Champions are ~{champ_cnt:.0f}% of customers but ~{champ_rev:.0f}% of revenue — "
    "exactly where retention and CRM budget should point first.",
    left=0.20, bottom=0.115, top=0.80)
y = np.arange(len(seg_rev))[::-1].astype(float)
h = 0.36
ax.barh(y + h / 2 + 0.02, seg_rev_share.values, height=h, color=COPPER, zorder=3,
        label="Share of revenue")
ax.barh(y - h / 2 - 0.02, seg_cnt_share.values, height=h, color=GREY, zorder=3,
        label="Share of customers")
xmax = max(seg_rev_share.max(), seg_cnt_share.max())
for yi, rv, cv in zip(y, seg_rev_share.values, seg_cnt_share.values):
    ax.text(rv + xmax * 0.012, yi + h / 2 + 0.02, f"{rv:.0f}%", va="center",
            fontsize=8.6, color=COPPER, fontweight="bold")
    ax.text(cv + xmax * 0.012, yi - h / 2 - 0.02, f"{cv:.0f}%", va="center",
            fontsize=8.6, color=MUTED)
ax.set_yticks(y)
ax.set_yticklabels(seg_rev.index, fontsize=9.6, color=INK_SOFT)
ax.set_xlim(0, xmax * 1.12)
ax.set_xticks([])
ax.legend(frameon=False, fontsize=8.8, loc="lower right", handlelength=1.1,
          borderpad=0.2, labelcolor=INK_SOFT)
style_axes(ax, spines=())
save(fig, "05-rfm-segments")

# --------------------------------------------------------------------------
# 6. Export every headline number for the website (single source of truth)
# --------------------------------------------------------------------------
findings = {
    "dataset": "UCI Online Retail II (real UK online retailer)",
    "source_url": "https://archive.ics.uci.edu/dataset/502/online+retail+ii",
    "generated_from": "case-study/notebook/measurement_integrity_audit.py",
    "audit": audit,
    "headline": headline,
    "segments": {
        "champions_customer_pct": float(champ_cnt),
        "champions_revenue_pct": float(champ_rev),
    },
    "retention_month_one_pct": float(m1),
    "uk_revenue_share_pct": float(uk_share),
}
out_json = ROOT / "findings.json"
out_json.write_text(json.dumps(findings, indent=2))
print(f"\nWrote {out_json.relative_to(ROOT)}")
print("\nDone. All numbers above are computed from the real file.")
