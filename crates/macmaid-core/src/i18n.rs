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
        m
    });
