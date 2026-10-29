-- KPI query library for the support-operations dashboard (SQLite dialect).
-- Each block is named so the notebook and tests can run it by name.

-- name: kpi_summary
SELECT COUNT(*)                                  AS tickets,
       ROUND(AVG(sla_met), 4)                    AS sla_attainment,
       ROUND(AVG(first_contact_resolved), 4)     AS first_contact_resolution,
       ROUND(AVG(first_response_min), 2)         AS avg_first_response_min,
       ROUND(AVG(handle_time_min), 2)            AS avg_handle_time_min,
       ROUND(AVG(reopened), 4)                   AS reopen_rate,
       ROUND(AVG(csat), 2)                       AS avg_csat,
       ROUND(AVG(cost_usd), 2)                   AS cost_per_ticket
FROM tickets;

-- name: monthly_trend
SELECT month,
       COUNT(*)                              AS tickets,
       ROUND(AVG(sla_met), 4)                AS sla_attainment,
       ROUND(AVG(first_contact_resolved), 4) AS fcr,
       ROUND(AVG(reopened), 4)               AS reopen_rate,
       ROUND(AVG(csat), 2)                   AS avg_csat,
       -- month-over-month volume change with a window function
       ROUND(100.0 * (COUNT(*) - LAG(COUNT(*)) OVER (ORDER BY month))
             / LAG(COUNT(*)) OVER (ORDER BY month), 1) AS volume_mom_pct
FROM tickets
GROUP BY month
ORDER BY month;

-- name: category_channel_mix
SELECT category, channel,
       COUNT(*)                         AS tickets,
       ROUND(SUM(handle_time_min)/60,1) AS agent_hours,
       ROUND(AVG(handle_time_min),1)    AS avg_handle_min,
       ROUND(AVG(first_contact_resolved),3) AS fcr
FROM tickets
GROUP BY category, channel
ORDER BY agent_hours DESC;

-- name: sla_breach_heatmap
SELECT weekday, hour,
       COUNT(*)                          AS tickets,
       ROUND(1 - AVG(sla_met), 4)        AS breach_rate
FROM tickets
WHERE hour BETWEEN 7 AND 18
GROUP BY weekday, hour;

-- name: reopen_by_region_month
SELECT region, month,
       COUNT(*)                 AS driver_network_tickets,
       ROUND(AVG(reopened), 4)  AS reopen_rate
FROM tickets
WHERE category = 'Print Driver / Network'
GROUP BY region, month
ORDER BY region, month;

-- name: agent_scorecard
SELECT t.agent_id, a.tier, a.shift,
       COUNT(*)                              AS tickets,
       ROUND(AVG(t.handle_time_min),1)       AS avg_handle_min,
       ROUND(AVG(t.first_contact_resolved),3) AS fcr,
       ROUND(AVG(t.csat),2)                  AS avg_csat,
       RANK() OVER (PARTITION BY a.tier ORDER BY AVG(t.csat) DESC) AS csat_rank_in_tier
FROM tickets t
JOIN agents a ON a.agent_id = t.agent_id
GROUP BY t.agent_id, a.tier, a.shift
ORDER BY a.tier, csat_rank_in_tier;

-- name: deflection_opportunity
-- Simple supply / meter-read requests handled by a live agent on phone or email
SELECT category, channel,
       COUNT(*)                          AS tickets,
       ROUND(SUM(handle_time_min)/60,1)  AS agent_hours,
       ROUND(SUM(handle_time_min)*0.85,0) AS agent_cost_usd
FROM tickets
WHERE simple_request = 1 AND channel IN ('Phone','Email')
GROUP BY category, channel;

-- name: sla_by_priority
SELECT t.priority, s.sla_target_hours,
       COUNT(*)                       AS tickets,
       ROUND(AVG(t.sla_met),4)        AS sla_attainment,
       ROUND(AVG(t.resolution_hours),2) AS avg_resolution_hours
FROM tickets t JOIN sla_targets s USING (priority)
GROUP BY t.priority, s.sla_target_hours
ORDER BY t.priority;
