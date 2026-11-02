use crate::modals::review_modal::{render_review_modal, ModalAction, ReviewModalState, StagedPlan};
use crate::theme::ThemeMode;
use crate::views::app_uninstaller::{
    render_app_uninstaller_view, AppUninstallerAction, AppUninstallerViewState,
};
use crate::views::developer::{
    render_developer_storage_view, DeveloperStorageAction, DeveloperStorageViewState,
};
use crate::views::doctor::{render_doctor_view, DoctorAction, DoctorViewState};
use crate::views::downloads::{
    render_smart_downloads_view, SmartDownloadsAction, SmartDownloadsViewState,
};
use crate::views::duplicates::{render_duplicates_view, DuplicateAction, DuplicateFinderViewState};
use crate::views::history::{render_history_view, HistoryAction, HistoryViewState};
use crate::views::large_files::{render_large_files_view, LargeFilesAction, LargeFilesViewState};
use crate::views::memory::{render_memory_view, MemoryAction, MemoryViewState};
use crate::views::project_purge::{
    render_project_purge_view, ProjectPurgeAction, ProjectPurgeViewState,
};
use crate::views::settings::{render_settings_view, SettingsAction, SettingsViewState};
use crate::views::sidebar::{render_sidebar, NavTab};
use crate::views::smart_clean::{render_smart_clean_view, SmartCleanAction, SmartCleanViewState};
use crate::views::treemap::{render_treemap_view, TreemapAction, TreemapViewState};
use eframe::egui::{self, RichText};
use macmaid_core::analyzer::{AnalyzerNode, IncrementalAnalyzer};
use macmaid_core::apps::ApplicationManager;
use macmaid_core::cleaner::Cleaner;
use macmaid_core::config::Config;
use macmaid_core::developer::DeveloperStorageCenter;
use macmaid_core::doctor::Doctor;
use macmaid_core::duplicates::DuplicateFinder;
use macmaid_core::large_files::{LargeOldFile, LargeOldFileScanner};
use macmaid_core::memory::MemoryService;
use macmaid_core::purge::ProjectPurgeManager;
use macmaid_core::review::{
    analyzer_trash_plan, application_plan, cleanup_plan, developer_plan, downloads_trash_plan,
    duplicate_trash_plan, large_files_trash_plan, process_plan, purge_plan, snapshot_plan,
    AUTHORIZATION_MANAGER,
};
use macmaid_core::scanner::Scanner;
use macmaid_core::smart_downloads::SmartDownloadsScanner;
use macmaid_core::snapshots::SnapshotManager;
use macmaid_core::update::check_update_status;
use std::path::PathBuf;
use std::sync::mpsc::{channel, Receiver, Sender};
use std::thread;

type HistoryResult = Result<
    (
        Vec<macmaid_core::reporting::OperationRecord>,
        Vec<macmaid_core::recovery::RestorableItem>,
    ),
    String,
>;

pub struct MacMaidGuiApp {
    pub theme_mode: ThemeMode,
    pub current_tab: NavTab,
    pub is_turkish: bool,

    // Views State
    pub smart_clean_state: SmartCleanViewState,
    pub app_uninstaller_state: AppUninstallerViewState,
    pub project_purge_state: ProjectPurgeViewState,
    pub developer_state: DeveloperStorageViewState,
    pub memory_state: MemoryViewState,
    pub treemap_state: TreemapViewState,
    pub duplicates_state: DuplicateFinderViewState,
    pub large_files_state: LargeFilesViewState,
    pub downloads_state: SmartDownloadsViewState,
    pub doctor_state: DoctorViewState,
    pub history_state: HistoryViewState,
    pub settings_state: SettingsViewState,

    // Safety Review Modal State
    pub review_modal: ReviewModalState,

    // Global action notification
    pub global_status: Option<(String, bool)>, // (message, is_error)

    // Async worker channels
    pub action_tx: Sender<Result<String, String>>,
    pub action_rx: Receiver<Result<String, String>>,

    // View specific worker channels
    pub treemap_tx: Sender<Result<Vec<AnalyzerNode>, String>>,
    pub treemap_rx: Receiver<Result<Vec<AnalyzerNode>, String>>,

    pub memory_tx: Sender<Vec<macmaid_core::memory::ProcessInfo>>,
    pub memory_rx: Receiver<Vec<macmaid_core::memory::ProcessInfo>>,

    pub clean_scan_tx: Sender<Vec<macmaid_core::models::CleanupItem>>,
    pub clean_scan_rx: Receiver<Vec<macmaid_core::models::CleanupItem>>,

    pub apps_scan_tx: Sender<Vec<macmaid_core::apps::InstalledApplication>>,
    pub apps_scan_rx: Receiver<Vec<macmaid_core::apps::InstalledApplication>>,

    pub purge_scan_tx: Sender<Vec<macmaid_core::purge::ProjectArtifact>>,
    pub purge_scan_rx: Receiver<Vec<macmaid_core::purge::ProjectArtifact>>,

    pub developer_scan_tx: Sender<Vec<macmaid_core::developer::DeveloperSection>>,
    pub developer_scan_rx: Receiver<Vec<macmaid_core::developer::DeveloperSection>>,

    pub duplicates_scan_tx: Sender<Vec<macmaid_core::duplicates::DuplicateGroup>>,
    pub duplicates_scan_rx: Receiver<Vec<macmaid_core::duplicates::DuplicateGroup>>,

    pub large_files_scan_tx: Sender<Vec<LargeOldFile>>,
    pub large_files_scan_rx: Receiver<Vec<LargeOldFile>>,

    pub downloads_scan_tx: Sender<macmaid_core::smart_downloads::SmartDownloadsReport>,
    pub downloads_scan_rx: Receiver<macmaid_core::smart_downloads::SmartDownloadsReport>,

    pub doctor_scan_tx: Sender<(
        Vec<macmaid_core::doctor::DiagnosticCheck>,
        Vec<macmaid_core::snapshots::SnapshotInfo>,
    )>,
    pub doctor_scan_rx: Receiver<(
        Vec<macmaid_core::doctor::DiagnosticCheck>,
        Vec<macmaid_core::snapshots::SnapshotInfo>,
    )>,

    pub update_check_tx: Sender<macmaid_core::update::UpdateStatus>,
    pub update_check_rx: Receiver<macmaid_core::update::UpdateStatus>,

    pub history_tx: Sender<HistoryResult>,
    pub history_rx: Receiver<HistoryResult>,
}

impl Default for MacMaidGuiApp {
    fn default() -> Self {
        let (action_tx, action_rx) = channel();
        let (treemap_tx, treemap_rx) = channel();
        let (memory_tx, memory_rx) = channel();
        let (clean_scan_tx, clean_scan_rx) = channel();
        let (apps_scan_tx, apps_scan_rx) = channel();
        let (purge_scan_tx, purge_scan_rx) = channel();
        let (developer_scan_tx, developer_scan_rx) = channel();
        let (duplicates_scan_tx, duplicates_scan_rx) = channel();
        let (large_files_scan_tx, large_files_scan_rx) = channel();
        let (downloads_scan_tx, downloads_scan_rx) = channel();
        let (doctor_scan_tx, doctor_scan_rx) = channel();
        let (update_check_tx, update_check_rx) = channel();
        let (history_tx, history_rx) = channel();

        Self {
            theme_mode: ThemeMode::Dark,
            current_tab: NavTab::SmartClean,
            is_turkish: false,

            smart_clean_state: SmartCleanViewState::default(),
            app_uninstaller_state: AppUninstallerViewState::default(),
            project_purge_state: ProjectPurgeViewState::default(),
            developer_state: DeveloperStorageViewState::default(),
            memory_state: MemoryViewState::default(),
            treemap_state: TreemapViewState::default(),
            duplicates_state: DuplicateFinderViewState::default(),
            large_files_state: LargeFilesViewState::default(),
            downloads_state: SmartDownloadsViewState::default(),
            doctor_state: DoctorViewState::default(),
            history_state: HistoryViewState::default(),
            settings_state: SettingsViewState::default(),

            review_modal: ReviewModalState::default(),
            global_status: None,

            action_tx,
            action_rx,
            treemap_tx,
            treemap_rx,
            memory_tx,
            memory_rx,
            clean_scan_tx,
            clean_scan_rx,
            apps_scan_tx,
            apps_scan_rx,
            purge_scan_tx,
            purge_scan_rx,
            developer_scan_tx,
            developer_scan_rx,
            duplicates_scan_tx,
            duplicates_scan_rx,
            large_files_scan_tx,
            large_files_scan_rx,
            downloads_scan_tx,
            downloads_scan_rx,
            doctor_scan_tx,
            doctor_scan_rx,
            update_check_tx,
            update_check_rx,
            history_tx,
            history_rx,
        }
    }
}

impl eframe::App for MacMaidGuiApp {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        // Poll async receivers
        self.poll_channels(ctx);

        // Apply theme visuals
        let visuals = match self.theme_mode {
            ThemeMode::Dark => egui::Visuals::dark(),
            ThemeMode::Light => egui::Visuals::light(),
        };
        ctx.set_visuals(visuals);

        // Sidebar Navigation Panel
        egui::SidePanel::left("macmaid_sidebar")
            .resizable(false)
            .exact_width(210.0)
            .frame(
                egui::Frame::NONE
                    .fill(self.theme_mode.sidebar_bg())
                    .inner_margin(12.0),
            )
            .show(ctx, |ui| {
                render_sidebar(
                    ui,
                    &mut self.current_tab,
                    self.is_turkish,
                    &mut self.theme_mode,
                );
            });

        // Central Content Area
        egui::CentralPanel::default()
            .frame(
                egui::Frame::NONE
                    .fill(self.theme_mode.bg())
                    .inner_margin(16.0),
            )
            .show(ctx, |ui| {
                // Global status toast bar
                let mut dismiss = false;
                if let Some((ref msg, is_err)) = self.global_status {
                    let color = if is_err {
                        self.theme_mode.danger()
                    } else {
                        self.theme_mode.success()
                    };
                    ui.horizontal(|ui| {
                        ui.label(RichText::new(format!("ℹ️ {msg}")).color(color).strong());
                        if ui.button("Dismiss").clicked() {
                            dismiss = true;
                        }
                    });
                    ui.add_space(6.0);
                }
                if dismiss {
                    self.global_status = None;
                }

                match self.current_tab {
                    NavTab::SmartClean => {
                        let action = render_smart_clean_view(
                            ui,
                            &self.theme_mode,
                            &mut self.smart_clean_state,
                            self.is_turkish,
                        );
                        self.handle_smart_clean_action(action, ctx);
                    }
                    NavTab::AppUninstaller => {
                        let action = render_app_uninstaller_view(
                            ui,
                            &self.theme_mode,
                            &mut self.app_uninstaller_state,
                            self.is_turkish,
                        );
                        self.handle_app_uninstaller_action(action, ctx);
                    }
                    NavTab::ProjectPurge => {
                        let action = render_project_purge_view(
                            ui,
                            &self.theme_mode,
                            &mut self.project_purge_state,
                        );
                        self.handle_project_purge_action(action, ctx);
                    }
                    NavTab::DeveloperStorage => {
                        let action = render_developer_storage_view(
                            ui,
                            &self.theme_mode,
                            &mut self.developer_state,
                            self.is_turkish,
                        );
                        self.handle_developer_action(action, ctx);
                    }
                    NavTab::MemoryManagement => {
                        let action =
                            render_memory_view(ui, &self.theme_mode, &mut self.memory_state);
                        self.handle_memory_action(action, ctx);
                    }
                    NavTab::StorageTreemap => {
                        let action =
                            render_treemap_view(ui, &self.theme_mode, &mut self.treemap_state);
                        self.handle_treemap_action(action, ctx);
                    }
                    NavTab::DuplicateFinder => {
                        let action = render_duplicates_view(
                            ui,
                            &self.theme_mode,
                            &mut self.duplicates_state,
                        );
                        self.handle_duplicates_action(action, ctx);
                    }
                    NavTab::LargeFiles => {
                        let action = render_large_files_view(
                            ui,
                            &self.theme_mode,
                            &mut self.large_files_state,
                        );
                        self.handle_large_files_action(action, ctx);
                    }
                    NavTab::SmartDownloads => {
                        let action = render_smart_downloads_view(
                            ui,
                            &self.theme_mode,
                            &mut self.downloads_state,
                        );
                        self.handle_downloads_action(action, ctx);
                    }
                    NavTab::HealthDoctor => {
                        let action =
                            render_doctor_view(ui, &self.theme_mode, &mut self.doctor_state);
                        self.handle_doctor_action(action, ctx);
                    }
                    NavTab::History => {
                        if self.history_state.operations.is_empty()
                            && self.history_state.restorable.is_empty()
                            && !self.history_state.is_loading
                        {
                            self.handle_history_action(HistoryAction::Refresh, ctx);
                        }
                        let action = render_history_view(
                            ui,
                            &self.theme_mode,
                            &mut self.history_state,
                            self.is_turkish,
                        );
                        self.handle_history_action(action, ctx);
                    }
                    NavTab::Settings => {
                        let action = render_settings_view(
                            ui,
                            &mut self.theme_mode,
                            &mut self.is_turkish,
                            &mut self.settings_state,
                        );
                        self.handle_settings_action(action, ctx);
                    }
                }
            });

        // Review Confirmation Sheet Modal (P0 Safety Barrier)
        let modal_action = render_review_modal(
            ctx,
            &self.theme_mode,
            &mut self.review_modal,
            self.is_turkish,
        );
        self.handle_modal_action(modal_action, ctx);
    }
}

impl MacMaidGuiApp {
    fn poll_channels(&mut self, ctx: &egui::Context) {
        if let Ok(res) = self.action_rx.try_recv() {
            match res {
                Ok(msg) => self.global_status = Some((msg, false)),
                Err(e) => self.global_status = Some((e, true)),
            }
            ctx.request_repaint();
        }

        if let Ok(res) = self.treemap_rx.try_recv() {
            self.treemap_state.is_scanning = false;
            match res {
                Ok(items) => {
                    self.treemap_state.items = items;
                    self.treemap_state.scan_progress_msg = "Scan complete".into();
                }
                Err(e) => {
                    self.treemap_state.scan_progress_msg = format!("Scan failed: {e}");
                    self.global_status = Some((e, true));
                }
            }
            ctx.request_repaint();
        }

        if let Ok(procs) = self.memory_rx.try_recv() {
            self.memory_state.is_refreshing = false;
            self.memory_state.processes = procs;
            ctx.request_repaint();
        }

        if let Ok(items) = self.clean_scan_rx.try_recv() {
            self.smart_clean_state.is_scanning = false;
            self.smart_clean_state.items = items;
            self.smart_clean_state.selected_ids = self
                .smart_clean_state
                .items
                .iter()
                .map(|it| it.id.clone())
                .collect();
            ctx.request_repaint();
        }

        if let Ok(apps) = self.apps_scan_rx.try_recv() {
            self.app_uninstaller_state.is_loading = false;
            self.app_uninstaller_state.apps = apps;
            ctx.request_repaint();
        }

        if let Ok(artifacts) = self.purge_scan_rx.try_recv() {
            self.project_purge_state.is_scanning = false;
            self.project_purge_state.artifacts = artifacts;
            self.project_purge_state.selected_paths = self
                .project_purge_state
                .artifacts
                .iter()
                .map(|a| a.path.clone())
                .collect();
            ctx.request_repaint();
        }

        if let Ok(sections) = self.developer_scan_rx.try_recv() {
            self.developer_state.is_scanning = false;
            self.developer_state.sections = sections;
            ctx.request_repaint();
        }

        if let Ok(groups) = self.duplicates_scan_rx.try_recv() {
            self.duplicates_state.is_scanning = false;
            self.duplicates_state.groups = groups;
            ctx.request_repaint();
        }

        if let Ok(files) = self.large_files_scan_rx.try_recv() {
            self.large_files_state.is_scanning = false;
            self.large_files_state.files = files;
            ctx.request_repaint();
        }

        if let Ok(report) = self.downloads_scan_rx.try_recv() {
            self.downloads_state.is_scanning = false;
            self.downloads_state.report = Some(report);
            ctx.request_repaint();
        }

        if let Ok((diags, snaps)) = self.doctor_scan_rx.try_recv() {
            self.doctor_state.is_running = false;
            self.doctor_state.diagnostics = diags;
            self.doctor_state.snapshots = snaps;
            ctx.request_repaint();
        }

        if let Ok(status) = self.update_check_rx.try_recv() {
            self.settings_state.is_checking_update = false;
            self.settings_state.update_status = Some(status);
            ctx.request_repaint();
        }

        if let Ok(res) = self.history_rx.try_recv() {
            self.history_state.is_loading = false;
            match res {
                Ok((ops, restorable)) => {
                    self.history_state.operations = ops;
                    self.history_state.restorable = restorable;
                }
                Err(e) => {
                    self.global_status = Some((e, true));
                }
            }
            ctx.request_repaint();
        }
    }

    fn handle_smart_clean_action(&mut self, action: SmartCleanAction, ctx: &egui::Context) {
        match action {
            SmartCleanAction::None => {}
            SmartCleanAction::TriggerScan {
                profile,
                include_trash,
                include_system_temp,
            } => {
                self.smart_clean_state.is_scanning = true;
                self.smart_clean_state.status_msg = "Scanning cleanup candidates...".into();
                let tx = self.clean_scan_tx.clone();
                let ctx_clone = ctx.clone();

                thread::spawn(move || {
                    let scanner = Scanner::new(Config::default());
                    let res = scanner.scan(
                        profile,
                        include_trash,
                        include_system_temp,
                        None,
                        |_, _, _| {},
                    );
                    let _ = tx.send(res.items);
                    ctx_clone.request_repaint();
                });
            }
            SmartCleanAction::StageClean(items) => {
                let plan = cleanup_plan("Smart Clean", &items);
                let token = AUTHORIZATION_MANAGER.issue_token("clean", &plan);
                self.review_modal.staged = Some(StagedPlan {
                    plan,
                    token,
                    ttl_seconds: 300,
                    cleanup_items: items,
                    app_target: None,
                    dev_target: None,
                });
                self.review_modal.is_open = true;
                self.review_modal.allow_extra_opt_in = false;
                self.review_modal.error_msg = None;
            }
        }
    }

    fn handle_app_uninstaller_action(&mut self, action: AppUninstallerAction, ctx: &egui::Context) {
        match action {
            AppUninstallerAction::None => {}
            AppUninstallerAction::RefreshApps => {
                self.app_uninstaller_state.is_loading = true;
                let tx = self.apps_scan_tx.clone();
                let ctx_clone = ctx.clone();

                thread::spawn(move || {
                    let apps = ApplicationManager::scan_applications(None);
                    let _ = tx.send(apps);
                    ctx_clone.request_repaint();
                });
            }
            AppUninstallerAction::StageUninstall { app, components } => {
                let plan = application_plan(&app, &components);
                let token = AUTHORIZATION_MANAGER.issue_token("apps", &plan);
                self.review_modal.staged = Some(StagedPlan {
                    plan,
                    token,
                    ttl_seconds: 300,
                    cleanup_items: Vec::new(),
                    app_target: Some(app),
                    dev_target: None,
                });
                self.review_modal.is_open = true;
                self.review_modal.allow_extra_opt_in = false;
                self.review_modal.error_msg = None;
            }
        }
    }

    fn handle_project_purge_action(&mut self, action: ProjectPurgeAction, ctx: &egui::Context) {
        match action {
            ProjectPurgeAction::None => {}
            ProjectPurgeAction::TriggerScan(paths) => {
                self.project_purge_state.is_scanning = true;
                self.project_purge_state.status_msg = "Scanning project build artifacts...".into();
                let tx = self.purge_scan_tx.clone();
                let ctx_clone = ctx.clone();

                thread::spawn(move || {
                    let artifacts = ProjectPurgeManager::scan_projects(&paths, None, |_, _| {});
                    let _ = tx.send(artifacts);
                    ctx_clone.request_repaint();
                });
            }
            ProjectPurgeAction::StagePurge(artifacts) => {
                let plan = purge_plan(&artifacts);
                let token = AUTHORIZATION_MANAGER.issue_token("purge", &plan);
                self.review_modal.staged = Some(StagedPlan {
                    plan,
                    token,
                    ttl_seconds: 300,
                    cleanup_items: Vec::new(),
                    app_target: None,
                    dev_target: None,
                });
                self.review_modal.is_open = true;
                self.review_modal.allow_extra_opt_in = false;
                self.review_modal.error_msg = None;
            }
        }
    }

    fn handle_developer_action(&mut self, action: DeveloperStorageAction, ctx: &egui::Context) {
        match action {
            DeveloperStorageAction::None => {}
            DeveloperStorageAction::TriggerScan => {
                self.developer_state.is_scanning = true;
                self.developer_state.status_msg = "Scanning developer environments...".into();
                let tx = self.developer_scan_tx.clone();
                let ctx_clone = ctx.clone();

                thread::spawn(move || {
                    let sections = DeveloperStorageCenter::scan_storage(None);
                    let _ = tx.send(sections);
                    ctx_clone.request_repaint();
                });
            }
            DeveloperStorageAction::StageClean(section) => {
                let plan = developer_plan(&section);
                let token = AUTHORIZATION_MANAGER.issue_token("developer", &plan);
                self.review_modal.staged = Some(StagedPlan {
                    plan,
                    token,
                    ttl_seconds: 300,
                    cleanup_items: Vec::new(),
                    app_target: None,
                    dev_target: Some(section),
                });
                self.review_modal.is_open = true;
                self.review_modal.allow_extra_opt_in = false;
                self.review_modal.error_msg = None;
            }
        }
    }

    fn handle_memory_action(&mut self, action: MemoryAction, ctx: &egui::Context) {
        match action {
            MemoryAction::None => {}
            MemoryAction::Refresh => {
                self.memory_state.is_refreshing = true;
                let tx = self.memory_tx.clone();
                let ctx_clone = ctx.clone();

                thread::spawn(move || {
                    let memory_service = MemoryService::default();
                    let procs = memory_service.snapshot();
                    let _ = tx.send(procs);
                    ctx_clone.request_repaint();
                });
            }
            MemoryAction::StageTerminate { proc, force } => {
                let plan = process_plan(&proc, force);
                let token = AUTHORIZATION_MANAGER.issue_token("memory", &plan);
                self.review_modal.staged = Some(StagedPlan {
                    plan,
                    token,
                    ttl_seconds: 300,
                    cleanup_items: Vec::new(),
                    app_target: None,
                    dev_target: None,
                });
                self.review_modal.is_open = true;
                self.review_modal.allow_extra_opt_in = false;
                self.review_modal.error_msg = None;
            }
        }
    }

    fn handle_treemap_action(&mut self, action: TreemapAction, ctx: &egui::Context) {
        match action {
            TreemapAction::None => {}
            TreemapAction::TriggerScan(path) => {
                self.treemap_state.is_scanning = true;
                self.treemap_state.scan_progress_msg = "Analyzing storage...".into();
                let tx = self.treemap_tx.clone();
                let ctx_clone = ctx.clone();

                thread::spawn(move || {
                    let result = IncrementalAnalyzer::analyze(&path, 100, 0, None, |_, _, _| {})
                        .map(|report| {
                            if !report.tree.children.is_empty() {
                                report.tree.children
                            } else {
                                report.top_items
                            }
                        });
                    let _ = tx.send(result);
                    ctx_clone.request_repaint();
                });
            }
            TreemapAction::StageTrash(path, bytes) => {
                let plan = analyzer_trash_plan(&[path], bytes);
                let token = AUTHORIZATION_MANAGER.issue_token("analyzer", &plan);
                self.review_modal.staged = Some(StagedPlan {
                    plan,
                    token,
                    ttl_seconds: 300,
                    cleanup_items: Vec::new(),
                    app_target: None,
                    dev_target: None,
                });
                self.review_modal.is_open = true;
                self.review_modal.allow_extra_opt_in = false;
                self.review_modal.error_msg = None;
            }
        }
    }

    fn handle_duplicates_action(&mut self, action: DuplicateAction, ctx: &egui::Context) {
        match action {
            DuplicateAction::None => {}
            DuplicateAction::TriggerScan { paths, min_bytes } => {
                self.duplicates_state.is_scanning = true;
                self.duplicates_state.status_msg = "Scanning duplicate files...".into();
                let tx = self.duplicates_scan_tx.clone();
                let ctx_clone = ctx.clone();

                thread::spawn(move || {
                    let groups =
                        DuplicateFinder::find_duplicates(&paths, min_bytes, None, |_, _| {});
                    let _ = tx.send(groups);
                    ctx_clone.request_repaint();
                });
            }
            DuplicateAction::StageTrash(paths, bytes) => {
                let plan = duplicate_trash_plan(&paths, bytes);
                let token = AUTHORIZATION_MANAGER.issue_token("duplicates", &plan);
                self.review_modal.staged = Some(StagedPlan {
                    plan,
                    token,
                    ttl_seconds: 300,
                    cleanup_items: Vec::new(),
                    app_target: None,
                    dev_target: None,
                });
                self.review_modal.is_open = true;
                self.review_modal.allow_extra_opt_in = false;
                self.review_modal.error_msg = None;
            }
        }
    }

    fn handle_large_files_action(&mut self, action: LargeFilesAction, ctx: &egui::Context) {
        match action {
            LargeFilesAction::None => {}
            LargeFilesAction::TriggerScan {
                paths,
                min_bytes,
                older_than_days,
            } => {
                self.large_files_state.is_scanning = true;
                self.large_files_state.status_msg = "Scanning large & old files...".into();
                let tx = self.large_files_scan_tx.clone();
                let ctx_clone = ctx.clone();

                thread::spawn(move || {
                    let files = LargeOldFileScanner::scan(
                        &paths,
                        min_bytes,
                        older_than_days,
                        None,
                        |_, _| {},
                    );
                    let _ = tx.send(files);
                    ctx_clone.request_repaint();
                });
            }
            LargeFilesAction::StageTrash(paths, bytes) => {
                let plan = large_files_trash_plan(&paths, bytes);
                let token = AUTHORIZATION_MANAGER.issue_token("large-files", &plan);
                self.review_modal.staged = Some(StagedPlan {
                    plan,
                    token,
                    ttl_seconds: 300,
                    cleanup_items: Vec::new(),
                    app_target: None,
                    dev_target: None,
                });
                self.review_modal.is_open = true;
                self.review_modal.allow_extra_opt_in = false;
                self.review_modal.error_msg = None;
            }
        }
    }

    fn handle_downloads_action(&mut self, action: SmartDownloadsAction, ctx: &egui::Context) {
        match action {
            SmartDownloadsAction::None => {}
            SmartDownloadsAction::TriggerScan(older_than_days) => {
                self.downloads_state.is_scanning = true;
                self.downloads_state.status_msg = "Classifying Downloads folder...".into();
                let tx = self.downloads_scan_tx.clone();
                let ctx_clone = ctx.clone();

                thread::spawn(move || {
                    let report = SmartDownloadsScanner::scan(older_than_days, None);
                    let _ = tx.send(report);
                    ctx_clone.request_repaint();
                });
            }
            SmartDownloadsAction::StageTrash(paths, bytes) => {
                let plan = downloads_trash_plan(&paths, bytes);
                let token = AUTHORIZATION_MANAGER.issue_token("downloads", &plan);
                self.review_modal.staged = Some(StagedPlan {
                    plan,
                    token,
                    ttl_seconds: 300,
                    cleanup_items: Vec::new(),
                    app_target: None,
                    dev_target: None,
                });
                self.review_modal.is_open = true;
                self.review_modal.allow_extra_opt_in = false;
                self.review_modal.error_msg = None;
            }
        }
    }

    fn handle_doctor_action(&mut self, action: DoctorAction, ctx: &egui::Context) {
        match action {
            DoctorAction::None => {}
            DoctorAction::RunDiagnostics => {
                self.doctor_state.is_running = true;
                let tx = self.doctor_scan_tx.clone();
                let ctx_clone = ctx.clone();

                thread::spawn(move || {
                    let diags = Doctor::run_diagnostics();
                    let snaps = SnapshotManager::list_snapshots();
                    let _ = tx.send((diags, snaps));
                    ctx_clone.request_repaint();
                });
            }
            DoctorAction::StageThinSnapshots(target_gb) => {
                let plan = snapshot_plan(target_gb);
                let token = AUTHORIZATION_MANAGER.issue_token("snapshots", &plan);
                self.review_modal.staged = Some(StagedPlan {
                    plan,
                    token,
                    ttl_seconds: 300,
                    cleanup_items: Vec::new(),
                    app_target: None,
                    dev_target: None,
                });
                self.review_modal.is_open = true;
                self.review_modal.allow_extra_opt_in = true;
                self.review_modal.error_msg = None;
            }
        }
    }

    fn handle_history_action(&mut self, action: HistoryAction, ctx: &egui::Context) {
        match action {
            HistoryAction::None => {}
            HistoryAction::Refresh => {
                self.history_state.is_loading = true;
                let tx = self.history_tx.clone();
                let ctx_clone = ctx.clone();
                thread::spawn(move || {
                    let logger = macmaid_core::reporting::AuditLogger::default();
                    let ops = logger.read_history(100);
                    let restorable = macmaid_core::recovery::RecoveryCenter::list_restorable(100);
                    let _ = tx.send(Ok((ops, restorable)));
                    ctx_clone.request_repaint();
                });
            }
            HistoryAction::Restore {
                trash_path,
                original_path,
            } => {
                let tx = self.action_tx.clone();
                let hist_tx = self.history_tx.clone();
                let ctx_clone = ctx.clone();
                thread::spawn(move || {
                    match macmaid_core::recovery::RecoveryCenter::restore(
                        &trash_path,
                        &original_path,
                        false,
                    ) {
                        Ok(_) => {
                            let _ = tx.send(Ok(format!(
                                "Successfully restored {}",
                                original_path.display()
                            )));
                            let logger = macmaid_core::reporting::AuditLogger::default();
                            let ops = logger.read_history(100);
                            let restorable =
                                macmaid_core::recovery::RecoveryCenter::list_restorable(100);
                            let _ = hist_tx.send(Ok((ops, restorable)));
                        }
                        Err(e) => {
                            let _ = tx.send(Err(format!("Restore failed: {e}")));
                        }
                    }
                    ctx_clone.request_repaint();
                });
            }
        }
    }

    fn handle_settings_action(&mut self, action: SettingsAction, ctx: &egui::Context) {
        match action {
            SettingsAction::None => {}
            SettingsAction::CheckUpdates => {
                self.settings_state.is_checking_update = true;
                let tx = self.update_check_tx.clone();
                let ctx_clone = ctx.clone();

                thread::spawn(move || {
                    let status = check_update_status();
                    let _ = tx.send(status);
                    ctx_clone.request_repaint();
                });
            }
            SettingsAction::AddWhitelistRule(rule) => {
                let config = Config::default();
                let _ = config.add_rule(&rule);
                self.settings_state.whitelist_rules = config.patterns(false).unwrap_or_default();
                self.global_status = Some((format!("Added whitelist rule: {rule}"), false));
            }
            SettingsAction::RemoveWhitelistRule(rule) => {
                let config = Config::default();
                let _ = config.remove_rule(&rule);
                self.settings_state.whitelist_rules = config.patterns(false).unwrap_or_default();
                self.global_status = Some((format!("Removed whitelist rule: {rule}"), false));
            }
        }
    }

    fn handle_modal_action(&mut self, modal_action: ModalAction, ctx: &egui::Context) {
        match modal_action {
            ModalAction::None => {}
            ModalAction::Cancel => {
                self.review_modal.is_open = false;
                self.review_modal.staged = None;
            }
            ModalAction::Confirm {
                scope,
                token,
                allow_extra,
            } => {
                if let Some(staged) = self.review_modal.staged.take() {
                    let plan = staged.plan.clone();
                    self.review_modal.is_open = false;

                    // Execute with Authorization Token Validation
                    let tx = self.action_tx.clone();
                    let ctx_clone = ctx.clone();
                    thread::spawn(move || {
                        let cleaner = Cleaner::default();
                        match scope.as_str() {
                            "clean" => {
                                match cleaner.execute_authorized(
                                    &scope,
                                    &token,
                                    &plan,
                                    &staged.cleanup_items,
                                    allow_extra,
                                    |_, _, _, _| {},
                                ) {
                                    Ok(res) => {
                                        let _ = tx.send(Ok(format!(
                                            "Cleaned {} items ({} reclaimed).",
                                            staged.cleanup_items.len(),
                                            macmaid_core::system::human_bytes(res.freed)
                                        )));
                                    }
                                    Err(e) => {
                                        let _ = tx.send(Err(format!("Clean error: {e}")));
                                    }
                                }
                            }
                            "apps" => {
                                if let Err(e) = AUTHORIZATION_MANAGER.validate_and_consume(
                                    &scope,
                                    &token,
                                    &plan,
                                    allow_extra,
                                ) {
                                    let _ = tx.send(Err(format!("Authorization denied: {e}")));
                                    ctx_clone.request_repaint();
                                    return;
                                }

                                if let Some(ref app) = staged.app_target {
                                    let comp_paths: Vec<String> = plan
                                        .items
                                        .iter()
                                        .filter(|it| !it.user_data || allow_extra)
                                        .map(|it| it.target.clone())
                                        .collect();

                                    match ApplicationManager::uninstall_app(
                                        app,
                                        &comp_paths,
                                        &cleaner,
                                    ) {
                                        Ok(count) => {
                                            let _ = tx.send(Ok(format!(
                                                "Successfully uninstalled {} ({} components removed).",
                                                app.name, count
                                            )));
                                        }
                                        Err(e) => {
                                            let _ = tx.send(Err(format!("Uninstall error: {e}")));
                                        }
                                    }
                                } else {
                                    let _ = tx.send(Err(
                                        "No application target found for uninstallation".into(),
                                    ));
                                }
                            }
                            "developer" => {
                                if let Err(e) = AUTHORIZATION_MANAGER.validate_and_consume(
                                    &scope,
                                    &token,
                                    &plan,
                                    allow_extra,
                                ) {
                                    let _ = tx.send(Err(format!("Authorization denied: {e}")));
                                    ctx_clone.request_repaint();
                                    return;
                                }

                                if let Some(ref sec) = staged.dev_target {
                                    match DeveloperStorageCenter::clean_section(sec, &cleaner) {
                                        Ok(count) => {
                                            let _ = tx.send(Ok(format!(
                                                "Successfully cleaned {} ({} items removed).",
                                                sec.name, count
                                            )));
                                        }
                                        Err(e) => {
                                            let _ =
                                                tx.send(Err(format!("Developer clean error: {e}")));
                                        }
                                    }
                                } else {
                                    let _ =
                                        tx.send(Err("No developer target section found".into()));
                                }
                            }
                            "purge" => {
                                if let Err(e) = AUTHORIZATION_MANAGER.validate_and_consume(
                                    &scope,
                                    &token,
                                    &plan,
                                    allow_extra,
                                ) {
                                    let _ = tx.send(Err(format!("Authorization denied: {e}")));
                                    ctx_clone.request_repaint();
                                    return;
                                }

                                let mut purged = 0;
                                let mut last_err = None;
                                for it in &plan.items {
                                    let p = PathBuf::from(&it.target);
                                    match cleaner.move_reviewed_item_to_trash(
                                        &p,
                                        ProjectPurgeManager::validate_project_artifact,
                                        Some(it.estimated_bytes),
                                    ) {
                                        Ok(_) => purged += 1,
                                        Err(e) => last_err = Some(e),
                                    }
                                }
                                if purged > 0 || last_err.is_none() {
                                    let _ = tx.send(Ok(format!(
                                        "Purged {purged} project artifacts to ~/.Trash."
                                    )));
                                } else {
                                    let _ = tx.send(Err(format!(
                                        "Failed to purge artifacts: {}",
                                        last_err.unwrap_or_else(|| "Unknown error".into())
                                    )));
                                }
                            }
                            "analyzer" | "duplicates" | "large-files" | "downloads" => {
                                if let Err(e) = AUTHORIZATION_MANAGER.validate_and_consume(
                                    &scope,
                                    &token,
                                    &plan,
                                    allow_extra,
                                ) {
                                    let _ = tx.send(Err(format!("Authorization denied: {e}")));
                                    ctx_clone.request_repaint();
                                    return;
                                }

                                let mut trashed = 0;
                                let mut last_err = None;
                                for it in &plan.items {
                                    let p = PathBuf::from(&it.target);
                                    match cleaner
                                        .move_analyzer_item_to_trash(&p, Some(it.estimated_bytes))
                                    {
                                        Ok(_) => trashed += 1,
                                        Err(e) => last_err = Some(e),
                                    }
                                }
                                if trashed > 0 || last_err.is_none() {
                                    let _ = tx.send(Ok(format!("Moved {trashed} items to Trash.")));
                                } else {
                                    let _ = tx.send(Err(format!(
                                        "Failed to move items to Trash: {}",
                                        last_err.unwrap_or_else(|| "Unknown error".into())
                                    )));
                                }
                            }
                            "memory" => {
                                if let Err(e) = AUTHORIZATION_MANAGER.validate_and_consume(
                                    &scope,
                                    &token,
                                    &plan,
                                    allow_extra,
                                ) {
                                    let _ = tx.send(Err(format!("Authorization denied: {e}")));
                                    ctx_clone.request_repaint();
                                    return;
                                }

                                if let Some(item) = plan.items.first() {
                                    let pid: u32 = item
                                        .key
                                        .split(':')
                                        .next()
                                        .and_then(|s| s.parse().ok())
                                        .unwrap_or(0);
                                    let start_time: Option<u64> =
                                        item.key.split(':').nth(1).and_then(|s| s.parse().ok());
                                    let force = item.action.contains("SIGKILL");

                                    let mem_service = MemoryService::default();
                                    match mem_service
                                        .terminate_process_checked(pid, start_time, force)
                                    {
                                        Ok(_) => {
                                            let _ = tx
                                                .send(Ok(format!("Terminated process PID {pid}")));
                                        }
                                        Err(e) => {
                                            let _ = tx.send(Err(format!(
                                                "Failed to terminate process: {e}"
                                            )));
                                        }
                                    }
                                }
                            }
                            "snapshots" => {
                                if let Err(e) = AUTHORIZATION_MANAGER.validate_and_consume(
                                    &scope,
                                    &token,
                                    &plan,
                                    allow_extra,
                                ) {
                                    let _ = tx.send(Err(format!("Authorization denied: {e}")));
                                    ctx_clone.request_repaint();
                                    return;
                                }

                                let target_bytes = plan.total_bytes;
                                match SnapshotManager::thin_snapshots(target_bytes, &cleaner) {
                                    Ok(res) => {
                                        let delta =
                                            res.observed_free_bytes_delta.unwrap_or(0).max(0)
                                                as u64;
                                        let _ = tx.send(Ok(format!(
                                            "Thinned snapshots ({} reclaimed).",
                                            macmaid_core::system::human_bytes(delta)
                                        )));
                                    }
                                    Err(e) => {
                                        let _ =
                                            tx.send(Err(format!("Failed to thin snapshots: {e}")));
                                    }
                                }
                            }
                            _ => {
                                let _ = tx.send(Ok("Action executed".into()));
                            }
                        }
                        ctx_clone.request_repaint();
                    });
                }
            }
        }
    }
}
