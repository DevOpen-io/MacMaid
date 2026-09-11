from __future__ import annotations

from pathlib import Path

from deepclean import developer
from deepclean.config import Config
from deepclean.developer import DeveloperStorageCenter


def test_developer_storage_center_groups_known_ecosystems(tmp_path, monkeypatch):
    home = tmp_path / "home"
    derived = home / "Library/Developer/Xcode/DerivedData/App"
    npm = home / ".npm"
    node_modules = home / "Projects/app/node_modules"
    cargo = home / ".cargo/registry"
    target = home / "Projects/rustapp/target"
    android = home / "Library/Android/sdk/platforms/android-35"
    for path in (derived, npm, node_modules, cargo, target, android):
        path.mkdir(parents=True)
        (path / "payload").write_bytes(b"x")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(developer, "which", lambda name: None)

    sections = DeveloperStorageCenter(Config(home=home)).scan()
    by_id = {section.id: section for section in sections}

    assert {"xcode", "node", "rust", "android"}.issubset(by_id)
    assert by_id["xcode"].bytes > 0
    assert any(item["label"] == "npm cache" for item in by_id["node"].items)
    assert any(item["label"] == "node_modules" for item in by_id["node"].items)
    assert any(item["label"] == "target directory" for item in by_id["rust"].items)
    assert all(item["removable"] is False for section in sections for item in section.items)


def test_developer_storage_center_reports_docker_inventory_without_deletion(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(developer, "which", lambda name: "/usr/bin/docker" if name == "docker" else None)
    monkeypatch.setattr(developer, "run_command", lambda *_args, **_kwargs: type("R", (), {"stdout": '{"Type":"Images","Size":"1GB"}\n'})())

    sections = DeveloperStorageCenter(Config(home=home)).scan()
    docker = next(section for section in sections if section.id == "docker")

    assert docker.items
    assert docker.items[0]["removable"] is False
    assert "volumes are never auto-deleted" in docker.note
