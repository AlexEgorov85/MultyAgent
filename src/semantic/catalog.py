"""Машинно-читаемый каталог метрик, измерений и допустимых значений.

Каталог — единый источник истины для:
* QueryPlan и SQL-компилятора;
* подсказки LLM о доступных метриках;
* проверки фильтров и измерений.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping

THEMES: tuple[str, ...] = ("ипотека", "потребкредитование", "платежи", "карты", "вклады")

AUDIT_STATUSES: tuple[str, ...] = ("запланирована", "в работе", "завершена", "отменена")
ACT_STATUSES: tuple[str, ...] = ("черновик", "на согласовании", "утверждён")
ITEM_TYPES: tuple[str, ...] = ("отклонение", "проблема")
ITEM_STATUSES: tuple[str, ...] = ("открыт", "в работе", "закрыт")
RISK_LEVELS: tuple[str, ...] = ("низкий", "средний", "высокий", "критический")
AUDIT_TYPES: tuple[str, ...] = (
    "плановая",
    "внеплановая",
    "тематическая",
    "повторная",
    "последующий контроль",
)
SCRIPT_LANGUAGES: tuple[str, ...] = ("SQL", "Python", "R", "Excel", "Другое")
RUN_STATUSES: tuple[str, ...] = ("успешно", "частично", "ошибка")
ENTITY_TYPES: tuple[str, ...] = ("договор", "транзакция", "карта", "счёт")

AUDIT_FROM = (
    "audit.audits a "
    "JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id"
)
AUDITOR_FROM = "audit.auditors au"
ACT_FROM = (
    "audit.acts ac "
    "JOIN audit.audits a ON a.audit_id = ac.audit_id "
    "JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id"
)
ITEM_FROM = (
    "audit.act_items i "
    "JOIN audit.acts ac ON ac.act_id = i.act_id "
    "JOIN audit.audits a ON a.audit_id = ac.audit_id "
    "JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id"
)
SCRIPT_FROM = (
    "audit.scripts s "
    "JOIN audit.act_items i ON i.item_id = s.item_id "
    "JOIN audit.acts ac ON ac.act_id = i.act_id "
    "JOIN audit.audits a ON a.audit_id = ac.audit_id "
    "JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id"
)
RUN_FROM = (
    "audit.script_runs r "
    "JOIN audit.scripts s ON s.script_id = r.script_id "
    "JOIN audit.act_items i ON i.item_id = s.item_id "
    "JOIN audit.acts ac ON ac.act_id = i.act_id "
    "JOIN audit.audits a ON a.audit_id = ac.audit_id "
    "JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id"
)
DEVIATION_FROM = (
    "audit.deviations d "
    "JOIN audit.act_items i ON i.item_id = d.item_id "
    "JOIN audit.acts ac ON ac.act_id = i.act_id "
    "JOIN audit.audits a ON a.audit_id = ac.audit_id "
    "JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id"
)

AUDIT_DIMENSIONS = {
    "year": "p.pocket_year",
    "month": (
        "to_char(date_trunc('month', "
        "COALESCE(a.end_date, a.start_date)), 'YYYY-MM')"
    ),
    "theme": "p.theme_code",
    "pocket": "p.title",
    "status": "a.status",
    "audit_type": "a.audit_type",
    "risk_level": "a.risk_level",
    "lead_auditor_id": "a.lead_auditor_id",
    "audit_code": "a.audit_code",
}
AUDITOR_DIMENSIONS = {
    "auditor_id": "au.auditor_id",
    "position": "au.position",
    "grade": "au.grade",
    "unit": "au.unit",
    "specialization": "au.specializations",
}
ACT_DIMENSIONS = {
    "year": "p.pocket_year",
    "theme": "p.theme_code",
    "pocket": "p.title",
    "status": "ac.status",
    "act_status": "ac.status",
    "audit_type": "a.audit_type",
    "risk_level": "a.risk_level",
    "approved_by": "ac.approved_by",
    "audit_code": "a.audit_code",
}
ITEM_DIMENSIONS = {
    "year": "p.pocket_year",
    "theme": "p.theme_code",
    "pocket": "p.title",
    "item_type": "i.item_type",
    "title": "i.title",
    "risk_level": "i.risk_level",
    "status": "i.status",
    "responsible_unit": "i.responsible_unit",
    "is_repeat": "i.is_repeat",
    "audit_code": "a.audit_code",
    "act_status": "ac.status",
}
SCRIPT_DIMENSIONS = {
    "year": "p.pocket_year",
    "theme": "p.theme_code",
    "pocket": "p.title",
    "language": "s.language",
    "audit_code": "a.audit_code",
    "item_type": "i.item_type",
    "risk_level": "i.risk_level",
}
RUN_DIMENSIONS = {
    "year": "p.pocket_year",
    "theme": "p.theme_code",
    "pocket": "p.title",
    "status": "r.status",
    "run_status": "r.status",
    "language": "s.language",
    "audit_code": "a.audit_code",
}
DEVIATION_DIMENSIONS = {
    "year": "p.pocket_year",
    "theme": "p.theme_code",
    "pocket": "p.title",
    "severity": "d.severity",
    "entity_type": "d.entity_type",
    "metric_name": "d.metric_name",
    "title": "i.title",
    "audit_code": "a.audit_code",
    "item_type": "i.item_type",
    "risk_level": "i.risk_level",
}


@dataclass(frozen=True)
class MetricSpec:
    """Метрика и её SQL-основа."""

    id: str
    title: str
    from_sql: str
    dimensions: Mapping[str, str]
    count_expr: str = "count(*)"
    extra_where: tuple[str, ...] = field(default_factory=tuple)
    allowed_values: Mapping[str, tuple[str, ...]] = field(default_factory=dict)
    description: str = ""
    required_dimensions: tuple[str, ...] = ()
    single_row: bool = False


METRICS: dict[str, MetricSpec] = {
    "audit_count": MetricSpec(
        id="audit_count",
        title="Количество проверок",
        from_sql=AUDIT_FROM,
        dimensions=AUDIT_DIMENSIONS,
        allowed_values={
            "status": AUDIT_STATUSES,
            "audit_type": AUDIT_TYPES,
            "risk_level": RISK_LEVELS,
            "theme": THEMES,
        },
        description="Считает проверки в audit.audits.",
    ),
    "auditor_count": MetricSpec(
        id="auditor_count",
        title="Количество аудиторов",
        from_sql=AUDITOR_FROM,
        dimensions=AUDITOR_DIMENSIONS,
        allowed_values={
            "specialization": THEMES,
        },
        description=(
            "Считает аудиторов. Для специализации используй filter "
            "specialization с op=contains."
        ),
    ),
    "act_count": MetricSpec(
        id="act_count",
        title="Количество актов",
        from_sql=ACT_FROM,
        dimensions=ACT_DIMENSIONS,
        allowed_values={
            "status": ACT_STATUSES,
            "act_status": ACT_STATUSES,
            "audit_type": AUDIT_TYPES,
            "risk_level": RISK_LEVELS,
            "theme": THEMES,
        },
        description="Считает акты в audit.acts.",
    ),
    "item_count": MetricSpec(
        id="item_count",
        title="Количество пунктов",
        from_sql=ITEM_FROM,
        dimensions=ITEM_DIMENSIONS,
        allowed_values={
            "item_type": ITEM_TYPES,
            "risk_level": RISK_LEVELS,
            "status": ITEM_STATUSES,
            "theme": THEMES,
            "act_status": ACT_STATUSES,
        },
        description="Считает пункты актов в audit.act_items.",
    ),
    "critical_item_count": MetricSpec(
        id="critical_item_count",
        title="Критические пункты",
        from_sql=ITEM_FROM,
        dimensions=ITEM_DIMENSIONS,
        extra_where=("i.risk_level = 'критический'",),
        allowed_values={
            "item_type": ITEM_TYPES,
            "status": ITEM_STATUSES,
            "theme": THEMES,
            "act_status": ACT_STATUSES,
        },
        description="Пункты с risk_level = критический.",
    ),
    "overdue_item_count": MetricSpec(
        id="overdue_item_count",
        title="Просроченные незакрытые пункты",
        from_sql=ITEM_FROM,
        dimensions=ITEM_DIMENSIONS,
        extra_where=(
            "i.status <> 'закрыт'",
            "i.deadline < audit.as_of_date()",
        ),
        allowed_values={
            "risk_level": RISK_LEVELS,
            "theme": THEMES,
            "item_type": ITEM_TYPES,
            "status": ITEM_STATUSES,
        },
        description="Открытые/в работе пункты с истёкшим deadline на as_of_date.",
    ),
    "repeat_item_count": MetricSpec(
        id="repeat_item_count",
        title="Повторные находки",
        from_sql=ITEM_FROM,
        dimensions=ITEM_DIMENSIONS,
        extra_where=("i.is_repeat = TRUE",),
        allowed_values={
            "risk_level": RISK_LEVELS,
            "theme": THEMES,
            "item_type": ITEM_TYPES,
            "status": ITEM_STATUSES,
        },
        description="Пункты с is_repeat = true.",
    ),
    "no_script_item_count": MetricSpec(
        id="no_script_item_count",
        title="Пункты без скриптов",
        from_sql=ITEM_FROM,
        dimensions=ITEM_DIMENSIONS,
        extra_where=(
            "NOT EXISTS ("
            "SELECT 1 FROM audit.scripts s2 WHERE s2.item_id = i.item_id"
            ")",
        ),
        allowed_values={
            "risk_level": RISK_LEVELS,
            "theme": THEMES,
            "item_type": ITEM_TYPES,
            "status": ITEM_STATUSES,
        },
        description="Пункты без ни одного скрипта-доказательства.",
    ),
    "script_count": MetricSpec(
        id="script_count",
        title="Количество скриптов",
        from_sql=SCRIPT_FROM,
        dimensions=SCRIPT_DIMENSIONS,
        allowed_values={
            "language": SCRIPT_LANGUAGES,
            "theme": THEMES,
            "item_type": ITEM_TYPES,
            "risk_level": RISK_LEVELS,
        },
        description="Считает скрипты в audit.scripts.",
    ),
    "run_count": MetricSpec(
        id="run_count",
        title="Количество запусков скриптов",
        from_sql=RUN_FROM,
        dimensions=RUN_DIMENSIONS,
        allowed_values={
            "status": RUN_STATUSES,
            "run_status": RUN_STATUSES,
            "language": SCRIPT_LANGUAGES,
            "theme": THEMES,
        },
        description="Считает запуски в audit.script_runs.",
    ),
    "run_script_mismatch_count": MetricSpec(
        id="run_script_mismatch_count",
        title="Расхождения запуска и скрипта",
        from_sql=RUN_FROM,
        dimensions=RUN_DIMENSIONS,
        extra_where=("r.rows_found <> s.rows_found",),
        allowed_values={
            "status": RUN_STATUSES,
            "language": SCRIPT_LANGUAGES,
            "theme": THEMES,
        },
        description="Запуски, где rows_found отличается от scripts.rows_found.",
    ),
    "deviation_count": MetricSpec(
        id="deviation_count",
        title="Количество отклонений",
        from_sql=DEVIATION_FROM,
        dimensions=DEVIATION_DIMENSIONS,
        allowed_values={
            "severity": RISK_LEVELS,
            "entity_type": ENTITY_TYPES,
            "theme": THEMES,
            "item_type": ITEM_TYPES,
        },
        description=(
            "Считает записи audit.deviations. Для пунктов-отклонений в актах "
            "используй item_count с filter item_type=отклонение."
        ),
    ),
    "deviation_gap_max": MetricSpec(
        id="deviation_gap_max",
        title="Максимальное отклонение",
        from_sql=DEVIATION_FROM,
        dimensions=DEVIATION_DIMENSIONS,
        count_expr="max(abs(d.metric_value - d.threshold_value))",
        allowed_values={
            "severity": RISK_LEVELS,
            "entity_type": ENTITY_TYPES,
            "theme": THEMES,
            "item_type": ITEM_TYPES,
        },
        description=(
            "Крупнейшее отклонение: максимальный разрыв между фактическим "
            "(metric_value) и пороговым (threshold_value) значением. Для "
            "вопроса «какое отклонение самое крупное» используй "
            "dimensions=[title, audit_code, severity, metric_name], "
            "order_by=count_desc, limit=1."
        ),
        required_dimensions=("title", "audit_code"),
        single_row=True,
    ),
}

CATALOG = METRICS


def get_metric(metric_id: str) -> MetricSpec:
    """Возвращает метрику или бросает KeyError."""
    if metric_id not in METRICS:
        raise KeyError(
            f"Неизвестная метрика {metric_id!r}. Доступны: {', '.join(METRICS)}"
        )
    return METRICS[metric_id]


def metric_ids() -> tuple[str, ...]:
    """Возвращает все id метрик каталога."""
    return tuple(METRICS)


def allowed_values(metric_id: str, field_name: str) -> tuple[str, ...]:
    """Допустимые значения измерения для метрики (пусто, если не заданы)."""
    spec = get_metric(metric_id)
    return tuple(spec.allowed_values.get(field_name, ()))


def catalog_text() -> str:
    """Текст каталога для structured-output планировщика."""
    lines = [
        "Метрики (используй только эти id):",
    ]
    for metric in METRICS.values():
        dims = ", ".join(metric.dimensions)
        lines.append(f"- {metric.id}: {metric.title}. Измерения: {dims}.")
        if metric.description:
            lines.append(f"  {metric.description}")
    lines += [
        "",
        "Допустимые значения:",
        f"- theme: {', '.join(THEMES)}",
        f"- audit status: {', '.join(AUDIT_STATUSES)}",
        f"- act status: {', '.join(ACT_STATUSES)}",
        f"- item_type: {', '.join(ITEM_TYPES)}",
        f"- item status: {', '.join(ITEM_STATUSES)}",
        f"- risk_level / severity: {', '.join(RISK_LEVELS)}",
        f"- audit_type: {', '.join(AUDIT_TYPES)}",
        f"- language: {', '.join(SCRIPT_LANGUAGES)}",
        f"- run status: {', '.join(RUN_STATUSES)}",
        f"- entity_type: {', '.join(ENTITY_TYPES)}",
        "",
        "Правила:",
        "- dimensions — только из списка метрики;",
        "- filters — year, theme, status, item_type, risk_level, language,",
        "  run_status, severity, entity_type, metric_name, audit_code,",
        "  responsible_unit, audit_type, act_status, lead_auditor_id,",
        "  approved_by, is_repeat;",
        "- не придумывай SQL, колонки и метрики;",
        "- «карман» — это измерение pocket (год + тема), а не status;",
        "- «по темам/годам/карманам/статусам» — это dimensions, а не фильтр;",
        "- «за последний год» — filter year=last, а не догадка о конкретном годе;",
        "- для одного года/темы/статуса используй filters;",
        "- «закрытая проверка» — status=завершена, «закрытый пункт» —",
        "  status=закрыт;",
        "- если объект вопроса не назван, считай проверки (audit_count):",
        "  это основная сущность аудита;",
        "- для специализации аудитора: field=specialization, op=contains;",
        "- для топа видов отклонений: dimensions=[title], limit=5.",
        "",
        "Примеры:",
        "- «Сколько завершённых проверок по ипотеке в 2026?» →",
        "  metric=audit_count, filters=[year=2026, theme=ипотека, status=завершена]",
        "- «Сколько закрыто проверок за последний год по каждому карману?» →",
        "  metric=audit_count, dimensions=[pocket],",
        "  filters=[year=last, status=завершена]",
        "- «Сколько отклонений и проблем в 2026?» →",
        "  metric=item_count, dimensions=[item_type], filters=[year=2026]",
        "- «Сколько отклонений по ипотеке в 2026?» →",
        "  metric=item_count, filters=[year=2026, theme=ипотека,",
        "  item_type=отклонение]",
        "- «Сколько отклонений каждого уровня критичности?» →",
        "  metric=deviation_count, dimensions=[severity]",
        "- «Какая тема дала больше всего критических отклонений в 2026?» →",
        "  metric=deviation_count, dimensions=[theme],",
        "  filters=[year=2026, severity=критический]",
        "- «Закрытые проверки по месяцам за последние 2 года» →",
        "  metric=audit_count, dimensions=[month],",
        "  filters=[status=завершена, year=last_2]",
        "- «Топ-5 видов отклонений» →",
        "  metric=deviation_count, dimensions=[title], limit=5",
        "- «Сколько аудиторов специализируются на ипотеке?» →",
        "  metric=auditor_count, filters=[specialization=ипотека op=contains]",
    ]
    return "\n".join(lines)

METRIC_LABELS: dict[str, str] = {
    "audit_count": "Проверок",
    "auditor_count": "Аудиторов",
    "act_count": "Актов",
    "item_count": "Пунктов",
    "critical_item_count": "Критических пунктов",
    "overdue_item_count": "Просроченных пунктов",
    "repeat_item_count": "Повторных пунктов",
    "no_script_item_count": "Пунктов без скриптов",
    "script_count": "Скриптов",
    "run_count": "Запусков скриптов",
    "run_script_mismatch_count": "Запусков с расхождением",
    "deviation_count": "Отклонений",
    "deviation_gap_max": "Разрыв с порогом",
}


def metric_label(metric_id: str) -> str:
    """Короткое название того, что посчитано, для ответа пользователю."""
    return METRIC_LABELS.get(str(metric_id or "").strip(), "")

