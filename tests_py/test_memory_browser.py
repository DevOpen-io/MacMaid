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
                browser = pw.chromium.launch(executable_path=shutil.which('chromium'), headless=True)
                page = browser.new_page(viewport={'width':1440, 'height':1000})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                # All process mutations target synthetic objects. No monitoring worker runs.
                page.goto(url, wait_until='domcontentloaded')
                page.locator('[data-tab="memory"]').click()
                page.locator('#memory-processes tr').first.wait_for()
                assert page.locator('#memory-processes tr').count() == 3
                assert page.locator('input[data-key="1:1.0"]').is_disabled()
                for theme in ['dark', 'light', 'midnight', 'cyber']:
                    page.evaluate('(theme) => document.documentElement.dataset.theme = theme', theme)
                    page.wait_for_timeout(500)
                    page.screenshot(path=str(OUTPUT / f'desktop-{theme}.png'))
                page.evaluate("document.documentElement.dataset.theme = 'dark'")
                page.select_option('#memory-filter', 'flutter')
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
                page.set_viewport_size({'width':390, 'height':844})
                page.evaluate("document.querySelector('.content-container').scrollTop = 0")
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUTPUT / 'mobile-dark.png'))
                page.evaluate("document.documentElement.dataset.theme = 'light'")
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUTPUT / 'mobile-light.png'))
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                for control in ['memory-search', 'memory-filter', 'memory-sort']:
                    assert page.locator('#'+control).evaluate('(el) => el.getBoundingClientRect().right <= innerWidth && el.clientWidth >= el.scrollWidth')
                page.set_viewport_size({'width':1440, 'height':1000})
                page.evaluate("document.getElementById('memory-rules').scrollIntoView()")
                page.wait_for_timeout(500)
                page.screenshot(path=str(OUTPUT / 'rules-activity.png'))
                assert not errors, errors
                browser.close()
        finally:
            server.shutdown(); server.server_close(); worker.join()
