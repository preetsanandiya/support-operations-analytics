"""
Generates a Power BI Project (PBIP: TMDL semantic model + PBIR report) for the support-operations analysis.
Open SupportOps.pbip in Power BI Desktop, set the DataFolder parameter if needed, and refresh.

Usage: python src/build_powerbi.py [output_dir] [data_folder_on_target_machine]
"""
import json, sys, uuid, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "powerbi" / "SupportOps-PowerBI"
DATA_FOLDER = sys.argv[2] if len(sys.argv) > 2 else r"C:\Users\preet\Documents\SupportOps-PowerBI\data" + "\\"
NS = uuid.UUID("6f1c2b55-3e0a-4c7e-9a51-2b1d6c0f7a10")
tag = lambda *k: str(uuid.uuid5(NS, "|".join(k)))
SM, RP = "SupportOps.SemanticModel", "SupportOps.Report"

if OUT.exists(): shutil.rmtree(OUT)
def w(rel, content):
    p = OUT / rel; p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content if isinstance(content, str) else json.dumps(content, indent=2, ensure_ascii=False), encoding="utf-8")

# ============================ semantic model ============================
w("SupportOps.pbip", {"version": "1.0", "artifacts": [{"report": {"path": RP}}], "settings": {"enableAutoRecovery": True}})
w(".gitignore", "**/.pbi/localSettings.json\n**/.pbi/cache.abf\n")
platform = lambda typ: {"$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
                        "metadata": {"type": typ, "displayName": "SupportOps"}, "config": {"version": "2.0", "logicalId": tag("platform", typ)}}
w(f"{SM}/.platform", platform("SemanticModel"))
w(f"{SM}/definition.pbism", {"version": "4.0", "settings": {}})
w(f"{SM}/definition/database.tmdl", "database\n\tcompatibilityLevel: 1567\n\n")
w(f"{SM}/definition/expressions.tmdl",
  f'expression DataFolder = "{DATA_FOLDER}" meta [IsParameterQuery = true, Type = "Text", IsParameterQueryRequired = true]\n'
  f'\tlineageTag: {tag("DataFolder")}\n\n\tannotation PBI_ResultType = Text\n\n')

TABLES = ["Tickets", "Agents", "dim_date", "Portal Adoption", "DataQuality", "_Measures"]
def q(name): return f"'{name}'" if (" " in name or not name.replace("_", "").isalnum()) else name
w(f"{SM}/definition/model.tmdl", "\n".join([
    "model Model", "\tculture: en-US", "\tdefaultPowerBIDataSourceVersion: powerBI_V3", "\tsourceQueryCulture: en-US",
    "\tdataAccessOptions", "\t\tlegacyRedirects", "\t\treturnErrorValuesAsNull", "",
    "annotation PBI_QueryOrder = " + json.dumps(["DataFolder"] + TABLES), "",
    "annotation __PBI_TimeIntelligenceEnabled = 0", "", "annotation PBIDesktopVersion = 2.130.930.0 (24.06)", "",
    'annotation PBI_ProTooling = ["DevMode"]', ""] + [f"ref table {q(t)}" for t in TABLES] + [""]))

def column(table, name, dtype, fmt=None, summarize="none", sort_by=None, hidden=False, extra=None):
    lines = [f"\tcolumn {q(name)}", f"\t\tdataType: {dtype}"]
    if fmt: lines.append(f"\t\tformatString: {fmt}")
    if hidden: lines.append("\t\tisHidden")
    lines += [f"\t\tlineageTag: {tag(table, name)}", f"\t\tsummarizeBy: {summarize}", f"\t\tsourceColumn: {name}"]
    if sort_by: lines.append(f"\t\tsortByColumn: {q(sort_by)}")
    lines += ["", "\t\tannotation SummarizationSetBy = Automatic", ""]
    if dtype == "dateTime" and extra == "date": lines += ["\t\tannotation UnderlyingDateTimeDataType = Date", ""]
    return "\n".join(lines)

def table(name, cols, m, extra_header=""):
    m_lines = "\n".join("\t\t\t\t" + ln for ln in m.strip("\n").split("\n"))
    return (f"table {q(name)}\n\tlineageTag: {tag(name)}\n{extra_header}\n" + "\n".join(cols) +
            f"\n\tpartition {q(name)} = m\n\t\tmode: import\n\t\tsource =\n{m_lines}\n\n\tannotation PBI_ResultType = Table\n\n")

FLAGS = ["escalated", "first_contact_resolved", "field_dispatch", "reopened", "sla_met", "simple_request"]
tickets_m = f'''
let
    Source = Csv.Document(File.Contents(DataFolder & "tickets_clean.csv"), [Delimiter = ",", Columns = 26, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Dropped = Table.RemoveColumns(Promoted, {{"resolved_at", "month"}}),
    Blanks = Table.TransformColumns(Dropped, {{}}, each if _ = "" then null else _),
    Typed = Table.TransformColumnTypes(Blanks, {{{{"ticket_id", type text}}, {{"created_at", type datetime}}, {{"channel", type text}}, {{"region", type text}}, {{"product_line", type text}}, {{"category", type text}}, {{"priority", type text}}, {{"sla_target_hours", Int64.Type}}, {{"first_response_target_min", Int64.Type}}, {{"first_response_min", type number}}, {{"handle_time_min", type number}}, {{"escalated", type logical}}, {{"tier", type text}}, {{"agent_id", type text}}, {{"first_contact_resolved", type logical}}, {{"field_dispatch", type logical}}, {{"resolution_hours", type number}}, {{"reopened", type logical}}, {{"sla_met", type logical}}, {{"csat", type number}}, {{"cost_usd", type number}}, {{"weekday", type text}}, {{"hour", Int64.Type}}, {{"simple_request", type logical}}}}, "en-US"),
    Flags = Table.TransformColumns(Typed, List.Transform({{{json.dumps(FLAGS)[1:-1]}}}, (c) => {{c, each if _ = true then 1 else 0, Int64.Type}})),
    CreatedDate = Table.AddColumn(Flags, "created_date", each DateTime.Date([created_at]), type date),
    WeekdayNum = Table.AddColumn(CreatedDate, "weekday_num", each Date.DayOfWeek([created_at], Day.Monday) + 1, Int64.Type)
in
    WeekdayNum
'''
tcols = [column("Tickets", "ticket_id", "string"), column("Tickets", "created_at", "dateTime", "yyyy-mm-dd hh:nn"),
         column("Tickets", "channel", "string"), column("Tickets", "region", "string"), column("Tickets", "product_line", "string"),
         column("Tickets", "category", "string"), column("Tickets", "priority", "string"),
         column("Tickets", "sla_target_hours", "int64", "0"), column("Tickets", "first_response_target_min", "int64", "0"),
         column("Tickets", "first_response_min", "double", "#,0.0"), column("Tickets", "handle_time_min", "double", "#,0.0"),
         column("Tickets", "tier", "string"), column("Tickets", "agent_id", "string"),
         column("Tickets", "resolution_hours", "double", "#,0.00"), column("Tickets", "csat", "double", "0.0"),
         column("Tickets", "cost_usd", "double", "$#,0.00"), column("Tickets", "weekday", "string", sort_by="weekday_num"),
         column("Tickets", "hour", "int64", "0"), column("Tickets", "created_date", "dateTime", "yyyy-mm-dd", extra="date", hidden=True),
         column("Tickets", "weekday_num", "int64", "0", hidden=True)] + [column("Tickets", f, "int64", "0", hidden=True) for f in FLAGS]
w(f"{SM}/definition/tables/Tickets.tmdl", table("Tickets", tcols, tickets_m))

agents_m = '''
let
    Source = Csv.Document(File.Contents(DataFolder & "agents.csv"), [Delimiter = ",", Columns = 3, Encoding = 65001, QuoteStyle = QuoteStyle.Csv]),
    Promoted = Table.PromoteHeaders(Source, [PromoteAllScalars = true]),
    Typed = Table.TransformColumnTypes(Promoted, {{"agent_id", type text}, {"tier", type text}, {"shift", type text}}, "en-US"),
    Renamed = Table.RenameColumns(Typed, {{"tier", "agent_tier"}})
in
    Renamed
'''
w(f"{SM}/definition/tables/Agents.tmdl", table("Agents", [column("Agents", "agent_id", "string"), column("Agents", "agent_tier", "string"),
                                                          column("Agents", "shift", "string")], agents_m))

date_m = '''
let
    Start = #date(2025, 10, 1),
    End = #date(2026, 9, 30),
    Dates = List.Dates(Start, Duration.Days(End - Start) + 1, #duration(1, 0, 0, 0)),
    Base = Table.FromList(Dates, Splitter.SplitByNothing(), {"Date"}),
    Typed = Table.TransformColumnTypes(Base, {{"Date", type date}}),
    MonthStart = Table.AddColumn(Typed, "Month Start", each Date.StartOfMonth([Date]), type date),
    MonthKey = Table.AddColumn(MonthStart, "Month Key", each Date.Year([Date]) * 100 + Date.Month([Date]), Int64.Type),
    Month = Table.AddColumn(MonthKey, "Month", each Date.ToText([Date], "MMM yyyy", "en-US"), type text)
in
    Month
'''
w(f"{SM}/definition/tables/dim_date.tmdl", table("dim_date", [
    column("dim_date", "Date", "dateTime", "yyyy-mm-dd", extra="date").replace("\t\tdataType: dateTime", "\t\tdataType: dateTime\n\t\tisKey"),
    column("dim_date", "Month Start", "dateTime", "mmm yyyy", extra="date"), column("dim_date", "Month Key", "int64", "0", hidden=True),
    column("dim_date", "Month", "string", sort_by="Month Key")], date_m, "\tdataCategory: Time"))

adopt_m = '''
let
    Source = Table.FromList({0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0}, Splitter.SplitByNothing(), {"Adoption"}),
    Typed = Table.TransformColumnTypes(Source, {{"Adoption", type number}})
in
    Typed
'''
w(f"{SM}/definition/tables/Portal Adoption.tmdl", table("Portal Adoption", [column("Portal Adoption", "Adoption", "double", "0%")], adopt_m))

dq = json.load(open(ROOT / "data" / "data_quality_report.json"))
dq_rows = [(1, "Rows received (raw extract)", dq["rows_in"], "Starting point"),
           (2, "Duplicate tickets", dq["duplicate_rows"], "Removed (same ticket_id)"),
           (3, "Region names with wrong case", dq["region_case_fixes"], "Standardized to title case"),
           (4, "Negative handle times", dq["negative_handle_time_fixed"], "Corrected to absolute value"),
           (5, "Resolved before created", dq["resolved_before_created"], "Checked; none found"),
           (6, "Missing ticket IDs", dq["null_ticket_ids"], "Checked; none found"),
           (7, "Rows after cleaning", dq["rows_out"], "Loaded to the model")]
dq_m = ('let\n    Source = #table(type table [Step = Int64.Type, Check = text, Count = Int64.Type, Action = text], {\n' +
        ",\n".join(f'        {{{a}, "{b}", {c}, "{d}"}}' for a, b, c, d in dq_rows) + "\n    })\nin\n    Source")
w(f"{SM}/definition/tables/DataQuality.tmdl", table("DataQuality", [column("DataQuality", "Step", "int64", "0"), column("DataQuality", "Check", "string"),
                                                                   column("DataQuality", "Count", "int64", "#,0"), column("DataQuality", "Action", "string")], dq_m))

SIMPLE_LIVE = 'Tickets[simple_request] = 1, KEEPFILTERS ( Tickets[channel] IN { "Phone", "Email" } )'
MEASURES = [  # name, expression, format, folder
    ("Ticket Count", "COUNTROWS ( Tickets )", "#,0", "Volume"),
    ("Agent Hours", "DIVIDE ( SUM ( Tickets[handle_time_min] ), 60 )", "#,0", "Volume"),
    ("SLA %", "DIVIDE ( SUM ( Tickets[sla_met] ), [Ticket Count] )", "0.0%", "Service"),
    ("Breach %", "1 - [SLA %]", "0.0%", "Service"),
    ("FCR %", "DIVIDE ( SUM ( Tickets[first_contact_resolved] ), [Ticket Count] )", "0.0%", "Service"),
    ("Reopen %", "DIVIDE ( SUM ( Tickets[reopened] ), [Ticket Count] )", "0.0%", "Quality"),
    ("Escalation %", "DIVIDE ( SUM ( Tickets[escalated] ), [Ticket Count] )", "0.0%", "Service"),
    ("Avg CSAT", "AVERAGE ( Tickets[csat] )", "0.00", "Quality"),
    ("Avg Handle Time (min)", "AVERAGE ( Tickets[handle_time_min] )", "0.0", "Service"),
    ("Avg First Response (min)", "AVERAGE ( Tickets[first_response_min] )", "0.0", "Service"),
    ("Total Cost", "SUM ( Tickets[cost_usd] )", "$#,0", "Cost"),
    ("Cost per Ticket", "DIVIDE ( [Total Cost], [Ticket Count] )", "$#,0.00", "Cost"),
    ("P1 SLA %", 'CALCULATE ( [SLA %], Tickets[priority] = "P1" )', "0.0%", "Service"),
    ("Monday Rush Breach %", 'CALCULATE ( [Breach %], Tickets[weekday] = "Monday", Tickets[hour] >= 8, Tickets[hour] <= 10 )', "0.0%", "Staffing"),
    ("Other Weekday Breach %",
     "CALCULATE (\n\t\t\t\t[Breach %],\n\t\t\t\tFILTER (\n\t\t\t\t\tALL ( Tickets[weekday], Tickets[weekday_num], Tickets[hour] ),\n"
     "\t\t\t\t\tTickets[weekday_num] <= 5 && Tickets[hour] >= 7 && Tickets[hour] <= 18\n"
     "\t\t\t\t\t\t&& NOT ( Tickets[weekday_num] = 1 && Tickets[hour] >= 8 && Tickets[hour] <= 10 )\n\t\t\t\t)\n\t\t\t)", "0.0%", "Staffing"),
    ("Breach Color", 'VAR v = [Breach %] RETURN SWITCH ( TRUE (), ISBLANK ( v ), "#FFFFFF", v >= 0.25, "#1E4470", v >= 0.20, "#3D72AD", v >= 0.15, "#6A95C6", v >= 0.10, "#C9D9EC", v >= 0.05, "#E6EEF7", "#FFFFFF" )', None, "Staffing"),
    ("SLA Color", 'VAR v = [SLA %] RETURN SWITCH ( TRUE (), ISBLANK ( v ), "#C9D9EC", v >= 0.9, "#9DB9DB", v >= 0.8, "#3D72AD", "#0F2238" )', None, "Formatting"),
    ("SLA Tint", 'VAR v = [SLA %] RETURN SWITCH ( TRUE (), ISBLANK ( v ), "#FFFFFF", v >= 0.9, "#FFFFFF", v >= 0.86, "#E6EEF7", "#C9D9EC" )', None, "Formatting"),
    ("Hours Shade", 'VAR r = RANKX ( ALL ( Tickets[category] ), [Agent Hours] ) RETURN SWITCH ( r, 1, "#0F2238", 2, "#16314F", 3, "#1E4470", 4, "#2B5A8F", 5, "#3D72AD", "#5584BC" )', None, "Formatting"),
    ("Breach Font", 'IF ( [Breach %] >= 0.2, "#FFFFFF", "#0F2238" )', None, "Formatting"),
    ("Reopen Font", 'IF ( [Driver Reopen %] >= 0.15, "#FFFFFF", "#0F2238" )', None, "Formatting"),
    ("Reopen Color", 'VAR v = [Driver Reopen %] RETURN SWITCH ( TRUE (), ISBLANK ( v ), "#FFFFFF", v >= 0.3, "#1E4470", v >= 0.15, "#6A95C6", v >= 0.09, "#C9D9EC", "#FFFFFF" )', None, "Formatting"),
    ("P1 SLA Target", "0.8", "0%", "Service"),
    ("Gauge Min", "0", "0%", "Formatting"),
    ("Gauge Max", "1", "0%", "Formatting"),
    ("IE Peak Reopen %", "MAXX ( ALL ( dim_date[Month Start] ), [IE Driver Reopen %] )", "0.0%", "Quality"),
    ("Rows Received", "CALCULATE ( SUM ( DataQuality[Count] ), DataQuality[Step] = 1 )", "#,0", "Data quality"),
    ("Rows Loaded", "CALCULATE ( SUM ( DataQuality[Count] ), DataQuality[Step] = 7 )", "#,0", "Data quality"),
    ("Defects Fixed", "CALCULATE ( SUM ( DataQuality[Count] ), DataQuality[Step] IN { 2, 3, 4 } )", "#,0", "Data quality"),
    ("Adoption Selected", "SELECTEDVALUE ( 'Portal Adoption'[Adoption], 0.6 )", "0%", "Business case"),
    ("Cost per Agent Minute", "0.85", "$0.00", "Business case"),
    ("Simple Live Tickets", f"CALCULATE ( [Ticket Count], {SIMPLE_LIVE} )", "#,0", "Business case"),
    ("Simple Live Hours", f"CALCULATE ( [Agent Hours], {SIMPLE_LIVE} )", "#,0", "Business case"),
    ("Portal Minutes (Simple)", 'CALCULATE ( [Avg Handle Time (min)], Tickets[simple_request] = 1, Tickets[channel] = "Portal" )', "0.0", "Business case"),
    ("Hours Saved", "[Adoption Selected] * ( [Simple Live Hours] - [Simple Live Tickets] * [Portal Minutes (Simple)] / 60 )", "#,0", "Business case"),
    ("Annual Value", "[Hours Saved] * 60 * [Cost per Agent Minute]", "$#,0", "Business case"),
    ("FTE Freed", "DIVIDE ( [Hours Saved], 1880 )", "0.00", "Business case"),
    ("Driver Reopen %", 'CALCULATE ( [Reopen %], Tickets[category] = "Print Driver / Network" )', "0.0%", "Quality"),
    ("IE Driver Reopen %", 'CALCULATE ( [Driver Reopen %], Tickets[region] = "Inland Empire" )', "0.0%", "Quality"),
    ("IE Reopen UCL",
     "VAR Baseline =\n\t\t\t\tADDCOLUMNS (\n\t\t\t\t\tCALCULATETABLE ( VALUES ( dim_date[Month Start] ), ALL ( dim_date ), dim_date[Date] < DATE ( 2026, 3, 1 ) ),\n"
     "\t\t\t\t\t\"@rate\", VAR m = dim_date[Month Start] RETURN CALCULATE ( [IE Driver Reopen %], ALL ( dim_date ), dim_date[Month Start] = m )\n"
     "\t\t\t\t)\n\t\t\tRETURN AVERAGEX ( Baseline, [@rate] ) + 3 * STDEVX.S ( Baseline, [@rate] )", "0.0%", "Quality"),
    ("IE Months Out of Control",
     "COUNTROWS ( FILTER ( VALUES ( dim_date[Month Start] ), [IE Driver Reopen %] > [IE Reopen UCL] ) )", "0", "Quality"),
]
mlines = [f"table _Measures\n\tlineageTag: {tag('_Measures')}\n"]
for name, expr, fmt, folder in MEASURES:
    body = " " + expr if "\n" not in expr else "\n\t\t\t" + expr
    fmt_line = f"\t\tformatString: {fmt}\n" if fmt else ""
    mlines.append(f"\tmeasure {q(name)} ={body}\n{fmt_line}\t\tdisplayFolder: {folder}\n\t\tlineageTag: {tag('m', name)}\n")
mlines.append(f"\tcolumn Dummy\n\t\tdataType: string\n\t\tisHidden\n\t\tlineageTag: {tag('_Measures', 'Dummy')}\n\t\tsummarizeBy: none\n\t\tsourceColumn: Dummy\n\n"
              "\t\tannotation SummarizationSetBy = Automatic\n\n\tpartition _Measures = m\n\t\tmode: import\n\t\tsource =\n"
              "\t\t\t\tlet\n\t\t\t\t    Source = #table(type table [Dummy = text], {})\n\t\t\t\tin\n\t\t\t\t    Source\n\n\tannotation PBI_ResultType = Table\n\n")
w(f"{SM}/definition/tables/_Measures.tmdl", "\n".join(mlines))

w(f"{SM}/definition/relationships.tmdl",
  f"relationship {tag('rel', 'date')}\n\tfromColumn: Tickets.created_date\n\ttoColumn: dim_date.Date\n\n"
  f"relationship {tag('rel', 'agent')}\n\tfromColumn: Tickets.agent_id\n\ttoColumn: Agents.agent_id\n\n")

# ============================ report ============================
w(f"{RP}/.platform", platform("Report"))
w(f"{RP}/definition.pbir", {"version": "4.0", "datasetReference": {"byPath": {"path": f"../{SM}"}, "byConnection": None}})
w(f"{RP}/definition/version.json", {"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json", "version": "2.0.0"})
THEME = "SummitSlate.json"
w(f"{RP}/definition/report.json", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/1.0.0/schema.json",
    "themeCollection": {"baseTheme": {"name": "CY24SU10", "reportVersionAtImport": "5.59", "type": "SharedResources"},
                        "customTheme": {"name": THEME, "reportVersionAtImport": "5.59", "type": "RegisteredResources"}},
    "layoutOptimization": "None",
    "resourcePackages": [{"name": "RegisteredResources", "type": "RegisteredResources",
                          "items": [{"name": THEME, "path": THEME, "type": "CustomTheme"}]}],
    "settings": {"useStylableVisualContainerHeader": True, "defaultDrillFilterOtherVisuals": True}})
# One-hue palette: navy in graduated shades (900 darkest -> 100 lightest)
N9, N8, N7, N6, N5, N4, N3, N2, N1 = "#0F2238", "#16314F", "#1E4470", "#2B5A8F", "#3D72AD", "#6A95C6", "#9DB9DB", "#C9D9EC", "#E6EEF7"
NAVY, INK, PAGE_BG, CARD_LINE = N9, "#0F2238", "#F4F6F9", "#DDE3EA"
WHITE, MUTED = "#FFFFFF", "#5B6B7F"
lit = lambda v: {"expr": {"Literal": {"Value": v}}}
color = lambda c: {"solid": {"color": lit(f"'{c}'")}}
w(f"{RP}/StaticResources/RegisteredResources/{THEME}", {
    "name": "Summit Navy", "dataColors": [N7, N4, N2, N9, N5, N3, N6, N8],
    "background": WHITE, "foreground": INK, "tableAccent": N7, "good": N5, "neutral": N4, "bad": N9,
    "maximum": N7, "center": N3, "minimum": WHITE,
    "textClasses": {"title": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": INK},
                    "callout": {"fontFace": "Segoe UI Semibold", "fontSize": 26, "color": INK},
                    "label": {"fontFace": "Segoe UI", "fontSize": 10, "color": MUTED},
                    "header": {"fontFace": "Segoe UI Semibold", "fontSize": 12, "color": INK}},
    "visualStyles": {"*": {"*": {"background": [{"show": True, "color": {"solid": {"color": WHITE}}, "transparency": 0}],
                                 "border": [{"show": True, "color": {"solid": {"color": CARD_LINE}}, "radius": 10}],
                                 "dropShadow": [{"show": True, "preset": "Custom", "shadowSpread": 1, "shadowBlur": 6,
                                                 "angle": 90, "shadowDistance": 2, "transparency": 88,
                                                 "color": {"solid": {"color": "#0B2239"}}, "position": "Outer"}]}},
                     "page": {"*": {"background": [{"color": {"solid": {"color": PAGE_BG}}, "transparency": 0}],
                                    "outspace": [{"color": {"solid": {"color": PAGE_BG}}}]}}}})

def mref(name): return {"Measure": {"Expression": {"SourceRef": {"Entity": "_Measures"}}, "Property": name}}
def cref(ent, col): return {"Column": {"Expression": {"SourceRef": {"Entity": ent}}, "Property": col}}
def qref(field):
    k = next(iter(field)); return f"{field[k]['Expression']['SourceRef']['Entity']}.{field[k]['Property']}"
def proj(field, display=None, active=False):
    p = {"field": field, "queryRef": qref(field), "nativeQueryRef": field[next(iter(field))]["Property"]}
    if active: p["active"] = True
    if display: p["displayName"] = display
    return p

class Page:
    def __init__(self, key, name):
        self.key, self.name, self.n = key, name, 0
        w(f"{RP}/definition/pages/{key}/page.json", {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/1.0.0/schema.json",
            "name": key, "displayName": name, "displayOption": "FitToPage", "height": 720, "width": 1280})
    def add(self, x, y, wd, ht, visual):
        vid = f"{self.key}{self.n:02d}"
        w(f"{RP}/definition/pages/{self.key}/visuals/{vid}/visual.json", {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/1.0.0/schema.json",
            "name": vid, "position": {"x": x, "y": y, "z": self.n, "width": wd, "height": ht, "tabOrder": self.n}, "visual": visual})
        self.n += 1

def style(v, title=None, bg=None, title_color=INK, border=True, shadow=True):
    vco = v.setdefault("visualContainerObjects", {})
    if title is not None:
        vco["title"] = [{"properties": {"show": lit("true"), "text": lit(f"'{title}'"), "fontColor": color(title_color),
                                        "fontSize": lit("11D"), "bold": lit("true")}}]
    else:
        vco["title"] = [{"properties": {"show": lit("false")}}]
    if bg: vco["background"] = [{"properties": {"show": lit("true"), "color": color(bg), "transparency": lit("0D")}}]
    if not border: vco["border"] = [{"properties": {"show": lit("false")}}]
    if not shadow: vco["dropShadow"] = [{"properties": {"show": lit("false")}}]
    v["drillFilterOtherVisuals"] = True
    return v
def textbox(runs, bg=None, border=True, shadow=True):
    paras = [{"textRuns": [{"value": t, "textStyle": st}]} for t, st in runs]
    return style({"visualType": "textbox", "objects": {"general": [{"properties": {"paragraphs": paras}}]}}, None, bg, border=border, shadow=shadow)
H1 = {"fontWeight": "bold", "fontSize": "18pt", "color": WHITE}
SUBST = {"fontSize": "9pt", "color": "#9DB9DB"}
BODY = {"fontSize": "10.5pt", "color": INK}
def header(pg, title, sub):
    pg.add(0, 0, 1280, 70, textbox([(title, H1), (sub, SUBST)], bg=NAVY, border=False, shadow=False))
    pg.add(860, 18, 405, 36, style({"visualType": "pageNavigator", "objects": {
        "fill": [{"properties": {"fillColor": color(N8), "transparency": lit("0D")}, "selector": {"id": "default"}},
                 {"properties": {"fillColor": color(N5), "transparency": lit("0D")}, "selector": {"id": "selected"}}],
        "text": [{"properties": {"fontColor": color(WHITE), "fontSize": lit("9D")}, "selector": {"id": "default"}}],
        "outline": [{"properties": {"show": lit("false")}, "selector": {"id": "default"}}]}}, None, bg=NAVY, border=False, shadow=False))
def tile(measure, title, bg):
    return style({"visualType": "card", "query": {"queryState": {"Values": {"projections": [proj(mref(measure))]}}},
                  "objects": {"categoryLabels": [{"properties": {"show": lit("false")}}],
                              "labels": [{"properties": {"labelDisplayUnits": lit("1D"), "color": color(WHITE), "fontSize": lit("26D")}}]}},
                 title, bg=bg, title_color=WHITE, border=False)
def slicer(ent, col, title, mode="Dropdown"):
    return style({"visualType": "slicer", "query": {"queryState": {"Values": {"projections": [proj(cref(ent, col), active=True)]}}},
                  "objects": {"data": [{"properties": {"mode": lit(f"'{mode}'")}}], "header": [{"properties": {"show": lit("false")}}]}}, title)
def series_colors(pairs):  # [(field, hex)]
    return [{"properties": {"fill": color(c)}, "selector": {"metadata": qref(f)}} for f, c in pairs]
def measure_fill(name):
    return [{"properties": {"fill": {"solid": {"color": {"expr": mref(name)}}}}, "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}]}}]
def chart(vtype, cat, ys, title, series=None, sort=None, objects=None, cat_role="Category", y_role="Y", labels=False):
    qs = {cat_role: {"projections": [proj(cat[0], cat[1], active=True)]}, y_role: {"projections": [proj(f, d) for f, d in ys]}}
    if series: qs["Series"] = {"projections": [proj(series[0], series[1])]}
    query = {"queryState": qs}
    if sort: query["sortDefinition"] = {"sort": [{"field": sort[0], "direction": sort[1]}]}
    obj = dict(objects or {})
    if labels: obj["labels"] = [{"properties": {"show": lit("true")}}]
    v = {"visualType": vtype, "query": query}
    if obj: v["objects"] = obj
    return style(v, title)
HEADERS = {"columnHeaders": [{"properties": {"backColor": color(NAVY), "fontColor": color(WHITE), "fontSize": lit("10D")}}]}
def table_v(fields, title, sort=None, cell_fill=None):
    query = {"queryState": {"Values": {"projections": [proj(f, d) for f, d in fields]}}}
    if sort: query["sortDefinition"] = {"sort": [{"field": sort[0], "direction": sort[1]}]}
    obj = dict(HEADERS)
    obj["values"] = [{"properties": {"fontSize": lit("10D")}}]
    if cell_fill:
        obj["values"].append({"properties": {"backColor": {"solid": {"color": {"expr": mref(cell_fill[1])}}}},
                              "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": qref(cell_fill[0])}})
    return style({"visualType": "tableEx", "query": query, "objects": obj}, title)
def matrix(rows, cols, val, title, fill=None, font="9D", font_color=None):
    v = {"visualType": "pivotTable", "query": {"queryState": {
        "Rows": {"projections": [proj(rows[0], rows[1], active=True)]},
        "Columns": {"projections": [proj(cols[0], cols[1], active=True)]},
        "Values": {"projections": [proj(val[0], val[1])]}}}, "objects": dict(HEADERS)}
    v["objects"]["columnHeaders"] = [{"properties": {"backColor": color(NAVY), "fontColor": color(WHITE), "fontSize": lit(font)}}]
    v["objects"]["rowHeaders"] = [{"properties": {"backColor": color("#F4F7FB"), "fontColor": color(INK), "fontSize": lit(font)}}]
    v["objects"]["values"] = [{"properties": {"fontSize": lit(font)}}]
    if fill:
        props = {"backColor": {"solid": {"color": {"expr": mref(fill)}}}}
        if font_color: props["fontColor"] = {"solid": {"color": {"expr": mref(font_color)}}}
        v["objects"]["values"].append({"properties": props,
                                       "selector": {"data": [{"dataViewWildcard": {"matchingOption": 1}}], "metadata": qref(val[0])}})
    return style(v, title)
def callout(title, lines, bg):
    return textbox([(title, {"fontWeight": "bold", "fontSize": "13pt", "color": WHITE})] +
                   [(t, {"fontSize": "10.5pt", "color": WHITE}) for t in lines], bg=bg, border=False)
def note(title, lines, bg=WHITE):
    return textbox([(title, {"fontWeight": "bold", "fontSize": "12pt", "color": INK})] + [(t, BODY) for t in lines], bg=bg)

MONTH = (cref("dim_date", "Month Start"), "Month")
SUB = "Summit Office Solutions (fictional) · Oct 2025 – Sep 2026 · simulated data · 48,000 tickets after cleaning"
TOP = 82

# ---- Page 1: Overview ----
p = Page("overview", "Overview")
header(p, "Support Operations Command Center", SUB)
for i, (m, t, c) in enumerate([("Ticket Count", "Tickets", N9), ("SLA %", "SLA attainment", N8), ("FCR %", "First-contact resolution", N7),
                               ("Reopen %", "Reopen rate", N6), ("Avg CSAT", "Avg CSAT (1-5)", N5), ("Cost per Ticket", "Cost per ticket", N4)]):
    p.add(20 + i * 208, TOP, 196, 92, tile(m, t, c))
for i, (col, t) in enumerate([("region", "Region"), ("priority", "Priority"), ("channel", "Channel"), ("product_line", "Product line")]):
    p.add(20 + i * 312, 184, 300, 56, slicer("Tickets", col, t))
p.add(20, 250, 430, 226, chart("lineChart", MONTH, [(mref("SLA %"), "SLA attainment"), (mref("FCR %"), "First-contact resolution")],
                               "SLA and first-contact resolution by month",
                               objects={"dataPoint": series_colors([(mref("SLA %"), N7), (mref("FCR %"), N4)]),
                                        "lineStyles": [{"properties": {"showMarker": lit("true")}}]}))
p.add(460, 250, 430, 226, chart("areaChart", MONTH, [(mref("Ticket Count"), "Tickets")], "Ticket volume by month",
                                objects={"dataPoint": series_colors([(mref("Ticket Count"), N6)]), "valueAxis": [{"properties": {"start": lit("0D")}}]}))
p.add(900, 250, 360, 226, chart("donutChart", (cref("Tickets", "channel"), "Channel"), [(mref("Ticket Count"), "Tickets")],
                                "Channel mix", objects={"labels": [{"properties": {"show": lit("true"), "labelStyle": lit("'Category, percent of total'")}}]}))
p.add(20, 486, 620, 224, chart("barChart", (cref("Tickets", "category"), "Category"), [(mref("Ticket Count"), "Tickets")],
                               "Tickets by category and channel", series=(cref("Tickets", "channel"), "Channel")))
p.add(650, 486, 610, 224, chart("clusteredColumnChart", (cref("Tickets", "priority"), "Priority"), [(mref("SLA %"), "SLA attainment")],
                                "SLA attainment by priority (darker = further below the 90% goal)", sort=(cref("Tickets", "priority"), "Ascending"),
                                objects={"dataPoint": measure_fill("SLA Color")}, labels=True))

# ---- Page 2: Self-service opportunity ----
p = Page("selfservice", "Self-service")
header(p, "Self-Service Opportunity", "Supplies and meter reads still handled by live agents · hours saved = adoption × (live hours − live tickets × portal minutes ÷ 60) · $0.85 per agent minute")
for i, (m, t, c) in enumerate([("Simple Live Tickets", "Simple requests, live", N9), ("Simple Live Hours", "Their agent hours", N8),
                               ("Hours Saved", "Hours saved / yr", N7), ("FTE Freed", "FTE freed", N6), ("Annual Value", "Annual value", N5)]):
    p.add(20 + i * 208, TOP, 196, 92, tile(m, t, c))
p.add(1060, TOP, 200, 92, slicer("Portal Adoption", "Adoption", "Portal adoption (what-if)"))
p.add(20, 186, 400, 300, chart("treemap", (cref("Tickets", "category"), "Category"), [(mref("Agent Hours"), "Agent hours")],
                               "Where agent hours go (darker = more hours)", cat_role="Group", y_role="Values", labels=True,
                               objects={"dataPoint": measure_fill("Hours Shade")}))
p.add(430, 186, 450, 300, chart("barChart", (cref("Tickets", "category"), "Category"), [(mref("Agent Hours"), "Agent hours")],
                                "Agent hours by category and channel", series=(cref("Tickets", "channel"), "Channel")))
p.add(890, 186, 370, 300, table_v([(cref("Tickets", "category"), "Category"), (cref("Tickets", "channel"), "Channel"),
                                   (mref("Simple Live Tickets"), "Tickets"), (mref("Simple Live Hours"), "Agent hours")],
                                  "Deflection scope: simple requests on phone/email"))
p.add(20, 496, 820, 214, note("What this page shows", [
    "Toner and supply reorders and meter reads are simple, repeatable requests, yet most arrive by phone or email and take a live agent's time. "
    "The same requests submitted through the portal take far fewer agent minutes.",
    "Use the adoption slicer to see the impact at 20-100% portal adoption.",
    "Estimates come from simulated data and stated assumptions; they are opportunities, not realized savings."]))
p.add(850, 496, 410, 214, callout("Recommendation", [
    "Launch a self-service portal with automatic supply reordering.",
    "At 60% adoption: about 830 agent hours and $42K a year, roughly 0.4 of a full-time agent freed for harder tickets."], N8))

# ---- Page 3: SLA & staffing ----
p = Page("sla", "SLA & staffing")
header(p, "SLA & Staffing", "Breach % = share of tickets not resolved within the SLA for their priority (P1 4h · P2 8h · P3 24h · P4 72h)")
for i, (m, t, c) in enumerate([("Monday Rush Breach %", "Breach rate, Mon 8-11am", N9), ("Other Weekday Breach %", "Breach rate, other weekday hours", N8),
                               ("SLA %", "Overall SLA attainment", N7), ("P1 SLA %", "P1 (critical) SLA attainment", N6)]):
    p.add(20 + i * 312, TOP, 300, 92, tile(m, t, c))
p.add(20, 186, 1240, 290, matrix((cref("Tickets", "weekday"), "Weekday"), (cref("Tickets", "hour"), "Hour"), (mref("Breach %"), "Breach %"),
                                 "SLA breach heatmap by weekday and hour of creation (darker = more breaches)", fill="Breach Color", font="8D", font_color="Breach Font"))
p.add(20, 486, 500, 224, chart("clusteredColumnChart", (cref("Tickets", "hour"), "Hour"), [(mref("Ticket Count"), "Tickets")],
                               "Ticket arrivals by hour", sort=(cref("Tickets", "hour"), "Ascending"),
                               objects={"dataPoint": [{"properties": {"fill": color(N6)}}]}))
p.add(530, 486, 320, 224, style({"visualType": "gauge", "query": {"queryState": {
    "Y": {"projections": [proj(mref("P1 SLA %"), "P1 SLA")]}, "MinValue": {"projections": [proj(mref("Gauge Min"))]},
    "MaxValue": {"projections": [proj(mref("Gauge Max"))]}, "TargetValue": {"projections": [proj(mref("P1 SLA Target"), "Target")]}}},
    "objects": {"dataPoint": [{"properties": {"fill": color(N6), "target": color(N9)}}]}}, "P1 SLA vs 80% target"))
p.add(860, 486, 400, 224, callout("Recommendation", [
    "Move three late-shift agents to a 7am Monday start: breaches pile up in the Monday 8-11am backlog while late shifts have spare capacity. "
    "Cost-neutral; about 360 fewer breaches a year.",
    "Add a P1 fast-track dispatch path: critical tickets meet SLA only about half the time."], N8))

# ---- Page 4: Quality & agents ----
p = Page("quality", "Quality & agents")
header(p, "Quality & Agents", "Firmware v4.2 (released Mar 9, 2026) · Print Driver / Network tickets · control limit = average + 3 standard deviations of Oct 2025 – Feb 2026")
for i, (m, t, c) in enumerate([("IE Months Out of Control", "Months above control limit (IE)", N9), ("IE Peak Reopen %", "Peak IE reopen rate", N8),
                               ("IE Reopen UCL", "Control limit", N7), ("Reopen %", "Reopen rate, all tickets", N6)]):
    p.add(20 + i * 312, TOP, 300, 92, tile(m, t, c))
p.add(20, 186, 620, 290, chart("lineChart", MONTH, [(mref("IE Driver Reopen %"), "Inland Empire reopen rate"), (mref("IE Reopen UCL"), "Upper control limit")],
                               "Inland Empire driver/network reopen rate vs control limit",
                               objects={"dataPoint": series_colors([(mref("IE Driver Reopen %"), N8), (mref("IE Reopen UCL"), N3)]),
                                        "lineStyles": [{"properties": {"showMarker": lit("true")}}]}))
p.add(650, 186, 610, 290, matrix(MONTH, (cref("Tickets", "region"), "Region"), (mref("Driver Reopen %"), "Reopen %"),
                                 "Driver/network reopen rate by region and month", fill="Reopen Color", font_color="Reopen Font"))
p.add(20, 486, 1240, 224, table_v([(cref("Tickets", "agent_id"), "Agent"), (cref("Agents", "agent_tier"), "Tier"), (cref("Agents", "shift"), "Shift"),
                                   (mref("Ticket Count"), "Tickets"), (mref("FCR %"), "FCR"), (mref("SLA %"), "SLA"),
                                   (mref("Avg Handle Time (min)"), "Avg handle min"), (mref("Avg CSAT"), "CSAT"), (mref("Reopen %"), "Reopen")],
                                  "Agent scorecard (SLA cell shaded darker when below 90%)", sort=(mref("Ticket Count"), "Descending"),
                                  cell_fill=(mref("SLA %"), "SLA Tint")))

# ---- Page 5: Data quality & definitions ----
p = Page("dataquality", "Data quality")
header(p, "Data Quality & Definitions", "Every cleaning step is counted so totals trace from the raw extract to the model")
for i, (m, t, c) in enumerate([("Rows Received", "Rows received (raw)", N9), ("Defects Fixed", "Defects removed or corrected", N7),
                               ("Rows Loaded", "Rows loaded to model", N5)]):
    p.add(20 + i * 416, TOP, 404, 92, tile(m, t, c))
p.add(20, 186, 620, 330, table_v([(cref("DataQuality", "Step"), "#"), (cref("DataQuality", "Check"), "Check"),
                                  (cref("DataQuality", "Count"), "Rows"), (cref("DataQuality", "Action"), "Action")],
                                 "Validation and cleaning log (Python pipeline, mirrored in Power Query)", sort=(cref("DataQuality", "Step"), "Ascending")))
defs = [("SLA attainment", "tickets resolved within the priority's SLA ÷ tickets"), ("First-contact resolution", "tickets solved without a follow-up contact ÷ tickets"),
        ("Reopen rate", "tickets reopened after resolution ÷ tickets"), ("Escalation rate", "tickets escalated to Tier 2 ÷ tickets"),
        ("Avg handle time", "average agent minutes per ticket"), ("Cost per ticket", "loaded agent cost ÷ tickets"),
        ("CSAT", "average 1-5 survey score; about 35% of customers respond")]
p.add(650, 186, 610, 330, note("KPI definitions", [f"{a}: {b}" for a, b in defs]))
p.add(20, 526, 1240, 184, callout("Validated across tools", [
    "KPIs in this report match the Python notebook, the SQL queries and the Excel workbook built from the same cleaned data. "
    "Automated tests in the repository fail if pandas and SQL disagree.",
    "Checked in Power BI: 48,000 tickets · 87.7% SLA · 56.2% FCR · 830 hours saved at 60% adoption · Monday 8-11am breach 20.1% vs 11.6% · P1 SLA 52.5%."], N7))

w(f"{RP}/definition/pages/pages.json", {
    "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json",
    "pageOrder": ["overview", "selfservice", "sla", "quality", "dataquality"], "activePageName": "overview"})
print("PBIP written to", OUT)
