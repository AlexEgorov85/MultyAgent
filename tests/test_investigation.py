"""Проверки спецификации investigation-orchestration (A7)."""

from __future__ import annotations

import json

import pytest

from src import db_runtime
from src.acl import make_acl_message
from src.graph.investigation_graph import build_investigation_graph
from src.rag.embeddings import HashEmbeddings
from src.rag.ingest import build_index
from src.schemas import (
    Critique,
    InvestigationAnswer,
    InvestigationPlan,
    RetrievalAnswer,
    SQLPlan,
)


class CoordinatorLLM:
    def __init__(self, plans, answers, refined=None):
        self.plans = list(plans)
        self.answers = list(answers)
        self.refined = list(refined or [])
        self.calls: list[str] = []

    def plan_investigation(self, **kwargs):
        self.calls.append("plan")
        return self.plans.pop(0)

    def refine_investigation(self, **kwargs):
        self.calls.append("refine")
        assert self.refined
        return self.refined.pop(0)

    def synthesize_investigation(self, **kwargs):
        self.calls.append("synthesize")
        return self.answers.pop(0)


class AnalyticsLLM:
    def plan_sql(self, **kwargs):
        return SQLPlan(
            strategy="generated",
            sql=(
                "SELECT count(*) AS cnt FROM audit.act_items i "
                "JOIN audit.acts ac ON ac.act_id = i.act_id "
                "JOIN audit.audits a ON a.audit_id = ac.audit_id "
                "JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id "
                "WHERE p.theme_code = 'ипотека' AND p.pocket_year = 2026 "
                "AND i.item_type = 'отклонение'"
            ),
            reason="количество отклонений по ипотеке",
        )

    def repair_sql(self, **kwargs):
        raise AssertionError("repair не ожидался")

    def plan_tools(self, **kwargs):
        raise AssertionError("multi-tool не ожидался")

    def summarize(self, **kwargs):
        return "Найден один пункт."


class RetrievalLLM:
    def __init__(self):
        self.calls: list[str] = []

    def answer_from_chunks(self, **kwargs):
        self.calls.append("answer")
        return RetrievalAnswer(
            text="Просроченная оценка залога подтверждается пунктом.",
            citations=["ITM-INV-01"],
        )

    def critique_answer(self, **kwargs):
        self.calls.append("critique")
        return Critique(verdict="ok")

    def rewrite_answer(self, **kwargs):
        raise AssertionError("rewrite не ожидался")


def acl_request(question: str) -> dict:
    return make_acl_message(
        performative="request",
        sender="orchestrator",
        receiver="investigation_coordinator",
        content={"question": question, "auditor_id": "AUD-001"},
        conversation_id="conv-inv-001",
    ).model_dump()


@pytest.fixture(autouse=True)
def acl_log_path(tmp_path, monkeypatch):
    path = tmp_path / "acl.jsonl"
    monkeypatch.setenv("ACL_LOG_PATH", str(path))
    return path


@pytest.fixture()
def investigation_data(server, tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "залог.md").write_text(
        "Просроченная оценка залога требует переоценки не реже раза в год.",
        encoding="utf-8",
    )
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.auditors "
            "(auditor_id, full_name, email, unit, position) "
            "VALUES ('INV-001', 'Тест Расследование', 'inv@audit.local', 'Аудит', 'Аудитор') "
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
            "VALUES ('AUD-2026-MORTGAGE-77', 'PKT-2026-MORTGAGE', "
            "        'AUD-2026-MORTGAGE-77', 'Проверка ипотеки', 'плановая', "
            "        '2026-02-01', '2026-03-01', 'завершена', 'INV-001', 2) "
            "ON CONFLICT (audit_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.acts "
            "(act_id, audit_id, act_number, act_date, status, approved_by, "
            " summary, full_text) "
            "VALUES ('ACT-2026-MORTGAGE-77', 'AUD-2026-MORTGAGE-77', "
            "        'ACT-2026-MORTGAGE-77', '2026-03-10', 'утверждён', 'INV-001', "
            "        'Акт по ипотеке', 'Просроченная оценка залога.') "
            "ON CONFLICT (act_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.act_items "
            "(item_id, act_id, item_number, item_type, test_type, "
            " finding_template_key, finding_scope, title, test_description, "
            " criterion, condition, cause, effect, recommendation, risk_level, "
            " status, deadline, responsible_unit, order_index) "
            "VALUES ('ITM-INV-01', 'ACT-2026-MORTGAGE-77', '5.1', 'отклонение', "
            "        'непрерывный', 'MORTGAGE-01', 'ипотека 2026', "
            "        'Просроченная оценка залога', 'Проверить срок оценки', "
            "        'п. 4.3', 'у 2 из 10', 'нет контроля', 'риск залога', "
            "        'настроить контроль', 'высокий', 'открыт', '2026-06-01', "
            "        'Департамент ипотеки', 1) "
            "ON CONFLICT (item_id) DO NOTHING"
        )
    build_index(server, HashEmbeddings(), knowledge)
    yield
    with db_runtime.connect(server) as conn:
        conn.execute("TRUNCATE audit.knowledge_chunks")
        conn.execute(
            "DELETE FROM audit.act_items WHERE act_id = 'ACT-2026-MORTGAGE-77'"
        )
        conn.execute("DELETE FROM audit.acts WHERE act_id = 'ACT-2026-MORTGAGE-77'")
        conn.execute(
            "DELETE FROM audit.audits WHERE audit_id = 'AUD-2026-MORTGAGE-77'"
        )
        conn.execute(
            "DELETE FROM audit.audit_pockets WHERE pocket_id = 'PKT-2026-MORTGAGE'"
        )
        conn.execute("DELETE FROM audit.auditors WHERE auditor_id = 'INV-001'")


def _plan(retrieval_focus="causes"):
    return InvestigationPlan(
        analytics_focus="compare",
        retrieval_focus=retrieval_focus,
        required_evidence=["sql_result", "item"],
        reason="нужны числа и подтверждение",
    )


def _fail_first_search(monkeypatch, times: int = 1):
    """Первые ``times`` поисков не находят чанков — проверяем второй раунд."""
    from src.graph import retrieval_graph

    real_search = retrieval_graph.search
    calls = {"count": 0}

    def flaky(server, query, **kwargs):
        calls["count"] += 1
        if calls["count"] <= times:
            return {"chunks": [], "mode": "fts"}
        return real_search(server, query, **kwargs)

    monkeypatch.setattr(retrieval_graph, "search", flaky)


def test_two_agents_in_one_round(server, investigation_data):
    coordinator = CoordinatorLLM(
        plans=[_plan()],
        answers=[
            InvestigationAnswer(
                text="Динамика подтверждена SQL и пунктом акта.",
                causal_claim=True,
            )
        ],
    )
    graph = build_investigation_graph(
        server,
        coordinator,
        analytics_llm=AnalyticsLLM(),
        retrieval_llm=RetrievalLLM(),
        embeddings=HashEmbeddings(),
    )

    result = graph.invoke(
        {"acl_request": acl_request("Почему выросла доля просроченных пунктов?")}
    )

    assert result["status"] == "ok"
    assert result["rounds"] == 1
    content = result["acl_response"]["content"]
    assert content["metrics"]["acl_rounds"] == 1
    assert content["metrics"]["investigation_completeness"] == 1.0
    assert content["causal_claim"] is True
    types = {item["type"] for item in content["evidence"]}
    assert "sql_result" in types
    assert types & {"item", "пункт"}
    # 2 запроса + 2 ответа в ACL-журнале
    assert len(result["acl_log"]) == 4


def test_acl_journal_persists_round_correlation(
    server, investigation_data, acl_log_path
):
    coordinator = CoordinatorLLM(
        plans=[_plan()],
        answers=[
            InvestigationAnswer(
                text="Динамика подтверждена SQL и пунктом акта.",
                causal_claim=True,
            )
        ],
    )
    graph = build_investigation_graph(
        server,
        coordinator,
        analytics_llm=AnalyticsLLM(),
        retrieval_llm=RetrievalLLM(),
        embeddings=HashEmbeddings(),
    )

    result = graph.invoke(
        {"acl_request": acl_request("Почему выросла доля просроченных пунктов?")}
    )

    lines = acl_log_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 4
    messages = [json.loads(line) for line in lines]
    assert all(message["conversation_id"] == "conv-inv-001" for message in messages)

    requests = [m for m in messages if m["performative"] == "request"]
    responses = [m for m in messages if m["performative"] == "inform"]
    assert len(requests) == 2
    assert len(responses) == 2
    assert {m["receiver"] for m in requests} == {
        "analytics_agent",
        "retrieval_agent",
    }
    assert {m["in_reply_to"] for m in responses} == {
        m["reply_with"] for m in requests
    }

    content = result["acl_response"]["content"]
    assert content["metrics"]["acl_log_count"] == 4
    assert content["metrics"]["acl_log_path"] == str(acl_log_path)


def test_second_round_when_evidence_missing(server, investigation_data, monkeypatch):
    _fail_first_search(monkeypatch)
    coordinator = CoordinatorLLM(
        plans=[_plan(retrieval_focus="causes")],
        answers=[
            InvestigationAnswer(text="Причина подтверждена.", causal_claim=True)
        ],
        refined=[
            InvestigationPlan(
                analytics_focus="compare",
                retrieval_focus="causes",
                required_evidence=["sql_result", "item"],
                reason="уточнение retrieval",
            )
        ],
    )
    graph = build_investigation_graph(
        server,
        coordinator,
        analytics_llm=AnalyticsLLM(),
        retrieval_llm=RetrievalLLM(),
        embeddings=HashEmbeddings(),
    )

    result = graph.invoke(
        {"acl_request": acl_request("Почему выросла доля просроченных пунктов?")}
    )

    assert result["rounds"] == 2
    assert coordinator.calls == ["plan", "refine", "synthesize"]
    assert result["missing"] == []
    content = result["acl_response"]["content"]
    assert content["causal_claim"] is True
    assert len(result["acl_log"]) == 6


def test_causal_claim_is_rejected_without_evidence(server, investigation_data, monkeypatch):
    _fail_first_search(monkeypatch, times=2)
    coordinator = CoordinatorLLM(
        plans=[_plan(retrieval_focus="causes")],
        answers=[
            InvestigationAnswer(text="Причина установлена.", causal_claim=True)
        ],
        refined=[
            InvestigationPlan(
                analytics_focus="compare",
                retrieval_focus="causes",
                required_evidence=["sql_result", "item"],
                reason="ничего не найдено",
            )
        ],
    )
    graph = build_investigation_graph(
        server,
        coordinator,
        analytics_llm=AnalyticsLLM(),
        retrieval_llm=RetrievalLLM(),
        embeddings=HashEmbeddings(),
    )

    result = graph.invoke(
        {"acl_request": acl_request("Почему выросла доля просроченных пунктов?")}
    )

    content = result["acl_response"]["content"]
    assert content["causal_claim"] is False
    assert "не подтверждён" in content["answer"]
    assert content["missing"]


def test_act_evidence_satisfies_item_requirement():
    from src.graph.investigation_graph import _missing_evidence

    assert _missing_evidence(["sql_result", "item"], {"sql_result", "act"}) == []
    assert _missing_evidence(["sql_result", "item"], {"item"}) == ["sql_result"]
    assert _missing_evidence(["item"], {"act"}) == []


def test_retrieval_evidence_outside_query_scope_is_removed(monkeypatch):
    from src.graph import investigation_graph

    monkeypatch.setattr(
        investigation_graph.db_tools,
        "act_scope_map",
        lambda server, codes: {
            "ACT-2025-DEPOSITS-01": {
                "theme": "вклады",
                "audit_code": "AUD-2025-DEPOSITS-01",
            },
            "ACT-2025-CONSUMER-07": {
                "theme": "потребителькредитование",
                "audit_code": "AUD-2025-CONSUMER-07",
            },
        },
    )
    retrieval = {
        "answer": "…",
        "sources": [
            {"source_type": "акт", "source_id": "ACT-2025-DEPOSITS-01"},
            {"source_type": "акт", "source_id": "ACT-2025-CONSUMER-07"},
            {"source_type": "методика", "source_id": "оценка_риска.md"},
        ],
        "citations": [
            "ACT-2025-DEPOSITS-01",
            "ACT-2025-CONSUMER-07",
            "оценка_риска.md",
        ],
        "evidence": [
            {"type": "акт", "source_id": "ACT-2025-CONSUMER-07"},
        ],
    }

    filtered = investigation_graph._filter_retrieval_by_scope(
        None, retrieval, {"theme": "вклады"}
    )

    assert [item["source_id"] for item in filtered["sources"]] == [
        "ACT-2025-DEPOSITS-01",
        "оценка_риска.md",
    ]
    assert filtered["citations"] == [
        "ACT-2025-DEPOSITS-01",
        "оценка_риска.md",
    ]
    assert filtered["evidence"] == []
