use chrono::Utc;
use serde::{Deserialize, Serialize};
use std::io::Write;
use std::path::Path;
use std::time::Duration;

use crate::cleaner::Cleaner;
use crate::reporting::FreeSpaceProbe;
use crate::system::run_command;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SnapshotInfo {
    pub name: String,
    pub date: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct SnapshotThinResult {
    pub success: bool,
    pub output: String,
    pub error: String,
    pub requested_reclaim_bytes: u64,
    pub observed_free_bytes_delta: Option<i64>,
}

pub struct SnapshotManager;

impl SnapshotManager {
    pub fn list_snapshots() -> Vec<SnapshotInfo> {
        let res = run_command(
            "/usr/bin/tmutil",
            &["listlocalsnapshots", "/"],
            Duration::from_secs(30),
            None,
        );
        if !res.succeeded() {
            return Vec::new();
        }

        res.stdout
            .lines()
            .filter(|line| {
                line.starts_with("com.apple.TimeMachine.") || line.starts_with("com.apple.")
            })
            .map(|line| {
                let name = line.trim().to_string();
                let date = if let Some(stripped) = name.strip_prefix("com.apple.TimeMachine.") {
                    stripped
                        .strip_suffix(".local")
                        .unwrap_or(stripped)
                        .to_string()
                } else {
                    name.clone()
                };
                SnapshotInfo { name, date }
            })
            .collect()
    }

    pub fn thin_snapshots(
        bytes_to_free: u64,
        cleaner: &Cleaner,
    ) -> Result<SnapshotThinResult, String> {
        let euid = unsafe { libc::geteuid() };
        if euid == 0 {
            return Err("MacMaid must run as your normal user, never with sudo/root".into());
        }

        let free_space = FreeSpaceProbe::capture([Some(Path::new("/"))]);
        let requested_str = bytes_to_free.to_string();
        let command_args = ["thinlocalsnapshots", "/", &requested_str, "4"];
        let res = run_command(
            "/usr/bin/tmutil",
            &command_args,
            Duration::from_secs(600),
            None,
        );
        let (observed, notes) = free_space.finish();

        let audit = serde_json::json!({
            "timestamp": Utc::now().to_rfc3339(),
            "recordType": "snapshot_thin",
            "action": "tmutil thinlocalsnapshots",
            "command": ["/usr/bin/tmutil", "thinlocalsnapshots", "/", &requested_str, "4"],
            "requestedReclaimBytes": bytes_to_free,
            "estimatedReclaimedBytes": 0,
            "observedFreeBytesDelta": observed,
            "unknownReclaimCount": if res.succeeded() { 1 } else { 0 },
            "result": if res.succeeded() { "success" } else { "failed" },
            "output": res.stdout,
            "error": res.stderr,
            "measurementNotes": notes,
        });

        if let Ok(mut f) = std::fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&cleaner.logger.log_file)
        {
            let _ = writeln!(f, "{audit}");
        }

        Ok(SnapshotThinResult {
            success: res.succeeded(),
            output: res.stdout,
            error: res.stderr,
            requested_reclaim_bytes: bytes_to_free,
            observed_free_bytes_delta: observed,
        })
    }
}
