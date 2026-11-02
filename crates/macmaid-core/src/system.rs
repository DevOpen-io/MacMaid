use serde::{Deserialize, Serialize};
use std::ffi::CString;
use std::os::unix::process::CommandExt;
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::mpsc;
use std::time::Duration;

use crate::cancellation::CancellationToken;
use crate::safety::dirs_home;

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CommandResult {
    pub status: i32,
    pub stdout: String,
    pub stderr: String,
}

impl CommandResult {
    pub fn succeeded(&self) -> bool {
        self.status == 0
    }
}

pub fn run_command(
    executable: &str,
    args: &[&str],
    timeout_duration: Duration,
    cancellation: Option<&CancellationToken>,
) -> CommandResult {
    let mut cmd = Command::new(executable);
    cmd.args(args);
    cmd.stdout(Stdio::piped());
    cmd.stderr(Stdio::piped());

    // Create a new process group so timeouts/cancellations can terminate children cleanly
    unsafe {
        cmd.pre_exec(|| {
            libc::setpgid(0, 0);
            Ok(())
        });
    }

    let child = match cmd.spawn() {
        Ok(c) => c,
        Err(e) => {
            return CommandResult {
                status: 127,
                stdout: String::new(),
                stderr: e.to_string(),
            };
        }
    };

    let pid = child.id() as i32;
    let (tx, rx) = mpsc::channel();

    let wait_thread = std::thread::spawn(move || {
        let output = child.wait_with_output();
        let _ = tx.send(output);
    });

    let start = std::time::Instant::now();
    loop {
        if let Ok(res) = rx.recv_timeout(Duration::from_millis(50)) {
            let _ = wait_thread.join();
            return match res {
                Ok(output) => CommandResult {
                    status: output.status.code().unwrap_or(1),
                    stdout: String::from_utf8_lossy(&output.stdout).trim().to_string(),
                    stderr: String::from_utf8_lossy(&output.stderr).trim().to_string(),
                },
                Err(e) => CommandResult {
                    status: 1,
                    stdout: String::new(),
                    stderr: e.to_string(),
                },
            };
        }

        if let Some(token) = cancellation {
            if token.is_cancelled() {
                unsafe {
                    libc::killpg(pid, libc::SIGKILL);
                }
                let _ = wait_thread.join();
                return CommandResult {
                    status: 130,
                    stdout: String::new(),
                    stderr: "command cancelled".into(),
                };
            }
        }

        if start.elapsed() >= timeout_duration {
            unsafe {
                libc::killpg(pid, libc::SIGKILL);
            }
            let _ = wait_thread.join();
            return CommandResult {
                status: 124,
                stdout: String::new(),
                stderr: "command timed out".into(),
            };
        }
    }
}

pub fn which(name: &str) -> Option<PathBuf> {
    if let Ok(path_var) = std::env::var("PATH") {
        for dir in std::env::split_paths(&path_var) {
            let candidate = dir.join(name);
            if candidate.is_file() && is_executable(&candidate) {
                return Some(candidate);
            }
        }
    }

    // Check standard macOS paths
    let well_known = [
        "/opt/homebrew/bin",
        "/opt/homebrew/sbin",
        "/usr/local/bin",
        "/usr/local/sbin",
        "/usr/bin",
        "/bin",
        "/usr/sbin",
        "/sbin",
    ];
    for dir in &well_known {
        let candidate = Path::new(dir).join(name);
        if candidate.is_file() && is_executable(&candidate) {
            return Some(candidate);
        }
    }

    if let Some(home) = dirs_home() {
        let user_dirs = [
            home.join(".cargo/bin"),
            home.join(".local/bin"),
            home.join(".bun/bin"),
        ];
        for dir in &user_dirs {
            let candidate = dir.join(name);
            if candidate.is_file() && is_executable(&candidate) {
                return Some(candidate);
            }
        }
    }

    None
}

fn is_executable(path: &Path) -> bool {
    use std::os::unix::fs::PermissionsExt;
    if let Ok(meta) = path.metadata() {
        meta.is_file() && (meta.permissions().mode() & 0o111 != 0)
    } else {
        false
    }
}

pub fn process_running(needle: &str) -> bool {
    let pgrep = which("pgrep").unwrap_or_else(|| PathBuf::from("/usr/bin/pgrep"));
    let pgrep_str = pgrep.to_string_lossy();
    let res = run_command(
        &pgrep_str,
        &["-f", "--", needle],
        Duration::from_secs(5),
        None,
    );
    res.status == 0
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DiskStats {
    pub total_bytes: u64,
    pub free_bytes: u64,
    pub available_bytes: u64,
}

pub fn statvfs_disk_info(path: &Path) -> Option<DiskStats> {
    let c_path = CString::new(path.as_os_str().to_string_lossy().as_bytes()).ok()?;
    let mut stat: libc::statvfs = unsafe { std::mem::zeroed() };
    let res = unsafe { libc::statvfs(c_path.as_ptr(), &mut stat) };
    if res == 0 {
        let fragment_size = stat.f_frsize as u64;
        let total_bytes = stat.f_blocks as u64 * fragment_size;
        let free_bytes = stat.f_bfree as u64 * fragment_size;
        let available_bytes = stat.f_bavail as u64 * fragment_size;
        Some(DiskStats {
            total_bytes,
            free_bytes,
            available_bytes,
        })
    } else {
        None
    }
}

pub fn human_bytes(value: u64) -> String {
    let mut amount = value as f64;
    let units = ["B", "KB", "MB", "GB", "TB"];
    for (i, unit) in units.iter().enumerate() {
        if amount < 1024.0 || i == units.len() - 1 {
            return if *unit == "B" {
                format!("{amount:.0} {unit}")
            } else {
                format!("{amount:.1} {unit}")
            };
        }
        amount /= 1024.0;
    }
    format!("{amount:.1} TB")
}

pub fn size_of(path: &Path, cancellation: Option<&CancellationToken>) -> u64 {
    if let Some(token) = cancellation {
        if token.is_cancelled() {
            return 0;
        }
    }

    if !path.exists() && std::fs::symlink_metadata(path).is_err() {
        return 0;
    }

    // Match exact macOS du -sk measurement for accurate APFS accounting
    let path_str = path.to_string_lossy();
    let res = run_command(
        "/usr/bin/du",
        &["-sk", &path_str],
        Duration::from_secs(120),
        cancellation,
    );
    if res.succeeded() {
        if let Some(first_word) = res.stdout.split_whitespace().next() {
            if let Ok(kb) = first_word.parse::<u64>() {
                return kb * 1024;
            }
        }
    }

    // Fallback recursive stat
    let mut total: u64 = 0;
    for entry in walkdir::WalkDir::new(path)
        .into_iter()
        .filter_map(|e| e.ok())
    {
        if let Some(token) = cancellation {
            if token.is_cancelled() {
                break;
            }
        }
        if let Ok(meta) = entry.metadata() {
            if meta.is_file() {
                total += meta.len();
            }
        }
    }
    total
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PermissionGroup {
    pub id: String,
    pub status: String,
    pub accessible: usize,
    pub total: usize,
    pub entries: Vec<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct PermissionReport {
    pub launch_context: String,
    pub full_disk_access: String,
    pub checks: Vec<PermissionGroup>,
    pub note: String,
}

pub fn macos_permission_report() -> PermissionReport {
    let home = dirs_home().unwrap_or_else(|| PathBuf::from("/Users/unknown"));
    let mut groups = Vec::new();

    // Check user directories
    let user_dirs = vec![
        home.join("Desktop"),
        home.join("Documents"),
        home.join("Downloads"),
    ];
    let mut accessible = 0;
    let mut entries = Vec::new();
    for dir in &user_dirs {
        if dir.exists() {
            match std::fs::read_dir(dir) {
                Ok(_) => {
                    accessible += 1;
                    entries.push(format!(
                        "{}: granted",
                        dir.file_name().unwrap_or_default().to_string_lossy()
                    ));
                }
                Err(_) => {
                    entries.push(format!(
                        "{}: denied",
                        dir.file_name().unwrap_or_default().to_string_lossy()
                    ));
                }
            }
        }
    }
    groups.push(PermissionGroup {
        id: "userFolders".into(),
        status: if accessible == user_dirs.len() {
            "granted".into()
        } else {
            "limited".into()
        },
        accessible,
        total: user_dirs.len(),
        entries,
    });

    // Probe protected system/TCC directories
    let protected_dirs = vec![
        home.join("Library/Containers"),
        home.join("Library/Safari"),
        home.join("Library/Mail"),
        PathBuf::from("/Library/Application Support/com.apple.TCC"),
    ];
    let mut prot_accessible = 0;
    let mut prot_entries = Vec::new();
    for dir in &protected_dirs {
        if dir.exists() {
            match std::fs::read_dir(dir) {
                Ok(_) => {
                    prot_accessible += 1;
                    prot_entries.push(format!("{}: granted", dir.display()));
                }
                Err(_) => {
                    prot_entries.push(format!("{}: denied", dir.display()));
                }
            }
        }
    }

    let fda_status = if prot_accessible >= 2 {
        "granted".to_string()
    } else {
        "not_granted".to_string()
    };

    groups.push(PermissionGroup {
        id: "protectedData".into(),
        status: fda_status.clone(),
        accessible: prot_accessible,
        total: protected_dirs.len(),
        entries: prot_entries,
    });

    PermissionReport {
        launch_context: if std::env::current_exe()
            .map(|p| p.to_string_lossy().contains(".app/Contents/"))
            .unwrap_or(false)
        {
            "app".into()
        } else {
            "cli".into()
        },
        full_disk_access: fda_status,
        checks: groups,
        note:
            "Capability probe only; macOS does not expose a definitive Full Disk Access query API."
                .into(),
    }
}
