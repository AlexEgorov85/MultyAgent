-- 002_schema.sql
-- Доменная модель «карманы → проверки → акты → пункты → скрипты».
-- Все значения enum и текстовые данные — на русском (см. ПЛАН_ПРОЕКТА.md, 14.12.0).

CREATE TYPE audit.risk_level AS ENUM ('низкий', 'средний', 'высокий', 'критический');
CREATE TYPE audit.audit_status AS ENUM ('запланирована', 'в работе', 'завершена', 'отменена');
CREATE TYPE audit.act_status AS ENUM ('черновик', 'на согласовании', 'утверждён');
CREATE TYPE audit.item_type AS ENUM ('отклонение', 'проблема');
CREATE TYPE audit.item_status AS ENUM ('открыт', 'в работе', 'закрыт');
CREATE TYPE audit.test_type AS ENUM (
    'непрерывный', 'выборочный', 'аналитический', 'повторное выполнение', 'опрос'
);
CREATE TYPE audit.script_language AS ENUM ('SQL', 'Python', 'R', 'Excel', 'Другое');

CREATE TABLE audit.auditors (
    auditor_id      text PRIMARY KEY,
    full_name       text NOT NULL,
    email           text NOT NULL UNIQUE,
    unit            text NOT NULL,
    position        text NOT NULL,
    grade           text,
    specializations text[] NOT NULL DEFAULT '{}',
    is_active       boolean NOT NULL DEFAULT true,
    created_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit.audit_pockets (
    pocket_id           text PRIMARY KEY,
    pocket_year         smallint NOT NULL CHECK (pocket_year BETWEEN 2025 AND 2026),
    theme_code          text NOT NULL CHECK (
        theme_code IN ('ипотека', 'потребкредитование', 'платежи', 'карты', 'вклады')
    ),
    title               text NOT NULL,
    description         text,
    owner_unit          text NOT NULL,
    period_start        date NOT NULL,
    period_end          date NOT NULL,
    planned_audit_count smallint NOT NULL CHECK (planned_audit_count BETWEEN 5 AND 20),
    risk_level          audit.risk_level NOT NULL DEFAULT 'средний',
    status              text NOT NULL DEFAULT 'активен' CHECK (status IN ('активен', 'закрыт')),
    created_at          timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_pocket_year_theme UNIQUE (pocket_year, theme_code),
    CONSTRAINT chk_pocket_period CHECK (period_end >= period_start)
);

CREATE TABLE audit.audits (
    audit_id        text PRIMARY KEY,
    pocket_id       text NOT NULL REFERENCES audit.audit_pockets(pocket_id),
    audit_code      text NOT NULL UNIQUE,
    title           text NOT NULL,
    audit_type      text NOT NULL CHECK (
        audit_type IN ('плановая', 'внеплановая', 'тематическая', 'повторная', 'последующий контроль')
    ),
    start_date      date NOT NULL,
    end_date        date NOT NULL,
    status          audit.audit_status NOT NULL,
    lead_auditor_id text NOT NULL REFERENCES audit.auditors(auditor_id),
    team_size       smallint NOT NULL CHECK (team_size BETWEEN 1 AND 10),
    scope           text,
    risk_level      audit.risk_level NOT NULL DEFAULT 'средний',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT chk_audit_dates CHECK (end_date >= start_date)
);

CREATE TABLE audit.acts (
    act_id      text PRIMARY KEY,
    audit_id    text NOT NULL UNIQUE REFERENCES audit.audits(audit_id) ON DELETE CASCADE,
    act_number  text NOT NULL UNIQUE,
    act_date    date NOT NULL,
    status      audit.act_status NOT NULL,
    approved_by text REFERENCES audit.auditors(auditor_id),
    summary     text,
    full_text   text,
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit.act_items (
    item_id           text PRIMARY KEY,
    act_id            text NOT NULL REFERENCES audit.acts(act_id) ON DELETE CASCADE,
    item_number       text NOT NULL,
    item_type         audit.item_type NOT NULL,
    test_type         audit.test_type NOT NULL,
    title             text NOT NULL,
    test_description  text NOT NULL,
    criterion         text,
    condition         text,
    cause             text,
    effect            text,
    recommendation    text,
    risk_level        audit.risk_level NOT NULL,
    status            audit.item_status NOT NULL DEFAULT 'открыт',
    deadline          date,
    responsible_unit  text,
    closed_at         date,
    is_repeat         boolean NOT NULL DEFAULT false,
    repeat_of_item_id text REFERENCES audit.act_items(item_id),
    order_index       smallint NOT NULL,
    embedding         vector(1536),
    search_vector     tsvector GENERATED ALWAYS AS (
        to_tsvector(
            'russian',
            coalesce(title, '') || ' ' ||
            coalesce(test_description, '') || ' ' ||
            coalesce(condition, '') || ' ' ||
            coalesce(cause, '') || ' ' ||
            coalesce(effect, '')
        )
    ) STORED,
    created_at        timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_act_item_number UNIQUE (act_id, item_number),
    CONSTRAINT chk_item_number CHECK (item_number ~ '^[0-9]{1,2}(\.[0-9]{1,2}){1,2}$'),
    CONSTRAINT chk_repeat_link CHECK (
        (is_repeat = false AND repeat_of_item_id IS NULL)
        OR (is_repeat = true AND repeat_of_item_id IS NOT NULL)
    ),
    CONSTRAINT chk_closed_at CHECK (status <> 'закрыт' OR closed_at IS NOT NULL)
);

CREATE TABLE audit.scripts (
    script_id       text PRIMARY KEY,
    item_id         text NOT NULL REFERENCES audit.act_items(item_id) ON DELETE CASCADE,
    name            text NOT NULL,
    language        audit.script_language NOT NULL,
    description     text,
    code            text NOT NULL,
    parameters      jsonb NOT NULL DEFAULT '{}'::jsonb,
    source_tables   text[] NOT NULL DEFAULT '{}',
    target_system   text,
    expected_result text,
    result_summary  text,
    population_size integer CHECK (population_size >= 0),
    rows_found      integer CHECK (rows_found >= 0),
    execution_ms    integer CHECK (execution_ms >= 0),
    executed_at     timestamptz,
    version         smallint NOT NULL DEFAULT 1,
    created_at      timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT uq_item_script_version UNIQUE (item_id, name, version)
);

CREATE TABLE audit.script_runs (
    run_id        text PRIMARY KEY,
    script_id     text NOT NULL REFERENCES audit.scripts(script_id) ON DELETE CASCADE,
    run_at        timestamptz NOT NULL,
    status        text NOT NULL CHECK (status IN ('успешно', 'частично', 'ошибка')),
    rows_found    integer NOT NULL DEFAULT 0 CHECK (rows_found >= 0),
    duration_ms   integer CHECK (duration_ms >= 0),
    result_sample jsonb,
    error_message text
);

CREATE TABLE audit.deviations (
    deviation_id    text PRIMARY KEY,
    item_id         text NOT NULL REFERENCES audit.act_items(item_id) ON DELETE CASCADE,
    script_id       text REFERENCES audit.scripts(script_id) ON DELETE SET NULL,
    entity_type     text NOT NULL,
    entity_id       text NOT NULL,
    detected_at     date NOT NULL,
    metric_name     text,
    metric_value    numeric(18, 2),
    threshold_value numeric(18, 2),
    severity        audit.risk_level NOT NULL,
    description     text NOT NULL,
    payload         jsonb NOT NULL DEFAULT '{}'::jsonb
);

-- Методический банк готовых SQL-скриптов: сценарий «готовый скрипт vs SQL от LLM».
CREATE TABLE audit.script_templates (
    template_id      text PRIMARY KEY,
    template_key     text NOT NULL UNIQUE,
    title            text NOT NULL,
    description      text NOT NULL,
    sql_template     text NOT NULL,
    parameters       jsonb NOT NULL DEFAULT '{}'::jsonb,
    max_rows_default integer NOT NULL DEFAULT 200 CHECK (max_rows_default BETWEEN 1 AND 1000),
    is_active        boolean NOT NULL DEFAULT true,
    created_at       timestamptz NOT NULL DEFAULT now()
);

-- Долгосрочная память аудитора (критерий A1).
CREATE TABLE audit.auditor_memory (
    auditor_id   text NOT NULL REFERENCES audit.auditors(auditor_id) ON DELETE CASCADE,
    memory_key   text NOT NULL,
    memory_value text NOT NULL,
    updated_at   timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (auditor_id, memory_key)
);

-- Чанки методических документов и актов для RAG.
CREATE TABLE audit.knowledge_chunks (
    chunk_id    text PRIMARY KEY,
    source_type text NOT NULL CHECK (source_type IN ('методика', 'акт', 'пункт')),
    source_id   text,
    title       text NOT NULL,
    content     text NOT NULL,
    embedding   vector(1536),
    created_at  timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX ix_audits_pocket ON audit.audits(pocket_id);
CREATE INDEX ix_audits_lead ON audit.audits(lead_auditor_id);
CREATE INDEX ix_audits_dates ON audit.audits(start_date, end_date);
CREATE INDEX ix_audits_status ON audit.audits(status);
CREATE INDEX ix_acts_date ON audit.acts(act_date);
CREATE INDEX ix_items_act ON audit.act_items(act_id);
CREATE INDEX ix_items_type_risk ON audit.act_items(item_type, risk_level);
CREATE INDEX ix_items_status_deadline ON audit.act_items(status, deadline);
CREATE INDEX ix_items_embedding ON audit.act_items USING hnsw (embedding vector_cosine_ops);
CREATE INDEX ix_items_fts ON audit.act_items USING gin (search_vector);
CREATE INDEX ix_scripts_item ON audit.scripts(item_id);
CREATE INDEX ix_scripts_language ON audit.scripts(language);
CREATE INDEX ix_deviations_item ON audit.deviations(item_id);
CREATE INDEX ix_deviations_script ON audit.deviations(script_id);
CREATE INDEX ix_chunks_embedding ON audit.knowledge_chunks USING hnsw (embedding vector_cosine_ops);
