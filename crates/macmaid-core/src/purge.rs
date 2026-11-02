use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use walkdir::WalkDir;

use crate::cancellation::CancellationToken;
use crate::cleaner::Cleaner;
use crate::safety::dirs_home;
use crate::system::size_of;

#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename_all = "camelCase")]
pub struct ProjectArtifact {
    pub name: String,
    pub path: String,
    pub project_path: String,
    pub project_name: String,
    pub bytes: u64,
    pub artifact_type: String, // "build" or "dependencies"
}

pub struct ProjectPurgeManager;

impl ProjectPurgeManager {
    pub fn scan_projects<F>(
        search_paths: &[PathBuf],
        cancellation: Option<&CancellationToken>,
        mut progress: F,
    ) -> Vec<ProjectArtifact>
    where
        F: FnMut(usize, &str),
    {
        let mut artifacts = Vec::new();
        let mut scanned = 0;

        let artifact_names = [
            ("node_modules", "dependencies"),
            ("target", "build"),
            (".venv", "dependencies"),
            ("venv", "dependencies"),
            ("build", "build"),
            ("dist", "build"),
            ("__pycache__", "build"),
            (".next", "build"),
            (".nuxt", "build"),
        ];

        for root in search_paths {
            if !root.exists() {
                continue;
            }

            for entry in WalkDir::new(root)
                .min_depth(1)
                .max_depth(5)
                .into_iter()
                .filter_map(|e| e.ok())
            {
                if let Some(token) = cancellation {
                    if token.is_cancelled() {
                        return artifacts;
                    }
                }

                scanned += 1;
                if scanned % 200 == 0 {
                    progress(scanned, &entry.path().to_string_lossy());
                }

                if entry.file_type().is_dir() {
                    let file_name = entry.file_name().to_string_lossy();
                    for (art_name, art_type) in &artifact_names {
                        if file_name == *art_name {
                            let path = entry.path();
                            if let Some(project_root) = Self::find_project_root(path) {
                                let bytes = size_of(path, cancellation);
                                if bytes > 0 {
                                    artifacts.push(ProjectArtifact {
                                        name: file_name.to_string(),
                                        path: path.to_string_lossy().to_string(),
                                        project_path: project_root.to_string_lossy().to_string(),
                                        project_name: project_root
                                            .file_name()
                                            .unwrap_or_default()
                                            .to_string_lossy()
                                            .to_string(),
                                        bytes,
                                        artifact_type: art_type.to_string(),
                                    });
                                }
                            }
                        }
                    }
                }
            }
        }

        artifacts.sort_by_key(|a| std::cmp::Reverse(a.bytes));
        artifacts
    }

    fn find_project_root(artifact_path: &Path) -> Option<PathBuf> {
        let markers = [
            "Cargo.toml",
            "package.json",
            "pyproject.toml",
            "go.mod",
            "pom.xml",
            "build.gradle",
            ".git",
        ];

        let mut curr = artifact_path.parent();
        while let Some(parent) = curr {
            for marker in &markers {
                if parent.join(marker).exists() {
                    return Some(parent.to_path_buf());
                }
            }
            if parent == Path::new("/")
                || parent == dirs_home().as_deref().unwrap_or(Path::new("/"))
            {
                break;
            }
            curr = parent.parent();
        }
        None
    }

    pub fn validate_project_artifact(
        raw: &Path,
    ) -> Result<PathBuf, crate::safety::PathSafetyError> {
        let path = crate::safety::PathSafety::lexical(raw)?;
        let home = crate::safety::dirs_home()
            .ok_or_else(|| crate::safety::PathSafetyError::EmptyOrSuspicious("no home".into()))?;
        if path == home || !path.starts_with(&home) {
            return Err(crate::safety::PathSafetyError::OutsideCleanupRoots(path));
        }
        let protected_anchors = [
            "Library",
            "Applications",
            "Desktop",
            "Documents",
            "Downloads",
        ];
        for anchor in protected_anchors {
            if path == home.join(anchor) {
                return Err(crate::safety::PathSafetyError::ProtectedHomeAnchor(path));
            }
        }
        crate::safety::PathSafety::reject_symlink_ancestors(&path)?;
        Ok(path)
    }

    pub fn purge_artifact(artifact: &ProjectArtifact, cleaner: &Cleaner) -> Result<u64, String> {
        let path = PathBuf::from(&artifact.path);
        let bytes = size_of(&path, None);
        cleaner.move_reviewed_item_to_trash(&path, Self::validate_project_artifact, Some(bytes))?;
        Ok(bytes)
    }
}
