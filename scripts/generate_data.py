"""Детерминированная генерация синтетических данных аудита.

Запуск:
    .venv\\Scripts\\python.exe scripts\\generate_data.py [--deviations]

Результат: CSV-файлы в data/seed/ (загружаются scripts/init_db.py --seed),
методические документы в data/knowledge/, манифест с seed и checksum.

Все содержательные данные — на русском (см. ПЛАН_ПРОЕКТА.md, 14.12.0).
Латиница допустима только в технических кодах, email и коде скриптов.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEED_DIR = ROOT / "data" / "seed"
KNOWLEDGE_DIR = ROOT / "data" / "knowledge"

SEED = 42
TODAY = date(2026, 11, 21)

YEARS = (2025, 2026)

# --------------------------------------------------------------------------
# Содержание домена
# --------------------------------------------------------------------------

THEMES: dict[str, dict] = {
    "ипотека": {
        "title": "Ипотечное кредитование",
        "owner": "Департамент ипотечного кредитования",
        "suffix": "MORTGAGE",
        "tables": ["mortgage.applications", "mortgage.collateral_valuations"],
        "entity": "договор",
        "findings": [
            {
                "title": "Просроченная актуализация оценки залога",
                "test": "Проверить, что по 100% действующих ипотечных договоров оценка залога актуализирована не реже одного раза в 12 месяцев.",
                "criterion": "п. 4.3 Регламента оценки залога",
                "metric": "срок с последней оценки, дней",
                "unit": "договоров",
                "field": "days_since_valuation",
            },
            {
                "title": "Превышение максимального уровня LTV",
                "test": "Проверить, что отношение суммы кредита к стоимости залога не превышает 80% на дату выдачи.",
                "criterion": "п. 2.1 Кредитной политики по ипотеке",
                "metric": "уровень LTV, %",
                "unit": "договоров",
                "field": "ltv_ratio",
            },
            {
                "title": "Выдача кредита при неполном пакете документов",
                "test": "Проверить наличие полного пакета документов по каждому выданному ипотечному кредиту.",
                "criterion": "п. 3.4 Регламента кредитования",
                "metric": "отсутствующих документов, шт.",
                "unit": "договоров",
                "field": "missing_docs",
                "kind": "проблема",
            },
            {
                "title": "Несоответствие дохода заёмщика подтверждающим документам",
                "test": "Сверить заявленный доход заёмщика с данными справок и выписок.",
                "criterion": "п. 3.7 Методики оценки платёжеспособности",
                "metric": "отклонение дохода, %",
                "unit": "заявок",
                "field": "income_gap_pct",
            },
            {
                "title": "Просроченная регистрация ипотеки",
                "test": "Проверить, что ипотека зарегистрирована не позднее 30 календарных дней с даты выдачи кредита.",
                "criterion": "п. 5.2 Регламента сопровождения сделки",
                "metric": "дней до регистрации",
                "unit": "договоров",
                "field": "days_to_registration",
            },
            {
                "title": "Отсутствие страхования предмета залога",
                "test": "Проверить наличие действующего договора страхования залога на отчётную дату.",
                "criterion": "п. 4.6 Регламента оценки залога",
                "metric": "дней без страхования",
                "unit": "договоров",
                "field": "days_without_insurance",
            },
            {
                "title": "Некорректный расчёт полной стоимости кредита",
                "test": "Пересчитать полную стоимость кредита и сравнить с расчётом в АБС.",
                "criterion": "п. 6.1 Методики расчёта ПСК",
                "metric": "отклонение ПСК, п.п.",
                "unit": "договоров",
                "field": "psc_deviation_pp",
                "kind": "проблема",
            },
            {
                "title": "Досрочное погашение с нарушением очерёдности",
                "test": "Проверить очерёдность списания средств при частичном досрочном погашении.",
                "criterion": "п. 7.3 Регламента обслуживания кредитов",
                "metric": "сумма неверно распределена, руб.",
                "unit": "платежей",
                "field": "misallocated_amount",
            },
        ],
    },
    "потребкредитование": {
        "title": "Потребительское кредитование",
        "owner": "Департамент розничного кредитования",
        "suffix": "CONSUMER",
        "tables": ["retail.loans", "retail.applications"],
        "entity": "договор",
        "findings": [
            {
                "title": "Превышение предельной долговой нагрузки",
                "test": "Проверить, что показатель долговой нагрузки заёмщика не превышает 80%.",
                "criterion": "п. 2.4 Кредитной политики по рознице",
                "metric": "ПДН, %",
                "unit": "договоров",
                "field": "dti_ratio",
            },
            {
                "title": "Выдача кредита без согласия на запрос кредитной истории",
                "test": "Проверить наличие согласия заёмщика на запрос кредитной истории в каждом кредитном деле.",
                "criterion": "п. 3.2 Регламента кредитования",
                "metric": "отсутствующих согласий, шт.",
                "unit": "заявок",
                "field": "missing_consents",
                "kind": "проблема",
            },
            {
                "title": "Некорректная категория качества ссуды",
                "test": "Пересчитать категорию качества и сравнить с учётной системой.",
                "criterion": "п. 4.1 Положения о классификации ссуд",
                "metric": "расхождений категорий, шт.",
                "unit": "договоров",
                "field": "quality_mismatch",
            },
            {
                "title": "Просроченная актуализация финансового положения заёмщика",
                "test": "Проверить актуальность данных о финансовом положении заёмщика.",
                "criterion": "п. 4.5 Регламента мониторинга",
                "metric": "месяцев с актуализации",
                "unit": "договоров",
                "field": "months_since_update",
            },
            {
                "title": "Отсутствие проверки по спискам ПОД/ФТ",
                "test": "Проверить, что каждый заёмщик проверен по спискам до выдачи кредита.",
                "criterion": "п. 8.1 Правил внутреннего контроля",
                "metric": "непроверенных заявок, шт.",
                "unit": "заявок",
                "field": "missing_screening",
                "kind": "проблема",
            },
            {
                "title": "Нецелевое использование кредита",
                "test": "Проверить подтверждение целевого использования средств по кредитам с целевым назначением.",
                "criterion": "п. 5.6 Регламента сопровождения",
                "metric": "сумма без подтверждения, руб.",
                "unit": "договоров",
                "field": "unconfirmed_amount",
            },
            {
                "title": "Ошибки в расчёте эффективной ставки",
                "test": "Пересчитать эффективную ставку и сравнить со значением в договоре.",
                "criterion": "п. 6.3 Методики расчёта ставки",
                "metric": "отклонение ставки, п.п.",
                "unit": "договоров",
                "field": "rate_deviation_pp",
                "kind": "проблема",
            },
            {
                "title": "Реструктуризация без подтверждающих документов",
                "test": "Проверить наличие оснований и документов по каждой реструктуризации.",
                "criterion": "п. 9.1 Регламента реструктуризации",
                "metric": "дел без документов, шт.",
                "unit": "договоров",
                "field": "missing_restructure_docs",
                "kind": "проблема",
            },
        ],
    },
    "платежи": {
        "title": "Переводы и платежи",
        "owner": "Операционный департамент",
        "suffix": "PAYMENTS",
        "tables": ["payments.transactions", "payments.orders"],
        "entity": "транзакция",
        "findings": [
            {
                "title": "Перевод без полной идентификации плательщика",
                "test": "Проверить полноту идентификации по переводам выше установленного порога.",
                "criterion": "п. 3.1 Правил внутреннего контроля",
                "metric": "неидентифицированных переводов, шт.",
                "unit": "переводов",
                "field": "incomplete_identification",
            },
            {
                "title": "Превышение лимита операции без дополнительной аутентификации",
                "test": "Проверить, что операции выше лимита подтверждены вторым фактором.",
                "criterion": "п. 2.7 Регламента дистанционного обслуживания",
                "metric": "превышение лимита, руб.",
                "unit": "операций",
                "field": "limit_excess",
            },
            {
                "title": "Дублирование платёжных поручений",
                "test": "Выявить повторные списания по одинаковым реквизитам в течение операционного дня.",
                "criterion": "п. 4.2 Регламента обработки платежей",
                "metric": "дублей, шт.",
                "unit": "поручений",
                "field": "duplicate_count",
            },
            {
                "title": "Нарушение сроков исполнения платёжных поручений",
                "test": "Проверить соблюдение сроков исполнения поручений по внутренним переводам.",
                "criterion": "п. 5.1 Регламента обработки платежей",
                "metric": "просрочка, часов",
                "unit": "поручений",
                "field": "delay_hours",
            },
            {
                "title": "Операции по счёту при действующей блокировке",
                "test": "Проверить отсутствие списаний по счетам с действующей блокировкой.",
                "criterion": "п. 6.4 Регламента блокировок",
                "metric": "операций при блокировке, шт.",
                "unit": "счетов",
                "field": "blocked_operations",
                "kind": "проблема",
            },
            {
                "title": "Некорректный код назначения платежа",
                "test": "Сверить код назначения платежа с фактическим содержанием операции.",
                "criterion": "п. 3.5 Справочника кодов платежей",
                "metric": "некорректных кодов, шт.",
                "unit": "платежей",
                "field": "wrong_purpose_code",
            },
            {
                "title": "Отсутствие контроля дублей по реквизитам",
                "test": "Оценить наличие автоматического контроля повторных реквизитов.",
                "criterion": "п. 4.5 Регламента обработки платежей",
                "metric": "непокрытых реквизитов, шт.",
                "unit": "правил",
                "field": "uncovered_rules",
                "kind": "проблема",
            },
            {
                "title": "Несоблюдение лимитов наличных расчётов",
                "test": "Проверить соблюдение лимита наличных расчётов между юридическими лицами.",
                "criterion": "п. 7.2 Регламента кассовых операций",
                "metric": "превышение лимита, руб.",
                "unit": "операций",
                "field": "cash_limit_excess",
            },
        ],
    },
    "карты": {
        "title": "Карты и эквайринг",
        "owner": "Департамент карточных продуктов",
        "suffix": "CARDS",
        "tables": ["cards.accounts", "cards.transactions"],
        "entity": "карта",
        "findings": [
            {
                "title": "Выпуск карты без полной идентификации клиента",
                "test": "Проверить наличие полной идентификации до выпуска карты.",
                "criterion": "п. 3.3 Правил внутреннего контроля",
                "metric": "карт без идентификации, шт.",
                "unit": "карт",
                "field": "cards_without_kyc",
                "kind": "проблема",
            },
            {
                "title": "Превышение лимита снятия наличных",
                "test": "Проверить соблюдение суточного лимита снятия наличных.",
                "criterion": "п. 4.1 Тарифов обслуживания карт",
                "metric": "превышение лимита, руб.",
                "unit": "операций",
                "field": "cash_limit_excess",
            },
            {
                "title": "Некорректное начисление кэшбэка",
                "test": "Пересчитать кэшбэк по операциям отчётного периода.",
                "criterion": "п. 5.2 Правил программы лояльности",
                "metric": "отклонение начисления, руб.",
                "unit": "операций",
                "field": "cashback_deviation",
            },
            {
                "title": "Мошеннические операции без своевременной блокировки",
                "test": "Проверить скорость блокировки карты после признаков мошенничества.",
                "criterion": "п. 6.4 Регламента противодействия мошенничеству",
                "metric": "часов до блокировки",
                "unit": "операций",
                "field": "hours_to_block",
            },
            {
                "title": "Отсутствие согласия на овердрафт",
                "test": "Проверить наличие согласия клиента на подключение овердрафта.",
                "criterion": "п. 4.6 Условий обслуживания карт",
                "metric": "карт без согласия, шт.",
                "unit": "карт",
                "field": "overdraft_without_consent",
                "kind": "проблема",
            },
            {
                "title": "Ошибки в тарифах эквайринга",
                "test": "Сверить применяемую ставку эквайринга с договором торговой точки.",
                "criterion": "п. 2.5 Тарифов эквайринга",
                "metric": "отклонение ставки, п.п.",
                "unit": "договоров",
                "field": "acquiring_rate_gap",
            },
            {
                "title": "Просроченный перевыпуск карт",
                "test": "Проверить перевыпуск карт до истечения срока действия.",
                "criterion": "п. 7.1 Регламента перевыпуска",
                "metric": "дней просрочки",
                "unit": "карт",
                "field": "days_overdue_reissue",
            },
            {
                "title": "Возвраты по спорным операциям вне регламента",
                "test": "Проверить соблюдение сроков и оснований возврата по спорным операциям.",
                "criterion": "п. 8.2 Регламента работы с претензиями",
                "metric": "нарушений срока, дней",
                "unit": "обращений",
                "field": "chargeback_delay_days",
                "kind": "проблема",
            },
        ],
    },
    "вклады": {
        "title": "Вклады и расчётные счета",
        "owner": "Департамент пассивных операций",
        "suffix": "DEPOSITS",
        "tables": ["deposits.accounts", "deposits.interest_accruals"],
        "entity": "счёт",
        "findings": [
            {
                "title": "Открытие счёта без полного комплекта документов",
                "test": "Проверить комплектность документов по каждому открытому счёту.",
                "criterion": "п. 2.2 Регламента открытия счетов",
                "metric": "счетов без документов, шт.",
                "unit": "счетов",
                "field": "missing_docs",
                "kind": "проблема",
            },
            {
                "title": "Некорректное начисление процентов по вкладу",
                "test": "Пересчитать проценты по каждому вкладу за отчётный период.",
                "criterion": "п. 3.1 Методики начисления процентов",
                "metric": "отклонение начисления, руб.",
                "unit": "счетов",
                "field": "interest_deviation",
            },
            {
                "title": "Досрочное закрытие вклада без согласия клиента",
                "test": "Проверить наличие согласия клиента на досрочное закрытие вклада.",
                "criterion": "п. 4.4 Условий вкладов",
                "metric": "счетов без согласия, шт.",
                "unit": "счетов",
                "field": "early_close_without_consent",
                "kind": "проблема",
            },
            {
                "title": "Превышение лимита страхования вкладов без информирования",
                "test": "Проверить информирование клиентов о превышении лимита страхования вкладов.",
                "criterion": "п. 5.3 Регламента информирования",
                "metric": "сумма сверх лимита, руб.",
                "unit": "счетов",
                "field": "amount_over_insurance",
            },
            {
                "title": "Неактуализированные персональные данные клиента",
                "test": "Проверить актуальность персональных данных клиентов.",
                "criterion": "п. 6.1 Регламента идентификации",
                "metric": "месяцев с актуализации",
                "unit": "клиентов",
                "field": "months_since_update",
            },
            {
                "title": "Ошибки в расчёте налога на проценты",
                "test": "Пересчитать налог на проценты по вкладам.",
                "criterion": "п. 7.2 Методики налогового учёта",
                "metric": "отклонение налога, руб.",
                "unit": "счетов",
                "field": "tax_deviation",
            },
            {
                "title": "Овердрафт по расчётному счёту без договора",
                "test": "Проверить наличие договора овердрафта по счетам с отрицательным остатком.",
                "criterion": "п. 3.6 Регламента расчётных операций",
                "metric": "счетов без договора, шт.",
                "unit": "счетов",
                "field": "overdraft_without_contract",
                "kind": "проблема",
            },
            {
                "title": "Несоблюдение очерёдности списания по счёту",
                "test": "Проверить очерёдность списания при недостаточности средств.",
                "criterion": "п. 4.7 Регламента расчётных операций",
                "metric": "нарушений очерёдности, шт.",
                "unit": "операций",
                "field": "priority_violations",
            },
        ],
    },
}

CAUSES = [
    "не настроено контрольное правило в АБС",
    "регламент не доведён до исполнителей",
    "ручной перенос данных выполнен без сверки",
    "отсутствует автоматическая блокировка операции",
    "недостаточная сегрегация обязанностей",
]

EFFECTS = [
    "риск занижения стоимости обеспечения",
    "риск регуляторных санкций",
    "риск финансовых потерь",
    "риск недостоверной отчётности",
    "риск вовлечения в сомнительные операции",
]

RECOMMENDATIONS = [
    "настроить автоматический контроль в АБС",
    "обновить регламент и провести обучение сотрудников",
    "ввести обязательную сверку реестров",
    "автоматизировать блокировку по контрольному правилу",
    "усилить последующий контроль руководителем подразделения",
]

AUDITORS = [
    ("AUD-001", "Смирнов Алексей Петрович", "a.smirnov@audit.local", "Управление внутреннего аудита", "Ведущий аудитор", "1 категория", ["ипотека", "вклады"]),
    ("AUD-002", "Кузнецова Мария Сергеевна", "m.kuznetsova@audit.local", "Управление внутреннего аудита", "Главный аудитор", "высшая", ["потребкредитование", "карты"]),
    ("AUD-003", "Волков Дмитрий Андреевич", "d.volkov@audit.local", "Управление внутреннего аудита", "Старший аудитор", "1 категория", ["платежи", "карты"]),
    ("AUD-004", "Соколова Анна Викторовна", "a.sokolova@audit.local", "Управление внутреннего аудита", "Аудитор", "2 категория", ["ипотека", "потребкредитование"]),
    ("AUD-005", "Морозов Игорь Николаевич", "i.morozov@audit.local", "Управление внутреннего аудита", "Руководитель направления", "высшая", ["платежи", "вклады"]),
    ("AUD-006", "Лебедева Ольга Игоревна", "o.lebedeva@audit.local", "Управление внутреннего аудита", "Ведущий аудитор", "1 категория", ["карты", "потребкредитование"]),
    ("AUD-007", "Новиков Павел Олегович", "p.novikov@audit.local", "Управление внутреннего аудита", "Аудитор", "2 категория", ["вклады", "ипотека"]),
    ("AUD-008", "Егорова Татьяна Львовна", "t.egorova@audit.local", "Управление внутреннего аудита", "Старший аудитор", "1 категория", ["платежи", "карты"]),
    ("AUD-009", "Козлов Сергей Максимович", "s.kozlov@audit.local", "Управление внутреннего аудита", "Аудитор", "без категории", ["ипотека", "потребкредитование"]),
    ("AUD-010", "Павлова Елена Дмитриевна", "e.pavlova@audit.local", "Управление внутреннего аудита", "Ведущий аудитор", "1 категория", ["вклады", "платежи"]),
    ("AUD-011", "Орлов Максим Ильич", "m.orlov@audit.local", "Управление внутреннего аудита", "Аудитор", "2 категория", ["карты", "ипотека"]),
    ("AUD-012", "Фёдорова Ирина Александровна", "i.fedorova@audit.local", "Управление внутреннего аудита", "Главный аудитор", "высшая", ["потребкредитование", "вклады"]),
]

RISK_BY_INDEX = ["низкий", "средний", "высокий", "критический"]
RISK_WEIGHTS = [25, 45, 22, 8]
STATUS_WEIGHTS = [35, 30, 35]  # открыт, в работе, закрыт
TEST_TYPES = ["непрерывный", "выборочный", "аналитический", "повторное выполнение", "опрос"]
TEST_WEIGHTS = [40, 20, 15, 10, 15]
LANG_WEIGHTS = [("SQL", 60), ("Python", 30), ("R", 5), ("Excel", 5)]

SUFFIX_TO_THEME = {theme["suffix"]: code for code, theme in THEMES.items()}


# --------------------------------------------------------------------------
# Вспомогательные функции
# --------------------------------------------------------------------------

def weighted(rng: random.Random, values: list, weights: list):
    return rng.choices(values, weights=weights, k=1)[0]


def workday_on_or_after(rng: random.Random, d: date) -> date:
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def add_workdays(d: date, days: int) -> date:
    current = d
    left = days
    while left > 0:
        current += timedelta(days=1)
        if current.weekday() < 5:
            left -= 1
    return current


def iso(d: date | None) -> str:
    return d.isoformat() if d else ""


def iso_ts(dt: datetime | None) -> str:
    return dt.isoformat() if dt else ""


def array_literal(values: list[str]) -> str:
    if not values:
        return "{}"
    escaped = [v.replace("\\", "\\\\").replace('"', '\\"') for v in values]
    return "{" + ",".join(f'"{v}"' if ("," in v or " " in v) else v for v in escaped) + "}"


def write_csv(name: str, header: list[str], rows: list[dict]) -> None:
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    path = SEED_DIR / f"{name}.csv"
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh, lineterminator="\n")
        writer.writerow(header)
        for row in rows:
            writer.writerow([row.get(col, "") for col in header])


# --------------------------------------------------------------------------
# Генерация
# --------------------------------------------------------------------------

def gen_auditors() -> list[dict]:
    return [
        {
            "auditor_id": aid,
            "full_name": name,
            "email": email,
            "unit": unit,
            "position": position,
            "grade": grade,
            "specializations": array_literal(specs),
            "is_active": "true",
        }
        for aid, name, email, unit, position, grade, specs in AUDITORS
    ]


def gen_pockets(rng: random.Random) -> list[dict]:
    rows = []
    for year in YEARS:
        for theme_code, theme in THEMES.items():
            rows.append(
                {
                    "pocket_id": f"PKT-{year}-{theme['suffix']}",
                    "pocket_year": year,
                    "theme_code": theme_code,
                    "title": f"{year}. {theme['title']}",
                    "description": (
                        f"Тематический портфель проверок: {theme['title'].lower()}. "
                        f"Период: календарный {year} год."
                    ),
                    "owner_unit": theme["owner"],
                    "period_start": iso(date(year, 1, 1)),
                    "period_end": iso(date(year, 12, 31)),
                    "planned_audit_count": rng.randint(5, 20),
                    "risk_level": weighted(rng, RISK_BY_INDEX, [15, 45, 30, 10]),
                    "status": "закрыт" if year == 2025 else "активен",
                }
            )
    return rows


def pick_auditor(rng: random.Random, theme_code: str, used_ranges: dict[str, list[tuple[date, date]]], start: date, end: date) -> str:
    candidates = [a for a in AUDITORS if theme_code in a[6]]
    rng.shuffle(candidates)
    for auditor in candidates:
        ranges = used_ranges.setdefault(auditor[0], [])
        if all(end < s or start > e for s, e in ranges):
            ranges.append((start, end))
            return auditor[0]
    # если все заняты — берём первого, пересечение допустимо, но помечаем диапазон
    auditor_id = candidates[0][0] if candidates else AUDITORS[0][0]
    used_ranges.setdefault(auditor_id, []).append((start, end))
    return auditor_id


def gen_audits(rng: random.Random, pockets: list[dict]) -> tuple[list[dict], list[dict]]:
    audits: list[dict] = []
    acts: list[dict] = []
    used_ranges: dict[str, list[tuple[date, date]]] = {}

    for pocket in pockets:
        year = pocket["pocket_year"]
        theme_code = pocket["theme_code"]
        theme = THEMES[theme_code]
        count = pocket["planned_audit_count"]

        for n in range(1, count + 1):
            audit_code = f"AUD-{year}-{theme['suffix']}-{n:02d}"
            audit_id = audit_code

            if year == 2025:
                status = weighted(rng, ["завершена", "отменена"], [90, 10])
            else:
                status = weighted(
                    rng, ["завершена", "в работе", "запланирована", "отменена"], [55, 20, 15, 10]
                )

            if status == "завершена":
                if year == 2025:
                    latest_start = date(2025, 9, 30)
                else:
                    latest_start = date(2026, 8, 31)
                start = workday_on_or_after(
                    rng, latest_start - timedelta(days=rng.randint(0, 240))
                )
                duration = rng.randint(15, 45)
                end = add_workdays(start, duration)
                if end > date(year, 11, 15):
                    end = add_workdays(start, min(duration, 20))
            elif status == "в работе":
                start = workday_on_or_after(rng, date(year, 10, 1) + timedelta(days=rng.randint(0, 30)))
                end = add_workdays(start, rng.randint(15, 40))
                if end > date(year, 12, 31):
                    end = date(year, 12, 31)
            elif status == "запланирована":
                start = workday_on_or_after(rng, date(year, 11, 20) + timedelta(days=rng.randint(0, 10)))
                end = min(add_workdays(start, rng.randint(10, 30)), date(year, 12, 31))
            else:  # отменена
                start = workday_on_or_after(rng, date(year, 2, 1) + timedelta(days=rng.randint(0, 240)))
                end = add_workdays(start, rng.randint(10, 40))

            if end > date(year, 12, 31):
                end = date(year, 12, 31)

            lead = pick_auditor(rng, theme_code, used_ranges, start, end)
            audit_type = weighted(
                rng,
                ["плановая", "тематическая", "внеплановая", "повторная", "последующий контроль"],
                [65, 15, 10, 5, 5],
            )

            audits.append(
                {
                    "audit_id": audit_id,
                    "pocket_id": pocket["pocket_id"],
                    "audit_code": audit_code,
                    "title": f"Проверка: {theme['title'].lower()} ({year}, {n:02d})",
                    "audit_type": audit_type,
                    "start_date": iso(start),
                    "end_date": iso(end),
                    "status": status,
                    "lead_auditor_id": lead,
                    "team_size": rng.randint(2, 6),
                    "scope": (
                        f"Процессы {theme['title'].lower()} за период "
                        f"{start.strftime('%d.%m.%Y')} — {end.strftime('%d.%m.%Y')}."
                    ),
                    "risk_level": weighted(rng, RISK_BY_INDEX, [20, 45, 25, 10]),
                }
            )

            if status in ("завершена", "в работе"):
                if status == "завершена":
                    act_date = end + timedelta(days=rng.randint(5, 15))
                    act_status = weighted(rng, ["утверждён", "на согласовании"], [90, 10])
                else:
                    act_date = max(start, min(end, TODAY) - timedelta(days=rng.randint(0, 5)))
                    act_status = "черновик"
                approver = rng.choice([a[0] for a in AUDITORS if a[0] != lead])
                acts.append(
                    {
                        "act_id": f"ACT-{year}-{theme['suffix']}-{n:02d}",
                        "audit_id": audit_id,
                        "act_number": f"ACT-{year}-{theme['suffix']}-{n:02d}",
                        "act_date": iso(act_date),
                        "status": act_status,
                        "approved_by": approver if act_status != "черновик" else "",
                        "summary": (
                            f"Акт по проверке {audit_code}: выявлены отклонения и проблемы "
                            f"в процессах {theme['title'].lower()}."
                        ),
                        "full_text": "",
                    }
                )

    return audits, acts


def make_item_numbers(rng: random.Random, total: int) -> list[str]:
    """Нумерация пунктов: 2–4 раздела, в 30% актов — трёхуровневый номер."""
    while True:
        sections = rng.randint(2, 4)
        sizes = [1] * sections
        for _ in range(total - sections):
            sizes[rng.randrange(sections)] += 1
        if max(sizes) <= 4:
            break

    numbers: list[str] = []
    for idx, size in enumerate(sizes):
        section = 5 + idx
        for sub in range(1, size + 1):
            numbers.append(f"{section}.{sub}")

    # трёхуровневый номер: первый пункт раздела становится родительским,
    # второй — вложенным (5.2 и 5.2.1)
    if rng.random() < 0.30:
        candidates = [i for i, num in enumerate(numbers) if num.count(".") == 1]
        if len(candidates) >= 2:
            parent = numbers[candidates[0]]
            numbers[candidates[1]] = f"{parent}.1"

    return numbers


def gen_script_code(rng: random.Random, language: str, theme: dict, finding: dict, threshold: int) -> str:
    table = theme["tables"][0]
    field = finding["field"]
    title = finding["title"]
    if language == "SQL":
        return (
            f"-- Проверка: {title}\n"
            f"WITH base AS (\n"
            f"    SELECT entity_id, {field}\n"
            f"    FROM {table}\n"
            f"    WHERE report_date >= :date_from\n"
            f"      AND report_date < :date_to\n"
            f")\n"
            f"SELECT entity_id, {field}\n"
            f"FROM base\n"
            f"WHERE {field} > {threshold}\n"
            f"ORDER BY {field} DESC;"
        )
    if language == "Python":
        return (
            "import pandas as pd\n\n"
            f"# Проверка: {title}\n"
            f'df = pd.read_sql("SELECT * FROM {table}", conn)\n'
            f"bad = df[df['{field}'] > {threshold}]\n"
            'print(f"Найдено отклонений: {len(bad)}")\n'
        )
    if language == "R":
        return (
            "library(dplyr)\n\n"
            f"# Проверка: {title}\n"
            f'df <- tbl(conn, "{table}") %>% collect()\n'
            f"bad <- df %>% filter({field} > {threshold})\n"
            "nrow(bad)\n"
        )
    return (
        f"=СЧЁТЕСЛИМН('{table}'!{field};\">\"&{threshold})\n"
        f"-- Проверка: {title}"
    )


def gen_items_and_scripts(
    rng: random.Random,
    audits: list[dict],
    acts: list[dict],
    with_deviations: bool,
) -> tuple[list[dict], list[dict], list[dict], list[dict], list[dict]]:
    items: list[dict] = []
    scripts: list[dict] = []
    runs: list[dict] = []
    deviations: list[dict] = []
    used_ranges: dict[str, list[tuple[date, date]]] = {}

    act_by_audit = {act["audit_id"]: act for act in acts}
    prev_items_by_theme: dict[str, list[dict]] = {}
    script_seq = 0
    run_seq = 0
    dev_seq = 0

    for audit in audits:
        act = act_by_audit.get(audit["audit_id"])
        if not act:
            continue

        theme_code = SUFFIX_TO_THEME[audit["pocket_id"].split("-", 2)[2]]
        theme = THEMES[theme_code]
        act_date = date.fromisoformat(act["act_date"])
        total_items = rng.randint(5, 10)
        numbers = make_item_numbers(rng, total_items)
        pool = theme["findings"] * 2
        rng.shuffle(pool)
        findings = pool[:total_items]

        act_items: list[dict] = []
        for idx, (number, finding) in enumerate(zip(numbers, findings), start=1):
            is_problem = finding.get("kind") == "проблема"
            item_type = "проблема" if (is_problem or rng.random() < 0.25) else "отклонение"

            if item_type == "отклонение":
                risk = weighted(rng, RISK_BY_INDEX, [10, 40, 35, 15])
            else:
                risk = weighted(rng, RISK_BY_INDEX, [35, 45, 15, 5])

            if item_type == "проблема":
                test_type = weighted(rng, TEST_TYPES, [10, 15, 20, 5, 50])
            else:
                test_type = weighted(
                    rng,
                    ["непрерывный", "выборочный", "аналитический", "повторное выполнение"],
                    [45, 25, 15, 15],
                )

            if audit["status"] == "завершена":
                status = weighted(rng, ["закрыт", "в работе", "открыт"], [70, 15, 15])
            else:
                status = weighted(rng, ["открыт", "в работе", "закрыт"], [55, 35, 10])

            deadline = act_date + timedelta(days=rng.randint(30, 180))
            closed_at = None
            if status == "закрыт":
                closed_at = deadline + timedelta(days=rng.randint(-20, 10))

            # часть открытых пунктов — просроченные
            if status != "закрыт" and rng.random() < 0.35:
                deadline = TODAY - timedelta(days=rng.randint(1, 120))

            total = rng.randint(200, 5000)
            share = rng.uniform(0.005, 0.06)
            found = max(1, int(total * share))
            condition = (
                f"у {found} из {total} {finding['unit']} "
                f"показатель «{finding['metric']}» превышает допустимое значение."
                if item_type == "отклонение"
                else f"по {found} из {total} {finding['unit']} не подтверждено соблюдение требования."
            )

            item_id = f"ITM-{audit['audit_code'][4:]}-{number.replace('.', '')}"
            item = {
                "item_id": item_id,
                "act_id": act["act_id"],
                "item_number": number,
                "item_type": item_type,
                "test_type": test_type,
                "title": finding["title"],
                "test_description": finding["test"],
                "criterion": finding["criterion"],
                "condition": condition,
                "cause": rng.choice(CAUSES),
                "effect": rng.choice(EFFECTS),
                "recommendation": rng.choice(RECOMMENDATIONS),
                "risk_level": risk,
                "status": status,
                "deadline": iso(deadline),
                "responsible_unit": theme["owner"],
                "closed_at": iso(closed_at),
                "is_repeat": "false",
                "repeat_of_item_id": "",
                "order_index": idx,
            }

            # повторные находки: 12–15% пунктов 2026 года со ссылкой на 2025 год
            if audit["pocket_id"].startswith("PKT-2026") and rng.random() < 0.135:
                candidates = [
                    prev for prev in prev_items_by_theme.get(theme_code, [])
                    if prev["item_type"] == item_type
                ]
                if candidates:
                    previous = rng.choice(candidates)
                    item["is_repeat"] = "true"
                    item["repeat_of_item_id"] = previous["item_id"]
                    item["title"] = previous["title"]

            act_items.append(item)
            items.append(item)

            # скрипты
            if item_type == "отклонение":
                script_count = rng.randint(1, 3)
            else:
                script_count = weighted(rng, [0, 1, 2], [35, 50, 15])

            for s_idx in range(1, int(script_count) + 1):
                script_seq += 1
                language = weighted(rng, [w[0] for w in LANG_WEIGHTS], [w[1] for w in LANG_WEIGHTS])
                threshold = rng.randint(30, 500)
                population = rng.randint(500, 10000)
                rows_found = (
                    max(1, int(population * rng.uniform(0.002, 0.05)))
                    if item_type == "отклонение"
                    else rng.choice([0, 0, 1, 2, 3])
                )
                executed = datetime.combine(
                    act_date + timedelta(days=rng.randint(1, 10)),
                    datetime.min.time(),
                    tzinfo=timezone.utc,
                ) + timedelta(hours=rng.randint(9, 19), minutes=rng.randint(0, 59))

                script_id = f"SCR-{audit['audit_code'][4:]}-{number.replace('.', '')}-{s_idx}"
                scripts.append(
                    {
                        "script_id": script_id,
                        "item_id": item_id,
                        "name": f"Скрипт проверки: {finding['title'].lower()}",
                        "language": language,
                        "description": (
                            f"Проверка показателя «{finding['metric']}» "
                            f"по источникам: {', '.join(theme['tables'])}."
                        ),
                        "code": gen_script_code(rng, language, theme, finding, threshold),
                        "parameters": json.dumps(
                            {"date_from": f"{audit['start_date']}", "date_to": f"{audit['end_date']}"},
                            ensure_ascii=False,
                        ),
                        "source_tables": array_literal(theme["tables"]),
                        "target_system": rng.choice(["АБС", "Хранилище данных", "Процессинг", "CRM"]),
                        "expected_result": (
                            f"Ожидается не более {max(1, population // 100)} записей "
                            f"с превышением порога {threshold}."
                        ),
                        "result_summary": (
                            f"Проверено {population} записей, выявлено {rows_found} "
                            f"отклонений по показателю «{finding['metric']}»."
                        ),
                        "population_size": population,
                        "rows_found": rows_found,
                        "execution_ms": rng.randint(50, 30000),
                        "executed_at": iso_ts(executed),
                        "version": s_idx,
                    }
                )

                # запуск скрипта
                run_seq += 1
                run_status = weighted(rng, ["успешно", "частично", "ошибка"], [90, 5, 5])
                if run_status == "ошибка":
                    rows_found_run = 0
                    error = rng.choice(
                        [
                            "Превышено время выполнения запроса.",
                            "Источник данных недоступен в момент запуска.",
                            "Не найдена обязательная колонка в источнике.",
                        ]
                    )
                else:
                    rows_found_run = rows_found if run_status == "успешно" else max(0, rows_found // 2)
                    error = ""

                runs.append(
                    {
                        "run_id": f"RUN-{run_seq:05d}",
                        "script_id": script_id,
                        "run_at": iso_ts(executed + timedelta(minutes=rng.randint(1, 30))),
                        "status": run_status,
                        "rows_found": rows_found_run,
                        "duration_ms": rng.randint(50, 45000),
                        "result_sample": json.dumps(
                            {"first_rows": min(rows_found_run, 3)}, ensure_ascii=False
                        ),
                        "error_message": error,
                    }
                )

                # отклонения-доказательства
                if with_deviations and run_status == "успешно" and rows_found > 0:
                    for _ in range(min(rows_found, rng.randint(0, 8))):
                        dev_seq += 1
                        deviations.append(
                            {
                                "deviation_id": f"DEV-{dev_seq:06d}",
                                "item_id": item_id,
                                "script_id": script_id,
                                "entity_type": theme["entity"],
                                "entity_id": f"{theme['suffix'][:3]}-{rng.randint(100000, 999999)}",
                                "detected_at": iso(act_date + timedelta(days=rng.randint(1, 15))),
                                "metric_name": finding["metric"],
                                "metric_value": round(rng.uniform(threshold * 1.01, threshold * 3), 2),
                                "threshold_value": float(threshold),
                                "severity": risk,
                                "description": (
                                    f"Выявлено превышение показателя «{finding['metric']}» "
                                    f"по объекту проверки."
                                ),
                                "payload": json.dumps(
                                    {"script": script_id, "item": item_id}, ensure_ascii=False
                                ),
                            }
                        )

        if audit["pocket_id"].startswith("PKT-2025"):
            prev_items_by_theme.setdefault(theme_code, []).extend(
                [i for i in act_items if i["is_repeat"] == "false"]
            )

    return items, scripts, runs, deviations


def gen_script_templates() -> list[dict]:
    templates = [
        (
            "TPL-001",
            "status_summary",
            "Сводка по статусам проверок",
            "Количество проверок по статусам за указанный год.",
            "SELECT status, count(*) AS cnt FROM audit.audits "
            "WHERE start_date >= :year::text || '-01-01'::date "
            "GROUP BY status ORDER BY cnt DESC",
            {"year": 2026},
        ),
        (
            "TPL-002",
            "top_findings",
            "Топ видов отклонений",
            "Самые частые формулировки отклонений за период.",
            "SELECT title, count(*) AS cnt FROM audit.act_items "
            "WHERE item_type = 'отклонение' AND created_at >= :date_from::date "
            "GROUP BY title ORDER BY cnt DESC LIMIT :limit",
            {"date_from": "2026-01-01", "limit": 10},
        ),
        (
            "TPL-003",
            "theme_dynamics",
            "Динамика по темам и годам",
            "Количество пунктов и критических находок по темам и годам.",
            "SELECT theme_code, pocket_year, item_count, critical_count, repeat_count "
            "FROM audit.v_theme_year_dynamics ORDER BY theme_code, pocket_year",
            {},
        ),
        (
            "TPL-004",
            "overdue_items",
            "Просроченные открытые пункты",
            "Открытые пункты с истёкшим сроком устранения.",
            "SELECT item_id, title, risk_level, deadline, days_overdue "
            "FROM audit.v_open_items WHERE is_overdue ORDER BY days_overdue DESC",
            {},
        ),
        (
            "TPL-005",
            "items_without_scripts",
            "Пункты без доказательств",
            "Пункты актов, по которым не приложен ни один скрипт.",
            "SELECT item_id, title, item_type, risk_level, act_number "
            "FROM audit.v_items_without_scripts ORDER BY act_number, item_number",
            {},
        ),
        (
            "TPL-006",
            "risk_by_pocket",
            "Риски по карманам",
            "Сводка по карманам: проверки, пункты, критические и просроченные.",
            "SELECT pocket_id, title, audit_count, item_count, critical_count, overdue_count "
            "FROM audit.v_pocket_summary ORDER BY pocket_year, theme_code",
            {},
        ),
    ]
    return [
        {
            "template_id": tid,
            "template_key": key,
            "title": title,
            "description": desc,
            "sql_template": sql,
            "parameters": json.dumps(params, ensure_ascii=False),
            "max_rows_default": 200,
            "is_active": "true",
        }
        for tid, key, title, desc, sql, params in templates
    ]


def gen_memory() -> list[dict]:
    now = iso_ts(datetime(2026, 11, 21, 10, 0, tzinfo=timezone.utc))
    rows = [
        ("AUD-001", "default_format", "краткий"),
        ("AUD-001", "focus_theme", "ипотека"),
        ("AUD-002", "default_format", "подробный"),
        ("AUD-002", "focus_theme", "потребкредитование"),
        ("AUD-003", "default_format", "краткий"),
        ("AUD-003", "focus_theme", "платежи"),
    ]
    return [
        {
            "auditor_id": auditor_id,
            "memory_key": key,
            "memory_value": value,
            "updated_at": now,
        }
        for auditor_id, key, value in rows
    ]


KNOWLEDGE_DOCS = {
    "классификация_находок.md": """# Классификация находок

В акте внутреннего аудита фиксируются два вида пунктов.

**Отклонение** — количественное подтверждённое расхождение с требованием.
У отклонения есть популяция, скрипт проверки и число найденных записей.
Пример: у 37 из 1 250 договоров оценка залога старше 12 месяцев.

**Проблема** — качественный недостаток или пробел контроля, который нельзя
выразить одним числом. Пример: регламент не доведён до исполнителей,
отсутствует автоматическая блокировка операции.

Для каждого пункта указываются критерий, условие, причина, следствие
и рекомендация. Пункт без критерия считается недооформленным.
""",
    "требования_к_акту.md": """# Требования к акту

Акт состоит из вводной части, разделов с находками и рекомендаций.

В вводной части указываются номер проверки, период, состав команды
и охват. Каждый пункт нумеруется по схеме «раздел.пункт» или
«раздел.подраздел.пункт».

Пункт содержит: заголовок, описание теста, критерий, условие,
причину, следствие, оценку риска, срок устранения и ответственное
подразделение. Для количественных находок прикладывается скрипт
и результат его выполнения.

Акт утверждается руководителем аудита. До утверждения он находится
на согласовании; черновик не является официальным документом.
""",
    "сроки_устранения.md": """# Сроки устранения

Срок устранения назначается исходя из риска.

- критический риск — до 30 календарных дней;
- высокий риск — до 60 календарных дней;
- средний риск — до 120 календарных дней;
- низкий риск — до 180 календарных дней.

Просроченным считается открытый или находящийся в работе пункт,
у которого истёк срок устранения. Просрочка фиксируется на отчётную
дату и влияет на оценку качества работы подразделения.

Закрытие пункта подтверждается документом или результатом повторного
скрипта. Закрытие без подтверждения не допускается.
""",
    "правила_формулировок.md": """# Правила формулировок

Формулировка пункта должна быть проверяемой и нейтральной.

1. Сначала условие, затем критерий: «у 12 из 400 договоров ...,
   что не соответствует п. 4.3 Регламента».
2. Не использовать оценочные суждения без фактов.
3. Не указывать реальные ФИО и названия организаций.
4. Причина описывает механизм возникновения, а не виновного.
5. Следствие описывает риск, а не наказание.
6. Рекомендация должна быть выполнимой и измеримой.

Запрещены формулировки «халатность», «недобросовестность»,
«систематическое нарушение» без количественного подтверждения.
""",
    "работа_со_скриптами.md": """# Работа со скриптами

Скрипт — это артефакт проверки, который подтверждает количественную находку.

В карточке скрипта указываются язык, описание, исходные таблицы,
параметры запуска, размер популяции, число найденных строк и сводка
результата. Для отклонения обязателен хотя бы один скрипт с ненулевым
результатом.

SQL-скрипт должен быть read-only: допускаются только SELECT и WITH.
Запрещены INSERT, UPDATE, DELETE, DROP, COPY и вызовы системных функций.

Если скрипт завершился ошибкой, это фиксируется в истории запусков
и не подменяется ручной оценкой.
""",
    "оценка_риска.md": """# Оценка риска

Уровень риска пункта определяется вероятностью и последствиями.

- **Критический** — прямое нарушение регуляторного требования или
  существенная финансовая потеря.
- **Высокий** — повторяющееся отклонение с заметным влиянием на отчётность.
- **Средний** — единичное отклонение без существенного финансового эффекта.
- **Низкий** — процедурный недостаток, устраняемый в рабочем порядке.

Повторная находка не понижает риск: если пункт повторяется из года в год,
уровень риска сохраняется или повышается.

Оценка риска влияет на срок устранения и на приоритет в отчёте.
""",
}


def write_knowledge() -> None:
    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
    for name, text in KNOWLEDGE_DOCS.items():
        (KNOWLEDGE_DIR / name).write_text(text, encoding="utf-8")


def manifest(counts: dict[str, int]) -> None:
    digest = hashlib.sha256()
    for path in sorted(SEED_DIR.glob("*.csv")):
        digest.update(path.name.encode("utf-8"))
        digest.update(path.read_bytes())
    data = {
        "seed": SEED,
        "generated_at": "2026-11-21",
        "counts": counts,
        "sha256": digest.hexdigest(),
        "note": "Все содержательные данные — синтетические и русскоязычные.",
    }
    (SEED_DIR / "manifest.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Генерация синтетических данных аудита")
    parser.add_argument(
        "--deviations",
        action="store_true",
        help="генерировать таблицу deviations (около 6 тыс. строк)",
    )
    args = parser.parse_args()

    rng = random.Random(SEED)
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    if not args.deviations:
        (SEED_DIR / "deviations.csv").unlink(missing_ok=True)

    auditors = gen_auditors()
    pockets = gen_pockets(rng)
    audits, acts = gen_audits(rng, pockets)
    items, scripts, runs, deviations = gen_items_and_scripts(
        rng, audits, acts, with_deviations=args.deviations
    )
    templates = gen_script_templates()
    memory = gen_memory()

    write_csv(
        "auditors",
        ["auditor_id", "full_name", "email", "unit", "position", "grade", "specializations", "is_active"],
        auditors,
    )
    write_csv(
        "audit_pockets",
        ["pocket_id", "pocket_year", "theme_code", "title", "description", "owner_unit",
         "period_start", "period_end", "planned_audit_count", "risk_level", "status"],
        pockets,
    )
    write_csv(
        "audits",
        ["audit_id", "pocket_id", "audit_code", "title", "audit_type", "start_date",
         "end_date", "status", "lead_auditor_id", "team_size", "scope", "risk_level"],
        audits,
    )
    write_csv(
        "acts",
        ["act_id", "audit_id", "act_number", "act_date", "status", "approved_by", "summary", "full_text"],
        acts,
    )
    write_csv(
        "act_items",
        ["item_id", "act_id", "item_number", "item_type", "test_type", "title",
         "test_description", "criterion", "condition", "cause", "effect",
         "recommendation", "risk_level", "status", "deadline", "responsible_unit",
         "closed_at", "is_repeat", "repeat_of_item_id", "order_index"],
        items,
    )
    write_csv(
        "scripts",
        ["script_id", "item_id", "name", "language", "description", "code", "parameters",
         "source_tables", "target_system", "expected_result", "result_summary",
         "population_size", "rows_found", "execution_ms", "executed_at", "version"],
        scripts,
    )
    write_csv(
        "script_runs",
        ["run_id", "script_id", "run_at", "status", "rows_found", "duration_ms",
         "result_sample", "error_message"],
        runs,
    )
    write_csv(
        "script_templates",
        ["template_id", "template_key", "title", "description", "sql_template",
         "parameters", "max_rows_default", "is_active"],
        templates,
    )
    write_csv(
        "auditor_memory",
        ["auditor_id", "memory_key", "memory_value", "updated_at"],
        memory,
    )
    if args.deviations:
        write_csv(
            "deviations",
            ["deviation_id", "item_id", "script_id", "entity_type", "entity_id",
             "detected_at", "metric_name", "metric_value", "threshold_value",
             "severity", "description", "payload"],
            deviations,
        )

    write_knowledge()
    counts = {
        "auditors": len(auditors),
        "audit_pockets": len(pockets),
        "audits": len(audits),
        "acts": len(acts),
        "act_items": len(items),
        "scripts": len(scripts),
        "script_runs": len(runs),
        "script_templates": len(templates),
        "auditor_memory": len(memory),
        "deviations": len(deviations) if args.deviations else 0,
    }
    manifest(counts)

    print("Сгенерировано:")
    for name, value in counts.items():
        print(f"  {name}: {value}")
    print(f"Каталог: {SEED_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
