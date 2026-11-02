use serde::{Deserialize, Serialize};
use std::collections::{HashMap, HashSet};
use std::sync::Mutex;
use std::time::{Duration, Instant};
use sysinfo::{Pid, ProcessesToUpdate, System};

pub const GROWTH_WINDOW_SECONDS: u64 = 120;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProcessInfo {
    pub pid: u32,
    pub ppid: u32,
    pub name: String,
    pub executable: String,
    pub rss_bytes: u64,
    pub cpu_percent: f32,
    pub category: String,
    pub is_protected: bool,
    pub growth_bytes_per_sec: f64,
}

pub struct MemoryService {
    system: Mutex<System>,
    history: Mutex<HashMap<u32, Vec<(Instant, u64)>>>,
    protected_names: HashSet<&'static str>,
}

impl Default for MemoryService {
    fn default() -> Self {
        let mut sys = System::new_all();
        sys.refresh_all();

        let protected_names = [
            "launchd",
            "kernel_task",
            "WindowServer",
            "loginwindow",
            "Finder",
            "Dock",
            "SystemUIServer",
            "Terminal",
            "iTerm2",
            "MacMaid",
            "macmaid",
            "syslogd",
            "opendirectoryd",
            "diskarbitrationd",
        ]
        .into_iter()
        .collect();

        Self {
            system: Mutex::new(sys),
            history: Mutex::new(HashMap::new()),
            protected_names,
        }
    }
}

impl MemoryService {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn snapshot(&self) -> Vec<ProcessInfo> {
        let mut sys = self.system.lock().unwrap();
        sys.refresh_processes(ProcessesToUpdate::All, true);

        let now = Instant::now();
        let mut history = self.history.lock().unwrap();

        // Prune old history entries
        history.retain(|_, samples| {
            samples.retain(|(t, _)| now.duration_since(*t).as_secs() <= GROWTH_WINDOW_SECONDS);
            !samples.is_empty()
        });

        let mut results = Vec::new();

        for (pid, proc_) in sys.processes() {
            let raw_pid = pid.as_u32();
            if raw_pid == 0 {
                continue;
            }

            let name = proc_.name().to_string_lossy().to_string();
            let exe = proc_
                .exe()
                .map(|p| p.to_string_lossy().to_string())
                .unwrap_or_default();
            let rss = proc_.memory();
            let cpu = proc_.cpu_usage();
            let ppid = proc_.parent().map(|p| p.as_u32()).unwrap_or(0);

            // Record memory sample for growth tracking
            let samples = history.entry(raw_pid).or_default();
            samples.push((now, rss));

            // Calculate growth slope (bytes/sec)
            let growth_rate = if samples.len() >= 3 {
                let first = samples.first().unwrap();
                let last = samples.last().unwrap();
                let dur = last.0.duration_since(first.0).as_secs_f64();
                if dur > 1.0 {
                    (last.1 as f64 - first.1 as f64) / dur
                } else {
                    0.0
                }
            } else {
                0.0
            };

            let is_protected = raw_pid == 1
                || self.protected_names.contains(name.as_str())
                || exe.contains("/System/Library/")
                || exe.contains("/usr/libexec/");

            let category = if is_protected {
                "protected"
            } else if exe.contains(".app/Contents/") {
                "applications"
            } else if exe.contains("/node")
                || exe.contains("/cargo")
                || exe.contains("/rust")
                || exe.contains("/python")
                || exe.contains("/git")
            {
                "developer"
            } else if exe.contains("flutter") || exe.contains("dart") {
                "flutter"
            } else if rss > 500 * 1024 * 1024 {
                "high"
            } else {
                "system"
            };

            results.push(ProcessInfo {
                pid: raw_pid,
                ppid,
                name,
                executable: exe,
                rss_bytes: rss,
                cpu_percent: cpu,
                category: category.into(),
                is_protected,
                growth_bytes_per_sec: growth_rate,
            });
        }

        results.sort_by_key(|a| std::cmp::Reverse(a.rss_bytes));
        results
    }

    pub fn terminate_process(&self, pid: u32) -> Result<(), String> {
        if pid <= 1 {
            return Err("Cannot terminate system root PID 1".into());
        }

        {
            let sys = self.system.lock().unwrap();
            if let Some(proc_) = sys.process(Pid::from_u32(pid)) {
                let name = proc_.name().to_string_lossy();
                if self.protected_names.contains(name.as_ref()) {
                    return Err(format!(
                        "Process '{name}' is protected and cannot be terminated"
                    ));
                }
            } else {
                return Err(format!("Process with PID {pid} not found"));
            }
        }

        // Send SIGTERM
        unsafe {
            if libc::kill(pid as i32, libc::SIGTERM) != 0 {
                return Err(format!("Failed to send SIGTERM to PID {pid}"));
            }
        }

        // Wait up to 1.5s for process to exit
        for _ in 0..15 {
            std::thread::sleep(Duration::from_millis(100));
            let still_alive = unsafe { libc::kill(pid as i32, 0) == 0 };
            if !still_alive {
                return Ok(());
            }
        }

        // Send SIGKILL
        unsafe {
            let _ = libc::kill(pid as i32, libc::SIGKILL);
        }

        std::thread::sleep(Duration::from_millis(200));
        let still_alive = unsafe { libc::kill(pid as i32, 0) == 0 };
        if still_alive {
            Err(format!("PID {pid} resisted termination"))
        } else {
            Ok(())
        }
    }
}
