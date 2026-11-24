"""Build deliverables/technical_report.pdf (A4, 10-15 pages) from the pipeline outputs.

    .venv\\Scripts\\python.exe -m deliverables.build_report

Structure follows the upGrad deliverable template: Executive Summary; Introduction & Business
Context; Data Architecture & Methodology; Implementation & Results; Strategic Deductions &
Business Impact; Limitations & Future Work (+ appendix).
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table,
                                TableStyle)

from . import figures as extra
from .common import AUTHOR, FIG, OUT, PROGRAM, REPO_URL, SEG_NAME, USD_PER_LITRE, load, ml, pct

# ------------------------------------------------------------------------------------ styling
FONT_DIR = Path("C:/Windows/Fonts")
pdfmetrics.registerFont(TTFont("Body", str(FONT_DIR / "calibri.ttf")))
pdfmetrics.registerFont(TTFont("Body-Bold", str(FONT_DIR / "calibrib.ttf")))
pdfmetrics.registerFont(TTFont("Body-Italic", str(FONT_DIR / "calibrii.ttf")))
pdfmetrics.registerFontFamily("Body", normal="Body", bold="Body-Bold", italic="Body-Italic", boldItalic="Body-Bold")

NAVY = colors.HexColor("#1E2761")
BLUE = colors.HexColor("#2a78d6")
INK = colors.HexColor("#0b0b0b")
INK2 = colors.HexColor("#52514e")
GRIDC = colors.HexColor("#d9d8d2")
TINT = colors.HexColor("#f1f4fa")

S = {
    "title": ParagraphStyle("title", fontName="Body-Bold", fontSize=24, leading=29, textColor=NAVY, spaceAfter=6),
    "subtitle": ParagraphStyle("subtitle", fontName="Body", fontSize=12.5, leading=16, textColor=INK2, spaceAfter=10),
    "h1": ParagraphStyle("h1", fontName="Body-Bold", fontSize=16, leading=20, textColor=NAVY, spaceBefore=4, spaceAfter=8),
    "h2": ParagraphStyle("h2", fontName="Body-Bold", fontSize=12, leading=15, textColor=NAVY, spaceBefore=8, spaceAfter=4),
    "body": ParagraphStyle("body", fontName="Body", fontSize=10.5, leading=14, textColor=INK, spaceAfter=6, alignment=TA_LEFT),
    "bullet": ParagraphStyle("bullet", fontName="Body", fontSize=10.5, leading=14, textColor=INK, leftIndent=12,
                             bulletIndent=2, spaceAfter=3),
    "small": ParagraphStyle("small", fontName="Body", fontSize=8.5, leading=11, textColor=INK2, spaceAfter=4),
    "cell": ParagraphStyle("cell", fontName="Body", fontSize=8.8, leading=11, textColor=INK),
    "cellb": ParagraphStyle("cellb", fontName="Body-Bold", fontSize=8.8, leading=11, textColor=colors.white),
    "kpi": ParagraphStyle("kpi", fontName="Body-Bold", fontSize=19, leading=22, textColor=NAVY),
    "kpil": ParagraphStyle("kpil", fontName="Body", fontSize=8.5, leading=10.5, textColor=INK2),
    "caption": ParagraphStyle("caption", fontName="Body-Italic", fontSize=8.5, leading=11, textColor=INK2, spaceAfter=8),
}
W = A4[0] - 4 * cm   # usable width


def P(text, style="body"):
    return Paragraph(text, S[style])


def bullets(items):
    return [Paragraph(i, S["bullet"], bulletText="•") for i in items]


def table(rows, widths, header=True, zebra=True, font=8.8):
    """rows: list of lists of str; first row is the header."""
    data = []
    for r, row in enumerate(rows):
        st = "cellb" if (header and r == 0) else "cell"
        data.append([Paragraph(str(c), S[st]) for c in row])
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.4, GRIDC),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
             ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    if header:
        style += [("BACKGROUND", (0, 0), (-1, 0), NAVY)]
    if zebra:
        for r in range(1 if header else 0, len(rows)):
            if r % 2 == 0:
                style.append(("BACKGROUND", (0, r), (-1, r), TINT))
    t.setStyle(TableStyle(style))
    return t


def fig(path, width=W, caption=None):
    from reportlab.lib.utils import ImageReader
    iw, ih = ImageReader(str(path)).getSize()
    img = Image(str(path), width=width, height=width * ih / iw)
    parts = [img]
    if caption:
        parts.append(P(caption, "caption"))
    return KeepTogether(parts)


def kpi_row(items):
    """items: list of (value, label)"""
    cells = [[Paragraph(v, S["kpi"]) for v, _ in items], [Paragraph(lbl, S["kpil"]) for _, lbl in items]]
    t = Table(cells, colWidths=[W / len(items)] * len(items))
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), TINT), ("VALIGN", (0, 0), (-1, -1), "TOP"),
                           ("LINEAFTER", (0, 0), (-2, -1), 1.5, colors.white),
                           ("TOPPADDING", (0, 0), (-1, 0), 7), ("BOTTOMPADDING", (0, 1), (-1, 1), 7),
                           ("LEFTPADDING", (0, 0), (-1, -1), 7)]))
    return t


def on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Body", 8)
    canvas.setFillColor(INK2)
    canvas.drawString(2 * cm, 1.2 * cm, "Vietnam Lubricant Demand Potential Monitor - Technical report")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {doc.page}")
    canvas.restoreState()


# ------------------------------------------------------------------------------------ content
def build() -> Path:
    f = load()
    t, T = f.t, f.tables
    figs = extra.make_all(f)
    bm = t["bmet"]
    pri, tests, checks, bt, sens = T["pri"], T["tests"], T["checks"], T["bt"], T["sens"]
    lo_usd, mid_usd, hi_usd = USD_PER_LITRE
    story = []

    # ================================================================ 1. EXECUTIVE SUMMARY
    story += [
        P("Vietnam Lubricant Demand Potential Monitor", "title"),
        P("Province-level market sizing for motorbike, passenger-car and heavy-duty lubricants, built on "
          "official government statistics and refreshed automatically", "subtitle"),
        P(f"{PROGRAM} &nbsp;|&nbsp; Author: {AUTHOR} &nbsp;|&nbsp; {dt.date.today():%d %B %Y} &nbsp;|&nbsp; "
          f"Code and data: <link href='{REPO_URL}' color='#2a78d6'>{REPO_URL}</link>", "small"),
        Spacer(1, 6),
        P("1. Executive Summary", "h1"),
        P("<b>Problem.</b> The lubricant sales team sets provincial targets, distributor coverage and sales "
          "headcount by splitting a national figure by population. Nobody can say how many litres of motorbike oil "
          "(MCO), passenger-car oil (PCMO) or heavy-duty oil (HDMO) each of Vietnam's 34 provinces can absorb. "
          "Every refresh after a government release took about two working days of manual spreadsheet work."),
        P(f"<b>Approach.</b> An automated pipeline downloads {t['n_sources']} official tables from the "
          "National Statistics Office (NSO). The key table is the 2025 count of registered vehicles in each "
          "province. The pipeline harmonises the old 63-province series onto the new 34 provinces and stores "
          "everything in a DuckDB warehouse. It then runs a 10,000-draw Monte Carlo model that converts each "
          "province's fleet into litres per segment with 95% intervals, and forecasts to 2028 with back-tested "
          "methods. A sales dashboard shows the results and refreshes itself when the NSO publishes new numbers."),
        kpi_row([(f"{ml(t['total25'], 0)} M L", f"2025 demand potential<br/>95%: {ml(t['lo25'], 0)}-{ml(t['hi25'], 0)} M L"),
                 (f"{ml(t['total28'], 0)} M L", f"2028 forecast<br/>CAGR {pct(t['cagr'], 1)}"),
                 (f"~USD {t['value25_usd_m']:,.0f} M", "indicative market value 2025<br/>(USD 1.56-1.93 per litre)"),
                 (f"{pct(t['misallocated_share'])}", "of volume mis-allocated by<br/>the population rule of thumb")]),
        Spacer(1, 8),
        P("<b>Key findings</b>"),
    ]
    story += bullets([
        f"Motorbike oil is the largest segment ({ml(t['MCO25'])} M L), but <b>passenger-car oil grows fastest</b> "
        f"(+{pct(t['PCMO_growth'])} by 2028). <b>Heavy-duty oil adds the most volume</b> "
        f"(+{ml(t['HDMO28'] - t['HDMO25'])} M L), driven by road freight, which has grown "
        f"{pct(t['freight_growth_2011_25'])} since 2011.",
        f"Ten tier-A provinces hold {pct(t['tierA_share'])} of 2025 demand and {pct(t['tierA_incr_share'])} of growth "
        f"to 2028. Nine of them are robust: they rank in the top 10 in at least 90% of simulations.",
        f"The population rule of thumb mis-states provincial volumes by {bm['mean_abs_diff_vs_population_share_pct']:.0f}% "
        f"on average (up to {bm['max_abs_diff_vs_population_share_pct']:.0f}%). It mis-allocates "
        f"{ml(t['misallocated_litres'])} M L (about USD {t['misallocated_usd_m']:,.0f} M) and would pick 2 of the "
        "wrong top-10 provinces.",
        "Vehicle density differs strongly by region. Its relationship with income is an inverted U: rising income "
        "adds vehicles in poorer provinces, but in the richest provinces it shifts demand from motorbikes to cars.",
        f"The refresh takes about {t['refresh_seconds']:.0f} seconds instead of about two days "
        f"(~{t['hours_saved_year']} analyst-hours saved a year). Every step is validated: the 63-to-34 roll-up "
        f"matches official totals within {t['rec_max']:.3f}%.",
    ])
    story += [P("<b>Recommendation.</b> Concentrate distributor and sales effort on the nine robust tier-A provinces. "
                "Lead with heavy-duty and fleet oils in the freight corridors (Hai Phong, Nghe An, Ninh Binh) and "
                "with PCMO in the high-income metros (Ho Chi Minh City, Ha Noi). Use the dashboard's 95% ranges "
                "rather than single numbers when setting targets. Fund one workshop survey of motorbike "
                "oil-change intervals, the single biggest source of uncertainty."),
              PageBreak()]

    # ================================================================ 2. INTRODUCTION
    story += [P("2. Introduction &amp; Business Context", "h1"),
              P("2.1 Why the problem matters", "h2"),
              P(f"Vietnam has {t['vehicles_total_k'] / 1000:,.1f} million registered cars and motorbikes, "
                f"{t['density_nat']:,.0f} per 1,000 people (NSO, 2025), one of the highest motorisation rates in "
                f"Asia. Published estimates put the lubricant market at 321-380 million litres and about "
                f"USD 594-620 million in 2025, growing about 5% a year. In a market this size, where a company puts "
                "its distributors and sales staff largely decides its volume and margin. A province under-served "
                "today loses share to competitors that is hard to win back."),
              P("2.2 Current practice and its pitfalls", "h2")]
    story += bullets([
        "<b>Top-down split by population:</b> ignores large differences in vehicle ownership, income and freight "
        "between provinces (quantified in section 5: up to 72% error for a single province).",
        "<b>Manual spreadsheets built from yearbook PDFs and press articles:</b> about two working days per refresh, "
        "unit errors (thousands vs units), no record of sources, no version history.",
        "<b>Paid consultancy reports:</b> national or regional only, annual, black-box methods, and expensive.",
        "<b>The July 2025 administrative reform</b> merged 63 provinces into 34, which broke every existing "
        "provincial spreadsheet and time series.",
    ])
    story += [P("2.3 Objectives, KPIs and hypotheses", "h2"),
              table([["KPI", "Definition", "Target", "Achieved"],
                     ["Demand potential", "Litres/year by province x segment with 95% interval", "34 x 3 segments",
                      "Yes: 102 series, 2025-2028"],
                     ["Forecast accuracy", "Hold-out 2023-2025, fit on years up to 2022",
                      "National MAPE <= 10%, median province <= 15%",
                      f"Freight {bt.set_index('variable').loc['road_freight_kt', 'national_mape_drift']:.1f}% / "
                      f"{bt.set_index('variable').loc['road_freight_kt', 'median_province_mape_drift']:.1f}%; "
                      f"population 0.4% / 0.4%"],
                     ["Beat baselines", "Lower hold-out error than naive; different allocation from population share",
                      "Yes / measurable", f"Yes; mean difference {bm['mean_abs_diff_vs_population_share_pct']:.0f}%"],
                     ["Refresh effort", "Time from NSO release to updated dashboard", "< 15 min, no manual steps",
                      f"~{t['refresh_seconds']:.0f} s, scheduled weekly"],
                     ["Decision output", "Ranked priority provinces with segment focus and robustness", "Top 10",
                      "Tier A/B/C + P(top 10)"]],
                    [2.6 * cm, 5.6 * cm, 4.1 * cm, 4.7 * cm]),
              Spacer(1, 6),
              P("Hypotheses, set before modelling and tested only on <i>observed</i> data (testing model outputs "
                "would be circular), with a Holm correction at alpha = 0.05:"),
              ]
    story += bullets(["<b>H1</b>: vehicle density (vehicles per 1,000 people) differs between the six regions.",
                      "<b>H2</b>: vehicle density rises with GRDP per capita, controlling for urbanisation.",
                      "<b>H3</b>: provinces with lower density grow faster in real GRDP (catch-up headroom)."])
    story += [P("2.4 Stakeholders and decisions", "h2"),
              table([["Stakeholder", "Decision supported"],
                     ["National Sales Director", "Regional volume targets; where to add sales headcount"],
                     ["Regional / area sales managers", "Territory plans; which provinces and key accounts first"],
                     ["Distributor development", "Where to appoint or expand distributors"],
                     ["Marketing / trade marketing", "Product mix (MCO vs PCMO vs HDMO) and budget by region"],
                     ["Supply chain", "Depot stock levels by region"]], [5.2 * cm, 11.8 * cm]),
              PageBreak()]

    # ================================================================ 3. DATA ARCHITECTURE & METHODOLOGY
    story += [P("3. Data Architecture &amp; Methodology", "h1"),
              P("3.1 Data sources", "h2"),
              P(f"All {t['n_sources']} tables come from the NSO PX-Web database (pxweb.nso.gov.vn). They are official "
                "statistics published for public use under the Law on Statistics (No. 89/2015/QH13). There is no "
                "personal data (all figures are province aggregates) and no employer data. Each download is archived "
                "unchanged, with its URL, time and SHA-256 hash, in data/raw/manifest.csv."),
              table([["Table", "Content", "Geography", "Years"],
                     ["PL.V14.59", "<b>Registered vehicles (cars + motorbikes)</b>; accidents per 10,000 vehicles", "34 provinces", "2025"],
                     ["PL.V02.02-04 / V02.03-07", "Population, urban / rural", "34 / 63 provinces", "2020-25 / 1995-2025"],
                     ["PL.V03.02 / V03.12", "GRDP per capita", "34 / 63", "2020-25 / 2018-25"],
                     ["PL.V03.01", "Real GRDP growth index", "34", "2020-25"],
                     ["PL.V12.07 / V12.17", "Road freight carried", "34 / 63", "2020-25 / 2000-25"],
                     ["PL.V12.03 / V12.07", "Road passengers carried", "34 / 63", "2020-25 / 2000-25"],
                     ["PL.V14.11, PL.V14.55, PL.V02.01", "Income per capita; accidents; area", "34", "2025"],
                     ["V07.05", "Motorbikes and cars assembled", "national", "1995-2025"]],
                    [4.0 * cm, 7.4 * cm, 2.9 * cm, 2.7 * cm]),
              Spacer(1, 6),
              P("3.2 Architecture", "h2"),
              fig(figs["architecture"], W, "Figure 1. Pipeline architecture. One command (python -m vnlube.pipeline) "
                  "runs every stage; a weekly scheduled task triggers it, and it rebuilds only when a source changed."),
              P("3.3 Architectural decisions and why", "h2"),
              table([["Decision", "Alternative rejected", "Why"],
                     ["JSON-stat download via the PX-Web form route", "PX file format; JSON API only",
                      "The PX export is ISO-8859-15 and silently replaces Vietnamese letters with '?'. The JSON API "
                      "exposes only some databases and returned 404 intermittently."],
                     ["DuckDB in-process warehouse, cleaning in SQL", "pandas scripts; a database server",
                      "Version-controlled SQL with window functions (interpolation, series bounds), zero setup, a single "
                      "file Power BI can read, and scales unchanged if monthly series are added."],
                     ["SHA-256 change detection + weekly schedule", "Rebuild on a fixed timer",
                      "No-change checks finish in ~30 s; previous releases are archived for audit."],
                     ["Official 34-province geography, history rolled up", "Keep 63 provinces",
                      "Sales territories follow the post-2025 provinces; the roll-up is validated against NSO's "
                      "own 34-province figures."],
                     ["Monte Carlo with triangular ranges", "Single point estimate",
                      "Usage assumptions are uncertain; ranges give honest 95% intervals and robustness of rankings."],
                     ["Hypotheses on observed data only", "Testing model outputs", "Avoids circular evidence."],
                     ["Forecast method chosen by back-test", "Always ETS",
                      "Damped ETS lost to drift on freight (20.9% vs 13.3% MAPE); the pipeline selects automatically."],
                     ["Streamlit app + Power BI star schema", "Static charts", "Interactive and refreshable; "
                      "what-if sliders let sales test assumptions without code."]],
                    [4.3 * cm, 3.4 * cm, 9.3 * cm]),
              P("3.4 Data preparation", "h2"),
              P(f"The {t['n_raw_cells']:,} raw cells were staged into one long table, then cleaned in SQL. Nothing is "
                "dropped blindly: each problem has a documented treatment and a data-quality table that a test enforces."),
              table([["Problem found in the raw data", "Treatment", "Evidence"],
                     ["Two look-alike capitals for D (U+0110 vs U+00D0), 'TP.Ho Chi Minh' without a space, "
                      "renamed provinces", "ASCII matching key (SQL macro) + alias table", "0 unmatched labels"],
                     ["Year labels 'So bo 2025' (preliminary) and 'Uoc tinh 2025' (estimate)",
                      "Parse year, keep a data-status column", "Flags carried into the marts"],
                     ["'..' cells", "Structural gaps (unit did not exist) left empty; interior gaps interpolated and flagged",
                      "1 random gap (Hoa Binh 2019, passengers)"],
                     ["63 former provinces in history vs 34 today", "Official merger map; roll-up from 2008",
                      f"Max difference vs official 34-province data: {t['rec_max']:.3f}%"],
                     ["Urban/rural reclassification in 2025", "Series-break table; models use 2024 urban share",
                      f"{t['n_breaks_2025']} provinces affected"],
                     ["Extreme values", "Robust z-score (median/MAD) > 3.5, reported not deleted",
                      f"Accident-rate outliers: {', '.join(t['outliers'])}"],
                     ["Province totals vs published totals", "Reconciliation check", "Exact match, all 6 regions + national"]],
                    [6.0 * cm, 6.0 * cm, 5.0 * cm]),
              P("3.5 Exploratory data analysis: what the data says", "h2")]
    story += bullets([
        f"<b>Motorisation is near saturation.</b> Density ranges from {t['density_min'][1]:,.0f} (Son La) to "
        f"{t['density_max'][1]:,.0f} vehicles per 1,000 people (Khanh Hoa). Motorbike assembly has plateaued at "
        f"3-4 million a year since 2011, while car assembly rose from {t['cars_assembled_2015']:,.0f}k (2015) to "
        f"{t['cars_assembled_2025']:,.0f}k (2025). Growth is shifting from motorbikes to cars, i.e. from MCO to PCMO.",
        f"<b>Freight is the fastest-moving driver.</b> Road freight grew {pct(t['freight_growth_2011_25'])} since 2011, "
        f"against population growth of {pct(t['pop_growth_2011_25'])}. The fastest growth (2020-25) is in Dien Bien, "
        "Quang Ninh and Ninh Binh. This is the HDMO opportunity.",
        f"<b>Income and urbanisation move together</b> (Spearman rho = {t['rho_grdp_urban']:.2f}), so their effects "
        "must be separated in a multivariable model rather than read off one scatter plot.",
        "<b>The distributions are skewed</b> (GRDP per capita skew 1.8, freight 1.7). Log transforms and "
        "rank-based tests were used accordingly.",
    ])
    story += [fig(figs["eda_trends"], W, "Figure 2. National trends: freight more than doubled; motorbike assembly "
                  "plateaued while car assembly kept rising."),
              fig(FIG / "fig1_density_by_region.png", W * 0.78, "Figure 3. Vehicle density by region (dot = province, "
                  "bar = regional median). The Southeast and Mekong Delta are about 200 vehicles per 1,000 above the "
                  "northern regions."),
              fig(figs["corr"], W * 0.55, "Figure 3b. Rank correlations across the 34 provinces. Density tracks "
                  "urban share and income, which are themselves strongly correlated; freight tracks population."),
              P("3.6 Feature engineering and model design", "h2"),
              P("Features: vehicles per 1,000 people, log GRDP per capita, urban share (2024), relative income "
                "(province / national), freight share, real GRDP growth 2022-2025 (geometric mean of the official "
                "index) and freight per capita. The demand model then works in three steps:"),
              ]
    story += bullets([
        "<b>Fleet split.</b> NSO publishes cars and motorbikes as one total. The split comes from a national car "
        "anchor (6.8-7.6 M cars; about 52% are passenger cars), allocated by relative income raised to an "
        "elasticity (0.6-1.4) and, for commercial vehicles, by freight share. Motorbikes are the remainder, so "
        "the official total is conserved exactly in every draw.",
        "<b>Litres.</b> Fleet x active share x (annual km / oil-change interval) x litres per change x top-up "
        "factor. All 15 usage parameters are triangular ranges with a documented rationale.",
        "<b>Forecast.</b> Motorbikes and cars grow with population and real income per head (elasticity about 0 "
        "and about 1.2); commercial vehicles grow with forecast freight. Population and freight are forecast with "
        "the back-test winner among damped ETS, drift and naive.",
    ])
    story += [PageBreak()]

    # ================================================================ 4. IMPLEMENTATION & RESULTS
    tv = tests.set_index(tests["test"].str[:2])
    story += [P("4. Implementation &amp; Results", "h1"),
              P("4.1 Pipeline", "h2"),
              P(f"The pipeline is a Python package (src/vnlube) with SQL transformations, 18 automated tests, pinned "
                f"dependencies and a weekly Windows scheduled task. A full rebuild takes about {t['refresh_seconds']:.0f} s. "
                "Outputs: a DuckDB warehouse, a CSV/Parquet star schema, a Streamlit dashboard (ranking, drill-down, "
                "priority matrix, what-if sliders, evidence tab), an auto-written findings note and an executed "
                "notebook covering every preparatory step."),
              P("4.2 Hypothesis tests", "h2"),
              table([["Hypothesis", "Method", "Statistic", "p (Holm)", "Result"]] +
                    [[r["test"], r["method"], f"{r['statistic']:.3f}", f"{r['p_holm']:.3f}",
                      "Reject H0" if r["reject_h0"] else "Not rejected"] for _, r in tests.iterrows()],
                    [5.3 * cm, 4.5 * cm, 2.0 * cm, 2.0 * cm, 3.2 * cm]),
              Spacer(1, 4)]
    story += bullets([
        f"<b>H1 confirmed</b> (epsilon squared = {tv.loc['H1', 'effect_size']:.2f}, a large effect).",
        "<b>H2, linear form, not supported.</b> With urban share in the model, the income elasticity is -0.03 "
        "(95% CI -0.22 to 0.16; region-clustered p = 0.75). Urban share is significant (p = 0.02).",
        "<b>H2 follow-up (exploratory).</b> The RESET test rejected the linear form. A quadratic term reveals an "
        "<b>inverted U</b>: elasticity +0.23 at 69 M VND per head (p = 0.04), about 0 at the median, -0.36 at "
        "169 M VND (p = 0.006), turning at about 97 M VND. It also has the best leave-one-out error (RMSE 0.162 "
        "vs 0.194 for the mean baseline). Because it was found after looking at the data, it is a hypothesis to "
        "re-test on the next release.",
        f"<b>H3 not supported</b> (rho = {tv.loc['H3', 'effect_size']:.2f}). There is no general catch-up "
        "effect, so growth has to be judged province by province.",
    ])
    story += [fig(figs["inverted_u"], W * 0.82, "Figure 4. Vehicle density against income: rising in poorer "
                  "provinces, falling in the richest, where cars replace motorbikes."),
              P("4.3 Model assumption checks", "h2"),
              table([["Model", "Assumption", "Check", "Result", "Remedy / consequence"]] +
                    [[r["model"], r["assumption"], r["check"],
                      ("pass" if r["passed"] else "<b>fail</b>") + (f" (p = {r['p_value']:.3f})" if r["p_value"] == r["p_value"] else f" ({r['statistic']:.2f})"),
                      r["consequence"]] for _, r in checks.iterrows()],
                    [2.1 * cm, 3.6 * cm, 3.0 * cm, 2.4 * cm, 5.9 * cm], font=8),
              P("All three failures are handled, and none changes the conclusions. Functional form: quadratic model "
                "(above). Independence: region fixed effects and region-clustered errors. Influence: refit without "
                "the 4 influential provinces. Monte Carlo checks also pass: the median moves less than 1% beyond "
                "2,500 draws and across seeds, parameters are uncorrelated (max |r| = 0.045), and the motorbike share "
                "never drops below 74%.", "small"),
              P("4.4 Forecast accuracy and baselines", "h2"),
              table([["Driver", "Chosen", "ETS (damped)", "Drift", "Naive (flat)", "National MAPE (chosen)"]] +
                    [[{"population_k": "Population", "road_freight_kt": "Road freight"}.get(r["variable"], r["variable"]),
                      r["chosen_method"],
                      f"{r['median_province_mape_ets_damped']:.1f}%", f"{r['median_province_mape_drift']:.1f}%",
                      f"{r['median_province_mape_naive']:.1f}%", f"{r['national_mape_' + r['chosen_method']]:.1f}%"]
                     for _, r in bt.iterrows()],
                    [3.3 * cm, 2.2 * cm, 2.6 * cm, 2.2 * cm, 2.6 * cm, 4.1 * cm]),
              P("Median province MAPE on the 2023-2025 hold-out. Both targets are met. Freight forecasts were biased "
                "about 12% low (freight accelerated after 2022), so the HDMO growth figures should be read as a "
                "lower bound.", "small"),
              P("4.5 Demand potential", "h2"),
              table([["Segment", "2025 median", "95% interval", "2028 median", "Change"]] +
                    [[SEG_NAME[s], f"{ml(t[s + '25'])} M L",
                      "{}-{} M L".format(*[ml(float(T["nat"].loc[(T["nat"]["segment"] == s) & (T["nat"]["year"] == 2025), c].iloc[0]))
                                           for c in ("litres_p025", "litres_p975")]),
                      f"{ml(t[s + '28'])} M L", f"+{pct(t[s + '_growth'])}"]
                     for s in ["MCO", "PCMO", "HDMO"]] +
                    [["<b>Total</b>", f"<b>{ml(t['total25'])} M L</b>", f"{ml(t['lo25'])}-{ml(t['hi25'])} M L",
                      f"<b>{ml(t['total28'])} M L</b>", f"+{pct(t['total28'] / t['total25'] - 1)}"]],
                    [5.2 * cm, 2.9 * cm, 3.4 * cm, 2.9 * cm, 2.6 * cm]),
              Spacer(1, 6),
              fig(FIG / "fig4_national_forecast.png", W * 0.72, "Figure 5. National demand potential with 95% band, "
                  "by segment."),
              fig(FIG / "fig3_top_provinces.png", W * 0.8, "Figure 6. The 15 largest provinces by 2025 demand potential, "
                  "split by segment (median of 10,000 simulations)."),
              P("4.6 Priority ranking", "h2"),
              P("The score is 60% size of the 2025 market and 40% absolute growth to 2028. It is recomputed in every "
                "simulation, so P(top 10) shows how robust each pick is."),
              table([["#", "Province", "Region", "2025 M L", "+M L to 2028", "CAGR", "Growth focus", "P(top 10)"]] +
                    [[int(r["priority_rank"]), r["province_en"], r["region_en"], ml(r["litres_2025_p50"]),
                      ml(r["increment_2025_2028_p50"]), pct(r["cagr_2025_2028_p50"], 1), r["growth_focus_segment"],
                      pct(r["prob_top10"])] for _, r in pri.head(12).iterrows()],
                    [0.7 * cm, 3.0 * cm, 4.7 * cm, 1.6 * cm, 2.0 * cm, 1.4 * cm, 1.9 * cm, 1.7 * cm]),
              Spacer(1, 6),
              fig(figs["priority"], W * 0.78, "Figure 7. Priority matrix: market size (log scale) against added litres "
                  "to 2028; the five largest tier-A provinces labelled (full list in the table above)."),
              P("4.7 Model vs baselines, uncertainty and triangulation", "h2")]
    story += bullets([
        f"<b>Deterministic baseline</b> (all assumptions at their most likely value): {bm['national_deterministic_ML']:.1f} M L, "
        f"{bm['mc_vs_deterministic_pct']:.1f}% below the Monte Carlo median. The assumption ranges are skewed, "
        "and a point estimate hides that.",
        f"<b>Population-share baseline:</b> rank correlation {bm['spearman_model_vs_population_share']:.2f}, but "
        f"provincial volumes differ by {bm['mean_abs_diff_vs_population_share_pct']:.0f}% on average and 2 top-10 "
        "provinces change (Figure 8).",
        f"<b>Biggest uncertainty drivers:</b> the motorbike oil-change interval (rank correlation "
        f"{sens.iloc[0]['spearman_with_total_2025']:+.2f}), then heavy-duty annual km and motorbike annual km.",
        "<b>Triangulation:</b> the road-vehicle estimate (241 M L) sits between published figures for automotive "
        "engine oils (215 M L) and all lubricants including industrial (321-380 M L), as expected.",
    ])
    story += [fig(figs["baseline"], W * 0.7, "Figure 8. Model vs population-share rule of thumb, by province (2025)."),
              PageBreak()]

    # ================================================================ 5. STRATEGIC DEDUCTIONS & BUSINESS IMPACT
    story += [P("5. Strategic Deductions &amp; Business Impact", "h1"),
              P(f"Volumes are converted to value at an indicative USD {mid_usd:.2f} per litre (range "
                f"{lo_usd:.2f}-{hi_usd:.2f}). This rate is derived from published 2025 market value (USD 594-620 M) "
                "and volume (321-380 M L) estimates. The value figures are orders of magnitude for prioritisation, "
                "not a revenue forecast."),
              table([["Impact lever", "Quantification", "Business meaning"],
                     ["Market size made visible", f"{ml(t['total25'], 0)} M L (~USD {t['value25_usd_m']:,.0f} M) in 2025, "
                      f"95% range {ml(t['lo25'], 0)}-{ml(t['hi25'], 0)} M L", "Credible base for targets and budgets"],
                     ["Growth to capture", f"+{ml(t['increment'], 0)} M L a year by 2028 (~USD {t['value_incr_usd_m']:,.0f} M)",
                      f"{pct(t['tierA_incr_share'])} of it sits in the 10 tier-A provinces"],
                     ["Mis-allocation avoided", f"{ml(t['misallocated_litres'])} M L ({pct(t['misallocated_share'])} of "
                      f"volume, ~USD {t['misallocated_usd_m']:,.0f} M) placed in the wrong provinces by the population rule",
                      "Sales and distributor effort reallocated to where the vehicles are"],
                     ["Focus", f"10 provinces = {pct(t['tierA_share'])} of 2025 demand", "Coverage plan for 29% of provinces"],
                     ["Analyst time", f"~{t['hours_saved_year']} hours a year saved (2 days x 4 releases), refresh in "
                      f"~{t['refresh_seconds']:.0f} s", "Faster reaction to new official data, no copy-paste errors"],
                     ["Risk", "Every number has a 95% range, robustness score and data-quality audit trail",
                      "Targets set with known uncertainty; fewer surprises"]],
                    [3.6 * cm, 7.2 * cm, 6.2 * cm]),
              Spacer(1, 6),
              P("5.1 Strategic deductions", "h2")]
    story += bullets([
        "<b>Segment strategy follows the income curve.</b> Above about 97 M VND GRDP per head (14 provinces, "
        "including Ho Chi Minh City, Ha Noi, Hai Phong and Quang Ninh), motorbike density falls as cars take over. "
        "Prioritise PCMO, premium and synthetic grades and car-service channels there. Below the turning point, "
        "income growth still adds motorbikes, so defend MCO volume through motorbike repair shops.",
        "<b>Heavy-duty is the volume engine.</b> HDMO adds the most litres to 2028 and is the growth focus in all "
        "tier-A provinces. Pursue fleet and logistics accounts along the freight corridors (Hai Phong port, the Nghe "
        "An / Thanh Hoa north-south axis, Dong Nai industrial zones). Freight forecasts are conservative, so the "
        "upside is larger.",
        "<b>Correct the rule-of-thumb bias.</b> Population share over-weights mountainous, low-density provinces "
        "(Son La -59%, Lai Chau -52%) and under-weights industrial and port provinces (Quang Ninh +72%, Hai Phong "
        "+27%, Ho Chi Minh City +23%). Move coverage accordingly.",
        f"<b>Treat borderline provinces as options, not commitments.</b> Thanh Hoa (P(top 10) 37%) and "
        f"{', '.join(p for p in t['fragile'] if p != 'Thanh Hoa') or 'Tay Ninh'} sit on the boundary. "
        "Review them at each data release before committing new distributors.",
    ])
    story += [P("5.2 Recommended actions", "h2"),
              table([["Horizon", "Action", "Owner", "KPI"],
                     ["0-3 months", "Re-cut 2026 provincial targets using model medians and ranges; reallocate coverage "
                      "from over-weighted mountain provinces to tier A", "Sales Director", "Target vs P50 gap"],
                     ["0-3 months", "Fleet/HDMO account programme in Hai Phong, Nghe An, Ninh Binh, Dong Nai",
                      "Key accounts", "HDMO volume growth"],
                     ["3-6 months", "PCMO channel push (car workshops, premium grades) in HCMC, Ha Noi, Quang Ninh",
                      "Marketing", "PCMO share of mix"],
                     ["3-6 months", "Workshop survey of motorbike oil-change intervals (n about 200) to narrow the main "
                      "uncertainty", "Market research", "Width of the 95% interval"],
                     ["Ongoing", "Weekly automated refresh; quarterly review of tier B / borderline provinces",
                      "Sales ops", "Refresh SLA, ranking stability"]],
                    [2.2 * cm, 9.0 * cm, 2.8 * cm, 3.0 * cm]),
              PageBreak()]

    # ================================================================ 6. LIMITATIONS & FUTURE WORK
    story += [P("6. Limitations &amp; Future Work", "h1"), P("6.1 Limitations", "h2")]
    story += bullets([
        "<b>Modelled car/motorbike split.</b> NSO publishes one combined vehicle count per province. The split "
        "relies on national anchors and allocation assumptions; its uncertainty is inside the intervals, but it is "
        "the largest structural assumption.",
        "<b>One year of provincial fleet data.</b> The 34-province vehicle table exists for 2025 only, so fleet "
        "growth is driven by population, income and freight forecasts, not by an observed fleet time series.",
        "<b>Registered is not active.</b> There is no compulsory de-registration of motorbikes; the active-share "
        "range (70-90%) covers this but is itself an assumption.",
        "<b>Usage parameters are elicited, not measured.</b> Oil-change intervals and annual km come from owner "
        "manuals and workshop practice. The sensitivity analysis shows the motorbike interval dominates.",
        "<b>Small sample for inference.</b> There are 34 provinces with spatial correlation, so the hypothesis "
        "tests have limited power. The inverted U is exploratory.",
        "<b>Scope.</b> The model covers road-vehicle lubricants only (no industrial, marine or agricultural "
        "machinery) and potential demand, not one company's sales or share.",
    ])
    story += [P("6.2 Ethical and bias considerations", "h2")]
    story += bullets([
        "No personal data is used; all inputs are public province aggregates. Provincial vehicle counts are "
        "registration-based, so provinces where vehicles are registered but used elsewhere (e.g. company fleets in "
        "the big cities) are over-stated.",
        "Allocating effort by potential can under-serve poorer, mountainous provinces. The model shows their "
        "potential is genuinely lower, but distributor decisions should still consider service obligations and "
        "road-safety effects (Thai Nguyen and Lang Son have about 2.5x the national accident rate per vehicle).",
        "Market benchmarks come from commercial research firms and are used only for triangulation, never as inputs.",
    ])
    story += [P("6.3 What production scaling requires", "h2")]
    story += bullets([
        "<b>Add internal data:</b> join company sales by province to turn potential into share and white-space "
        "(potential minus sales). The star schema already has the province key.",
        "<b>Replace assumptions with measurements:</b> the oil-change interval survey; province-level car "
        "registrations from the Traffic Police or Vietnam Register if they become accessible.",
        "<b>Operations:</b> move the scheduled task to a server or cloud job with alerting on failed downloads "
        "(the manifest already logs failures), publish the dashboard behind company sign-in, and version the "
        "warehouse per release.",
        "<b>Re-test the inverted-U hypothesis</b> when the 2026 provincial vehicle table is published, and refit the "
        "car-allocation elasticity on the observed change.",
    ])
    story += [P("Appendix: Reproducibility", "h2"),
              P(f"Repository: <link href='{REPO_URL}' color='#2a78d6'>{REPO_URL}</link>. Setup: python -m venv .venv; "
                "pip install -r requirements.txt; pip install -e .; python -m vnlube.pipeline --offline. Preliminary model: "
                "notebooks/01_preliminary_model.ipynb (problem framing, cleaning, EDA, feature engineering, "
                "storage, model preparation, assumption checks, baselines). This report is generated by "
                "deliverables/build_report.py from the pipeline outputs.", "small")]

    out = OUT / "technical_report.pdf"
    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=2 * cm, rightMargin=2 * cm, topMargin=1.8 * cm,
                            bottomMargin=1.8 * cm, title="Vietnam Lubricant Demand Potential Monitor - Technical report",
                            author=AUTHOR, subject="upGrad BYOC capstone technical report")
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)
    return out


if __name__ == "__main__":
    print("wrote", build())
