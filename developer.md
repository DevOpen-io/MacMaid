# MacMaid geliştirici kılavuzu

Bu belge, **bu çalışma ağacındaki** MacMaid uygulamasının geliştirici haritasıdır. Normatif güvenlik, test ve sürüm kuralları için önce [AGENTS.md](AGENTS.md) ve [CONTRIBUTING.md](CONTRIBUTING.md) okunmalıdır. Ayrıntılı güvenlik sınırları [SECURITY.md](SECURITY.md), paket yöneticisi fallback kararları [FALLBACK_POLICY.md](FALLBACK_POLICY.md), kullanıcı komutları [README.md](README.md) içindedir. Kodla çelişen tarihsel açıklamalar yerine ilgili modülün yürürlükteki davranışı esas alınır.

## 1. Kapsam ve çalışma ortamı

MacMaid macOS 13+ üzerinde Python 3.11+ ile çalışan, root olarak başlatılmayan bir temizlik, disk inceleme, uygulama kaldırma, geliştirici depolama ve süreç belleği gözlem aracıdır. Kaynak/dev kurulumu Intel ve Apple Silicon üzerinde çalışabilir; **mevcut DMG/Homebrew yayınları arm64** hedefler. SIP/TCC veya Full Disk Access engelleri atlanmaz; erişilemeyen hedefler raporlanır ya da işlem durdurulur. Çöp Kutusu'na taşıma alanı hemen boşaltmaz; taranan boyut, işlenen tahmin, tahmini geri kazanım ve dosya sistemi genelindeki serbest alan değişimi farklı ölçülerdir.

- Paket: `src/macmaid`; giriş noktası `macmaid = "macmaid.cli:main"` (`pyproject.toml`). Argümansız komut TUI'yi açar.
- Bağımlılıklar: `psutil>=7`, `textual>=6,<8`; `uv`/`uv.lock`, `uv_build`; dev grubunda pytest, Ruff, mypy; tarayıcı grubunda Playwright.
- Sunum: argparse CLI, Textual TUI, standart kütüphaneden `ThreadingHTTPServer` ile localhost API, build adımı olmayan HTML/CSS/vanilla JS Web UI. `src/macmaid/native/MacMaidApp.swift` Web arayüzünü yerel macOS penceresinde barındıran uygulama kabuğudur; bağımsız bir iş mantığı katmanı değildir.
- Web UI: `macmaid ui` varsayılan olarak `127.0.0.1:8123` üzerinde; `--port`, `--no-open`, `--app` seçenekleri vardır. `web`, `gui`, `dashboard`, `app` aynı komutun takma adlarıdır.

### Modül haritası

| Dosya | Sorumluluk |
|---|---|
| `models.py`, `config.py`, `safety.py`, `system.py` | Temel veri sözleşmeleri, kullanıcı ayarları/whitelist, yol kapıları, güvenli dosya/süreç/komut yardımcıları |
| `scanner.py`, `cleaner.py`, `reporting.py`, `review.py`, `cancellation.py` | Salt-okunur aday keşfi, ortak icra/audit, alan ölçüm raporu, inceleme planı/token, iptal |
| `analyzer.py`, `large_files.py`, `duplicates.py`, `smart_downloads.py`, `browser_storage.py` | Disk gezinme ve salt-okunur özel keşif akışları |
| `developer.py`, `features.py`, `memory.py` | Yöneticiye ait geliştirici kaynakları; uygulama/proje/sağlık/geçmiş/kurtarma; süreç izleme ve sinyal kapıları |
| `cli.py`, `tui.py`, `web.py`, `web_queries.py`, `web_mutations.py` | Ortak çekirdeği çağıran arayüz/HTTP adaptörleri; GET ve POST rotaları ayrı dosyalardadır |
| `i18n.py`, `WebUI/i18n.js`, `WebUI/icons.js` | TUI/CLI çeviri yardımcısı ve Web EN/TR kataloğu; ortak SF Symbols benzeri SVG kataloğu |
| `WebUI/app.js`, `api.js`, `ui.js`, `progress.js`, `memory.js`, `features/*.js`, `index.html`, `styles.css` | Web gezinmesi, API/review yardımcıları, ilerleme, Memory görünümü ve özellik görünümleri |

UI'larda yeni tarama/silme/ölçme kuralı yazılmaz. Ortak davranış önce çekirdekte eklenir; CLI/TUI/Web aynı hizmetleri kullanır. Çekirdek modüller UI modüllerini import etmez (HTTP rota adaptörlerinin `web.py` tip/handler bağlantısı hariç).

## 2. Güvenlik ve veri sözleşmesi

### Temizlik modeli

`models.py`:

- `RiskLevel`: `SAFE=0`, `MODERATE=1`, `AGGRESSIVE=2`, `MANUAL_ONLY=3`. `MANUAL_ONLY` otomatik seçilmez.
- `CleanupProfile`: `safe` (SAFE), `deep` (MODERATE), `developer` (MODERATE + geliştirici), `aggressive` (AGGRESSIVE + geliştirici). Çöp Kutusu ve sistem geçicileri profilin zorunlu parçası değildir; taramada ayrı bayraklarla etkinleştirilir.
- `ActionType`: `REMOVE_PATH`, `REMOVE_CHILDREN`, `COMMAND`, `COMMAND_WITH_CACHE_FALLBACK`, `MANUAL_CACHE_FALLBACK`, `MOVE_TO_TRASH`. Adında fallback geçen komut **başarısızsa kendiliğinden ham recursive silmeye dönmez**.
- `CleanupItem`: kategori, açıklama, hedef/komut, tahmini bayt, risk, gerekçe, aksiyon, gerekirse kapanması gereken uygulama, UUID kimliği. `ScanResult.status` `complete`/`partial`/`cancelled` olabilir; eksik tarama Web ve CLI temizleme isteği için uygun değildir.
- `OperationResult`: `freed` geriye uyumlu **tahmini geri kazanım** alanıdır; Trash taşımaları ve doğrulanamayan yönetici etkileri buna eklenmez. Ayrıca `scanned_estimated_bytes`, `processed_estimated_bytes`, `trash_moved_estimated_bytes`, `observed_free_bytes_delta`, `unknown_reclaim_count` ve ölçüm notları bulunur. APFS ve eşzamanlı disk etkinliği yüzünden serbest alan değişimi tek başına MacMaid'e atfedilemez.

### İşlem anındaki kapılar

`PathSafety` (`safety.py`) mutlak/lexical yolu doğrular; `..`, NUL, satır sonu ve symlink'li ataları reddeder. `/`, `/System`, `/bin`, `/sbin`, `/usr`, `/etc`, `/var`, `/private`, `/Library`, `/Applications`, `/Users`, `/Volumes` gibi korumalı köklerin kendisi silinemez. Normal cache silmede açıkça izinli ev dizini kökleri, dar sandbox (`Containers/<id>/Data/Library/Caches`) ve onaylı `Application Support` **cache yaprakları** geçerlidir; bütün `Application Support` silinmez. `/private/tmp` ve `/private/var/tmp` için ayrı dar yol denetimi vardır. `validate_trash_candidate()` Downloads/Desktop altındaki özel adayları, `validate_analyzer_candidate()` ev dizini altındaki kullanıcı dosyalarını sınırlar; analizör `~/Library`, ev dizini ankrajları, `.app` ve `.photoslibrary` paketleri ile başka kullanıcıya ait hedeflere dokunamaz.

`Config` (`config.py`): `~/.config/macmaid/{whitelist,preferences.json}`, `~/Library/Logs/MacMaid/operations.jsonl`; Memory ayarları `~/.config/macmaid/memory.json`. Tarama whitelist'i bir kez okuyarak keşif filtresi uygular; **icra sırasında** `require_unprotected()` whitelist'i tekrar, katı biçimde ve sahiplik/symlink kontrolüyle okur. İlgili dosya okunamaz veya güvenilir değilse işlem durur. Bir üst dizin altında korunan çocuk varsa üst dizin toptan silinemez. `replace_whitelist()` atomik ve doğrulanmış yazım yapar. Whitelist'in tarama zamanındaki görünümü icra izni değildir.

`Cleaner.execute()` (`cleaner.py`) `apply=False` iken değişiklik yapmaz; root'u engeller, gerekli CLI onayını ve uygulama-kapalı şartını arar, manuel fallback'i ayrıca `allow_manual_fallback` olmadan çalıştırmaz. Her hedef işlemden hemen önce yeniden yetkilendirilir. `system.py` içinde `directory_fd()`/`remove_validated_path()` dizin tanımlayıcısına sabitlenmiş, symlink takip etmeyen ve sahipliği kontrol eden silme uygular. Trash taşıma `renameatx_np` ile üzerine yazmayan atomik rename kullanır; platform bunu sunmuyorsa güvenlik düşürülmez. Hedef sahipliği, Trash dizini, whitelist ve kaynak kimliği yeniden kontrol edilir; kaynak yok/hedef var son koşulu doğrulanır. `run_command()` shell kullanmaz, argüman dizisi ve timeout uygular, zaman aşımında süreç grubunu durdurur. `size_of()` macOS `du -sk` kullanır; `sizes_of()` sınırlı worker havuzuyla ölçer. GUI PATH'i için `ensure_tool_search_path()` bilinen **var olan** araç yollarını ekleyebilir; Homebrew konumu körlemesine sabitlenmez.

İşlem/audit kayıtları JSONL'dir; başarısız/atlanan hedefler ve özet de kaydedilir. `RecoveryCenter` (`features.py`) doğrulanmış Trash kaydı ve `operation_id` ile restore/copy ve çakışma kontrolü sunar. Trash'e taşınan baytları “boşaltılan alan” diye göstermeyin. Akış: keşfet → açık inceleme/izin → canlı kimlik, yol, whitelist, sahiplik, symlink ve çalışan uygulama kontrolleri → icra → post-condition → audit. User data (çerez, oturum, veritabanı, tercih, kaynak kodu vb.) sıradan önbellek değildir.

### Web mutasyon sınırı

`web.py` Host'u localhost ile sınırlar; POST için JSON içerik türü, aynı portlu `Origin`, `HttpOnly; SameSite=Strict` oturum çerezi ve token ister. CSP ve `nosniff` kullanılır; `mutation_lock` aynı anda mutasyonları sınırlar. Birçok yıkıcı uç nokta `web_mutations._review_gate()` ile önce `reviewOnly` planı döndürür; HMAC'li token plan fingerprint'i, kapsam, tarama generation'ı ve süreye bağlıdır (varsayılan en fazla 300 saniye), **tek kullanımlıktır**. Kullanıcı verisi/MANUAL için ilave `extraOptIn` gerekir. Yeniden tarama veya whitelist değişimi eski incelemeleri geçersiz kılar. Memory'nin SIGTERM/SIGKILL incelemeleri ayrıdır; bazı POST'lar (`settings`, `scan/cancel`, `update/check`) yıkıcı review akışı değil, ancak aynı oturum/Origin sınırına tabidir. Mutasyon GET olarak eklenmez. Web'in son taramasındaki kimlik/yolları kabul etmesi çekirdeğin işlem zamanı doğrulamasının yerini almaz.

## 3. Keşif ve özellikler

- `Scanner.scan()` (`scanner.py`): salt-okunur fazlar user/browser/application/sandbox cache ve log/diagnostik; `developer`/`aggressive` profilde geliştirici ve paket yöneticisi cache fazları; `deep`/`aggressive` profilde saved state; isteğe bağlı Trash ve yalnızca `deep`/`aggressive` için sistem temp. `CancellationToken`, progress, issue/notlar, aday deduplikasyonu ve sıralama kullanır. `PackageManagerCacheScanner` yöneticinin resmi komutunu/kapasitesini araştırır; manuel fallback ancak dar allowlist + ayrı izinle, Docker/Podman'ın değerli state'i otomatik silinmeden kullanılır. `scan_installers()` eski imajları; `scan_leftovers()` kurulu app bundle ID'lerinden hareketle terk edilmiş bileşenleri tarar. Eksik/iptal edilmiş sonuçlar sessizce tam sayılamaz.
- `IncrementalAnalyzer` (`analyzer.py`): `snapshot()` hızlı dizin listesi, `scan()`/worker'lar kademeli ölçüm, `progress()`, `cancel_active()`, `approved_paths()` ve silme sonrası `invalidate_after_removal()`. `focus_id`/generation eski navigasyon sonuçlarının yeni görünümü ezmesini engeller; sınırlı havuz, duraklatma/önbellek vardır. Analizör keşfi ile Trash izni ayrı kapılardır.
- `DuplicateFinder` (`duplicates.py`) ve `LargeOldFileScanner` (`large_files.py`) okunur inceleme listeleri üretir; `SmartDownloadsScanner` (`smart_downloads.py`) yükleyici/arşiv/eksik ve yinelenen indirmeleri sınıflandırır; `BrowserStorageInspector` (`browser_storage.py`) cache ile oturum/çerez gibi kullanıcı verisini ayırır. Otomatik silme/seçim yoktur; kullanıcı tarafından seçilmiş dosya Trash işlemleri `Cleaner` ve analizör güvenlik kapısından geçer.
- `ApplicationManager` (`features.py`): `/Applications` ve `~/Applications` uygulamalarını plist/bundle ID ile bulur; Homebrew cask sahipliğini yöneticiden sorgular. Bundle, güvenli kalıntılar ve **varsayılan seçili olmayan** kullanıcı verisi bileşenleri ayrı incelenir. Çalışan uygulama, bundle kimliği, cask sahipliği ve whitelist işlem anında yeniden kontrol edilir. Cask için `brew uninstall --cask`; diğer onaylı `.app` ve kalıntılar için Trash kullanılır; yönetici yetkisiyle `osascript` veya sessiz `sudo` fallback'i yoktur. Yetki yoksa atlanır.
- `ProjectPurgeManager` (`features.py`): proje marker'larıyla (`.git`, `pyproject.toml`, `package.json`, vb.) kaynak kökünü doğrular; `build`, `dist`, `target`, `.next`, `node_modules`, `.venv`, `Pods` vb. oluşturulabilir hedefleri sınıflandırır. Yerel çıktılar en az 7, bağımlılık dizinleri en az 30 günlükse varsayılan seçilir; kullanıcı seçiminden sonra proje kimliği ve hedef yeniden doğrulanıp Trash'e taşınır.
- `DeveloperStorageCenter` (`developer.py`): Xcode, Node, Python, Rust, Android ve Docker depolama görünümü. `DeveloperInventory`: `runtime`, `environment`, `tool`, `sdk` envanteri; korunan/aktif/baz ortam ve bağımlı kaynaklarda `removable=False`. Kaldırma resmi yöneticinin doğrulanmış komutuna gider; ham runtime dizini silinmez. `FALLBACK_POLICY.md` cache fallback'i için yetkili kaynaktır.
- `features.py` ayrıca `system_status()`/`health_indicators()` (psutil, pil/termal/izin/sağlık), `doctor()`, `compatibility_checks()`, Homebrew MacMaid güncelleme kontrolü/uygulaması, Time Machine yerel snapshot listeleme/inceltme, geçmiş ve kurtarma içerir. **`OPTIMIZATIONS = []`: DNS/Quick Look/Finder/Dock/Spotlight bakım görevleri şu anda stabilite incelemesi bitene kadar devre dışıdır.** CLI/TUI/Web boş liste ve `OPTIMIZATION_UNAVAILABLE_REASON` kullanır; bunları çalışır özellik diye tanıtmayın. Snapshot inceltme ayrı, açıkça incelenen bir işlem olup bu listeden bağımsızdır.

## 4. Memory mimarisi (`memory.py`)

`MemoryService` yalnızca MacMaid çalışırken etkin olan, daemon kurmayan servistir. `psutil` ile normalde 5 saniyede bir örnek alır; `PID:create_time` anahtarları, kullanıcı/sistem/MacMaid süreç koruması, exe/entrypoint ve sahiplik doğrulaması PID reuse ve yanlış sürece sinyali engeller. Kimliği doğrulanamayan süreç gösterilebilir ama eyleme uygun değildir. RSS paylaşılan sayfalar da içerir, geri kazanılabilir RAM değildir. `/usr/bin/memory_pressure -Q` pressure headroom için kullanılır; veri yoksa sahte alternatif üretilmez.

Son sürümde süreç bazlı tabloya **uygulama ve süreç ailesi grupları** eklenmiştir: çalıştırılabilirin en dıştaki `.app` bundle yolu grubu belirler; bundle dışındaki çocuk yalnızca aynı exe'li ebeveyne katılır. Grup `children`, `memberKeys`, `protectedCount`, `eligibleCount`, `memoryBytes` ve `memoryMetric` ile sunulur. Ayrı, zaman bütçeli ölçüm işçisi `/usr/bin/footprint` ile aynı kullanıcı süreçlerinin fiziksel footprint'ini örnekler; çok süreçli grupta ortak sayfalar toplamda tek kez sayılır. Araç erişilemezse, çıktı kısmi/eskiyse veya üyelik imzası değiştiyse görünüm dürüstçe RSS'e döner; footprint tahmini PSS değildir. Tek süreçli gruplar toplu ölçülür, çok süreçli gruplar ayrı ölçülür. 10 dakikalık büyüme analizi süreç RSS geçmişinden veya **yeterli ve aynı üyelik imzalı** grup footprint geçmişinden gelir; en az 256 MiB, başlangıca göre %25 ve yükselen dakikalık medyan eşikleri gerekir. 15 saniyeyi aşan örnek aralığı sürekliliği sıfırlar.

İşlem yetkisi gruba değil, gruptan seçilen **tek tek** güncel süreç anahtarlarına bağlıdır (en fazla 100). Manuel `review()` tam hedef fingerprint'i üretir; Web tek kullanımlık token ister. SIGTERM sonrası en az 5 saniye hâlâ yaşayan uygun süreç için yeni, ayrı Force Stop/SIGKILL incelemesi gerekir. CLI `memory --stop PID` varsayılan salt-okunur review; `--apply` ve etkileşimsiz durumda `--yes` gerekir. `--watch` ile geçmiş örneklenebilir; `--growing` için en az 600 saniye izleme şarttır. TUI/Web örnekleme ve müdahaleyi UI döngüsü dışında yürütür.

Otomatik helper rule'ları varsayılan kapalıdır; yalnızca exact Dart analysis server ve TypeScript `tsserver.js` entrypoint'i uygundur, genel Node/Dart süreçleri değil. Rule, exclusion, cooldown ve hata durumları `memory.json` içinde korunur. Varsayılan kapılar: RSS >2 GiB, 5 dakika kesintisiz eşik, pressure headroom <%15; 30 dakika cooldown; canlı kimlik ve RSS yeniden doğrulanır. Otomasyon yalnızca SIGTERM gönderir, SIGKILL göndermez; iki başarısız denemeden sonra rule durur. Memory testlerinde sahte saat/psutil ile bu kapılar ve grup üyeliği/footprint fallback'i sınanır.

## 5. Kullanıcı arayüzleri ve HTTP haritası

CLI (`cli.py`) `doctor`, `status`, `scan`/`clean`, `leftovers`, `installers`, `developer-caches`, `apps`, `analyze`, `duplicates`, `large-files`, `smart-downloads`, `browser-storage`, `purge`, `developer`, `memory`, `optimize`, `snapshots`, `history`, `restore`, `completion`, `whitelist`, `uninstall`, `ui` sunar. Değiştirici CLI işlemleri normalde `--apply` olmadan yalnızca incelemedir; interaktif onay veya otomasyon için açık `--yes` gerekir. `apps` CLI yalnızca envanter sunar; kaldırma incelenmiş Web/TUI akışındadır. `restore` için operation ID ve Trash yolu gerekir. `optimize` komutu bulunur fakat görev listesi şu anda boştur.

TUI (`tui.py`) 11 gezinme bölümü tanımlar: Clean, Uninstall Apps, Optimize, Analyze, Project Purge, Developer Tools, Mac Health, Files & Storage, System & History, Memory ve Check for Updates. `@work`/worker ve iptal token'ları yavaş işleri UI döngüsünden ayırır. Geçerli binding'ler kodun `MacMaidTUI.BINDINGS` listesindedir (`j/k`, `space`, `t`, `d`, `r`, `c`, `q`, `h`/`m`/`Ctrl+N`, `l` vb.); eskiden belgelenen 1–9 doğrudan sekme kısayollarına güvenmeyin. TUI/CLI gösteriminde Unicode eylem ikonları eklemeyin.

Web görünümü `index.html` + `WebUI/features/*.js` modülleri ve `memory.js` kullanır; navigasyon ağır taramaları kendiliğinden başlatmaz, tarama düğmesiyle başlatır. Web metinleri EN/TR `WebUI/i18n.js` içindeki anahtarlardan `t()` ile, TUI metinleri `i18n.py`/`translate()` ile yerelleştirilir. Web ikonları `WebUI/icons.js` içindeki tek `SF_SYMBOLS` kataloğundan `sfSymbol()`/`data-icon` ile gelir; Lucide/emoji/hardcoded SVG eklemeyin. Tema ve dil ayarları Web tarafında localStorage; kullanıcı dili tercihi çekirdekte `preferences.json` ile saklanabilir.

HTTP GET rotaları `web_queries.py`, POST rotaları `web_mutations.py` içindedir; `web.py` statik dosya/oturum/dispatch ve `WebState` yaşam döngüsünü yönetir. Başlıca rotalar (tam liste için `route_get()`/`route_post()`):

| Alan | Salt-okunur GET | Oturumlu POST (mutasyon/eylem) |
|---|---|---|
| Temizlik | `/api/scan`, `/api/progress`, `/api/installers`, `/api/leftovers` | `/api/clean`, `/api/installers/clean`, `/api/leftovers/clean`, `/api/scan/cancel` |
| Uygulama ve proje | `/api/apps`, `/api/apps/leftovers`, `/api/purge` | `/api/apps/uninstall`, `/api/purge` |
| Disk/dosyalar | `/api/analyze`, `/api/treemap`, `/api/duplicates`, `/api/large-files`, `/api/smart-downloads`, `/api/browser-storage` | `/api/analyze/trash`, `/api/treemap/trash`, `/api/treemap/open`, `/api/duplicates/trash`, `/api/large-files/trash`, `/api/smart-downloads/trash`, `/api/browser-storage/clean` |
| Geliştirici | `/api/developer/storage`, `/api/developer/caches`, `/api/developer/{runtimes,environments,tools,sdks}` | `/api/developer/caches/clean`, `/api/developer/remove` |
| Sistem/geçmiş | `/api/status`, `/api/doctor`, `/api/permissions`, `/api/optimize`, `/api/snapshots`, `/api/history`, `/api/recovery/conflict`, `/api/whitelist`, `/api/macmaid/update` | `/api/permissions/open-full-disk-access`, `/api/optimize/run`, `/api/optimize/run-all`, `/api/snapshots/thin`, `/api/recovery/restore`, `/api/whitelist`, `/api/macmaid/update/check`, `/api/macmaid/update` |
| Bellek | `/api/memory`, `/api/memory/history` | `/api/memory/stop`, `/api/memory/force-stop`, `/api/memory/settings` |

## 6. Geliştirme, doğrulama ve yayın

```sh
uv sync --all-groups
uv run macmaid --help
uv run pytest tests_py/test_core.py -vv  # değişen alana göre odaklı test seç
uv run pytest
uv run ruff check src/macmaid tests_py
uv run mypy
uv run python -m compileall -q src/macmaid
node --check src/macmaid/WebUI/app.js
node --check src/macmaid/WebUI/memory.js
uv build
git diff --check
```

Ruff ve mypy sonucu **sıfır hata** olmalıdır; testleri veya kapsamı daraltarak geçiş sağlanmaz. CI `.github/workflows/ci.yml` macOS üzerinde lock kontrolü, lint, type check, compile, JS syntax ve pytest çalıştırır. Gerçek Chromium testleri normal koşuda opt-in'dir, CI'da ayrı browser job'unda zorunludur:

```sh
MACMAID_BROWSER_TESTS=1 uv run pytest \
  tests_py/test_memory_browser.py tests_py/test_webui_devcaches_e2e.py -q
```

Testler `tests_py/` altındadır: `test_execution_safety.py`, `test_trash_safety.py`, `test_system_safety.py`, `test_scan_mutability.py`, `test_review.py`, `test_recovery.py`, `test_memory.py`, `test_memory_groups.py`, `test_memory_webui.py`, `test_web.py`, `test_analyzer.py`, `test_packaging.py` vb. Güvenlik değişikliklerinde olumlu/olumsuz vaka ve mümkün olduğunda **geçici hata enjeksiyonu** (doğru kod PASS → hedef koruma bozulunca FAIL → geri alınınca PASS) gereklidir. Gerçek kullanıcının Mac'indeki dosyalar silinerek test yapılmaz; geçici HOME/dizin, kontrollü sahte süreç/komut ve gerçek tarayıcı testi gerektiğinde Chromium kullanılır. Testlerin yalnızca “hata vermedi” demesi yeterli değildir.

Kurulum: `./install.sh` veya `uv tool install --force .`; kullanıcı seviyesinde uygulama/binary: `make prod-install` → `scripts/prod-install.sh`; yayın DMG/CLI: `scripts/build-macos-app.sh`, `scripts/create-dmg.sh` ve `.github/workflows/macos-dmg.yml`. Kaldırma: `./uninstall.sh` (`--purge-data` isteğe bağlı). `Makefile` içindeki `check` yalnızca compile/test/smoke-check yapar; **Ruff/mypy yerine geçmez**.

### Sürüm kuralı

Bu çalışma ağacındaki sürüm **0.15.0**; güncel değeri `pyproject.toml` üzerinden doğrulayın. Kullanıcıya görünen kod değişikliğinden sonra SemVer'e göre artırın: geriye uyumlu özellik MINOR, hata/güvenlik/UI düzeltmesi PATCH, uyumsuzluk MAJOR (0.x için uyumsuz değişimde minor artırılır). Dört yüzeyi birlikte güncelleyin: `pyproject.toml`, `src/macmaid/__init__.py`, `uv.lock`, `src/macmaid/WebUI/index.html`; ilgili paketleme/sürüm testlerini çalıştırın. `scripts/prod-install.sh` app metadata'sında sürümü `macmaid.__version__` üzerinden okur. Yerel Git tag'i oluşturmayın/değiştirmeyin/push etmeyin: değişmez `v<version>` tag'ini yalnızca release CI oluşturur. Sadece dokümantasyon düzenlemesi için sürüm artırımı gerekmez. `README.md` veya diğer Markdown-only değişiklikleri CI path-ignore sebebiyle tek başına workflow tetiklemez; yerel kontrolleri atlamayın.

## 7. Yeni özellik kontrol listesi

1. Verinin gerçekten yeniden üretilebilir mi yoksa kullanıcı verisi mi olduğunu, doğru risk düzeyini, uygulama-kapalı ve yönetici-sahipliği şartlarını belirleyin. Temizlik için dar leaf/allowed root seçin; tüm `Application Support`/Docker state'i/aktif runtime silmeyin.
2. Ortak çekirdekte keşif, inceleme, **işlem anında** yol/whitelist/sahiplik/symlink/kimlik doğrulaması ve audit/post-condition akışını uygulayın; UI'ya yalnızca sunum/çağrı koyun. `shell=True`, geniş `rm -rf`, root işlem, güvenliği düşüren fallback yok.
3. Kullanıcıya görünen TUI/Web metni için hem Türkçe hem İngilizce çeviri, Web ikonu için tek SF kataloğu girdisi sağlayın. Var olan API/CLI inceleme ve dry-run sözleşmesini koruyun.
4. İzole davranış testleri, negatif güvenlik testleri, kritik regressions için fault-injection kanıtı, ilgili HTTP/gerçek browser testleri ekleyin. Önce odaklı test, ardından gerekli tam doğrulama ve sürüm yüzeyleri kontrolü yapın.
