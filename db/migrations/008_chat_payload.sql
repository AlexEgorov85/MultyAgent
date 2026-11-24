-- Payload последнего ответа агента для follow-up запросов.
-- Нужен, чтобы «построй диаграмму на основании этих данных» работал
-- не по тексту ответа, а по исходным строкам и колонкам.

ALTER TABLE audit.chat_messages
    ADD COLUMN IF NOT EXISTS payload jsonb;
