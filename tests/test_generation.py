"""Проверки спецификации data-generation на сгенерированных CSV."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

import scripts.generate_data as gen


def _run(tmp_path, monkeypatch) -> tuple[Path, Path]:
    seed = tmp_path / "seed"
    knowledge = tmp_path / "knowledge"
    monkeypatch.setattr(gen, "SEED_DIR", seed)
    monkeypatch.setattr(gen, "KNOWLEDGE_DIR", knowledge)
    monkeypatch.setattr(sys, "argv", ["generate_data.py", "--deviations"])
    assert gen.main() == 0
    return seed, knowledge


def _rows(seed: Path, name: str) -> list[dict]:
    with (seed / f"{name}.csv").open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def test_generation_is_deterministic(tmp_path, monkeypatch):
    first, _ = _run(tmp_path / "first", monkeypatch)
    second, _ = _run(tmp_path / "second", monkeypatch)

    manifest_first = json.loads((first / "manifest.json").read_text(encoding="utf-8"))
    manifest_second = json.loads((second / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_first["sha256"] == manifest_second["sha256"]

    for path in sorted(first.glob("*.csv")):
        assert path.read_bytes() == (second / path.name).read_bytes(), path.name


def test_dataset_invariants(tmp_path, monkeypatch):
    seed, _ = _run(tmp_path, monkeypatch)

    pockets = _rows(seed, "audit_pockets")
    audits = _rows(seed, "audits")
    acts = _rows(seed, "acts")
    items = _rows(seed, "act_items")
    scripts = _rows(seed, "scripts")
    runs = _rows(seed, "script_runs")

    assert len(pockets) == 10
    per_pocket = Counter(a["pocket_id"] for a in audits)
    assert set(per_pocket) == {p["pocket_id"] for p in pockets}
    assert all(5 <= count <= 20 for count in per_pocket.values())

    by_auditor = defaultdict(list)
    for audit in audits:
        by_auditor[audit["lead_auditor_id"]].append(
            (
                date.fromisoformat(audit["start_date"]),
                date.fromisoformat(audit["end_date"]),
            )
        )
    for ranges in by_auditor.values():
        ranges.sort()
        for (_, end), (start, _) in zip(ranges, ranges[1:]):
            assert start > end

    acts_by_audit = Counter(a["audit_id"] for a in acts)
    for audit in audits:
        expected = 1 if audit["status"] in ("завершена", "в работе") else 0
        assert acts_by_audit[audit["audit_id"]] == expected

    for act in acts:
        assert act["full_text"].strip()
        assert (act["status"] == "утверждён") == bool(act["approved_by"])

    items_by_act = Counter(i["act_id"] for i in items)
    assert all(5 <= count <= 10 for count in items_by_act.values())

    seen = set()
    for item in items:
        assert item["finding_template_key"]
        assert item["finding_scope"]
        key = (item["act_id"], item["finding_template_key"], item["finding_scope"])
        assert key not in seen
        seen.add(key)

    problem_share = sum(i["item_type"] == "проблема" for i in items) / len(items)
    assert 0.30 <= problem_share <= 0.40

    ids_2026 = {
        i["item_id"]
        for i in items
        if i["act_id"].startswith("ACT-2026")
    }
    repeats = [i for i in items if i["is_repeat"] == "true"]
    assert repeats
    assert all(i["item_id"] in ids_2026 for i in repeats)
    assert 0.12 <= len(repeats) / len(ids_2026) <= 0.15

    act_by_id = {a["act_id"]: a for a in acts}
    item_by_id = {i["item_id"]: i for i in items}
    by_item = defaultdict(list)
    for script in scripts:
        by_item[script["item_id"]].append(script)
    for item in items:
        if item["item_type"] == "отклонение":
            assert any(int(s["rows_found"]) > 0 for s in by_item[item["item_id"]])
        if item["is_repeat"] == "true":
            previous = item_by_id[item["repeat_of_item_id"]]
            assert previous["act_id"].startswith("ACT-2025")
            assert previous["item_type"] == item["item_type"]

    assert any(r["status"] == "ошибка" for r in runs)
    assert any(i["item_number"].count(".") == 2 for i in items)
    assert any(a["status"] == "на согласовании" for a in acts)
    assert any(
        a["status"] == "отменена" and acts_by_audit[a["audit_id"]] == 0
        for a in audits
    )
    assert act_by_id


def test_sql_scripts_start_without_leading_comments(tmp_path, monkeypatch):
    seed, _ = _run(tmp_path, monkeypatch)

    scripts = [s for s in _rows(seed, "scripts") if s["language"] == "SQL"]
    assert scripts
    for script in scripts:
        code = script["code"]
        assert not code.lstrip().startswith("--"), script["script_id"]
        assert re.match(r"^(SELECT|WITH)\b", code, re.IGNORECASE), script["script_id"]

    for template in _rows(seed, "script_templates"):
        sql = template["sql_template"]
        assert not sql.lstrip().startswith("--"), template["template_key"]
        assert re.match(r"^(SELECT|WITH)\b", sql, re.IGNORECASE), template[
            "template_key"
        ]
