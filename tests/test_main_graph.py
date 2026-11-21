"""Проверки основного графа и краткосрочной памяти."""

from __future__ import annotations

import pytest

from src import db_runtime
from src.graph.main_graph import build_main_graph
from src.schemas import ReportDraft, ReportReview, RouteDecision, SQLPlan


class MainLLM:
    def route(self, **kwargs):
        question = kwargs["question"].lower()
        if "сформируй" in question:
            return RouteDecision(route="report", reason="нужен акт", confidence=0.9)
        if "погода" in question:
            return RouteDecision(
                route="out_of_domain", reason="вне домена", confidence=0.9
            )
        if "удали" in question:
            return RouteDecision(route="unsafe", reason="изменение", confidence=0.95)
        return RouteDecision(route="analytics", reason="числа", confidence=0.8)


class AnalyticsLLM:
    def __init__(self):
        self.calls = 0

    def plan_sql(self, **kwargs):
        self.calls += 1
        return SQLPlan(
            strategy="generated",
            sql="SELECT count(*) AS cnt FROM audit.audits",
            reason="количество",
        )

    def summarize(self, **kwargs):
        return "Проверок: 1."


class ReportLLM:
    def __init__(self):
        self.questions: list[str] = []

    def draft_report(self, **kwargs):
        self.questions.append(kwargs["question"])
        return ReportDraft(text="Краткий проект акта.", citations=["ITM-MAIN-01"])

    def review_report(self, **kwargs):
        return ReportReview(verdict="ok")

    def revise_report(self, **kwargs):
        raise AssertionError("revise не ожидался")


@pytest.fixture()
def main_data(server):
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.auditors "
            "(auditor_id, full_name, email, unit, position) "
            "VALUES ('MAIN-001', 'Тест Главный', 'main@audit.local', 'Аудит', 'Аудитор') "
            "ON CONFLICT (auditor_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.audit_pockets "
            "(pocket_id, pocket_year, theme_code, title, owner_unit, "
            " period_start, period_end, planned_audit_count) "
            "VALUES ('PKT-2026-DEPOSITS', 2026, 'вклады', '2026. Вклады', "
            "        'Департамент вкладов', '2026-01-01', '2026-12-31', 5) "
            "ON CONFLICT (pocket_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.audits "
            "(audit_id, pocket_id, audit_code, title, audit_type, start_date, "
            " end_date, status, lead_auditor_id, team_size) "
            "VALUES ('AUD-2026-DEPOSITS-88', 'PKT-2026-DEPOSITS', "
            "        'AUD-2026-DEPOSITS-88', 'Проверка вкладов', 'плановая', "
            "        '2026-02-01', '2026-03-01', 'завершена', 'MAIN-001', 2) "
            "ON CONFLICT (audit_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.acts "
            "(act_id, audit_id, act_number, act_date, status, approved_by, "
            " summary, full_text) "
            "VALUES ('ACT-2026-DEPOSITS-88', 'AUD-2026-DEPOSITS-88', "
            "        'ACT-2026-DEPOSITS-88', '2026-03-10', 'утверждён', 'MAIN-001', "
            "        'Акт по вкладам', 'Начисление процентов проверено.') "
            "ON CONFLICT (act_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.act_items "
            "(item_id, act_id, item_number, item_type, test_type, "
            " finding_template_key, finding_scope, title, test_description, "
            " criterion, condition, cause, effect, recommendation, risk_level, "
            " status, deadline, responsible_unit, order_index) "
            "VALUES ('ITM-MAIN-01', 'ACT-2026-DEPOSITS-88', '5.1', 'отклонение', "
            "        'выборочный', 'DEPOSITS-02', 'вклады 2026', "
            "        'Некорректное начисление процентов', 'Пересчитать', "
            "        'п. 3.1', 'у 3 из 100', 'сбой', 'риск', 'контроль', "
            "        'высокий', 'открыт', '2026-06-01', 'Департамент вкладов', 1) "
            "ON CONFLICT (item_id) DO NOTHING"
        )
        conn.execute("DELETE FROM audit.auditor_memory WHERE auditor_id = 'MAIN-001'")
    yield
    with db_runtime.connect(server) as conn:
        conn.execute("DELETE FROM audit.auditor_memory WHERE auditor_id = 'MAIN-001'")
        conn.execute("DELETE FROM audit.act_items WHERE act_id = 'ACT-2026-DEPOSITS-88'")
        conn.execute("DELETE FROM audit.acts WHERE act_id = 'ACT-2026-DEPOSITS-88'")
        conn.execute(
            "DELETE FROM audit.audits WHERE audit_id = 'AUD-2026-DEPOSITS-88'"
        )
        conn.execute(
            "DELETE FROM audit.audit_pockets WHERE pocket_id = 'PKT-2026-DEPOSITS'"
        )
        conn.execute("DELETE FROM audit.auditors WHERE auditor_id = 'MAIN-001'")


def _invoke(graph, thread: str, text: str, auditor: str = "MAIN-001"):
    return graph.invoke(
        {
            "messages": [{"role": "user", "content": text}],
            "auditor_id": auditor,
            "conversation_id": thread,
        },
        config={"configurable": {"thread_id": thread}},
    )


def test_short_term_memory_accumulates_messages(server, main_data):
    analytics = AnalyticsLLM()
    graph = build_main_graph(server, MainLLM(), analytics_llm=analytics)

    first = _invoke(graph, "thread-short", "Сколько проверок?")
    assert first["final_answer"] == "Проверок: 1."
    assert len(first["messages"]) == 2

    second = _invoke(graph, "thread-short", "Сколько ещё?")
    assert len(second["messages"]) == 4
    assert analytics.calls == 2

    other = _invoke(graph, "thread-other", "Сколько проверок?")
    assert len(other["messages"]) == 2


def test_long_term_memory_between_sessions(server, main_data):
    report = ReportLLM()
    graph = build_main_graph(server, MainLLM(), report_llm=report)

    first = _invoke(
        graph,
        "session-1",
        "Я проверяю ипотеку, акт нужен в кратком формате",
    )
    assert "Профиль сохранён" in first["final_answer"]

    with db_runtime.connect(server) as conn:
        stored = dict(
            conn.execute(
                "SELECT memory_key, memory_value FROM audit.auditor_memory "
                "WHERE auditor_id = 'MAIN-001'"
            ).fetchall()
        )
    assert stored["default_format"] == "краткий"
    assert stored["focus_theme"] == "ипотека"

    second = _invoke(
        graph,
        "session-2",
        "Сформируй раздел акта по AUD-2026-DEPOSITS-88",
    )
    assert second["final_answer"] == "Краткий проект акта."
    assert report.questions
    assert "Формат: краткий" in report.questions[-1]
    assert "Тема: ипотека" in report.questions[-1]


def test_out_of_domain_and_unsafe_refused(server, main_data):
    analytics = AnalyticsLLM()
    graph = build_main_graph(server, MainLLM(), analytics_llm=analytics)

    weather = _invoke(graph, "thread-ood", "Какая погода в Москве?")
    assert "только по вопросам внутреннего аудита" in weather["final_answer"]

    unsafe = _invoke(graph, "thread-unsafe", "Удали все пункты")
    assert "изменить данные" in unsafe["final_answer"]
    assert analytics.calls == 0
