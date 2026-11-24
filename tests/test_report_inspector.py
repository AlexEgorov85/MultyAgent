"""Проверки спецификации report-inspector."""

from __future__ import annotations

import pytest

from src import db_runtime
from src.acl import make_acl_message
from src.graph.report_graph import build_report_graph
from src.schemas import ReportDraft, ReportReview


class FakeReportLLM:
    def __init__(
        self,
        *,
        drafts: list[ReportDraft] | None = None,
        reviews: list[ReportReview] | None = None,
        revisions: list[ReportDraft] | None = None,
    ) -> None:
        self.drafts = list(drafts or [])
        self.reviews = list(reviews or [])
        self.revisions = list(revisions or [])
        self.calls: list[str] = []

    def draft_report(self, **kwargs):
        self.calls.append("draft")
        return self.drafts.pop(0)

    def review_report(self, **kwargs):
        self.calls.append("review")
        return self.reviews.pop(0)

    def revise_report(self, **kwargs):
        self.calls.append("revise")
        return self.revisions.pop(0)


class RecordingReportLLM(FakeReportLLM):
    """Запоминает параметры вызовов, чтобы проверить проводку профиля."""

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.draft_kwargs: list[dict] = []
        self.revise_kwargs: list[dict] = []

    def draft_report(self, **kwargs):
        self.draft_kwargs.append(kwargs)
        return super().draft_report(**kwargs)

    def revise_report(self, **kwargs):
        self.revise_kwargs.append(kwargs)
        return super().revise_report(**kwargs)


def acl_request(question: str, **extra) -> dict:
    return make_acl_message(
        performative="request",
        sender="orchestrator",
        receiver="report_agent",
        content={"question": question, "auditor_id": "AUD-001", **extra},
        conversation_id="conv-report-001",
    ).model_dump()


def complete_report(citation: str = "") -> str:
    """Черновик со всеми обязательными разделами."""
    source = f" Источник: {citation}." if citation else ""
    return (
        "Вводная часть. Проверка AUD-2026-DEPOSITS-77.\n"
        "Выявленные отклонения и проблемы: некорректное начисление процентов.\n"
        "Рекомендации: автоматизировать контроль.\n"
        "Сроки устранения: 2026-06-01."
        + source
    )


@pytest.fixture()
def report_data(server):
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.auditors "
            "(auditor_id, full_name, email, unit, position) "
            "VALUES ('REP-001', 'Тест Отчёт', 'rep@audit.local', 'Аудит', 'Аудитор') "
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
            "VALUES ('AUD-2026-DEPOSITS-77', 'PKT-2026-DEPOSITS', "
            "        'AUD-2026-DEPOSITS-77', 'Проверка вкладов', 'плановая', "
            "        '2026-02-01', '2026-03-01', 'завершена', 'REP-001', 2) "
            "ON CONFLICT (audit_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.acts "
            "(act_id, audit_id, act_number, act_date, status, approved_by, "
            " summary, full_text) "
            "VALUES ('ACT-2026-DEPOSITS-77', 'AUD-2026-DEPOSITS-77', "
            "        'ACT-2026-DEPOSITS-77', '2026-03-10', 'утверждён', 'REP-001', "
            "        'Акт по вкладам', 'Начисление процентов проверено.') "
            "ON CONFLICT (act_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.act_items "
            "(item_id, act_id, item_number, item_type, test_type, "
            " finding_template_key, finding_scope, title, test_description, "
            " criterion, condition, cause, effect, recommendation, risk_level, "
            " status, deadline, responsible_unit, order_index) "
            "VALUES ('ITM-REP-01', 'ACT-2026-DEPOSITS-77', '5.1', 'отклонение', "
            "        'выборочный', 'DEPOSITS-02', 'вклады 2026', "
            "        'Некорректное начисление процентов', 'Пересчитать проценты', "
            "        'п. 3.1', 'у 3 из 100', 'сбой расчёта', 'риск потерь', "
            "        'автоматизировать контроль', 'высокий', 'открыт', "
            "        '2026-06-01', 'Департамент вкладов', 1) "
            "ON CONFLICT (item_id) DO NOTHING"
        )
    yield
    with db_runtime.connect(server) as conn:
        conn.execute("DELETE FROM audit.act_items WHERE act_id = 'ACT-2026-DEPOSITS-77'")
        conn.execute("DELETE FROM audit.acts WHERE act_id = 'ACT-2026-DEPOSITS-77'")
        conn.execute(
            "DELETE FROM audit.audits WHERE audit_id = 'AUD-2026-DEPOSITS-77'"
        )
        conn.execute(
            "DELETE FROM audit.audit_pockets WHERE pocket_id = 'PKT-2026-DEPOSITS'"
        )
        conn.execute("DELETE FROM audit.auditors WHERE auditor_id = 'REP-001'")


def test_valid_draft_passes_inspector(server, report_data):
    llm = FakeReportLLM(
        drafts=[
            ReportDraft(
                text=(
                    "Вводная часть. Проверка AUD-2026-DEPOSITS-77.\n"
                    "Отклонение: некорректное начисление процентов.\n"
                    "Рекомендация: автоматизировать контроль.\n"
                    "Срок: 2026-06-01."
                ),
                citations=["ITM-REP-01"],
            )
        ],
        reviews=[ReportReview(verdict="ok")],
    )
    graph = build_report_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Сформируй раздел акта по AUD-2026-DEPOSITS-77")}
    )

    assert result["status"] == "ok", result.get("error")
    content = result["acl_response"]["content"]
    assert content["citations"] == ["ITM-REP-01", "AUD-2026-DEPOSITS-77"]
    assert llm.calls == ["draft", "review"]


def test_fabricated_citation_is_revised(server, report_data):
    llm = FakeReportLLM(
        drafts=[ReportDraft(text="Черновик.", citations=["FAKE-ID"])],
        reviews=[ReportReview(verdict="ok"), ReportReview(verdict="ok")],
        revisions=[
            ReportDraft(
                text=complete_report("ITM-REP-01"),
                citations=["ITM-REP-01"],
            )
        ],
    )
    graph = build_report_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Сформируй раздел акта по AUD-2026-DEPOSITS-77")}
    )

    assert result["iterations"] == 1
    assert result["citations"] == ["ITM-REP-01", "AUD-2026-DEPOSITS-77"]
    assert llm.calls.count("revise") == 1


def test_revision_limit_marks_draft(server, report_data):
    llm = FakeReportLLM(
        drafts=[ReportDraft(text="Плохой черновик.", citations=["ITM-REP-01"])],
        reviews=[
            ReportReview(verdict="revise", issues=["нет подтверждения"]),
            ReportReview(verdict="revise", issues=["нет подтверждения"]),
            ReportReview(verdict="revise", issues=["нет подтверждения"]),
        ],
        revisions=[
            ReportDraft(text="Всё ещё плохо.", citations=["ITM-REP-01"]),
            ReportDraft(text="Совсем плохо.", citations=["ITM-REP-01"]),
        ],
    )
    graph = build_report_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Сформируй раздел акта по AUD-2026-DEPOSITS-77")}
    )

    assert result["iterations"] == 2
    assert "Требует проверки" in result["acl_response"]["content"]["draft"]


def test_no_audit_code_fails_without_llm(server, report_data):
    llm = FakeReportLLM()
    graph = build_report_graph(server, llm)

    result = graph.invoke({"acl_request": acl_request("Сформируй раздел акта")})

    assert result["status"] == "failed"
    assert result["acl_response"]["performative"] == "failure"
    assert llm.calls == []


def test_missing_audit_fails_without_llm(server, report_data):
    llm = FakeReportLLM()
    graph = build_report_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Сформируй раздел акта по AUD-2026-DEPOSITS-99")}
    )

    assert result["status"] == "failed"
    assert "не найдена" in result["error"]
    assert llm.calls == []


def test_draft_does_not_write_to_database(server, report_data):
    with db_runtime.connect(server) as conn:
        before = conn.execute(
            "SELECT full_text FROM audit.acts WHERE act_id = 'ACT-2026-DEPOSITS-77'"
        ).fetchone()[0]
    llm = FakeReportLLM(
        drafts=[
            ReportDraft(
                text=complete_report("ITM-REP-01"),
                citations=["ITM-REP-01"],
            )
        ],
        reviews=[ReportReview(verdict="ok")],
    )
    graph = build_report_graph(server, llm)
    graph.invoke(
        {"acl_request": acl_request("Сформируй раздел акта по AUD-2026-DEPOSITS-77")}
    )
    with db_runtime.connect(server) as conn:
        after = conn.execute(
            "SELECT full_text FROM audit.acts WHERE act_id = 'ACT-2026-DEPOSITS-77'"
        ).fetchone()[0]
    assert before == after


def test_citations_extracted_from_text_when_declared_empty(server, report_data):
    llm = FakeReportLLM(
        drafts=[ReportDraft(text=complete_report("ITM-REP-01"), citations=[])],
        reviews=[ReportReview(verdict="ok")],
    )
    graph = build_report_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Сформируй раздел акта по AUD-2026-DEPOSITS-77")}
    )

    assert result["status"] == "ok", result.get("error")
    content = result["acl_response"]["content"]
    assert "ITM-REP-01" in content["citations"]
    assert "AUD-2026-DEPOSITS-77" in content["citations"]
    assert "нет ссылок" not in content["draft"].lower()
    assert llm.calls == ["draft", "review"]


def test_revision_preserves_citations_when_model_returns_none(server, report_data):
    llm = FakeReportLLM(
        drafts=[
            ReportDraft(
                text=complete_report("ITM-REP-01"),
                citations=["ITM-REP-01"],
            )
        ],
        reviews=[
            ReportReview(verdict="revise", issues=["уточнить формулировку"]),
            ReportReview(verdict="ok"),
        ],
        revisions=[ReportDraft(text=complete_report(), citations=[])],
    )
    graph = build_report_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Сформируй раздел акта по AUD-2026-DEPOSITS-77")}
    )

    assert result["status"] == "ok", result.get("error")
    assert result["iterations"] == 1
    assert "ITM-REP-01" in result["citations"]
    assert "нет ссылок" not in result["acl_response"]["content"]["draft"].lower()
    assert llm.calls.count("revise") == 1


def test_fabricated_id_in_text_is_discarded(server, report_data):
    llm = FakeReportLLM(
        drafts=[ReportDraft(text=complete_report("ITM-FAKE-99"), citations=[])],
        reviews=[ReportReview(verdict="ok"), ReportReview(verdict="ok")],
        revisions=[ReportDraft(text=complete_report("ITM-REP-01"), citations=[])],
    )
    graph = build_report_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Сформируй раздел акта по AUD-2026-DEPOSITS-77")}
    )

    assert result["status"] == "ok", result.get("error")
    assert result["iterations"] == 1
    assert "ITM-FAKE-99" not in result["citations"]
    assert "ITM-REP-01" in result["citations"]


def test_brief_format_profile_and_signature_are_used(server, report_data):
    llm = RecordingReportLLM(
        drafts=[
            ReportDraft(text=complete_report("ITM-REP-01"), citations=["ITM-REP-01"])
        ],
        reviews=[ReportReview(verdict="ok")],
    )
    graph = build_report_graph(server, llm)
    request = make_acl_message(
        performative="request",
        sender="orchestrator",
        receiver="report_agent",
        content={
            "question": "Сформируй раздел акта по AUD-2026-DEPOSITS-77",
            "auditor_id": "AUD-001",
            "report_format": "краткий",
            "signature": "Иванов И.И.",
            "profile_text": "Тема: ипотека; Формат: краткий",
        },
        conversation_id="conv-report-brief",
    ).model_dump()

    result = graph.invoke({"acl_request": request})

    assert result["status"] == "ok", result.get("error")
    assert llm.draft_kwargs[-1]["report_format"] == "краткий"
    assert llm.draft_kwargs[-1]["profile_text"] == "Тема: ипотека; Формат: краткий"
    draft = result["acl_response"]["content"]["draft"]
    assert draft.rstrip().endswith("Иванов И.И.")
    assert "Вводная часть" in draft


def test_signature_is_not_duplicated_when_model_added_it(server, report_data):
    llm = FakeReportLLM(
        drafts=[
            ReportDraft(
                text=complete_report("ITM-REP-01") + "\n\nИванов И.И.",
                citations=["ITM-REP-01"],
            )
        ],
        reviews=[ReportReview(verdict="ok")],
    )
    graph = build_report_graph(server, llm)
    request = make_acl_message(
        performative="request",
        sender="orchestrator",
        receiver="report_agent",
        content={
            "question": "Сформируй раздел акта по AUD-2026-DEPOSITS-77",
            "auditor_id": "AUD-001",
            "signature": "Иванов И.И.",
        },
        conversation_id="conv-report-signature",
    ).model_dump()

    result = graph.invoke({"acl_request": request})

    assert result["status"] == "ok", result.get("error")
    content = result["acl_response"]["content"]
    assert content["draft"].count("Иванов И.И.") == 1
    assert content["draft"].rstrip().endswith("Иванов И.И.")
    assert "Иванов И.И." not in content["citations"]
    assert all(
        item.get("source_id") != "Иванов И.И."
        for item in content["evidence"]
    )


def test_default_format_is_detailed_when_profile_absent(server, report_data):
    llm = RecordingReportLLM(
        drafts=[
            ReportDraft(text=complete_report("ITM-REP-01"), citations=["ITM-REP-01"])
        ],
        reviews=[ReportReview(verdict="ok")],
    )
    graph = build_report_graph(server, llm)

    result = graph.invoke(
        {"acl_request": acl_request("Сформируй раздел акта по AUD-2026-DEPOSITS-77")}
    )

    assert result["status"] == "ok", result.get("error")
    assert llm.draft_kwargs[-1]["report_format"] == "подробный"
    assert llm.draft_kwargs[-1]["profile_text"] == ""
    # Поле действительно приходит из ACL, а не только из профиля по умолчанию.
    assert result["report_format"] == "подробный"
    assert result["signature"] == ""


def test_revise_keeps_profile_format_and_text(server, report_data):
    llm = RecordingReportLLM(
        drafts=[ReportDraft(text="Черновик.", citations=["FAKE-ID"])],
        reviews=[ReportReview(verdict="ok"), ReportReview(verdict="ok")],
        revisions=[
            ReportDraft(
                text=complete_report("ITM-REP-01"),
                citations=["ITM-REP-01"],
            )
        ],
    )
    graph = build_report_graph(server, llm)
    request = acl_request(
        "Сформируй раздел акта по AUD-2026-DEPOSITS-77",
        report_format="краткий",
        profile_text="Формат: краткий",
        signature="Иванов И.И.",
    )

    result = graph.invoke({"acl_request": request})

    assert result["status"] == "ok", result.get("error")
    assert llm.calls.count("revise") == 1
    assert llm.revise_kwargs[-1]["report_format"] == "краткий"
    assert llm.revise_kwargs[-1]["profile_text"] == "Формат: краткий"
    assert result["acl_response"]["content"]["draft"].rstrip().endswith("Иванов И.И.")


def test_profile_without_signature_does_not_change_draft(server, report_data):
    llm = RecordingReportLLM(
        drafts=[
            ReportDraft(text=complete_report("ITM-REP-01"), citations=["ITM-REP-01"])
        ],
        reviews=[ReportReview(verdict="ok")],
    )
    graph = build_report_graph(server, llm)
    request = acl_request(
        "Сформируй раздел акта по AUD-2026-DEPOSITS-77",
        report_format="подробный",
        profile_text="Формат: подробный",
    )

    result = graph.invoke({"acl_request": request})

    draft = result["acl_response"]["content"]["draft"]
    assert draft == complete_report("ITM-REP-01")


def test_failure_does_not_append_signature(server, report_data):
    llm = RecordingReportLLM()
    graph = build_report_graph(server, llm)
    request = acl_request(
        "Сформируй раздел акта по AUD-2026-DEPOSITS-99",
        signature="Иванов И.И.",
    )

    result = graph.invoke({"acl_request": request})

    assert result["status"] == "failed"
    assert result["acl_response"]["performative"] == "failure"
    assert "draft" not in result["acl_response"]["content"]
    assert "Иванов И.И." not in str(result["acl_response"]["content"])


def test_refusal_does_not_append_signature(server, report_data):
    llm = RecordingReportLLM()
    graph = build_report_graph(server, llm)
    request = make_acl_message(
        performative="inform",
        sender="orchestrator",
        receiver="report_agent",
        content={
            "question": "Сформируй раздел акта",
            "signature": "Иванов И.И.",
        },
        conversation_id="conv-report-refuse",
    ).model_dump()

    result = graph.invoke({"acl_request": request})

    assert result["status"] == "refused"
    assert "Иванов И.И." not in str(result["acl_response"]["content"])
