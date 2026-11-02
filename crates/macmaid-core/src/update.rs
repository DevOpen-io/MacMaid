use serde::{Deserialize, Serialize};
use std::time::Duration;

use crate::system::run_command;
use crate::VERSION;

pub const MACMAID_RELEASES_URL: &str = "https://github.com/DevOpen-io/MacMaid/releases";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct UpdateStatus {
    pub channel: String,
    pub installed: bool,
    pub can_apply: bool,
    pub available: bool,
    pub checked: bool,
    pub installed_version: String,
    pub latest_version: Option<String>,
    pub update_command: Option<String>,
    pub update_url: String,
    pub reason: Option<String>,
}

pub fn detect_install_channel() -> String {
    // 1. Check Homebrew Cask or Formula
    let brew_res = run_command("/usr/bin/which", &["brew"], Duration::from_secs(5), None);
    if brew_res.succeeded() {
        let brew_path = brew_res.stdout.trim();
        if run_command(
            brew_path,
            &["list", "--cask", "macmaid"],
            Duration::from_secs(10),
            None,
        )
        .succeeded()
        {
            return "homebrew-cask".to_string();
        }
        if run_command(
            brew_path,
            &["list", "macmaid"],
            Duration::from_secs(10),
            None,
        )
        .succeeded()
        {
            return "homebrew-formula".to_string();
        }
    }

    // 2. Check App bundle in /Applications or ~/Applications
    if std::path::Path::new("/Applications/MacMaid.app").exists() {
        return "app-bundle".to_string();
    }
    if let Some(home) = crate::safety::dirs_home() {
        if home.join("Applications/MacMaid.app").exists() {
            return "app-bundle".to_string();
        }
        if home.join(".local/bin/macmaid").exists() {
            return "local-binary".to_string();
        }
    }

    "standalone-binary".to_string()
}

pub fn check_update_status() -> UpdateStatus {
    let channel = detect_install_channel();
    let current_version = VERSION.to_string();

    if channel.starts_with("homebrew") {
        let is_cask = channel == "homebrew-cask";
        let brew_res = run_command("/usr/bin/which", &["brew"], Duration::from_secs(5), None);
        let brew_path = if brew_res.succeeded() {
            brew_res.stdout.trim()
        } else {
            "/opt/homebrew/bin/brew"
        };
        let outdated_args = if is_cask {
            vec!["outdated", "--cask", "--json=v2"]
        } else {
            vec!["outdated", "--formula", "--json=v2"]
        };
        let res = run_command(brew_path, &outdated_args, Duration::from_secs(30), None);

        let mut available = false;
        let mut latest_version = None;

        if res.succeeded() {
            if let Ok(val) = serde_json::from_str::<serde_json::Value>(&res.stdout) {
                let target_key = if is_cask { "casks" } else { "formulae" };
                if let Some(list) = val.get(target_key).and_then(|v| v.as_array()) {
                    for item in list {
                        if item.get("name").and_then(|n| n.as_str()) == Some("macmaid") {
                            available = true;
                            latest_version = item
                                .get("current_version")
                                .and_then(|v| v.as_str())
                                .map(ToString::to_string);
                        }
                    }
                }
            }
        }

        let update_cmd = if is_cask {
            "brew upgrade --cask macmaid"
        } else {
            "brew upgrade macmaid"
        };

        return UpdateStatus {
            channel,
            installed: true,
            can_apply: true,
            available,
            checked: res.succeeded(),
            installed_version: current_version.clone(),
            latest_version: latest_version.or(Some(current_version)),
            update_command: Some(update_cmd.to_string()),
            update_url: MACMAID_RELEASES_URL.to_string(),
            reason: if res.succeeded() {
                None
            } else {
                Some(res.stderr)
            },
        };
    }

    // Non-homebrew channels: check via GitHub API
    let curl_res = run_command(
        "/usr/bin/curl",
        &[
            "-s",
            "-m",
            "10",
            "https://api.github.com/repos/DevOpen-io/MacMaid/releases/latest",
        ],
        Duration::from_secs(12),
        None,
    );

    if curl_res.succeeded() {
        if let Ok(val) = serde_json::from_str::<serde_json::Value>(&curl_res.stdout) {
            if let Some(tag) = val.get("tag_name").and_then(|t| t.as_str()) {
                let latest_ver = tag.trim_start_matches('v').to_string();
                let available = is_newer_version(&latest_ver, &current_version);
                return UpdateStatus {
                    channel: channel.clone(),
                    installed: true,
                    can_apply: false,
                    available,
                    checked: true,
                    installed_version: current_version,
                    latest_version: Some(latest_ver),
                    update_command: None,
                    update_url: val
                        .get("html_url")
                        .and_then(|u| u.as_str())
                        .unwrap_or(MACMAID_RELEASES_URL)
                        .to_string(),
                    reason: None,
                };
            }
        }
    }

    UpdateStatus {
        channel,
        installed: true,
        can_apply: false,
        available: false,
        checked: false,
        installed_version: current_version,
        latest_version: None,
        update_command: None,
        update_url: MACMAID_RELEASES_URL.to_string(),
        reason: Some("Could not check for updates (offline or rate-limited)".into()),
    }
}

fn is_newer_version(latest: &str, current: &str) -> bool {
    let parse = |v: &str| -> Vec<u32> {
        v.split('.')
            .filter_map(|p| {
                p.chars()
                    .take_while(|c| c.is_ascii_digit())
                    .collect::<String>()
                    .parse()
                    .ok()
            })
            .collect()
    };
    let l_parts = parse(latest);
    let c_parts = parse(current);
    l_parts > c_parts
}
