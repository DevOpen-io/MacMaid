from __future__ import annotations

import subprocess
from pathlib import Path

from macmaid import __version__


def test_workflow_packages_runtime_internal_and_uses_libexec() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow_path = root / ".github/workflows/macos-dmg.yml"
    content = workflow_path.read_text()

    assert 'tar -C build/macos-app/cli-package -czf "$CLI_TARBALL" macmaid _internal' in content
    assert 'libexec.install Dir["*"]' in content
    assert 'bin.install_symlink libexec/"macmaid"' in content


def test_homebrew_update_retries_release_asset_downloads() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/macos-dmg.yml").read_text()

    retry_flags = "--retry 5 --retry-delay 2 --retry-all-errors"
    assert f'curl {retry_flags} -fsSL "$BASE_URL/$ARM_DMG"' in workflow
    assert f'curl {retry_flags} -fsSL "$BASE_URL/$ARM_CLI"' in workflow


def test_build_macos_app_script_stages_cli_directory_with_internal() -> None:
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts/build-macos-app.sh"
    content = script_path.read_text()

    assert "CLI_DIR=$BUILD_DIR/cli" in content
    assert 'install -m 755 "$BUNDLE_DIR/$BIN_NAME" "$CLI_DIR/$BIN_NAME"' in content
    assert 'cp -R "$BUNDLE_DIR/_internal" "$CLI_DIR/_internal"' in content


def test_native_launchers_explicitly_target_supported_macos() -> None:
    root = Path(__file__).resolve().parents[1]
    for relative_path in ("scripts/build-macos-app.sh", "scripts/prod-install.sh"):
        content = (root / relative_path).read_text()
        assert "MACOS_DEPLOYMENT_TARGET=${MACOS_DEPLOYMENT_TARGET:-13.0}" in content
        assert '-target "$(uname -m)-apple-macosx$MACOS_DEPLOYMENT_TARGET"' in content


def test_homebrew_libexec_symlink_structure_resolution(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    dist_dir = root / "build/prod/dist/macmaid"

    # If local build artifacts are present, test the real binary execution
    if (dist_dir / "macmaid").is_file() and (dist_dir / "_internal").is_dir():
        libexec = tmp_path / "libexec"
        bin_dir = tmp_path / "bin"
        libexec.mkdir()
        bin_dir.mkdir()

        import shutil
        shutil.copy(dist_dir / "macmaid", libexec / "macmaid")
        shutil.copytree(dist_dir / "_internal", libexec / "_internal")

        symlink = bin_dir / "macmaid"
        symlink.symlink_to(libexec / "macmaid")

        result = subprocess.run([str(symlink), "--version"], capture_output=True, text=True)
        assert result.returncode == 0
        assert result.stdout.strip().startswith("macmaid ")
    else:
        # Test symlink path resolution invariant
        libexec = tmp_path / "libexec"
        bin_dir = tmp_path / "bin"
        libexec.mkdir()
        bin_dir.mkdir()

        mock_bin = libexec / "macmaid"
        mock_bin.write_text("#!/bin/sh\nprintf '%s\\n' \"$0\"\n")
        mock_bin.chmod(0o755)
        (libexec / "_internal").mkdir()

        symlink = bin_dir / "macmaid"
        symlink.symlink_to(libexec / "macmaid")

        resolved = symlink.resolve()
        assert resolved == mock_bin
        assert (resolved.parent / "_internal").is_dir()


def test_ci_requires_python_lint_and_type_checks() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow = (root / ".github/workflows/ci.yml").read_text()
    project = (root / "pyproject.toml").read_text()

    assert "uv run ruff check src/macmaid" in workflow
    assert "uv run mypy" in workflow
    assert '"ruff>=0.11,<1"' in project
    assert '"mypy>=1.15,<2"' in project


def test_memory_release_version_surfaces_are_synchronized() -> None:
    import re
    import tomllib
    root = Path(__file__).resolve().parents[1]
    project = tomllib.loads((root / "pyproject.toml").read_text())["project"]
    lock = tomllib.loads((root / "uv.lock").read_text())
    package = next(item for item in lock["package"] if item["name"] == "macmaid")
    html = (root / "src/macmaid/WebUI/index.html").read_text()
    displayed = re.search(r'class="settings-info-value settings-info-mono">([0-9.]+)<', html).group(1)
    assert project["version"] == package["version"] == displayed == __version__
    assert tuple(map(int, __version__.split("."))) >= (0, 12, 0)
    assert 'from macmaid import __version__' in (root / "scripts/prod-install.sh").read_text()
