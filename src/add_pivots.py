"""Adds real Excel PivotTables to the KPI workbook (built through LibreOffice's DataPilot API, saved as .xlsx).
Usage: python src/add_pivots.py  (needs LibreOffice; run after build_workbook.py)"""
import subprocess, time, os, uno
from pathlib import Path
from com.sun.star.beans import PropertyValue
from com.sun.star.table import CellAddress, CellRangeAddress
from com.sun.star.sheet.DataPilotFieldOrientation import ROW, COLUMN, DATA, PAGE
from com.sun.star.sheet.GeneralFunction import SUM, AVERAGE, COUNT

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "reports" / "Support_Operations_KPI_Workbook.xlsx"
proc = subprocess.Popen(["soffice", "--headless", "--invisible", "--norestore", "--accept=socket,host=localhost,port=2003;urp;"])
for _ in range(60):
    try:
        local = uno.getComponentContext()
        ctx = local.ServiceManager.createInstanceWithContext("com.sun.star.bridge.UnoUrlResolver", local).resolve(
            "uno:socket,host=localhost,port=2003;urp;StarOffice.ComponentContext"); break
    except Exception: time.sleep(0.5)
desktop = ctx.ServiceManager.createInstanceWithContext("com.sun.star.frame.Desktop", ctx)
def P(n, v): p = PropertyValue(); p.Name, p.Value = n, v; return p
doc = desktop.loadComponentFromURL(uno.systemPathToFileUrl(str(SRC)), "_blank", 0, (P("Hidden", True),))
sheets = doc.Sheets; data = sheets.getByName("Data"); di = [sheets.ElementNames.index("Data")][0]
cols = [data.getCellByPosition(c, 0).String for c in range(20)]
src = CellRangeAddress(); src.Sheet, src.StartColumn, src.StartRow, src.EndColumn, src.EndRow = di, 0, 0, 19, 48000

def pivot(sheet_name, name, rows, colf, datas, page=None):
    if not sheets.hasByName(sheet_name): sheets.insertNewByName(sheet_name, sheets.Count)
    sh = sheets.getByName(sheet_name); tables = sh.DataPilotTables
    d = tables.createDataPilotDescriptor(); d.SourceRange = src
    f = d.DataPilotFields
    for r in rows: f.getByIndex(cols.index(r)).Orientation = ROW
    if colf: f.getByIndex(cols.index(colf)).Orientation = COLUMN
    if page: f.getByIndex(cols.index(page)).Orientation = PAGE
    for fld, fn in datas:
        x = f.getByIndex(cols.index(fld)); x.Orientation = DATA; x.Function = fn
    d.setPropertyValue("ShowFilterButton", True)
    dest = CellAddress(); dest.Sheet, dest.Column, dest.Row = sheets.ElementNames.index(sheet_name), 0, 3
    tables.insertNewByName(name, dest, d)
    sh.getCellByPosition(0, 0).String = {"Pivot_Category_Channel": "PivotTable: ticket count by category and channel (filter by region)",
                                         "Pivot_Region_Month": "PivotTable: reopened tickets by region and month",
                                         "Pivot_Priority_SLA": "PivotTable: SLA met / tickets by priority (SLA % = SLA met ÷ tickets)"}[sheet_name]

pivot("Pivot_Category_Channel", "pvCatChannel", ["category"], "channel", [("ticket_id", COUNT)], page="region")
pivot("Pivot_Region_Month", "pvRegionMonth", ["region"], "month", [("reopened", SUM)])
pivot("Pivot_Priority_SLA", "pvPrioritySLA", ["priority"], None, [("sla_met", SUM), ("ticket_id", COUNT), ("handle_time_min", AVERAGE)])
doc.calculateAll()
doc.storeToURL(uno.systemPathToFileUrl(str(SRC)), (P("FilterName", "Calc MS Excel 2007 XML"),))
doc.close(True)
try: desktop.terminate()
except Exception: pass
proc.wait(timeout=60); print("pivots added ->", SRC)
