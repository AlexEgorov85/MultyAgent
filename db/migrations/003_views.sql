-- 003_views.sql
-- Готовые срезы для NL→SQL, UI и QA.

CREATE VIEW audit.v_pocket_summary AS
SELECT
    p.pocket_id,
    p.pocket_year,
    p.theme_code,
    p.title,
    p.risk_level,
    p.planned_audit_count,
    count(DISTINCT a.audit_id)                                        AS audit_count,
    count(DISTINCT ac.act_id)                                         AS act_count,
    count(i.item_id)                                                  AS item_count,
    count(i.item_id) FILTER (WHERE i.item_type = 'отклонение')        AS deviation_count,
    count(i.item_id) FILTER (WHERE i.item_type = 'проблема')          AS problem_count,
    count(i.item_id) FILTER (WHERE i.risk_level = 'критический')      AS critical_count,
    count(i.item_id) FILTER (WHERE i.status = 'открыт')               AS open_count,
    count(i.item_id) FILTER (
        WHERE i.status <> 'закрыт' AND i.deadline < CURRENT_DATE
    )                                                                 AS overdue_count
FROM audit.audit_pockets p
LEFT JOIN audit.audits a ON a.pocket_id = p.pocket_id
LEFT JOIN audit.acts ac ON ac.audit_id = a.audit_id
LEFT JOIN audit.act_items i ON i.act_id = ac.act_id
GROUP BY p.pocket_id, p.pocket_year, p.theme_code, p.title, p.risk_level, p.planned_audit_count;

CREATE VIEW audit.v_audit_summary AS
SELECT
    a.audit_id,
    a.audit_code,
    a.title,
    a.status,
    a.audit_type,
    a.start_date,
    a.end_date,
    a.risk_level,
    p.pocket_id,
    p.pocket_year,
    p.theme_code,
    p.title                AS pocket_title,
    au.full_name           AS lead_auditor,
    ac.act_id,
    ac.act_number,
    ac.status              AS act_status,
    ac.act_date,
    count(i.item_id)                                       AS item_count,
    count(i.item_id) FILTER (WHERE i.item_type = 'отклонение') AS deviation_count,
    count(i.item_id) FILTER (WHERE i.item_type = 'проблема')   AS problem_count,
    count(i.item_id) FILTER (WHERE i.status = 'открыт')        AS open_count
FROM audit.audits a
JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id
JOIN audit.auditors au ON au.auditor_id = a.lead_auditor_id
LEFT JOIN audit.acts ac ON ac.audit_id = a.audit_id
LEFT JOIN audit.act_items i ON i.act_id = ac.act_id
GROUP BY a.audit_id, p.pocket_id, au.full_name, ac.act_id;

CREATE VIEW audit.v_act_item_details AS
SELECT
    i.item_id,
    i.item_number,
    i.item_type,
    i.test_type,
    i.title,
    i.test_description,
    i.condition,
    i.cause,
    i.effect,
    i.recommendation,
    i.risk_level,
    i.status,
    i.deadline,
    i.closed_at,
    i.is_repeat,
    i.repeat_of_item_id,
    ac.act_id,
    ac.act_number,
    ac.act_date,
    a.audit_id,
    a.audit_code,
    a.title                AS audit_title,
    p.pocket_id,
    p.pocket_year,
    p.theme_code,
    count(s.script_id)                                      AS script_count,
    coalesce(sum(s.rows_found), 0)                          AS rows_found_total,
    count(s.script_id) FILTER (WHERE s.language = 'SQL')    AS sql_script_count
FROM audit.act_items i
JOIN audit.acts ac ON ac.act_id = i.act_id
JOIN audit.audits a ON a.audit_id = ac.audit_id
JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id
LEFT JOIN audit.scripts s ON s.item_id = i.item_id
GROUP BY i.item_id, ac.act_id, a.audit_id, p.pocket_id;

CREATE VIEW audit.v_open_items AS
SELECT
    i.item_id,
    i.item_number,
    i.title,
    i.item_type,
    i.risk_level,
    i.status,
    i.deadline,
    ac.act_number,
    a.audit_code,
    p.theme_code,
    (i.deadline IS NOT NULL AND i.deadline < CURRENT_DATE) AS is_overdue,
    CURRENT_DATE - i.deadline                              AS days_overdue
FROM audit.act_items i
JOIN audit.acts ac ON ac.act_id = i.act_id
JOIN audit.audits a ON a.audit_id = ac.audit_id
JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id
WHERE i.status <> 'закрыт';

CREATE VIEW audit.v_repeat_items AS
SELECT
    i.item_id,
    i.item_number,
    i.title,
    i.risk_level,
    i.status,
    i.repeat_of_item_id,
    prev.title       AS previous_title,
    prev.item_number AS previous_number,
    ac_current.act_number AS act_number,
    ac_prev.act_number    AS previous_act_number,
    p_current.theme_code  AS theme_code,
    p_current.pocket_year AS pocket_year
FROM audit.act_items i
JOIN audit.acts ac_current ON ac_current.act_id = i.act_id
JOIN audit.audits a_current ON a_current.audit_id = ac_current.audit_id
JOIN audit.audit_pockets p_current ON p_current.pocket_id = a_current.pocket_id
JOIN audit.act_items prev ON prev.item_id = i.repeat_of_item_id
JOIN audit.acts ac_prev ON ac_prev.act_id = prev.act_id
WHERE i.is_repeat = true;

CREATE VIEW audit.v_script_usage AS
SELECT
    s.language,
    count(*)                                   AS script_count,
    count(*) FILTER (WHERE s.rows_found > 0)   AS scripts_with_findings,
    sum(s.rows_found)                          AS rows_found_total,
    round(avg(s.rows_found), 1)                AS rows_found_avg,
    round(avg(s.execution_ms), 0)              AS execution_ms_avg
FROM audit.scripts s
GROUP BY s.language;

CREATE VIEW audit.v_theme_year_dynamics AS
SELECT
    p.theme_code,
    p.pocket_year,
    count(i.item_id)                                              AS item_count,
    count(i.item_id) FILTER (WHERE i.item_type = 'отклонение')    AS deviation_count,
    count(i.item_id) FILTER (WHERE i.item_type = 'проблема')      AS problem_count,
    count(i.item_id) FILTER (WHERE i.risk_level = 'критический')  AS critical_count,
    count(i.item_id) FILTER (WHERE i.is_repeat)                   AS repeat_count,
    count(i.item_id) FILTER (WHERE i.status = 'закрыт')           AS closed_count
FROM audit.audit_pockets p
LEFT JOIN audit.audits a ON a.pocket_id = p.pocket_id
LEFT JOIN audit.acts ac ON ac.audit_id = a.audit_id
LEFT JOIN audit.act_items i ON i.act_id = ac.act_id
GROUP BY p.theme_code, p.pocket_year;

CREATE VIEW audit.v_items_without_scripts AS
SELECT
    i.item_id,
    i.item_number,
    i.title,
    i.item_type,
    i.test_type,
    i.risk_level,
    i.status,
    ac.act_number,
    a.audit_code
FROM audit.act_items i
JOIN audit.acts ac ON ac.act_id = i.act_id
JOIN audit.audits a ON a.audit_id = ac.audit_id
WHERE NOT EXISTS (
    SELECT 1 FROM audit.scripts s WHERE s.item_id = i.item_id
);
