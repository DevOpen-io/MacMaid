use std::collections::HashSet;
use std::fmt;
use std::os::unix::fs::MetadataExt;
use std::path::{Component, Path, PathBuf};

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum PathSafetyError {
    EmptyOrSuspicious(String),
    ProtectedPath(PathBuf),
    OutsideCleanupRoots(PathBuf),
    SymlinkedAncestor(PathBuf),
    OutsideTrashRoots(PathBuf),
    ProtectedHomeAnchor(PathBuf),
    ProtectedLibraryContent(PathBuf),
    ProtectedBundle(PathBuf),
    NotOwnedByCurrentUser(PathBuf),
    TargetUnavailable(PathBuf),
}

impl fmt::Display for PathSafetyError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::EmptyOrSuspicious(msg) => write!(f, "empty or suspicious path: {msg}"),
            Self::ProtectedPath(p) => write!(f, "protected path: {}", p.display()),
            Self::OutsideCleanupRoots(p) => write!(f, "outside cleanup roots: {}", p.display()),
            Self::SymlinkedAncestor(p) => {
                write!(f, "symlinked ancestor is not allowed: {}", p.display())
            }
            Self::OutsideTrashRoots(p) => {
                write!(f, "outside Trash candidate roots: {}", p.display())
            }
            Self::ProtectedHomeAnchor(p) => write!(f, "protected home anchor: {}", p.display()),
            Self::ProtectedLibraryContent(p) => {
                write!(f, "protected Library content: {}", p.display())
            }
            Self::ProtectedBundle(p) => write!(f, "protected bundle/library: {}", p.display()),
            Self::NotOwnedByCurrentUser(p) => write!(
                f,
                "target is not owned by the current user: {}",
                p.display()
            ),
            Self::TargetUnavailable(p) => write!(f, "target is unavailable: {}", p.display()),
        }
    }
}

impl std::error::Error for PathSafetyError {}

pub struct PathSafety {
    pub hard_blocked: HashSet<PathBuf>,
    pub allowed_roots: Vec<PathBuf>,
}

impl Default for PathSafety {
    fn default() -> Self {
        Self::new(Vec::new())
    }
}

impl PathSafety {
    pub fn new(extra_allowed_roots: Vec<PathBuf>) -> Self {
        let hard_blocked: HashSet<PathBuf> = [
            "/",
            "/System",
            "/bin",
            "/sbin",
            "/usr",
            "/etc",
            "/var",
            "/private",
            "/Library",
            "/Applications",
            "/Users",
            "/Volumes",
        ]
        .iter()
        .map(PathBuf::from)
        .collect();

        let home = dirs_home().unwrap_or_else(|| PathBuf::from("/Users/unknown"));
        let mut allowed_roots = vec![
            home.join("Library/Caches"),
            home.join("Library/Logs"),
            home.join("Library/DiagnosticReports"),
            home.join("Library/Saved Application State"),
            home.join("Library/Developer/Xcode/DerivedData"),
            home.join("Library/Developer/CoreSimulator/Caches"),
            home.join(".npm"),
            home.join(".gradle/caches"),
            home.join(".m2/repository"),
            home.join(".cargo/registry/cache"),
            home.join(".cargo/git/db"),
            home.join(".bun/install/cache"),
            home.join("Library/pnpm/store"),
            home.join(".pub-cache"),
            home.join(".Trash"),
        ];
        allowed_roots.extend(extra_allowed_roots);

        Self {
            hard_blocked,
            allowed_roots,
        }
    }

    pub fn lexical(raw: impl AsRef<Path>) -> Result<PathBuf, PathSafetyError> {
        let path = raw.as_ref();
        let raw_str = path.to_string_lossy();
        if raw_str.is_empty()
            || raw_str.contains('\0')
            || raw_str.contains('\n')
            || raw_str.contains('\r')
        {
            return Err(PathSafetyError::EmptyOrSuspicious(
                "empty or null/newline characters".into(),
            ));
        }

        let expanded = if raw_str.starts_with('~') {
            if let Some(home) = dirs_home() {
                if raw_str == "~" {
                    home
                } else if let Some(stripped) = raw_str.strip_prefix("~/") {
                    home.join(stripped)
                } else {
                    return Err(PathSafetyError::EmptyOrSuspicious(format!(
                        "unsupported user tilde expansion: {raw_str}"
                    )));
                }
            } else {
                return Err(PathSafetyError::EmptyOrSuspicious(
                    "home directory unavailable".into(),
                ));
            }
        } else {
            path.to_path_buf()
        };

        if !expanded.is_absolute() {
            return Err(PathSafetyError::EmptyOrSuspicious(format!(
                "path must be absolute: {raw_str}"
            )));
        }

        // Normalize lexical components without following symlinks
        let mut normalized = PathBuf::new();
        for component in expanded.components() {
            match component {
                Component::Prefix(p) => normalized.push(p.as_os_str()),
                Component::RootDir => normalized.push("/"),
                Component::CurDir => {}
                Component::ParentDir => {
                    return Err(PathSafetyError::EmptyOrSuspicious(format!(
                        "parent traversal '..' rejected: {raw_str}"
                    )));
                }
                Component::Normal(c) => normalized.push(c),
            }
        }

        Ok(normalized)
    }

    pub fn reject_symlink_ancestors(path: &Path) -> Result<(), PathSafetyError> {
        let mut current = path.parent();
        while let Some(parent) = current {
            if parent == Path::new("/") || parent.as_os_str().is_empty() {
                break;
            }
            if let Ok(meta) = std::fs::symlink_metadata(parent) {
                if meta.file_type().is_symlink() {
                    return Err(PathSafetyError::SymlinkedAncestor(parent.to_path_buf()));
                }
            }
            current = parent.parent();
        }
        Ok(())
    }

    pub fn validate_deletion_path(
        &self,
        raw: impl AsRef<Path>,
    ) -> Result<PathBuf, PathSafetyError> {
        let path = Self::lexical(raw)?;
        if self.hard_blocked.contains(&path) {
            return Err(PathSafetyError::ProtectedPath(path));
        }

        let mut allowed = self
            .allowed_roots
            .iter()
            .any(|root| path == *root || path.starts_with(root));
        let path_str = path.to_string_lossy();
        allowed |=
            path_str.starts_with("/private/tmp/") || path_str.starts_with("/private/var/tmp/");
        allowed |= Self::allowed_sandbox_cache(&path);
        allowed |= Self::allowed_app_support_cache(&path);

        if !allowed {
            return Err(PathSafetyError::OutsideCleanupRoots(path));
        }

        Self::reject_symlink_ancestors(&path)?;
        Ok(path)
    }

    pub fn validate_trash_candidate(raw: impl AsRef<Path>) -> Result<PathBuf, PathSafetyError> {
        let path = Self::lexical(raw)?;
        let home = dirs_home()
            .ok_or_else(|| PathSafetyError::EmptyOrSuspicious("no home directory".into()))?;
        let downloads = home.join("Downloads");
        let desktop = home.join("Desktop");

        let allowed = (path.starts_with(&downloads) && path != downloads)
            || (path.starts_with(&desktop) && path != desktop);
        if !allowed {
            return Err(PathSafetyError::OutsideTrashRoots(path));
        }

        Self::reject_symlink_ancestors(&path)?;
        Ok(path)
    }

    pub fn validate_analyzer_candidate(raw: impl AsRef<Path>) -> Result<PathBuf, PathSafetyError> {
        let path = Self::lexical(raw)?;
        let home = dirs_home()
            .ok_or_else(|| PathSafetyError::EmptyOrSuspicious("no home directory".into()))?;

        if !path.starts_with(&home) || path == home {
            return Err(PathSafetyError::EmptyOrSuspicious(
                "analyzer target must be an item below the current user's home".into(),
            ));
        }

        let protected_anchors = [
            "Library",
            "Applications",
            "Public",
            "Desktop",
            "Documents",
            "Downloads",
            "Pictures",
            "Movies",
            "Music",
        ];
        for anchor in protected_anchors {
            let anchor_path = home.join(anchor);
            if path == anchor_path {
                return Err(PathSafetyError::ProtectedHomeAnchor(path));
            }
        }

        let home_library = home.join("Library");
        if path.starts_with(&home_library) {
            return Err(PathSafetyError::ProtectedLibraryContent(path));
        }

        if let Ok(rel) = path.strip_prefix(&home) {
            for component in rel.components() {
                let name = component.as_os_str().to_string_lossy().to_lowercase();
                if name.ends_with(".app") || name.ends_with(".photoslibrary") {
                    return Err(PathSafetyError::ProtectedBundle(path));
                }
            }
        }

        Self::reject_symlink_ancestors(&path)?;

        let meta = std::fs::symlink_metadata(&path)
            .map_err(|_| PathSafetyError::TargetUnavailable(path.clone()))?;
        let uid = unsafe { libc::getuid() };
        if meta.uid() != uid {
            return Err(PathSafetyError::NotOwnedByCurrentUser(path));
        }

        Ok(path)
    }

    fn allowed_sandbox_cache(path: &Path) -> bool {
        let home = match dirs_home() {
            Some(h) => h,
            None => return false,
        };
        let containers = home.join("Library/Containers");
        let rel = match path.strip_prefix(&containers) {
            Ok(r) => r,
            Err(_) => return false,
        };
        let parts: Vec<_> = rel
            .components()
            .map(|c| c.as_os_str().to_string_lossy().to_string())
            .collect();
        parts.len() >= 4 && parts[1] == "Data" && parts[2] == "Library" && parts[3] == "Caches"
    }

    fn allowed_app_support_cache(path: &Path) -> bool {
        let home = match dirs_home() {
            Some(h) => h,
            None => return false,
        };
        let browser_roots = [
            home.join("Library/Application Support/Google/Chrome"),
            home.join("Library/Application Support/Chromium"),
            home.join("Library/Application Support/BraveSoftware/Brave-Browser"),
            home.join("Library/Application Support/Microsoft Edge"),
        ];

        let leaves = [
            "Cache",
            "Code Cache",
            "GPUCache",
            "DawnCache",
            "GrShaderCache",
            "ShaderCache",
            "Media Cache",
        ];

        for root in &browser_roots {
            if let Ok(rel) = path.strip_prefix(root) {
                let parts: Vec<_> = rel
                    .components()
                    .map(|c| c.as_os_str().to_string_lossy().to_string())
                    .collect();
                if parts.len() == 2 {
                    let profile = &parts[0];
                    let leaf = &parts[1];
                    let valid_profile = profile == "Default"
                        || profile == "Guest Profile"
                        || profile == "System Profile"
                        || (profile.starts_with("Profile ")
                            && profile[8..].chars().all(|c| c.is_ascii_digit()));
                    if valid_profile && leaves.contains(&leaf.as_str()) {
                        return true;
                    }
                }
            }
        }

        let app_names = [
            "Code",
            "Code - Insiders",
            "Cursor",
            "Slack",
            "discord",
            "Spotify",
        ];
        let app_leaves = [
            "Cache",
            "Code Cache",
            "GPUCache",
            "DawnCache",
            "GrShaderCache",
            "ShaderCache",
            "Media Cache",
            "Caches",
            "CachedData",
            "CachedExtensionVSIXs",
            "CachedProfilesData",
            "logs",
        ];

        for name in &app_names {
            let app_root = home.join("Library/Application Support").join(name);
            if let Some(parent) = path.parent() {
                if parent == app_root {
                    if let Some(file_name) = path.file_name() {
                        let name_str = file_name.to_string_lossy();
                        if app_leaves.contains(&name_str.as_ref()) {
                            return true;
                        }
                    }
                }
            }
        }

        false
    }
}

pub fn dirs_home() -> Option<PathBuf> {
    std::env::var_os("HOME").map(PathBuf::from)
}

pub fn manual_cache_allowed(manager: &str, path: &Path) -> bool {
    let home = match dirs_home() {
        Some(h) => h,
        None => return false,
    };
    let norm = match PathSafety::lexical(path) {
        Ok(p) => p,
        Err(_) => return false,
    };

    let exact_npm = [
        home.join(".npm"),
        home.join(".npm/_npx"),
        home.join(".npm/_libvips"),
        home.join(".npm/_logs"),
    ];
    let exact_pipx = [
        home.join(".local/pipx/.cache"),
        home.join("Library/Caches/pipx"),
        home.join(".cache/pipx"),
    ];
    let exact_pip = [home.join("Library/Caches/pip"), home.join(".cache/pip")];
    let exact_bun = [home.join(".bun/install/cache")];
    let exact_go = [
        home.join("Library/Caches/go-build"),
        home.join(".cache/go-build"),
    ];
    let exact_brew = [
        home.join("Library/Caches/Homebrew"),
        home.join(".cache/Homebrew"),
    ];
    let exact_gradle = [home.join(".gradle/caches")];
    let exact_cargo_reg = [home.join(".cargo/registry/cache")];
    let exact_cargo_git = [home.join(".cargo/git/db")];
    let exact_pixi = [home.join("Library/Caches/pixi"), home.join(".cache/pixi")];
    let exact_rattler = [
        home.join("Library/Caches/rattler"),
        home.join(".cache/rattler"),
    ];

    let mgr = manager.to_lowercase();
    match mgr.as_str() {
        "pipx" => exact_pipx.contains(&norm),
        "pip" => exact_pip.contains(&norm),
        "npm" => exact_npm.contains(&norm),
        "bun" => exact_bun.contains(&norm),
        "go" => exact_go.contains(&norm),
        "brew-downloads" => exact_brew.contains(&norm),
        "gradle" => exact_gradle.contains(&norm),
        "cargo-registry" => exact_cargo_reg.contains(&norm),
        "cargo-git" => exact_cargo_git.contains(&norm),
        "pixi" => exact_pixi.contains(&norm),
        "rattler" => exact_rattler.contains(&norm),
        "pnpm" => {
            let roots = [
                home.join("Library/pnpm/store"),
                home.join(".local/share/pnpm/store"),
            ];
            roots.iter().any(|r| norm == *r || norm.starts_with(r))
        }
        "yarn-classic" => {
            let roots = [home.join("Library/Caches/Yarn"), home.join(".cache/yarn")];
            roots.iter().any(|r| norm == *r || norm.starts_with(r))
        }
        "composer" => {
            let roots = [
                home.join("Library/Caches/composer"),
                home.join(".cache/composer"),
            ];
            roots.iter().any(|r| norm == *r || norm.starts_with(r))
        }
        _ => false,
    }
}
