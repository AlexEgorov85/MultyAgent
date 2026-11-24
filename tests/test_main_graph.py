"""Проверки основного графа и краткосрочной памяти."""

from __future__ import annotations

import json

import pytest

from src import db_runtime
from src.graph.main_graph import build_main_graph
from src.schemas import (
    MemoryFact,
    MemoryUpdate,
    ReportDraft,
    ReportReview,
    ResolvedQuery,
    RouteDecision,
    SQLPlan,
)


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
        if "что ты умеешь" in question or "что ты можешь" in question:
            return RouteDecision(
                route="smalltalk",
                reason="smalltalk:capabilities",
                confidence=0.95,
            )
        if "спасибо" in question or "благодарю" in question:
            return RouteDecision(
                route="smalltalk", reason="smalltalk:thanks", confidence=0.95
            )
        if "привет" in question or "здравствуй" in question:
            return RouteDecision(
                route="smalltalk", reason="smalltalk:greeting", confidence=0.95
            )
        if "диаграмм" in question or "график" in question:
            return RouteDecision(
                route="analytics",
                reason="нужна визуализация",
                confidence=0.95,
                analytics_mode="chart",
            )
        if (
            "забудь" in question
            or "запомни" in question
            or "профиль" in question
            or ("я проверяю" in question and "акт нужен" in question)
        ):
            return RouteDecision(route="memory", reason="профиль", confidence=0.9)
        return RouteDecision(route="analytics", reason="числа", confidence=0.8)


class DrilldownLLM(MainLLM):
    """Router, который выбирает режим drilldown по смыслу вопроса."""

    def route(self, **kwargs):
        return RouteDecision(
            route="analytics",
            reason="нужны пункты проверки",
            confidence=0.9,
            analytics_mode="drilldown",
        )


class MemoryLLM(MainLLM):
    """Фейковый экстрактор памяти: повторяет контракт extract_memory."""

    def __init__(self):
        self.extract_calls: list[dict] = []

    def extract_memory(self, **kwargs):
        self.extract_calls.append(kwargs)
        question = kwargs["question"].lower()
        facts: list[MemoryFact] = []
        forget: list[str] = []
        if "забудь" in question or "сбрось" in question:
            forget = ["focus_theme", "default_format", "signature"]
        else:
            if "ипотек" in question:
                facts.append(MemoryFact(key="focus_theme", value="ипотека"))
            if "кратк" in question:
                facts.append(MemoryFact(key="default_format", value="краткий"))
            elif "подробн" in question:
                facts.append(MemoryFact(key="default_format", value="подробный"))
            if "подписывай" in question:
                facts.append(MemoryFact(key="signature", value="Иванов И.И."))
        return MemoryUpdate(facts=facts, forget=forget, reason="тест")


class AnalyticsLLM:
    def __init__(self):
        self.calls = 0

    def plan_sql(self, **kwargs):
        self.calls += 1
        question = kwargs["question"].lower()
        if "ипотек" in question:
            sql = (
                "SELECT count(*) AS cnt FROM audit.audits AS a "
                "JOIN audit.audit_pockets AS p ON a.pocket_id = p.pocket_id "
                "WHERE p.theme_code = 'ипотека'"
            )
        else:
            sql = "SELECT count(*) AS cnt FROM audit.audits"
        return SQLPlan(strategy="generated", sql=sql, reason="количество")

    def summarize(self, **kwargs):
        return "Проверок: 1."


class ReportLLM:
    def __init__(self):
        self.questions: list[str] = []
        self.formats: list[str] = []
        self.profiles: list[str] = []

    def draft_report(self, **kwargs):
        self.questions.append(kwargs["question"])
        self.formats.append(kwargs.get("report_format", "подробный"))
        self.profiles.append(kwargs.get("profile_text", ""))
        # Черновик должен содержать обязательные разделы, иначе Inspector
        # отправит его на доработку (revise), а этот фейк её не поддерживает.
        if kwargs.get("report_format") == "краткий":
            return ReportDraft(
                text=(
                    "Вводная часть: проверка AUD-2026-DEPOSITS-88.\n"
                    "Выявленные отклонения и проблемы: начисление процентов.\n"
                    "Рекомендации: автоматизировать контроль.\n"
                    "Сроки устранения: 2026-06-01."
                ),
                citations=["ITM-MAIN-01"],
            )
        return ReportDraft(
            text=(
                "Вводная часть. Проверка AUD-2026-DEPOSITS-88 проведена в "
                "период с 2026-02-01 по 2026-03-01, руководитель — MAIN-001, "
                "команда из двух аудиторов. Предмет проверки — начисление "
                "процентов по вкладам.\n"
                "Выявленные отклонения и проблемы: некорректное начисление "
                "процентов по трём договорам из ста проверенных; отклонение "
                "зафиксировано в пункте ITM-MAIN-01 и требует устранения.\n"
                "Рекомендации: автоматизировать контроль начисления процентов, "
                "пересчитать проценты по затронутым договорам и уведомить "
                "владельцев процесса о результатах пересчёта.\n"
                "Сроки устранения: 2026-06-01 согласно пункту ITM-MAIN-01; "
                "ответственное подразделение — Департамент вкладов."
            ),
            citations=["ITM-MAIN-01"],
        )

    def review_report(self, **kwargs):
        return ReportReview(verdict="ok")

    def revise_report(self, **kwargs):
        raise AssertionError("revise не ожидался")


@pytest.fixture(autouse=True)
def acl_log_path(tmp_path, monkeypatch):
    path = tmp_path / "acl.jsonl"
    monkeypatch.setenv("ACL_LOG_PATH", str(path))
    return path


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
        conn.execute(
            "DELETE FROM audit.audit_pockets WHERE pocket_id = 'PKT-2026-MORTGAGE'"
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
    assert "cnt" not in first["final_answer"]
    assert len(first["messages"]) == 2

    second = _invoke(graph, "thread-short", "Сколько ещё?")
    assert len(second["messages"]) == 4
    assert analytics.calls == 2

    other = _invoke(graph, "thread-other", "Сколько проверок?")
    assert len(other["messages"]) == 2


def test_router_mode_is_passed_to_analytics(server, main_data):
    graph = build_main_graph(server, DrilldownLLM(), analytics_llm=AnalyticsLLM())

    result = _invoke(
        graph, "thread-drilldown", "Какие пункты по AUD-2026-DEPOSITS-88?"
    )

    assert result["route"] == "analytics"
    assert result["analytics_mode"] == "drilldown"
    assert result["final_answer"]
    assert any(
        item.get("item_id") == "ITM-MAIN-01" for item in result["evidence"]
    )


def test_router_selects_chart_mode(server, main_data):
    graph = build_main_graph(server, MainLLM(), analytics_llm=AnalyticsLLM())

    result = _invoke(
        graph,
        "thread-chart-mode",
        "Построй диаграмму на основании этих данных",
    )

    assert result["route"] == "analytics"
    assert result["analytics_mode"] == "chart"
    assert "Нет предыдущего аналитического результата" in result["final_answer"]


def test_long_term_memory_between_sessions(server, main_data):
    report = ReportLLM()
    graph = build_main_graph(server, MemoryLLM(), report_llm=report)

    first = _invoke(
        graph,
        "session-1",
        "Я проверяю ипотеку, акт нужен в кратком формате",
    )
    assert first["route"] == "memory"
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
    assert "Вводная часть" in second["final_answer"]
    assert "Сроки устранения" in second["final_answer"]
    assert report.questions
    assert report.formats[-1] == "краткий"
    assert "Формат: краткий" in report.profiles[-1]
    assert "Тема: ипотека" in report.profiles[-1]
    assert report.formats[-1] == "краткий"


def test_mixed_question_is_not_hijacked_by_memory(server, main_data):
    """«Я проверяю ипотеку, сколько проверок?» — аналитика, не память."""
    llm = MemoryLLM()
    analytics = AnalyticsLLM()
    graph = build_main_graph(server, llm, analytics_llm=analytics)

    result = _invoke(
        graph, "thread-mixed", "Я проверяю ипотеку, сколько проверок?"
    )

    assert result["route"] == "analytics"
    assert result["final_answer"] == "Проверок: 1."
    assert llm.extract_calls == []
    with db_runtime.connect(server) as conn:
        count = conn.execute(
            "SELECT count(*) FROM audit.auditor_memory "
            "WHERE auditor_id = 'MAIN-001'"
        ).fetchone()[0]
    assert count == 0


def test_memory_forget_and_profile_query(server, main_data):
    graph = build_main_graph(server, MemoryLLM())

    saved = _invoke(
        graph,
        "session-forget-1",
        "Я проверяю ипотеку, акт нужен в кратком формате",
    )
    assert "Профиль сохранён" in saved["final_answer"]

    shown = _invoke(graph, "session-forget-2", "Какой у меня профиль?")
    assert shown["route"] == "memory"
    assert "Ваш профиль" in shown["final_answer"]
    assert "краткий" in shown["final_answer"]

    forgot = _invoke(graph, "session-forget-3", "Забудь мой профиль")
    assert forgot["route"] == "memory"
    assert "Профиль сброшен" in forgot["final_answer"]
    with db_runtime.connect(server) as conn:
        count = conn.execute(
            "SELECT count(*) FROM audit.auditor_memory "
            "WHERE auditor_id = 'MAIN-001'"
        ).fetchone()[0]
    assert count == 0


def test_memory_is_not_inferred_without_llm(server, main_data):
    """Без extract_memory профиль не обновляется: keyword-fallback удалён."""

    class BrokenExtractLLM(MainLLM):
        def extract_memory(self, **kwargs):
            raise RuntimeError("LLM недоступна")

    for llm in (MainLLM(), BrokenExtractLLM()):
        graph = build_main_graph(server, llm)
        result = _invoke(
            graph,
            "thread-memory-fallback",
            "Я проверяю ипотеку, акт нужен в кратком формате",
        )
        assert result["route"] == "memory"
        assert "Профиль сохранён" not in result["final_answer"]
        with db_runtime.connect(server) as conn:
            count = conn.execute(
                "SELECT count(*) FROM audit.auditor_memory "
                "WHERE auditor_id = 'MAIN-001'"
            ).fetchone()[0]
            assert count == 0
            conn.execute(
                "DELETE FROM audit.auditor_memory WHERE auditor_id = 'MAIN-001'"
            )


def test_memory_without_auditor_id_is_graceful(server, main_data):
    graph = build_main_graph(server, MemoryLLM())

    result = graph.invoke(
        {
            "messages": [
                {"role": "user", "content": "Запомни: я проверяю ипотеку"}
            ],
            "auditor_id": "",
            "conversation_id": "thread-no-auditor",
        },
        config={"configurable": {"thread_id": "thread-no-auditor"}},
    )

    assert result["route"] == "memory"
    assert "не задан идентификатор" in result["final_answer"]


def test_report_format_and_signature_follow_profile(server, main_data):
    report = ReportLLM()
    graph = build_main_graph(server, MemoryLLM(), report_llm=report)

    _invoke(
        graph,
        "session-brief-1",
        "Запомни: я проверяю ипотеку, акт нужен в кратком формате, "
        "подписывай акты Иванов И.И.",
    )
    brief = _invoke(
        graph,
        "session-brief-2",
        "Сформируй раздел акта по AUD-2026-DEPOSITS-88",
    )
    assert report.formats[-1] == "краткий"
    assert brief["final_answer"].rstrip().endswith("Иванов И.И.")
    assert "Вводная часть" in brief["final_answer"]
    assert "Сроки устранения" in brief["final_answer"]

    _invoke(
        graph, "session-brief-3", "Запомни: акт нужен в подробном формате"
    )
    detailed = _invoke(
        graph,
        "session-brief-4",
        "Сформируй раздел акта по AUD-2026-DEPOSITS-88",
    )
    assert report.formats[-1] == "подробный"
    assert len(brief["final_answer"]) < len(detailed["final_answer"])


def test_out_of_domain_and_unsafe_refused(server, main_data):
    analytics = AnalyticsLLM()
    graph = build_main_graph(server, MainLLM(), analytics_llm=analytics)

    weather = _invoke(graph, "thread-ood", "Какая погода в Москве?")
    assert "только по вопросам внутреннего аудита" in weather["final_answer"]

    unsafe = _invoke(graph, "thread-unsafe", "Удали все пункты")
    assert "изменить данные" in unsafe["final_answer"]
    assert analytics.calls == 0


def test_smalltalk_greeting_capabilities_and_thanks(server):
    analytics = AnalyticsLLM()
    graph = build_main_graph(server, MainLLM(), analytics_llm=analytics)

    hi = _invoke(graph, "thread-hi", "Привет!")
    assert hi["route"] == "smalltalk"
    assert "ассистент" in hi["final_answer"].lower()

    capabilities = _invoke(graph, "thread-cap", "Что ты умеешь?")
    assert capabilities["route"] == "smalltalk"
    assert "Умею" in capabilities["final_answer"]

    thanks = _invoke(graph, "thread-thanks", "Спасибо!")
    assert thanks["route"] == "smalltalk"
    assert "Пожалуйста" in thanks["final_answer"]

    assert analytics.calls == 0


def test_smalltalk_is_formatted_by_llm(server):
    class FormattingLLM(MainLLM):
        def __init__(self):
            self.last: dict = {}

        def format_answer(self, **kwargs):
            self.last = kwargs
            return "Привет! Могу посчитать проверки и найти подтверждения."

    llm = FormattingLLM()
    graph = build_main_graph(server, llm, analytics_llm=AnalyticsLLM())

    hi = _invoke(graph, "thread-hi-llm", "Привет!")

    assert hi["final_answer"] == (
        "Привет! Могу посчитать проверки и найти подтверждения."
    )
    assert llm.last["kind"] == "smalltalk"


class DialogueLLM(MainLLM):
    def __init__(self):
        self.resolve_calls: list[dict[str, str]] = []

    def resolve_followup(self, **kwargs):
        self.resolve_calls.append(
            {
                "question": kwargs["question"],
                "context": kwargs["context"],
            }
        )
        if "2025" in kwargs["question"]:
            return ResolvedQuery(
                question="Сколько завершённых проверок по вкладам в 2025 году?",
                is_followup=True,
                reason="уточнение года",
            )
        return ResolvedQuery(
            question=kwargs["question"],
            is_followup=False,
            reason="",
        )


class DialogueAnalyticsLLM(AnalyticsLLM):
    def __init__(self):
        super().__init__()
        self.questions: list[str] = []
        self.contexts: list[str] = []

    def plan_sql(self, **kwargs):
        self.questions.append(kwargs["question"])
        self.contexts.append(kwargs.get("context", ""))
        question = kwargs["question"].lower()
        year = "2025" if "2025" in question else "2026"
        theme = (
            "ипотека"
            if "ипотек" in question
            else "вклады"
            if "вклад" in question
            else "карты"
        )
        status = " AND a.status = 'завершена'" if "заверш" in question else ""
        return SQLPlan(
            strategy="generated",
            sql=(
                "SELECT count(*) AS cnt FROM audit.audits AS a "
                "JOIN audit.audit_pockets AS p ON a.pocket_id = p.pocket_id "
                f"WHERE p.pocket_year = {year} AND p.theme_code = '{theme}'"
                f"{status}"
            ),
            reason="количество",
        )


def test_followup_uses_previous_thread_history(server, main_data):
    resolver = DialogueLLM()
    analytics = DialogueAnalyticsLLM()
    graph = build_main_graph(server, resolver, analytics_llm=analytics)

    _invoke(graph, "thread-dialogue", "Сколько проверок по вкладам в 2026 году?")
    second = _invoke(graph, "thread-dialogue", "А за 2025 год?")

    assert resolver.resolve_calls
    assert resolver.resolve_calls[-1]["question"] == "А за 2025 год?"
    assert "2026" in resolver.resolve_calls[-1]["context"]
    assert "2025" in analytics.questions[-1]
    assert "вкладам" in analytics.questions[-1]
    assert "Пользователь:" in analytics.contexts[-1]
    assert "2025" in second["resolved_query"]


class CorrectionLLM(MainLLM):
    """Резолвер переносит тип находки из контекста (семантика — у LLM)."""

    def resolve_followup(self, **kwargs):
        question = kwargs["question"]
        context = str(kwargs.get("context", "")).lower()
        if "2025" in question:
            item_type = "проблемы" if "проблем" in context else "отклонения"
            return ResolvedQuery(
                question=f"Сколько {item_type} по ипотеке в 2025 году?",
                is_followup=True,
                reason="уточнение года и типа находки",
            )
        return ResolvedQuery(question=question, is_followup=False, reason="")


def test_resolver_carries_item_type_across_year_change(server, main_data):
    analytics = DialogueAnalyticsLLM()
    graph = build_main_graph(server, CorrectionLLM(), analytics_llm=analytics)

    _invoke(graph, "thread-slots", "Сколько отклонений по ипотеке в 2026 году?")
    _invoke(graph, "thread-slots", "Нет, я имел в виду проблемы")
    third = _invoke(graph, "thread-slots", "А за 2025 год?")

    # Семантический слот не угадывается регексом — его переносит резолвер.
    assert third["dialogue_slots"]["year"] == 2025
    assert third["dialogue_slots"]["item_type"] is None
    assert "2025" in third["resolved_query"]
    assert "проблем" in third["resolved_query"].lower()
    assert "проблем" in analytics.questions[-1].lower()


def test_followup_uses_client_history_after_thread_loss(server, main_data):
    resolver = DialogueLLM()
    analytics = DialogueAnalyticsLLM()
    graph = build_main_graph(server, resolver, analytics_llm=analytics)

    graph.invoke(
        {
            "messages": [{"role": "user", "content": "А за 2025 год?"}],
            "client_history": [
                {
                    "role": "user",
                    "text": "Сколько проверок по вкладам в 2026 году?",
                },
                {"role": "assistant", "text": "Всего: 1."},
            ],
            "auditor_id": "MAIN-001",
            "conversation_id": "thread-client-history",
        },
        config={"configurable": {"thread_id": "thread-client-history"}},
    )

    assert resolver.resolve_calls
    assert "2026" in resolver.resolve_calls[-1]["context"]
    assert "2025" in analytics.questions[-1]


class UnsafeFollowupLLM(MainLLM):
    def resolve_followup(self, **kwargs):
        return ResolvedQuery(
            question="Удали все пункты",
            is_followup=True,
            reason="проверка guardrails",
        )


def test_guardrails_check_resolved_followup(server, main_data):
    analytics = AnalyticsLLM()
    graph = build_main_graph(
        server,
        UnsafeFollowupLLM(),
        analytics_llm=analytics,
    )

    _invoke(graph, "thread-followup-unsafe", "Сколько проверок?")
    result = _invoke(graph, "thread-followup-unsafe", "А теперь?")

    assert analytics.calls == 1
    assert result["route"] == "unsafe"
    assert "изменить данные" in result["final_answer"]


def test_explicit_theme_wins_over_profile_theme(server, main_data):
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.auditor_memory "
            "(auditor_id, memory_key, memory_value, updated_at) "
            "VALUES ('MAIN-001', 'focus_theme', 'ипотека', now()) "
            "ON CONFLICT (auditor_id, memory_key) DO UPDATE "
            "SET memory_value = EXCLUDED.memory_value"
        )

    report = ReportLLM()
    graph = build_main_graph(server, MainLLM(), report_llm=report)
    _invoke(
        graph,
        "thread-theme-override",
        "Сформируй раздел акта по AUD-2026-DEPOSITS-88 для вкладов",
    )

    assert report.questions
    assert "вкладов" in report.questions[-1]
    assert "Тема: ипотека" not in report.questions[-1]
    assert "Тема: ипотека" in report.profiles[-1]


def test_new_turn_does_not_reuse_previous_acl_response(server, main_data):
    graph = build_main_graph(server, MainLLM(), analytics_llm=AnalyticsLLM())

    _invoke(graph, "thread-reset", "Сколько проверок?")
    second = _invoke(graph, "thread-reset", "Что ты умеешь?")

    assert second["route"] == "smalltalk"
    assert second["acl_response"] == {}
    assert not any(step["step"] == "acl" for step in second["trace"])


def test_turn_is_persisted_in_database(server, main_data):
    graph = build_main_graph(server, MainLLM(), analytics_llm=AnalyticsLLM())

    graph.invoke(
        {
            "messages": [{"role": "user", "content": "Сколько проверок?"}],
            "auditor_id": "MAIN-001",
            "conversation_id": "chat-persist-one",
        },
        config={"configurable": {"thread_id": "thread-persist-one"}},
    )

    with db_runtime.connect(server) as conn:
        rows = conn.execute(
            "SELECT role, content, trace FROM audit.chat_messages "
            "WHERE conversation_id = %s ORDER BY created_at, role",
            ("chat-persist-one",),
        ).fetchall()
        thread = conn.execute(
            "SELECT title FROM audit.chat_threads "
            "WHERE conversation_id = %s",
            ("chat-persist-one",),
        ).fetchone()

    assert [row[0] for row in rows] == ["user", "assistant"]
    assert rows[0][1] == "Сколько проверок?"
    assert rows[1][1]
    assert rows[1][2] is not None
    assert thread and thread[0] == "Сколько проверок?"


def test_history_from_db_survives_new_thread(server, main_data):
    first_resolver = DialogueLLM()
    first_analytics = DialogueAnalyticsLLM()
    first_graph = build_main_graph(
        server,
        first_resolver,
        analytics_llm=first_analytics,
    )
    first_graph.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "Сколько проверок по вкладам в 2026 году?",
                }
            ],
            "auditor_id": "MAIN-001",
            "conversation_id": "chat-persist-restart",
        },
        config={"configurable": {"thread_id": "thread-persist-old"}},
    )

    resolver = DialogueLLM()
    analytics = DialogueAnalyticsLLM()
    second_graph = build_main_graph(
        server,
        resolver,
        analytics_llm=analytics,
    )
    second_graph.invoke(
        {
            "messages": [{"role": "user", "content": "А за 2025 год?"}],
            "auditor_id": "MAIN-001",
            "conversation_id": "chat-persist-restart",
        },
        config={"configurable": {"thread_id": "thread-persist-new"}},
    )

    assert resolver.resolve_calls
    assert "2026" in resolver.resolve_calls[-1]["context"]
    assert "2025" in analytics.questions[-1]
    assert "вкладам" in analytics.questions[-1]


def test_acl_exchange_is_logged_and_write_error_is_safe(
    server, main_data, acl_log_path, monkeypatch
):
    graph = build_main_graph(server, MainLLM(), analytics_llm=AnalyticsLLM())

    result = _invoke(graph, "thread-acl-log", "Сколько проверок?")
    assert result["final_answer"] == "Проверок: 1."

    messages = [
        json.loads(line)
        for line in acl_log_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(messages) == 2
    request, response = messages
    assert request["performative"] == "request"
    assert request["receiver"] == "analytics_agent"
    assert request["conversation_id"] == "thread-acl-log"
    assert response["in_reply_to"] == request["reply_with"]
    assert response["conversation_id"] == request["conversation_id"]

    def broken_append(*args, **kwargs):
        raise OSError("журнал недоступен")

    monkeypatch.setattr("src.graph.main_graph.append_acl_log", broken_append)

    failed = _invoke(graph, "thread-acl-log-fail", "Сколько проверок ещё?")
    assert failed["final_answer"] == "Проверок: 1."
    assert failed["route"] == "analytics"
    assert len(acl_log_path.read_text(encoding="utf-8").splitlines()) == 2
