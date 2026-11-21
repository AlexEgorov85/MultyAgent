-- 001_extensions.sql
-- Расширения и схема. Миграция должна быть безопасной при повторном запуске
-- через реестр public.schema_migrations: DROP SCHEMA здесь запрещён.

CREATE EXTENSION IF NOT EXISTS vector;
CREATE SCHEMA IF NOT EXISTS audit;
