"""Small JS behavior checks without a browser or real process actions."""
import subprocess
from pathlib import Path


def test_memory_filter_and_selection_follow_process_identity():
    source = (Path(__file__).parents[1] / 'src/macmaid/WebUI/memory.js').read_text()
    script = '''
const assert = require('node:assert/strict');
const controls = Object.fromEntries(['memory-search','memory-filter','memory-sort','memory-selection','memory-stop','memory-force'].map(key => [key, {value:''}]));
const document = {getElementById:key=>controls[key], addEventListener:()=>{}};
const I18N = {en:{},tr:{}};
const state = {lang:'en'};
const t = key => I18N[state.lang][key];
''' + source + '''
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
state.lang='tr'; assert.equal(mt('title'),'Bellek');
for(const [key,translations] of Object.entries(MEMORY_COPY)) assert.equal(translations.length,2,key);
'''
    subprocess.run(['node', '-e', script], check=True, capture_output=True, text=True)


def test_memory_workspace_keeps_overview_controls_and_safety_context_together():
    root = Path(__file__).parents[1]
    html = (root / 'src/macmaid/WebUI/index.html').read_text()
    styles = (root / 'src/macmaid/WebUI/styles.css').read_text()

    assert 'class="memory-overview"' in html
    assert 'class="memory-workbench"' in html
    assert 'class="memory-management-grid"' in html
    assert 'data-i18n="memory.monitoring"' in html
    assert 'data-i18n="memory.rssNote"' in html
    assert '.memory-status.is-growing' in styles
    assert '@media (max-width: 520px)' in styles
