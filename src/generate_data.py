"""
Generate a synthetic (simulated) support-ticket dataset for a fictional office-equipment
dealer, "Summit Office Solutions". No real company data is used.

Built-in, realistic patterns the analysis is meant to *discover*:
  1. Simple supply/meter-read requests flood the phone queue (deflection opportunity).
  2. Monday 8-11am backlog drives SLA breaches.
  3. A March 2026 firmware release spikes reopens for driver/network tickets in one region.
Run:  python src/generate_data.py   ->  data/tickets.csv, data/agents.csv, data/sla_targets.csv
"""
import numpy as np, pandas as pd
from pathlib import Path

rng = np.random.default_rng(2026)
OUT = Path(__file__).resolve().parents[1] / "data"
OUT.mkdir(exist_ok=True)

START, END = pd.Timestamp("2025-10-01"), pd.Timestamp("2026-09-30 23:59")
N = 48_000

categories = {  # share, avg phone handle min, fcr prob, field-dispatch prob
    "Toner / Supplies Reorder":   (0.21, 7.0, 0.95, 0.00),
    "Meter Read / Billing":        (0.13, 8.5, 0.90, 0.00),
    "Paper Jam / Hardware Fault":  (0.25, 14.0, 0.55, 0.35),
    "Print Driver / Network":      (0.18, 19.0, 0.50, 0.05),
    "Scan-to-Email / Software":    (0.12, 16.0, 0.62, 0.02),
    "Service Dispatch Request":    (0.11, 10.0, 0.30, 0.85),
}
regions = ["Los Angeles", "Orange County", "Inland Empire", "San Diego", "Ventura"]
region_p = [0.30, 0.24, 0.18, 0.18, 0.10]
products = ["A3 Color MFP", "A4 Mono MFP", "Production Print", "Managed IT Services"]
product_p = [0.42, 0.33, 0.12, 0.13]
sla = pd.DataFrame({"priority": ["P1", "P2", "P3", "P4"],
                    "sla_target_hours": [4, 8, 24, 72],
                    "first_response_target_min": [15, 30, 60, 240]})

# ---- arrival timestamps: business-hours weighted, Monday-heavy ----
days = pd.date_range(START.normalize(), END.normalize(), freq="D")
day_w = np.array([{0: 1.45, 1: 1.1, 2: 1.0, 3: 1.0, 4: 0.9, 5: 0.18, 6: 0.08}[d.weekday()] for d in days])
day_idx = rng.choice(len(days), size=N, p=day_w / day_w.sum())
hour_w = np.array([0.2]*7 + [1.2, 2.4, 2.6, 2.3, 1.7, 1.4, 1.9, 1.8, 1.5, 1.1, 0.6] + [0.25]*6)
hours = rng.choice(24, size=N, p=hour_w / hour_w.sum())
created = days[day_idx] + pd.to_timedelta(hours, unit="h") + pd.to_timedelta(rng.integers(0, 3600, N), unit="s")

cat_names = list(categories)
cat = rng.choice(cat_names, size=N, p=[categories[c][0] for c in cat_names])
region = rng.choice(regions, size=N, p=region_p)
product = rng.choice(products, size=N, p=product_p)

# Channel: simple requests still mostly come by phone (the problem we want to find)
channel = np.empty(N, dtype=object)
for c in cat_names:
    m = cat == c
    p = [0.62, 0.20, 0.18] if c in ("Toner / Supplies Reorder", "Meter Read / Billing") else [0.55, 0.30, 0.15]
    channel[m] = rng.choice(["Phone", "Email", "Portal"], size=m.sum(), p=p)

prio = np.where(cat == "Service Dispatch Request", rng.choice(["P1", "P2", "P3"], N, p=[.2, .5, .3]),
        np.where(np.isin(cat, ["Paper Jam / Hardware Fault", "Print Driver / Network"]),
                 rng.choice(["P1", "P2", "P3", "P4"], N, p=[.06, .30, .52, .12]),
                 rng.choice(["P2", "P3", "P4"], N, p=[.10, .50, .40])))

df = pd.DataFrame({"created_at": created, "channel": channel, "region": region,
                   "product_line": product, "category": cat, "priority": prio})
df = df.sort_values("created_at").reset_index(drop=True)
df.insert(0, "ticket_id", [f"TKT-{100000+i}" for i in range(N)])
df = df.merge(sla, on="priority", how="left")

wd, hr = df.created_at.dt.weekday, df.created_at.dt.hour
monday_rush = (wd == 0) & hr.between(8, 10)
after_hours = (hr < 7) | (hr >= 18) | (wd >= 5)

# First response (minutes)
base_fr = df.channel.map({"Phone": 4, "Email": 70, "Portal": 35}).to_numpy(float)
fr = rng.gamma(2.0, base_fr / 2.0)
fr = fr * np.where(monday_rush, 2.6, 1.0) * np.where(after_hours, 3.0, 1.0)
df["first_response_min"] = fr.round(1)

# Handle time (agent minutes) -- portal supply/meter requests are mostly automated
aht = np.array([categories[c][1] for c in df.category])
aht = aht * df.channel.map({"Phone": 1.0, "Email": 0.8, "Portal": 0.6}).to_numpy()
auto = (df.channel == "Portal") & df.category.isin(["Toner / Supplies Reorder", "Meter Read / Billing"])
aht = np.where(auto, rng.uniform(0.5, 1.5, N), rng.gamma(4, aht / 4))
df["handle_time_min"] = aht.round(1)

# Tier / escalation
esc_p = df.category.map({"Print Driver / Network": .38, "Scan-to-Email / Software": .25,
                         "Paper Jam / Hardware Fault": .18, "Service Dispatch Request": .10}).fillna(.03)
df["escalated"] = rng.random(N) < esc_p
df["tier"] = np.where(df.escalated, "Tier 2", "Tier 1")
t1 = [f"A{100+i}" for i in range(28)]; t2 = [f"A{200+i}" for i in range(9)]
df["agent_id"] = np.where(df.escalated, rng.choice(t2, N), rng.choice(t1, N))

# First-contact resolution
fcr_p = np.array([categories[c][2] for c in df.category])
fcr_p = np.where(auto, 0.97, fcr_p) * np.where(df.escalated, 0.0, 1.0)
df["first_contact_resolved"] = rng.random(N) < fcr_p

# Field dispatch
disp_p = np.array([categories[c][3] for c in df.category])
df["field_dispatch"] = rng.random(N) < disp_p

# Resolution hours
res = rng.gamma(2.2, 1.0, N) * df.priority.map({"P1": 1.1, "P2": 2.0, "P3": 5.0, "P4": 11.0}).to_numpy()
res = res + np.where(df.field_dispatch, rng.gamma(3, 2.2, N), 0) + np.where(df.escalated, rng.gamma(2, 2.5, N), 0)
res = res * np.where(monday_rush, 1.55, 1.0)
res = np.where(df.first_contact_resolved, df.handle_time_min / 60 + rng.uniform(0, .3, N), res)
df["resolution_hours"] = np.round(res, 2)
df["resolved_at"] = df.created_at + pd.to_timedelta(df.resolution_hours, unit="h")

# Reopens: firmware v4.2 release (2026-03-09) broke drivers in Inland Empire for ~10 weeks
fw = (df.category == "Print Driver / Network") & (df.region == "Inland Empire") & \
     df.created_at.between("2026-03-09", "2026-05-18")
reopen_p = np.where(fw, 0.34, np.where(df.first_contact_resolved, 0.03, 0.08))
df["reopened"] = rng.random(N) < reopen_p

df["sla_met"] = df.resolution_hours <= df.sla_target_hours

# CSAT (1-5), ~35% response rate
cs = 4.4 - 1.3 * (~df.sla_met) - 0.9 * df.reopened - 0.3 * df.escalated + rng.normal(0, .6, N)
cs = np.clip(np.round(cs), 1, 5)
df["csat"] = np.where(rng.random(N) < 0.35, cs, np.nan)

# Cost: $0.85 per agent minute (loaded) + $145 per field visit
df["cost_usd"] = (df.handle_time_min * 0.85 + df.field_dispatch * 145).round(2)

# --- inject a little real-world mess for the data-quality step ---
dirty = df.sample(60, random_state=7).index
df.loc[dirty[:20], "region"] = df.loc[dirty[:20], "region"].str.upper()        # inconsistent case
df.loc[dirty[20:35], "handle_time_min"] = -df.loc[dirty[20:35], "handle_time_min"]  # sign errors
dupes = df.sample(25, random_state=11)                                          # duplicate exports
df = pd.concat([df, dupes]).sort_values("created_at").reset_index(drop=True)

df.to_csv(OUT / "tickets.csv", index=False)
pd.DataFrame({"agent_id": t1 + t2, "tier": ["Tier 1"]*len(t1) + ["Tier 2"]*len(t2),
              "shift": rng.choice(["Early 7-3", "Day 8-4", "Late 10-6"], len(t1)+len(t2))}
             ).to_csv(OUT / "agents.csv", index=False)
sla.to_csv(OUT / "sla_targets.csv", index=False)
print(f"tickets.csv: {len(df):,} rows  ->  {OUT}")
