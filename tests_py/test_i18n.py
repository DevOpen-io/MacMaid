from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

from macmaid.i18n import DEFAULT_LANGUAGE, normalize_language, translate


def test_default_language_is_english_and_dynamic_copy_is_bilingual() -> None:
    assert DEFAULT_LANGUAGE == "en"
    assert normalize_language(None) == "en"
    assert translate("Tarama iptal edildi · sonuçlar eksik ve işlem yapılamaz", "en") == (
        "Scan cancelled · results are incomplete and cannot be applied"
    )
    assert translate("Starting scan…", "tr") == "Tarama başlatılıyor…"


def test_tui_render_calls_do_not_leave_untranslated_turkish_copy_in_english() -> None:
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "src/macmaid/tui.py").read_text())
    render_calls = {
        "Static", "Label", "Input", "_page", "_action_menu", "_set_activity",
        "_warn", "_set_state", "update",
    }
    copy: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = (
            node.func.attr if isinstance(node.func, ast.Attribute)
            else node.func.id if isinstance(node.func, ast.Name)
            else ""
        )
        if name not in render_calls:
            continue
        copy.update(
            child.value for child in ast.walk(node)
            if isinstance(child, ast.Constant) and isinstance(child.value, str)
        )

    untranslated = sorted(
        text for text in copy
        if text != "Türkçe"
        and any(character in text for character in "çÇğĞıİöÖşŞüÜ")
        and translate(text, "en") == text
    )
    assert untranslated == []


def test_translation_catalogs_have_no_duplicate_keys() -> None:
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / "src/macmaid/i18n.py").read_text())
    catalogs: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        target = value = None
        if isinstance(node, ast.Assign) and node.targets:
            target, value = node.targets[0], node.value
        elif isinstance(node, ast.AnnAssign):
            target, value = node.target, node.value
        if not (isinstance(target, ast.Name) and target.id.startswith(("_EN", "_TR"))):
            continue
        # Catalogs are either dict literals (_EN/_TR/_EXTRA) or
        # tuple(sorted({...}.items(), ...)) fragment tables (_EN_FRAGMENTS/
        # _TR_FRAGMENTS). Dict literals silently collapse duplicate keys at
        # runtime, so the AST is the only place they can be detected: walk the
        # assigned value and collect every dict literal's keys, wherever the
        # dict sits inside the expression.
        keys = [
            key.value
            for sub in ast.walk(value) if isinstance(sub, ast.Dict)
            for key in sub.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        ]
        if keys:
            catalogs[target.id] = keys

    expected = {"_EN", "_TR", "_EN_EXTRA", "_TR_EXTRA", "_EN_FRAGMENTS", "_TR_FRAGMENTS"}
    assert expected <= catalogs.keys(), f"missing catalogs: {expected - catalogs.keys()}"
    for name, keys in catalogs.items():
        duplicates = sorted(key for key, count in Counter(keys).items() if count > 1)
        assert duplicates == [], f"{name} has duplicate keys: {duplicates}"
