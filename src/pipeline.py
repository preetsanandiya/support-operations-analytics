"""Reusable pipeline: load -> validate/clean -> SQLite -> KPIs. Imported by the notebook and tests."""
import sqlite3
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA, DB = ROOT / "data", ROOT / "data" / "support.db"
VALID_REGIONS = {"Los Angeles", "Orange County", "Inland Empire", "San Diego", "Ventura"}


def load_raw() -> pd.DataFrame:
    return pd.read_csv(DATA / "tickets.csv", parse_dates=["created_at", "resolved_at"])


def clean(df: pd.DataFrame):
    """Return (clean_df, data_quality_report). Every fix is logged so it can be audited."""
    report = {"rows_in": len(df)}
    report["duplicate_rows"] = int(df.duplicated().sum())
    df = df.drop_duplicates().copy()

    bad_case = ~df.region.isin(VALID_REGIONS)
    report["region_case_fixes"] = int(bad_case.sum())
    df["region"] = df.region.str.title()

    neg = df.handle_time_min < 0
    report["negative_handle_time_fixed"] = int(neg.sum())
    df.loc[neg, "handle_time_min"] = df.loc[neg, "handle_time_min"].abs()

    report["resolved_before_created"] = int((df.resolved_at < df.created_at).sum())
    report["null_ticket_ids"] = int(df.ticket_id.isna().sum())
    report["csat_response_rate"] = round(float(df.csat.notna().mean()), 3)
    report["rows_out"] = len(df)

    df["month"] = df.created_at.dt.to_period("M").astype(str)
    df["weekday"] = df.created_at.dt.day_name()
    df["hour"] = df.created_at.dt.hour
    df["simple_request"] = df.category.isin(["Toner / Supplies Reorder", "Meter Read / Billing"])
    return df.reset_index(drop=True), report


def load_sqlite(df: pd.DataFrame, db_path: Path = DB) -> Path:
    con = sqlite3.connect(db_path)
    out = df.copy()
    for c in ("created_at", "resolved_at"):
        out[c] = out[c].dt.strftime("%Y-%m-%d %H:%M:%S")
    for c in ("escalated", "first_contact_resolved", "field_dispatch", "reopened", "sla_met", "simple_request"):
        out[c] = out[c].astype(int)
    out.to_sql("tickets", con, if_exists="replace", index=False)
    pd.read_csv(DATA / "agents.csv").to_sql("agents", con, if_exists="replace", index=False)
    pd.read_csv(DATA / "sla_targets.csv").to_sql("sla_targets", con, if_exists="replace", index=False)
    con.execute("CREATE INDEX IF NOT EXISTS ix_month ON tickets(month)")
    con.commit(); con.close()
    return db_path


def kpis(df: pd.DataFrame) -> dict:
    return {
        "tickets": len(df),
        "sla_attainment": df.sla_met.mean(),
        "first_contact_resolution": df.first_contact_resolved.mean(),
        "avg_first_response_min": df.first_response_min.mean(),
        "avg_handle_time_min": df.handle_time_min.mean(),
        "reopen_rate": df.reopened.mean(),
        "escalation_rate": df.escalated.mean(),
        "avg_csat": df.csat.mean(),
        "cost_per_ticket": df.cost_usd.mean(),
        "total_agent_hours": df.handle_time_min.sum() / 60,
    }


def run_sql(query: str, db_path: Path = DB) -> pd.DataFrame:
    with sqlite3.connect(db_path) as con:
        return pd.read_sql_query(query, con)


def named_queries(path: Path = ROOT / "sql" / "kpi_queries.sql") -> dict:
    """Parse '-- name: xyz' blocks from the SQL file."""
    blocks, name, buf = {}, None, []
    for line in path.read_text().splitlines():
        if line.startswith("-- name:"):
            if name: blocks[name] = "\n".join(buf).strip()
            name, buf = line.split(":", 1)[1].strip(), []
        elif name:
            buf.append(line)
    if name: blocks[name] = "\n".join(buf).strip()
    return blocks


if __name__ == "__main__":
    # Raw CSV -> validated/cleaned CSV + SQLite database + data-quality report
    import json
    df, report = clean(load_raw())
    out = Path(__file__).resolve().parents[1] / "data"
    df.to_csv(out / "tickets_clean.csv", index=False)
    load_sqlite(df)
    json.dump(report, open(out / "data_quality_report.json", "w"), indent=1, default=float)
    print(json.dumps(report, indent=1, default=float))
