-- Модель эмбеддингов, которой построен RAG-индекс.
-- Нужна, чтобы backend не смешивал hash- и OpenAI-эмбеддинги: запрос
-- должен считаться той же моделью, что и чанки.

ALTER TABLE audit.dataset_metadata
    ADD COLUMN IF NOT EXISTS embedding_model text;
