use std::collections::HashMap;

pub fn translate<'a>(key: &'a str, lang: &str) -> &'a str {
    match lang {
        "tr" => TRANSLATIONS_TR.get(key).copied().unwrap_or(key),
        _ => TRANSLATIONS_EN.get(key).copied().unwrap_or(key),
    }
}

static TRANSLATIONS_EN: std::sync::LazyLock<HashMap<&'static str, &'static str>> =
    std::sync::LazyLock::new(|| {
        let mut m = HashMap::new();
        m.insert("ARAÇ SEÇ", "SELECT TOOL");
        m.insert("Ayarlar / Settings", "Settings");
        m.insert("Araç Sonuçları", "Tool Results");
        m.insert("Uygulama Kaldırıcı", "App Uninstaller");
        m.insert("Disk Alanı Analizörü", "Disk Analyzer");
        m.insert("Mac Sağlığı", "Mac Health");
        m.insert("Ayarlar", "Settings");
        m.insert("Dosyalar ve Depolama", "Files & Storage");
        m.insert("Sistem ve Geçmiş", "System & History");
        m.insert("Choose cleanup profile", "Choose Cleanup Profile");
        m.insert("Temizlik Profili Seç", "Choose Cleanup Profile");
        m.insert("Temizlik", "Clean");
        m.insert("Uygulama Kaldır", "Uninstall Apps");
        m.insert("Analiz", "Analyze");
        m.insert("Proje Temizliği", "Project Purge");
        m.insert("Geliştirici Araçları", "Developer Tools");
        m.insert("Bellek Yönetimi", "Memory Management");
        m.insert("Kopya Dosyalar", "Duplicate Finder");
        m.insert("Büyük ve Eski Dosyalar", "Large & Old Files");
        m.insert("İndirilenler", "Smart Downloads");
        m.insert("Geçmiş ve Geri Yükleme", "History & Restore");
        m.insert("Güvenli Liste", "Whitelist");
        m.insert("Tara", "Scan");
        m.insert("Temizle", "Clean");
        m.insert("İptal", "Cancel");
        m.insert("Uygula", "Apply");
        m.insert("Kaldır", "Uninstall");
        m.insert("Sonlandır", "Terminate");
        m.insert("Geri Yükle", "Restore");
        m.insert("Yenile", "Refresh");
        m.insert("Tamamlandı", "Completed");
        m.insert("Başarısız", "Failed");
        m.insert("Atlandı", "Skipped");
        m.insert("Çalışıyor", "Running");
        m.insert("Hazır", "Ready");
        m.insert("Dil", "Language");
        m.insert("Bildirim", "Notice");
        m.insert("Tamam", "OK");
        m.insert("Geri", "Back");
        m
    });

static TRANSLATIONS_TR: std::sync::LazyLock<HashMap<&'static str, &'static str>> =
    std::sync::LazyLock::new(|| {
        let mut m = HashMap::new();
        m.insert("SELECT TOOL", "ARAÇ SEÇ");
        m.insert("Settings", "Ayarlar");
        m.insert("Tool Results", "Araç Sonuçları");
        m.insert("App Uninstaller", "Uygulama Kaldırıcı");
        m.insert("Disk Analyzer", "Disk Analizörü");
        m.insert("Mac Health", "Mac Sağlığı");
        m.insert("Files & Storage", "Dosyalar ve Depolama");
        m.insert("System & History", "Sistem ve Geçmiş");
        m.insert("Choose Cleanup Profile", "Temizlik Profili Seç");
        m.insert("Clean", "Temizlik");
        m.insert("Uninstall Apps", "Uygulama Kaldır");
        m.insert("Analyze", "Analiz");
        m.insert("Project Purge", "Proje Temizliği");
        m.insert("Developer Tools", "Geliştirici Araçları");
        m.insert("Memory Management", "Bellek Yönetimi");
        m.insert("Duplicate Finder", "Kopya Dosyalar");
        m.insert("Large & Old Files", "Büyük ve Eski Dosyalar");
        m.insert("Smart Downloads", "İndirilenler");
        m.insert("History & Restore", "Geçmiş ve Geri Yükleme");
        m.insert("Whitelist", "Güvenli Liste");
        m.insert("Scan", "Tara");
        m.insert("Cancel", "İptal");
        m.insert("Apply", "Uygula");
        m.insert("Uninstall", "Kaldır");
        m.insert("Terminate", "Sonlandır");
        m.insert("Restore", "Geri Yükle");
        m.insert("Refresh", "Yenile");
        m.insert("Completed", "Tamamlandı");
        m.insert("Failed", "Başarısız");
        m.insert("Skipped", "Atlandı");
        m.insert("Running", "Çalışıyor");
        m.insert("Ready", "Hazır");
        m.insert("Language", "Dil");
        m.insert("Storage Treemap", "Depolama Ağaç Haritası");
        m.insert("Scan Disk", "Diski Tara");
        m.insert("Scan Home Directory", "Ana Dizini Tara");
        m.insert("Visual Storage Treemap", "Görsel Depolama Ağaç Haritası");
        m.insert(
            "Visualize disk space consumption with interactive proportional boxes.",
            "Etkileşimli orantılı kutularla disk alanı tüketimini görselleştirin.",
        );
        m.insert("Back", "Geri");
        m.insert("Reveal in Finder", "Finder'da Göster");
        m.insert("Move to Trash", "Çöp Sepetine Taşı");
        m.insert("Notice", "Bildirim");
        m.insert("OK", "Tamam");
        m.insert("Profile", "Profil");
        m.insert("Safe", "Güvenli");
        m.insert("Deep", "Derin");
        m.insert("Developer", "Geliştirici");
        m.insert("Aggressive", "Agresif");
        m.insert("Include Trash", "Çöpü Dahil Et");
        m.insert("System Temp", "Sistem Geçici Dosyaları");
        m.insert("Min Size", "Min Boyut");
        m.insert("Directory", "Dizin");
        m.insert("Age", "Yaş");
        m.insert("Any Time", "Her Zaman");
        m.insert("Select All", "Tümünü Seç");
        m.insert("Deselect All", "Seçimi Kaldır");
        m.insert("Trash Selected", "Seçilenleri Çöpe Taşı");
        m.insert("Select Duplicates", "Kopyaları Seç");
        m.insert("Original", "Orijinal");
        m.insert("Duplicate", "Kopya");
        m.insert("Older than", "Daha eski");
        m.insert("days", "gün");
        m.insert(
            "Downloads Cleanup Potential",
            "İndirilenler Temizleme Potansiyeli",
        );
        m.insert("Select Safe Cleanable", "Güvenli Temizlenebilirleri Seç");
        m.insert(
            "Installers (.dmg, .pkg, .iso)",
            "Yükleyiciler (.dmg, .pkg, .iso)",
        );
        m.insert("Archives (.zip, .tar, .7z)", "Arşivler (.zip, .tar, .7z)");
        m.insert(
            "Incomplete Downloads (.crdownload, .part)",
            "Tamamlanmamış İndirmeler (.crdownload, .part)",
        );
        m.insert(
            "Duplicate Downloads (e.g. file (1).ext)",
            "Kopya İndirmeler (örn. dosya (1).uzantı)",
        );
        m.insert(
            "Smart Downloads Categorizer",
            "Akıllı İndirilenler Kategorilendirici",
        );
        m.insert("Group by App", "Uygulamaya Göre Grupla");
        m.insert("Filter processes...", "Süreçleri filtrele...");
        m.insert("All", "Tümü");
        m.insert("Applications", "Uygulamalar");
        m.insert("High Memory", "Yüksek Bellek");
        m.insert("Protected", "Korumalı");
        m.insert("Terminate (SIGTERM)", "Sonlandır (SIGTERM)");
        m.insert("Kill (SIGKILL)", "Zorla Kapat (SIGKILL)");
        m.insert(
            "Time Machine APFS Snapshots",
            "Time Machine APFS Anlık Görüntüleri",
        );
        m.insert("local snapshot(s)", "yerel anlık görüntü");
        m.insert("Target", "Hedef");
        m.insert("Thin Snapshots", "Anlık Görüntüleri Azalt");
        m.insert(
            "No local APFS snapshots found on root volume.",
            "Kök birimde yerel APFS anlık görüntüsü bulunamadı.",
        );
        m.insert(
            "Software Updates & Release Channel",
            "Yazılım Güncellemeleri ve Sürüm Kanalı",
        );
        m.insert("Installation Channel:", "Kurulum Kanalı:");
        m.insert("Installed", "Yüklü");
        m.insert("Check for Updates", "Güncellemeleri Denetle");
        m.insert("New version available", "Yeni sürüm mevcut");
        m.insert("View Release", "Sürümü Görüntüle");
        m.insert("MacMaid is up to date.", "MacMaid güncel.");
        m.insert("Purge to Trash", "Çöpe Temizle");
        m.insert("Managed tool / runtime", "Yönetilen araç / çalışma ortamı");
        m.insert("Finder", "Finder");
        m
    });
