"""Small JS behavior checks without a browser or real process actions."""
import subprocess
from pathlib import Path


def _webui_js(root: Path) -> str:
    """Concatenate every served Web UI script (root files plus features/)."""
    webui = root / 'src/macmaid/WebUI'
    parts = [p.read_text() for p in sorted(webui.glob('*.js'))]
    features = webui / 'features'
    if features.is_dir():
        parts += [p.read_text() for p in sorted(features.glob('*.js'))]
    return "\n".join(parts)


def test_memory_filter_and_selection_follow_process_identity():
    root = Path(__file__).parents[1]
    source = (root / 'src/macmaid/WebUI/memory.js').read_text()
    app_source = _webui_js(root)
    catalog = app_source[app_source.index('const MEMORY_COPY = {'):app_source.index('function t(key, fallback =')]
    script = '''
const assert = require('node:assert/strict');
const controls = Object.fromEntries(['memory-search','memory-filter','memory-sort','memory-selection','memory-stop','memory-force'].map(key => [key, {value:''}]));
const document = {getElementById:key=>controls[key], addEventListener:()=>{}};
const I18N = {en:{},tr:{}};
const state = {lang:'en'};
const t = key => I18N[state.lang][key];
''' + catalog + source + '''
controls['memory-filter'].value='all'; controls['memory-sort'].value='rssBytes';
memoryState.snapshot={processes:[
 {key:'7:100',pid:7,name:'dart',exe:'/sdk/dart',category:'flutter',role:'dart-analysis',rssBytes:300,protected:'',forceEligible:true},
 {key:'8:100',pid:8,name:'node',exe:'/sdk/node',category:'developer',role:'development-tool',rssBytes:200,protected:'',forceEligible:false},
 {key:'1:100',pid:1,name:'launchd',exe:'/sbin/launchd',category:'all',role:'application',rssBytes:100,protected:'system-process'}
]};
assert.equal(memoryVisibleRows().length,3);
controls['memory-filter'].value='developer'; assert.equal(memoryVisibleRows().length,2);
controls['memory-filter'].value='flutter'; assert.equal(memoryVisibleRows().length,1);
memoryState.selected=new Set(['7:100','8:100','1:100']); memorySelection();
assert.deepEqual([...memoryState.selected],['7:100','8:100']);
assert.equal(controls['memory-force'].disabled,true);
memoryState.selected=new Set(['7:100']); memorySelection();
assert.equal(controls['memory-force'].disabled,false);
memoryState.snapshot.processes[0].key='7:200'; memorySelection();
assert.equal(memoryState.selected.size,0); assert.equal(controls['memory-stop'].disabled,true);
memoryState.selected=new Set();
addMemorySelection([{key:'safe:100',protected:''},{key:'protected:100',protected:'system-process'}]);
assert.deepEqual([...memoryState.selected],['safe:100']);
memoryState.snapshot.processes=Array.from({length:101},(_,index)=>({key:`${index}:100`,pid:index,name:`proc-${index}`,exe:`/app/${index}`,category:'all',role:'application',protected:''}));
memoryState.selected=new Set(memoryState.snapshot.processes.map(row=>row.key)); memorySelection();
assert.equal(memoryState.selected.size,100);
addMemorySelection(memoryState.snapshot.processes); assert.equal(memoryState.selected.size,100);
state.lang='tr'; assert.equal(mt('title'),'Bellek'); assert.equal(mt('ruleHeadroom',{pressure:15}),'Baskı payı %15 altında');
for(const [key,translations] of Object.entries(MEMORY_COPY)) assert.equal(translations.length,2,key);
'''
    subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)


def test_memory_workspace_keeps_overview_controls_and_safety_context_together():
    root = Path(__file__).parents[1]
    html = (root / 'src/macmaid/WebUI/index.html').read_text()
    script = (root / 'src/macmaid/WebUI/memory.js').read_text()
    catalog = _webui_js(root)
    styles = (root / 'src/macmaid/WebUI/styles.css').read_text()

    assert 'class="memory-overview"' in html
    assert 'class="memory-workbench"' in html
    assert 'class="memory-management-grid"' in html
    assert 'data-i18n="memory.monitoring"' in html
    assert 'data-i18n="memory.rssNote"' in html
    assert 'data-i18n-title="memory.refreshProcesses"' in html
    assert 'data-i18n-aria="memory.processFilters"' in html
    assert 'data-i18n-aria="memory.select"' in html
    assert "sfSymbol('gearshape')" not in script
    assert "'user', 'mini-icon'" not in script
    assert "sfSymbol('slider.horizontal.3')" in script
    assert 'const MEMORY_COPY = {' in catalog
    assert 'const MEMORY_COPY = {' not in script
    assert '.memory-status.is-growing' in styles
    assert '@media (max-width: 520px)' in styles


def test_memory_growth_progress_renders_server_values_only():
    """Collecting cells render real backend progress; no client-side timers."""
    root = Path(__file__).parents[1]
    source = (root / 'src/macmaid/WebUI/memory.js').read_text()
    app_source = _webui_js(root)
    catalog = app_source[app_source.index('const MEMORY_COPY = {'):app_source.index('function t(key, fallback =')]
    script = '''
const assert = require('node:assert/strict');
const document = {getElementById:()=>null, querySelector:()=>null, querySelectorAll:()=>[], addEventListener:()=>{}};
const I18N = {en:{},tr:{}};
const state = {lang:'en'};
const t = (key, fallback='') => (I18N[state.lang] && I18N[state.lang][key]) || fallback || key;
const escapeHtml = s => String(s);
const sfSymbol = () => '';
const formatBytes = b => `${b}B`;
''' + catalog + source + '''
const collecting = {growthBytes:null, growthWindowElapsedSeconds:402, growthWindowRemainingSeconds:198, growthWindowProgress:0.67, rssBytes:100};
const cell = memoryGrowthCell(collecting, 'is-collecting');
assert.match(cell, /Collecting history/);
assert.match(cell, /growth-progress-fill/);
assert.match(cell, /width: 67%/);
assert.match(cell, /6:42 \/ 10:00/);
assert.match(cell, /3:18 left/);
assert.equal(memoryDuration(402), '6:42');
assert.equal(memoryDuration(600), '10:00');
assert.equal(memoryGrowthLabel(collecting), 'Collecting history · 6:42 / 10:00 · 3:18 left');

const ready = {growthBytes:44*1024*1024, growing:true, growthWindowElapsedSeconds:600, growthWindowRemainingSeconds:0, growthWindowProgress:1, rssBytes:100};
const readyCell = memoryGrowthCell(ready, 'is-growing');
assert.match(readyCell, /\+46137344B/);
assert.ok(!readyCell.includes('growth-progress-fill'), 'ready rows must not render the progress bar');

const unavailable = {growthBytes:null, growthWindowElapsedSeconds:null, growthWindowRemainingSeconds:null, growthWindowProgress:null, rssBytes:null};
const unCell = memoryGrowthCell(unavailable, 'is-collecting');
assert.match(unCell, /Unavailable/);
assert.ok(!unCell.includes('growth-progress-fill'), 'unavailable rows must not fake progress');

state.lang='tr';
assert.equal(memoryGrowthLabel(collecting), 'Geçmiş toplanıyor · 6:42 / 10:00 · 3:18 kaldı');
'''
    subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)

    # The single shared refresh loop is the only timer; progress must come from
    # server snapshots, never wall-clock counting inside the renderer.
    assert source.count('setInterval') == 1
    assert 'Date.now' not in source and 'performance.now' not in source
