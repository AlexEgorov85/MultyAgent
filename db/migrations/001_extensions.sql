-- 001_extensions.sql
-- Схема аудита создаётся с нуля: это упрощает повторный запуск init_db.py.

CREATE EXTENSION IF NOT EXISTS vector;

DROP SCHEMA IF EXISTS audit CASCADE;
CREATE SCHEMA audit;
