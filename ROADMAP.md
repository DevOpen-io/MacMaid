# MacMaid — v1.0.0 Yolu ve Sonrası

Tüm harita kararları çözüldü: [issue #26](https://github.com/DevOpen-io/MacMaid/issues/26).
Bu dosya, tag'lenmemiş kalan işleri ve post-1.0 backlog'unu listeler.

Her madde ortak backend ve güvenlik modelini kullanmalıdır:

```text
Discover → Classify → PathSafety → Whitelist → Preview → Confirmation → Execute → Verify → History
```

## v1.0.0 Release Bar'ı (onaylı)

Tag ancak şunların tamamı sağlanınca atılır:

- [ ] `uv run ruff check src/macmaid tests_py` → 0 hata
- [ ] `uv run mypy` → 0 hata
- [ ] `uv run pytest tests_py -q` → tamamı yeşil
- [ ] Dört sürüm yüzeyi `1.0.0`'da senkron: `pyproject.toml`, `src/macmaid/__init__.py`, `uv.lock`, `src/macmaid/WebUI/index.html`
- [ ] README / SECURITY / FAQ iddiaları koda karşı doğru
- [ ] **Temiz makinede manuel smoke testi** (tag öncesi şart):
  - DMG'den kurulum → Gatekeeper akışı (Open Anyway / quarantine) beklenen gibi
  - Full Disk Access ver → `macmaid doctor` "Granted" raporluyor
  - Bir gerçek Smart Clean turu: preview → review → uygula → history'de kayıt
- [ ] `main`'e push → release CI `v1.0.0` immutable tag + GitHub Release + sha256 asset'leri + Homebrew tap güncellemesi
- [ ] Release sonrası doğrulama: `brew install --cask macmaid` ve DMG indirme gerçekten çalışıyor

## Kararlar (1.0 için kilitli)

- **Platform**: macOS 13+, arm64 paketlenmiş dağıtım; Intel yalnızca source/`install.sh`/`uv tool` (#36)
- **İmzalama**: 1.0 unsigned/unnotarized çıkar; Gatekeeper FAQ yolu kalıcı (#37, tarif #27'de hazır)
- **Update**: kanal-aware `macmaid update`; brew self-apply review-gated, diğer kanallar release linki (#33)
- **Onboarding**: minimal inline FDA/TCC uyarısı tüm yüzeylerde, terminal-app tuzağı dahil (#34)
- **Destek**: issue formları + private vuln reporting + README FAQ; ayrı CHANGELOG yok, Discussions yok (#35)
- **Özellik seti**: donmuş — Smart Clean, Treemap, App removal, Memory, Developer/Browser Storage, Duplicates, Large Files, Smart Downloads, History
- **Semver**: `1.0.0` tag'i CLI komut/flag yüzeyini ve Web API endpoint kontratlarını public yapar; kırıcı değişiklik → `2.0.0`. İç refactor ve UI düzeltmeleri minor/patch'te devam eder

## Sıradaki adımlar (sıralı)

- [ ] 1. Bu session'ın birikmiş 1.0-readiness değişikliklerini `main`'e land et (commit/merge)
- [ ] 2. Yukarıdaki manuel smoke testini gerçek makinede koş
- [ ] 3. Sürüm yüzeylerini `1.0.0`'a çek, kapıları koştur
- [ ] 4. `main`'e push → CI release'ini izle → Homebrew + DMG kurulumunu doğrula

## Post-1.0 backlog (öncelik sırasız)

- **Apple imzalama + notarization** — Developer Program önkoşulu gelince; mekanik tarif [docs/research/notarization-ci.md](https://github.com/DevOpen-io/MacMaid/blob/research/notarization-ci/docs/research/notarization-ci.md) (#27)
- **Intel (x86_64) paketlenmiş build'ler** — x86 runner veya cross-compile CI işi
- **Genişletilmiş lokalizasyon** — CONTRIBUTING/docs İngilizce paritesi ve ek diller
- **Karşılaştırıcı özellik yüzeyleri** — Finder extension, menu-bar widget (gap audit post-1.0 listesi)
- **Support-bundle export + in-app feedback** — tek tıkla teşhis paketi; issue'a eklenebilir çıktı
- **GitHub Discussions / curated CHANGELOG** — yalnızca talep oluşursa
