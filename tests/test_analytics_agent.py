"""Проверки спецификации analytics-agent на fake-LLM."""

from __future__ import annotations

import pytest

from src.acl import make_acl_message
from src import db_runtime
from src.graph.analytics_graph import build_analytics_graph
from src.schemas import SQLPlan, ToolCall, ToolPlan


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


def acl_request(question: str) -> dict:
    return make_acl_message(
        performative="request",
        sender="orchestrator",
        receiver="analytics_agent",
        content={"question": question, "auditor_id": "AUD-001"},
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
    yield
    with db_runtime.connect(server) as conn:
        conn.execute("DELETE FROM audit.act_items WHERE act_id = 'ACT-2026-MORTGAGE-03'")
        conn.execute("DELETE FROM audit.acts WHERE act_id = 'ACT-2026-MORTGAGE-03'")
        conn.execute("DELETE FROM audit.audits WHERE audit_id = 'AUD-2026-MORTGAGE-03'")
        conn.execute("DELETE FROM audit.audit_pockets WHERE pocket_id = 'PKT-2026-MORTGAGE'")
        conn.execute("DELETE FROM audit.auditors WHERE auditor_id = 'AN-001'")
        conn.execute("DELETE FROM audit.script_templates WHERE template_id = 'TPL-AN'")


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

    result = graph.invoke({"acl_request": acl_request("Сколько проверок по статусам?")})

    assert result["status"] == "ok"
    assert "Результат" in result["answer"] or "cnt" in result["answer"]
    assert result["rows"]
    assert result["acl_response"]["performative"] == "inform"
    assert result["acl_response"]["content"]["sql"].upper().count("LIMIT") == 1
    assert result["evidence"][0]["type"] == "sql_result"


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


def test_script_template_strategy(server, sample_graph_data):
    llm = FakeLLM(
        plans=[
            SQLPlan(
                strategy="script",
                template_key="test_status",
                parameters={},
                reason="есть готовый шаблон",
            )
        ],
        answer="Статусы получены.",
    )
    graph = build_analytics_graph(server, llm)

    result = graph.invoke({"acl_request": acl_request("Покажи статусы проверок")})

    assert result["strategy"] == "script"
    assert result["rows"]
    assert result["evidence"][0]["type"] == "script_template"
    assert llm.calls == ["plan_sql"]


def test_drilldown_by_audit_code(server, sample_graph_data):
    llm = FakeLLM()
    graph = build_analytics_graph(server, llm)

    result = graph.invoke(
        {
            "acl_request": acl_request(
                "Какие критические отклонения в AUD-2026-MORTGAGE-03?"
            )
        }
    )

    assert result["status"] == "ok"
    assert "AUD-2026-MORTGAGE-03" in result["answer"]
    assert {item["item_id"] for item in result["evidence"]} == {"ITM-T-01", "ITM-T-02"}
    assert llm.calls == []


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
                "и похожие формулировки в других актах"
            )
        }
    )

    assert result["strategy"] == "multi_tool"
    assert len(result["tool_calls"]) == 2
    assert llm.calls == ["plan_tools"]
    types = {item["type"] for item in result["evidence"]}
    assert "item" in types
    assert "act" in types or "tool" in types
