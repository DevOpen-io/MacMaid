"""Opt-in real Web UI E2E for the developer package-caches page.

Run with MACMAID_BROWSER_TESTS=1 (Playwright must be installed).

Isolation contract: the whole flow runs against a temporary HOME with a minimal
PATH containing only a synthetic npm provider. No real user configuration files,
no real package caches and no real manager binaries are touched. A sentinel
whitelist/preferences pair inside the isolated HOME plus the user's real
whitelist (read-only snapshot) are verified unchanged afterwards.
"""
import json
import os
import shutil
import stat
import threading
import time
from pathlib import Path

import pytest

from macmaid import cleaner, web
from macmaid.config import Config

REAL_HOME = Path.home()
REAL_WHITELIST = REAL_HOME / ".config" / "macmaid" / "whitelist"

FAKE_NPM = """#!/usr/bin/env python3
import shutil
import sys
from pathlib import Path

ROOT = Path({root!r})
if sys.argv[1:] == ["config", "get", "cache"]:
    print(ROOT)
elif sys.argv[1:3] == ["cache", "clean"]:
    shutil.rmtree(ROOT / "_cacache", ignore_errors=True)
    (ROOT / "_cacache").mkdir()
sys.exit(0)
"""


@pytest.mark.skipif(os.environ.get("MACMAID_BROWSER_TESTS") != "1", reason="Opt-in headless browser test")
def test_devcaches_webui_scan_clean_rescan_isolated(monkeypatch, tmp_path):
    from playwright.sync_api import sync_playwright

    home = (tmp_path / "home").resolve()
    home.mkdir()
    # Synthetic cache fixtures inside the isolated HOME (never the real one).
    cacache = home / ".npm" / "_cacache"
    npx = home / ".npm" / "_npx"
    logs = home / ".npm" / "_logs"
    for directory in (cacache, npx, logs):
        directory.mkdir(parents=True)
    (cacache / "blob.bin").write_bytes(b"c" * (2 * 1024 * 1024))
    (npx / "pkg.bin").write_bytes(b"n" * (2 * 1024 * 1024))
    (logs / "debug.log").write_bytes(b"small")  # below the 1 MiB listing threshold

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    npm_script = fake_bin / "npm"
    npm_script.write_text(FAKE_NPM.format(root=str(home / ".npm")))
    npm_script.chmod(npm_script.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

    # Minimal PATH: only the fake provider exists; real brew/pnpm/uv/npm are invisible.
    monkeypatch.setenv("PATH", f"{fake_bin}:/usr/bin:/bin")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(web, "Config", lambda: Config(home=home))
    monkeypatch.setattr(cleaner.os, "geteuid", lambda: 501)

    # Sentinel user files: the backend must never rewrite configuration.
    # The whitelist is intentionally absent until phase 5: a non-empty strict
    # whitelist fail-closed skips every command-based cleanup by design.
    config_dir = home / ".config" / "macmaid"
    config_dir.mkdir(parents=True)
    whitelist = config_dir / "whitelist"
    preferences = config_dir / "preferences.json"
    preferences.write_text(json.dumps({"language": "en", "sentinel": "keep-me"}))
    real_whitelist_before = REAL_WHITELIST.read_bytes() if REAL_WHITELIST.exists() else None

    state = web.WebState()
    server = web.MacMaidHTTPServer(("127.0.0.1", 0), state)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f"http://127.0.0.1:{server.server_port}"
    try:
        with sync_playwright() as pw:
            kwargs = {"executable_path": shutil.which("chromium")} if shutil.which("chromium") else {}
            browser = pw.chromium.launch(headless=True, **kwargs)
            page = browser.new_page(viewport={"width": 1500, "height": 1000})
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(url, wait_until="domcontentloaded")
            page.locator('[data-tab="developer"]').click()
            page.locator('[data-devsubtab="caches"]').click()

            def rows():
                return page.evaluate("""() => [...document.querySelectorAll('#tbody-devcaches tr')].map(tr => {
                    const t = tr.querySelectorAll('td');
                    if (t.length < 6) return null;
                    const chk = tr.querySelector('input.devcache-chk');
                    return {id: chk?.dataset.id, checked: chk?.checked, disabled: chk?.disabled,
                            label: t[1].innerText.trim(), path: t[2].innerText.trim(),
                            risk: t[3].innerText.trim(), size: t[5].innerText.trim()};
                }).filter(Boolean)""")

            def wait_rows(timeout=120):
                deadline = time.time() + timeout
                while time.time() < deadline:
                    if page.evaluate("document.querySelectorAll('#tbody-devcaches tr td').length") >= 6:
                        return
                    page.wait_for_timeout(150)
                raise AssertionError("dev caches table never populated")

            # 1. Scan: fake npm row + manual npx row; sub-threshold _logs stays hidden.
            page.locator("#btn-scan-devcaches").click()
            wait_rows()
            first = rows()
            labels = [r["label"] for r in first]
            assert any(label.startswith("npm cache clean") for label in labels), labels
            assert any(label.startswith("npx package cache") for label in labels), labels
            assert not any("logs" in label.lower() for label in labels), labels
            native = next(r for r in first if r["label"].startswith("npm cache clean"))
            manual = next(r for r in first if r["label"].startswith("npx package cache"))
            assert native["checked"] and not native["disabled"]
            assert manual["disabled"] and not manual["checked"]
            assert native["path"] == str(cacache)

            # 2. Clean through the real modal flow.
            page.locator("#btn-execute-devcaches-clean").click()
            page.locator("#modal-container:not(.hidden)").wait_for(timeout=10000)
            assert str(cacache) in page.locator("#modal-body").inner_text()
            page.locator("#modal-footer .btn-danger").click()
            deadline = time.time() + 120
            toast_text = ""
            while time.time() < deadline:
                toast = page.locator(".toast").last
                if toast.count():
                    toast_text = toast.inner_text()
                    toast_class = toast.get_attribute("class") or ""
                    break
                page.wait_for_timeout(120)
            assert "success" in toast_class, toast_text
            assert "failed" not in toast_text.lower(), toast_text
            assert not any(cacache.iterdir())

            # 3. Auto-rescan: cleaned row must not return; manual row persists.
            deadline = time.time() + 120
            second = []
            while time.time() < deadline:
                second = rows()
                if second and not any(r["label"].startswith("npm cache clean") for r in second):
                    break
                page.wait_for_timeout(150)
            assert not any(r["label"].startswith("npm cache clean") for r in second), second
            assert any(r["label"].startswith("npx package cache") for r in second), second

            # 4. Stale ids are rejected instead of mutating again.
            stale = page.evaluate("""async (ids) => {
                const res = await fetch('/api/developer/caches/clean', {method: 'POST',
                    headers: {'Content-Type': 'application/json'}, body: JSON.stringify({itemIds: ids})});
                return {status: res.status, body: await res.json()};
            }""", [native["id"]])
            assert stale["status"] != 200
            assert not stale["body"].get("success")

            # 5. Non-empty whitelist: command items are skipped fail-closed
            #    and user config files must remain byte-identical.
            whitelist.write_text("sentinel-whitelist-entry\n")
            (cacache / "blob2.bin").write_bytes(b"d" * (2 * 1024 * 1024))
            page.locator("#btn-scan-devcaches").click()
            deadline = time.time() + 120
            third = []
            while time.time() < deadline:
                third = rows()
                if any(r["label"].startswith("npm cache clean") for r in third):
                    break
                page.wait_for_timeout(150)
            assert any(r["label"].startswith("npm cache clean") for r in third), third
            page.locator("#btn-execute-devcaches-clean").click()
            page.locator("#modal-container:not(.hidden)").wait_for(timeout=10000)
            page.evaluate("document.querySelectorAll('.toast').forEach(el => el.remove())")
            page.locator("#modal-footer .btn-danger").click()
            deadline = time.time() + 120
            toast2_text = ""
            while time.time() < deadline:
                toast = page.locator(".toast").last
                if toast.count():
                    toast2_text = toast.inner_text().replace("\n", " ")
                    break
                page.wait_for_timeout(120)
            assert "skipped" in toast2_text.lower(), toast2_text
            assert (cacache / "blob2.bin").exists()

            assert not errors, errors
            browser.close()
    finally:
        server.shutdown()
        server.server_close()
        worker.join()

    # 5. Isolation: sentinel config untouched, real user whitelist untouched.
    assert whitelist.read_text() == "sentinel-whitelist-entry\n"
    assert preferences.read_text() == json.dumps({"language": "en", "sentinel": "keep-me"})
    real_whitelist_after = REAL_WHITELIST.read_bytes() if REAL_WHITELIST.exists() else None
    assert real_whitelist_after == real_whitelist_before
