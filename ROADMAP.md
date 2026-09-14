# MacMaid Roadmap

## Hedef

MacMaid'i güvenli, şeffaf ve geliştirici odaklı bir macOS storage management aracına dönüştürmek.

Temel ilkeler: safety first; destructive işlemden önce preview ve confirmation; mümkünse Trash; user data için otomatik silme yok; her işlem history'ye yazılır; dry-run desteklenir; gerçek reclaim mümkün olduğunca ölçülür.

## Teslim Kuralı

Her feature şu parçaların tamamı bitmeden tamamlanmış sayılmaz ve sonraki büyük feature'a geçilmez:

```text
Backend · Safety · Tests · TUI · Web UI · Documentation
```

Her uzun tarama cancellable, non-blocking ve incremental olmalı; recursive symlink takibi yapmamalıdır. Her cleanup modülü dry-run, preview, history, error handling ve test desteği sunmalıdır.

## Sürümler

### 0.9.17 — Recovery / Undo Center

- [x] Her işlem için `operation_id`, `original_path`, `trash_path`, `timestamp`, `size`, `restorable` sakla.
- [x] Restore, Restore as copy ve conflict detection ekle.
- [x] Cleanup history ile bütünleştir.
- [x] Package manager işlemlerini `Not Restorable` göster.

### 0.9.18 — Duplicate File Finder

- [x] Byte-for-byte eşleşmeyi `size → partial hash → full hash → confirmation` sırasıyla doğrula.
- [x] Hardlink ve aynı inode'u duplicate sayma; APFS clone durumunu dikkate al.
- [x] Dosyaları otomatik seçme; silmeden önce review zorunlu olsun.

### 0.9.19 — Large & Old Files

- [x] `>500 MB`, `>1 GB`, `>5 GB`, `>10 GB` boyut filtreleri ekle.
- [x] `30/90/180 gün` ve `1 yıl` yaş filtreleri ekle.
- [x] Large files, Old files, Archives, Videos, Disk images ve Downloads kategorilerini göster.
- [x] User dosyalarını otomatik seçme.

### 0.9.19 — Smart Downloads

- [x] Downloads içinde `.dmg`, `.pkg`, `.xip`, `.iso`, `.ipsw`, `.zip`, `.rar`, `.7z`, `.crdownload`, `.download`, `.part` tara.
- [x] Installers, Archives, Old Downloads, Incomplete Downloads ve Duplicates olarak sınıflandır.
- [x] Documents, photos ve source code'u otomatik junk sayma.

### 0.9.20 — Developer Storage Center

- [x] Xcode: DerivedData, ModuleCache, DeviceSupport, Simulators, Archives.
- [x] Node.js: npm cache, pnpm store, yarn cache, node_modules, old runtimes.
- [x] Python: uv cache, pip cache, pipx, Poetry, Conda, virtualenvs.
- [x] Rust: Cargo cache, target directories, toolchains.
- [x] Android storage görünümü ekle.
- [x] Docker: Images, Containers, Volumes, Build Cache göster; volumes otomatik silinmesin.

### 0.9.21 — Browser Storage Inspector

- [x] Safari, Chrome, Chromium, Brave, Edge, Firefox ve Arc destekle.
- [x] Cache, Code Cache, GPU Cache, Service Workers, IndexedDB, Local Storage, Cookies ve Sessions alanlarını ayrı göster.
- [x] Smart Clean yalnız güvenli cache alanlarını temizlesin.
- [x] Cookies, sessions ve diğer user data otomatik seçilmesin.

### 0.9.22 — Storage Treemap

- [x] Existing Disk Analyzer backend'ini kullanan interactive Web UI treemap ekle.
- [x] Folder size, percentage ve file count göster.
- [x] Drill-down, back navigation, Open in Finder ve cleanup candidate review ekle.

### 0.9.23 — Diagnostic Reports

- [ ] Storage Report, Cleanup Report, System Health, Developer Storage ve Applications export'u ekle.
- [ ] Markdown ve JSON formatlarını destekle.
- [ ] Privacy-safe export seçeneği ekle.

## Global Safety Contract

Tüm destructive işlemler yalnız ortak pipeline üzerinden yürür:

```text
Discover
→ Classify
→ Calculate Size
→ PathSafety
→ Whitelist
→ Preview
→ Confirmation
→ Execute
→ Verify
→ History
```

Classification:

```text
SAFE_CACHE · REGENERATABLE · APPLICATION_LEFTOVER · DEVELOPER_CACHE
DOWNLOAD · DUPLICATE · USER_DATA · SYSTEM_DATA · UNKNOWN
```

Risk:

```text
LOW · MEDIUM · HIGH · BLOCKED
```

Şunlar asla otomatik silinmez: Documents, Pictures, Movies, Music, Docker Volumes, project source files, browser cookies, browser sessions ve unknown files.

## Öncelik

```text
1. Recovery Center
2. Duplicate Finder
3. Large & Old Files
4. Smart Downloads
5. Developer Storage Center
6. Browser Storage Inspector
7. Storage Treemap
8. Diagnostic Reports
9. Security Audit
10. v1.0 Release
```
