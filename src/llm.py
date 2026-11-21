"""Обёртка над LLM с structured output и injectable-клиентом для тестов."""

from __future__ import annotations

import os
from typing import Any, Protocol

from .schemas import (
    AnswerDraft,
    Critique,
    InvestigationAnswer,
    InvestigationPlan,
    ReportDraft,
    ReportReview,
    RetrievalAnswer,
    SQLPlan,
    ToolPlan,
)


class LLMError(RuntimeError):
    """LLM недоступна или вернула некорректный ответ."""


class LLMClient(Protocol):
    def plan_sql(
        self, *, question: str, schema_text: str, templates: list[dict[str, Any]]
    ) -> SQLPlan: ...

    def repair_sql(
        self, *, question: str, sql: str, error: str, schema_text: str
    ) -> SQLPlan: ...

    def plan_tools(
        self, *, question: str, tools_text: str
    ) -> ToolPlan: ...

    def summarize(
        self,
        *,
        question: str,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> str: ...

    def answer_from_chunks(
        self,
        *,
        question: str,
        chunks: list[dict[str, Any]],
    ) -> "RetrievalAnswer": ...

    def critique_answer(
        self,
        *,
        question: str,
        answer: "RetrievalAnswer",
        chunks: list[dict[str, Any]],
    ) -> "Critique": ...

    def rewrite_answer(
        self,
        *,
        question: str,
        answer: "RetrievalAnswer",
        issues: list[str],
        chunks: list[dict[str, Any]],
    ) -> "RetrievalAnswer": ...

    def draft_report(
        self,
        *,
        question: str,
        facts_text: str,
        allowed_ids: list[str],
    ) -> "ReportDraft": ...

    def review_report(
        self,
        *,
        draft: "ReportDraft",
        facts_text: str,
        allowed_ids: list[str],
    ) -> "ReportReview": ...

    def revise_report(
        self,
        *,
        draft: "ReportDraft",
        review: "ReportReview",
        facts_text: str,
        allowed_ids: list[str],
    ) -> "ReportDraft": ...

    def plan_investigation(
        self,
        *,
        question: str,
        schema_text: str,
    ) -> "InvestigationPlan": ...

    def refine_investigation(
        self,
        *,
        question: str,
        plan: "InvestigationPlan",
        missing: list[str],
    ) -> "InvestigationPlan": ...

    def synthesize_investigation(
        self,
        *,
        question: str,
        analytics: dict[str, Any],
        retrieval: dict[str, Any],
        missing: list[str],
        rounds: int,
    ) -> "InvestigationAnswer": ...


class OpenAILLM:
    """Реализация через OpenAI-совместимый endpoint."""

    def __init__(self, model: str | None = None, client: Any | None = None) -> None:
        if client is None:
            from openai import OpenAI

            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                raise LLMError("Не задан OPENAI_API_KEY")
            client = OpenAI(
                api_key=api_key,
                base_url=os.getenv("OPENAI_BASE_URL") or None,
            )
        self.client = client
        self.model = model or os.getenv("LLM_MODEL", "gpt-5-mini")

    def _parse(self, *, system: str, user: str, schema: type) -> Any:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        try:
            response = self.client.beta.chat.completions.parse(
                model=self.model,
                messages=messages,
                response_format=schema,
                temperature=0,
            )
            parsed = response.choices[0].message.parsed
            if parsed is None:
                raise LLMError("Модель вернула пустой structured output")
            return parsed
        except Exception as first_error:
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    response_format={"type": "json_object"},
                    temperature=0,
                )
                content = response.choices[0].message.content or "{}"
                return schema.model_validate_json(content)
            except Exception as second_error:
                raise LLMError(
                    f"Structured output не получен: {first_error}; {second_error}"
                ) from second_error

    def plan_sql(
        self, *, question: str, schema_text: str, templates: list[dict[str, Any]]
    ) -> SQLPlan:
        template_lines = "\n".join(
            f"- {item['template_key']}: {item['title']} (параметры: {item['parameters']})"
            for item in templates
        )
        return self._parse(
            system=(
                "Ты — аналитик внутреннего аудита. Построй один read-only SELECT "
                "по схеме audit или выбери готовый шаблон. Значения статусов — "
                "русские строки в кавычках. Не более 200 строк."
            ),
            user=(
                f"Вопрос: {question}\n\n"
                f"Схема:\n{schema_text}\n\n"
                f"Готовые шаблоны:\n{template_lines or '(нет)'}\n\n"
                "Верни SQLPlan: strategy, template_key, parameters, sql, reason."
            ),
            schema=SQLPlan,
        )

    def repair_sql(
        self, *, question: str, sql: str, error: str, schema_text: str
    ) -> SQLPlan:
        return self._parse(
            system=(
                "Ты исправляешь read-only SELECT после ошибки PostgreSQL. "
                "Сохрани смысл вопроса и верни только безопасный SQL."
            ),
            user=(
                f"Вопрос: {question}\nSQL: {sql}\nОшибка: {error}\n"
                f"Схема:\n{schema_text}\n"
                "Верни SQLPlan со strategy=generated."
            ),
            schema=SQLPlan,
        )

    def plan_tools(self, *, question: str, tools_text: str) -> ToolPlan:
        return self._parse(
            system=(
                "Ты выбираешь инструменты для ответа аудитору. "
                "Можно выбрать несколько инструментов за один ответ."
            ),
            user=(
                f"Вопрос: {question}\nДоступные инструменты:\n{tools_text}\n"
                "Верни ToolPlan со списком calls (name, arguments)."
            ),
            schema=ToolPlan,
        )

    def summarize(
        self,
        *,
        question: str,
        columns: list[str],
        rows: list[dict[str, Any]],
    ) -> str:
        preview = rows[:20]
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "Ты — ассистент внутреннего аудитора. Ответь кратко "
                            "по-русски только по переданным данным. Не выдумывай числа."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Вопрос: {question}\nКолонки: {columns}\n"
                            f"Строки: {preview}"
                        ),
                    },
                ],
                temperature=0,
            )
            text = (response.choices[0].message.content or "").strip()
            if text:
                return text
        except Exception:
            pass
        return f"Найдено строк: {len(rows)}."

    @staticmethod
    def _chunks_text(chunks: list[dict[str, Any]]) -> str:
        lines = []
        for index, chunk in enumerate(chunks, start=1):
            lines.append(
                f"[{index}] source_type={chunk['source_type']} "
                f"source_id={chunk['source_id']} title={chunk['title']}\n"
                f"{chunk['content']}"
            )
        return "\n\n".join(lines)

    def answer_from_chunks(
        self,
        *,
        question: str,
        chunks: list[dict[str, Any]],
    ) -> RetrievalAnswer:
        return self._parse(
            system=(
                "Ты — ассистент внутреннего аудитора. Отвечай только по найденным "
                "фрагментам. Каждое утверждение подкрепи source_id из фрагмента. "
                "Если подтверждения нет — не утверждай это. Не используй общие знания."
            ),
            user=(
                f"Вопрос: {question}\n\nФрагменты:\n{self._chunks_text(chunks)}\n\n"
                "Верни RetrievalAnswer: text, citations (список source_id)."
            ),
            schema=RetrievalAnswer,
        )

    def critique_answer(
        self,
        *,
        question: str,
        answer: RetrievalAnswer,
        chunks: list[dict[str, Any]],
    ) -> Critique:
        return self._parse(
            system=(
                "Ты — критик RAG-ответа. Проверь: релевантность вопросу, "
                "подтверждённость каждого утверждения, корректность citations. "
                "Если утверждение не подтверждено — verdict=rewrite."
            ),
            user=(
                f"Вопрос: {question}\nОтвет: {answer.model_dump_json()}\n\n"
                f"Фрагменты:\n{self._chunks_text(chunks)}\n\n"
                "Верни Critique: verdict, issues, suggestions, grounded, citations_ok."
            ),
            schema=Critique,
        )

    def rewrite_answer(
        self,
        *,
        question: str,
        answer: RetrievalAnswer,
        issues: list[str],
        chunks: list[dict[str, Any]],
    ) -> RetrievalAnswer:
        return self._parse(
            system=(
                "Ты исправляешь RAG-ответ по замечаниям критика. "
                "Не добавляй факты, которых нет во фрагментах."
            ),
            user=(
                f"Вопрос: {question}\nЧерновик: {answer.model_dump_json()}\n"
                f"Замечания: {issues}\n\nФрагменты:\n{self._chunks_text(chunks)}\n\n"
                "Верни исправленный RetrievalAnswer."
            ),
            schema=RetrievalAnswer,
        )

    def draft_report(
        self,
        *,
        question: str,
        facts_text: str,
        allowed_ids: list[str],
    ) -> ReportDraft:
        return self._parse(
            system=(
                "Ты — внутренний аудитор. Составь проект раздела акта по-русски "
                "строго по фактам. Структура: вводная часть, выявленные отклонения "
                "и проблемы, рекомендации, сроки. Каждое утверждение подкрепи ID "
                "из списка. Не добавляй факты, которых нет в данных."
            ),
            user=(
                f"Запрос: {question}\n\nФакты:\n{facts_text}\n\n"
                f"Допустимые ID: {', '.join(allowed_ids)}\n\n"
                "Верни ReportDraft: text, citations."
            ),
            schema=ReportDraft,
        )

    def review_report(
        self,
        *,
        draft: ReportDraft,
        facts_text: str,
        allowed_ids: list[str],
    ) -> ReportReview:
        return self._parse(
            system=(
                "Ты — инспектор качества аудиторского акта. Проверь: каждое "
                "утверждение подтверждено фактами, все ID существуют, структура "
                "полная, чисел и выводов вне фактов нет."
            ),
            user=(
                f"Черновик: {draft.model_dump_json()}\n\nФакты:\n{facts_text}\n\n"
                f"Допустимые ID: {', '.join(allowed_ids)}\n\n"
                "Верни ReportReview: verdict, unsupported_claims, missing_sections, "
                "issues, citations_ok."
            ),
            schema=ReportReview,
        )

    def revise_report(
        self,
        *,
        draft: ReportDraft,
        review: ReportReview,
        facts_text: str,
        allowed_ids: list[str],
    ) -> ReportDraft:
        return self._parse(
            system=(
                "Ты исправляешь проект акта по замечаниям инспектора. "
                "Удаляй или смягчай неподтверждённое; не добавляй новых фактов."
            ),
            user=(
                f"Черновик: {draft.model_dump_json()}\n"
                f"Замечания: {review.model_dump_json()}\n\n"
                f"Факты:\n{facts_text}\n\n"
                f"Допустимые ID: {', '.join(allowed_ids)}\n\n"
                "Верни исправленный ReportDraft."
            ),
            schema=ReportDraft,
        )

    def plan_investigation(
        self,
        *,
        question: str,
        schema_text: str,
    ) -> InvestigationPlan:
        return self._parse(
            system=(
                "Ты — координатор аудиторского расследования. Разбей вопрос "
                "на количественную часть для Analytics и смысловую для Retrieval. "
                "Укажи, какие доказательства обязательны."
            ),
            user=(
                f"Вопрос: {question}\nСхема:\n{schema_text}\n\n"
                "Верни InvestigationPlan: analytics_question, retrieval_question, "
                "required_evidence, reason."
            ),
            schema=InvestigationPlan,
        )

    def refine_investigation(
        self,
        *,
        question: str,
        plan: InvestigationPlan,
        missing: list[str],
    ) -> InvestigationPlan:
        return self._parse(
            system=(
                "Ты уточняешь план расследования, если не хватает доказательств. "
                "Не повторяй уже выполненный запрос без изменений."
            ),
            user=(
                f"Вопрос: {question}\nПлан: {plan.model_dump_json()}\n"
                f"Не хватает: {', '.join(missing)}\n\n"
                "Верни обновлённый InvestigationPlan."
            ),
            schema=InvestigationPlan,
        )

    def synthesize_investigation(
        self,
        *,
        question: str,
        analytics: dict[str, Any],
        retrieval: dict[str, Any],
        missing: list[str],
        rounds: int,
    ) -> InvestigationAnswer:
        return self._parse(
            system=(
                "Ты синтезируешь итог расследования. Отделяй подтверждённый факт "
                "от гипотезы. Причинное утверждение допустимо только при наличии "
                "и количественных, и текстовых доказательств. Если доказательств "
                "не хватает — скажи об этом прямо."
            ),
            user=(
                f"Вопрос: {question}\nРаундов: {rounds}\n"
                f"Analytics: {analytics}\nRetrieval: {retrieval}\n"
                f"Не хватает: {', '.join(missing) or 'ничего'}\n\n"
                "Верни InvestigationAnswer: text, causal_claim."
            ),
            schema=InvestigationAnswer,
        )
