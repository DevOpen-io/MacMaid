use glob::Pattern;
use serde::{Deserialize, Serialize};
use std::fs;
use std::io::{self, Write};
use std::os::unix::fs::MetadataExt;
use std::path::{Path, PathBuf};

use crate::safety::{dirs_home, PathSafety, PathSafetyError};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AppSettings {
    #[serde(default = "default_language")]
    pub language: String,
}

fn default_language() -> String {
    "en".to_string()
}

impl Default for AppSettings {
    fn default() -> Self {
        Self {
            language: default_language(),
        }
    }
}

#[derive(Debug, Clone)]
pub struct Config {
    pub config_dir: PathBuf,
    pub whitelist_path: PathBuf,
    pub settings_path: PathBuf,
}

impl Default for Config {
    fn default() -> Self {
        let home = dirs_home().unwrap_or_else(|| PathBuf::from("/Users/unknown"));
        let config_dir = home.join(".config/macmaid");
        let whitelist_path = config_dir.join("whitelist");
        let settings_path = config_dir.join("settings.json");
        Self {
            config_dir,
            whitelist_path,
            settings_path,
        }
    }
}

impl Config {
    pub fn ensure_config_dir(&self) -> io::Result<()> {
        if !self.config_dir.exists() {
            fs::create_dir_all(&self.config_dir)?;
        }
        Ok(())
    }

    pub fn load_settings(&self) -> AppSettings {
        if let Ok(content) = fs::read_to_string(&self.settings_path) {
            if let Ok(settings) = serde_json::from_str::<AppSettings>(&content) {
                return settings;
            }
        }
        AppSettings::default()
    }

    pub fn save_settings(&self, settings: &AppSettings) -> io::Result<()> {
        self.ensure_config_dir()?;
        let json = serde_json::to_string_pretty(settings)
            .map_err(|e| io::Error::new(io::ErrorKind::InvalidData, e))?;
        atomic_write(&self.settings_path, json.as_bytes())
    }

    pub fn patterns(&self, strict: bool) -> Result<Vec<String>, PathSafetyError> {
        if !self.whitelist_path.exists() {
            return Ok(Vec::new());
        }

        // Validate whitelist file itself
        let meta = fs::symlink_metadata(&self.whitelist_path)
            .map_err(|_| PathSafetyError::TargetUnavailable(self.whitelist_path.clone()))?;

        if meta.file_type().is_symlink() {
            return Err(PathSafetyError::SymlinkedAncestor(
                self.whitelist_path.clone(),
            ));
        }

        let uid = unsafe { libc::getuid() };
        if meta.uid() != uid {
            return Err(PathSafetyError::NotOwnedByCurrentUser(
                self.whitelist_path.clone(),
            ));
        }

        PathSafety::reject_symlink_ancestors(&self.whitelist_path)?;

        let content = fs::read_to_string(&self.whitelist_path)
            .map_err(|_| PathSafetyError::TargetUnavailable(self.whitelist_path.clone()))?;

        let mut rules = Vec::new();
        for line in content.lines() {
            let trimmed = line.trim();
            if trimmed.is_empty() || trimmed.starts_with('#') {
                continue;
            }
            if strict {
                // Validate pattern
                if trimmed.contains('\0') {
                    return Err(PathSafetyError::EmptyOrSuspicious(
                        "null byte in whitelist pattern".into(),
                    ));
                }
            }
            rules.push(trimmed.to_string());
        }

        Ok(rules)
    }

    pub fn is_protected(&self, path: &Path) -> Result<bool, PathSafetyError> {
        let rules = self.patterns(true)?;
        let path_buf = PathSafety::lexical(path)?;
        let path_str = path_buf.to_string_lossy();

        for rule in rules {
            let expanded_rule = if rule.starts_with('~') {
                if let Some(home) = dirs_home() {
                    if rule == "~" {
                        home.to_string_lossy().to_string()
                    } else if let Some(stripped) = rule.strip_prefix("~/") {
                        home.join(stripped).to_string_lossy().to_string()
                    } else {
                        rule
                    }
                } else {
                    rule
                }
            } else {
                rule
            };

            // Exact match or ancestor/descendant protection
            let rule_path = PathBuf::from(&expanded_rule);
            if path_buf == rule_path
                || path_buf.starts_with(&rule_path)
                || rule_path.starts_with(&path_buf)
            {
                return Ok(true);
            }

            // Glob pattern match
            if let Ok(pattern) = Pattern::new(&expanded_rule) {
                if pattern.matches(&path_str) {
                    return Ok(true);
                }
            }
        }

        Ok(false)
    }

    pub fn require_unprotected(&self, path: &Path) -> Result<(), PathSafetyError> {
        if self.is_protected(path)? {
            return Err(PathSafetyError::ProtectedPath(path.to_path_buf()));
        }
        Ok(())
    }

    pub fn save_whitelist(&self, rules: &[String]) -> io::Result<()> {
        self.ensure_config_dir()?;
        let content = if rules.is_empty() {
            String::new()
        } else {
            rules.join("\n") + "\n"
        };
        atomic_write(&self.whitelist_path, content.as_bytes())?;
        crate::review::AUTHORIZATION_MANAGER.bump_generation("clean");
        crate::review::AUTHORIZATION_MANAGER.bump_generation("whitelist");
        Ok(())
    }

    pub fn add_rule(&self, rule: &str) -> io::Result<()> {
        self.ensure_config_dir()?;
        let mut rules = self.patterns(false).unwrap_or_default();
        let trimmed = rule.trim().to_string();
        if !rules.contains(&trimmed) {
            rules.push(trimmed);
            let content = rules.join("\n") + "\n";
            atomic_write(&self.whitelist_path, content.as_bytes())?;
            crate::review::AUTHORIZATION_MANAGER.bump_generation("clean");
            crate::review::AUTHORIZATION_MANAGER.bump_generation("whitelist");
        }
        Ok(())
    }

    pub fn remove_rule(&self, rule: &str) -> io::Result<()> {
        let mut rules = self.patterns(false).unwrap_or_default();
        let trimmed = rule.trim();
        let initial_len = rules.len();
        rules.retain(|r| r != trimmed);
        if rules.len() != initial_len {
            let content = if rules.is_empty() {
                String::new()
            } else {
                rules.join("\n") + "\n"
            };
            atomic_write(&self.whitelist_path, content.as_bytes())?;
            crate::review::AUTHORIZATION_MANAGER.bump_generation("clean");
            crate::review::AUTHORIZATION_MANAGER.bump_generation("whitelist");
        }
        Ok(())
    }
}

pub fn atomic_write(path: &Path, data: &[u8]) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "path has no parent"))?;
    let temp_file_name = format!(
        ".tmp_{}_{}",
        path.file_name().unwrap_or_default().to_string_lossy(),
        uuid::Uuid::new_v4()
    );
    let temp_path = parent.join(temp_file_name);

    {
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .mode(0o600)
            .open(&temp_path)?;
        file.write_all(data)?;
        file.sync_all()?;
    }

    fs::rename(&temp_path, path)?;
    Ok(())
}

use std::os::unix::fs::OpenOptionsExt;
