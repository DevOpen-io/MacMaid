use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};
use std::collections::HashMap;
use std::fmt;
use std::path::PathBuf;
use std::sync::{LazyLock, Mutex};
use std::time::{SystemTime, UNIX_EPOCH};
use uuid::Uuid;

use crate::apps::{AppComponent, InstalledApplication};
use crate::developer::DeveloperSection;
use crate::memory::ProcessInfo;
use crate::models::{ActionType, CleanupItem, RiskLevel};
use crate::purge::ProjectArtifact;

pub const DEFAULT_MAX_TOKEN_AGE_SECS: u64 = 300; // 5 minutes

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ReviewItem {
    pub key: String,
    pub label: String,
    pub target: String,
    pub action: String,
    pub risk: String,
    pub reason: String,
    pub estimated_bytes: u64,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub requires_app_closed: Option<String>,
    pub user_data: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ReviewPlan {
    pub scope: String,
    pub title: String,
    pub items: Vec<ReviewItem>,
    pub impact: String,
    pub estimate_note: String,
    pub total_bytes: u64,
    pub requires_extra_opt_in: bool,
}

impl ReviewPlan {
    pub fn fingerprint(&self) -> String {
        // Canonical JSON payload for deterministic hashing
        #[derive(Serialize)]
        struct Canonical<'a> {
            scope: &'a str,
            title: &'a str,
            items: &'a [ReviewItem],
            total_bytes: u64,
            requires_extra_opt_in: bool,
        }
        let canonical = Canonical {
            scope: &self.scope,
            title: &self.title,
            items: &self.items,
            total_bytes: self.total_bytes,
            requires_extra_opt_in: self.requires_extra_opt_in,
        };
        let bytes = serde_json::to_vec(&canonical).unwrap_or_default();
        let hash = Sha256::digest(&bytes);
        format!("{:x}", hash)
    }
}

// ──────────────────────────────────────────────
// Plan Constructors
// ──────────────────────────────────────────────

pub fn cleanup_plan(title: &str, items: &[CleanupItem]) -> ReviewPlan {
    let mut review_items = Vec::with_capacity(items.len());
    let mut total_bytes = 0u64;
    let mut requires_extra = false;

    for item in items {
        total_bytes += item.estimated_bytes;
        let risk_str = match item.risk {
            RiskLevel::Safe => "SAFE",
            RiskLevel::Moderate => "MODERATE",
            RiskLevel::Aggressive => "AGGRESSIVE",
            RiskLevel::ManualOnly => "MANUAL",
        };
        let is_user_data = item.risk == RiskLevel::ManualOnly;
        if is_user_data || item.risk == RiskLevel::Aggressive {
            requires_extra = true;
        }

        let action_str = match item.action.kind {
            ActionType::RemovePath => "Permanent delete",
            ActionType::RemoveChildren => "Permanent delete contents",
            ActionType::MoveToTrash => "Move to Trash (recoverable)",
            ActionType::Command => "Manager command",
            ActionType::CommandWithCacheFallback => "Manager command with cache fallback",
            ActionType::ManualCacheFallback => "Manual cache fallback",
        };

        let target = if let Some(p) = &item.path {
            p.to_string_lossy().to_string()
        } else if let Some(exec) = &item.action.executable {
            format!("{exec} {}", item.action.arguments.join(" "))
        } else {
            action_str.to_string()
        };

        review_items.push(ReviewItem {
            key: item.id.clone(),
            label: item.label.clone(),
            target,
            action: action_str.to_string(),
            risk: risk_str.to_string(),
            reason: item.reason.clone(),
            estimated_bytes: item.estimated_bytes,
            requires_app_closed: item.requires_app_closed.clone(),
            user_data: is_user_data,
        });
    }

    ReviewPlan {
        scope: "clean".into(),
        title: title.into(),
        items: review_items,
        impact: "Only the exact reviewed cleanup actions below will be requested.".into(),
        estimate_note: "Estimated scan size is not guaranteed reclaimed disk space on APFS.".into(),
        total_bytes,
        requires_extra_opt_in: requires_extra,
    }
}

pub fn application_plan(app: &InstalledApplication, components: &[AppComponent]) -> ReviewPlan {
    let mut review_items = Vec::with_capacity(components.len() + 1);
    let mut total_bytes = app.bytes;
    let is_cask = app.brew_cask.is_some();

    // App bundle itself
    review_items.push(ReviewItem {
        key: app.path.clone(),
        label: format!("Application: {}", app.name),
        target: app.path.clone(),
        action: if is_cask {
            "Homebrew Cask uninstall".into()
        } else {
            "Move to Trash (recoverable)".into()
        },
        risk: "AGGRESSIVE".into(),
        reason: "Reviewed application bundle".into(),
        estimated_bytes: app.bytes,
        requires_app_closed: Some(app.name.clone()),
        user_data: false,
    });

    for comp in components {
        if comp.path == app.path {
            continue; // already added bundle
        }
        total_bytes += comp.bytes;
        let is_user_data = comp.risk.contains("userData") || comp.risk.contains("Preferences");
        review_items.push(ReviewItem {
            key: comp.path.clone(),
            label: comp.label.clone(),
            target: comp.path.clone(),
            action: "Move to Trash (recoverable)".into(),
            risk: if is_user_data {
                "AGGRESSIVE".into()
            } else {
                "SAFE".into()
            },
            reason: "Exact bundle-ID-derived component".into(),
            estimated_bytes: comp.bytes,
            requires_app_closed: Some(app.name.clone()),
            user_data: is_user_data,
        });
    }

    ReviewPlan {
        scope: "apps".into(),
        title: format!("Uninstall {}", app.name),
        items: review_items,
        impact: "The app must be closed. User-data components require explicit opt-in.".into(),
        estimate_note: "Application bundle and selected leftovers will move to ~/.Trash.".into(),
        total_bytes,
        requires_extra_opt_in: true,
    }
}

pub fn purge_plan(artifacts: &[ProjectArtifact]) -> ReviewPlan {
    let mut review_items = Vec::with_capacity(artifacts.len());
    let mut total_bytes = 0u64;

    for art in artifacts {
        total_bytes += art.bytes;
        review_items.push(ReviewItem {
            key: art.path.clone(),
            label: format!("{} · {}", art.project_name, art.name),
            target: art.path.clone(),
            action: "Move to Trash (recoverable)".into(),
            risk: "MODERATE".into(),
            reason: format!("Rebuildable {} project artifact", art.artifact_type),
            estimated_bytes: art.bytes,
            requires_app_closed: None,
            user_data: false,
        });
    }

    ReviewPlan {
        scope: "purge".into(),
        title: "Project Artifact Purge".into(),
        items: review_items,
        impact: "Project source is never touched; only proven generated artifacts move to Trash."
            .into(),
        estimate_note: "Rebuildable output will be moved safely to Trash.".into(),
        total_bytes,
        requires_extra_opt_in: false,
    }
}

pub fn developer_plan(section: &DeveloperSection) -> ReviewPlan {
    let target = section.path.clone().unwrap_or_else(|| section.name.clone());
    let action_str = match section.action_type.as_str() {
        "delete_children" => "Clean directory contents",
        "command" => "Owning manager command",
        _ => "Move to Trash (recoverable)",
    };

    let item = ReviewItem {
        key: section.name.clone(),
        label: section.name.clone(),
        target,
        action: action_str.into(),
        risk: "MODERATE".into(),
        reason: section.description.clone(),
        estimated_bytes: section.bytes,
        requires_app_closed: None,
        user_data: false,
    };

    ReviewPlan {
        scope: "developer".into(),
        title: format!("Clean {}", section.name),
        items: vec![item],
        impact: "Manager-safe cache deletion; tool binaries and runtimes will not be deleted."
            .into(),
        estimate_note: "Developer caches will be reclaimed.".into(),
        total_bytes: section.bytes,
        requires_extra_opt_in: false,
    }
}

pub fn process_plan(proc: &ProcessInfo, force: bool) -> ReviewPlan {
    let action_str = if force {
        "Send SIGKILL"
    } else {
        "Send SIGTERM"
    };
    let item = ReviewItem {
        key: format!("{}:{}", proc.pid, proc.start_time),
        label: format!("Process: {} (PID {})", proc.name, proc.pid),
        target: proc.executable.clone(),
        action: action_str.into(),
        risk: if force {
            "AGGRESSIVE".into()
        } else {
            "MODERATE".into()
        },
        reason: format!(
            "Resident memory: {} bytes · CPU: {:.1}%",
            proc.rss_bytes, proc.cpu_percent
        ),
        estimated_bytes: proc.rss_bytes,
        requires_app_closed: None,
        user_data: false,
    };

    ReviewPlan {
        scope: "memory".into(),
        title: format!("Terminate Process {}", proc.name),
        items: vec![item],
        impact: if force {
            "SIGKILL immediately halts process execution. Unsaved work may be lost."
        } else {
            "SIGTERM requests graceful process shutdown. Applications may lose unsaved work."
        }
        .into(),
        estimate_note: "Process termination authorization is single-use and PID-bound.".into(),
        total_bytes: proc.rss_bytes,
        requires_extra_opt_in: force,
    }
}

pub fn analyzer_trash_plan(paths: &[PathBuf], estimated_bytes: u64) -> ReviewPlan {
    let items = paths
        .iter()
        .map(|p| ReviewItem {
            key: p.to_string_lossy().to_string(),
            label: p
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| p.to_string_lossy().to_string()),
            target: p.to_string_lossy().to_string(),
            action: "Move to Trash (recoverable)".into(),
            risk: "AGGRESSIVE".into(),
            reason: "User-selected disk analyzer item".into(),
            estimated_bytes: 0,
            requires_app_closed: None,
            user_data: true,
        })
        .collect();

    ReviewPlan {
        scope: "analyzer".into(),
        title: "Move Selection to Trash".into(),
        items,
        impact: "Selected files will move to ~/.Trash. Trash remains recoverable until emptied."
            .into(),
        estimate_note: "User files and folders are moved to Trash.".into(),
        total_bytes: estimated_bytes,
        requires_extra_opt_in: true,
    }
}

pub fn duplicate_trash_plan(paths: &[PathBuf], estimated_bytes: u64) -> ReviewPlan {
    let items = paths
        .iter()
        .map(|p| ReviewItem {
            key: p.to_string_lossy().to_string(),
            label: p
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| p.to_string_lossy().to_string()),
            target: p.to_string_lossy().to_string(),
            action: "Move to Trash (recoverable)".into(),
            risk: "SAFE".into(),
            reason: "Redundant duplicate copy (at least one copy preserved)".into(),
            estimated_bytes: 0,
            requires_app_closed: None,
            user_data: false,
        })
        .collect();

    ReviewPlan {
        scope: "duplicates".into(),
        title: "Clean Duplicate Files".into(),
        items,
        impact: "Selected duplicate copies will move to ~/.Trash. Master copy is retained.".into(),
        estimate_note: "Recoverable from ~/.Trash.".into(),
        total_bytes: estimated_bytes,
        requires_extra_opt_in: false,
    }
}

pub fn large_files_trash_plan(paths: &[PathBuf], estimated_bytes: u64) -> ReviewPlan {
    let items = paths
        .iter()
        .map(|p| ReviewItem {
            key: p.to_string_lossy().to_string(),
            label: p
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| p.to_string_lossy().to_string()),
            target: p.to_string_lossy().to_string(),
            action: "Move to Trash (recoverable)".into(),
            risk: "MODERATE".into(),
            reason: "User-selected large/old file candidate".into(),
            estimated_bytes: 0,
            requires_app_closed: None,
            user_data: true,
        })
        .collect();

    ReviewPlan {
        scope: "large-files".into(),
        title: "Move Large & Old Files to Trash".into(),
        items,
        impact: "Selected files will move to ~/.Trash. Trash remains recoverable until emptied."
            .into(),
        estimate_note: "Recoverable from ~/.Trash.".into(),
        total_bytes: estimated_bytes,
        requires_extra_opt_in: false,
    }
}

pub fn downloads_trash_plan(paths: &[PathBuf], estimated_bytes: u64) -> ReviewPlan {
    let items = paths
        .iter()
        .map(|p| ReviewItem {
            key: p.to_string_lossy().to_string(),
            label: p
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_else(|| p.to_string_lossy().to_string()),
            target: p.to_string_lossy().to_string(),
            action: "Move to Trash (recoverable)".into(),
            risk: "SAFE".into(),
            reason: "Categorized download item (installer/archive/incomplete)".into(),
            estimated_bytes: 0,
            requires_app_closed: None,
            user_data: false,
        })
        .collect();

    ReviewPlan {
        scope: "downloads".into(),
        title: "Clean Categorized Downloads".into(),
        items,
        impact: "Selected downloads will move to ~/.Trash.".into(),
        estimate_note: "Recoverable from ~/.Trash.".into(),
        total_bytes: estimated_bytes,
        requires_extra_opt_in: false,
    }
}

pub fn snapshot_plan(target_gb: u64) -> ReviewPlan {
    let target_bytes = target_gb * 1024 * 1024 * 1024;
    let item = ReviewItem {
        key: "time-machine-thin".into(),
        label: "Thin local Time Machine snapshots".into(),
        target: format!("Reclaim target: {target_gb} GB"),
        action: "tmutil thinlocalsnapshots".into(),
        risk: "AGGRESSIVE".into(),
        reason: "Time Machine chooses reclaimable local APFS snapshots".into(),
        estimated_bytes: target_bytes,
        requires_app_closed: None,
        user_data: false,
    };

    ReviewPlan {
        scope: "snapshots".into(),
        title: "Thin Time Machine snapshots".into(),
        items: vec![item],
        impact: "Apple normally manages local snapshots automatically. Use this only for an immediate space need; local recovery snapshots may be removed, while backup-disk history is not selected.".into(),
        estimate_note: "Requested reclaim target is not a guarantee. Time Machine decides what is reclaimable; measured free-space change is recorded after the command.".into(),
        total_bytes: target_bytes,
        requires_extra_opt_in: true,
    }
}

// ──────────────────────────────────────────────
// Authorization Error & Manager
// ──────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AuthorizationError {
    MissingToken,
    InvalidTokenFormat,
    ExpiredToken { age_secs: u64, max_age: u64 },
    FutureToken,
    StaleGeneration { token_gen: u64, current_gen: u64 },
    FingerprintMismatch,
    InvalidSignature,
    TokenAlreadyConsumed,
    ExtraOptInRequired,
    TargetIdentityChanged(String),
}

impl fmt::Display for AuthorizationError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::MissingToken => write!(f, "A review token is required for this operation"),
            Self::InvalidTokenFormat => write!(f, "Invalid review token format"),
            Self::ExpiredToken { age_secs, max_age } => write!(
                f,
                "Review token expired (age {age_secs}s > max {max_age}s); fresh review required"
            ),
            Self::FutureToken => write!(f, "Review token timestamp is in the future"),
            Self::StaleGeneration { token_gen, current_gen } => write!(
                f,
                "Review is stale (generation {token_gen} != {current_gen}); rules or configuration changed"
            ),
            Self::FingerprintMismatch => write!(
                f,
                "Review plan fingerprint mismatch; selection or target items changed"
            ),
            Self::InvalidSignature => write!(f, "Invalid review token cryptographic signature"),
            Self::TokenAlreadyConsumed => write!(
                f,
                "Review token was already consumed; single-use tokens cannot be reused"
            ),
            Self::ExtraOptInRequired => write!(
                f,
                "Explicit user-data/aggressive opt-in is required for this operation"
            ),
            Self::TargetIdentityChanged(msg) => {
                write!(f, "Target identity changed since review: {msg}")
            }
        }
    }
}

impl std::error::Error for AuthorizationError {}

#[derive(Debug, Clone)]
struct ActiveToken {
    scope: String,
    generation: u64,
    fingerprint: String,
    created_at: u64,
}

pub struct AuthorizationManager {
    secret: [u8; 32],
    generations: Mutex<HashMap<String, u64>>,
    active_tokens: Mutex<HashMap<String, ActiveToken>>,
}

impl Default for AuthorizationManager {
    fn default() -> Self {
        Self::new()
    }
}

impl AuthorizationManager {
    pub fn new() -> Self {
        let mut secret = [0u8; 32];
        let uuid1 = Uuid::new_v4();
        let uuid2 = Uuid::new_v4();
        secret[..16].copy_from_slice(uuid1.as_bytes());
        secret[16..].copy_from_slice(uuid2.as_bytes());

        Self {
            secret,
            generations: Mutex::new(HashMap::new()),
            active_tokens: Mutex::new(HashMap::new()),
        }
    }

    pub fn bump_generation(&self, scope: &str) {
        let mut gens = self.generations.lock().unwrap();
        let entry = gens.entry(scope.to_string()).or_insert(0);
        *entry += 1;
    }

    pub fn generation(&self, scope: &str) -> u64 {
        let gens = self.generations.lock().unwrap();
        gens.get(scope).copied().unwrap_or(0)
    }

    pub fn issue_token(&self, scope: &str, plan: &ReviewPlan) -> String {
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();
        let generation = self.generation(scope);
        let fingerprint = plan.fingerprint();
        let nonce = Uuid::new_v4().simple().to_string();

        let payload = format!("{now}:{generation}:{fingerprint}:{nonce}");
        let sig = self.compute_signature(scope, &payload);
        let full_token = format!("{payload}:{sig}");

        let mut tokens = self.active_tokens.lock().unwrap();
        // Prune old tokens if exceeding capacity
        if tokens.len() >= 256 {
            tokens.retain(|_, t| now.saturating_sub(t.created_at) < DEFAULT_MAX_TOKEN_AGE_SECS);
        }

        tokens.insert(
            full_token.clone(),
            ActiveToken {
                scope: scope.to_string(),
                generation,
                fingerprint,
                created_at: now,
            },
        );

        full_token
    }

    pub fn validate_and_consume(
        &self,
        scope: &str,
        token: &str,
        plan: &ReviewPlan,
        extra_opt_in: bool,
    ) -> Result<(), AuthorizationError> {
        let parts: Vec<&str> = token.split(':').collect();
        if parts.len() != 5 {
            return Err(AuthorizationError::InvalidTokenFormat);
        }

        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs();

        let timestamp: u64 = parts[0]
            .parse()
            .map_err(|_| AuthorizationError::InvalidTokenFormat)?;
        let token_gen: u64 = parts[1]
            .parse()
            .map_err(|_| AuthorizationError::InvalidTokenFormat)?;
        let fingerprint = parts[2];
        let _nonce = parts[3];
        let signature = parts[4];

        // 1. Check timestamp
        if timestamp > now + 5 {
            return Err(AuthorizationError::FutureToken);
        }
        let age = now.saturating_sub(timestamp);
        if age > DEFAULT_MAX_TOKEN_AGE_SECS {
            return Err(AuthorizationError::ExpiredToken {
                age_secs: age,
                max_age: DEFAULT_MAX_TOKEN_AGE_SECS,
            });
        }

        // 2. Check generation
        let current_gen = self.generation(scope);
        if token_gen != current_gen {
            return Err(AuthorizationError::StaleGeneration {
                token_gen,
                current_gen,
            });
        }

        // 3. Check fingerprint
        let plan_fingerprint = plan.fingerprint();
        if fingerprint != plan_fingerprint {
            return Err(AuthorizationError::FingerprintMismatch);
        }

        // 4. Verify cryptographic signature
        let payload = format!("{timestamp}:{token_gen}:{fingerprint}:{_nonce}");
        let expected_sig = self.compute_signature(scope, &payload);
        if !constant_time_eq_str(signature, &expected_sig) {
            return Err(AuthorizationError::InvalidSignature);
        }

        // 5. Check active tokens map and consume (SINGLE-USE!)
        let mut tokens = self.active_tokens.lock().unwrap();
        match tokens.remove(token) {
            Some(record) => {
                if record.scope != scope
                    || record.generation != current_gen
                    || record.fingerprint != plan_fingerprint
                {
                    return Err(AuthorizationError::FingerprintMismatch);
                }
            }
            None => {
                return Err(AuthorizationError::TokenAlreadyConsumed);
            }
        }

        // 6. Extra opt-in check for aggressive/user-data operations
        if plan.requires_extra_opt_in && !extra_opt_in {
            return Err(AuthorizationError::ExtraOptInRequired);
        }

        Ok(())
    }

    fn compute_signature(&self, scope: &str, payload: &str) -> String {
        let message = format!("{scope}:{payload}");
        let hmac = hmac_sha256(&self.secret, message.as_bytes());
        format!("{:x}", Sha256::digest(hmac))
    }
}

pub static AUTHORIZATION_MANAGER: LazyLock<AuthorizationManager> =
    LazyLock::new(AuthorizationManager::new);

// ──────────────────────────────────────────────
// Crypto Helper Functions
// ──────────────────────────────────────────────

fn hmac_sha256(key: &[u8], message: &[u8]) -> [u8; 32] {
    let mut k = [0u8; 64];
    if key.len() > 64 {
        let hash = Sha256::digest(key);
        k[..32].copy_from_slice(&hash);
    } else {
        k[..key.len()].copy_from_slice(key);
    }

    let mut k_ipad = [0x36u8; 64];
    let mut k_opad = [0x5cu8; 64];
    for i in 0..64 {
        k_ipad[i] ^= k[i];
        k_opad[i] ^= k[i];
    }

    let mut inner = Sha256::new();
    inner.update(k_ipad);
    inner.update(message);
    let inner_hash = inner.finalize();

    let mut outer = Sha256::new();
    outer.update(k_opad);
    outer.update(inner_hash);
    outer.finalize().into()
}

fn constant_time_eq_str(a: &str, b: &str) -> bool {
    let a_bytes = a.as_bytes();
    let b_bytes = b.as_bytes();
    if a_bytes.len() != b_bytes.len() {
        return false;
    }
    let mut diff = 0u8;
    for (x, y) in a_bytes.iter().zip(b_bytes.iter()) {
        diff |= x ^ y;
    }
    diff == 0
}
