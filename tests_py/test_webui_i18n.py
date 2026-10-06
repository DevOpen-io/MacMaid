"""Every data-i18n* key used in index.html must resolve in both WebUI catalogs."""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path


def _catalog_keys(root: Path) -> dict[str, list[str]]:
    source = (root / "src/macmaid/WebUI/i18n.js").read_text()
    script = (
        "const state = {lang:'en'};\n"
        + source
        + "\nconsole.log(JSON.stringify({en:Object.keys(I18N.en),tr:Object.keys(I18N.tr)}));\n"
    )
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, check=True)
    return json.loads(out.stdout)


def test_webui_data_i18n_keys_resolve_in_both_catalogs() -> None:
    root = Path(__file__).resolve().parents[1]
    html = (root / "src/macmaid/WebUI/index.html").read_text()
    used = {
        key
        for key in re.findall(r'data-i18n(?:-html|-title|-aria|-placeholder)?="([^"]+)"', html)
        if "${" not in key
    }
    catalogs = _catalog_keys(root)
    en, tr = set(catalogs["en"]), set(catalogs["tr"])
    assert used <= en, sorted(used - en)
    assert used <= tr, sorted(used - tr)


def test_webui_catalogs_have_key_parity() -> None:
    root = Path(__file__).resolve().parents[1]
    catalogs = _catalog_keys(root)
    en, tr = set(catalogs["en"]), set(catalogs["tr"])
    assert en == tr, sorted(en ^ tr)
