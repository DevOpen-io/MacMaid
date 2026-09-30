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


def test_hatası_suffix_does_not_chop_into_errors_fragment() -> None:
    # " hata" → " errors" must not split "hatası" into "hata"+"sı".
    assert translate("Analiz hatası: bozuk", "en") == "Analysis failed: bozuk"
    assert translate("Tarama hatası: x", "en") == "Scan failed: x"
    assert translate("Bileşen tarama hatası: x", "en") == "Component scan failed: x"
    assert translate("Envanter hatası: x", "en") == "Inventory scan failed: x"
    assert translate("3 hata", "en") == "3 errors"


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


def test_non_tui_surfaces_emit_no_turkish_source_literals() -> None:
    # CLI prints, Web progress strings and analyzer status copy are
    # English-source; only the TUI (Turkish-source + widget auto-translate)
    # and the catalog itself may hold Turkish literals.
    root = Path(__file__).resolve().parents[1]
    leaks: list[str] = []
    for name in ("cli.py", "web.py", "web_queries.py", "web_mutations.py", "analyzer.py"):
        tree = ast.parse((root / "src/macmaid" / name).read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if any(character in node.value for character in "çÇğĞıİöÖşŞüÜ"):
                    leaks.append(f"{name}:{node.lineno} {node.value!r}")
    assert leaks == []


def test_api_progress_localizes_saved_language(tmp_path, monkeypatch) -> None:
    from types import SimpleNamespace

    from macmaid import web
    from macmaid.config import Config

    home = tmp_path / "home"; home.mkdir()
    config = Config(home=home); config.ensure_files()
    config.set_language("tr")
    state = web.WebState(config)
    handler = object.__new__(web.MacMaidHandler); handler.server = SimpleNamespace(state=state)

    state.progress.start("cleaner", "Smart system scan (safe)")
    state.progress.update(40, "User caches", str(home / "Library/Caches/x"))
    state.progress.finish("42 items found")

    payload = handler._route_get("/api/progress", {})
    assert payload["action"] == "Akıllı Sistem Taraması (güvenli)"
    assert payload["phase"] == "42 öğe bulundu"
    assert payload["logs"][0] == "Akıllı Sistem Taraması (güvenli)"
    assert payload["logs"][-1] == "42 öğe bulundu"
    path_lines = [line for line in payload["logs"] if ": " in line and "/" in line.partition(": ")[2]]
    assert all(line.startswith("Kullanıcı önbellekleri: ") for line in path_lines)

    config.set_language("en")
    payload = handler._route_get("/api/progress", {})
    assert payload["phase"] == "42 items found"
    assert all("öğe" not in line for line in payload["logs"])
