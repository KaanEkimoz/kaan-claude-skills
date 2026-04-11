---
name: en-to-tr-pdf-translation
description: "İngilizce kitap PDF'lerini Türkçe'ye profesyonel kalitede çeviren skill. Sadece İngilizce'den Türkçe'ye kitap/doküman çevirisi yapar. Bu skill'i şu durumlarda kullan: kullanıcı bir İngilizce PDF'i Türkçe'ye çevirmek istediğinde, İngilizce bir kitabın Türkçe çevirisini istediğinde, \"çevir\", \"translate\", \"Türkçe'ye çevir\", \"kitap çevirisi\", \"PDF çevirisi\" gibi ifadeler kullandığında, veya İngilizce bir dokümanın Türkçe versiyonunu istediğinde. Kısaca: İngilizce PDF + Türkçe çeviri = bu skill. Başka dil çiftleri için kullanma."
---

# İngilizce'den Türkçe'ye PDF Kitap Çevirisi

İngilizce kitap ve doküman PDF'lerini profesyonel yayın kalitesinde Türkçe'ye çevirir. Hedef: orijinal sayfa görünümünü (görseller, tablolar, font, düzen) bit-düzeyinde koru, sadece metnin dilini değiştir. Türkçe okuyucu kitabı sanki orijinali Türkçe yazılmış gibi okumalı.

## Dosya Yapısı

```
en-to-tr-pdf-translation/
├── SKILL.md
├── scripts/                   ← saf Python, CLI ile çağır
│   ├── pipeline.py
│   ├── overlay.py
│   ├── extract_page.py        ← PDF sayfa → PNG + spans.json
│   ├── overlay_page.py        ← PNG + spans + translations → TR PNG + qc.json
│   ├── assemble_pdf.py        ← TR PNG'leri PDF'e birleştir
│   ├── glossary.py            ← paylaşılan terminoloji sözlüğü
│   └── cache.py               ← çeviri önbelleği
└── references/
    ├── translation_rules.md   ← ilk sayfadan önce oku
    ├── agents.md              ← çok bölümlü kitaba başlamadan önce oku
    ├── vision_prompt.md       ← vision çağrısı şablonu
    ├── overflow_control.md    ← QC adımında oku
    └── known_pitfalls.md      ← beklenmedik bir durumda oku
```

## Pipeline

Her sayfa aynı pipeline'dan geçer:

1. `extract_page.py` → PNG + spans.json
2. `cache.py apply` → bilinen çevirileri translations.json'a yaz
3. Vision çağrısı → kalan benzersiz span'lar için Türkçe çeviri üret
4. `overlay_page.py` → arka planı örnekle, orijinali sil, Türkçeyi sığdır, `page_NNN_qc.json` yaz
5. Yeni çevirileri `cache.py put` ile kalıcılaştır

Tüm CLI script'leri stdout'a JSON basar; agent bunu parse ederek durumunu günceller. Stderr sadece hata için.

PNG sayfanın tıpkısıdır: fotoğraflar, çizimler, tablo çizgileri bit-düzeyinde korunur. Sadece metin span'larının üstüne Türkçe yazılır. Vektör/path olarak çizilmiş metinler vision adımında `extras` alanına yakalanır.

## Çeviri Kuralları

İlk sayfayı çevirmeden önce **`references/translation_rules.md`** oku. Yayın çevirisi, birebir değil; doğal Türkçe akışı esas.

## Çok Ajanlı İş Akışı

Üç rol:

- **Koordinatör** (ana seans, Sonnet): plan, paylaşılan dosyalar, subagent başlatma, birleştirme. Çeviri yapmaz.
- **Çevirmen subagent** (bölüm başına bir tane, paralel, **her zaman Opus**): sayfa pipeline'ı + vision çağrıları. Birinci bölüm dahil bütün bölümler bir Opus çevirmen subagent'a atanır; koordinatör hiçbir sayfayı kendi çevirmez.
- **QC subagent** (bölüm bittikten sonra, Haiku): `overlay_page.py`'nin bıraktığı `page_NNN_qc.json` dosyalarını okur, sadece flagged sayfaları gözle doğrular.

Prompt şablonları, paralellik kuralları, glossary/cache kilit davranışı için **`references/agents.md`**. Çok bölümlü bir kitaba başlamadan önce oku.

## İş Akışı

### Aşama 0: Hazırlık (koordinatör)

1. PDF'i aç, bölüm yapısını ve sayfa sayısını çıkar.
2. İlk birkaç sayfadan baskın fontları belirle (`get_text("dict")`).
3. Kullanıcıya plan sun: kitap bilgisi, bölüm yapısı, bölüm başına tahmini sayfa, font tespiti, özel isim listesi (çevrilmeyecekler).
4. Onay al.
5. Çalışma dizinini kur:
   ```bash
   python -m scripts.glossary init --path work/glossary.json
   python -m scripts.cache init --path work/cache.json
   mkdir -p work/ch01 work/ch02 ...
   ```
6. Paragraf gruplama kalibrasyonu çalıştır:
   ```bash
   python -m scripts.extract_page --pdf book.pdf --page 0 \
       --out-dir work/calib --calibrate --save-config work/grouping.json
   ```
   Bu, `group_line_spans_into_paragraphs` eşiklerini (x_close, y_adjacent) bu kitap için optimize eder. Sonraki tüm `extract_page` çağrıları `--config work/grouping.json` ile bu ayarları kullanır.

### Aşama 1: Paralel Çeviri (Opus çevirmen subagent'ları)

Birinci bölüm dahil her bölüm için bir Opus çevirmen subagent başlat. Görev tanımı şablonu `references/agents.md`'de. Çevirmen her sayfa için şu akışı izler:

- `extract_page` → `cache apply` → vision → `overlay_page` → `cache put`

`cache apply`'ın JSON çıktısında `uncovered` listesi bulunur; vision çağrısına sadece bu metinler gider. Vision prompt'una her span'ın bbox genişliği ve font boyutu zorunlu olarak eklenir (şablon için `references/vision_prompt.md`).

### Aşama 2: QC (QC subagent'ları)

Her bölüm bittiğinde Haiku QC subagent'ı başlat. QC'nin ilk adımı: her sayfanın `page_NNN_qc.json` dosyasını oku. Bu dosya `overlay_page.py` tarafından deterministik üretilir ve şu anomalileri içerir:

- `small_font` — `fit_text_in_bbox` son çareye düşmüş
- `wrapped_lines` — çeviri 2 veya 3 satıra sarılmış
- `horizontal_overlap` — span bbox'ı komşu bir span'ın bbox'ıyla kesişmiş
- `vertical_overlap` — çeviri alt satıra taşmış
- `missing_font_variant` — Bold/Italic varyantı bulunamamış, Regular'a düşülmüş

`clean: true` olan sayfalar atlanır (QC PNG'yi yüklemez). `clean: false` sayfalar için QC PNG'yi açar, `references/overflow_control.md`'deki 5 çakışma tipi rehberine göre doğrular ve flagged rapor döner:

```json
{
  "chapter": "ch[NN]",
  "total_pages": N,
  "deterministic_clean": K,
  "flagged": [{"page": 3, "issue_type": "...", "span_text": "...", "note": "..."}]
}
```

Koordinatör flagged sayfalar için düzeltme döngüsü çalıştırır:
1. translations.json'da ilgili terimi kısalt, gerekirse glossary'yi güncelle.
2. `overlay_page.py`'yi tekrar çalıştır (yeni `page_NNN_qc.json` üretilir).
3. QC'yi flagged listeye tekrar bak.

### Aşama 3: Birleştirme (koordinatör)

```bash
python -m scripts.assemble_pdf \
    --pages-dirs work/ch01 work/ch02 ... \
    --pattern "page_*_tr.png" \
    --out output/ceviri_final.pdf \
    --page-numbers
```

Varsa içindekiler tablosunu orijinal sayfa numaralarından yeni numaralara eşle. Glossary'yi ek olarak dahil etmeyi kullanıcıya sor.

## Son Kontrol Listesi

- Tüm bölümler çevrildi ve QC taraması geçildi mi?
- Flagged sayfaların düzeltme döngüsü kapandı mı?
- Vektör grafik metni yakalanamayan sayfaların listesi kullanıcıya iletildi mi?
- Glossary ek olarak dahil edilsin mi? (kullanıcıya sor)
- Sayfa numaraları final PDF'te doğru mu?
- Türkçe karakterler (ç, ğ, ı, ö, ş, ü, İ) doğru render oluyor mu?

## Kullanıcıya Raporlama

Her bölüm bittiğinde kısa özet ver: sayfa sayısı, yeni glossary terim sayısı, deterministik temiz / flagged sayfa sayısı, çakışma tipleri. Belirsiz terimlerde varsayım yapma, kullanıcıya sor. Uzun kitaplarda ilerleme bildir ("3/12 bölüm"). Vektör grafik metni yakalanamamış sayfalar varsa listeyi göster.

## Beklenmedik Durum

Bir sayfada tuhaflık fark edersen (satır satır İngilizce kalmış paragraf, ortada atlanmış cümle, vektör grafik etiketi yakalanmamış, son çareye düşen küçük font): **`references/known_pitfalls.md`**.
