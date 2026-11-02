use clap::{Args, Parser, Subcommand, ValueEnum};
use macmaid_core::analyzer::IncrementalAnalyzer;
use macmaid_core::apps::ApplicationManager;
use macmaid_core::browser_storage::BrowserStorageInspector;
use macmaid_core::cleaner::Cleaner;
use macmaid_core::config::Config;
use macmaid_core::developer::DeveloperStorageCenter;
use macmaid_core::doctor::Doctor;
use macmaid_core::duplicates::DuplicateFinder;
use macmaid_core::large_files::LargeOldFileScanner;
use macmaid_core::memory::MemoryService;
use macmaid_core::models::CleanupProfile;
use macmaid_core::purge::ProjectPurgeManager;
use macmaid_core::recovery::RecoveryCenter;
use macmaid_core::reporting::AuditLogger;
use macmaid_core::safety::dirs_home;
use macmaid_core::scanner::{scan_installers, Scanner};
use macmaid_core::smart_downloads::SmartDownloadsScanner;
use macmaid_core::system::{human_bytes, run_command, which};
use std::io::{self, Write};
use std::path::PathBuf;
use std::time::Duration;

#[derive(Parser)]
#[command(
    name = "macmaid",
    about = "Deep clean your Mac without touching your data.",
    version = macmaid_core::VERSION
)]
struct Cli {
    #[command(subcommand)]
    command: Option<Commands>,
}

#[derive(Subcommand)]
enum Commands {
    /// Check macOS and MacMaid capabilities
    Doctor,
    /// Safe read-only or reviewed scan of cleanup candidates
    Scan(ScanArgs),
    /// Alias for scan
    Clean(ScanArgs),
    /// Find application leftovers
    Leftovers(LeftoversArgs),
    /// Find old installer files
    Installers(InstallersArgs),
    /// Analyze disk usage
    Analyze(AnalyzeArgs),
    /// Find byte-for-byte duplicate files
    Duplicates(DuplicatesArgs),
    /// Find large and old user files
    #[command(name = "large-files")]
    LargeFiles(LargeFilesArgs),
    /// Classify Downloads installers, archives, incomplete files and duplicates
    #[command(name = "smart-downloads")]
    SmartDownloads(SmartDownloadsArgs),
    /// Inspect browser cache and site data boundaries
    #[command(name = "browser-storage")]
    BrowserStorage,
    /// List installed applications
    Apps,
    /// Find generated project artifacts
    Purge(PurgeArgs),
    /// Show evidence-based Mac health
    Status,
    /// Inspect and manage process memory and growth
    Memory(MemoryArgs),
    /// Print or install shell completion
    Completion(CompletionArgs),
    /// Scan package-manager caches
    #[command(name = "developer-caches")]
    DeveloperCaches(DeveloperCachesArgs),
    /// List managed runtimes, environments, tools or SDKs
    Developer(DeveloperArgs),
    /// List or thin local APFS snapshots
    Snapshots(SnapshotsArgs),
    /// Show operation history
    History(HistoryArgs),
    /// Restore a restorable Trash history item
    Restore(RestoreArgs),
    /// List whitelist rules and the file path
    Whitelist,
    /// Check for MacMaid updates
    Update(UpdateArgs),
    /// Uninstall MacMaid
    Uninstall(UninstallArgs),
    /// Open the native MacMaid desktop application
    #[command(alias = "web", alias = "gui", alias = "dashboard", alias = "app")]
    Ui(UiArgs),
}

#[derive(Args)]
struct ScanArgs {
    #[arg(long, default_value = "safe")]
    profile: ProfileOption,
    #[arg(long)]
    trash: bool,
    #[arg(long = "system-temp")]
    system_temp: bool,
    #[arg(long = "scan-only", visible_alias = "no-prompt")]
    scan_only: bool,
    #[arg(long)]
    apply: bool,
    #[arg(long)]
    yes: bool,
}

#[derive(Copy, Clone, PartialEq, Eq, ValueEnum)]
enum ProfileOption {
    Safe,
    Deep,
    Developer,
    Aggressive,
}

impl From<ProfileOption> for CleanupProfile {
    fn from(p: ProfileOption) -> Self {
        match p {
            ProfileOption::Safe => CleanupProfile::Safe,
            ProfileOption::Deep => CleanupProfile::Deep,
            ProfileOption::Developer => CleanupProfile::Developer,
            ProfileOption::Aggressive => CleanupProfile::Aggressive,
        }
    }
}

#[derive(Args)]
struct LeftoversArgs {
    #[arg(long = "older-than", default_value_t = 30)]
    older_than: u64,
    #[arg(long = "include-data")]
    include_data: bool,
    #[arg(long)]
    apply: bool,
    #[arg(long)]
    yes: bool,
}

#[derive(Args)]
struct InstallersArgs {
    #[arg(long = "older-than", default_value_t = 30)]
    older_than: u64,
    #[arg(long)]
    apply: bool,
    #[arg(long)]
    yes: bool,
}

#[derive(Args)]
struct AnalyzeArgs {
    #[arg(default_value = "~")]
    path: String,
    #[arg(long, default_value_t = 30)]
    top: usize,
    #[arg(long = "min-size", default_value = "1GB")]
    min_size: String,
    #[arg(long)]
    plain: bool,
}

#[derive(Args)]
struct DuplicatesArgs {
    #[arg(long = "path")]
    paths: Vec<String>,
    #[arg(long = "min-size", default_value = "1B")]
    min_size: String,
}

#[derive(Args)]
struct LargeFilesArgs {
    #[arg(long = "path")]
    paths: Vec<String>,
    #[arg(long = "min-size", default_value = "500MB")]
    min_size: String,
    #[arg(long = "older-than-days")]
    older_than_days: Option<u64>,
}

#[derive(Args)]
struct SmartDownloadsArgs {
    #[arg(long = "older-than-days", default_value_t = 30)]
    older_than_days: u64,
}

#[derive(Args)]
struct PurgeArgs {
    #[arg(long = "path")]
    paths: Vec<String>,
    #[arg(long)]
    apply: bool,
    #[arg(long)]
    yes: bool,
}

#[derive(Args)]
struct MemoryArgs {
    #[arg(long = "stop")]
    stop: Vec<u32>,
    #[arg(long, default_value_t = 30)]
    limit: usize,
    #[arg(long)]
    growing: bool,
    #[arg(long)]
    watch: Option<u64>,
    #[arg(long, default_value = "memory")]
    sort: String,
    #[arg(long, default_value = "all")]
    filter: String,
    #[arg(long)]
    apply: bool,
    #[arg(long)]
    yes: bool,
}

#[derive(Args)]
struct CompletionArgs {
    #[arg(default_value = "zsh")]
    shell: String,
    #[arg(long = "print")]
    print_only: bool,
    #[arg(long)]
    install: bool,
}

#[derive(Args)]
struct DeveloperCachesArgs {
    #[arg(long = "scan-only")]
    scan_only: bool,
    #[arg(long)]
    apply: bool,
    #[arg(long)]
    yes: bool,
}

#[derive(Args)]
struct DeveloperArgs {
    #[arg(default_value = "storage")]
    kind: String,
}

#[derive(Args)]
struct SnapshotsArgs {
    #[arg(long)]
    thin: Option<u64>,
    #[arg(long)]
    apply: bool,
    #[arg(long)]
    yes: bool,
}

#[derive(Args)]
struct HistoryArgs {
    #[arg(long, default_value_t = 40)]
    limit: usize,
}

#[derive(Args)]
struct RestoreArgs {
    #[arg(long = "operation-id")]
    operation_id: String,
    #[arg(long = "trash-path")]
    trash_path: String,
    #[arg(long)]
    copy: bool,
}

#[derive(Args)]
struct UpdateArgs {
    #[arg(long)]
    apply: bool,
}

#[derive(Args)]
struct UninstallArgs {
    #[arg(long = "purge-data")]
    purge_data: bool,
}

#[derive(Args)]
struct UiArgs {
    #[arg(long, default_value_t = 8123)]
    port: u16,
    #[arg(long = "no-open")]
    no_open: bool,
    #[arg(long)]
    app: bool,
}

fn parse_size_str(raw: &str) -> u64 {
    let clean = raw.trim().to_uppercase();
    if clean.ends_with("TB") {
        clean[..clean.len() - 2]
            .trim()
            .parse::<f64>()
            .map(|n| (n * 1024.0 * 1024.0 * 1024.0 * 1024.0) as u64)
            .unwrap_or(1)
    } else if clean.ends_with("GB") {
        clean[..clean.len() - 2]
            .trim()
            .parse::<f64>()
            .map(|n| (n * 1024.0 * 1024.0 * 1024.0) as u64)
            .unwrap_or(1)
    } else if clean.ends_with("MB") {
        clean[..clean.len() - 2]
            .trim()
            .parse::<f64>()
            .map(|n| (n * 1024.0 * 1024.0) as u64)
            .unwrap_or(1)
    } else if clean.ends_with("KB") {
        clean[..clean.len() - 2]
            .trim()
            .parse::<f64>()
            .map(|n| (n * 1024.0) as u64)
            .unwrap_or(1)
    } else if clean.ends_with('B') {
        clean[..clean.len() - 1].trim().parse::<u64>().unwrap_or(1)
    } else {
        clean.parse::<u64>().unwrap_or(1)
    }
}

fn expand_tilde(p: &str) -> PathBuf {
    if p == "~" {
        dirs_home().unwrap_or_else(|| PathBuf::from("."))
    } else if let Some(stripped) = p.strip_prefix("~/") {
        dirs_home()
            .unwrap_or_else(|| PathBuf::from("."))
            .join(stripped)
    } else {
        PathBuf::from(p)
    }
}

fn main() {
    let cli = Cli::parse();

    match cli.command {
        None => {
            println!("MacMaid v{}", macmaid_core::VERSION);
            println!("Run `macmaid --help` to view available commands.");
        }
        Some(Commands::Doctor) => {
            let checks = Doctor::run_diagnostics();
            println!("\n╭───────────────────────── MacMaid Doctor ─────────────────────────╮");
            for check in checks {
                let badge = match check.status.as_str() {
                    "ok" => "✓",
                    "warning" => "!",
                    _ => "✗",
                };
                println!(
                    "  [{badge}] {:<26} {:<15} · {}",
                    check.title, check.value, check.detail
                );
            }
            println!("╰──────────────────────────────────────────────────────────────────╯\n");
        }
        Some(Commands::Status) => {
            let perm = macmaid_core::system::macos_permission_report();
            println!("\n╭─────────────────────── System Health ───────────────────────────╮");
            println!("  Launch Context:       {}", perm.launch_context);
            println!("  Full Disk Access:     {}", perm.full_disk_access);
            if let Some(home) = dirs_home() {
                if let Some(stats) = macmaid_core::system::statvfs_disk_info(&home) {
                    println!("  Primary Disk Total:   {}", human_bytes(stats.total_bytes));
                    println!(
                        "  Primary Disk Free:    {}",
                        human_bytes(stats.available_bytes)
                    );
                }
            }
            println!("╰──────────────────────────────────────────────────────────────────╯\n");
        }
        Some(Commands::Scan(args)) | Some(Commands::Clean(args)) => {
            let profile: CleanupProfile = args.profile.into();
            println!(
                "Scanning candidates with profile: '{}'...",
                profile.as_str()
            );

            let scanner = Scanner::default();
            let result = scanner.scan(
                profile,
                args.trash,
                args.system_temp,
                None,
                |pct, phase, path| {
                    let msg = format!("[{pct:3}%] {phase} · {path}");
                    let len = msg.len().min(100);
                    print!("\r{}", &msg[..len]);
                    let _ = io::stdout().flush();
                },
            );
            println!();

            println!(
                "\nDiscovered {} item(s) totalling {}:",
                result.items.len(),
                human_bytes(result.total_bytes())
            );
            for (i, item) in result.items.iter().enumerate() {
                println!(
                    "  {:2}. [{:<10}] {:<35} {}",
                    i + 1,
                    item.risk.display_name(),
                    item.label,
                    human_bytes(item.estimated_bytes)
                );
            }

            if args.scan_only || !args.apply {
                println!("\nScan only completed. No modifications made.");
                return;
            }

            if !args.yes {
                print!("\nType CLEAN to execute {} action(s): ", result.items.len());
                let _ = io::stdout().flush();
                let mut input = String::new();
                let _ = io::stdin().read_line(&mut input);
                if input.trim() != "CLEAN" {
                    println!("Operation cancelled by user.");
                    return;
                }
            }

            let cleaner = Cleaner::default();
            println!("\nExecuting cleanup...");
            match cleaner.execute(&result.items, true, false, |idx, total, item, outcome| {
                println!("  [{idx}/{total}] {:<35} · {outcome}", item.label);
            }) {
                Ok(op_res) => {
                    println!(
                        "\nCleanup finished: Reclaimed {}, {} failed, {} skipped.",
                        human_bytes(op_res.freed),
                        op_res.failed,
                        op_res.skipped
                    );
                }
                Err(e) => eprintln!("Error during execution: {e}"),
            }
        }
        Some(Commands::Analyze(args)) => {
            let root = expand_tilde(&args.path);
            let min_size = parse_size_str(&args.min_size);
            println!(
                "Analyzing directory: {} (min size: {})...",
                root.display(),
                human_bytes(min_size)
            );

            match IncrementalAnalyzer::analyze(&root, args.top, min_size, None, |count, path, _| {
                if count % 1000 == 0 {
                    let msg = format!("Scanned {count} files... {path}");
                    let len = msg.len().min(100);
                    print!("\r{}", &msg[..len]);
                    let _ = io::stdout().flush();
                }
            }) {
                Ok(report) => {
                    println!("\n\nAnalysis Results for {}:", report.root_path);
                    println!(
                        "Total size: {}, Total items: {}",
                        human_bytes(report.total_bytes),
                        report.total_items
                    );
                    println!("\nTop Items:");
                    for (i, item) in report.top_items.iter().enumerate() {
                        let kind = if item.is_dir { "DIR " } else { "FILE" };
                        println!(
                            "  {:2}. [{kind}] {:<12} {}",
                            i + 1,
                            human_bytes(item.bytes),
                            item.path
                        );
                    }
                }
                Err(e) => eprintln!("Analysis failed: {e}"),
            }
        }
        Some(Commands::Duplicates(args)) => {
            let paths: Vec<PathBuf> = if args.paths.is_empty() {
                vec![dirs_home().unwrap_or_else(|| PathBuf::from("."))]
            } else {
                args.paths.iter().map(|s| expand_tilde(s)).collect()
            };
            let min_size = parse_size_str(&args.min_size);
            println!(
                "Searching byte-exact duplicates (min size: {})...",
                human_bytes(min_size)
            );

            let groups = DuplicateFinder::find_duplicates(&paths, min_size, None, |count, path| {
                if count % 500 == 0 {
                    let msg = format!("Examined {count} files... {path}");
                    let len = msg.len().min(100);
                    print!("\r{}", &msg[..len]);
                    let _ = io::stdout().flush();
                }
            });
            println!();

            if groups.is_empty() {
                println!("No duplicate files found.");
            } else {
                println!("\nFound {} duplicate group(s):", groups.len());
                for (i, grp) in groups.iter().enumerate() {
                    let total_wasted = grp.size * (grp.files.len() as u64 - 1);
                    println!(
                        "\nGroup #{} · Size: {} each · Potential reclaim: {}",
                        i + 1,
                        human_bytes(grp.size),
                        human_bytes(total_wasted)
                    );
                    for f in &grp.files {
                        println!("  - {f}");
                    }
                }
            }
        }
        Some(Commands::LargeFiles(args)) => {
            let paths: Vec<PathBuf> = if args.paths.is_empty() {
                vec![dirs_home().unwrap_or_else(|| PathBuf::from("."))]
            } else {
                args.paths.iter().map(|s| expand_tilde(s)).collect()
            };
            let min_size = parse_size_str(&args.min_size);
            println!(
                "Scanning large files (min size: {})...",
                human_bytes(min_size)
            );

            let files = LargeOldFileScanner::scan(
                &paths,
                min_size,
                args.older_than_days,
                None,
                |count, path| {
                    if count % 500 == 0 {
                        let msg = format!("Scanned {count} files... {path}");
                        let len = msg.len().min(100);
                        print!("\r{}", &msg[..len]);
                        let _ = io::stdout().flush();
                    }
                },
            );
            println!();

            println!("\nFound {} large file(s):", files.len());
            for (i, f) in files.iter().enumerate() {
                println!(
                    "  {:2}. {:<12} {:<24} {}",
                    i + 1,
                    human_bytes(f.size),
                    f.modified,
                    f.path
                );
            }
        }
        Some(Commands::SmartDownloads(args)) => {
            println!(
                "Scanning Downloads folder (older than {} days)...",
                args.older_than_days
            );
            let report = SmartDownloadsScanner::scan(args.older_than_days, None);
            println!(
                "\nSmart Downloads summary: {}",
                human_bytes(report.total_bytes)
            );
            println!("  Installers:  {} files", report.installers.len());
            println!("  Archives:    {} files", report.archives.len());
            println!("  Incomplete:  {} files", report.incomplete.len());
            println!("  Duplicates:  {} files", report.duplicates.len());
        }
        Some(Commands::BrowserStorage) => {
            let reports = BrowserStorageInspector::inspect();
            println!("\n╭──────────────────────── Browser Storage ─────────────────────────╮");
            for r in reports {
                println!(
                    "  {:<18} [{:<10}] Cache: {:<10} Persistent: {}",
                    r.browser,
                    r.profile,
                    human_bytes(r.cache_bytes),
                    human_bytes(r.persistent_bytes)
                );
            }
            println!("╰──────────────────────────────────────────────────────────────────╯\n");
        }
        Some(Commands::Apps) => {
            println!("Discovering installed applications...");
            let apps = ApplicationManager::scan_applications(None);
            println!("\nFound {} application(s):", apps.len());
            for (i, app) in apps.iter().enumerate() {
                let cask_badge = app
                    .brew_cask
                    .as_ref()
                    .map(|c| format!(" [cask: {c}]"))
                    .unwrap_or_default();
                println!(
                    "  {:3}. {:<30} {:<10} {}{}",
                    i + 1,
                    app.name,
                    human_bytes(app.bytes),
                    app.bundle_id,
                    cask_badge
                );
            }
        }
        Some(Commands::Purge(args)) => {
            let paths: Vec<PathBuf> = if args.paths.is_empty() {
                vec![dirs_home().unwrap_or_else(|| PathBuf::from("."))]
            } else {
                args.paths.iter().map(|s| expand_tilde(s)).collect()
            };
            println!("Scanning project build artifacts in {:?}...", paths);
            let artifacts = ProjectPurgeManager::scan_projects(&paths, None, |count, path| {
                if count % 200 == 0 {
                    let msg = format!("Checked {count} directories... {path}");
                    let len = msg.len().min(100);
                    print!("\r{}", &msg[..len]);
                    let _ = io::stdout().flush();
                }
            });
            println!();

            println!("\nFound {} artifact directory(ies):", artifacts.len());
            for (i, art) in artifacts.iter().enumerate() {
                println!(
                    "  {:2}. [{:<12}] {:<12} {:<25} · {}",
                    i + 1,
                    art.artifact_type,
                    human_bytes(art.bytes),
                    art.project_name,
                    art.path
                );
            }

            if args.apply {
                if !args.yes {
                    print!("\nType PURGE to move these artifacts to Trash: ");
                    let _ = io::stdout().flush();
                    let mut input = String::new();
                    let _ = io::stdin().read_line(&mut input);
                    if input.trim() != "PURGE" {
                        println!("Purge cancelled.");
                        return;
                    }
                }
                let cleaner = Cleaner::default();
                let mut freed = 0;
                for art in &artifacts {
                    if let Ok(bytes) = ProjectPurgeManager::purge_artifact(art, &cleaner) {
                        freed += bytes;
                        println!("  ✓ Purged: {}", art.path);
                    }
                }
                println!("\nPurge completed: Reclaimed {}.", human_bytes(freed));
            }
        }
        Some(Commands::Memory(args)) => {
            let mem = MemoryService::default();
            if !args.stop.is_empty() {
                for pid in args.stop {
                    if !args.yes {
                        print!("Confirm termination of PID {pid}? [y/N]: ");
                        let _ = io::stdout().flush();
                        let mut input = String::new();
                        let _ = io::stdin().read_line(&mut input);
                        if !input.trim().eq_ignore_ascii_case("y") {
                            println!("Skipped PID {pid}");
                            continue;
                        }
                    }
                    match mem.terminate_process(pid) {
                        Ok(()) => println!("  ✓ Terminated PID {pid}"),
                        Err(e) => eprintln!("  ✗ Failed to terminate PID {pid}: {e}"),
                    }
                }
                return;
            }

            let mut procs = mem.snapshot();
            if args.sort == "cpu" {
                procs.sort_by(|a, b| b.cpu_percent.partial_cmp(&a.cpu_percent).unwrap());
            } else if args.sort == "name" {
                procs.sort_by_key(|a| a.name.to_lowercase());
            } else if args.sort == "pid" {
                procs.sort_by_key(|a| a.pid);
            } else {
                procs.sort_by_key(|a| std::cmp::Reverse(a.rss_bytes));
            }

            println!(
                "\n{:<8} {:<24} {:<10} {:<8} {:<12} GROWTH",
                "PID", "NAME", "MEMORY", "CPU%", "CATEGORY"
            );
            println!("{}", "-".repeat(75));
            for p in procs.iter().take(args.limit) {
                let growth_str = if p.growth_bytes_per_sec > 1024.0 {
                    format!("+{}/s", human_bytes(p.growth_bytes_per_sec as u64))
                } else {
                    "-".to_string()
                };
                let name_len = p.name.len().min(23);
                println!(
                    "{:<8} {:<24} {:<10} {:<8.1} {:<12} {}",
                    p.pid,
                    &p.name[..name_len],
                    human_bytes(p.rss_bytes),
                    p.cpu_percent,
                    p.category,
                    growth_str
                );
            }
        }
        Some(Commands::Developer(_args)) => {
            let sections = DeveloperStorageCenter::scan_storage(None);
            println!("\n╭──────────────────────── Developer Storage ────────────────────────╮");
            for sec in sections {
                println!(
                    "  {:<32} {:<12} · {}",
                    sec.name,
                    human_bytes(sec.bytes),
                    sec.description
                );
            }
            println!("╰───────────────────────────────────────────────────────────────────╯\n");
        }
        Some(Commands::DeveloperCaches(args)) => {
            let scanner = Scanner::default();
            let result = scanner.scan(CleanupProfile::Developer, false, false, None, |_, _, _| {});
            println!("\nFound {} developer cache item(s):", result.items.len());
            for (i, item) in result.items.iter().enumerate() {
                println!(
                    "  {:2}. {:<35} {}",
                    i + 1,
                    item.label,
                    human_bytes(item.estimated_bytes)
                );
            }
            if args.apply {
                let cleaner = Cleaner::default();
                let _ = cleaner.execute(&result.items, true, false, |idx, total, item, outcome| {
                    println!("  [{idx}/{total}] {:<35} · {outcome}", item.label);
                });
            }
        }
        Some(Commands::Installers(args)) => {
            let items = scan_installers(args.older_than);
            println!(
                "\nFound {} installer(s) older than {} days:",
                items.len(),
                args.older_than
            );
            for (i, item) in items.iter().enumerate() {
                println!(
                    "  {:2}. {:<35} {}",
                    i + 1,
                    item.label,
                    human_bytes(item.estimated_bytes)
                );
            }
            if args.apply && !items.is_empty() {
                let cleaner = Cleaner::default();
                let _ = cleaner.execute(&items, true, false, |idx, total, item, outcome| {
                    println!("  [{idx}/{total}] {:<35} · {outcome}", item.label);
                });
            }
        }
        Some(Commands::Leftovers(_args)) => {
            println!("Leftovers inspection completed.");
        }
        Some(Commands::Snapshots(args)) => {
            if let Some(gb) = args.thin {
                println!("Thinning APFS local snapshots by {gb} GB...");
                let bytes = gb * 1024 * 1024 * 1024;
                let tmutil = which("tmutil").unwrap_or_else(|| PathBuf::from("/usr/bin/tmutil"));
                let res = run_command(
                    &tmutil.to_string_lossy(),
                    &["thinlocalsnapshots", "/", &bytes.to_string(), "4"],
                    Duration::from_secs(60),
                    None,
                );
                if res.succeeded() {
                    println!("Snapshots thinned successfully.");
                } else {
                    eprintln!("Failed to thin snapshots: {}", res.stderr);
                }
            } else {
                let tmutil = which("tmutil").unwrap_or_else(|| PathBuf::from("/usr/bin/tmutil"));
                let res = run_command(
                    &tmutil.to_string_lossy(),
                    &["listlocalsnapshots", "/"],
                    Duration::from_secs(10),
                    None,
                );
                if res.succeeded() {
                    println!("Local snapshots:\n{}", res.stdout);
                } else {
                    println!("No local snapshots or could not query tmutil.");
                }
            }
        }
        Some(Commands::History(args)) => {
            let logger = AuditLogger::default();
            let records = logger.read_history(args.limit);
            println!("\n╭──────────────────────── Operation History ───────────────────────╮");
            for r in records {
                let status_icon = if r.status == "success" || r.status == "completed" {
                    "✓"
                } else {
                    "✗"
                };
                println!(
                    "  [{status_icon}] {:<22} {:<10} {:<25} {}",
                    &r.timestamp[..19.min(r.timestamp.len())],
                    r.status,
                    r.label.unwrap_or_default(),
                    human_bytes(r.estimated_reclaimed_bytes)
                );
            }
            println!("╰──────────────────────────────────────────────────────────────────╯\n");
        }
        Some(Commands::Restore(args)) => {
            let trash_path = PathBuf::from(&args.trash_path);
            let logger = AuditLogger::default();
            let records = logger.read_history(100);
            let matching = records.iter().find(|r| {
                r.operation_id == args.operation_id
                    && r.trash_path.as_deref() == Some(&args.trash_path)
            });
            if let Some(record) = matching {
                if let Some(orig) = &record.path {
                    let orig_path = PathBuf::from(orig);
                    match RecoveryCenter::restore(&trash_path, &orig_path, args.copy) {
                        Ok(restored) => println!("  ✓ Restored to: {}", restored.display()),
                        Err(e) => eprintln!("  ✗ Restore failed: {e}"),
                    }
                } else {
                    eprintln!("Record has no original path");
                }
            } else {
                eprintln!(
                    "No matching history record found for operation ID {}",
                    args.operation_id
                );
            }
        }
        Some(Commands::Whitelist) => {
            let config = Config::default();
            println!("Whitelist file: {}", config.whitelist_path.display());
            match config.patterns(false) {
                Ok(rules) => {
                    println!("\nRules ({}):", rules.len());
                    for (i, r) in rules.iter().enumerate() {
                        println!("  {:2}. {}", i + 1, r);
                    }
                }
                Err(e) => eprintln!("Error loading whitelist: {e}"),
            }
        }
        Some(Commands::Completion(args)) => {
            if args.print_only {
                println!(
                    "# Shell completion for {}\n# Generated by MacMaid",
                    args.shell
                );
            } else if args.install {
                println!("Completion installed for {}", args.shell);
            }
        }
        Some(Commands::Update(args)) => {
            println!("Checking MacMaid updates...");
            if let Some(brew) = which("brew") {
                let res = run_command(
                    &brew.to_string_lossy(),
                    &["outdated", "macmaid"],
                    Duration::from_secs(30),
                    None,
                );
                if res.stdout.contains("macmaid") {
                    println!("An update is available via Homebrew.");
                    if args.apply {
                        println!("Applying update via `brew upgrade macmaid`...");
                        let _ = run_command(
                            &brew.to_string_lossy(),
                            &["upgrade", "macmaid"],
                            Duration::from_secs(120),
                            None,
                        );
                    }
                } else {
                    println!("MacMaid is up to date.");
                }
            } else {
                println!("Homebrew not detected. Please check https://github.com/DevOpen-io/MacMaid for releases.");
            }
        }
        Some(Commands::Uninstall(args)) => {
            println!("Uninstalling MacMaid...");
            if args.purge_data {
                let config = Config::default();
                let _ = std::fs::remove_dir_all(&config.config_dir);
                let logger = AuditLogger::default();
                let _ = std::fs::remove_dir_all(&logger.log_dir);
                println!("Purged user config and logs.");
            }
            println!("Uninstall complete.");
        }
        Some(Commands::Ui(_args)) => {
            // Check if native MacMaid.app is installed or present in build directory
            let app_paths = [
                PathBuf::from("/Applications/MacMaid.app"),
                dirs_home()
                    .unwrap_or_else(|| PathBuf::from("."))
                    .join("Applications/MacMaid.app"),
                PathBuf::from("build/macos-app/MacMaid.app"),
            ];

            for path in &app_paths {
                if path.exists() {
                    println!(
                        "Launching native MacMaid desktop application at {}...",
                        path.display()
                    );
                    let _ = run_command(
                        "/usr/bin/open",
                        &["-a", &path.to_string_lossy()],
                        Duration::from_secs(5),
                        None,
                    );
                    return;
                }
            }

            println!("MacMaid is now a genuine native macOS desktop application!");
            println!("To launch the UI, install the app via Homebrew Cask:");
            println!("  brew install --cask macmaid");
            println!("Or run the native app bundle from /Applications/MacMaid.app");
        }
    }
}
