use serde::{Deserialize, Serialize};
use std::path::PathBuf;
use uuid::Uuid;

#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum RiskLevel {
    Safe = 0,
    Moderate = 1,
    Aggressive = 2,
    ManualOnly = 3,
}

impl RiskLevel {
    pub fn display_name(&self) -> &'static str {
        match self {
            Self::Safe => "SAFE",
            Self::Moderate => "MODERATE",
            Self::Aggressive => "AGGRESSIVE",
            Self::ManualOnly => "MANUAL",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum CleanupProfile {
    Safe,
    Deep,
    Developer,
    Aggressive,
}

impl CleanupProfile {
    pub fn maximum_risk(&self) -> RiskLevel {
        match self {
            Self::Safe => RiskLevel::Safe,
            Self::Deep => RiskLevel::Moderate,
            Self::Developer => RiskLevel::Moderate,
            Self::Aggressive => RiskLevel::Aggressive,
        }
    }

    pub fn includes_developer(&self) -> bool {
        matches!(self, Self::Developer | Self::Aggressive)
    }

    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Safe => "safe",
            Self::Deep => "deep",
            Self::Developer => "developer",
            Self::Aggressive => "aggressive",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum CleanupCategory {
    #[serde(rename = "User caches")]
    UserCaches,
    #[serde(rename = "Browser caches")]
    BrowserCaches,
    #[serde(rename = "Application caches")]
    AppCaches,
    #[serde(rename = "Logs & diagnostics")]
    Logs,
    #[serde(rename = "Developer tools")]
    Developer,
    #[serde(rename = "Package-manager caches")]
    PackageManagers,
    #[serde(rename = "Temporary files")]
    Temporary,
    #[serde(rename = "Trash")]
    Trash,
    #[serde(rename = "Uninstalled-app leftovers")]
    Leftovers,
    #[serde(rename = "Installer files")]
    Installers,
    #[serde(rename = "Maintenance commands")]
    Maintenance,
}

impl CleanupCategory {
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::UserCaches => "User caches",
            Self::BrowserCaches => "Browser caches",
            Self::AppCaches => "Application caches",
            Self::Logs => "Logs & diagnostics",
            Self::Developer => "Developer tools",
            Self::PackageManagers => "Package-manager caches",
            Self::Temporary => "Temporary files",
            Self::Trash => "Trash",
            Self::Leftovers => "Uninstalled-app leftovers",
            Self::Installers => "Installer files",
            Self::Maintenance => "Maintenance commands",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ActionType {
    RemovePath,
    RemoveChildren,
    Command,
    CommandWithCacheFallback,
    ManualCacheFallback,
    MoveToTrash,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CleanupAction {
    pub kind: ActionType,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub executable: Option<String>,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub arguments: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dry_run_arguments: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fallback_manager: Option<String>,
}

impl CleanupAction {
    pub fn remove_path() -> Self {
        Self {
            kind: ActionType::RemovePath,
            executable: None,
            arguments: Vec::new(),
            dry_run_arguments: None,
            fallback_manager: None,
        }
    }

    pub fn remove_children() -> Self {
        Self {
            kind: ActionType::RemoveChildren,
            executable: None,
            arguments: Vec::new(),
            dry_run_arguments: None,
            fallback_manager: None,
        }
    }

    pub fn move_to_trash() -> Self {
        Self {
            kind: ActionType::MoveToTrash,
            executable: None,
            arguments: Vec::new(),
            dry_run_arguments: None,
            fallback_manager: None,
        }
    }

    pub fn command(executable: impl Into<String>, arguments: Vec<String>) -> Self {
        Self {
            kind: ActionType::Command,
            executable: Some(executable.into()),
            arguments,
            dry_run_arguments: None,
            fallback_manager: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct CleanupItem {
    pub id: String,
    pub category: CleanupCategory,
    pub label: String,
    pub path: Option<PathBuf>,
    pub estimated_bytes: u64,
    pub risk: RiskLevel,
    pub reason: String,
    pub action: CleanupAction,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub requires_app_closed: Option<String>,
}

impl CleanupItem {
    pub fn new(
        category: CleanupCategory,
        label: impl Into<String>,
        path: Option<PathBuf>,
        estimated_bytes: u64,
        risk: RiskLevel,
        reason: impl Into<String>,
        action: CleanupAction,
    ) -> Self {
        Self {
            id: Uuid::new_v4().to_string(),
            category,
            label: label.into(),
            path,
            estimated_bytes,
            risk,
            reason: reason.into(),
            action,
            requires_app_closed: None,
        }
    }

    pub fn with_app_closed(mut self, app: impl Into<String>) -> Self {
        self.requires_app_closed = Some(app.into());
        self
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ScanResult {
    pub items: Vec<CleanupItem>,
    pub notes: Vec<String>,
    pub status: String,
    pub issues: Vec<String>,
}

impl ScanResult {
    pub fn is_complete(&self) -> bool {
        self.status == "complete"
    }

    pub fn total_bytes(&self) -> u64 {
        self.items.iter().map(|item| item.estimated_bytes).sum()
    }
}

#[derive(Debug, Clone, Default, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct OperationResult {
    pub freed: u64,
    pub failed: usize,
    pub skipped: usize,
    pub details: Vec<String>,
    pub scanned_estimated_bytes: u64,
    pub processed_estimated_bytes: u64,
    pub trash_moved_estimated_bytes: u64,
    pub observed_free_bytes_delta: Option<i64>,
    pub unknown_reclaim_count: usize,
    pub measurement_notes: Vec<String>,
}
