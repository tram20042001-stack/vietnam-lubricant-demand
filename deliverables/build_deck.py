"""Build deliverables/executive_presentation.pptx (16:9) from the pipeline outputs.

    .venv\\Scripts\\python.exe -m deliverables.build_deck

Follows the upGrad template: hook & problem (2) -> methodology & architecture (2) ->
implementation & demo (4) -> lessons & trade-offs (1) -> conclusions & next steps (2),
plus two hidden appendix slides for Q&A. Charts are native PowerPoint charts (editable);
speaker notes carry the narration.
"""
from __future__ import annotations

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData, XyChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import (XL_CHART_TYPE, XL_LABEL_POSITION, XL_LEGEND_POSITION, XL_MARKER_STYLE,
                             XL_TICK_LABEL_POSITION)
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Emu, Inches, Pt

from vnlube import data_access as da
from vnlube import statistics as st

from .common import AUTHOR, FIG, OUT, PROGRAM, REPO_URL, SEG_NAME, load, ml, pct

# ------------------------------------------------------------------------------------ design tokens
NAVY = RGBColor(0x1E, 0x27, 0x61)       # dominant brand colour (title / closing / headings)
ICE = RGBColor(0xCA, 0xDC, 0xFC)        # light accent on navy
INK = RGBColor(0x1A, 0x1A, 0x1A)
INK2 = RGBColor(0x52, 0x51, 0x4E)
MUTED = RGBColor(0x89, 0x87, 0x81)
CARD = RGBColor(0xF1, 0xF4, 0xFA)       # card tint on white slides
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SEG = {"MCO": RGBColor(0x2A, 0x78, 0xD6), "PCMO": RGBColor(0xEB, 0x68, 0x34), "HDMO": RGBColor(0x1B, 0xAF, 0x7A)}
HEAD, BODY = "Cambria", "Calibri"
SW, SH = Inches(13.333), Inches(7.5)
MARGIN = Inches(0.6)


def text(slide, x, y, w, h, runs, size=16, color=INK, bold=False, font=BODY, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, name=None, spacing=None):
    """Add a text box. `runs` is a str, or a list of paragraphs; a paragraph is a str or a list of
    (text, {overrides}) tuples."""
    tb = slide.shapes.add_textbox(x, y, w, h)
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = Inches(0.04)
    tf.margin_top = tf.margin_bottom = Inches(0.02)
    tf.vertical_anchor = anchor
    paras = runs if isinstance(runs, list) else [runs]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        if spacing:
            p.space_after = Pt(spacing)
        parts = para if isinstance(para, list) else [(para, {})]
        for t_, o in parts:
            r = p.add_run()
            r.text = t_
            r.font.name = o.get("font", font)
            r.font.size = Pt(o.get("size", size))
            r.font.bold = o.get("bold", bold)
            r.font.italic = o.get("italic", False)
            r.font.color.rgb = o.get("color", color)
    return tb


def bullets(slide, x, y, w, h, items, size=15, color=INK, gap=6):
    """Real bulleted paragraphs (bullet character set in the paragraph properties, not typed)."""
    tb = text(slide, x, y, w, h, items, size=size, color=color, spacing=gap)
    for p in tb.text_frame.paragraphs:
        pPr = p._p.get_or_add_pPr()
        pPr.set("marL", str(Emu(Inches(0.25))))
        pPr.set("indent", str(-Emu(Inches(0.22))))
        bu = etree.SubElement(pPr, "{http://schemas.openxmlformats.org/drawingml/2006/main}buChar")
        bu.set("char", "•")
    return tb


def box(slide, x, y, w, h, fill=CARD, line=None, shape=MSO_SHAPE.ROUNDED_RECTANGLE, name=None):
    s = slide.shapes.add_shape(shape, x, y, w, h)
    if shape == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = 0.08
    s.fill.solid()
    s.fill.fore_color.rgb = fill
    if line is None:
        s.line.fill.background()
    else:
        s.line.color.rgb = line
        s.line.width = Pt(1)
    s.shadow.inherit = False
    if name:
        s.name = name
    return s


def title(slide, t, sub=None, dark=False):
    """Content-slide title at a fixed position on every slide."""
    text(slide, MARGIN, Inches(0.38), SW - 2 * MARGIN, Inches(0.8), t, size=30, bold=True, font=HEAD,
         color=WHITE if dark else NAVY, name="Title")
    if sub:
        text(slide, MARGIN, Inches(1.12), SW - 2 * MARGIN, Inches(0.45), sub, size=15,
             color=ICE if dark else INK2, name="Subtitle")


def footer(slide, n, dark=False):
    text(slide, MARGIN, SH - Inches(0.42), Inches(8), Inches(0.3), "Vietnam Lubricant Demand Potential Monitor",
         size=10, color=ICE if dark else MUTED)
    text(slide, SW - MARGIN - Inches(1), SH - Inches(0.42), Inches(1), Inches(0.3), str(n), size=10,
         color=ICE if dark else MUTED, align=PP_ALIGN.RIGHT)


def stat(slide, x, y, w, value, label, color=NAVY, vsize=40, bg=CARD, h=Inches(1.55), lcolor=INK2):
    box(slide, x, y, w, h, fill=bg)
    text(slide, x + Inches(0.2), y + Inches(0.12), w - Inches(0.4), Inches(0.8), value, size=vsize, bold=True,
         font=HEAD, color=color)
    text(slide, x + Inches(0.2), y + Inches(0.92), w - Inches(0.4), h - Inches(0.95), label, size=13, color=lcolor)


def style_chart(chart, legend=True, size=12):
    chart.font.name = BODY
    chart.font.size = Pt(size)
    chart.font.color.rgb = INK2
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(size)


def quiet_axes(chart, gridlines=True):
    va = chart.value_axis
    va.has_major_gridlines = gridlines
    if gridlines:
        va.major_gridlines.format.line.color.rgb = RGBColor(0xE1, 0xE0, 0xD9)
        va.major_gridlines.format.line.width = Pt(0.75)
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(11)
    va.tick_labels.font.color.rgb = MUTED
    ca = chart.category_axis
    ca.format.line.color.rgb = RGBColor(0xC3, 0xC2, 0xB7)
    ca.tick_labels.font.size = Pt(11)
    ca.tick_labels.font.color.rgb = INK2


def no_invert(series):
    """Stop PowerPoint drawing negative bars hollow: set invertIfNegative=0 on the series AND on every
    coloured data point (a <c:dPt> without the flag is drawn inverted)."""
    series.invert_if_negative = False
    ns = "{http://schemas.openxmlformats.org/drawingml/2006/chart}"
    for dpt in series._element.findall(f"{ns}dPt"):
        if dpt.find(f"{ns}invertIfNegative") is None:
            el = etree.SubElement(dpt, f"{ns}invertIfNegative")
            el.set("val", "0")
            dpt.remove(el)
            dpt.find(f"{ns}idx").addnext(el)   # schema order: idx, invertIfNegative, ..., spPr


def notes(slide, s):
    slide.notes_slide.notes_text_frame.text = s


def hide(slide):
    slide._element.set("show", "0")


# ------------------------------------------------------------------------------------ deck
def build():
    f = load()
    t, T = f.t, f.tables
    bm = t["bmet"]
    pri, nat = T["pri"], T["nat"]
    prs = Presentation()
    prs.slide_width, prs.slide_height = SW, SH
    blank = prs.slide_layouts[6]
    n = 0

    def new(dark=False):
        nonlocal n
        n += 1
        s = prs.slides.add_slide(blank)
        bg = s.background.fill
        bg.solid()
        bg.fore_color.rgb = NAVY if dark else WHITE
        return s

    # 1 ---------------------------------------------------------------- title (hook)
    s = new(dark=True)
    text(s, MARGIN, Inches(1.7), Inches(11.5), Inches(0.5), "VIETNAM LUBRICANT DEMAND POTENTIAL", size=16,
         bold=True, color=ICE)
    text(s, MARGIN, Inches(2.2), Inches(11.8), Inches(2.0),
         f"Where Vietnam's next {ml(t['increment'], 0)} million litres of lubricant demand will come from",
         size=44, bold=True, font=HEAD, color=WHITE)
    text(s, MARGIN, Inches(4.45), Inches(11), Inches(0.9),
         "Province-level market sizing for motorbike, car and heavy-duty oils from official government data, "
         "refreshed automatically", size=18, color=ICE)
    text(s, MARGIN, Inches(6.2), Inches(11.5), Inches(0.6), f"{PROGRAM}   |   {AUTHOR}   |   {REPO_URL}",
         size=12, color=ICE)
    notes(s, "Open with the question sales leadership asks every planning cycle: where should our next "
             "distributor, sales rep and marketing budget go? Today that answer comes from a population split. "
             f"This project replaces it with a validated, automatically refreshed estimate: {ml(t['total25'], 0)} "
             f"million litres today, growing by {ml(t['increment'], 0)} million litres a year by 2028.")

    # 2 ---------------------------------------------------------------- problem
    s = new()
    title(s, f"We plan a ~USD {round(t['value25_usd_m'], -1):,.0f} M market with a rule of thumb",
          "Today: national total x population share, rebuilt by hand in spreadsheets after every government release")
    cw = (SW - 2 * MARGIN - Inches(0.9)) / 4
    stats = [(f"{t['vehicles_total_k'] / 1000:,.1f} M", "registered cars and motorbikes (NSO, 2025)", NAVY),
             (f"{ml(t['total25'], 0)} M L", f"lubricant demand potential 2025, ~USD {t['value25_usd_m']:,.0f} M", NAVY),
             (f"{bm['mean_abs_diff_vs_population_share_pct']:.0f}%", "average error of the population split per "
              f"province (up to {bm['max_abs_diff_vs_population_share_pct']:.0f}%)", SEG["PCMO"]),
             ("2 days", "manual work per data refresh; 63 -> 34 provinces broke every sheet", SEG["PCMO"])]
    for i, (v, lbl, c) in enumerate(stats):
        stat(s, MARGIN + i * (cw + Inches(0.3)), Inches(1.9), cw, v, lbl, color=c, h=Inches(1.9))
    box(s, MARGIN, Inches(4.25), SW - 2 * MARGIN, Inches(2.35), fill=WHITE, line=RGBColor(0xE1, 0xE0, 0xD9))
    text(s, MARGIN + Inches(0.3), Inches(4.4), Inches(6), Inches(0.4), "The decisions at stake", size=18,
         bold=True, font=HEAD, color=NAVY)
    bullets(s, MARGIN + Inches(0.3), Inches(4.9), Inches(5.8), Inches(1.6),
            ["Which provinces get new distributors and sales reps",
             "Provincial volume targets for 2026",
             "Product mix: motorbike vs car vs heavy-duty oil"], size=15)
    text(s, Inches(7.0), Inches(4.4), Inches(5.6), Inches(0.4), "What a wrong split costs", size=18, bold=True,
         font=HEAD, color=NAVY)
    bullets(s, Inches(7.0), Inches(4.9), Inches(5.6), Inches(1.6),
            [f"{ml(t['misallocated_litres'])} M L (~USD {t['misallocated_usd_m']:,.0f} M) of demand placed in the wrong provinces",
             "2 of the true top-10 provinces missed",
             "Targets that ignore where the vehicles actually are"], size=15)
    footer(s, n)
    notes(s, "Four numbers frame the problem. The market is large. The current method splits it by headcount, "
             f"which mis-states a typical province by {bm['mean_abs_diff_vs_population_share_pct']:.0f}% and "
             "Quang Ninh by more than 70%. Each refresh takes two days, and the 2025 merger of 63 provinces into 34 "
             "broke every historical spreadsheet. The value figures use an indicative USD 1.75 per litre derived "
             "from published market estimates.")

    # 3 ---------------------------------------------------------------- architecture
    s = new()
    title(s, "One command turns 14 government tables into a sales plan",
          "Automated, validated, and rebuilt only when the statistics office publishes something new")
    steps = [("1", "Ingest", "14 NSO tables as UTF-8 JSON-stat; retries; SHA-256 change detection"),
             ("2", "Clean in SQL", "Names, years, gaps; 63 -> 34 provinces; 0.000% reconciliation"),
             ("3", "Test & forecast", "Hypotheses on observed data; forecasts chosen by back-test"),
             ("4", "Simulate", "10,000 Monte Carlo draws: fleet -> litres, 95% ranges"),
             ("5", "Deliver", "Dashboard, what-if sliders, Power BI schema, auto report")]
    sw_ = (SW - 2 * MARGIN - Inches(0.25) * 4) / 5
    for i, (k, h_, d) in enumerate(steps):
        x = MARGIN + i * (sw_ + Inches(0.25))
        box(s, x, Inches(1.95), sw_, Inches(2.6), fill=CARD)
        c = s.shapes.add_shape(MSO_SHAPE.OVAL, x + Inches(0.2), Inches(2.15), Inches(0.55), Inches(0.55))
        c.fill.solid(); c.fill.fore_color.rgb = NAVY; c.line.fill.background()
        c.text_frame.text = k
        c.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER
        r = c.text_frame.paragraphs[0].runs[0]
        r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(16), True, WHITE, BODY
        text(s, x + Inches(0.2), Inches(2.85), sw_ - Inches(0.4), Inches(0.5), h_, size=16, bold=True, color=NAVY)
        text(s, x + Inches(0.2), Inches(3.35), sw_ - Inches(0.4), Inches(1.15), d, size=13, color=INK2)
        if i < 4:
            # connector coordinates must be integer EMU (a float like 2602931.0 makes the file unopenable)
            a = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, int(x + sw_ + Inches(0.02)), int(Inches(3.25)),
                                       int(x + sw_ + Inches(0.23)), int(Inches(3.25)))
            a.line.color.rgb = MUTED; a.line.width = Pt(2)
            a.line._get_or_add_ln().append(etree.fromstring(
                '<a:tailEnd xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" type="triangle"/>'))
    text(s, MARGIN, Inches(4.85), Inches(5), Inches(0.4), "Why these choices", size=18, bold=True, font=HEAD, color=NAVY)
    whys = [("DuckDB, not a server", "Cleaning as version-controlled SQL, zero setup, one file Power BI can read"),
            ("JSON-stat, not PX files", "The PX export silently destroys Vietnamese letters"),
            ("Ranges, not one number", "Usage habits are uncertain; targets need honest bands")]
    ww = (SW - 2 * MARGIN - Inches(0.6)) / 3
    for i, (h_, d) in enumerate(whys):
        x = MARGIN + i * (ww + Inches(0.3))
        text(s, x, Inches(5.35), ww, Inches(1.3), [[(h_, {"bold": True, "color": NAVY})], d], size=14, spacing=3)
    footer(s, n)
    notes(s, "The architecture in one line: download, clean, test, simulate, deliver. Three choices matter. "
             "DuckDB keeps all cleaning in auditable SQL without a server. JSON-stat because the statistics office's "
             "PX export loses Vietnamese characters, which would destroy province names. Ranges, because nobody knows "
             "exactly how often a motorbike's oil is changed, and pretending otherwise produces false precision. "
             "A weekly scheduled task checks for new releases; if nothing changed it stops in about 30 seconds.")

    # 4 ---------------------------------------------------------------- methodology: vehicles -> litres
    s = new()
    title(s, "From official vehicle counts to litres",
          "The fleet is official; usage is uncertain, so every assumption is a range simulated 10,000 times")
    chain = [("Vehicle count", f"{t['vehicles_total_k'] / 1000:,.1f} M\nofficial, by province"),
             ("Split by segment", "cars by income,\ntrucks by freight"),
             ("x active share", "70-90% of\nmotorbikes in use"),
             ("x oil changes / yr", "annual km /\nchange interval"),
             ("x litres / change", "+ gear & top-up\nfluids"),
             ("= litres / year", "per province,\nsegment, year")]
    cw2 = (SW - 2 * MARGIN - Inches(0.2) * 5) / 6
    for i, (h_, d) in enumerate(chain):
        x = MARGIN + i * (cw2 + Inches(0.2))
        box(s, x, Inches(1.9), cw2, Inches(1.65), fill=NAVY if i in (0, 5) else CARD)
        text(s, x + Inches(0.12), Inches(2.02), cw2 - Inches(0.24), Inches(0.5), h_, size=14, bold=True,
             color=WHITE if i in (0, 5) else NAVY)
        text(s, x + Inches(0.12), Inches(2.55), cw2 - Inches(0.24), Inches(0.95), d, size=13,
             color=ICE if i in (0, 5) else INK2)
    # litres per vehicle native bar chart
    cd = CategoryChartData()
    lpv = {"MCO": 1.57, "PCMO": 7.44, "HDMO": 23.89}   # medians, recomputed below from the assumptions
    try:
        from vnlube import demand
        p_ = demand.draw_parameters(da.triangular_table("ref_lubricant_assumptions"),
                                    da.triangular_table("ref_fleet_split_assumptions"), n=10000, seed=2025)
        import numpy as np
        lpv = {k: float(np.median(p_[f"{k}.active_share"] * p_[f"{k}.annual_km"] / p_[f"{k}.drain_interval_km"]
                                  * p_[f"{k}.fill_litres"] * p_[f"{k}.other_fluids_factor"])) for k in lpv}
    except Exception:  # noqa: BLE001 - fall back to the documented medians
        pass
    cd.categories = ["Motorbike", "Passenger car", "Truck / bus"]
    cd.add_series("Litres per registered vehicle per year (median)", [round(v, 1) for v in lpv.values()])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, MARGIN, Inches(3.95), Inches(6.2), Inches(2.6), cd)
    ch = gf.chart
    style_chart(ch, legend=False)
    quiet_axes(ch, gridlines=False)
    ch.value_axis.visible = False
    ch.has_title = True
    ch.chart_title.text_frame.text = "Litres per registered vehicle per year (median)"
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(13)
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.color.rgb = INK2
    pl = ch.plots[0]
    pl.gap_width = 60
    pl.has_data_labels = True
    pl.data_labels.number_format = '0.0" L"'
    pl.data_labels.number_format_is_linked = False
    pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    pl.data_labels.font.size = Pt(13)
    for i, k in enumerate(["MCO", "PCMO", "HDMO"]):
        pt = pl.series[0].points[i]
        pt.format.fill.solid(); pt.format.fill.fore_color.rgb = SEG[k]
    ch.category_axis.reverse_order = True
    text(s, Inches(7.2), Inches(3.95), Inches(5.5), Inches(0.4), "Proof the data can be trusted", size=18, bold=True,
         font=HEAD, color=NAVY)
    bullets(s, Inches(7.2), Inches(4.45), Inches(5.5), Inches(2.2),
            [f"Old 63-province history rolled up to the 34 new provinces matches official figures within {t['rec_max']:.3f}%",
             "Provinces add up exactly to the published regional and national vehicle totals",
             "Gaps classified (unit did not exist vs missing); nothing dropped blindly",
             "18 automated tests run on every rebuild"], size=14)
    footer(s, n)
    notes(s, "This is the whole model on one line. The vehicle count is official. Cars are allocated by income and "
             "trucks by freight, so the official total is always conserved. Each vehicle type is then turned into "
             "litres with ranges for how much it is used and how often its oil is changed. A motorbike uses about "
             f"{lpv['MCO']:.1f} litres a year and a truck about {lpv['HDMO']:.0f}, which is why trucks matter far "
             "more than their numbers suggest. On the right, why the inputs can be trusted: the historical "
             "roll-up reproduces the official 34-province figures to the third decimal.")

    # 5 ---------------------------------------------------------------- results: national
    s = new()
    title(s, f"{ml(t['total25'], 0)} M litres today, {ml(t['total28'], 0)} M by 2028",
          f"Cars and trucks drive the growth. Bars: segment medians of 10,000 simulations (total 95% range 2025: "
          f"{ml(t['lo25'], 0)}-{ml(t['hi25'], 0)} M L)")
    cd = CategoryChartData()
    years = [2025, 2026, 2027, 2028]
    cd.categories = [str(y) for y in years]
    for seg in ["MCO", "PCMO", "HDMO"]:
        vals = [float(nat.loc[(nat["segment"] == seg) & (nat["year"] == y), "litres_p50"].iloc[0]) for y in years]
        cd.add_series(SEG_NAME[seg], [round(v / 1e6, 1) for v in vals])
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_STACKED, MARGIN, Inches(1.75), Inches(7.6), Inches(5.0), cd)
    ch = gf.chart
    style_chart(ch)
    quiet_axes(ch)
    ch.value_axis.has_title = True
    ch.value_axis.axis_title.text_frame.text = "million litres"
    ch.value_axis.axis_title.text_frame.paragraphs[0].runs[0].font.size = Pt(11)
    pl = ch.plots[0]
    pl.gap_width = 55
    pl.overlap = 100
    pl.has_data_labels = True
    pl.data_labels.position = XL_LABEL_POSITION.CENTER
    pl.data_labels.font.size = Pt(12)
    pl.data_labels.font.color.rgb = WHITE
    pl.data_labels.number_format = "0"
    pl.data_labels.number_format_is_linked = False
    for i, seg in enumerate(["MCO", "PCMO", "HDMO"]):
        ser = pl.series[i]
        ser.format.fill.solid(); ser.format.fill.fore_color.rgb = SEG[seg]
        ser.format.line.color.rgb = WHITE; ser.format.line.width = Pt(1.5)
    x0 = Inches(8.55)
    stat(s, x0, Inches(1.85), Inches(4.2), f"+{pct(t['PCMO_growth'])}", "passenger-car oil 2025->2028:\nfastest growing segment",
         color=SEG["PCMO"], vsize=36, h=Inches(1.5))
    stat(s, x0, Inches(3.5), Inches(4.2), f"+{ml(t['HDMO28'] - t['HDMO25'])} M L", "heavy-duty oil: largest absolute gain,\n"
         f"freight up {pct(t['freight_growth_2011_25'])} since 2011", color=SEG["HDMO"], vsize=36, h=Inches(1.5))
    stat(s, x0, Inches(5.15), Inches(4.2), f"{ml(t['MCO25'], 0)} M L", "motorbike oil: largest today,\nbut near saturation",
         color=SEG["MCO"], vsize=36, h=Inches(1.5))
    footer(s, n)
    notes(s, f"The market is about {ml(t['total25'], 0)} million litres, with an honest range of "
             f"{ml(t['lo25'], 0)} to {ml(t['hi25'], 0)}. Published market estimates sit either side of this: "
             "215 million for engine oils only, 320 to 380 including industrial oils, so the order of magnitude checks "
             f"out. Growth is {pct(t['cagr'], 1)} a year. Motorbike oil is the biggest segment but barely grows: "
             "motorbike assembly has been flat for a decade. Car oil grows fastest; heavy-duty oil adds the most "
             "litres because road freight has more than doubled.")

    # 6 ---------------------------------------------------------------- results: where (top provinces)
    s = new()
    title(s, f"Ten provinces hold {pct(t['tierA_share'])} of demand and {pct(t['tierA_incr_share'])} of growth",
          "Priority = 60% market size + 40% growth to 2028, recomputed in each of 10,000 simulations")
    top = pri.head(10).iloc[::-1]
    cd = CategoryChartData()
    cd.categories = list(top["province_en"])
    for seg, col in [("MCO", "mco_share_2025"), ("PCMO", "pcmo_share_2025"), ("HDMO", "hdmo_share_2025")]:
        cd.add_series(SEG_NAME[seg], [round(a * b / 1e6, 2) for a, b in zip(top[col], top["litres_2025_p50"])])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_STACKED, MARGIN, Inches(1.75), Inches(7.4), Inches(5.0), cd)
    ch = gf.chart
    style_chart(ch)
    quiet_axes(ch)
    ch.value_axis.has_title = True
    ch.value_axis.axis_title.text_frame.text = "million litres, 2025"
    ch.value_axis.axis_title.text_frame.paragraphs[0].runs[0].font.size = Pt(11)
    pl = ch.plots[0]
    pl.gap_width = 45
    pl.overlap = 100
    for i, seg in enumerate(["MCO", "PCMO", "HDMO"]):
        ser = pl.series[i]
        ser.format.fill.solid(); ser.format.fill.fore_color.rgb = SEG[seg]
        ser.format.line.color.rgb = WHITE; ser.format.line.width = Pt(1.5)
    # robustness table
    rows = [("Province", "+M L to 2028", "P(top 10)")] + [
        (r["province_en"], f"+{r['increment_2025_2028_p50'] / 1e6:.1f}", pct(r["prob_top10"])) for _, r in pri.head(10).iterrows()]
    tbl = s.shapes.add_table(len(rows), 3, Inches(8.3), Inches(1.85), Inches(4.45), Inches(4.4)).table
    tbl.columns[0].width, tbl.columns[1].width, tbl.columns[2].width = Inches(1.95), Inches(1.3), Inches(1.2)
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            cell = tbl.cell(i, j)
            cell.text = v
            p = cell.text_frame.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT
            r = p.runs[0]
            r.font.size, r.font.name = Pt(13), BODY
            fragile = i > 0 and float(pri.iloc[i - 1]["prob_top10"]) < 0.9
            r.font.bold = i == 0
            r.font.color.rgb = WHITE if i == 0 else (SEG["PCMO"] if fragile and j == 2 else INK)
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if i == 0 else (CARD if i % 2 == 0 else WHITE)
            cell.margin_top = cell.margin_bottom = Inches(0.03)
    text(s, Inches(8.3), Inches(6.35), Inches(4.45), Inches(0.5),
         "Orange = borderline: in the top 10 in under 90% of simulations", size=11, color=INK2)
    footer(s, n)
    notes(s, "Where is it? Ten provinces carry most of the market and most of the growth. The table shows how robust "
             f"each pick is: nine of the ten are in the top 10 in at least 90% of simulations. Thanh Hoa makes it in only "
             f"{pct(float(pri.set_index('province_en').loc['Thanh Hoa', 'prob_top10']))} of simulations, so treat it as an "
             "option to review, not a commitment. Heavy-duty oil is the growth focus in every tier-A province.")

    # 7 ---------------------------------------------------------------- insight: inverted U (native XY)
    s = new()
    title(s, "Richer provinces switch from motorbikes to cars",
          "Vehicle density vs income across 34 provinces: rises, peaks near 97 M VND per head, then falls")
    base = da.province_base()
    _, _, dd = st.h2_design(base)
    import numpy as np
    import statsmodels.api as sm
    dd = dd.assign(sq=dd["log_grdp"] ** 2)
    m = sm.OLS(dd["log_density"], sm.add_constant(dd[["log_grdp", "sq", "urban_share_model"]])).fit()
    nl = st.h2_nonlinear(base)
    xy = XyChartData()
    s1 = xy.add_series("Province")
    for gx, dy in zip(dd["grdp_pc_mvnd"], dd["vehicles_per_1000"]):
        s1.add_data_point(round(float(gx), 1), round(float(dy), 0))
    s2 = xy.add_series("Fitted curve (average urban share)")
    for g in np.linspace(dd["log_grdp"].min(), dd["log_grdp"].max(), 40):
        y = m.params["const"] + m.params["log_grdp"] * g + m.params["sq"] * g * g + m.params["urban_share_model"] * dd["urban_share_model"].mean()
        s2.add_data_point(round(float(np.exp(g)), 1), round(float(np.exp(y)), 0))
    gf = s.shapes.add_chart(XL_CHART_TYPE.XY_SCATTER, MARGIN, Inches(1.75), Inches(7.6), Inches(5.0), xy)
    ch = gf.chart
    style_chart(ch)
    quiet_axes(ch)
    ch.category_axis.has_title = True
    ch.category_axis.axis_title.text_frame.text = "GRDP per capita 2025, million VND"
    ch.value_axis.has_title = True
    ch.value_axis.axis_title.text_frame.text = "vehicles per 1,000 people"
    for ax in (ch.category_axis, ch.value_axis):
        ax.axis_title.text_frame.paragraphs[0].runs[0].font.size = Pt(11)
    ch.value_axis.minimum_scale = 400
    ch.category_axis.minimum_scale = 40
    ch.category_axis.maximum_scale = 280
    sp, sl = ch.plots[0].series[0], ch.plots[0].series[1]
    sp.format.line.fill.background()
    sp.marker.style = XL_MARKER_STYLE.CIRCLE
    sp.marker.size = 9
    sp.marker.format.fill.solid(); sp.marker.format.fill.fore_color.rgb = SEG["MCO"]
    sp.marker.format.line.color.rgb = WHITE
    sl.marker.style = XL_MARKER_STYLE.NONE
    sl.format.line.color.rgb = NAVY
    sl.format.line.width = Pt(2.5)
    sl.smooth = True
    eff = {e["percentile"]: e for e in nl["elasticity_at"]}
    stat(s, Inches(8.55), Inches(1.85), Inches(4.2), f"{eff[10]['elasticity']:+.2f}",
         f"income effect in poorer provinces\n(~{eff[10]['grdp_pc_mvnd']:.0f} M VND): more motorbikes",
         color=SEG["MCO"], vsize=36, h=Inches(1.5))
    stat(s, Inches(8.55), Inches(3.5), Inches(4.2), f"{eff[90]['elasticity']:+.2f}",
         f"income effect in richest provinces\n(~{eff[90]['grdp_pc_mvnd']:.0f} M VND): cars replace bikes",
         color=SEG["PCMO"], vsize=36, h=Inches(1.5))
    box(s, Inches(8.55), Inches(5.15), Inches(4.2), Inches(1.5), fill=WHITE, line=RGBColor(0xE1, 0xE0, 0xD9))
    text(s, Inches(8.75), Inches(5.25), Inches(3.85), Inches(1.35),
         [[("So what: ", {"bold": True, "color": NAVY}), ("push PCMO and premium grades in the 14 provinces above the "
           "turning point; defend MCO through repair shops below it.", {})]], size=14)
    footer(s, n)
    notes(s, "The most useful insight from the exploratory analysis. Our pre-registered linear test said income does "
             "not explain vehicle density. But the assumption checks showed a straight line was the wrong shape. With "
             f"a curve the picture is clear: in poorer provinces, more income means more vehicles, mostly motorbikes "
             f"({eff[10]['elasticity']:+.2f}). Past about 97 million dong per head, density falls "
             f"({eff[90]['elasticity']:+.2f}) as households trade motorbikes for cars. It is exploratory, so we re-test "
             "it on next year's data, but it already tells marketing where to lead with car oil and where with "
             "motorbike oil. Regional differences (H1) are confirmed; there is no general catch-up effect (H3).")

    # 8 ---------------------------------------------------------------- model vs rule of thumb
    s = new()
    title(s, f"The population rule misplaces {pct(t['misallocated_share'])} of demand",
          "Model vs national total split by population, 2025: largest differences by province")
    bc = T["bcmp"].sort_values("diff_vs_population_share_pct")
    pick = list(bc.head(5)["province_en"]) + list(bc.tail(5)["province_en"])
    vals = list(bc.head(5)["diff_vs_population_share_pct"]) + list(bc.tail(5)["diff_vs_population_share_pct"])
    cd = CategoryChartData()
    cd.categories = pick
    cd.add_series("Model vs population split (%)", [round(v, 0) for v in vals])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, MARGIN, Inches(1.75), Inches(7.4), Inches(5.0), cd)
    ch = gf.chart
    style_chart(ch, legend=False)
    quiet_axes(ch)
    ch.value_axis.tick_labels.number_format = '0"%"'
    ch.value_axis.tick_labels.number_format_is_linked = False
    pl = ch.plots[0]
    pl.gap_width = 40
    pl.has_data_labels = True
    pl.data_labels.number_format = '+0"%";-0"%"'
    pl.data_labels.number_format_is_linked = False
    pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    pl.data_labels.font.size = Pt(12)
    pl.series[0].invert_if_negative = False   # otherwise PowerPoint draws negative bars hollow/white
    for i, v in enumerate(vals):
        pt = pl.series[0].points[i]
        pt.format.fill.solid(); pt.format.fill.fore_color.rgb = SEG["MCO"] if v > 0 else SEG["PCMO"]
    no_invert(pl.series[0])
    ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW  # labels left of bars, also for negatives
    stat(s, Inches(8.55), Inches(1.85), Inches(4.2), f"{ml(t['misallocated_litres'])} M L",
         f"mis-allocated by the population rule\n({pct(t['misallocated_share'])} of volume, ~USD {t['misallocated_usd_m']:,.0f} M)",
         color=NAVY, vsize=36, h=Inches(1.5))
    box(s, Inches(8.55), Inches(3.55), Inches(4.2), Inches(3.1), fill=WHITE, line=RGBColor(0xE1, 0xE0, 0xD9))
    bullets(s, Inches(8.75), Inches(3.7), Inches(3.9), Inches(2.9),
            [[("Under-estimated (blue): ", {"bold": True, "color": SEG["MCO"]}), ("industrial and port provinces, metros", {})],
             [("Over-estimated (orange): ", {"bold": True, "color": SEG["PCMO"]}), ("mountain provinces with few vehicles per head", {})],
             "Top-10 changes: Lam Dong and Tay Ninh in; Bac Ninh and Thanh Hoa out (by 2025 volume)"], size=14)
    footer(s, n)
    notes(s, "Why not keep the simple method? Because it puts about one litre in eight in the wrong place. It "
             "over-weights mountainous provinces like Son La and Lai Chau, which have many people but few vehicles, "
             "and under-weights Quang Ninh, Hai Phong and Ho Chi Minh City, where vehicles and freight concentrate. "
             f"The model also beats its own deterministic version: the single best-guess run gives "
             f"{bm['national_deterministic_ML']:.0f} M L but hides a range of {ml(t['lo25'], 0)} to {ml(t['hi25'], 0)}.")

    # 9 ---------------------------------------------------------------- demo
    s = new()
    title(s, "Live demo: the sales dashboard", "Streamlit app on the same data; one button re-checks the statistics office")
    shot = FIG / "dashboard_screenshot.png"
    if shot.exists():
        pic = s.shapes.add_picture(str(shot), MARGIN, Inches(1.7), height=Inches(5.15))
        pic.name = "Dashboard screenshot"
        ln = pic.line
        ln.color.rgb = RGBColor(0xE1, 0xE0, 0xD9); ln.width = Pt(1)
        x1 = MARGIN + pic.width + Inches(0.4)
    else:
        x1 = Inches(7.5)
    feats = [("Province ranking", "stacked by segment, hover for the 95% range"),
             ("Drill-down", "forecast bands, fleet, freight, segment mix"),
             ("Priority matrix", "size vs growth, P(top 10) bars"),
             ("What-if sliders", "change oil-change interval, km, fill; demand updates live"),
             ("Evidence tab", "tests, assumption checks, baselines, data quality")]
    text(s, x1, Inches(1.8), SW - x1 - MARGIN, Inches(0.4), "Five views for five questions", size=18, bold=True,
         font=HEAD, color=NAVY)
    y = Inches(2.35)
    for h_, d in feats:
        text(s, x1, y, SW - x1 - MARGIN, Inches(0.85), [[(h_, {"bold": True, "color": NAVY})], d], size=14, spacing=2)
        y += Inches(0.86)
    footer(s, n)
    notes(s, "Demo (2 minutes): open the dashboard with: .venv\\Scripts\\streamlit.exe run dashboard\\app.py. "
             "1) Filter Region = Southeast to show the ranking change. 2) Drill into Hai Phong: heavy-duty oil drives "
             "the growth band. 3) Priority matrix: hover Thanh Hoa to show P(top 10) of 37%. 4) What-if: move the "
             "motorbike oil-change interval from 2,500 to 4,000 km and watch national demand fall: this is the "
             "biggest uncertainty. 5) Evidence tab: the assumption checks and baselines. If the live demo fails, use "
             "this screenshot.")

    # 10 ---------------------------------------------------------------- lessons & trade-offs
    s = new()
    title(s, "Lessons & trade-offs: where the hard work was",
          "Real government data is messy; every hurdle became a design decision")
    rows = [("Hurdle", "Choice made", "Trade-off accepted"),
            ("No car/motorbike split by province", "Allocate cars by income, trucks by freight; conserve the official total",
             "Structural assumption, priced into the 95% range"),
            ("PX export corrupts Vietnamese; API returns 404s", "Script the web form, download UTF-8 JSON-stat",
             "Depends on the NSO page layout; tests catch breakage"),
            ("63 -> 34 provinces in July 2025", "Official merger map, validated against NSO's own totals",
             "History usable only from 2008 (stable boundaries)"),
            ("ETS forecast lost to a naive drift on freight", "Choose the method by hold-out back-test",
             "Simpler model; HDMO growth is conservative (-12% bias)"),
            ("Linear income test failed RESET", "Report the pre-registered result + exploratory curve",
             "Inverted U labelled a hypothesis, re-test in 2026"),
            ("Flaky DNS and TLS on the government site", "Retries + OS trust store; rebuild only on change",
             "Weekly, not real-time, freshness")]
    tbl = s.shapes.add_table(len(rows), 3, MARGIN, Inches(1.75), SW - 2 * MARGIN, Inches(4.9)).table
    for j, wdt in enumerate([Inches(3.6), Inches(4.9), Inches(3.63)]):
        tbl.columns[j].width = wdt
    for i, row in enumerate(rows):
        for j, v in enumerate(row):
            cell = tbl.cell(i, j)
            cell.text = v
            r = cell.text_frame.paragraphs[0].runs[0]
            r.font.size, r.font.name = Pt(14), BODY
            r.font.bold = i == 0 or j == 0
            r.font.color.rgb = WHITE if i == 0 else (NAVY if j == 0 else INK)
            cell.fill.solid()
            cell.fill.fore_color.rgb = NAVY if i == 0 else (CARD if i % 2 == 0 else WHITE)
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    footer(s, n)
    notes(s, "This is where most of the effort went. The biggest hurdle: the government publishes cars and motorbikes "
             "as one number per province, so the split had to be modelled, conserving the official total and carrying "
             "its uncertainty. A sophisticated forecasting model lost to a simple trend on freight, so we let the "
             "back-test pick the method instead of our preference. When a statistical assumption check failed, we kept "
             "the pre-registered result and labelled the new finding exploratory rather than over-claiming.")

    # 11 ---------------------------------------------------------------- impact & next steps (dark)
    s = new(dark=True)
    title(s, "Impact and next steps", "If the sales organisation adopts the monitor", dark=True)
    cw = (SW - 2 * MARGIN - Inches(0.9)) / 4
    impacts = [(f"{ml(t['misallocated_litres'], 0)} M L", f"~USD {t['misallocated_usd_m']:,.0f} M of demand\nre-allocated to the right provinces"),
               (f"+{ml(t['increment'], 0)} M L", f"growth to 2028; {pct(t['tierA_incr_share'])} of it\nin 10 tier-A provinces"),
               (f"~{t['hours_saved_year']} h", "analyst time saved a year;\nrefresh in ~30 seconds"),
               ("95%", "range on every number:\ntargets with known risk")]
    for i, (v, lbl) in enumerate(impacts):
        stat(s, MARGIN + i * (cw + Inches(0.3)), Inches(1.85), cw, v, lbl, color=WHITE, bg=RGBColor(0x2B, 0x36, 0x7A),
             h=Inches(1.75), lcolor=ICE)
    steps = [("0-3 months", "Re-cut 2026 targets on model medians and ranges; HDMO fleet programme in Hai Phong, "
                            "Nghe An, Ninh Binh, Dong Nai"),
             ("3-6 months", "PCMO and premium push in HCMC, Ha Noi, Quang Ninh; workshop survey of motorbike "
                            "oil-change intervals"),
             ("6-12 months", "Join company sales to measure share and white space; re-test the income curve on 2026 data")]
    y = Inches(4.0)
    for h_, d in steps:
        text(s, MARGIN, y, Inches(2.2), Inches(0.8), h_, size=17, bold=True, color=ICE)
        text(s, MARGIN + Inches(2.3), y, Inches(9.8), Inches(0.8), d, size=16, color=WHITE)
        y += Inches(0.82)
    footer(s, n, dark=True)
    notes(s, "Close with the ask. Adopt the monitor for the 2026 planning cycle. Immediate value: about "
             f"{ml(t['misallocated_litres'], 0)} million litres of demand moved to where the vehicles are, and a growth "
             "plan focused on ten provinces. The one investment requested is a small workshop survey, because the "
             "motorbike oil-change interval is the largest single source of uncertainty. Then connect our own sales "
             "data to turn potential into share and white space. Thank you; questions.")

    # A1 ---------------------------------------------------------------- appendix (hidden): statistics
    s = new()
    title(s, "Appendix A: hypothesis tests and assumption checks", "Hidden back-up slide for Q&A")
    tests = T["tests"]
    rows = [("Test", "Method", "p (Holm)", "Result")] + [
        (r["test"], r["method"], f"{r['p_holm']:.3f}", "reject H0" if r["reject_h0"] else "not rejected") for _, r in tests.iterrows()]
    tb1 = s.shapes.add_table(len(rows), 4, MARGIN, Inches(1.7), SW - 2 * MARGIN, Inches(1.5)).table
    for j, wdt in enumerate([Inches(4.6), Inches(4.0), Inches(1.5), Inches(2.03)]):
        tb1.columns[j].width = wdt
    chk = T["checks"]
    rows2 = [("Model", "Assumption", "Check", "Result")] + [
        (r["model"], r["assumption"], r["check"], "pass" if r["passed"] else "FAIL - handled") for _, r in chk.iterrows()]
    tb2 = s.shapes.add_table(len(rows2), 4, MARGIN, Inches(3.45), SW - 2 * MARGIN, Inches(3.3)).table
    for j, wdt in enumerate([Inches(2.4), Inches(4.4), Inches(3.4), Inches(1.93)]):
        tb2.columns[j].width = wdt
    for tb, rws in ((tb1, rows), (tb2, rows2)):
        for i, row in enumerate(rws):
            for j, v in enumerate(row):
                c = tb.cell(i, j)
                c.text = str(v)
                r = c.text_frame.paragraphs[0].runs[0]
                r.font.size, r.font.name, r.font.bold = Pt(11), BODY, i == 0
                r.font.color.rgb = WHITE if i == 0 else (SEG["PCMO"] if "FAIL" in str(v) else INK)
                c.fill.solid(); c.fill.fore_color.rgb = NAVY if i == 0 else (CARD if i % 2 == 0 else WHITE)
                c.margin_top = c.margin_bottom = Inches(0.02)
    footer(s, n)
    hide(s)
    notes(s, "Back-up. Failed checks and remedies: RESET -> quadratic specification; Durbin-Watson (spatial "
             "correlation) -> region fixed effects and clustered errors; Cook's distance -> refit without 4 influential "
             "provinces. None changes the conclusions.")

    # A2 ---------------------------------------------------------------- appendix (hidden): uncertainty
    s = new()
    title(s, "Appendix B: back-test and uncertainty drivers", "Hidden back-up slide for Q&A")
    bt = T["bt"]
    cd = CategoryChartData()
    cd.categories = ["Population", "Road freight"]
    for mth, lbl in [("ets_damped", "ETS damped"), ("drift", "Drift (chosen)"), ("naive", "Naive")]:
        cd.add_series(lbl, [round(float(bt.set_index("variable").loc[v, f"median_province_mape_{mth}"]), 1)
                            for v in ["population_k", "road_freight_kt"]])
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, MARGIN, Inches(1.75), Inches(5.9), Inches(4.9), cd)
    ch = gf.chart
    style_chart(ch)
    quiet_axes(ch)
    ch.has_title = True
    ch.chart_title.text_frame.text = "Median province MAPE, 2023-2025 hold-out (%)"
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(13)
    pl = ch.plots[0]
    pl.has_data_labels = True
    pl.data_labels.number_format = '0.0'
    pl.data_labels.number_format_is_linked = False
    pl.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END
    for i, c in enumerate([RGBColor(0xC3, 0xC2, 0xB7), SEG["MCO"], RGBColor(0x9A, 0x98, 0x90)]):
        pl.series[i].format.fill.solid(); pl.series[i].format.fill.fore_color.rgb = c
    sens = T["sens"].head(8).iloc[::-1]
    cd = CategoryChartData()
    cd.categories = list(sens["parameter"])
    cd.add_series("Rank correlation with national 2025 demand", [round(v, 2) for v in sens["spearman_with_total_2025"]])
    gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(6.9), Inches(1.75), Inches(5.85), Inches(4.9), cd)
    ch = gf.chart
    style_chart(ch, legend=False)
    quiet_axes(ch)
    ch.has_title = True
    ch.chart_title.text_frame.text = "What drives the uncertainty (rank correlation)"
    ch.chart_title.text_frame.paragraphs[0].runs[0].font.size = Pt(13)
    ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
    pl = ch.plots[0]
    pl.gap_width = 40
    pl.series[0].invert_if_negative = False
    for i, v in enumerate(sens["spearman_with_total_2025"]):
        pt = pl.series[0].points[i]
        pt.format.fill.solid(); pt.format.fill.fore_color.rgb = SEG["MCO"] if v > 0 else SEG["PCMO"]
    no_invert(pl.series[0])
    footer(s, n)
    hide(s)
    notes(s, "Back-up. Drift beat damped ETS on freight (13.3% vs 20.9% median province MAPE); national MAPE 6.9%. "
             "The motorbike oil-change interval is the dominant uncertainty, hence the survey recommendation.")

    prs.core_properties.title = "Vietnam Lubricant Demand Potential Monitor - Executive presentation"
    prs.core_properties.author = AUTHOR
    out = OUT / "executive_presentation.pptx"
    prs.save(out)
    return out


if __name__ == "__main__":
    print("wrote", build())
