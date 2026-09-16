from __future__ import annotations

import ast
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
