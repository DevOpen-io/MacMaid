from __future__ import annotations

import subprocess
from pathlib import Path


def _webui_js(root: Path) -> str:
    """Concatenate every served Web UI script (root files plus features/)."""
    webui = root / "src/macmaid/WebUI"
    parts = [p.read_text() for p in sorted(webui.glob("*.js"))]
    features = webui / "features"
    if features.is_dir():
        parts += [p.read_text() for p in sorted(features.glob("*.js"))]
    return "\n".join(parts)


def test_cleaner_does_not_enable_trash_scanning_by_default():
    html = (Path(__file__).parents[1] / "src/macmaid/WebUI/index.html").read_text()
    assert '<input type="checkbox" id="chk-trash">' in html
    assert '<input type="checkbox" id="chk-trash" checked>' not in html


def test_webui_icons_use_shared_symbol_catalog():
    root = Path(__file__).parents[1]
    html = (root / "src/macmaid/WebUI/index.html").read_text()
    app_js = _webui_js(root)
    obsolete_icon_glyphs = "📂📁📄✦⌫⚙◫⌁⌘▤▦◌▣◇↓▧◉⧉◷✚≡⋯●×"

    memory_js = (root / "src/macmaid/WebUI/memory.js").read_text()

    assert "const SF_SYMBOLS" in app_js
    assert "function sfSymbol" in app_js
    assert "data-icon=\"sparkles\"" in html
    assert "data-icon=\"folder\"" in html
    assert "lucide" not in html.lower()
    assert "lucide" not in app_js.lower()
    assert "lucide" not in memory_js.lower()
    assert not any(glyph in html for glyph in obsolete_icon_glyphs)


def test_every_referenced_icon_exists_in_symbol_catalog():
    import re

    root = Path(__file__).parents[1]
    html = (root / "src/macmaid/WebUI/index.html").read_text()
    app_js = _webui_js(root)
    memory_js = (root / "src/macmaid/WebUI/memory.js").read_text()

    catalog_start = app_js.index("const SF_SYMBOLS = {")
    catalog_end = app_js.index("};", catalog_start)
    catalog = app_js[catalog_start:catalog_end]
    defined = set(re.findall(r"'([a-z0-9.]+)': \['(?:fill|stroke)'", catalog))
    assert len(defined) > 30
    assert {"sparkles", "trash", "gearshape", "internaldrive", "memorychip",
            "terminal", "magnifyingglass", "arrow.clockwise", "checkmark.circle",
            "exclamationmark.triangle", "info.circle", "folder", "xmark"} <= defined

    referenced = set(re.findall(r'data-icon="([a-z0-9.]+)"', html))
    for call in re.finditer(r"sfSymbol\(([^)]*)\)", app_js + memory_js):
        first_arg = call.group(1).split(",")[0]
        referenced |= set(re.findall(r"(?:^|\?|:)\s*'([a-z0-9.]+)'", first_arg))
    # Names bound to variables before rendering (categoryIcon/statusIcon/toast map).
    dynamic_names = {"square.stack.3d.up", "terminal", "cpu", "app", "shield",
                     "chart.line.uptrend.xyaxis", "checkmark", "clock",
                     "checkmark.circle", "exclamationmark.circle",
                     "exclamationmark.triangle", "info.circle"}
    assert dynamic_names <= defined
    missing = referenced - defined
    assert not missing, f"icon references without catalog entries: {sorted(missing)}"


def test_project_cleanup_formats_unix_timestamps_for_display():
    source = (
        Path(__file__).parents[1] / "src/macmaid/WebUI/features/purge.js"
    ).read_text()
    start = source.index("function formatPurgeModified(value)")
    end = source.index("function renderPurgeArtifacts()", start)
    formatter = source[start:end]
    script = f"""
const assert = require('node:assert/strict');
const state = {{ lang: 'en' }};
const t = (_key, fallback) => fallback;
{formatter}
assert.equal(formatPurgeModified(1789976963.5401623), 'Sep 21, 2026');
assert.equal(formatPurgeModified(''), 'Unknown');
assert.equal(formatPurgeModified('not-a-date'), 'not-a-date');
"""
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)


def test_explanatory_copy_uses_compact_information_tooltips():
    root = Path(__file__).parents[1]
    ui_source = (root / "src/macmaid/WebUI/ui.js").read_text()
    clean_source = (root / "src/macmaid/WebUI/features/clean.js").read_text()
    styles = (root / "src/macmaid/WebUI/styles.css").read_text()

    assert "function enhanceInformationCopy" in ui_source
    assert "'.pane-header .pane-subtitle'" in ui_source
    assert "'.memory-section-header .memory-note[data-i18n]'" in ui_source
    assert "'#clean-profile-context'" in ui_source
    assert "informationButton(item.reason, 'mm-table-info')" in clean_source
    assert '<span class="table-secondary">${escapeHtml(item.reason)}</span>' not in clean_source
    assert "'.card-desc[data-i18n]'" in ui_source
    assert "'.setting-row .text-muted[data-i18n]'" in ui_source
    assert "'.hero-state-desc[data-i18n]'" not in ui_source
    assert "new MutationObserver(records =>" in ui_source
    assert ".mm-info-tooltip" in styles
    assert ".mm-info-source" in styles
    assert ".mm-info-button .sf { width: 18px; height: 18px;" in styles


def test_clean_selection_never_marks_incomplete_scan_as_selected():
    source = _webui_js(Path(__file__).parents[1])
    start = source.index("function cleanActionableItems()")
    end = source.index("async function executeClean()", start)
    selection_code = source[start:end]
    script = f"""
const state = {{ currentScan: null, selectedCleanItems: new Set() }};
const elements = {{
  'res-selected-bytes': {{}}, 'master-clean-chk': {{}},
  'btn-select-all': {{}}, 'btn-deselect-all': {{}}, 'btn-execute-clean': {{}}
}};
global.document = {{ getElementById: id => elements[id] }};
global.formatBytes = value => String(value);
global.syncMasterCheckbox = (id, total, selected) => {{
  const checkbox = elements[id];
  checkbox.checked = total > 0 && selected === total;
  checkbox.indeterminate = selected > 0 && selected < total;
  checkbox.disabled = total === 0;
}};
global.renderScanResults = () => {{}};
{selection_code}
const safe = {{ id: 'safe', risk: 'SAFE', estimatedBytes: 10 }};
const manual = {{ id: 'manual', risk: 'MANUAL', estimatedBytes: 20 }};
state.currentScan = {{ isComplete: false, items: [safe, manual] }};
state.selectedCleanItems = new Set(['safe']);
updateSelectedCleanStats();
if (state.selectedCleanItems.size !== 0 || !elements['master-clean-chk'].disabled || !elements['btn-select-all'].disabled || !elements['btn-execute-clean'].disabled) process.exit(1);
if (setCleanSelection(true) !== false || state.selectedCleanItems.size !== 0) process.exit(2);
state.currentScan = {{ isComplete: true, items: [safe, manual] }};
if (setCleanSelection(true) !== true || !state.selectedCleanItems.has('safe') || state.selectedCleanItems.has('manual')) process.exit(3);
updateSelectedCleanStats();
if (elements['master-clean-chk'].disabled || elements['btn-execute-clean'].disabled) process.exit(4);
"""
    subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
