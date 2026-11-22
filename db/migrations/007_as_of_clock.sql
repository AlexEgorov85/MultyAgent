-- 007_as_of_clock.sql
-- Единая точка отсчёта для просрочек: audit.dataset_metadata.as_of_date.
--
-- Миграция перекрывает определения представлений из 003_views.sql, где
-- использовалась системная дата CURRENT_DATE. Спецификация data-generation
-- требует фиксированный срез 2026-11-21 и запрещает зависимость от
-- CURRENT_DATE. Старые миграции не изменяются: реестр
-- public.schema_migrations хранит их checksum.

CREATE OR REPLACE FUNCTION audit.as_of_date()
RETURNS date
LANGUAGE sql
STABLE
PARALLEL SAFE
AS $$
    SELECT coalesce(
        (SELECT as_of_date FROM audit.dataset_metadata WHERE metadata_id = 1),
        DATE '2026-11-21'
    );
$$;

-- Роли создаются позже миграций (db_runtime.ensure_roles), поэтому гранты
-- выдаются только уже существующим ролям. Для новых баз права на функции
-- дополнительно раздаёт ensure_roles.
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'audit_ro') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION audit.as_of_date() TO audit_ro';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'audit_app') THEN
        EXECUTE 'GRANT EXECUTE ON FUNCTION audit.as_of_date() TO audit_app';
    END IF;
END
$$;

CREATE OR REPLACE VIEW audit.v_pocket_summary AS
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
        WHERE i.status <> 'закрыт' AND i.deadline < audit.as_of_date()
    )                                                                 AS overdue_count
FROM audit.audit_pockets p
LEFT JOIN audit.audits a ON a.pocket_id = p.pocket_id
LEFT JOIN audit.acts ac ON ac.audit_id = a.audit_id
LEFT JOIN audit.act_items i ON i.act_id = ac.act_id
GROUP BY p.pocket_id, p.pocket_year, p.theme_code, p.title, p.risk_level, p.planned_audit_count;

CREATE OR REPLACE VIEW audit.v_open_items AS
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
    (i.deadline IS NOT NULL AND i.deadline < audit.as_of_date()) AS is_overdue,
    audit.as_of_date() - i.deadline                              AS days_overdue
FROM audit.act_items i
JOIN audit.acts ac ON ac.act_id = i.act_id
JOIN audit.audits a ON a.audit_id = ac.audit_id
JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id
WHERE i.status <> 'закрыт';
