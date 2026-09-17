from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from .developer import DeveloperItem
from .i18n import translate
from .features import AppComponent, InstalledApplication, ProjectArtifact
from .models import ActionType, CleanupItem, RiskLevel
from .system import human_bytes


_ACTION_LABELS = {
    ActionType.REMOVE_PATH: "Permanent delete",
    ActionType.REMOVE_CHILDREN: "Permanent delete contents",
    ActionType.MOVE_TO_TRASH: "Move to Trash (recoverable)",
    ActionType.COMMAND: "Manager/system command",
    ActionType.COMMAND_WITH_CACHE_FALLBACK: "Manager command (no automatic raw fallback)",
    ActionType.MANUAL_CACHE_FALLBACK: "Manual cache fallback",
}


@dataclass(frozen=True, slots=True)
class ReviewItem:
    key: str
    label: str
    target: str
    action: str
    risk: str
    reason: str
    estimated_bytes: int = 0
    requires_app_closed: str = ""
    user_data: bool = False

    def web_dict(self) -> dict:
        return dict(asdict(self), estimatedBytes=self.estimated_bytes, humanEstimated=human_bytes(self.estimated_bytes))


@dataclass(frozen=True, slots=True)
class ReviewPlan:
    title: str
    items: tuple[ReviewItem, ...]
    impact: str
    estimate_note: str = "Estimated scan size is not guaranteed reclaimed disk space, especially on APFS."

    @property
    def estimated_bytes(self) -> int:
        return sum(item.estimated_bytes for item in self.items)

    @property
    def requires_extra_opt_in(self) -> bool:
        return any(item.user_data or item.risk == "MANUAL" for item in self.items)

    @property
    def fingerprint(self) -> str:
        payload = json.dumps(asdict(self), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode()).hexdigest()

    def web_dict(self) -> dict:
        return {
            "title": self.title,
            "impact": self.impact,
            "estimateNote": self.estimate_note,
            "estimatedBytes": self.estimated_bytes,
            "humanEstimated": human_bytes(self.estimated_bytes),
            "requiresExtraOptIn": self.requires_extra_opt_in,
            "fingerprint": self.fingerprint,
            "items": [item.web_dict() for item in self.items],
        }

    def text(self, language: str = "en") -> str:
        localize = lambda value: translate(value, language)
        lines = [localize(self.impact), localize("Items: {count} · scanned estimate: {size}").format(count=len(self.items), size=human_bytes(self.estimated_bytes))]
        for item in self.items:
            close = localize(" · close {app}").format(app=item.requires_app_closed) if item.requires_app_closed else ""
            data = localize(" · USER DATA OPT-IN") if item.user_data else ""
            lines.append(f"[{item.risk}] {localize(item.label)} · {localize(item.action)}{close}{data}\n  {localize(item.target)}\n  {localize(item.reason)}")
        lines.append(localize(self.estimate_note))
        lines.append(localize("Whitelist, path, ownership, symlink and running-state checks run again immediately before execution."))
        return "\n\n".join(lines)


def _risk(value: RiskLevel | str) -> str:
    if isinstance(value, RiskLevel):
        return "MANUAL" if value is RiskLevel.MANUAL_ONLY else value.name
    normalized = str(value).replace("_", "").lower()
    return {"safe": "SAFE", "moderate": "MODERATE", "aggressive": "AGGRESSIVE",
            "manual": "MANUAL", "manualonly": "MANUAL", "userdata": "AGGRESSIVE"}.get(normalized, str(value).upper())


def cleanup_plan(title: str, items: Iterable[CleanupItem]) -> ReviewPlan:
    reviewed = []
    for item in items:
        command = ""
        if item.action.executable:
            command = " ".join([item.action.executable, *item.action.arguments])
        reviewed.append(ReviewItem(
            item.id, item.label, str(item.path) if item.path else command or item.action.kind.value,
            _ACTION_LABELS[item.action.kind], _risk(item.risk), item.reason, item.estimated_bytes,
            item.requires_app_closed or "", item.risk is RiskLevel.MANUAL_ONLY,
        ))
    return ReviewPlan(title, tuple(reviewed), "Only the exact reviewed cleanup actions below will be requested.")


def application_plan(app: InstalledApplication, components: Sequence[AppComponent]) -> ReviewPlan:
    reviewed = []
    for component in components:
        is_bundle = component.path == app.path
        action = "Homebrew Cask uninstall" if is_bundle and app.brew_cask else "Move to Trash (recoverable)"
        reviewed.append(ReviewItem(
            str(component.path), component.label, str(component.path), action,
            "AGGRESSIVE" if is_bundle else _risk(component.risk), "Exact bundle-ID-derived component" if not is_bundle else "Reviewed application bundle",
            component.bytes, str(app.path), component.risk == "userData",
        ))
    return ReviewPlan(f"Uninstall {app.name}", tuple(reviewed), "The app must be closed. User-data components require explicit extra opt-in.")


def purge_plan(artifacts: Sequence[ProjectArtifact]) -> ReviewPlan:
    items = tuple(ReviewItem(str(item.path), f"{item.project_name} · {item.artifact_name}", str(item.path),
                             "Move to Trash (recoverable)", "MODERATE" if item.dependency else "SAFE",
                             "Dependency restore required" if item.dependency else "Rebuildable project output",
                             item.bytes) for item in artifacts)
    return ReviewPlan("Project Purge", items, "Project source is not selected; only proven generated artifacts move to Trash.")


def developer_plan(item: DeveloperItem) -> ReviewPlan:
    command = " ".join([item.executable or "", *item.arguments]).strip()
    reviewed = ReviewItem(item.id, f"{item.title} {item.version}".strip(), command or str(item.path),
                          "Owning manager command", "AGGRESSIVE", item.note or "Manager-owned removal",
                          item.bytes)
    return ReviewPlan("Remove developer resource", (reviewed,), "No raw directory deletion fallback will be used.")


def analyzer_trash_plan(paths: Sequence[Path], sizes: Mapping[Path, int] | None = None) -> ReviewPlan:
    sizes = sizes or {}
    items = tuple(ReviewItem(str(path), path.name, str(path), "Move to Trash (recoverable)", "AGGRESSIVE",
                             "User-selected disk analyzer item", sizes.get(path, 0), user_data=True) for path in paths)
    return ReviewPlan("Move analyzer selection to Trash", items, "These may be ordinary user files. Trash remains recoverable until emptied.")


def snapshot_plan(target_gb: int) -> ReviewPlan:
    if target_gb <= 0:
        raise ValueError("Snapshot thinning target must be positive")
    target_bytes = target_gb * 1024**3
    item = ReviewItem("time-machine-thin", "Thin local Time Machine snapshots", f"Reclaim target: {target_gb} GB",
                      "tmutil thinlocalsnapshots", "AGGRESSIVE", "Time Machine chooses reclaimable local snapshots", target_bytes)
    return ReviewPlan(
        "Thin Time Machine snapshots", (item,),
        "Apple normally manages local snapshots automatically. Use this only for an immediate space need; local recovery snapshots may be removed, while backup-disk history is not selected.",
        "Requested reclaim target is not an estimate or guarantee. Time Machine decides what is reclaimable; measured free-space change is recorded after the command.",
    )


def macmaid_update_plan(status: Mapping[str, object]) -> ReviewPlan:
    installed = str(status.get("installedVersion") or "installed version")
    latest = str(status.get("latestVersion") or "latest available version")
    item = ReviewItem("macmaid-brew-update", "Update MacMaid with Homebrew", "brew upgrade --cask macmaid",
                      "Homebrew Cask upgrade", "MODERATE", f"Upgrade {installed} to {latest}")
    return ReviewPlan("Update MacMaid", (item,), "Homebrew will replace the MacMaid application bundle. Restart MacMaid after the update completes.")


def optimization_plan(tasks: Sequence[dict]) -> ReviewPlan:
    items = tuple(ReviewItem(str(task["id"]), str(task["title"]), str(task["id"]), "macOS maintenance command",
                             str(task["risk"]), "May refresh a visible macOS service", 0) for task in tasks)
    return ReviewPlan("Run macOS maintenance", items, "Selected services may briefly restart or rebuild state.")


def issue_review_token(secret: str, scope: str, generation: int, plan: ReviewPlan, *, now: float | None = None) -> str:
    timestamp = int(now if now is not None else time.time())
    payload = f"{timestamp}:{generation}:{plan.fingerprint}:{secrets.token_hex(8)}"
    signature = hmac.new(secret.encode(), f"{scope}:{payload}".encode(), hashlib.sha256).hexdigest()
    return f"{payload}:{signature}"


def validate_review_token(secret: str, scope: str, generation: int, plan: ReviewPlan, token: str,
                          *, now: float | None = None, max_age: int = 300) -> bool:
    try:
        timestamp_text, generation_text, fingerprint, nonce, signature = token.split(":", 4)
        timestamp = int(timestamp_text)
        token_generation = int(generation_text)
    except (TypeError, ValueError):
        return False
    current = int(now if now is not None else time.time())
    if timestamp > current + 5 or current - timestamp > max_age or token_generation != generation or fingerprint != plan.fingerprint:
        return False
    expected = hmac.new(secret.encode(), f"{scope}:{timestamp}:{generation}:{fingerprint}:{nonce}".encode(), hashlib.sha256).hexdigest()
    return hmac.compare_digest(signature, expected)
