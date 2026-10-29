"""Stakeholder Excel workbook: data table + formula-driven KPI dashboard + editable business-case model."""
import sys; sys.path.insert(0, str(__import__('pathlib').Path(__file__).parent))
import pandas as pd
from pipeline import load_raw, clean, ROOT

df, dq = clean(load_raw())
cols = ["ticket_id", "created_at", "month", "weekday", "hour", "channel", "region", "category", "priority",
        "tier", "handle_time_min", "first_response_min", "resolution_hours", "sla_met",
        "first_contact_resolved", "reopened", "escalated", "csat", "cost_usd", "simple_request"]
d = df[cols].copy()
for c in ["sla_met", "first_contact_resolved", "reopened", "escalated", "simple_request"]:
    d[c] = d[c].astype(int)
d["created_at"] = d.created_at.dt.strftime("%Y-%m-%d %H:%M")

out = ROOT / "reports" / "Support_Operations_KPI_Workbook.xlsx"
with pd.ExcelWriter(out, engine="xlsxwriter") as xw:
    wb = xw.book
    H = wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "border": 1, "text_wrap": True, "valign": "vcenter"})
    T = wb.add_format({"bold": True, "font_size": 14})
    pct = wb.add_format({"num_format": "0.0%", "border": 1}); num = wb.add_format({"num_format": "#,##0", "border": 1})
    dec = wb.add_format({"num_format": "0.00", "border": 1}); usd = wb.add_format({"num_format": "$#,##0", "border": 1})
    inp = wb.add_format({"bg_color": "#FFF2CC", "border": 1}); inp_pct = wb.add_format({"bg_color": "#FFF2CC", "border": 1, "num_format": "0%"})
    txt = wb.add_format({"border": 1}); note = wb.add_format({"italic": True, "font_color": "#595959"})

    # ---- Data sheet as an Excel Table (filterable, PivotTable-ready) ----
    d.to_excel(xw, sheet_name="Data", index=False, startrow=0)
    ws = xw.sheets["Data"]
    n = len(d)
    ws.add_table(0, 0, n, len(cols) - 1, {"name": "Tickets", "style": "Table Style Medium 2",
                                         "columns": [{"header": c} for c in cols]})
    ws.freeze_panes(1, 0); ws.set_column(0, len(cols) - 1, 14)

    # ---- KPI dashboard driven entirely by formulas on the Tickets table ----
    k = wb.add_worksheet("KPI_Dashboard"); wb.worksheets_objs.insert(0, wb.worksheets_objs.pop())
    k.write("A1", "Support Operations KPI Dashboard — simulated data, Oct 2025–Sep 2026", T)
    k.write("A2", "All figures are live formulas on the Tickets table (COUNTIFS / AVERAGEIFS / SUMIFS).", note)
    heads = ["KPI", "Value"]; k.write_row("A4", heads, H)
    kp = [("Tickets", "=ROWS(Tickets[ticket_id])", num),
          ("SLA attainment", "=AVERAGE(Tickets[sla_met])", pct),
          ("First-contact resolution", "=AVERAGE(Tickets[first_contact_resolved])", pct),
          ("Reopen rate", "=AVERAGE(Tickets[reopened])", pct),
          ("Escalation rate", "=AVERAGE(Tickets[escalated])", pct),
          ("Avg first response (min)", "=AVERAGE(Tickets[first_response_min])", dec),
          ("Avg handle time (min)", "=AVERAGE(Tickets[handle_time_min])", dec),
          ("Avg CSAT (1-5)", "=AVERAGE(Tickets[csat])", dec),
          ("Cost per ticket", "=AVERAGE(Tickets[cost_usd])", usd),
          ("Total agent hours", "=SUM(Tickets[handle_time_min])/60", num)]
    for i, (name, f, fmt) in enumerate(kp, start=5):
        k.write(f"A{i}", name, txt); k.write_formula(f"B{i}", f, fmt)

    months = sorted(d.month.unique())
    k.write_row("D4", ["Month", "Tickets", "SLA %", "FCR %", "Reopen %", "CSAT"], H)
    for i, m in enumerate(months, start=5):
        k.write(f"D{i}", m, txt)
        k.write_formula(f"E{i}", f'=COUNTIFS(Tickets[month],D{i})', num)
        k.write_formula(f"F{i}", f'=AVERAGEIFS(Tickets[sla_met],Tickets[month],D{i})', pct)
        k.write_formula(f"G{i}", f'=AVERAGEIFS(Tickets[first_contact_resolved],Tickets[month],D{i})', pct)
        k.write_formula(f"H{i}", f'=AVERAGEIFS(Tickets[reopened],Tickets[month],D{i})', pct)
        k.write_formula(f"I{i}", f'=AVERAGEIFS(Tickets[csat],Tickets[month],D{i})', dec)
    last = 4 + len(months)

    cats = sorted(d.category.unique())
    r0 = last + 3
    k.write_row(f"D{r0}", ["Category", "Phone hrs", "Email hrs", "Portal hrs", "Total hrs", "FCR %"], H)
    for j, c in enumerate(cats, start=r0 + 1):
        k.write(f"D{j}", c, txt)
        for col, ch in zip("EFG", ["Phone", "Email", "Portal"]):
            k.write_formula(f"{col}{j}", f'=SUMIFS(Tickets[handle_time_min],Tickets[category],$D{j},Tickets[channel],"{ch}")/60', num)
        k.write_formula(f"H{j}", f"=SUM(E{j}:G{j})", num)
        k.write_formula(f"I{j}", f'=AVERAGEIFS(Tickets[first_contact_resolved],Tickets[category],$D{j})', pct)
    k.set_column("A:A", 26); k.set_column("B:B", 12); k.set_column("D:D", 28); k.set_column("E:I", 11)

    ch = wb.add_chart({"type": "line"})
    ch.add_series({"name": "SLA %", "categories": ["KPI_Dashboard", 4, 3, last - 1, 3], "values": ["KPI_Dashboard", 4, 5, last - 1, 5], "marker": {"type": "circle"}})
    ch.add_series({"name": "FCR %", "categories": ["KPI_Dashboard", 4, 3, last - 1, 3], "values": ["KPI_Dashboard", 4, 6, last - 1, 6], "marker": {"type": "circle"}})
    ch.set_title({"name": "Service levels by month"}); ch.set_y_axis({"num_format": "0%"}); ch.set_size({"width": 620, "height": 300})
    k.insert_chart("K4", ch)
    bc = wb.add_chart({"type": "bar", "subtype": "stacked"})
    for col_i, nm in zip([4, 5, 6], ["Phone", "Email", "Portal"]):
        bc.add_series({"name": nm, "categories": ["KPI_Dashboard", r0, 3, r0 + len(cats) - 1, 3], "values": ["KPI_Dashboard", r0, col_i, r0 + len(cats) - 1, col_i]})
    bc.set_title({"name": "Agent hours by category and channel"}); bc.set_size({"width": 620, "height": 320})
    k.insert_chart("K21", bc)

    # ---- Business case with editable assumptions ----
    b = wb.add_worksheet("Business_Case")
    b.write("A1", "Business case — change the yellow assumption cells and every figure recalculates", T)
    b.write_row("A3", ["Assumption", "Value"], H)
    b.write("A4", "Loaded agent cost per minute", txt); b.write("B4", 0.85, inp)
    b.write("A5", "Portal adoption for simple requests", txt); b.write("B5", 0.60, inp_pct)
    b.write("A6", "Productive hours per FTE per year", txt); b.write("B6", 1880, inp)
    b.write_row("A8", ["R1 — Self-service portal for supplies & meter reads", "Value"], H)
    b.write("A9", "Simple requests handled live (phone/email)", txt)
    b.write_formula("B9", '=COUNTIFS(Tickets[simple_request],1,Tickets[channel],"Phone")+COUNTIFS(Tickets[simple_request],1,Tickets[channel],"Email")', num)
    b.write("A10", "Their agent hours", txt)
    b.write_formula("B10", '=(SUMIFS(Tickets[handle_time_min],Tickets[simple_request],1,Tickets[channel],"Phone")+SUMIFS(Tickets[handle_time_min],Tickets[simple_request],1,Tickets[channel],"Email"))/60', num)
    b.write("A11", "Avg portal minutes for the same requests", txt)
    b.write_formula("B11", '=AVERAGEIFS(Tickets[handle_time_min],Tickets[simple_request],1,Tickets[channel],"Portal")', dec)
    b.write("A12", "Agent hours saved per year", txt); b.write_formula("B12", "=B5*(B10-B9*B11/60)", num)
    b.write("A13", "FTE freed", txt); b.write_formula("B13", "=B12/B6", dec)
    b.write("A14", "Annual value", txt); b.write_formula("B14", "=B12*60*B4", usd)
    b.write("A16", "R2–R4 are documented in the notebook (shift realignment, firmware release gate, P1 fast-track).", note)
    b.set_column("A:A", 52); b.set_column("B:B", 14)

    # ---- Data quality log ----
    q = wb.add_worksheet("Data_Quality")
    q.write_row("A1", ["Check", "Count"], H)
    for i, (kk, v) in enumerate(dq.items(), start=2):
        q.write(f"A{i}", kk.replace("_", " "), txt); q.write(f"B{i}", v, txt)
    q.set_column("A:A", 32)
print("saved", out)
