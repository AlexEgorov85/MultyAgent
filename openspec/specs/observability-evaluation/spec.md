# Observability and Evaluation

## Purpose

Делает качество и стоимость системы измеримыми: собирает метрики по каждому запросу, прогоняет фиксированный набор кейсов и публикует воспроизводимые результаты.

## Requirements

### Requirement: Метрики эффективности

Система SHALL собирать latency, токены, стоимость, число вызовов LLM и tools, SQL-повторы и ACL-раунды.

#### Scenario: Один запрос

- **WHEN** запрос завершён
- **THEN** метрики содержат `latency_total_sec`, `llm_calls`, `tool_calls`, `sql_queries`, `sql_retries`, `input_tokens`, `output_tokens`, `cost_usd`
- **AND** для investigation дополнительно `acl_rounds`

#### Scenario: Ошибка на середине

- **WHEN** запрос завершился отказом или ошибкой
- **THEN** собранные до этого метрики сохраняются
- **AND** фиксируется причина завершения

### Requirement: Метрики качества

Система SHALL рассчитывать метрики качества по фиксированному набору кейсов.

#### Scenario: Обязательный минимум

- **WHEN** запускается оценка
- **THEN** рассчитываются `route_accuracy`, `sql_validity_rate`, `numeric_accuracy`, `evidence_coverage` и `success_rate`
- **AND** для investigation дополнительно сохраняются ACL-раунды и типы evidence

> `sql_execution_success_rate`, `citation_precision`, `investigation_completeness`
> и LLM-judge с рубрикой 1–10 вынесены в план развития после сдачи
> (`docs/improvement_plan.md`); в текущей реализации они не считаются.

### Requirement: Процессные метрики и снимок состояния

Система SHALL собирать метрики процесса агента, а не только итоговый ответ.

#### Scenario: Один ход бенчмарка

- **WHEN** выполняется реплика бенчмарка
- **THEN** фиксируются вызовы LLM, input/output/cached токены, стоимость,
  вызовы инструментов, SQL-retries, ACL-раунды и шаги `trace`
- **AND** сохраняется разбивка времени: общее, LLM, инструменты, overhead
- **AND** сохраняется компактный `state`: маршрут, `resolved_query`,
  guardrails, ACL, evidence, шаги, промпты и `fingerprint`

#### Scenario: Версии промптов

- **WHEN** LLM загружает промпт
- **THEN** в телеметрию попадают `id`, `version` и `hash`
- **AND** отчёт содержит реестр версий промптов и использованные версии по репликам

#### Scenario: Ограничения процесса

- **WHEN** в кейсе заданы `max_llm_calls`, `max_llm_errors`,
  `max_tool_calls`, `max_total_tokens`, `max_cost_usd`, `max_latency_sec`,
  `max_sql_retries`, `max_acl_rounds`, `max_steps`, `expected_steps` или
  `forbidden_tools`
- **THEN** превышение или нарушение делает `process_success = false`
- **AND** ответ может остаться корректным, но общий `success` будет false

### Requirement: Triage, diff и regression-gate

Система SHALL превращать результаты бенчмарка в backlog доработок и
проверять изменения перед принятием.

#### Scenario: Разбор провалов

- **WHEN** выполняется `scripts/benchmark_triage.py`
- **THEN** создаются `reports/benchmark_backlog.md` и `.json`
- **AND** провалы классифицируются по слоям: routing, context, tool_policy,
  sql, evidence, citations, numeric, answer, steps, efficiency
- **AND** `provider` и `runtime` отделяются от ошибок качества агента
- **AND** для кластера указаны файлы-кандидаты и команда целевого прогона

#### Scenario: Сравнение baseline и candidate

- **WHEN** выполняется `scripts/benchmark_diff.py baseline.json candidate.json --gate`
- **THEN** отчёт содержит улучшения, регрессии и Δ summary/tokens/latency/cost
- **AND** gate возвращает код 1 при падении success, росте бюджета или регрессиях

#### Scenario: Предложение по доработке

- **WHEN** выполняется `scripts/improve_agent.py`
- **THEN** создаётся безопасное предложение без изменения кода
- **AND** предложение не меняет разметку бенчмарка и guardrails

### Requirement: Структурированный журнал запуска

Система SHALL сохранять по каждому запуску состояние, ACL, SQL, вызовы tools и метрики.

#### Scenario: Восстановление хода выполнения

- **WHEN** разработчик открывает лог запуска
- **THEN** видны маршрут, ACL-сообщения, выполненные и отклонённые SQL, вызовы tools и итоговые метрики
- **AND** секреты и чувствительные данные отсутствуют

### Requirement: Фиксированный тестовый набор

Система SHALL содержать не менее 26 кейсов, покрывающих аналитику, поиск, отчёт, расследование, память и отказы.

#### Scenario: Состав набора

- **WHEN** набор загружен
- **THEN** в нём есть кейсы `analytics`, `retrieval`, `report`, `investigation`, `out_of_domain`, `unsafe` и `memory`
- **AND** каждый кейс содержит ожидаемый маршрут, ожидаемые tools и признаки корректного ответа

#### Scenario: Кейс расследования

- **WHEN** выполняется `inv_01`
- **THEN** проверяются ожидаемые ACL-агенты, минимум раундов и обязательные типы evidence
- **AND** причинное утверждение без доказательств считается ошибкой

### Requirement: Многоуровневый бенчмарк и проверка контекста

Система SHALL содержать отдельный бенчмарк из простых, сложных и цепочечных
кейсов и измерять перенос контекста между репликами.

#### Scenario: Простые и сложные вопросы

- **WHEN** выполняется `scripts/benchmark.py`
- **THEN** простые кейсы проверяют один факт, шаблон или drill-down
- **AND** сложные кейсы проверяют multi-tool, отчёт, investigation и динамику
- **AND** для каждой реплики проверяются маршрут, числа, tools, strategy и evidence

#### Scenario: Цепочка уточнений

- **WHEN** выполняется кейс уровня `chain`
- **THEN** все реплики идут в одной нити `thread_id`
- **AND** проверяется, что год, тема или код проверки попали в `resolved_query`
  либо в ответ
- **AND** метрики содержат `context_retention_rate`, `context_rewrite_rate` и
  `context_answer_rate`

#### Scenario: Потеря серверной нити

- **WHEN** в цепочке указан `reset_thread`
- **THEN** предыдущие реплики передаются через `client_history`
- **AND** уточнение после смены нити не теряет сущности предыдущего вопроса

### Requirement: Воспроизводимый прогон оценки

Система SHALL поддерживать повторный прогон оценки при temperature 0 с публикацией среднего и стандартного отклонения.

#### Scenario: Три прогона

- **WHEN** выполняется `scripts/evaluate.py --repeat 3`
- **THEN** каждый кейс выполняется три раза в изолированной нити
- **AND** создаются `reports/metrics.csv` и `reports/metrics.md`
- **AND** для метрик указаны mean и стандартное отклонение (population std)
- **AND** настройки модели и seed зафиксированы

### Requirement: Публикация результатов

Система SHALL включать актуальные значения метрик в README.

#### Scenario: Чтение README

- **WHEN** проверяющий открывает README
- **THEN** он видит таблицу метрик эффективности и качества
- **AND** понимает, на каком наборе и при каких настройках получены значения

#### Scenario: Достоверность опубликованных метрик

- **WHEN** в README или документации указаны числа прогона
- **THEN** рядом указаны дата, модель, seed и набор кейсов
- **AND** метрики прошлой ревизии помечены как исторические
- **AND** частичный или прерванный прогон не публикуется как оценка системы
