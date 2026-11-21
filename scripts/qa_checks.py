"""Проверки качества синтетических данных (ПЛАН_ПРОЕКТА.md, 14.12.5).

Запуск:
    .venv\\Scripts\\python.exe scripts\\qa_checks.py

Скрипт поднимает БД, выполняет набор SQL-проверок и печатает отчёт.
Код возврата 1, если хотя бы одна проверка не прошла.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import db_runtime  # noqa: E402

CHECKS: list[tuple[str, str, str]] = [
    (
        "Карманы: ровно 10, по 5 на год",
        "SELECT count(*) FROM audit.audit_pockets",
        "= 10",
    ),
    (
        "Карманы: по 5 на каждый год",
        "SELECT count(*) FROM ("
        "  SELECT pocket_year FROM audit.audit_pockets GROUP BY pocket_year HAVING count(*) = 5"
        ") t",
        "= 2",
    ),
    (
        "Проверки: 5–20 в каждом кармане",
        "SELECT count(*) FROM ("
        "  SELECT pocket_id FROM audit.audits GROUP BY pocket_id"
        "  HAVING count(*) BETWEEN 5 AND 20"
        ") t",
        "= 10",
    ),
    (
        "Проверки: даты внутри периода кармана",
        "SELECT count(*) FROM audit.audits a "
        "JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id "
        "WHERE a.start_date < p.period_start OR a.end_date > p.period_end",
        "= 0",
    ),
    (
        "Акты: у завершённых и идущих ровно один",
        "SELECT count(*) FROM ("
        "  SELECT a.audit_id FROM audit.audits a "
        "  LEFT JOIN audit.acts ac ON ac.audit_id = a.audit_id "
        "  WHERE a.status IN ('завершена', 'в работе') "
        "  GROUP BY a.audit_id HAVING count(ac.act_id) <> 1"
        ") t",
        "= 0 (строк)",
    ),
    (
        "Акты: у запланированных и отменённых акта нет",
        "SELECT count(*) FROM audit.audits a "
        "JOIN audit.acts ac ON ac.audit_id = a.audit_id "
        "WHERE a.status IN ('запланирована', 'отменена')",
        "= 0",
    ),
    (
        "Пункты: 5–10 в каждом акте",
        "SELECT count(*) FROM ("
        "  SELECT act_id FROM audit.act_items GROUP BY act_id"
        "  HAVING count(*) BETWEEN 5 AND 10"
        ") t",
        "= числу актов",
    ),
    (
        "Пункты: номера соответствуют шаблону",
        "SELECT count(*) FROM audit.act_items "
        "WHERE item_number !~ '^[0-9]{1,2}(\\.[0-9]{1,2}){1,2}$'",
        "= 0",
    ),
    (
        "Отклонения: есть скрипт и rows_found > 0",
        "SELECT count(*) FROM audit.act_items i "
        "WHERE i.item_type = 'отклонение' "
        "AND NOT EXISTS (SELECT 1 FROM audit.scripts s "
        "                WHERE s.item_id = i.item_id AND s.rows_found > 0)",
        "= 0",
    ),
    (
        "Скрипты: rows_found <= population_size",
        "SELECT count(*) FROM audit.scripts WHERE rows_found > population_size",
        "= 0",
    ),
    (
        "Скрипты: SQL начинается с SELECT/WITH и без DDL/DML",
        "SELECT count(*) FROM audit.scripts "
        "WHERE language = 'SQL' AND ("
        "  code !~* '^\\s*(--[^\\n]*\\n\\s*)*(SELECT|WITH)' "
        "  OR code ~* '\\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|COPY|CALL|DO)\\b'"
        ")",
        "= 0",
    ),
    (
        "Статусы пунктов: closed => closed_at",
        "SELECT count(*) FROM audit.act_items "
        "WHERE status = 'закрыт' AND closed_at IS NULL",
        "= 0",
    ),
    (
        "Статусы актов: утверждён => approved_by",
        "SELECT count(*) FROM audit.acts "
        "WHERE status = 'утверждён' AND approved_by IS NULL",
        "= 0",
    ),
    (
        "Повторы: ссылка на пункт 2025 года той же темы",
        "SELECT count(*) FROM audit.act_items i "
        "JOIN audit.act_items p ON p.item_id = i.repeat_of_item_id "
        "JOIN audit.acts ac ON ac.act_id = p.act_id "
        "JOIN audit.audits a ON a.audit_id = ac.audit_id "
        "JOIN audit.audit_pockets pk ON pk.pocket_id = a.pocket_id "
        "WHERE i.is_repeat AND (pk.pocket_year <> 2025 OR i.item_type <> p.item_type)",
        "= 0",
    ),
    (
        "Ловушки: есть отменённая проверка без акта",
        "SELECT count(*) FROM audit.audits a "
        "LEFT JOIN audit.acts ac ON ac.audit_id = a.audit_id "
        "WHERE a.status = 'отменена' AND ac.act_id IS NULL",
        "> 0",
    ),
    (
        "Ловушки: есть акт на согласовании",
        "SELECT count(*) FROM audit.acts WHERE status = 'на согласовании'",
        "> 0",
    ),
    (
        "Ловушки: есть пункты без скрипта",
        "SELECT count(*) FROM audit.act_items i "
        "WHERE NOT EXISTS (SELECT 1 FROM audit.scripts s WHERE s.item_id = i.item_id)",
        "> 0",
    ),
    (
        "Ловушки: есть просроченный открытый пункт",
        "SELECT count(*) FROM audit.act_items "
        "WHERE status <> 'закрыт' AND deadline < CURRENT_DATE",
        "> 0",
    ),
    (
        "Пункты: маркеры шаблона и области заполнены",
        "SELECT count(*) FROM audit.act_items "
        "WHERE finding_template_key IS NULL OR btrim(finding_template_key) = '' "
        "   OR finding_scope IS NULL OR btrim(finding_scope) = ''",
        "= 0",
    ),
    (
        "Пункты: нет дублей (акт, шаблон, область)",
        "SELECT count(*) FROM ("
        "  SELECT act_id, finding_template_key, finding_scope "
        "  FROM audit.act_items "
        "  GROUP BY 1, 2, 3 HAVING count(*) > 1"
        ") t",
        "= 0",
    ),
    (
        "Акты: полный текст заполнен",
        "SELECT count(*) FROM audit.acts "
        "WHERE full_text IS NULL OR btrim(full_text) = ''",
        "= 0",
    ),
    (
        "Акты: неутверждённые без утверждающего",
        "SELECT count(*) FROM audit.acts "
        "WHERE status <> 'утверждён' AND approved_by IS NOT NULL",
        "= 0",
    ),
    (
        "Скрипты: есть запуск со статусом ошибка",
        "SELECT count(*) FROM audit.script_runs WHERE status = 'ошибка'",
        "> 0",
    ),
    (
        "ФИО: 12 аудиторов, email уникальны",
        "SELECT count(DISTINCT email) FROM audit.auditors",
        "= 12",
    ),
]

LATIN_FIELDS = [
    ("audit.act_items", "title"),
    ("audit.act_items", "test_description"),
    ("audit.act_items", "criterion"),
    ("audit.act_items", "condition"),
    ("audit.act_items", "cause"),
    ("audit.act_items", "effect"),
    ("audit.act_items", "recommendation"),
    ("audit.acts", "summary"),
    ("audit.audit_pockets", "title"),
    ("audit.audit_pockets", "description"),
    ("audit.script_templates", "title"),
    ("audit.script_templates", "description"),
]

WHITELIST = re.compile(r"(SQL|Python|Excel|LTV|АБС|ПОД/ФТ|НПА|ИТ|DWH|CRM)")
CODE_RE = re.compile(
    r"\b(?:PKT|AUD|ACT|ITM|SCR|RUN|DEV|TPL)-(?:[A-Z0-9]+-)*[A-Z0-9]+\b"
)


def strip_codes(text: str) -> str:
    return CODE_RE.sub("", text or "")


def parse_expectation(expr: str) -> tuple[str, int]:
    expr = expr.strip()
    if expr.startswith(">="):
        return ">=", int(expr[2:])
    if expr.startswith("<="):
        return "<=", int(expr[2:])
    if expr.startswith(">"):
        return ">", int(expr[1:])
    if expr.startswith("<"):
        return "<", int(expr[1:])
    if expr.startswith("="):
        return "=", int(expr[1:].split()[0])
    raise ValueError(expr)


def main() -> int:
    db_runtime.ensure_ascii_pg_install()
    server = db_runtime.start_server()
    failures = 0
    try:
        with db_runtime.connect(server, database="audit") as conn:
            for name, sql, expected in CHECKS:
                value = conn.execute(sql).fetchone()[0]
                if "числу актов" in expected:
                    target = conn.execute("SELECT count(*) FROM audit.acts").fetchone()[0]
                    op = "="
                else:
                    op, target = parse_expectation(expected)

                ok = {
                    "=": value == target,
                    ">": value > target,
                    "<": value < target,
                    ">=": value >= target,
                    "<=": value <= target,
                }[op]
                status = "OK  " if ok else "FAIL"
                if not ok:
                    failures += 1
                print(f"[{status}] {name}: {value} (ожидалось {expected})")

            # Латиница в содержательных полях
            latin_total = 0
            for table, column in LATIN_FIELDS:
                rows = conn.execute(
                    f"SELECT {column} FROM {table} WHERE {column} ~ '[A-Za-z]'"
                ).fetchall()
                bad = [
                    r[0] for r in rows
                    if not WHITELIST.search(strip_codes(r[0] or ""))
                    and re.search(r"[A-Za-z]", strip_codes(r[0] or ""))
                ]
                latin_total += len(bad)
                if bad:
                    print(f"[FAIL] Латиница в {table}.{column}: {len(bad)}")
                    for sample in bad[:3]:
                        print(f"       {sample[:120]}")
            if latin_total == 0:
                print("[OK  ] Латиница в содержательных полях: 0")
            else:
                failures += 1

            # Иерархия номеров: для 5.2.1 существует 5.2
            gaps = conn.execute(
                "SELECT count(*) FROM audit.act_items i "
                "WHERE i.item_number ~ '^[0-9]+\\.[0-9]+\\.[0-9]+$' "
                "AND NOT EXISTS ("
                "  SELECT 1 FROM audit.act_items p "
                "  WHERE p.act_id = i.act_id "
                "    AND p.item_number = regexp_replace(i.item_number, '\\.[0-9]+$', '')"
                ")"
            ).fetchone()[0]
            print(f"[{'OK  ' if gaps == 0 else 'FAIL'}] Иерархия номеров: разрывов {gaps}")
            failures += 1 if gaps else 0

            overlaps = conn.execute(
                "SELECT count(*) FROM audit.audits a "
                "JOIN audit.audits b "
                "  ON a.lead_auditor_id = b.lead_auditor_id "
                " AND a.audit_id < b.audit_id "
                " AND a.start_date <= b.end_date "
                " AND b.start_date <= a.end_date"
            ).fetchone()[0]
            print(f"[{'OK  ' if overlaps == 0 else 'FAIL'}] Пересечения проверок у аудитора: {overlaps}")
            failures += 1 if overlaps else 0

            deviation_share = conn.execute(
                "SELECT count(*) FILTER (WHERE item_type = 'отклонение')::numeric "
                "/ nullif(count(*), 0) FROM audit.act_items"
            ).fetchone()[0]
            ratio_ok = deviation_share is not None and 0.60 <= float(deviation_share) <= 0.70
            print(
                f"[{'OK  ' if ratio_ok else 'FAIL'}] Доля отклонений: "
                f"{float(deviation_share or 0):.3f} (ожидалось 0.60–0.70)"
            )
            failures += 0 if ratio_ok else 1

            repeat_share = conn.execute(
                "SELECT count(*) FILTER (WHERE is_repeat)::numeric "
                "/ nullif(count(*), 0) FROM audit.act_items i "
                "JOIN audit.acts ac ON ac.act_id = i.act_id "
                "JOIN audit.audits a ON a.audit_id = ac.audit_id "
                "JOIN audit.audit_pockets p ON p.pocket_id = a.pocket_id "
                "WHERE p.pocket_year = 2026"
            ).fetchone()[0]
            repeat_ok = repeat_share is not None and 0.12 <= float(repeat_share) <= 0.15
            print(
                f"[{'OK  ' if repeat_ok else 'FAIL'}] Доля повторов в 2026: "
                f"{float(repeat_share or 0):.3f} (ожидалось 0.12–0.15)"
            )
            failures += 0 if repeat_ok else 1

            # Готовые SQL-шаблоны должны выполняться с bind-параметрами.
            template_failures = 0
            templates = conn.execute(
                "SELECT template_key, sql_template, parameters "
                "FROM audit.script_templates WHERE is_active"
            ).fetchall()
            for key, sql, params in templates:
                try:
                    conn.execute(sql, params or {})
                except Exception as exc:
                    template_failures += 1
                    print(f"[FAIL] Шаблон {key}: {type(exc).__name__}: {exc}")
            if template_failures == 0:
                print(f"[OK  ] SQL-шаблоны выполняются: {len(templates)}")
            failures += template_failures
    finally:
        server.cleanup()

    print()
    if failures:
        print(f"Проверок с ошибками: {failures}")
        return 1
    print("Все проверки пройдены.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
