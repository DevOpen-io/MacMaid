# ncdu Entegrasyon Araştırma Raporu

**Tarih:** 2026-09-18
**Kapsam:** ncdu'nun MacMaid disk-analiz mimarisine entegrasyonunun teknik fizibilitesi
**Test ortamı:** macOS 27.0 (Apple Silicon, arm64), ncdu 2.9.2 (Homebrew), MacMaid 0.12.0

> **Önemli düzeltme:** Araştırma brief'inde MacMaid için "Swift implementasyonu" ve "native Swift scanner" ifadeleri geçiyor. Mevcut MacMaid (bu repo, v0.12.0) tamamen **Python 3.11+** ile yazılmıştır (`src/macmaid`, bağımlılıklar: `psutil` + `textual`). Swift tarafı yoktur; üretilen `MacMaid.app` paketlenmiş Python çalıştırılabiliridir. Raporda "Swift" geçen seçenekler **"native Python scanner"** ve gerektiğinde "derlenmiş yardımcı binary" olarak yorumlanmıştır.

---

## 1. ncdu nedir?

**ncdu (NCurses Disk Usage)**, Yorhel tarafından geliştirilen, disk kullanımını interaktif metin arayüzünde gösteren bir POSIX aracıdır. `du`'nun interaktif, gezilebilir karşılığıdır: bir dizin ağacını tarar, tüm hiyerarşiyi modelinde tutar ve kullanıcıya klasörler arasında gezinme, silme, yenileme imkânı verir.

- **Lisans:** MIT
- **Sürüm hattı:** 2.x dalı **Zig** ile yazılmıştır (build için Zig 0.14/0.15 gerekir); 1.x dalı C'dir ve hâlâ LTS bakımı görür (1.22, 2025-03).
- **Hedef platform:** "Her POSIX sistemi" — resmî olarak macOS Homebrew formülü vardır; Linux için statik binary'ler dağıtılır.
- **Boyut:** arm64 binary ~378 KB (`libncursesw` + `libzstd` dinamik bağımlılıklarıyla).
- **Temel tasarım:** Uzaktaki/sunucu ortamlarında GUI olmadan "yer kaplayanı bul" aracı. Tarama çıktısı bir *tam ağaç modelidir* — ncdu bir stream analyzer değil, bir **interactive browser**'dır.

## 2. ncdu nasıl çalışıyor?

Kaynak kod incelemesi (`ncdu-2.9.2/src/scan.zig`, `sink.zig`, `model.zig`):

### Tarama motoru

- Her öğe için `fstatat(parent_fd, name, AT_SYMLINK_NOFOLLOW)` çağrılır; dizinler `openDirZ(..., .no_follow = true)` ile açılır → **fd-anchored, symlink-güvenli traversal**. Varsayılan olarak symlink takip edilmez (`-L` ile dosya hedefleri takip edilebilir, dizin symlink'leri asla).
- Her `Dir` explicit bir stack'te tutulur (rekürsiyon yok); 4096 baytlık isim tamponu.
- Ölçülen alanlar: `st_blocks` (dsize), `st_size` (asize), `st_dev`, `st_ino`, `st_nlink`, opsiyonel `mtime/uid/gid/mode` (`-e` extended).
- **Hardlink dedup:** `nlink > 1` dosyalar `(dev,ino)` hash haritasında dairesel bağlı listeye alınır; dizin bazında **shared vs unique** blok ayrımı yapılır (bir dizini silmenin gerçekten kazandıracağı alan `entry − shared`).
- **Filesystem sınırı:** `-x` ile `st_dev` karşılaştırması → mount/firmlink geçişi `otherfs` olarak işaretlenir.
- `--exclude PATTERN` eşleşmesi `stat()`'tan **önce** uygulanır (eşleşen öğe için stat atlanır → performans kazancı).
- `CACHEDIR.TAG` imzası (`--exclude-caches`) ve Linux kernfs filtresi desteklenir; okuma hataları `read_error`/`err` bayrağıyla işaretlenir ama **taramayı durdurmaz** — kısmi sonuçlar korunur.

### Bellek modeli

- `extern struct` kompakt kayıtlar: `Dir`/`File`/`Link` ~70-90 bayt + isim. `st_dev` u64, `u30` DevId tablosuna indirgenir. Bu model tarama sırasında RAM'de kurulur ve browser UI'nın veri tabanıdır.
- `-e` (extended) modu belleği ~%30 artırır.

### Parallel scanning (`-t N`, ncdu ≥ 2.5)

- 16-slot'lık paylaşılan LIFO kuyruk; her iş parçacığı önce kendine düşen dizini tamamen tarar, sonra kuyruktan iş çeker. `condvar` tabanlı, kuyruk dolunca iş kendi stack'ine düşer — basit work-stealing.
- **Kısıt:** Çok iş parçacıklı tarama ile JSON export birlikte çalışmaz — JSON export tek iş parçacığında stream edebilirken, `-t>1` ile önce tüm ağaç RAM'de kurulup sonra yazılır. Binary export (`-O`) bu kısıtı kaldırır.

### Export/Import (programatik kullanım)

| Format | Bayrak | Özellik |
|---|---|---|
| JSON | `-o FILE` / `-f FILE` | Tek doküman, tarama sonunda üretilir; ~600-700 KiB / 10k dosya; `dsize`/`asize`/`ino`/`nlink`/`excluded`/`read_error` alanları; stdin'den import destekli. gdu/tdu gibi üçüncü araçlar da okur. |
| Binary | `-O FILE` / `-f FILE` | ncdu 2.6+: CBOR item'ları + zstd blokları + index bloğu; tüm ağacı RAM'e almadan lazy browsing; `cumdsize` kümülatif boyutlar gömülü. Format dokümante ama ncdu-içi tasarım. |

Programatik kullanım = **subprocess + export parse**. Kütüphane/libncdu diye bir şey yoktur; `scan.zig` tek bir uygulamanın parçasıdır.

## 3. MacMaid'in mevcut disk-scanning mimarisi

MacMaid'de **iki farklı ölçüm stratejisi** vardır — bu ayrım kritik:

### 3.1 `system.py::size_of` / `sizes_of` — gerçek disk kullanımı

- Her hedef için `/usr/bin/du -sk <path>` subprocess'i; `ThreadPoolExecutor` ile en fazla 8 paralel iş.
- `du`'nun semantiği = ncdu'nunkiyle aynı: `st_blocks` tabanlı tahsis edilmiş blok sayımı → **sparse dosyalar, APFS sıkıştırma ve firmlink dışı kopyalar gerçek disk kullanımı olarak ölçülür**.
- Kullanıldığı yerler: tüm cleanup tahminleri (scanner), Trash-taşıma tahminleri (cleaner, analyzer trash, large-files, smart-downloads, duplicates), uygulama/component boyutları (features), geliştirici depolaması (developer).
- `run_command` sarmalayıcısı: `shell=False`, timeout, `start_new_session` + grup-kill, iptal callback'i.

### 3.2 `analyzer.py::IncrementalAnalyzer` — progresif disk analizörü

Web UI'daki **Disk Analyzer** ve **Treemap** ekranlarının motoru — ncdu'nun işlevsel karşılığı budur:

- **Model:** Kök dizin senkron listelenir → her doğrudan child `pending` durumuyla hemen gösterilir → 4-8'lik sınırlı worker havuzu her child'ı `_walk` ile ölçer → sonuçlar child bazında akar.
- `_walk`: `os.scandir` + explicit stack; symlink'ler atlanır; **`stat.st_size` (apparent size)** toplanır — `st_blocks` kullanılmaz; child içinde **tek bir erişim hatası bile tüm child ölçümünü `failed` yapar** (fail-closed).
- Navigasyon semantiği: yeni dizine geçince önceki job **pause** edilir (ölçülenler korunur), geri dönüş cache-hit'tir; `focus_id` ile bayat istekler reddedilir; `cancel_active` tek job iptali; `invalidate_after_removal` Trash sonrası cache temizler.
- Güvenlik: `validate_analyzer_candidate` → hedef `$HOME` altında, Library/.app/.photoslibrary dışı, symlink'siz, kullanıcıya ait olmalı.
- Bellek: sadece doğrudan child'lar + top-N "largest files" tutulur — sabit üst sınırlı, ağaç boyutundan bağımsız.

### 3.3 Diğer tarayıcılar

`scanner.py` (bilinen cache kökleri + paket-yöneticisi tarayıcısı), `duplicates.py`, `large_files.py`, `smart_downloads.py`, `browser_storage.py` — hepsi hedefli köklerde `os.scandir` ile çalışır; `st_size` yalnızca tek-dosya metadata'sı için kullanılır (doğru seçim).

## 4. ncdu vs MacMaid mevcut implementasyonu

| Boyut | ncdu 2.9.2 | MacMaid |
|---|---|---|
| Ölçüm semantiği | `st_blocks` (dsize) + `st_size` (asize) ikisi de | `du -sk` (blocks) cleanup tarafı; `st_size` analyzer tarafı |
| Tarama modeli | Tüm ağaç → tek tamamlanmış snapshot | Child-bazlı progresif akış; pause/resume/cancel |
| Symlink | Takip etmez (fd-anchored, no_follow) | Takip etmez (scandir + `is_symlink` reddi) |
| Hardlink | `(dev,ino)` dedup, shared/unique ayrımı | Dedup yok (`du` da yok — her path ayrı ölçülür) |
| FS sınırı | `-x` ile `st_dev` kontrolü | Yok (hedef zaten $HOME altında sınırlı) |
| Firmlink | **2.x'te tespit yok** (1.x'teki `"frmlink"` exclusion Zig dalına taşınmamış) | Yok — ama analyzer yalnızca $HOME altına izin verdiği için pratik risk yok |
| Erişim hatası | `read_error` flag, kısmi toplam korunur | Tüm child `failed` (fail-closed; mutasyon bloklu) |
| Kapsam | Kullanıcının verdiği herhangi bir kök, `/` dahil | `$HOME` altı + allowlist; Library/bundle'lar view-only |
| Sonuç | İnteraktif browser veya export dosyası | Web/TUI'da progresif tablo + Trash aksiyonu |
| Çıktı boyutu | ~80 bayt/girdi RAM | ~23 MB sabit Python baseline + sınırlı state |

**Firmlink notu (gerçek ölçüm):** Bu macOS 27 sisteminde `/Users` ile `/System/Volumes/Data/Users` aynı `st_dev` (16777231) ve aynı `st_ino` (14539) döndürüyor; `/usr`,`/bin` sentetik ino değerli normal dizin görünümünde. Yani ncdu 2.x'te `/` taraması firmlinkli içeriği **iki kez sayar** (1.x'in `frmlink` exclusion'ı Zig sürümüne taşınmamış). MacMaid `/` taraması yapmadığı için bu onun için risk değil — ama "ncdu her şeyi doğru sayar" varsayımı macOS'ta doğru değil.

## 5. Performans karşılaştırması (gerçek benchmark)

Yöntem: `/usr/bin/time -l` (duvar süresi + peak RSS) ve MacMaid için `resource.getrusage`. ncdu modları: saf tarama (`-0 --quit-after-scan`), JSON export (`-0 -o /dev/null`), binary export (`-O`). MacMaid: `IncrementalAnalyzer.snapshot()` tamamlanana dek + `sizes_of` (paralel `du`).

### `/opt/homebrew` — 151k dosya + 22.5k dizin + 32k symlink, ~5.3 GB

| Araç | Süre | Peak RSS | CPU (user+sys) |
|---|---|---|---|
| ncdu `-0 --quit-after-scan` (1t) | 1.18 s | 11.9 MB | 1.12 s |
| ncdu `-0 --quit-after-scan -t8` | **0.48 s** | 12.3 MB | 2.59 s |
| ncdu `-0 -o /dev/null` (JSON) | 1.23 s | **2.5 MB** | 1.10 s |
| ncdu `-0 -O /dev/null` (binary) | 1.00 s | 3.8 MB | 0.98 s |
| MacMaid analyzer (w4, st_size) | 1.20 s | 23.0 MB | — |
| MacMaid `sizes_of` (du ×4) | **0.85 s** | 23.1 MB | — |

### `~/Library/Caches` — 31.6k dosya, ~4 GB

| Araç | Süre | Peak RSS |
|---|---|---|
| ncdu 1t | 0.93 s | 4.1 MB |
| ncdu -t8 | 0.08 s | 4.4 MB |
| MacMaid analyzer w4 | 0.28 s | 23.1 MB (9 child erişim hatası) |
| MacMaid du ×4 | 0.19 s | 23.5 MB |

### `~/Library` — 156k dosya, ~11.2 GB (TCC-korumalı alt ağaçlar içerir)

| Araç | Süre | Not |
|---|---|---|
| ncdu -t8 | 3.48 s | 14.3 MB; reddedilenler `read_error` ile sayılır |
| ncdu 1t | 5.02 s | 13.9 MB |
| MacMaid analyzer w4 | 2.11 s | **yalnız 26.9k dosya / 1.5 GB** — 31 child tamamen `failed` |
| MacMaid du ×4 | 2.67 s | 1.55 GB (du kısmi toplamları korur) |

### Sentetik: `/tmp/ncdu-bench` — 4.3k dosya, 1 GB gerçek + 5 GB sparse

| Araç | Süre | Toplam |
|---|---|---|
| ncdu apparent export | 0.02 s | — |
| MacMaid analyzer | 0.107 s | **6.45 GB** (st_size → sparse tam sayılır) |
| MacMaid du ×4 | 0.026 s | **1.09 GB** (sparse = 0 blok) |
| ncdu dsize | — | 1.08 GB (du ile aynı semantik doğrulandı) |

### Sentetik: `many-small` — 50.000 küçük dosya (200 dizin), ~115 MB

| Araç | Süre | Peak RSS |
|---|---|---|
| ncdu 1t | 0.11 s | 4.0 MB |
| ncdu -t8 | 0.04 s | 4.3 MB |
| MacMaid analyzer w4 | 0.22-0.32 s | 23.1 MB |
| MacMaid du ×4 (200 subprocess) | 0.49 s | 22.9 MB |

### Benchmark yorumu

1. **Tarama I/O-bound'dur.** NVMe SSD'de tek iş parçacıklı ncdu ile MacMaid analyzer neredeyse aynı duvar süresindedir (1.18s vs 1.20s /opt/homebrew) — fark baskın olarak kernel çağrılarıdır, dil değil.
2. **Gerçek hız farkı `-t`'dedir:** ncdu -t8, tek dev çocuk dizini baskın olan ağaçlarda ~2.5-10× hızlıdır; MacMaid paralelliği yalnızca üst-seviye child'lar arasındadır (tek dev çocuk = tek thread).
3. **du-subprocess stratejisi rekabetçidir:** az sayıda büyük child'da du ×4 ncdu'yu geçer (0.85s); çok sayıda küçük child'da subprocess spawn maliyeti (200 × ~2 ms) geriye düşürür (0.49s).
4. **RAM:** ncdu in-memory model ~80 bayt/girdi (50k ≈ 4 MB; 175k ≈ 12 MB) — milyonlarca dosyada yüzlerce MB'a çıkar. JSON export stream'i 2.5 MB sabitte kalır ama tek thread'le sınırlı. MacMaid ~23 MB Python baseline + sınırlı state; incremental maliyet küçüktür.
5. **Mikro-fark:** 50k küçük dosyada Python öğe-başına ~4-6 µs ek yük görünür (0.22s vs 0.11s). 1M dosyada bu ~5 sn eder — önemli ama felaket değil.
6. **Ölçüm semantiği farkı gerçektir:** sparse dosyada analyzer (st_size) 6.45 GB, ncdu/du (st_blocks) 1.09 GB saydı — aynı ağaçta 6× fark. Ancak MacMaid'in cleanup tarafı zaten `du` kullanıyor; fark yalnızca analyzer görünümündedir.

## 6. Entegrasyon seçenekleri

### Seçenek A — ncdu binary'sini bundle edip subprocess ile çalıştırmak

```
MacMaid UI → analyzer servisi → ncdu -0 -o out.json <dir> → JSON parse → model → UI
```

**Artılar**
- MIT lisansı sorunsuz; ~380 KB binary; read-only, kullanıcı yetkisiyle çalışır (MacMaid'in "asla root" kuralıyla uyumlu).
- Tek komutta gerçek `st_blocks` + hardlink-dedup + FS-sınırı davranışı.
- ncdu JSON formatı 1.9'dan beri geriye uyumlu ve dokümante; diğer araçlar da okuyor.

**Eksiler (yapısal)**
1. **Mimari uyumsuzluk:** JSON export tarama **bitene kadar** hiçbir şey vermez. MacMaid'in analyzer'ı child-bazlı akış, pause-on-navigate, job-cache ve tek-job iptal üzerine kurulu — batch export bu UX'in gerisine düşer. `-1` satır-progress parse etmek kırılgan bir hack; `-O` lazy okuma sunar ama CBOR+zstd okuyucusu ve iki yeni bağımlılık gerektirir (MacMaid kasten stdlib'e yakın duruyor).
2. **Dağıtım:** Homebrew binary'si `/opt/homebrew/opt/{ncurses,zstd}` dylib'lerine bağlı — doğrudan bundle edilemez; Zig toolchain ile statik/relokasyonlu build + `install_name_tool` + aynı Developer ID ile imza + hardened runtime gerekir. Şu an arm64-only dağıtım bunu tolere eder; Intel desteği için ikinci arch build şart.
3. **Kontrol kaybı:** Fail-closed güvenlik modeli (kısmi sonuç → mutasyon yok) ncdu'nun best-effort modeline dönüşür; view-only/Library kuralları ve whitelist uygulaması export sonrası filtreye kalır — taranan veri yine de okunmuş olur.
4. **Tedarik zinciri:** Sabitlenmiş sürüm + checksum + imza pipeline'ı gerektirir; ncdu güncellemeleri MacMaid release'ine bağlanır.

**Verdict:** Teknik olarak mümkün, ölçülen kazanç ise NVMe'de ~0.5-2.5× duvar süresi — karşılığında UX gerilemesi + paketleme karmaşası. Gerçekçi senaryo: ancak **milyonlarca dosyalık tam-disk analizi** bir gün hedef olursa, `IncrementalAnalyzer` arayüzünün arkasında yardımcı motor olarak.

### Seçenek B — ncdu kaynak kodunu adapte etmek

- Zig→Python portu: sıcak yol syscall'dir (`fstatat`/`getdirentries`), dil değil; `os.scandir` + `DirEntry.stat(follow_symlinks=False)` aynı syscall dizisini zaten üretir. Portun getireceği performans ≈ 0.
- Zig/C'nin tek somut avantajı öğe-başına ~µs'lık object-overhead azaltımı — 1M dosyada birkaç saniye; karşılığı: kalıcı fork, MIT atıf yönetimi, upstream ile divergence bakımı.
- Gerçekten native hız gerekirse doğru biçim "kaynak portu" değil, minik bir **derlenmiş yardımcı** (C/Rust/Zig extension veya `/usr/bin/du`'nun zaten yaptığı gibi sistem aracı) — ama bölüm 5 gösteriyor ki buna gerek yok.

**Verdict:** Ölçülebilir kazanç yok, bakım maliyeti yüksek. Reddedilmeli.

### Seçenek C — Mevcut native scanner'ı geliştirmek (ncdu tekniklerinden ödünç alarak)

ncdu'nun gerçek avantajları incelendiğinde hepsi küçük, ucuz değişikliklerle alınabilir:

| ncdu tekniği | MacMaid'de durumu | Maliyet |
|---|---|---|
| `st_blocks` disk-usage | `du -sk` ile zaten var; analyzer `_walk`'a `stat.st_blocks` eklemek ~1 satır (aynı `stat()` sonucunda bedava) | Düşük |
| Ağaç-içi paralellik | Child-bazlı var; tek-dev-çocuk darboğazında `_walk` içine bounded alt-paralellik eklenebilir | Orta |
| Hardlink dedup | Yok; `(dev,ino)` set'i `_walk`'a eklenebilir (kullanıcı dizinlerinde hardlink nadirdir — `.pnpm`, yedekler) | Düşük |
| `-x` FS-sınırı | Yok; `st_dev` karşılaştırması 1 satır | Düşük |
| `CACHEDIR.TAG` | Scanner'da hedefli kökler zaten biliniyor; analyzer görünümüne eklenebilir | Düşük |
| Kısmi-hata toleransı | Bilinçli tasarım farkı (fail-closed) — değiştirilmemeli, ama "kısmi boyut + failed flag" gösterimi düşünülebilir | Tasarım kararı |

**Verdict:** Mevcut mimariyi koruyup ölçülen gerçek boşlukları kapatmak en yüksek değer/maliyet oranını verir.

## 7. macOS / Sandbox / App Store / dağıtım riskleri

| Konu | Değerlendirme |
|---|---|
| **App Sandbox / App Store** | MacMaid geniş FS okuması + Trash yazması gerektirir → sandbox'lı App Store dağıtımı bu ürün sınıfı için zaten uygun değil (hedef dağıtım: Homebrew + DMG + yerel kurulum). ncdu bundle etmek durumu değiştirmez ama App Store'u tamamen devre dışı bırakır — zaten dışarıda. |
| **TCC / permission** | ncdu da aynı kullanıcı yetkisiyle çalışır; Mail/Safari/FDA kısıtları aynen geçerli — ncdu farkı: reddedilenleri `read_error` ile sayar, MacMaid fail-closed tutar. |
| **Code signing** | Bundle'daki ncdu'nun ana binary ile aynı Developer ID + hardened runtime ile imzalanması gerekir. Homebrew build'i adhoc + harici dylib'li → pratikte kaynaktan build şart. Mevcut `prod-install` zaten imzasız/adhoc dünyada çalışıyor; CI notarize release için ek imza adımı gerekir. |
| **Hardened Runtime / Notarization** | ncdu özel entitlement istemez; ama notarize akışına bir binary daha eklenir (imza + stapling kapsamı). |
| **Apple Silicon** | Mevcut brew binary arm64; release zaten arm64-only → uyumlu. |
| **Intel** | Kaynaktan x86_64 build gerekir (Zig cross-compile mümkün); universal2 lipo veya arch-seçimli dispatch. MacMaid kaynak/dev kurulumu Intel'de çalışır — bundle edilirse ncdu da iki arch'ta derlenmeli. |
| **Firmlink/APFS** | ncdu 2.x firmlink tespiti yok; `/` taramasında çift sayım. MacMaid'in kullanım senaryosunda ($HOME altı) etkisiz ama ncdu'ya "doğru sayar" diye güvenmek yanıltıcı olur. APFS clone'lar (copy-on-write) her iki tarafta da inode-bazlı sayılır — eşit sınırlama. |
| **SIP** | Okuma tarafında sorun yok. |
| **Binary boyutu** | +~0.4-1.5 MB (binary + dylib'ler) — önemsiz. |

## 8. Lisans değerlendirmesi

- ncdu: **MIT** — MacMaid'in MIT lisansıyla tam uyumlu. Bundle/source-adaptasyon serbest; tek yükümlülük copyright + lisans metninin dağıtıma eklenmesi (`LICENSES/MIT.txt` veya THIRD-PARTY-NOTICES).
- Bağımlılıklar: `ncursesw` (MIT-X benzeri), `zstd` (BSD) — bundle edilirse onların da lisans metinleri gerekir.
- Kaynak-adaptasyon (Seçenek B) de MIT kapsamında serbest ama attribution + fork-bakımı ekler.
- **Lisans bir engel değil** — karar tamamen teknik/mimari gerekçelerle verilmeli.

## 9. Entegrasyonun sağlayacağı gerçek faydalar

1. `-t N` ile ağaç-içi paralellik → tek-baskın-child senaryosunda ~2.5-10× duvar süresi kazancı (ölçülen: 0.48s vs 1.20s /opt/homebrew; 0.04s vs 0.22s 50k-dosya).
2. `st_blocks` + hardlink-dedup doğruluğu, tek araçta — ama MacMaid bunu `du` ile zaten eşdeğer elde ediyor.
3. `-O` formatının lazy-browse özelliği — teorik olarak devasa ağaçlarda bellek tasarrufu; karşılığı özel parser bağımlılığı.
4. Battle-tested traversal (kernfs/CACHEDIR.TAG/exclude öncesi-stat optimizasyonları) — küçük optimizasyonlar, port değil ilham değeri.

## 10. Entegrasyonun getireceği dezavantajlar

1. **UX gerilemesi:** progresif child-akışı + pause/resume/navigate-cache → batch-wait modeline döner (veya -O için özel parser).
2. **Güvenlik-modeli gerilemesi:** fail-closed → best-effort; whitelist/view-only kontrolleri tarama öncesi değil sonrası uygulanır.
3. **Paketleme:** Zig toolchain + çift-arch build + dylib relokasyonu + imza/notarize pipeline'ı + sürüm sabitleme.
4. **Kavramsal fazlalık:** MacMaid'in "ncdu işi" dediği şeyin çoğu `du -sk` paralelle zaten yapılıyor ve ölçümlerde kazanabiliyor.
5. **Yeni hata yüzeyi:** subprocess lifecycle, export-format evrimi, ncdu'nun kendi edge-case'leri (firmlink çift-sayımı dahil).
6. ncdu'nun modeli "tek tamamlanmış snapshot" — MacMaid'in incremental/cancellable contract'ına yapısal olarak uymaz; iki model arasına köprü yazmak asıl maliyeti oluşturur.

## 11. Önerilen mimari

**ncdu entegre edilmemeli.** Ölçülen veri bunu destekliyor: aynı duvar süresi (tek-thread'de), MacMaid'in `du`-paralel stratejisi zaten bazı senaryolarda daha hızlı, ve ncdu'nun gerçekten üstün olduğu iki nokta (ağaç-içi `-t` paralellik, hardlink dedup) kullanıcı-görünür değeri sınırlı ve native olarak ucuza kapatılabilir.

**Bunun yerine (Seçenek C) önerilen somut iyileştirmeler:**

1. `analyzer.py::_walk` içinde `stat.st_blocks`'u da topla; analyzer/treemap'e "apparent vs disk usage" görünümü ekle — cleanup tahminleriyle (`du`) tutarlılık sağlar, sparse/sıkıştırma doğruluğu gelir. *(~satırlarca iş)*
2. Tek-dev-çocuk darboğazı için `_walk`'a bounded ikinci-seviye paralellik düşün (worker sayısı toplamda 8'i geçmeyecek şekilde paylaştırılmış) — ncdu `-t` kazancının büyük kısmını yakalar.
3. İsteğe bağlı `(dev,ino)` dedup set'i `_walk`'a — yalnızca dedup-ağır ağaçlarda (`.pnpm`, backup'lar) doğruluk.
4. Analyzer'a `st_dev` sınır bayrağı (`-x` eşdeğeri) — mount/firmlink geçişini kazara ölçmemek için.
5. `CACHEDIR.TAG` işaretini analyzer görünümünde gösterge olarak kullan (silme değil, bilgi).

**Seçenek A ne zaman yeniden değerlendirilmeli:** Eğer MacMaid bir gün tam-disk/milyonlarca-dosya analizini hedef alırsa, `IncrementalAnalyzer`'ın mevcut kontratını (progresif akış, cancel, cache) bozmadan arkasına `ncdu -t8 -O` + özel okuyucu koymak teknik olarak en temiz entegrasyon biçimidir — ama o hedef bugün yok ve bugünün verisi maliyeti haklı çıkarmıyor.

**Seçenek B (kaynak portu):** kesin olarak reddedilmeli — sıfır ölçülebilir kazanç, kalıcı fork maliyeti.

---

### Ek — Benchmark üretkenliği

Komutlar (tekrarlanabilir):
```sh
/usr/bin/time -l ncdu -0 --quit-after-scan [-t8] <dir>
/usr/bin/time -l ncdu -0 -o /dev/null [--apparent-size] <dir>
/usr/bin/time -l ncdu -0 -O /dev/null <dir>
# MacMaid tarafı: /tmp/ncdu-bench/bench_macmaid.py <dir>
```

Sınırlamalar: Tek makine, tek mimari (arm64), sıcak/soğuk cache karışık (ardışık çalıştırmalarda FS-cache farkı vardır — sayılar ±%30 doğrultusunda okunmalı); `~/Library` ölçümü iki araç için iş-yükü açısından eşit değildir (MacMaid fail-closed davranıp reddedilen alt ağaçları tamamen atlar, ncdu kısmi sayar). Ağ/HDD/sürücü-yoğun senaryolar ölçülmedi — orada `-t` avantajının büyümesi beklenir.
