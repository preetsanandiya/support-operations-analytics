"""Validation tests: the deliverables must be internally consistent before anyone sees them."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pytest
from pipeline import load_raw, clean, load_sqlite, kpis, run_sql, named_queries, VALID_REGIONS


@pytest.fixture(scope="module")
def data():
    df, dq = clean(load_raw())
    load_sqlite(df)
    return df, dq


def test_no_duplicates_after_cleaning(data):
    df, _ = data
    assert not df.duplicated().any()
    assert df.ticket_id.is_unique


def test_values_are_valid(data):
    df, _ = data
    assert set(df.region) <= VALID_REGIONS
    assert (df.handle_time_min >= 0).all()
    assert (df.resolved_at >= df.created_at).all()
    assert df.csat.dropna().between(1, 5).all()


def test_sla_flag_matches_definition(data):
    df, _ = data
    assert (df.sla_met == (df.resolution_hours <= df.sla_target_hours)).all()


def test_sql_matches_pandas(data):
    df, _ = data
    s = run_sql(named_queries()["kpi_summary"]).iloc[0]
    k = kpis(df)
    assert s.tickets == k["tickets"]
    assert s.sla_attainment == pytest.approx(k["sla_attainment"], abs=1e-4)
    assert s.first_contact_resolution == pytest.approx(k["first_contact_resolution"], abs=1e-4)
    assert s.avg_csat == pytest.approx(k["avg_csat"], abs=0.01)


def test_monthly_totals_reconcile(data):
    df, _ = data
    trend = run_sql(named_queries()["monthly_trend"])
    assert trend.tickets.sum() == len(df)
    assert len(trend) == 12


def test_every_named_query_runs(data):
    for name, q in named_queries().items():
        assert len(run_sql(q)) > 0, name
