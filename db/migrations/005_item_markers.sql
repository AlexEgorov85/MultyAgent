-- 005_item_markers.sql
-- Каждый новый пункт обязан иметь технический ключ шаблона и область применения.
-- Ограничение добавлено как NOT VALID, чтобы миграция не зависела от старых строк;
-- генератор и QA проверяют заполненность для всего набора.

ALTER TABLE audit.act_items
    ADD CONSTRAINT chk_finding_marker CHECK (
        finding_template_key IS NOT NULL
        AND finding_scope IS NOT NULL
    ) NOT VALID;
