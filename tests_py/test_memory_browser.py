"""Opt-in browser regression using only synthetic process actions.

Run with MACMAID_BROWSER_TESTS=1 and Playwright available via uv --with playwright.
A locally installed Chromium is used when available; otherwise install Playwright's browser.
"""
import os
import shutil
import tempfile
import threading
import time
from collections import deque
from pathlib import Path
from unittest.mock import patch

import pytest

from macmaid.config import Config
from macmaid.web import MacMaidHTTPServer, WebState


@pytest.mark.skipif(os.environ.get("MACMAID_BROWSER_TESTS") != "1", reason="Opt-in headless browser test")
def test_memory_browser_workflow(tmp_path):
    import base64

    from playwright.sync_api import sync_playwright
    OUTPUT = tmp_path / 'captures'
    OUTPUT.mkdir(exist_ok=True)

    class FakeProcess:
        pid = 54321
        def terminate(self): pass
        def kill(self): pass

    with tempfile.TemporaryDirectory() as home:
        state = WebState(Config(home=Path(home)))
        service = state.memory
        row = dict(key='54321:100.0', pid=54321, created=100.0, name='dart', exe='/opt/flutter/bin/cache/dart-sdk/bin/dart', category='flutter', role='dart-analysis', entrypoint='/opt/flutter/bin/cache/dart-sdk/bin/dart', rssBytes=3*1024**3, cpuPercent=3.2, protected='', helper=True, growthBytes=512*1024**2, growing=True, historyReady=True, forceEligible=False)
        protected = dict(row, key='1:1.0', pid=1, name='launchd', exe='/sbin/launchd', category='all', role='application', protected='system-process', helper=False, growing=False, growthBytes=0, rssBytes=30*1024**2)
        editor = dict(row, key='54322:100.0', pid=54322, name='Code Helper (Renderer)', exe='/Applications/Visual Studio Code.app/Contents/MacOS/Code Helper', category='all', role='application', helper=False, growing=False, growthBytes=None, historyReady=False, rssBytes=600*1024**2)
        service.rows = {r['key']: r for r in [row, protected, editor]}
        service.metrics = dict(used=12*1024**3, total=16*1024**3, available=4*1024**3, swap=2*1024**3, pressureHeadroom=10, measuredAt=time.time())
        service.histories[row['key']] = deque([(time.monotonic()-600+i*5, 2*1024**3+i*5*1024**2) for i in range(121)])
        service._target = lambda key: (FakeProcess(), service.rows[key])
        server = MacMaidHTTPServer(('127.0.0.1', 0), state)
        worker = threading.Thread(target=server.serve_forever, daemon=True); worker.start()
        url = f'http://127.0.0.1:{server.server_port}'
        try:
            with sync_playwright() as pw, patch('macmaid.memory.psutil.wait_procs', lambda procs, timeout: ([], procs)):
                chrome = Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
                executable = shutil.which('chromium') or (str(chrome) if chrome.is_file() else None)
                browser = pw.chromium.launch(executable_path=executable, headless=True)
                page = browser.new_page(viewport={'width':1440, 'height':1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))

                def capture_surface(name, selector):
                    """Capture the same shared surface in browser and native-shell modes."""
                    for shell, native in [('web', False), ('desktop', True)]:
                        page.evaluate(
                            "native => { document.documentElement.classList.toggle('is-native-app', native); document.body.classList.toggle('is-native-app', native); }",
                            native,
                        )
                        for theme in ['dark', 'light']:
                            page.evaluate('(value) => document.documentElement.dataset.theme = value', theme)
                            page.locator(selector).screenshot(
                                path=str(OUTPUT / f'{shell}-{name}-{theme}.png'),
                                animations='disabled',
                            )
                    page.evaluate("document.documentElement.classList.remove('is-native-app'); document.body.classList.remove('is-native-app')")
                    page.evaluate("document.documentElement.dataset.theme = 'dark'")

                # All process mutations target synthetic objects. No monitoring worker runs.
                pixel = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL/nwAAAABJRU5ErkJggg==')
                page.route('**/api/memory/icon?**', lambda route: route.fulfill(status=200, body=pixel, content_type='image/png'))
                page.goto(url, wait_until='domcontentloaded')
                page.locator('[data-tab="memory"]').click()
                page.locator('#memory-processes tr').first.wait_for()
                page.screenshot(path=str(OUTPUT / 'workspace-dark.png'))
                # Separate the nested table scrollbar from the page scrollbar
                # without disabling either scroll region.
                scroll_edges = page.evaluate('''() => {
                  const pane = document.getElementById('pane-memory');
                  const table = pane.querySelector('.memory-table-wrap');
                  return {
                    gap: pane.getBoundingClientRect().right - table.getBoundingClientRect().right,
                    pageOverflow: getComputedStyle(pane).overflowY,
                    tableOverflow: getComputedStyle(table).overflowY,
                  };
                }''')
                assert scroll_edges['gap'] >= 20, scroll_edges
                assert scroll_edges['pageOverflow'] == 'auto'
                assert scroll_edges['tableOverflow'] == 'auto'
                assert page.locator('#memory-processes tr').count() == 3
                # The application group uses its real bundle artwork. Missing
                # icons must reveal the existing category symbol instead.
                app_row = page.locator('#memory-processes tr[data-group-id^="app:"]')
                image = app_row.locator('.memory-app-icon')
                assert image.count() == 1
                image.evaluate('(img) => { img.loading = "eager"; }')
                page.wait_for_function("document.querySelector('#memory-processes tr[data-group-id^=\"app:\"] .memory-app-icon').naturalWidth > 0")
                page.unroute('**/api/memory/icon?**')
                page.route('**/api/memory/icon?**', lambda route: route.fulfill(status=404, body=''))
                page.evaluate('renderMemory()')
                app_row.locator('.memory-app-icon').evaluate('(img) => { img.loading = "eager"; }')
                page.wait_for_function("document.querySelector('#memory-processes tr[data-group-id^=\"app:\"] .memory-app-icon') === null")
                assert app_row.locator('.memory-proc-icon .sf').count() == 1
                icon_positions = page.evaluate('''() => {
                  const app = document.querySelector('#memory-processes tr[data-group-id^="app:"]');
                  const process = document.querySelector('#memory-processes tr[data-group-id^="proc:"]');
                  const expanded = app.cloneNode(true);
                  expanded.classList.add('memory-group-row');
                  const disclosure = document.createElement('button');
                  disclosure.className = 'memory-disclosure';
                  expanded.querySelector('.memory-proc-info').prepend(disclosure);
                  app.after(expanded);
                  const left = row => row.querySelector('.memory-proc-icon').getBoundingClientRect().left;
                  const positions = [left(app), left(process), left(expanded)];
                  expanded.remove();
                  return positions;
                }''')
                assert max(icon_positions) - min(icon_positions) < 1, icon_positions
                page.unroute('**/api/memory/icon?**')
                assert page.locator('input[data-key="1:1.0"]').is_disabled()
                memory_help = page.locator('.memory-help summary')
                memory_help.focus()
                assert memory_help.evaluate('(el) => el === document.activeElement')
                memory_help.press('Enter')
                assert page.locator('.memory-help-popover').is_visible()
                memory_help.press('Enter')
                for theme in ['dark', 'light', 'midnight', 'cyber']:
                    page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
                    page.wait_for_timeout(500)
                    page.screenshot(path=str(OUTPUT / f'desktop-{theme}.png'))
                page.evaluate("document.documentElement.dataset.theme = 'dark'")
                page.select_option('#memory-filter', 'developer')
                assert page.locator('#memory-processes tr').count() == 1
                page.locator('input[data-key="54321:100.0"]').check()
                page.evaluate('refreshMemory()')
                assert page.locator('input[data-key="54321:100.0"]').is_checked()
                page.locator('[data-memory-action="details"]').click()
                page.locator('.memory-trend').wait_for()
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUTPUT / 'details.png'))
                page.locator('[data-memory-action="rule"]').click()
                page.locator('#memory-rule-form').wait_for()
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUTPUT / 'rule.png'))
                page.locator('#memory-rule-form input[name="consent"]').check()
                page.get_by_role('button', name='Save helper rule', exact=True).click()
                page.locator('#memory-rules .memory-rule').wait_for()
                assert service.settings['paused'] is True
                rule_button = page.locator('#memory-rules [data-rule-id]')
                rule_button.focus()
                page.evaluate('refreshMemory()')
                assert rule_button.evaluate('(el) => el === document.activeElement')
                service.configure({'operation': 'exclude', 'key': '54322:100.0'})
                page.evaluate('refreshMemory()')
                exclusion_button = page.locator('#memory-exclusions [data-exclusion]')
                exclusion_button.focus()
                page.evaluate('refreshMemory()')
                assert exclusion_button.evaluate('(el) => el === document.activeElement')
                page.locator('#memory-stop').click()
                page.locator('#memory-stop-consent').wait_for()
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUTPUT / 'review-stop.png'))
                capture_surface('review-modal', '.glass-modal')
                page.locator('#memory-stop-consent').check()
                page.get_by_role('button', name='Stop selected processes', exact=True).click()
                page.wait_for_function("document.getElementById('memory-outcome').textContent.includes('Still running')")
                assert page.locator('#memory-force').is_enabled()
                page.locator('#memory-force').click()
                page.locator('#memory-stop-consent').wait_for()
                assert 'SIGKILL' in page.locator('#modal-body').inner_text()
                page.get_by_role('button', name='Cancel', exact=True).click()
                page.select_option('#memory-filter', 'all')
                page.evaluate("applyLanguage('tr')")
                assert 'Son saatteki yerleşik bellek' in page.locator('#memory-details').inner_text()
                assert 'Growing memory means' not in page.locator('#memory-details').inner_text()
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUTPUT / 'desktop-turkish.png'))
                page.evaluate("applyLanguage('en'); renderMemory()")
                # At compact desktop widths the source list must still expose
                # every nested destination; a collapsed icon rail loses them.
                page.set_viewport_size({'width':680, 'height':840})
                page.locator('[data-tab="developer"]').click()
                page.locator('[data-devsubtab="sdks"]').click()
                assert page.locator('#subpane-dev-sdks').is_visible()
                page.locator('[data-tab="more"]').click()
                page.locator('[data-subtab="history"]').click()
                assert page.locator('#subpane-more-history').is_visible()
                page.locator('[data-tab="memory"]').click()
                page.set_viewport_size({'width':390, 'height':844})
                page.evaluate("document.querySelector('.content-container').scrollTop = 0")
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUTPUT / 'mobile-dark.png'))
                page.evaluate("document.documentElement.dataset.theme = 'light'")
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUTPUT / 'mobile-light.png'))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                for control in ['memory-search', 'memory-filter', 'memory-sort']:
                    assert page.locator('#'+control).evaluate('(el) => el.getBoundingClientRect().right <= innerWidth && el.clientWidth >= el.scrollWidth'), page.locator('#'+control).evaluate('(el) => ({right: el.getBoundingClientRect().right, width: el.clientWidth, scroll: el.scrollWidth, viewport: innerWidth})')
                page.set_viewport_size({'width':1440, 'height':1000})
                page.locator('[data-tab="memory"]').click()
                page.evaluate("document.querySelector('.content-container').scrollTop = 0")
                capture_surface('memory-top', '.memory-overview')
                capture_surface('memory-table', '.memory-workbench')
                capture_surface('memory-details', '#memory-details')

                for tab, name in [
                    ('dashboard', 'system-status'),
                    ('cleaner', 'clean'),
                    ('apps', 'applications'),
                    ('optimize', 'maintenance'),
                    ('analyzer', 'storage'),
                    ('purge', 'project-cleanup'),
                ]:
                    page.locator(f'[data-tab="{tab}"]').click()
                    page.wait_for_timeout(300)
                    capture_surface(name, f'#pane-{tab}')

                page.locator('[data-tab="cleaner"]').click()
                assert page.locator('.clean-idle-state').is_visible()
                assert 'Nothing is removed during a scan' in page.locator('.clean-idle-state').inner_text()
                page.evaluate("applyLanguage('tr')")
                assert 'Tarama sırasında hiçbir şey silinmez' in page.locator('.clean-idle-state').inner_text()
                page.evaluate("applyLanguage('en')")
                page.screenshot(path=str(OUTPUT / 'workspace-clean-light.png'))
                page.evaluate("document.getElementById('scan-results-box').classList.remove('hidden')")
                assert not page.locator('.clean-idle-state').is_visible()
                capture_surface('clean-results', '#scan-results-box')
                page.evaluate("document.getElementById('scan-results-box').classList.add('hidden')")
                page.evaluate("document.getElementById('cleaner-progress-card').classList.remove('hidden')")
                capture_surface('progress', '#cleaner-progress-card')
                page.evaluate("document.getElementById('cleaner-progress-card').classList.add('hidden')")

                page.locator('[data-tab="developer"]').click()
                for subtab in ['storage', 'caches', 'runtimes', 'environments', 'tools', 'sdks']:
                    page.locator(f'[data-devsubtab="{subtab}"]').click()
                    page.wait_for_timeout(200)
                    capture_surface(f'developer-{subtab}', f'#subpane-dev-{subtab}')

                page.locator('[data-tab="more"]').click()
                for subtab in [
                    'leftovers', 'installers', 'treemap', 'browser-storage',
                    'smart-downloads', 'duplicates', 'large-files', 'snapshots',
                    'doctor', 'history', 'whitelist',
                ]:
                    page.locator(f'[data-subtab="{subtab}"]').click()
                    page.wait_for_timeout(200)
                    capture_surface(f'utility-{subtab}', f'#subpane-more-{subtab}')

                page.locator('#settings-btn').click()
                page.wait_for_timeout(300)
                capture_surface('settings', '#pane-settings')
                page.locator('#btn-manage-permissions').click()
                page.locator('#permission-modal-list').wait_for()
                capture_surface('permissions', '.glass-modal')
                page.locator('#modal-close-btn').click()

                page.locator('[data-tab="memory"]').click()
                page.evaluate("document.getElementById('memory-rules').scrollIntoView()")
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUTPUT / 'rules-activity.png'))
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown(); server.server_close(); worker.join()
