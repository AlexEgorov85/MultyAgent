"""Проверки спецификации analytics-agent на fake-LLM."""

from __future__ import annotations

import pytest

from src.acl import make_acl_message
from src import config, db_runtime, dialogue_store
from src.graph.analytics_graph import build_analytics_graph
from src.query import QueryFilter, QueryPlan
from src.schemas import ChartPoint, ChartSpec, SQLPlan, ToolCall, ToolPlan


class FakeLLM:
    def __init__(
        self,
        *,
        plans: list[SQLPlan] | None = None,
        repairs: list[SQLPlan] | None = None,
        tool_plan: ToolPlan | None = None,
        answer: str = "Готово.",
    ) -> None:
        self.plans = list(plans or [])
        self.repairs = list(repairs or [])
        self.tool_plan = tool_plan
        self.answer = answer
        self.calls: list[str] = []

    def plan_sql(self, **kwargs):
        self.calls.append("plan_sql")
        return self.plans.pop(0)

    def repair_sql(self, **kwargs):
        self.calls.append("repair_sql")
        return self.repairs.pop(0)

    def plan_tools(self, **kwargs):
        self.calls.append("plan_tools")
        assert self.tool_plan is not None
        return self.tool_plan

    def summarize(self, **kwargs):
        self.calls.append("summarize")
        return self.answer


class QueryPlanFakeLLM(FakeLLM):
    """Fake с Query IR: SQL должен собрать компилятор, а не LLM."""

    def __init__(self, plan: QueryPlan, answer: str) -> None:
        super().__init__(answer=answer)
        self.query_plan = plan

    def plan_query(self, **kwargs):
        self.calls.append("plan_query")
        return self.query_plan

    def plan_sql(self, **kwargs):
        self.calls.append("plan_sql")
        raise AssertionError("plan_sql не должен вызываться при валидном QueryPlan")


class ChartFakeLLM(FakeLLM):
    """Fake с выбором визуализации моделью."""

    def __init__(self, chart: ChartSpec, **kwargs) -> None:
        super().__init__(**kwargs)
        self.chart = chart

    def plan_chart(self, **kwargs):
        self.calls.append("plan_chart")
        return self.chart


class FormattingFakeLLM(FakeLLM):
    """Fake с отдельным шагом оформления готового ответа."""

    def __init__(self, formatted: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self.formatted = formatted

    def format_answer(self, **kwargs):
        self.calls.append("format_answer")
        return self.formatted


def acl_request(question: str, mode: str | None = None) -> dict:
    content: dict[str, object] = {"question": question, "auditor_id": "AUD-001"}
    if mode is not None:
        content["analytics_mode"] = mode
    return make_acl_message(
        performative="request",
        sender="orchestrator",
        receiver="analytics_agent",
        content=content,
        conversation_id="conv-test-001",
    ).model_dump()


@pytest.fixture()
def sample_graph_data(server):
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.auditors "
            "(auditor_id, full_name, email, unit, position) "
            "VALUES ('AN-001', 'Аналитик Тестов', 'an@audit.local', 'Аудит', 'Аудитор') "
            "ON CONFLICT (auditor_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.audit_pockets "
            "(pocket_id, pocket_year, theme_code, title, owner_unit, "
            " period_start, period_end, planned_audit_count) "
            "VALUES ('PKT-2026-MORTGAGE', 2026, 'ипотека', '2026. Ипотека', "
            "        'Департамент ипотеки', '2026-01-01', '2026-12-31', 5) "
            "ON CONFLICT (pocket_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.audits "
            "(audit_id, pocket_id, audit_code, title, audit_type, start_date, "
            " end_date, status, lead_auditor_id, team_size) "
            "VALUES ('AUD-2026-MORTGAGE-03', 'PKT-2026-MORTGAGE', "
            "        'AUD-2026-MORTGAGE-03', 'Проверка ипотеки', 'плановая', "
            "        '2026-02-01', '2026-03-01', 'завершена', 'AN-001', 2) "
            "ON CONFLICT (audit_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.acts "
            "(act_id, audit_id, act_number, act_date, status, approved_by, "
            " summary, full_text) "
            "VALUES ('ACT-2026-MORTGAGE-03', 'AUD-2026-MORTGAGE-03', "
            "        'ACT-2026-MORTGAGE-03', '2026-03-10', 'утверждён', 'AN-001', "
            "        'Акт по ипотеке', "
            "        'Просроченная актуализация оценки залога. "
            "         Выявлены отклонения по залоговым договорам.') "
            "ON CONFLICT (act_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.act_items "
            "(item_id, act_id, item_number, item_type, test_type, "
            " finding_template_key, finding_scope, title, test_description, "
            " criterion, condition, cause, effect, recommendation, risk_level, "
            " status, deadline, responsible_unit, order_index) "
            "VALUES "
            "('ITM-T-01', 'ACT-2026-MORTGAGE-03', '5.1', 'отклонение', 'непрерывный', "
            " 'MORTGAGE-01', 'договоры 2026', 'Просроченная оценка залога', "
            " 'Проверить срок оценки', 'п. 4.3', 'у 2 из 10', 'нет контроля', "
            " 'риск залога', 'настроить контроль', 'критический', 'открыт', "
            " '2026-06-01', 'Департамент ипотеки', 1), "
            "('ITM-T-02', 'ACT-2026-MORTGAGE-03', '5.2', 'проблема', 'опрос', "
            " 'MORTGAGE-03', 'договоры 2026', 'Неполный пакет документов', "
            " 'Проверить документы', 'п. 3.4', 'по 1 из 10', 'регламент', "
            " 'риск отказа', 'обновить регламент', 'средний', 'открыт', "
            " '2026-05-01', 'Департамент ипотеки', 2) "
            "ON CONFLICT (item_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.script_templates "
            "(template_id, template_key, title, description, sql_template, "
            " parameters, max_rows_default, is_active) "
            "VALUES ('TPL-AN', 'test_status', 'Статусы', 'Тест', "
            "        'SELECT status, count(*) AS cnt FROM audit.audits "
            "         GROUP BY status ORDER BY cnt DESC', '{}', 50, true) "
            "ON CONFLICT (template_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.script_templates "
            "(template_id, template_key, title, description, sql_template, "
            " parameters, max_rows_default, is_active) "
            "VALUES ('TPL-STATUS', 'status_summary', 'Сводка по статусам', 'Тест', "
            "        'SELECT status, count(*) AS cnt FROM audit.audits "
            "         WHERE start_date >= make_date(%(year)s, 1, 1) "
            "         GROUP BY status ORDER BY cnt DESC', "
            "        '{\"year\": 2026}', 50, true) "
            "ON CONFLICT (template_id) DO NOTHING"
        )
    yield
    with db_runtime.connect(server) as conn:
        conn.execute("DELETE FROM audit.act_items WHERE act_id = 'ACT-2026-MORTGAGE-03'")
        conn.execute("DELETE FROM audit.acts WHERE act_id = 'ACT-2026-MORTGAGE-03'")
        conn.execute("DELETE FROM audit.audits WHERE audit_id = 'AUD-2026-MORTGAGE-03'")
        conn.execute("DELETE FROM audit.audit_pockets WHERE pocket_id = 'PKT-2026-MORTGAGE'")
        conn.execute("DELETE FROM audit.auditors WHERE auditor_id = 'AN-001'")
        conn.execute(
            "DELETE FROM audit.script_templates "
            "WHERE template_id IN ('TPL-AN', 'TPL-STATUS')"
        )


def test_generated_sql_answer(server, sample_graph_data):
    llm = FakeLLM(
        plans=[
            SQLPlan(
                strategy="generated",
                sql="SELECT status, count(*) AS cnt FROM audit.audits "
                "GROUP BY status ORDER BY cnt DESC",
                reason="агрегат по статусам",
            )
        ],
        answer="Завершено: 1 проверка.",
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke({"acl_request": acl_request("Покажи проверки")})

    assert result["status"] == "ok"
    assert result["answer"] == "Завершено: 1 проверка."
    assert result["answer_source"] == "llm"
    assert result["rows"]
    assert llm.calls.count("summarize") == 1
    assert result["acl_response"]["performative"] == "inform"
    assert result["acl_response"]["content"]["sql"].upper().count("LIMIT") == 1
    assert result["evidence"][0]["type"] == "sql_result"


def test_query_ir_compiles_sql_without_plan_sql(server, sample_graph_data):
    llm = QueryPlanFakeLLM(
        plan=QueryPlan(
            metric="audit_count",
            dimensions=["status"],
            filters=[QueryFilter(field="theme", value="ипотека")],
        ),
        answer="Завершено: 1 проверка.",
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Сколько проверок по статусам по ипотеке?")}
    )

    assert result["status"] == "ok"
    assert "plan_query" in llm.calls
    assert "plan_sql" not in llm.calls
    assert result["acl_response"]["content"]["metrics"]["plan_source"] == "query_ir"
    assert "GROUP BY a.status" in result["acl_response"]["content"]["sql"]
    assert result["rows"]


def test_invalid_analytics_mode_falls_back_to_sql(server, sample_graph_data):
    llm = FakeLLM(
        plans=[
            SQLPlan(
                strategy="generated",
                sql="SELECT audit_code, status FROM audit.audits",
                reason="обычный SQL",
            )
        ],
        answer="Найдена одна проверка.",
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Покажи проверки", mode="unknown-mode")}
    )

    assert result["status"] == "ok"
    assert result["mode"] == "sql"
    assert llm.calls == ["plan_sql", "summarize"]


def test_invalid_acl_is_refused_without_llm(server, sample_graph_data):
    llm = FakeLLM()
    graph = build_analytics_graph(server, llm)

    result = graph.invoke({"acl_request": {"performative": "request"}})

    assert result["status"] == "refused"
    assert llm.calls == []
    assert "error" in result["acl_response"]


def test_unsafe_sql_is_refused(server, sample_graph_data):
    llm = FakeLLM(
        plans=[
            SQLPlan(
                strategy="generated",
                sql="DELETE FROM audit.audits",
                reason="опасный запрос",
            )
        ]
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke({"acl_request": acl_request("Удали проверки")})

    assert result["status"] == "refused"
    assert result["acl_response"]["performative"] == "refuse"
    assert "SQL отклонён" in result["error"]


def test_sql_error_is_repaired(server, sample_graph_data):
    llm = FakeLLM(
        plans=[
            SQLPlan(
                strategy="generated",
                sql="SELECT missing_column FROM audit.audits",
                reason="ошибка",
            )
        ],
        repairs=[
            SQLPlan(
                strategy="generated",
                sql="SELECT audit_code, status FROM audit.audits",
                reason="исправлено",
            )
        ],
        answer="Найдена одна проверка.",
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke({"acl_request": acl_request("Покажи проверки")})

    assert result["retries"] == 1
    assert result["status"] == "ok"
    assert llm.calls.count("repair_sql") == 1
    assert result["rows"][0]["audit_code"] == "AUD-2026-MORTGAGE-03"


def test_repair_limit_then_failure(server, sample_graph_data):
    bad = SQLPlan(
        strategy="generated",
        sql="SELECT missing_column FROM audit.audits",
        reason="ошибка",
    )
    llm = FakeLLM(plans=[bad], repairs=[bad, bad])
    graph = build_analytics_graph(server, llm)

    result = graph.invoke({"acl_request": acl_request("Покажи проверки")})

    assert result["status"] == "failed"
    assert result["acl_response"]["performative"] == "failure"
    assert result["retries"] == 2


def test_empty_result_is_honest(server, sample_graph_data):
    llm = FakeLLM(
        plans=[
            SQLPlan(
                strategy="generated",
                sql="SELECT audit_code FROM audit.audits "
                "WHERE audit_code = 'AUD-0000-NONE-00'",
                reason="нет данных",
            )
        ]
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke({"acl_request": acl_request("Найди несуществующую проверку")})

    assert result["answer"] == "По заданным условиям ничего не найдено."
    assert result["rows"] == []


def test_template_is_selected_by_contract_not_by_llm(
    server, sample_graph_data
):
    llm = QueryPlanFakeLLM(
        plan=QueryPlan(
            metric="audit_count",
            dimensions=["status"],
            reason="LLM описала только смысл",
        ),
        answer="Статусы получены.",
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke({"acl_request": acl_request("Сколько проверок по статусам?")})

    assert result["strategy"] == "script"
    assert result["rows"]
    assert result["evidence"][0]["type"] == "script_template"
    assert llm.calls == ["summarize"]
    assert (
        result["acl_response"]["content"]["metrics"]["plan_source"]
        == "template_contract"
    )
    assert result["plan"]["template_key"] == "status_summary"
    assert "Статусы получены." in result["answer"]
    assert result["answer_source"] == "llm"


def test_template_selection_uses_plan_year_not_llm_choice(
    server, sample_graph_data
):
    llm = QueryPlanFakeLLM(
        plan=QueryPlan(
            metric="audit_count",
            dimensions=["status"],
            filters=[QueryFilter(field="year", value=2026)],
            reason="год в плане",
        ),
        answer="Статусы получены.",
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Покажи сводку по статусам проверок за 2026 год")}
    )

    assert result["status"] == "ok"
    assert result["strategy"] == "script"
    assert result["plan"]["template_key"] == "status_summary"
    assert result["plan"]["parameters"]["year"] == 2026
    assert "plan_sql" not in llm.calls


def test_template_uses_latest_year_when_plan_has_no_year(
    server, sample_graph_data
):
    llm = QueryPlanFakeLLM(
        plan=QueryPlan(
            metric="audit_count",
            dimensions=["status"],
            reason="год не назван",
        ),
        answer="Статусы получены.",
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Покажи сводку по статусам проверок")}
    )

    assert result["status"] == "ok"
    assert result["strategy"] == "script"
    assert result["plan"]["parameters"]["year"] == 2026


def test_incomplete_plan_is_completed_and_template_not_substituted(
    server, sample_graph_data
):
    """LLM не выбирает шаблон, а неполный план не подменяется статусами."""
    llm = QueryPlanFakeLLM(
        plan=QueryPlan(
            metric="audit_count",
            reason="LLM не заполнила dimensions/filters",
        ),
        answer="Готово.",
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {
            "acl_request": acl_request(
                "Сколько было закрыто проверок за последний год "
                "по каждому карману?"
            )
        }
    )

    assert result["status"] == "ok"
    assert result["strategy"] == "generated"
    assert result["plan"]["plan_source"] == "query_ir"
    assert result["plan"]["template_key"] == ""
    assert result["evidence"][0]["type"] == "sql_result"

    sql = result["acl_response"]["content"]["sql"]
    assert "p.title AS pocket" in sql
    assert "a.status = 'завершена'" in sql
    assert "max(p_last.pocket_year)" in sql.lower()
    assert result["plan"]["query_plan"]["dimensions"] == ["pocket"]


def test_plan_without_template_compiles_sql(server, sample_graph_data):
    llm = QueryPlanFakeLLM(
        plan=QueryPlan(
            metric="audit_count",
            filters=[QueryFilter(field="year", value=2026)],
            reason="обычный Query IR",
        ),
        answer="Найдена одна проверка.",
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Сколько проверок в 2026 году?")}
    )

    assert result["status"] == "ok"
    assert result["strategy"] == "generated"
    assert result["acl_response"]["content"]["metrics"]["plan_source"] == "query_ir"
    assert "plan_sql" not in llm.calls


def test_chart_mode_uses_previous_analytics_payload(server, sample_graph_data):
    conversation_id = "conv-chart-test"
    try:
        dialogue_store.append_turn(
            server,
            conversation_id=conversation_id,
            auditor_id="AUD-001",
            turn_id="turn-chart-1",
            user_text="Сколько закрыто проверок по каждому карману?",
            assistant_text="По карманам: ...",
            trace=[],
            payload={
                "rows": [
                    {"pocket": "2026. Ипотека", "cnt": 5},
                    {"pocket": "2026. Карты", "cnt": 7},
                ],
                "columns": ["pocket", "cnt"],
                "sql": "SELECT 1",
                "question": "Сколько закрыто проверок по каждому карману?",
            },
        )
        request = make_acl_message(
            performative="request",
            sender="orchestrator",
            receiver="analytics_agent",
            content={
                "question": "Построй диаграмму на основании этих данных",
                "auditor_id": "AUD-001",
                "analytics_mode": "chart",
            },
            conversation_id=conversation_id,
        )
        llm = ChartFakeLLM(
            ChartSpec(
                type="pie",
                title="Закрытые проверки по карманам",
                value_label="Проверок",
                data=[
                    ChartPoint(label="2026. Ипотека", value=5),
                    ChartPoint(label="2026. Карты", value=7),
                ],
            )
        )
        graph = build_analytics_graph(server, llm)

        result = graph.invoke({"acl_request": request.model_dump()})

        assert result["status"] == "ok"
        assert result["strategy"] == "chart"
        assert llm.calls == ["plan_chart"]
        chart = result["acl_response"]["content"]["chart"]
        assert chart["type"] == "pie"
        assert chart["title"] == "Закрытые проверки по карманам"
        assert [point["label"] for point in chart["data"]] == [
            "2026. Ипотека",
            "2026. Карты",
        ]
    finally:
        dialogue_store.delete_thread(
            server, conversation_id, auditor_id="AUD-001"
        )


def test_chart_hallucinated_data_falls_back_to_grounded_chart(
    server, sample_graph_data
):
    conversation_id = "conv-chart-fallback"
    try:
        dialogue_store.append_turn(
            server,
            conversation_id=conversation_id,
            auditor_id="AUD-001",
            turn_id="turn-chart-2",
            user_text="Сколько проверок по статусам?",
            assistant_text="Статусы",
            payload={
                "rows": [
                    {"status": "завершена", "cnt": 28},
                    {"status": "в работе", "cnt": 10},
                ],
                "columns": ["status", "cnt"],
                "sql": "SELECT 1",
                "question": "Сколько проверок по статусам?",
            },
        )
        request = make_acl_message(
            performative="request",
            sender="orchestrator",
            receiver="analytics_agent",
            content={
                "question": "Построй диаграмму на основании этих данных",
                "auditor_id": "AUD-001",
                "analytics_mode": "chart",
            },
            conversation_id=conversation_id,
        )
        llm = ChartFakeLLM(
            ChartSpec(
                type="pie",
                title="Придуманные данные",
                data=[
                    ChartPoint(label="не существует", value=999),
                    ChartPoint(label="тоже нет", value=1000),
                ],
            )
        )
        graph = build_analytics_graph(server, llm)

        result = graph.invoke({"acl_request": request.model_dump()})

        assert result["status"] == "ok"
        assert llm.calls == ["plan_chart"]
        chart = result["acl_response"]["content"]["chart"]
        assert chart["type"] == "bar"
        assert chart["value_field"] == "cnt"
        assert {point["label"] for point in chart["data"]} == {
            "завершена",
            "в работе",
        }
    finally:
        dialogue_store.delete_thread(
            server, conversation_id, auditor_id="AUD-001"
        )


def test_chart_mode_without_previous_data_is_honest(server, sample_graph_data):
    request = make_acl_message(
        performative="request",
        sender="orchestrator",
        receiver="analytics_agent",
        content={
            "question": "Построй диаграмму на основании этих данных",
            "auditor_id": "AUD-001",
            "analytics_mode": "chart",
        },
        conversation_id="conv-chart-empty",
    )
    graph = build_analytics_graph(server, FakeLLM())

    result = graph.invoke({"acl_request": request.model_dump()})

    assert result["status"] == "ok"
    assert result["strategy"] == "chart"
    assert "Нет предыдущего аналитического результата" in result["answer"]
    assert "chart" not in result["acl_response"]["content"]


def test_drilldown_by_audit_code(server, sample_graph_data):
    llm = FakeLLM()
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {
            "acl_request": acl_request(
                "Какие критические отклонения в AUD-2026-MORTGAGE-03?",
                mode="drilldown",
            )
        }
    )

    assert result["status"] == "ok"
    assert "AUD-2026-MORTGAGE-03" in result["answer"]
    assert {item["item_id"] for item in result["evidence"]} == {"ITM-T-01", "ITM-T-02"}
    assert llm.calls == []


def test_drilldown_is_formatted_by_llm(server, sample_graph_data):
    llm = FormattingFakeLLM("Найдено 2 пункта: 5.1 и 5.2.")
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {
            "acl_request": acl_request(
                "Какие критические отклонения в AUD-2026-MORTGAGE-03?",
                mode="drilldown",
            )
        }
    )

    assert result["answer"] == "Найдено 2 пункта: 5.1 и 5.2."
    assert result["answer_source"] == "llm"
    assert llm.calls == ["format_answer"]


def test_drilldown_falls_back_when_llm_loses_total(server, sample_graph_data):
    llm = FormattingFakeLLM("Найдено пунктов: 5.")
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {
            "acl_request": acl_request(
                "Какие критические отклонения в AUD-2026-MORTGAGE-03?",
                mode="drilldown",
            )
        }
    )

    assert result["answer_source"] == "agent"
    assert "найдено пунктов: 2" in result["answer"].lower()


def test_multi_tool_in_one_llm_call(server, sample_graph_data):
    llm = FakeLLM(
        tool_plan=ToolPlan(
            calls=[
                ToolCall(
                    name="get_act_items",
                    arguments={"audit_code": "AUD-2026-MORTGAGE-03"},
                ),
                ToolCall(name="search_acts", arguments={"query": "залог"}),
            ],
            reason="нужны пункты и похожие акты",
        )
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {
            "acl_request": acl_request(
                "Найди отклонения по AUD-2026-MORTGAGE-03 "
                "и похожие формулировки в других актах",
                mode="multi_tool",
            )
        }
    )

    assert result["strategy"] == "multi_tool"
    assert len(result["tool_calls"]) == 2
    assert llm.calls == ["plan_tools"]
    types = {item["type"] for item in result["evidence"]}
    assert "item" in types
    assert "act" in types or "tool" in types


def test_multi_tool_plan_is_truncated_to_limit(server, sample_graph_data):
    """7 инструментов в плане: выполняем только MAX_AGENT_ITERATIONS и помечаем это."""
    calls = [
        ToolCall(
            name="get_act_items",
            arguments={"audit_code": "AUD-2026-MORTGAGE-03"},
        )
    ] + [
        ToolCall(name="search_acts", arguments={"query": f"залог {index}"})
        for index in range(6)
    ]
    llm = FakeLLM(
        tool_plan=ToolPlan(calls=calls, reason="модель запросила слишком много")
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {
            "acl_request": acl_request(
                "Найди отклонения по AUD-2026-MORTGAGE-03 "
                "и похожие формулировки в других актах",
                mode="multi_tool",
            )
        }
    )

    limit = config.MAX_AGENT_ITERATIONS
    assert result["status"] == "ok"
    assert result["strategy"] == "multi_tool"
    assert len(result["tool_calls"]) == limit
    assert len(calls) == 7

    content = result["acl_response"]["content"]
    assert content["tool_calls_truncated"] is True
    assert content["tool_calls_requested"] == 7
    assert content["metrics"]["tool_calls_truncated"] is True
    assert content["metrics"]["tool_calls_requested"] == 7
    assert content["metrics"]["tool_calls"] == limit
    assert (
        f"Выполнены первые {limit} из 7 инструментов." in content["answer"]
    )
    assert content["answer"].rstrip().endswith("инструментов.")
    assert llm.calls == ["plan_tools"]


def test_multi_tool_is_formatted_by_llm(server, sample_graph_data):
    llm = FormattingFakeLLM(
        "Найдены пункты проверки и похожие формулировки в других актах.",
        tool_plan=ToolPlan(
            calls=[
                ToolCall(
                    name="get_act_items",
                    arguments={"audit_code": "AUD-2026-MORTGAGE-03"},
                ),
                ToolCall(name="search_acts", arguments={"query": "залог"}),
            ],
            reason="нужны пункты и похожие акты",
        ),
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {
            "acl_request": acl_request(
                "Найди отклонения по AUD-2026-MORTGAGE-03 "
                "и похожие формулировки в других актах",
                mode="multi_tool",
            )
        }
    )

    assert result["answer"] == (
        "Найдены пункты проверки и похожие формулировки в других актах."
    )
    assert result["answer_source"] == "llm"
    assert llm.calls == ["plan_tools", "format_answer"]
