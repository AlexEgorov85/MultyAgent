"""Проверки спецификации retrieval-rag."""

from __future__ import annotations

import pytest

from src import db_runtime
from src.acl import make_acl_message
from src.graph.retrieval_graph import build_retrieval_graph
from src.rag.embeddings import HashEmbeddings
from src.rag.ingest import build_index
from src.rag.vector_store import search
from src.schemas import Critique, RetrievalAnswer


class FakeRagLLM:
    def __init__(
        self,
        *,
        answers: list[RetrievalAnswer] | None = None,
        critiques: list[Critique] | None = None,
        rewrites: list[RetrievalAnswer] | None = None,
    ) -> None:
        self.answers = list(answers or [])
        self.critiques = list(critiques or [])
        self.rewrites = list(rewrites or [])
        self.calls: list[str] = []

    def answer_from_chunks(self, **kwargs):
        self.calls.append("answer")
        return self.answers.pop(0)

    def critique_answer(self, **kwargs):
        self.calls.append("critique")
        return self.critiques.pop(0)

    def rewrite_answer(self, **kwargs):
        self.calls.append("rewrite")
        return self.rewrites.pop(0)


def acl_request(question: str) -> dict:
    return make_acl_message(
        performative="request",
        sender="orchestrator",
        receiver="retrieval_agent",
        content={"question": question, "auditor_id": "AUD-001"},
        conversation_id="conv-rag-001",
    ).model_dump()


@pytest.fixture()
def rag_data(server, tmp_path):
    knowledge = tmp_path / "knowledge"
    knowledge.mkdir()
    (knowledge / "противодействие_мошенничеству.md").write_text(
        "# Противодействие мошенничеству\n\n"
        "Мошеннические операции блокируются в течение 24 часов после выявления. "
        "Ответственное подразделение — служба комплаенса.",
        encoding="utf-8",
    )
    with db_runtime.connect(server) as conn:
        conn.execute(
            "INSERT INTO audit.auditors "
            "(auditor_id, full_name, email, unit, position) "
            "VALUES ('RET-001', 'Тест RAG', 'rag@audit.local', 'Аудит', 'Аудитор') "
            "ON CONFLICT (auditor_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.audit_pockets "
            "(pocket_id, pocket_year, theme_code, title, owner_unit, "
            " period_start, period_end, planned_audit_count) "
            "VALUES ('PKT-2026-CARDS', 2026, 'карты', '2026. Карты', "
            "        'Департамент карт', '2026-01-01', '2026-12-31', 5) "
            "ON CONFLICT (pocket_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.audits "
            "(audit_id, pocket_id, audit_code, title, audit_type, start_date, "
            " end_date, status, lead_auditor_id, team_size) "
            "VALUES ('AUD-2026-CARDS-99', 'PKT-2026-CARDS', "
            "        'AUD-2026-CARDS-99', 'Проверка карт', 'плановая', "
            "        '2026-02-01', '2026-03-01', 'завершена', 'RET-001', 2) "
            "ON CONFLICT (audit_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.acts "
            "(act_id, audit_id, act_number, act_date, status, approved_by, "
            " summary, full_text) "
            "VALUES ('ACT-2026-CARDS-99', 'AUD-2026-CARDS-99', "
            "        'ACT-2026-CARDS-99', '2026-03-10', 'утверждён', 'RET-001', "
            "        'Акт по картам', "
            "        'Мошеннические операции без своевременной блокировки. "
            "         Служба комплаенса не всегда укладывается в 24 часа.') "
            "ON CONFLICT (act_id) DO NOTHING"
        )
        conn.execute(
            "INSERT INTO audit.act_items "
            "(item_id, act_id, item_number, item_type, test_type, "
            " finding_template_key, finding_scope, title, test_description, "
            " criterion, condition, cause, effect, recommendation, risk_level, "
            " status, deadline, responsible_unit, order_index) "
            "VALUES ('ITM-RET-01', 'ACT-2026-CARDS-99', '5.1', 'отклонение', "
            "        'непрерывный', 'CARDS-04', 'карты 2026', "
            "        'Мошеннические операции без своевременной блокировки', "
            "        'Проверить срок блокировки', 'п. 6.4', 'у 2 из 10', "
            "        'нет автоматизации', 'риск потерь', 'автоматизировать', "
            "        'высокий', 'открыт', '2026-06-01', 'Департамент карт', 1) "
            "ON CONFLICT (item_id) DO NOTHING"
        )

    counts = build_index(server, HashEmbeddings(), knowledge)
    yield {"knowledge": knowledge, "counts": counts}

    with db_runtime.connect(server) as conn:
        conn.execute("TRUNCATE audit.knowledge_chunks")
        conn.execute("DELETE FROM audit.act_items WHERE act_id = 'ACT-2026-CARDS-99'")
        conn.execute("DELETE FROM audit.acts WHERE act_id = 'ACT-2026-CARDS-99'")
        conn.execute("DELETE FROM audit.audits WHERE audit_id = 'AUD-2026-CARDS-99'")
        conn.execute("DELETE FROM audit.audit_pockets WHERE pocket_id = 'PKT-2026-CARDS'")
        conn.execute("DELETE FROM audit.auditors WHERE auditor_id = 'RET-001'")


def test_index_contains_all_sources(server, rag_data):
    assert rag_data["counts"].get("методика", 0) >= 1
    assert rag_data["counts"].get("пункт", 0) >= 1
    assert rag_data["counts"].get("акт", 0) >= 1

    with db_runtime.connect(server) as conn:
        total = conn.execute("SELECT count(*) FROM audit.knowledge_chunks").fetchone()[0]
        with_vectors = conn.execute(
            "SELECT count(*) FROM audit.knowledge_chunks WHERE embedding IS NOT NULL"
        ).fetchone()[0]
    assert total >= 3
    assert with_vectors == total


def test_index_rebuild_is_idempotent(server, rag_data):
    with db_runtime.connect(server) as conn:
        before = conn.execute(
            "SELECT count(*) FROM audit.knowledge_chunks"
        ).fetchone()[0]
    build_index(server, HashEmbeddings(), rag_data["knowledge"])
    with db_runtime.connect(server) as conn:
        after = conn.execute(
            "SELECT count(*) FROM audit.knowledge_chunks"
        ).fetchone()[0]
    assert before == after


def test_hybrid_search_finds_item(server, rag_data):
    result = search(
        server, "мошеннические операции", embeddings=HashEmbeddings(), top_k=5
    )
    assert result["chunks"]
    assert result["mode"] == "hybrid"
    assert any(chunk["source_id"] == "ITM-RET-01" for chunk in result["chunks"])


def test_answer_with_valid_citations(server, rag_data):
    llm = FakeRagLLM(
        answers=[
            RetrievalAnswer(
                text="Мошеннические операции должны блокироваться в течение 24 часов.",
                citations=["ACT-2026-CARDS-99"],
            )
        ],
        critiques=[Critique(verdict="ok")],
    )
    graph = build_retrieval_graph(server, llm, embeddings=HashEmbeddings())

    result = graph.invoke({"acl_request": acl_request("Что сказано про мошеннические операции?")})

    assert result["status"] == "ok", result.get("error")
    assert result["acl_response"]["performative"] == "inform"
    content = result["acl_response"]["content"]
    assert content["citations"] == ["ACT-2026-CARDS-99"]
    assert content["evidence"] == [{"type": "акт", "source_id": "ACT-2026-CARDS-99"}]
    assert llm.calls == ["answer", "critique"]


def test_invalid_citation_triggers_rewrite(server, rag_data):
    llm = FakeRagLLM(
        answers=[
            RetrievalAnswer(text="Черновик.", citations=["FAKE-ID"])
        ],
        critiques=[Critique(verdict="ok"), Critique(verdict="ok")],
        rewrites=[
            RetrievalAnswer(text="Исправлено.", citations=["ACT-2026-CARDS-99"])
        ],
    )
    graph = build_retrieval_graph(server, llm, embeddings=HashEmbeddings())

    result = graph.invoke({"acl_request": acl_request("Что сказано про мошеннические операции?")})

    assert result["iterations"] == 1
    assert result["citations"] == ["ACT-2026-CARDS-99"]
    assert llm.calls.count("rewrite") == 1


def test_invalid_text_id_triggers_rewrite(server, rag_data):
    llm = FakeRagLLM(
        answers=[
            RetrievalAnswer(
                text="Подтверждение: см. ITM-FAKE-01.",
                citations=["ACT-2026-CARDS-99"],
            )
        ],
        critiques=[Critique(verdict="ok"), Critique(verdict="ok")],
        rewrites=[
            RetrievalAnswer(
                text="Подтверждение без вымышленных ID.",
                citations=["ACT-2026-CARDS-99"],
            )
        ],
    )
    graph = build_retrieval_graph(server, llm, embeddings=HashEmbeddings())

    result = graph.invoke(
        {"acl_request": acl_request("Что сказано про мошеннические операции?")}
    )

    assert result["iterations"] == 1
    assert llm.calls.count("rewrite") == 1
    assert "ITM-FAKE-01" not in result["acl_response"]["content"]["answer"]


def test_empty_result_does_not_call_llm(server, rag_data):
    llm = FakeRagLLM()
    graph = build_retrieval_graph(server, llm, embeddings=HashEmbeddings())

    result = graph.invoke({"acl_request": acl_request("квантовая физика и теория струн")})

    assert result["status"] == "ok"
    assert result["chunks"] == []
    assert "не найдено" in result["acl_response"]["content"]["answer"]
    assert llm.calls == []


def test_rewrite_limit_marks_answer(server, rag_data):
    llm = FakeRagLLM(
        answers=[RetrievalAnswer(text="Плохой ответ.", citations=["ACT-2026-CARDS-99"])],
        critiques=[
            Critique(verdict="rewrite", issues=["нет подтверждения"]),
            Critique(verdict="rewrite", issues=["нет подтверждения"]),
            Critique(verdict="rewrite", issues=["нет подтверждения"]),
        ],
        rewrites=[
            RetrievalAnswer(text="Всё ещё плохо.", citations=["ACT-2026-CARDS-99"]),
            RetrievalAnswer(text="Совсем плохо.", citations=["ACT-2026-CARDS-99"]),
        ],
    )
    graph = build_retrieval_graph(server, llm, embeddings=HashEmbeddings())

    result = graph.invoke({"acl_request": acl_request("Что сказано про мошеннические операции?")})

    assert result["iterations"] == 2
    assert "Требует проверки" in result["acl_response"]["content"]["answer"]
    assert llm.calls.count("rewrite") == 2
