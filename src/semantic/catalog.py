"""Машинно-читаемый каталог метрик, измерений и допустимых значений.

Каталог — единый источник истины для:
* QueryPlan и SQL-компилятора;
* подсказки LLM о доступных метриках;
* проверки фильтров и измерений.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

THEMES: tuple[str, ...] = ("ипотека", "потребкредитование", "платежи", "карты", "вклады")

# Доменный лексикон тем. Это не замена LLM, а проверка явного упоминания:
# модель регулярно теряет фильтр темы, а бенчмарк показывает неверные числа.
# Формы слов и исключения нужны для омонимов («картина» ≠ «карты»).
_THEME_FORMS: dict[str, str] = {
    "ипотека": r"ипотечн\w*|ипотек(?:а|и|е|у|ой|ою|ам|ами|ах)?",
    "потребкредитование": r"потребкредит\w*|потребительск\w*\s+кредит\w*",
    "платежи": r"платеж(?:а|у|е|и|ей|ам|ами|ах|ом|ем)?|платежн\w*",
    "карты": r"карт(?:а|ы|е|у|ой|ою|ам|ами|ах)?|карточн\w*",
    "вклады": r"вклад(?:а|у|ом|е|ы|ов|ам|ами|ах)?|вкладчик\w*|вкладчиц\w*",
}
_THEME_PATTERNS: dict[str, re.Pattern[str]] = {
    theme: re.compile(rf"(?<![а-яё])(?:{forms})(?![а-яё])", re.IGNORECASE)
    for theme, forms in _THEME_FORMS.items()
}
_THEME_EXCLUSIONS: dict[str, tuple[re.Pattern[str], ...]] = {
    "карты": (
        re.compile(r"карт\w*\s+провер(?:ки|ок|кам|ками|ках)", re.IGNORECASE),
        re.compile(r"карт\w*\s+риск(?:а|ов|ам|ами|ах)?", re.IGNORECASE),
        re.compile(r"карт\w*\s+местности", re.IGNORECASE),
        re.compile(r"дорожн\w*\s+карт\w*", re.IGNORECASE),
        re.compile(r"игральн\w*\s+карт\w*", re.IGNORECASE),
    ),
}


def _normalise_text(text: str) -> str:
    return " ".join(str(text or "").lower().replace("ё", "е").split())


def theme_in_text(theme: str, text: str) -> bool:
    """Упоминается ли тема целым словом с учётом падежей и омонимов."""
    value = str(theme or "").strip().lower()
    cleaned = _normalise_text(text)
    if not value or not cleaned:
        return False
    pattern = _THEME_PATTERNS.get(value)
    if pattern is None:
        return value in cleaned
    for rule in _THEME_EXCLUSIONS.get(value, ()):
        cleaned = rule.sub(" ", cleaned)
    return bool(pattern.search(cleaned))


def find_themes(text: str) -> tuple[str, ...]:
    return tuple(theme for theme in THEMES if theme_in_text(theme, text))


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
        description="Считает отклонения в audit.deviations.",
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
        "- «Сколько отклонений каждого уровня критичности?» →",
        "  metric=deviation_count, dimensions=[severity]",
        "- «Топ-5 видов отклонений» →",
        "  metric=deviation_count, dimensions=[title], limit=5",
        "- «Сколько аудиторов специализируются на ипотеке?» →",
        "  metric=auditor_count, filters=[specialization=ипотека op=contains]",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Доменный язык → типизированные сигналы запроса
# ---------------------------------------------------------------------------
#
# LLM хорошо понимает смысл, но её structured output нестабилен: она может
# вернуть пустые dimensions/filters или выбрать шаблон, который не покрывает
# вопрос. Эти сигналы — детерминированное дополнение плана по каталогу.
# Это не подбор под конкретную фразу: правила описывают доменные измерения и
# значения из semantic layer, а неизвестные конструкции остаются LLM.

_AUDIT_CODE_RE = re.compile(r"AUD-\d{4}-[A-Z]+-\d{2}", re.IGNORECASE)
_EXPLICIT_YEAR_RE = re.compile(r"\b(20\d{2})\b")
_LATEST_YEAR_RE = re.compile(
    r"(?<![а-яё])(?:за\s+)?последн\w*\s+(?:год|12\s+мес\w*)"
    r"|(?<![a-zа-яё])last\s+year(?![a-zа-яё])",
    re.IGNORECASE,
)

_CLOSED_AUDIT = r"(?<![а-яё])(?<!не\s)(?:закрыт|заверш)\w*"
_CLOSED_ITEM = r"(?<![а-яё])(?<!не\s)закрыт\w*"
_OPEN_ITEM = r"(?<![а-яё])(?<!не\s)открыт\w*"
_CANCELED = r"(?<![а-яё])(?<!не\s)отмен\w*"
_PLANNED = r"(?<![а-яё])(?<!не\s)запланирован\w*"
_IN_PROGRESS = r"(?<![а-яё])(?<!не\s)в\s+работе"
_APPROVED = r"(?<![а-яё])(?<!не\s)утвержд\w*"
_ON_APPROVAL = r"(?<![а-яё])на\s+согласовани\w*|(?<![а-яё])согласу\w*"
_DRAFT = r"(?<![а-яё])черновик\w*"
_ERROR = r"(?<![а-яё])ошибк\w*"
_SUCCESS = r"(?<![а-яё])успешн\w*"
_PARTIAL = r"(?<![а-яё])частичн\w*"
_DEVIATION = r"(?<![а-яё])отклонен\w*"
_PROBLEM = r"(?<![а-яё])проблем\w*"
_CRITICAL = r"(?<![а-яё])критич\w*"
_HIGH = r"(?<![а-яё])высок\w*"
_MEDIUM = r"(?<![а-яё])средн\w*"
_LOW = r"(?<![а-яё])низк\w*"


@dataclass(frozen=True)
class DimensionCue:
    """Явный запрос разреза: «по карманам», «по годам» и т.п."""

    label: str
    pattern: re.Pattern[str]
    candidates: tuple[str, ...]

    def dimension(self, spec: MetricSpec | None) -> str | None:
        for candidate in self.candidates:
            if spec is None or candidate in spec.dimensions:
                return candidate
        return None


@dataclass(frozen=True)
class FilterCue:
    """Доменное значение, которое в вопросе означает фильтр."""

    field: str
    value: str
    pattern: re.Pattern[str]


DIMENSION_CUES: tuple[DimensionCue, ...] = (
    DimensionCue(
        "разбивка по карманам",
        re.compile(
            r"(?<![а-яё])карманам\b"
            r"|(?<![а-яё])карманах\b"
            r"|(?<![а-яё])карманы\b"
            r"|(?<![а-яё])по\s+каждому\s+карману\b"
            r"|(?<![а-яё])в\s+разрезе\s+карман\w*",
            re.IGNORECASE,
        ),
        ("pocket",),
    ),
    DimensionCue(
        "разбивка по годам",
        re.compile(
            r"(?<![а-яё])по\s+годам\b"
            r"|(?<![а-яё])по\s+каждому\s+году\b"
            r"|(?<![а-яё])в\s+разрезе\s+год\w*",
            re.IGNORECASE,
        ),
        ("year",),
    ),
    DimensionCue(
        "разбивка по темам",
        re.compile(
            r"(?<![а-яё])по\s+темам\b"
            r"|(?<![а-яё])по\s+каждой\s+теме\b"
            r"|(?<![а-яё])в\s+разрезе\s+тем\w*",
            re.IGNORECASE,
        ),
        ("theme",),
    ),
    DimensionCue(
        "разбивка по статусам",
        re.compile(
            r"(?<![а-яё])по\s+статусам\b"
            r"|(?<![а-яё])по\s+каждому\s+статусу\b"
            r"|(?<![а-яё])в\s+разрезе\s+статус\w*",
            re.IGNORECASE,
        ),
        ("status", "act_status", "run_status"),
    ),
    DimensionCue(
        "разбивка по типам находок",
        re.compile(
            r"(?<![а-яё])по\s+типам\s+находок\b"
            r"|(?<![а-яё])по\s+типу\s+находк\w*",
            re.IGNORECASE,
        ),
        ("item_type",),
    ),
    DimensionCue(
        "разбивка по типам проверок",
        re.compile(
            r"(?<![а-яё])по\s+типам\s+провер\w*"
            r"|(?<![а-яё])по\s+типу\s+провер\w*",
            re.IGNORECASE,
        ),
        ("audit_type",),
    ),
    DimensionCue(
        "разбивка по типам",
        re.compile(r"(?<![а-яё])по\s+типам\b", re.IGNORECASE),
        ("item_type", "audit_type"),
    ),
    DimensionCue(
        "разбивка по уровню риска",
        re.compile(
            r"(?<![а-яё])по\s+уровн\w*\s+риска\b"
            r"|(?<![а-яё])по\s+риску\b"
            r"|(?<![а-яё])по\s+каждому\s+уровн\w*",
            re.IGNORECASE,
        ),
        ("risk_level", "severity"),
    ),
    DimensionCue(
        "разбивка по уровню критичности",
        re.compile(
            r"(?<![а-яё])по\s+уровн\w*\s+критичности\b"
            r"|(?<![а-яё])по\s+критичности\b",
            re.IGNORECASE,
        ),
        ("severity", "risk_level"),
    ),
    DimensionCue(
        "разбивка по языкам",
        re.compile(
            r"(?<![а-яё])по\s+языкам\b|(?<![а-яё])по\s+языку\b",
            re.IGNORECASE,
        ),
        ("language",),
    ),
    DimensionCue(
        "разбивка по специализациям",
        re.compile(
            r"(?<![а-яё])по\s+специализаци\w*",
            re.IGNORECASE,
        ),
        ("specialization",),
    ),
    DimensionCue(
        "разбивка по проверкам",
        re.compile(
            r"(?<![а-яё])по\s+проверкам\b"
            r"|(?<![а-яё])по\s+каждой\s+проверке\b",
            re.IGNORECASE,
        ),
        ("audit_code",),
    ),
    DimensionCue(
        "топ формулировок",
        re.compile(
            r"(?<![а-яё])топ\s*[-‑]?\s*\d*\s*(?:видов|формулировок)",
            re.IGNORECASE,
        ),
        ("title",),
    ),
)


def _cue(field: str, value: str, pattern: str) -> FilterCue:
    return FilterCue(field, value, re.compile(pattern, re.IGNORECASE))


FILTER_CUES: dict[str, tuple[FilterCue, ...]] = {
    "audit_count": (
        _cue("status", "завершена", _CLOSED_AUDIT),
        _cue("status", "отменена", _CANCELED),
        _cue("status", "запланирована", _PLANNED),
        _cue("status", "в работе", _IN_PROGRESS),
        _cue("risk_level", "критический", _CRITICAL),
        _cue("risk_level", "высокий", _HIGH),
        _cue("risk_level", "средний", _MEDIUM),
        _cue("risk_level", "низкий", _LOW),
    ),
    "act_count": (
        _cue("status", "утверждён", _APPROVED),
        _cue("status", "на согласовании", _ON_APPROVAL),
        _cue("status", "черновик", _DRAFT),
        _cue("risk_level", "критический", _CRITICAL),
        _cue("risk_level", "высокий", _HIGH),
        _cue("risk_level", "средний", _MEDIUM),
        _cue("risk_level", "низкий", _LOW),
    ),
    "item_count": (
        _cue("status", "закрыт", _CLOSED_ITEM),
        _cue("status", "открыт", _OPEN_ITEM),
        _cue("status", "в работе", _IN_PROGRESS),
        _cue("item_type", "отклонение", _DEVIATION),
        _cue("item_type", "проблема", _PROBLEM),
        _cue("risk_level", "критический", _CRITICAL),
        _cue("risk_level", "высокий", _HIGH),
        _cue("risk_level", "средний", _MEDIUM),
        _cue("risk_level", "низкий", _LOW),
    ),
    "critical_item_count": (
        _cue("status", "закрыт", _CLOSED_ITEM),
        _cue("status", "открыт", _OPEN_ITEM),
        _cue("status", "в работе", _IN_PROGRESS),
        _cue("item_type", "отклонение", _DEVIATION),
        _cue("item_type", "проблема", _PROBLEM),
        _cue("risk_level", "высокий", _HIGH),
        _cue("risk_level", "средний", _MEDIUM),
        _cue("risk_level", "низкий", _LOW),
    ),
    "overdue_item_count": (
        _cue("item_type", "отклонение", _DEVIATION),
        _cue("item_type", "проблема", _PROBLEM),
        _cue("risk_level", "критический", _CRITICAL),
        _cue("risk_level", "высокий", _HIGH),
        _cue("risk_level", "средний", _MEDIUM),
        _cue("risk_level", "низкий", _LOW),
    ),
    "repeat_item_count": (
        _cue("item_type", "отклонение", _DEVIATION),
        _cue("item_type", "проблема", _PROBLEM),
        _cue("risk_level", "критический", _CRITICAL),
        _cue("risk_level", "высокий", _HIGH),
        _cue("risk_level", "средний", _MEDIUM),
        _cue("risk_level", "низкий", _LOW),
    ),
    "no_script_item_count": (
        _cue("item_type", "отклонение", _DEVIATION),
        _cue("item_type", "проблема", _PROBLEM),
        _cue("risk_level", "критический", _CRITICAL),
        _cue("risk_level", "высокий", _HIGH),
        _cue("risk_level", "средний", _MEDIUM),
        _cue("risk_level", "низкий", _LOW),
    ),
    "script_count": (
        _cue("item_type", "отклонение", _DEVIATION),
        _cue("item_type", "проблема", _PROBLEM),
        _cue("risk_level", "критический", _CRITICAL),
        _cue("risk_level", "высокий", _HIGH),
        _cue("risk_level", "средний", _MEDIUM),
        _cue("risk_level", "низкий", _LOW),
    ),
    "run_count": (
        _cue("status", "ошибка", _ERROR),
        _cue("status", "успешно", _SUCCESS),
        _cue("status", "частично", _PARTIAL),
    ),
    "run_script_mismatch_count": (
        _cue("status", "ошибка", _ERROR),
        _cue("status", "успешно", _SUCCESS),
        _cue("status", "частично", _PARTIAL),
    ),
    "deviation_count": (
        _cue("severity", "критический", _CRITICAL),
        _cue("severity", "высокий", _HIGH),
        _cue("severity", "средний", _MEDIUM),
        _cue("severity", "низкий", _LOW),
        _cue("item_type", "отклонение", _DEVIATION),
        _cue("item_type", "проблема", _PROBLEM),
    ),
    "auditor_count": (),
}

LANGUAGE_CUES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("SQL", re.compile(r"(?<![a-zа-яё])sql(?![a-zа-яё])", re.IGNORECASE)),
    ("Python", re.compile(r"(?<![a-zа-яё])python(?![a-zа-яё])", re.IGNORECASE)),
    ("Excel", re.compile(r"(?<![a-zа-яё])excel(?![a-zа-яё])", re.IGNORECASE)),
    ("R", re.compile(r"(?<![a-zа-яё])r(?![a-zа-яё])", re.IGNORECASE)),
    ("Другое", re.compile(r"(?<![а-яё])друг\w*", re.IGNORECASE)),
)


@dataclass(frozen=True)
class QuerySignalFilter:
    """Фильтр, выведенный из доменного языка вопроса."""

    field: str
    value: Any
    op: str = "eq"


@dataclass(frozen=True)
class QuestionSignals:
    """Что вопрос явно просит посчитать и как разрезать."""

    dimensions: tuple[str, ...] = ()
    filters: tuple[QuerySignalFilter, ...] = ()
    latest_year: bool = False
    years: tuple[int, ...] = ()
    unsupported: tuple[str, ...] = ()


def _dedupe(items: Sequence[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(items))


def question_signals(
    text: str,
    spec: MetricSpec | None = None,
) -> QuestionSignals:
    """Извлекает разрезы, фильтры и период из текста вопроса.

    ``spec=None`` используется для проверки чужого SQL (шаблона): тогда
    доступны только структурные сигналы, а доменные значения проверяет
    вызывающая сторона через каталог метрики.
    """
    normalized = _normalise_text(text)
    if not normalized:
        return QuestionSignals()

    dimensions: list[str] = []
    unsupported: list[str] = []

    for cue in DIMENSION_CUES:
        if not cue.pattern.search(normalized):
            continue
        dimension = cue.dimension(spec)
        if dimension is None:
            unsupported.append(cue.label)
        elif dimension not in dimensions:
            dimensions.append(dimension)

    years = tuple(
        sorted({int(year) for year in _EXPLICIT_YEAR_RE.findall(normalized)})
    )
    filters: list[QuerySignalFilter] = []

    if "year" not in dimensions:
        if len(years) > 1:
            if spec is None or "year" in spec.dimensions:
                dimensions.append("year")
            else:
                unsupported.append("разбивка по годам")
        elif len(years) == 1:
            filters.append(QuerySignalFilter("year", years[0]))

    latest_year = bool(_LATEST_YEAR_RE.search(normalized)) and not years
    if latest_year and "year" not in dimensions:
        if spec is None or "year" in spec.dimensions:
            filters.append(QuerySignalFilter("year", "last"))
        else:
            unsupported.append("период «последний год»")

    if spec is not None:
        by_field: dict[str, dict[str, str]] = {}
        for cue in FILTER_CUES.get(spec.id, ()):
            if cue.pattern.search(normalized):
                by_field.setdefault(cue.field, {})[cue.value] = cue.value

        for field, values in by_field.items():
            if field in dimensions:
                continue
            if field not in spec.dimensions:
                unsupported.append(f"фильтр по полю {field}")
                continue
            if len(values) > 1:
                dimensions.append(field)
            else:
                filters.append(QuerySignalFilter(field, next(iter(values))))

        themes = find_themes(normalized)
        if themes:
            if spec.id == "auditor_count" and "specialization" in spec.dimensions:
                if len(themes) > 1 and "specialization" not in dimensions:
                    dimensions.append("specialization")
                elif len(themes) == 1 and "specialization" not in dimensions:
                    filters.append(
                        QuerySignalFilter(
                            "specialization", themes[0], op="contains"
                        )
                    )
            elif "theme" in spec.dimensions and "theme" not in dimensions:
                if len(themes) > 1:
                    dimensions.append("theme")
                else:
                    filters.append(QuerySignalFilter("theme", themes[0]))

        languages = [
            value
            for value, pattern in LANGUAGE_CUES
            if pattern.search(normalized)
        ]
        if languages and "language" in spec.dimensions and "language" not in dimensions:
            if len(languages) > 1:
                dimensions.append("language")
            else:
                filters.append(QuerySignalFilter("language", languages[0]))

    codes = tuple(dict.fromkeys(code.upper() for code in _AUDIT_CODE_RE.findall(text)))
    if codes:
        if len(codes) == 1:
            if spec is None or "audit_code" in spec.dimensions:
                filters.append(QuerySignalFilter("audit_code", codes[0]))
            else:
                unsupported.append("фильтр по коду проверки")
        elif spec is None or "audit_code" in spec.dimensions:
            dimensions.append("audit_code")
        else:
            unsupported.append("разбивка по проверкам")

    return QuestionSignals(
        dimensions=_dedupe(dimensions),
        filters=tuple(filters),
        latest_year=latest_year,
        years=years,
        unsupported=_dedupe(unsupported),
    )
