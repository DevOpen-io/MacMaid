# MacMaid TUI Parity Roadmap

Bu roadmap yalnızca Web GUI'de mevcut olup TUI'da henüz bulunmayan veya aynı esneklikte sunulmayan özellikleri içerir.

## Teslim Standardı

Her madde ortak backend ve güvenlik modelini kullanmalıdır:

```text
Discover → Classify → PathSafety → Whitelist → Preview → Confirmation → Execute → Verify → History
```

- Tarama işlemleri arka planda, iptal edilebilir ve symlink takip etmeden çalışır.
- Kullanıcı verisi varsayılan olarak seçilmez.
- Dosya işlemleri mümkün olduğunda Trash'e taşınır.
- Yeni TUI kontrolleri klavye ile erişilebilir, açıklayıcı ve responsive olmalıdır.

## Öncelik 1 — Ayarlar ve Uygulama Yönetimi

### TUI Settings ekranı

- [x] Whitelist'i sadece görüntülemek yerine TUI içinden güvenli biçimde düzenleme ve kaydetme.
- [x] Arayüz dili seçimi (Türkçe / English).
- [x] Ayarların kaydedildiğine veya hata oluştuğuna dair açık geri bildirim.

### İzin Durumu

- [x] Okunabilen, sınırlı ve erişilemeyen cleanup konumlarının özetini göster.
- [x] Tam Disk Erişimi durumunu ve uygulama/CLI bağlamını göster.
- [x] Engellenen konumların ayrıntılarını listede sun.
- [x] Kullanıcı isterse macOS Full Disk Access ayarlarını açan güvenli aksiyon ekle.

### Güncelleme Yönetimi

- [x] Homebrew kurulumu için güncelleme denetimi ekle.
- [x] Yeni sürüm varsa mevcut ve hedef sürümü göster.
- [x] Yalnızca açık onay sonrası Homebrew ile güncelleme başlat.
- [x] Homebrew ile kurulmayan uygulamalarda anlaşılır, salt-okunur durum mesajı göster.

## Öncelik 2 — Görsel Disk Keşfi ve Snapshot Yönetimi

### Time Machine Snapshot Thinning

- [x] Yerel APFS snapshot listesinin yanında 10 / 20 / 50 GB hedefli thinning seçeneklerini sun.
- [x] Apple'ın snapshot'ları otomatik yönettiğini ve işlemin yalnızca acil alan ihtiyacı için olduğunu açıkça belirt.
- [x] Uygulama öncesinde hedef reclaim miktarını ve etkisini onay ekranında göster.
- [x] Komut sonucu, hata ve tahmini/ölçülen kazanımı history'ye yaz.

## Öncelik 3 — Mevcut Dosya Araçları İçin Filtre Paritesi

### Application Leftovers

- [x] Yaş filtresi ekle: tümü, 14 gün ve 30 gün.
- [x] Application Support / Containers kullanıcı verisini dahil etmeyi ayrı, varsayılan kapalı bir opt-in olarak sun.

### Old Installers

- [x] Minimum yaş filtresi ekle: tümü, 7, 14 ve 30 gün.

### Smart Downloads

- [x] Eski indirmeler için 30 / 90 / 180 / 365 gün filtresi ekle.

### Large & Old Files

- [x] Boyut filtresi ile yaş filtresini aynı ekranda bağımsız seçilebilir yap.
- [x] Yaş seçenekleri: tümü, 30, 90, 180 ve 365 gün.
- [x] Mevcut 500 MB / 1 GB / 5 GB / 10 GB boyut eşiklerini koru.

## Öncelik 4 — TUI İşlem Geri Bildirimi

- [ ] GUI'deki canlı log akışına denk, tarama/işlem sırasında açılıp kapanabilen bir TUI olay günlüğü ekle.
- [ ] Aktif yol, aşama, yüzde ve bulunan öğe sayısını aynı görünümde göster.
- [ ] Log akışının UI event loop'u engellememesini ve iptal sonrası eski olayları göstermemesini sağla.