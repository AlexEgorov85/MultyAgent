-- Постоянная история диалога.
--
-- Ключ conversation_id — стабильный id чата из UI. Он не зависит от
-- backend thread_id и переживает пересоздание LangGraph-треда.

CREATE TABLE audit.chat_threads (
    conversation_id text PRIMARY KEY,
    auditor_id      text NOT NULL DEFAULT '',
    title           text NOT NULL DEFAULT '',
    created_at      timestamptz NOT NULL DEFAULT now(),
    updated_at      timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE audit.chat_messages (
    message_id      text PRIMARY KEY,
    conversation_id text NOT NULL REFERENCES audit.chat_threads(conversation_id)
                    ON DELETE CASCADE,
    turn_id         text NOT NULL,
    role            text NOT NULL CHECK (role IN ('user', 'assistant')),
    content         text NOT NULL,
    trace           jsonb,
    resolved_query  text,
    created_at      timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (conversation_id, turn_id, role)
);

CREATE INDEX ix_chat_messages_thread_time
    ON audit.chat_messages (conversation_id, created_at);

CREATE INDEX ix_chat_threads_auditor_time
    ON audit.chat_threads (auditor_id, updated_at DESC);
