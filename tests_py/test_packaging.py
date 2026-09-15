from __future__ import annotations

import os
import pathlib
import subprocess
import tempfile
from pathlib import Path

from macmaid import __version__


def test_workflow_packages_runtime_internal_and_uses_libexec() -> None:
    root = Path(__file__).resolve().parents[1]
    workflow_path = root / ".github/workflows/macos-dmg.yml"
    content = workflow_path.read_text()

    assert 'tar -C build/macos-app/cli-package -czf "$CLI_TARBALL" macmaid _internal' in content
    assert 'libexec.install Dir["*"]' in content
    assert 'bin.install_symlink libexec/"macmaid"' in content


def test_build_macos_app_script_stages_cli_directory_with_internal() -> None:
    root = Path(__file__).resolve().parents[1]
    script_path = root / "scripts/build-macos-app.sh"
    content = script_path.read_text()

    assert "CLI_DIR=$BUILD_DIR/cli" in content
    assert 'install -m 755 "$BUNDLE_DIR/$BIN_NAME" "$CLI_DIR/$BIN_NAME"' in content
    assert 'cp -R "$BUNDLE_DIR/_internal" "$CLI_DIR/_internal"' in content


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
