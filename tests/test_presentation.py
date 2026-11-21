"""Политики презентационного узла и путь работы агента."""

from __future__ import annotations

from src.presentation import build_presentation, build_trace, present


def _state(**overrides):
    base = {
        "route": "analytics",
        "user_query": "Сколько завершённых проверок по ипотеке в 2026 году?",
        "language": "ru",
        "acl_response": {
            "performative": "inform",
            "sender": "analytics_agent",
            "content": {},
        },
        "profile": {},
        "guardrail": {"safe": True},
        "metrics": {},
    }
    base.update(overrides)
    return base


def test_count_answer_uses_human_label_and_hides_aliases():
    state = _state(
        acl_response={
            "performative": "inform",
            "sender": "analytics_agent",
            "content": {
                "rows": [
                    {
                        "pocket_year": 2026,
                        "theme_code": "ипотека",
                        "status": "завершена",
                        "audit_count": 5,
                    }
                ],
                "columns": ["pocket_year", "theme_code", "status", "audit_count"],
                "sql": "SELECT COUNT(*) AS audit_count ...",
            },
        }
    )

    presentation = build_presentation(state)

    assert presentation["kind"] == "count"
    assert presentation["text"] == "Завершённых проверок: 5."
    assert "pocket_year" not in presentation["text"]
    assert "ипотека" not in presentation["text"]


def test_count_alias_without_count_suffix_is_humanized():
    state = _state()
    state["acl_response"]["content"] = {
        "rows": [{"completed_audits": 5}],
        "columns": ["completed_audits"],
    }

    presentation = build_presentation(state)

    assert presentation["kind"] == "count"
    assert presentation["text"] == "Завершённых проверок: 5."


def test_generic_count_alias_uses_question_context():
    state = _state()
    state["acl_response"]["content"] = {
        "rows": [{"count": 5}],
        "columns": ["count"],
    }

    presentation = build_presentation(state)

    assert presentation["kind"] == "count"
    assert presentation["text"] == "Завершённых проверок: 5."


def test_llm_answer_replaces_single_row_template():
    state = _state(
        acl_response={
            "performative": "inform",
            "sender": "analytics_agent",
            "content": {
                "rows": [{"completed_audits": 5}],
                "columns": ["completed_audits"],
                "answer": "По ипотеке в 2026 году завершено 5 проверок.",
                "answer_source": "llm",
            },
        }
    )

    presentation = build_presentation(state)

    assert presentation["kind"] == "count"
    assert presentation["text"] == "По ипотеке в 2026 году завершено 5 проверок."
    assert presentation["facts"] == [
        {"label": "Завершённых проверок", "value": "5"}
    ]


def test_template_answer_keeps_humanized_single_row():
    state = _state(
        acl_response={
            "performative": "inform",
            "sender": "analytics_agent",
            "content": {
                "rows": [{"completed_audits": 5}],
                "columns": ["completed_audits"],
                "answer": "Всего completed_audits: 5.",
                "answer_source": "template",
            },
        }
    )

    presentation = build_presentation(state)

    assert presentation["text"] == "Завершённых проверок: 5."


def test_table_answer_has_no_raw_column_names():
    state = _state(
        acl_response={
            "performative": "inform",
            "sender": "analytics_agent",
            "content": {
                "rows": [
                    {"audit_code": "AUD-1", "status": "завершена", "item_id": "ITM-1"},
                    {"audit_code": "AUD-2", "status": "завершена", "item_id": "ITM-2"},
                ],
                "columns": ["audit_code", "status", "item_id"],
            },
        }
    )

    presentation = build_presentation(state)

    assert presentation["kind"] == "table"
    assert presentation["text"].startswith("Найдено строк: 2.")
    assert "audit_code" not in presentation["text"]
    assert "| проверка |" in presentation["text"]
    assert "| AUD-1 |" in presentation["text"]


def test_closed_audits_alias_is_humanized_in_table():
    state = _state(
        user_query="Сколько проверок было закрыто по годам и карманам?",
        acl_response={
            "performative": "inform",
            "sender": "analytics_agent",
            "content": {
                "rows": [
                    {"pocket_year": 2025, "theme_code": "ипотека", "closed_audits_count": 8},
                    {"pocket_year": 2026, "theme_code": "ипотека", "closed_audits_count": 5},
                ],
                "columns": ["pocket_year", "theme_code", "closed_audits_count"],
            },
        },
    )

    text = build_presentation(state)["text"]

    assert "| год | тема | Завершённых проверок |" in text
    assert "closed_audits_count" not in text


def test_text_report_and_refusal_pass_through():
    retrieval = _state(
        route="retrieval",
        acl_response={
            "performative": "inform",
            "sender": "retrieval_agent",
            "content": {"answer": "Найдено совпадение.", "citations": ["ACT-1"]},
        },
    )
    assert build_presentation(retrieval)["text"] == "Найдено совпадение."

    report = _state(
        route="report",
        acl_response={
            "performative": "inform",
            "sender": "report_agent",
            "content": {"draft": "Краткий проект акта.", "citations": []},
        },
    )
    assert build_presentation(report)["text"] == "Краткий проект акта."

    refused = _state(
        route="unsafe",
        final_answer="Не могу выполнить запрос: изменение данных запрещено.",
        acl_response={"performative": "refuse", "content": {}},
    )
    assert build_presentation(refused)["kind"] == "refusal"
    assert "изменение данных" in build_presentation(refused)["text"]


def test_trace_contains_route_sql_and_guard_steps():
    state = _state(
        route_confidence=0.9,
        route_reason="вопрос про количество",
        acl_response={
            "performative": "inform",
            "sender": "analytics_agent",
            "content": {
                "rows": [{"audit_count": 5}],
                "columns": ["audit_count"],
                "sql": "SELECT COUNT(*) AS audit_count FROM audit.audits",
                "metrics": {"sql_retries": 1},
            },
        },
    )

    result = present(state)
    steps = {step["step"]: step for step in result["trace"]}

    assert result["final_answer"] == "Завершённых проверок: 5."
    assert "route" in steps
    assert steps["sql"]["detail"].startswith("SELECT COUNT(*)")
    assert "sql_result" in steps
    assert "guard_request" in steps
    assert "guard_answer" in steps


def test_empty_result_is_explained():
    state = _state(
        acl_response={
            "performative": "inform",
            "sender": "analytics_agent",
            "content": {"rows": [], "columns": [], "sql": "SELECT 1"},
        }
    )
    presentation = build_presentation(state)
    assert presentation["kind"] == "empty"
    assert presentation["text"] == "По заданным условиям ничего не найдено."


def test_english_policy():
    state = _state(language="en")
    state["acl_response"]["content"] = {
        "rows": [{"completed_count": 5}],
        "columns": ["completed_count"],
    }
    assert build_presentation(state)["text"] == "Completed audits: 5."


def test_trace_is_json_serializable():
    state = _state()
    result = present(state)
    import json

    json.dumps(result["presentation"], ensure_ascii=False)
    json.dumps(result["trace"], ensure_ascii=False)
