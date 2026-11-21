-- 004_spec_alignment.sql
-- Приведение схемы к OpenSpec-спецификациям data-platform / data-generation.
-- Новые колонки пунктов пока nullable: генератор заполнит их на следующем шаге,
-- после чего отдельная миграция закрепит NOT NULL.

-- Утверждённый акт обязан иметь утверждающего; остальные статусы — не имеют.
ALTER TABLE audit.acts
    ADD CONSTRAINT chk_act_approval CHECK (
        (status = 'утверждён' AND approved_by IS NOT NULL)
        OR (status <> 'утверждён' AND approved_by IS NULL)
    ) NOT VALID;

-- Различение однотипных находок по объекту/периоду.
ALTER TABLE audit.act_items
    ADD COLUMN IF NOT EXISTS finding_template_key text,
    ADD COLUMN IF NOT EXISTS finding_scope text;

ALTER TABLE audit.act_items
    ADD CONSTRAINT uq_act_item_scope
    UNIQUE (act_id, finding_template_key, finding_scope);

-- Статус и дата закрытия должны быть согласованы в обе стороны.
ALTER TABLE audit.act_items DROP CONSTRAINT IF EXISTS chk_closed_at;
ALTER TABLE audit.act_items
    ADD CONSTRAINT chk_closed_at CHECK (
        (status = 'закрыт' AND closed_at IS NOT NULL)
        OR (status <> 'закрыт' AND closed_at IS NULL)
    );

-- Результат скрипта не может превышать популяцию.
ALTER TABLE audit.scripts
    ADD CONSTRAINT chk_script_rows CHECK (
        population_size IS NULL
        OR rows_found IS NULL
        OR rows_found <= population_size
    );

-- Фиксированный срез набора: просрочки не зависят от системной даты.
CREATE TABLE IF NOT EXISTS audit.dataset_metadata (
    metadata_id smallint PRIMARY KEY CHECK (metadata_id = 1),
    as_of_date  date NOT NULL,
    seed        integer NOT NULL,
    checksum    text NOT NULL
);
