#ifndef MACMAID_FFI_H
#define MACMAID_FFI_H

#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Memory cleanup
void macmaid_free_string(char *ptr);

// Cancellation
typedef struct CancellationToken CancellationToken;
CancellationToken *macmaid_cancellation_token_new(void);
void macmaid_cancellation_token_cancel(CancellationToken *token);
void macmaid_cancellation_token_free(CancellationToken *token);

// Diagnostics & System Health
char *macmaid_run_diagnostics(void);
char *macmaid_get_system_health(void);

// Smart Clean
typedef void (*ScanProgressCallback)(size_t percent, const char *phase, const char *path, void *user_data);
typedef void (*CleanProgressCallback)(size_t index, size_t total, const char *label, const char *outcome, void *user_data);

char *macmaid_scan(
    const char *profile,
    bool include_trash,
    bool include_temp,
    CancellationToken *token,
    ScanProgressCallback callback,
    void *user_data
);

char *macmaid_execute_clean(
    const char *items_json,
    bool apply,
    bool allow_manual,
    CancellationToken *token,
    CleanProgressCallback callback,
    void *user_data
);

// Disk Analyzer
typedef void (*AnalyzerProgressCallback)(size_t count, const char *path, void *user_data);

char *macmaid_analyze_directory(
    const char *path,
    size_t top_limit,
    uint64_t min_size,
    CancellationToken *token,
    AnalyzerProgressCallback callback,
    void *user_data
);

char *macmaid_move_analyzer_item_to_trash(const char *path, uint64_t estimated_bytes);

// App Uninstaller
char *macmaid_scan_applications(CancellationToken *token);
char *macmaid_scan_app_components(const char *bundle_id);
char *macmaid_uninstall_application(const char *app_json, const char *components_json);

// Memory Management
char *macmaid_memory_snapshot(void);
char *macmaid_terminate_process(uint32_t pid);

// Developer Storage
char *macmaid_developer_storage(CancellationToken *token);
char *macmaid_developer_clean(const char *section_json);

// Duplicates, Large Files & Downloads
typedef void (*DuplicateProgressCallback)(size_t count, const char *path, void *user_data);

char *macmaid_find_duplicates(
    const char *paths_json,
    uint64_t min_size,
    CancellationToken *token,
    DuplicateProgressCallback callback,
    void *user_data
);

char *macmaid_large_files(const char *paths_json, uint64_t min_size, uint64_t older_than_days, CancellationToken *token);
char *macmaid_smart_downloads(uint64_t older_than_days, CancellationToken *token);

// Project Purge
char *macmaid_purge_scan(const char *paths_json, CancellationToken *token);
char *macmaid_purge_item(const char *artifact_json);

// History & Restore
char *macmaid_read_history(size_t limit);
char *macmaid_list_restorable(size_t limit);
char *macmaid_restore_trash_item(const char *trash_path, const char *orig_path, bool allow_copy);

// Whitelist & Settings
char *macmaid_load_whitelist(void);
char *macmaid_add_whitelist_rule(const char *rule);
char *macmaid_remove_whitelist_rule(const char *rule);
char *macmaid_load_settings(void);
char *macmaid_save_settings(const char *settings_json);
char *macmaid_translate(const char *key, const char *lang);

#ifdef __cplusplus
}
#endif

#endif // MACMAID_FFI_H
