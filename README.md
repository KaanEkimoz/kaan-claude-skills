# kaan-claude-skills

Claude Code için yazılmış kişisel skill koleksiyonu. Her skill, tek bir `.skill` bundle dosyası olarak dağıtılır ve Claude Code tarafından doğrudan yüklenip kullanılabilir.

---

## Skills

| Skill | Ne yapar |
|---|---|
| [`en-to-tr-pdf-translation-v3.skill`](./en-to-tr-pdf-translation-v3.skill) | İngilizce kitap PDF'lerini sayfa düzenini koruyarak Türkçe'ye çevirir. |
| [`auzef-course-downloader.skill`](./auzef-course-downloader.skill) | AUZEF ders materyallerini indirip baskıya hazır PDF'e çevirir. |
| [`notebooklm-video-generator.skill`](./notebooklm-video-generator.skill) | NotebookLM'de kaynak başına Türkçe açıklayıcı video üretir. |
| [`chatgpt-gorsel-uretme.skill`](./chatgpt-gorsel-uretme.skill) | ChatGPT web arayüzünü Chrome'dan sürerek görsel üretir ve indirir. |
| [`gemini-gorsel-uretme.skill`](./gemini-gorsel-uretme.skill) | Gemini web arayüzünü Chrome'dan sürerek görsel üretir ve indirir. |
| [`meshy-3d-assets.skill`](./meshy-3d-assets.skill) | Meshy AI ile oyun için 3D model üretip Unity'ye aktarır. |
| [`bilgisayari-kapat.skill`](./bilgisayari-kapat.skill) | İş bitince işi kaydedip Mac'i kapatır. |
| [`tr-alisveris.skill`](./tr-alisveris.skill) | idefix, Trendyol, Hepsiburada ve D&R'da ürün araştırıp sepete ekler. |
| [`mac-app-uninstaller.skill`](./mac-app-uninstaller.skill) | Mac uygulamasını tüm artık dosyalarıyla birlikte kaldırır. |

---

### `en-to-tr-pdf-translation` &mdash; İngilizce PDF → Türkçe Profesyonel Çeviri

**Bundle:** [`en-to-tr-pdf-translation-v3.skill`](./en-to-tr-pdf-translation-v3.skill)

İngilizce kitap ve doküman PDF'lerini, sayfa düzenini bozmadan, **yayın kalitesinde** Türkçe'ye çeviren komple bir pipeline. Birebir kelime çevirisi değil; doğal Türkçe akışını esas alan, çevirmen subagent'larla paralelleşen, deterministik ve cache'lenebilir bir sistem.

#### Ne işe yarar?

- Çok bölümlü İngilizce kitapları girdi olarak alır.
- Her sayfanın orijinal layout'unu (font, paragraf konumu, satır kırılımları) koruyarak Türkçe karşılığını üretir.
- Çıktı olarak tek bir, sayfa numaralandırılmış Türkçe PDF döner.

#### Pipeline mimarisi

Her sayfa aynı deterministik akıştan geçer:

```
extract_page  →  cache apply  →  vision  →  overlay_page  →  cache put
```

1. **`extract_page`** &mdash; PDF sayfasından span'ları (metin parçalarını) çıkarır, paragraf gruplarına böler. İlk çağrıda kitaba özgü `x_close` / `y_adjacent` eşikleri kalibre edilir ve `work/grouping.json` içine kaydedilir.
2. **`cache apply`** &mdash; Daha önce çevrilmiş span'ları cache'ten uygular. Yalnızca `uncovered` listesi vision modeline gider; aynı cümleyi iki kez çevirmez.
3. **Vision çağrısı** &mdash; Çevrilmemiş metinler, her span'ın bbox genişliği ve font boyutu zorunlu olarak eklenmiş bir prompt ile (`references/vision_prompt.md` şablonu) çevirmen subagent'a gönderilir.
4. **`overlay_page`** &mdash; Türkçe karşılıklar, orijinal sayfanın üstüne piksel düzeyinde overlay'lenir. Taşma kontrolü (`references/overflow_control.md`'deki 5 çakışma tipi) burada uygulanır.
5. **`cache put`** &mdash; Yeni çeviriler cache'e yazılır; sonraki sayfalarda veya sonraki çalıştırmalarda yeniden kullanılabilir.

Bittiğinde tüm sayfalar `assemble_pdf` ile birleştirilir:

```bash
python -m scripts.assemble_pdf \
    --pages-dirs work/ch01 work/ch02 ... \
    --pattern "page_*_tr.png" \
    --out output/ceviri_final.pdf \
    --page-numbers
```

#### Paralellik

Birinci bölüm dahil her bölüm için ayrı bir Opus çevirmen subagent başlatılır. Görev tanımı şablonu ve glossary/cache kilit davranışı `references/agents.md` içinde tanımlı &mdash; çok bölümlü bir kitaba başlamadan önce mutlaka okunmalı.

#### Kalite kontrolü

Her sayfa render sonrası QC'den geçer:

- `clean: true` olan sayfalar atlanır (QC PNG'yi yüklemez).
- `clean: false` sayfalar için QC PNG açılır, `references/overflow_control.md`'deki çakışma tipi rehberine göre doğrulanır ve flagged rapor üretilir.

Çeviri ilkeleri (yayın kalitesi, doğal akış, özel isim listesi, terim tutarlılığı) `references/translation_rules.md` içinde; sık karşılaşılan hata kalıpları `references/known_pitfalls.md` içinde belgeli.

#### Bundle içeriği

```
en-to-tr-pdf-translation-v3.skill
├── SKILL.md                      # Skill manifest + üst seviye akış
├── scripts/
│   ├── pipeline.py               # Tüm akışı orkestre eden entrypoint
│   ├── extract_page.py           # Span çıkarma + paragraf gruplama
│   ├── glossary.py               # Özel isim / terim sözlüğü
│   ├── cache.py                  # Span bazlı çeviri cache'i
│   ├── overlay.py                # Overlay motoru (taşma kontrolü)
│   ├── overlay_page.py           # Sayfa bazında overlay
│   └── assemble_pdf.py           # Tek PDF'e birleştirme
└── references/
    ├── agents.md                 # Subagent görev şablonu + paralellik kuralları
    ├── vision_prompt.md          # Vision çağrısı prompt şablonu
    ├── translation_rules.md      # Yayın çevirisi ilkeleri
    ├── overflow_control.md       # 5 çakışma tipi rehberi
    └── known_pitfalls.md         # Bilinen hata kalıpları
```

#### Nasıl kullanılır?

Claude Code'a `.skill` dosyasını yükle ve doğal dilde iste:

> "Bu İngilizce kitap PDF'ini Türkçe'ye çevir."

Skill otomatik olarak tetiklenir, kitap bilgisi + bölüm yapısı + font tespiti + özel isim listesi içeren bir plan sunar, onay aldıktan sonra pipeline'ı çalıştırır.

---

## Repo yapısı

```
kaan-claude-skills/
├── README.md
└── *.skill        # Her skill tek bir bundle dosyası
```

Her skill, kendi kendine yeten tek bir `.skill` bundle dosyası olarak repo köküne eklenir.
