# DeepClean Geliştirme Yol Haritası

Amaç: macOS bakımını daha güvenilir, anlaşılır ve ölçülebilir yapmak; daha fazla alan temizlemek uğruna kullanıcı verilerini riske atmamak.

## Mevcut başlangıç noktası

- TUI araç geçişlerinde eski tarama sonuçları ve seçimler sıfırlanıyor.
- Terk edilen taramaların geç gelen sonuçları ekranı güncellemiyor.
- Son doğrulamada macOS 26.2 Apple Silicon üzerinde 201 test, Python/JavaScript sözdizimi kontrolleri ve paket oluşturma başarılıydı.
- Intel ve eski desteklenen macOS sürümleri otomatik uyumluluk testlerinde kapsanıyor; mevcut doğrulama ortamında fiziksel olarak çalıştırılmadıkları ayrıca kayıtlıdır.

**Durum:** 1., 2., 3., 4., 5. ve 6. aşamalar tamamlandı. Her aşama ayrı, incelenebilir değişikliklerle tamamlanır. Güvenlik açığı bulunursa sonraki özelliklerden önce giderilir.

## 1. Güvenlik testleri ve yürütme sınırları

**Öncelik:** En yüksek · **Bağımlılık:** Yok

### Uygulanan ilk paket: Cleaner ve Web analyzer Trash güvenliği

- [x] Web analyzer'ın doğrudan `shutil.move` yolu kaldırıldı; TUI ile aynı Cleaner metodunu kullanıyor.
- [x] Normal Trash işlemlerine eksik whitelist kontrolü eklendi; hedef ve whitelist taşıma öncesinde tekrar doğrulanıyor.
- [x] Ortak Trash yolunda root, hedef sahipliği, hedef/ata symlink ve Trash dizini kontrolleri eklendi.
- [x] Analyzer taşımasının son koşulu çekirdek katmanda doğrulanıyor; başarı/hata audit kaydı oluşturuluyor.
- [x] Ad çakışması, hazırlık sırasında değişen hedef/whitelist, izin hatası, etkisiz taşıma ve korunan kökler için izole regresyon testleri eklendi.
- [x] Doğrulama: 20 yeni test; toplam 65 test geçti. `compileall` ve `uv build` başarılı.

### Tamamlama paketi

- [x] ApplicationManager ve ProjectPurgeManager ortak, audit edilen Cleaner Trash yürütme yoluna bağlandı.
- [x] macOS Trash taşıması descriptor-anchored `renameatx_np(RENAME_EXCL)` kullanıyor; symlink takip etmiyor, mevcut hedefi ezmiyor ve cross-volume kopyalama fallback'i yapmıyor.
- [x] Recursive silme descriptor-anchored/no-follow yapıldı; hedef ve kök sahipliği doğrulanıyor.
- [x] Hedefin herhangi bir alt öğesi whitelist tarafından korunabiliyorsa toplu işlem tamamen engelleniyor.
- [x] Eksik, okunamayan, bozuk, relative veya symlink whitelist fail-closed; audit dizini/dosyası da symlink ve sahiplik doğrulamasından geçiyor.
- [x] Homebrew Cask başarısızlığının raw silmeye düşmesi kaldırıldı; non-cask uygulamalar Trash'e taşınıyor ve uygulama kaldırma yetki yükseltmiyor.
- [x] Aktif/base/dependent runtime korumaları sertleştirildi. Shell metni gerektiren NVM/SDKMAN ve bağımlılık güvenliği kanıtlanamayan kaynaklar inventory-only yapıldı.
- [x] Subprocess yürütmesi explicit argv + `shell=False`, timeout, process-group sonlandırma, pipe-drain ve kontrollü missing executable davranışıyla doğrulandı.
- [x] TUI çift mutasyonu/araç değişimini engelliyor. Web mutasyonları exact Host/Origin/session doğrulaması ve tek-mutasyon kilidi kullanıyor. CLI dry-run/onay sözleşmesi test edildi.
- [x] Pozitif ve negatif testler whitelist TOCTOU, symlink escape, ownership mismatch, running app, protected runtime, missing manager, timeout, Trash collision, partial failure ve post-condition senaryolarını kapsıyor.
- [x] Doğrulama: toplam 157 test geçti; `compileall` ve `uv build` başarılı.

1. aşama testleri geçici HOME, sentetik bundle/proje ağaçları ve taklit subprocess'lerle çalıştı. Gerçek kullanıcı dosyaları üzerinde mutasyon yapılmadı.

### Yapılacaklar

- Cleaner, PathSafety, uygulama kaldırma, Project Purge ve geliştirici araçlarının mevcut yürütme yollarını incele.
- Eksik olan pozitif ve negatif testleri ekle:
  - Tarama sonrasında whitelist'e eklenen hedefin korunması.
  - Hedefin veya atasının symlink ile değiştirilmesi.
  - Korunan kökler, geçersiz yollar ve uygun yerlerde sahiplik uyuşmazlığı.
  - Çalışan uygulama, aktif runtime ve manager'ın temel ortamının korunması.
  - Eksik komut, timeout, izin hatası ve kısmi başarısızlık.
  - Trash ad çakışması ve taşıma son koşulunun doğrulanması.
- TUI, CLI ve Web işlemlerinin ortak güvenlik katmanına ulaştığını doğrula.
- Saptanan kusurları kapsamı dar yamalarla düzelt; izin listelerini genişleterek çözme.

### Tamamlanma kriteri

- [x] Testler geçici dizinler ve taklit subprocess'lerle çalışır; gerçek kullanıcı dosyalarına dokunmaz.
- [x] Belirsiz veya güvenli olmayan hedeflerde mutasyon gerçekleşmediği doğrulanır.
- [x] Root koruması, yürütme anında yeniden doğrulama ve işlem kaydı korunur.
- [x] İlgili testler ve tam test paketi geçer.

## 2. Temizlik öncesi açık işlem özeti ve onay

**Öncelik:** Yüksek · **Bağımlılık:** 1

### Uygulanan

- [x] Ortak `ReviewPlan`/`ReviewItem` modeli eklendi: exact hedef veya manager komutu, işlem türü, risk, gerekçe, tahmini boyut, uygulama-kapatma gereksinimi ve user-data sınıfını taşır.
- [x] TUI'ye ayrı inceleme ekranı, terminal tarzı `[y/N]` onayı ve USER DATA/MANUAL seçimler için ikinci açık `y` onayı eklendi; Enter/`n`/Esc güvenli varsayılan olarak iptal eder.
- [x] TUI seçim/tarama değişimini fingerprint ile algılıyor; eski plan callback'i çalıştırılmadan iptal ediliyor.
- [x] CLI temizleme, Project Purge, Optimize ve snapshot işlemlerinde exact planı onaydan önce yazdırıyor; dry-run/`--apply` sözleşmesi korundu.
- [x] Web arayüzü her destructive işlem için önce sunucudan ortak plan alıyor; UI planın tüm hedeflerini ve etkisini gösteriyor.
- [x] Web yürütmesi exact plan + scan generation'a bağlı, imzalı, 5 dakika ömürlü ve tek kullanımlık review token gerektiriyor.
- [x] Yeni tarama, değişen seçim, token replay/expiry ve eksik user-data opt-in yürütmeden önce engelleniyor.
- [x] App ve Developer manager işlemleri, incelemede gösterilen exact kimlik/komut değişirse yürütülmüyor.
- [x] Review'den sonra da whitelist, PathSafety, sahiplik, symlink, uygulama/runtime durumu ve post-condition kontrolleri çekirdek katmanda tekrar çalışıyor.
- [x] Doğrulama: toplam 172 test, JavaScript sözdizimi kontrolü, `compileall` ve `uv build` başarılı.

### Yapılacaklar

- Mevcut onay akışlarını incele; doğrudan yürütmeye geçen yolları tespit et.
- Seçilen işlemler için ortak, yapılandırılmış bir inceleme özeti oluştur:
  - Tam hedef veya manager işlemi.
  - İşlem türü: Trash, kalıcı silme veya manager komutu.
  - Risk seviyesi, gerekçe ve olası kullanıcı etkisi.
  - Kapatılması gereken uygulamalar.
  - Tahmini alan ve ölçümün sınırları.
- TUI'de işlemden önce açık onay/iptal adımı sun; CLI ve Web'de mevcut korumaları zayıflatmadan aynı bilgileri göster.
- Kullanıcı verisi ve MANUAL_ONLY hedeflerde ayrı, açık opt-in davranışını koru.
- Seçim, profil veya tarama değişirse önceki onayı geçersiz kıl.

### Tamamlanma kriteri

- [x] Onay verilmeden hiçbir mutasyon başlatılmaz.
- [x] İptal ve araç değişimi işlemi başlatmaz; eski seçimlere ait onay yeniden kullanılamaz.
- [x] Özet ile yürütmeye gönderilen hedeflerin aynı olduğu test edilir.
- [x] Onaydan sonra da PathSafety ve whitelist yeniden değerlendirilir.

## 3. Alan kazanımını dürüst raporlama

**Öncelik:** Yüksek · **Bağımlılık:** 1–2

### Uygulanan

- [x] `OperationResult` geriye uyumlu biçimde tarama tahmini, başarıyla işlenen hedef tahmini, konservatif geri kazanım tahmini, Trash tahmini, gözlenen boş alan farkı ve bilinmeyen manager etkilerini ayrı alanlarda taşıyor.
- [x] `freed` uyumluluk alanı Trash taşımalarını ve ölçülemeyen manager komutlarını dışlayan konservatif bir tahmin olarak sınırlandı.
- [x] Başarısız ve atlanan hedefler işlenen hedef veya geri kazanım toplamlarına dahil edilmiyor.
- [x] Aynı dosya sistemi cihazları için işlem öncesi/sonrası boş alan örnekleniyor; ölçüm yoksa `None` ve açıklayıcı not dönülüyor.
- [x] macOS durum göstergesi read-only `/` System volume yerine kullanıcı dosyalarının bulunduğu `/System/Volumes/Data` volume'unu kullanıyor; kullanım ve kullanılabilir alan aynı volume bazında açıkça etiketleniyor.
- [x] TUI, CLI ve Web; tarama/işlenen/geri kazanım tahminlerini ve gözlenen dosya sistemi farkını farklı etiketlerle gösteriyor.
- [x] Trash işlemleri açıkça “alan boşalmadı” olarak raporlanıyor; Project Purge, installer, analyzer ve uygulama bileşenleri aynı kurala uyuyor.
- [x] Developer, Homebrew Cask ve snapshot manager etkileri kesin alan kazanımı yerine “bilinmiyor” olarak sınıflandırılıyor.
- [x] JSONL item kayıtları yeni alanlarla genişletildi ve aggregate `operation_summary` kaydı eklendi; eski `bytes`/`freed` alanları uyumluluk için korundu.
- [x] History API/UI yalnız açık tahmini geri kazanımı topluyor; Trash ve bilinmeyen manager etkilerini toplam kazanç olarak göstermiyor.
- [x] APFS clone, snapshot, sparse dosya ve eşzamanlı disk etkinliği uyarısı tüm gözlenen fark raporlarına eklendi.
- [x] Doğrulama: toplam 176 test, JavaScript sözdizimi kontrolü, Python `compileall` ve `uv build` başarılı.

### Yapılacaklar

- Mevcut boyut ölçümü ve `freed` hesaplamalarını incele; APFS farkındalığını koru.
- Arayüz ve kayıtlarda şu değerleri birbirinden ayır:
  - Taramada tahmin edilen temizlenebilir alan.
  - Başarıyla işlenen hedeflerin tahmini boyutu.
  - İlgili dosya sisteminde işlem öncesi/sonrası gözlenen boş alan farkı.
- Aynı diskte Trash'e taşınan veriyi boşaltılmış alan olarak sayma.
- APFS clone, snapshot, sparse dosya ve eşzamanlı disk etkinliğinin ölçümü etkileyebileceğini belirt.
- Manager komutu veya ölçüm hatasında alan kazanımı bilinmiyorsa bunu açıkça göster.
- Mevcut API ve JSONL kayıtlarını uyumluluğu gözeterek geliştir.

### Tamamlanma kriteri

- [x] Tahmin ile ölçülen fark farklı etiketlerle gösterilir.
- [x] Gözlenen disk farkı, yalnızca DeepClean'in sağladığı kesin kazanım diye sunulmaz.
- [x] Başarısız veya atlanan hedefler başarılı kazanıma dahil edilmez.
- [x] Trash taşıması, ölçüm hatası ve kısmi başarı senaryoları test edilir.

## 4. İptal edilebilir tarama ve eksik sonuç bildirimi

**Öncelik:** Orta-yüksek · **Bağımlılık:** 1

### Uygulanan

- [x] Paylaşılan thread-safe `CancellationToken` ve `ScanCancelled` sinyali eklendi.
- [x] Smart Clean, app/component, Project Purge, developer/cache, leftovers ve installer taramaları güvenli kontrol noktalarında işbirlikçi iptali destekliyor.
- [x] Boyut ölçümü tüm işi baştan kuyruğa doldurmak yerine sınırlı sayıda future planlıyor; iptalden sonra yeni ölçüm planlanmıyor.
- [x] `du` ve developer/package-manager envanter subprocess'leri bekleme sırasında iptali kontrol ediyor; iptalde yalnız sahip olunan process group sonlandırılıyor.
- [x] Incremental Analyzer aktif işi gerçekten durduruyor, bekleyen future'ları iptal ediyor ve `cancelled` satır/durum bilgisini koruyor.
- [x] TUI'ye `c` ile “taramayı durdur” eylemi eklendi; devam eden cleanup mutation bu eylemden özellikle ayrıldı ve zorla kesilmiyor.
- [x] Web'e korumalı `POST /api/scan/cancel` endpoint'i ve yalnız aktif Smart Clean/Analyzer sırasında görünen durdurma kontrolü eklendi.
- [x] CLI read-only taramaları `Ctrl+C` durumunda subprocess'i güvenle sonlandırıp “değişiklik yapılmadı” mesajıyla çıkıyor.
- [x] `ScanResult` complete/partial/cancelled/failed durumlarını ve erişim/ölçüm sorunlarını yapılandırılmış olarak taşıyor.
- [x] Permission/TCC sorunları “temiz” sonucu olarak gizlenmiyor; Full Disk Access açıklaması yalnız ilgili erişilemeyen konumlar için sunuluyor.
- [x] Kısmi veya iptal edilmiş toplu tarama sonuçları TUI, CLI, Web UI ve API katmanlarında otomatik seçilemiyor veya temizlemeye gönderilemiyor.
- [x] Eski worker callback/generation koruması muhafaza edildi; yeni tarama eski işi iptal ediyor ve stale sonuç aktif durumu değiştiremiyor.
- [x] Doğrulama: toplam 186 test, JavaScript sözdizimi kontrolü, `compileall` ve `uv build` başarılı.

### Yapılacaklar

- Tarama ve analizde mevcut iptal mekanizmalarını incele; yalnızca geç sonuçları gizlemekle kalmayıp mümkün olan işi de durdur.
- Uzun döngülerde işbirlikçi iptal, sınırlı worker havuzları ve kontrollü subprocess sonlandırması kullan.
- TUI'de taramayı durdurma eylemi sun; diğer arayüzlerde aynı çekirdek davranışı kullan.
- Tamamlandı, kısmi, iptal edildi ve başarısız durumlarını ayır.
- Erişilemeyen hedefleri ve nedenlerini özetle; TCC/Full Disk Access engellerini kullanıcıya anlaşılır biçimde bildir.
- Kısmi tarama sonucundan toplu temizliğe sessizce geçme; desteklenecekse ayrı inceleme ve açık onay gerektir.

### Tamamlanma kriteri

- [x] İptal sonrası yeni tarama işi planlanmaz; çalışan işler güvenli kontrol noktalarında sonlanır.
- [x] İptal edilen veya eski nesle ait sonuçlar aktif ekranı değiştiremez.
- [x] İzin hatasıyla eksik kalan tarama, “her şey temiz” diye raporlanmaz.
- [x] Yavaş tarama, ardışık profil değişimi ve hata sırasında TUI duyarlı kalır.
- [x] Mutasyon iptali, tarama iptaliyle karıştırılmaz; süren dosya işlemi zorla yarıda kesilmez.

## 5. Somut göstergelere dayalı Mac sağlık ekranı

**Öncelik:** Orta · **Bağımlılık:** 1, 3–4

### Uygulanan

- [x] Ortak `HealthIndicator` modeli disk alanı, macOS bellek baskısı, termal durum ve pil sağlığını durum/değer/gerekçe/öneri/ölçüm zamanı alanlarıyla taşıyor.
- [x] Bellek uyarısı ham RAM doluluk oranından değil, macOS `memory_pressure -Q` çıktısındaki kullanılabilir baskı payından üretiliyor; okuma başarısızsa değer “bilinmiyor” kalıyor.
- [x] Disk uyarı eşikleri hem yüzdeyi hem kullanılabilir baytı açıkça kullanıyor ve Data volume ölçüm temelini belirtiyor.
- [x] Termal durum `pmset` uyarı seviyelerinden, pil sağlığı `ioreg` smart-battery koşulundan okunuyor; komut/sensör hataları normal sayılmıyor.
- [x] Pili olmayan Mac “uygulanamaz”, varlığı veya sağlık durumu kanıtlanamayan pil “bilinmiyor” olarak ayrılıyor.
- [x] Pahalı native ölçümler thread-safe olarak 30 saniye cache'leniyor; TUI bunları arka plan worker'ında çalıştırıyor.
- [x] TUI, CLI ve Web aynı ortak sağlık özetini gösteriyor; keyfî sağlık puanı, performans vaadi, otomatik temizlik veya sistem mutasyonu eklenmedi.
- [x] Kısıtlı süreç/boot görünürlüğü bütün durum ekranını çökertmiyor; ilgili ikincil veri güvenle boş bırakılıyor.
- [x] Eksik pil, okunamayan sensör/komut, eşik uyarıları, yalnız ioreg üzerinden okunan pil ve probe rate-limit senaryoları izole testlerle doğrulandı.
- [x] Doğrulama: toplam 194 test, JavaScript sözdizimi kontrolü, Python `compileall` ve `uv build` başarılı.

### Yapılacaklar

- Mevcut sistem durumu ve doctor yeteneklerini tekrar kullan; iş mantığını TUI'ye taşıma.
- Desteklenen ölçümleri göster:
  - Disk boşluğu ve alan baskısı.
  - Bellek baskısı; yalnızca RAM doluluk yüzdesini sorun sayma.
  - Termal durum ve mevcutsa pil sağlığı.
- Her göstergeye güncellik bilgisi, kısa açıklama ve gerektiğinde güvenli öneri ekle.
- Desteklenmeyen veya okunamayan ölçümü “normal” yerine “bilinmiyor” olarak göster.
- Pahalı sorguları arka planda ve sınırlı sıklıkta çalıştır.

### Tamamlanma kriteri

- [x] Keyfî sağlık puanı veya garanti edilen performans artışı iddiası bulunmaz.
- [x] Uyarılar somut ölçüme ve belgelenmiş gerekçeye dayanır.
- [x] Sağlık ekranı otomatik temizlik, process öldürme veya sistem ayarı değişikliği yapmaz.
- [x] Eksik pil, desteklenmeyen sensör ve komut hatası senaryoları test edilir.

## 6. macOS uyumluluğu ve sürüm hazırlığı

**Öncelik:** Yayın kapısı · **Bağımlılık:** Önceki aşamalar

### Uygulanan

- [x] Destek sözleşmesi macOS 13+, Python 3.11+, Apple Silicon ve Intel hedefleri olarak README ve paket sınıflandırıcılarında açıklandı.
- [x] Ortak Doctor çıktısı macOS, Python ve mimari desteğini yapılandırılmış `ok` durumu ile raporluyor; Web UI bilinmeyen/başarısız kontrolleri başarılı göstermiyor.
- [x] `arm64` ve `x86_64` tanıma yolları, desteklenmeyen macOS/Python/mimari, eksik PATH ve manager, boş envanter, izin reddi ve Unicode/boşluk içeren subprocess argümanları izole testlerle kapsandı.
- [x] Paket, Python modülü ve Web UI sürüm bilgilerinin aynı kalmasını sağlayan regresyon testi eklendi.
- [x] TUI bütün araçlarda 80×24 ve 120×40 klavye akışlarıyla; yeniden taramada eski durum temizliği ve işlem sonrası güvenli dönüşle doğrulandı.
- [x] CLI dry-run/açık onay ile Web Host/Origin/session/mutation kilidi regresyonları tam paket içinde geçti.
- [x] 2026-09-11 yerel doğrulaması macOS 26.2 (25C56), Apple Silicon ve Python 3.11.15 üzerinde yapıldı; fiziksel Intel ve macOS 13–15 doğrulaması bulunmadığı README'de açıkça belirtildi.
- [x] Doğrulama: toplam 201 test, JavaScript sözdizimi kontrolü, Python `compileall` ve `uv build` başarılı.

### Yapılacaklar

- Desteklenen Python ve macOS kapsamını belgelerle netleştir.
- Apple Silicon ve Intel üzerinde mevcut imkânlara göre ayrı doğrulama yap; doğrulanamayan ortamları açıkça belirt.
- Eksik PATH, bulunamayan manager, boş envanter, Unicode/boşluk içeren yollar ve izin hatalarını test et.
- TUI'yi en az 80×24 ve 120×40 boyutlarında; hızlı gezinme, yeniden tarama ve işlem sonrası dönüş akışlarıyla doğrula.
- CLI dry-run, açık onay ve Web Host/Origin/session kontrollerinin regresyon testlerini çalıştır.
- Kullanıcıya görünen değişiklikleri ve ölçüm sınırlamalarını README'ye ekle.

### Tamamlanma kriteri

- [x] Tam test paketi, `uv run python -m compileall -q src/deepclean` ve `uv build` başarılıdır.
- [x] Gerçek sistemdeki kontroller salt okunurdur; mutasyon testleri izole ortamdadır.
- [x] Doğrulanan mimariler/sürümler ve kalan kısıtlar kayıtlıdır.

## Uygulama sırası ve çalışma kuralı

**1 → 2 → 3 → 4 → 5 → 6**

Her aşamada: mevcut davranışı incele → küçük değişiklik yap → ilgili testleri çalıştır → güvenlik regresyonlarını kontrol et → sonucu belgele. Ortaya çıkan güvenlik kusurları sırayı keser ve öncelik alır. Her aşamanın sonunda bu belgedeki durum güncellenir; test edilmemiş özellik tamamlanmış sayılmaz.

## Kapsam dışında

- RAM temizleme ve rutin memory purge.
- Otomatik Docker/Podman volume veya container silme.
- SIP, TCC veya Gatekeeper'ı devre dışı bırakma.
- Genel yetki yükseltme veya uygulamayı root çalıştırma.
- Kullanıcı verisini sıradan cache gibi sınıflandırma.
- Belgelenmemiş kalıcı sistem ayarları ve otomatik agresif optimizasyonlar.
