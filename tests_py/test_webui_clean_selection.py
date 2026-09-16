from __future__ import annotations

import subprocess
from pathlib import Path


def test_cleaner_does_not_enable_trash_scanning_by_default():
    html = (Path(__file__).parents[1] / "src/macmaid/WebUI/index.html").read_text()
    assert '<input type="checkbox" id="chk-trash">' in html
    assert '<input type="checkbox" id="chk-trash" checked>' not in html


def test_webui_navigation_icons_use_lucide_set():
    root = Path(__file__).parents[1]
    html = (root / "src/macmaid/WebUI/index.html").read_text()
    app_js = (root / "src/macmaid/WebUI/app.js").read_text()
    obsolete_icon_glyphs = "📂📁📄✦⌫⚙◫⌁⌘▤▦◌▣◇↓▧◉⧉◷✚≡⋯●×"

    assert "const LUCIDE_ICONS" in app_js
    assert "function lucideIcon" in app_js
    assert "data-lucide=\"sparkles\"" in html
    assert "data-lucide=\"folder-open\"" in html
    assert not any(glyph in html for glyph in obsolete_icon_glyphs)


def test_clean_selection_never_marks_incomplete_scan_as_selected():
    source = (Path(__file__).parents[1] / "src/macmaid/WebUI/app.js").read_text()
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
