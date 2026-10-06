from __future__ import annotations

import threading
from types import SimpleNamespace
from unittest.mock import Mock

from macmaid import features, web, web_mutations
from macmaid.system import CommandResult


def handler(state):
    route = object.__new__(web.MacMaidHandler)
    route.server = SimpleNamespace(state=state)
    return route


def state():
    return SimpleNamespace(token="secret", generations={}, review_tokens={}, lock=threading.RLock())


def test_homebrew_outdated_exit_one_with_json_means_update_available(monkeypatch):
    monkeypatch.setattr(features, "which", lambda name: "brew")
    responses = iter([
        CommandResult(0),
        CommandResult(1, '{"formulae": [], "casks": [{"name": "macmaid", "installed_versions": ["0.9.29"], "current_version": "0.9.30"}]}'),
    ])
    monkeypatch.setattr(features, "run_command", lambda *args, **kwargs: next(responses))

    assert features.macmaid_brew_update_status() == {
        "available": True, "installed": True, "checked": True, "installedVersion": "0.9.29",
        "latestVersion": "0.9.30", "brewCask": True, "reason": None,
    }


def test_update_check_refreshes_homebrew_and_update_requires_review(monkeypatch):
    current = state()
    route = handler(current)
    status = {"installed": True, "available": True, "installedVersion": "0.9.27", "latestVersion": "0.9.28", "canApply": True}
    check = Mock(return_value=status)
    apply = Mock(return_value=dict(status, updated=True))
    monkeypatch.setattr(web_mutations, "macmaid_update_status", check)
    monkeypatch.setattr(web_mutations, "apply_macmaid_brew_update", apply)

    assert route._route_post("/api/macmaid/update/check", {}) == status
    assert check.call_args.kwargs == {"refresh": True}

    prepared = route._route_post("/api/macmaid/update", {"reviewOnly": True})
    result = route._route_post("/api/macmaid/update", {"reviewToken": prepared["reviewToken"]})
    assert result["success"] is True and result["updated"] is True
    apply.assert_called_once_with()


def test_brew_formula_channel_uses_formula_commands(monkeypatch):
    monkeypatch.setattr(features, "which", lambda name: "brew")
    calls: list[list[str]] = []

    def fake_run(binary, args, **kwargs):
        calls.append(list(args))
        if args[:2] == ["list", "--cask"]:
            return CommandResult(1, stderr="no cask")
        if args[:1] == ["list"]:
            return CommandResult(0)
        if args[:1] == ["outdated"]:
            return CommandResult(1, '{"formulae": [{"name": "macmaid", "installed_versions": ["0.9.29"], "current_version": "0.9.30"}], "casks": []}')
        raise AssertionError(args)

    monkeypatch.setattr(features, "run_command", fake_run)
    status = features.macmaid_update_status()
    assert status["channel"] == "homebrew-formula"
    assert status["available"] is True and status["canApply"] is True
    assert status["updateCommand"] == "brew upgrade macmaid"
    assert not any("--cask" in call for call in calls if call and call[0] == "outdated")


def test_non_brew_channel_uses_github_releases(monkeypatch):
    monkeypatch.setattr(features, "macmaid_install_channel", lambda: "uv-tool")
    monkeypatch.setattr(features, "_latest_github_release",
                        lambda version: {"version": "99.0.0", "url": "https://example.invalid/release"})
    status = features.macmaid_update_status()
    assert status["channel"] == "uv-tool"
    assert status["available"] is True and status["canApply"] is False
    from macmaid import __version__
    assert status["installedVersion"] == __version__
    assert status["latestVersion"] == "99.0.0"
    assert status["updateCommand"] == "sh install.sh"
    assert status["updateUrl"] == "https://example.invalid/release"


def test_non_brew_channel_reports_up_to_date(monkeypatch):
    monkeypatch.setattr(features, "macmaid_install_channel", lambda: "app-bundle")
    monkeypatch.setattr(features, "_latest_github_release",
                        lambda version: {"version": version, "url": "https://example.invalid/x"})
    status = features.macmaid_update_status()
    assert status["available"] is False
    assert status["reason"] == "MacMaid is up to date"
    assert status["updateCommand"] is None


def test_non_brew_channel_handles_github_failure(monkeypatch):
    monkeypatch.setattr(features, "macmaid_install_channel", lambda: "source")
    def boom(version):
        raise OSError("network unreachable")
    monkeypatch.setattr(features, "_latest_github_release", boom)
    status = features.macmaid_update_status()
    assert status["available"] is False and status["canApply"] is False
    assert status["checked"] is False
    assert "Could not check GitHub Releases" in status["reason"]


def _github_response(payload: str):
    class _Resp:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def read(self):
            return payload.encode()
    return _Resp()


def test_latest_github_release_parses_tag_and_url(monkeypatch):
    import urllib.request
    seen = []
    def fake_urlopen(request, timeout):
        seen.append((request.full_url, timeout))
        return _github_response('{"tag_name": "v1.2.3", "html_url": "https://example.invalid/v1.2.3"}')
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    release = features._latest_github_release("0.1.0")
    assert release == {"version": "1.2.3", "url": "https://example.invalid/v1.2.3"}
    assert seen == [("https://api.github.com/repos/DevOpen-io/MacMaid/releases/latest", 10)]


def test_latest_github_release_rejects_missing_tag(monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda request, timeout: _github_response('{"html_url": "https://example.invalid/x"}'))
    try:
        features._latest_github_release("0.1.0")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "tag_name" in str(exc)


def test_latest_github_release_rejects_non_object_json(monkeypatch):
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda request, timeout: _github_response('[1, 2, 3]'))
    try:
        features._latest_github_release("0.1.0")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "not a JSON object" in str(exc)


def test_unparseable_release_tag_marks_check_failed(monkeypatch):
    monkeypatch.setattr(features, "macmaid_install_channel", lambda: "source")
    monkeypatch.setattr(features, "_latest_github_release",
                        lambda version: {"version": "beta", "url": "https://example.invalid/x"})
    status = features.macmaid_update_status()
    assert status["checked"] is False and status["available"] is False
    assert "Could not parse the latest release tag" in status["reason"]


def test_update_plan_matches_channel(monkeypatch):
    from macmaid.review import macmaid_update_plan
    cask_plan = macmaid_update_plan({"channel": "homebrew-cask", "installedVersion": "1", "latestVersion": "2"})
    assert cask_plan.items[0].target == "brew upgrade --cask macmaid"
    assert "application bundle" in cask_plan.impact
    formula_plan = macmaid_update_plan({"channel": "homebrew-formula", "installedVersion": "1", "latestVersion": "2"})
    assert formula_plan.items[0].target == "brew upgrade macmaid"
    assert "command-line package" in formula_plan.impact


def test_cli_update_failed_check_exits_nonzero(monkeypatch, tmp_path):
    from macmaid import cli
    from macmaid.config import Config
    monkeypatch.setattr(cli, "Config", lambda: Config(home=tmp_path))
    monkeypatch.setattr(cli, "macmaid_update_status", lambda refresh=True: {
        "channel": "source", "installed": True, "available": False, "checked": False,
        "canApply": False, "installedVersion": "0.1.0", "latestVersion": None,
        "updateCommand": None, "updateUrl": "https://example.invalid", "reason": "Could not check GitHub Releases: boom"})
    try:
        cli.main(["update"])
        raise AssertionError("expected SystemExit")
    except SystemExit as exc:
        assert exc.code == 1


def test_cli_update_reports_channel_and_guidance(monkeypatch, tmp_path, capsys):
    from macmaid import cli
    from macmaid.config import Config
    monkeypatch.setattr(cli, "Config", lambda: Config(home=tmp_path))
    monkeypatch.setattr(cli, "macmaid_update_status", lambda refresh=True: {
        "channel": "uv-tool", "installed": True, "available": True, "canApply": False,
        "installedVersion": "0.15.0", "latestVersion": "0.15.30",
        "updateCommand": "sh install.sh", "updateUrl": "https://example.invalid/r", "reason": None})
    cli.main(["update"])
    out = capsys.readouterr().out
    assert "uv-tool" in out and "0.15.30" in out and "sh install.sh" in out


def test_cli_update_apply_only_works_for_homebrew(monkeypatch, tmp_path, capsys):
    from macmaid import cli
    from macmaid.config import Config
    monkeypatch.setattr(cli, "Config", lambda: Config(home=tmp_path))
    monkeypatch.setattr(cli, "macmaid_update_status", lambda refresh=True: {
        "channel": "app-bundle", "installed": True, "available": True, "canApply": False,
        "installedVersion": "0.15.0", "latestVersion": "0.15.30",
        "updateCommand": None, "updateUrl": "https://example.invalid/r", "reason": None})
    applied = []
    monkeypatch.setattr(cli, "apply_macmaid_brew_update", lambda: applied.append(True) or {"updated": True})
    cli.main(["update", "--apply"])
    out = capsys.readouterr().out
    assert applied == []  # non-Homebrew channels must never invoke brew
    assert "example.invalid" in out


def test_web_apply_rejects_non_homebrew_channel(monkeypatch):
    current = state()
    route = handler(current)
    status = {"installed": True, "available": True, "canApply": False, "channel": "uv-tool",
              "updateCommand": "sh install.sh", "updateUrl": "https://example.invalid/r", "reason": None}
    monkeypatch.setattr(web_mutations, "macmaid_update_status", Mock(return_value=status))
    result = route._route_post("/api/macmaid/update", {})
    assert result["success"] is False
    assert result["updateCommand"] == "sh install.sh"
    assert "reviewToken" not in result  # no review offered for a channel that cannot apply
