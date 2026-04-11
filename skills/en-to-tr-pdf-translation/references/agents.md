# Çok Ajanlı İş Akışı

Kitap çevirisi paralellik için idealdir: sayfalar bağımsız, tek paylaşılan durum terminoloji sözlüğü. Üç rol ile çalış.

## Koordinatör (ana seans, Sonnet)

Plan, orkestrasyon, paylaşılan dosyalar, final birleştirme. Çeviri yapmaz — birinci bölüm dahil her bölüm için bir Opus çevirmen subagent başlatılır.

Çalışma dizini kurulumu:

```bash
python -m scripts.glossary init --path work/glossary.json
python -m scripts.cache init --path work/cache.json
python -m scripts.extract_page --pdf book.pdf --page 0 \
    --out-dir work/calib --calibrate --save-config work/grouping.json
mkdir -p work/ch01 work/ch02 ...
```

Her bölüm için bir Opus çevirmen subagent (aşağıdaki şablonla). Bölümler paralel başlatılır. Bir bölüm bittiğinde QC subagent'ı (aşağıdaki şablonla) başlat. QC raporundaki `flagged` sayfalar için düzeltme döngüsü: translations.json'daki terimi kısalt → `overlay_page.py` tekrar → QC flagged listesini yeniden kontrol et. Tüm bölümler temizlendiğinde `assemble_pdf.py` ile final PDF.

## Çevirmen Subagent (bölüm başına bir tane, paralel, Opus)

Görev tanımı şablonu:

```
Sen bu kitabın [bölüm adı / sayfa aralığı] bölümünü çeviren bir
çevirmensin. Skill: en-to-tr-pdf-translation.

Paylaşılan kaynaklar:
- Glossary:       work/glossary.json
- Cache:          work/cache.json
- Grouping cfg:   work/grouping.json
- Çıktı dizini:   work/ch[NN]/

Her sayfa için sırayla:

1. python -m scripts.extract_page --pdf book.pdf --page NNN \
     --out-dir work/ch[NN]/ --config work/grouping.json
   → stdout JSON: {"png", "spans", "span_count"}

2. python -m scripts.cache apply --path work/cache.json \
     --spans work/ch[NN]/page_NNN_spans.json \
     --out   work/ch[NN]/page_NNN_cached.json
   → stdout JSON: {"total", "hit", "uncovered_count", "uncovered": [...]}

3. `uncovered` boş değilse vision çağrısı yap:
   - PNG'yi attach et: work/ch[NN]/page_NNN.png
   - Glossary bloğu için:
       python -m scripts.glossary prompt --path work/glossary.json
   - Prompt şablonu: references/vision_prompt.md
   - Her span için bbox_width ve font_size zorunlu olarak gönderilir
   - Vision cevabını parse et:
     * translations'ı cached.json ile birleştir → translations.json
     * extras varsa spans listesine ekle (overlay öncesi)
     * new_glossary_terms'i kaydet:
         python -m scripts.glossary add --path work/glossary.json \
             --en "..." --tr "..." --note "..."
     * Yeni çevirileri cache'e koy:
         python -m scripts.cache put --path work/cache.json \
             --en "..." --tr "..."

4. python -m scripts.overlay_page \
     --png   work/ch[NN]/page_NNN.png \
     --spans work/ch[NN]/page_NNN_spans.json \
     --translations work/ch[NN]/page_NNN_translations.json \
     --out   work/ch[NN]/page_NNN_tr.png \
     --qc-out work/ch[NN]/page_NNN_qc.json
   → stdout JSON: {"out", "qc", "covered", "total", "clean", "issue_count"}

Çeviri kuralları: references/translation_rules.md
Beklenmedik durum: references/known_pitfalls.md

Bittiğinde rapor et: sayfa sayısı, yeni glossary terim sayısı,
deterministik clean/flagged sayıları, flagged sayfaların listesi.
```

## QC Subagent (bölüm bittikten sonra, Haiku)

Görev tanımı şablonu:

```
Sen bu bölümün kalite kontrolünü yapan bir denetleyicisin. Skill:
en-to-tr-pdf-translation.

Bölüm dizini: work/ch[NN]/

Adım 1 (deterministik, PNG yüklemeden):
  Her page_NNN_qc.json dosyasını oku.
  clean: true olan sayfaları "deterministic_clean" listesine ekle, atla.
  clean: false olan sayfaların listesini tut — sadece bunlar için Adım 2.

Adım 2 (görsel doğrulama, sadece flagged sayfalar):
  Her flagged sayfa için:
    - page_NNN.png ve page_NNN_tr.png'yi yan yana aç
    - page_NNN_qc.json'daki her issue'yu doğrula
    - references/overflow_control.md'deki 5 çakışma tipine göre
      ek bir sorun var mı bak (determinik kontrol kaçırmış olabilir)
  Ek kontrol:
    - Eksik çeviri: İngilizce kalan blok (özel isim/sayı değilse)
    - Karakter sorunları: ç, ğ, ı, ö, ş, ü, İ doğru render
    - Terminoloji tutarsızlığı: glossary'deki kararla çelişen çeviri

Çıktı formatı:
{
  "chapter": "ch[NN]",
  "total_pages": N,
  "deterministic_clean": K,
  "flagged": [
    {
      "page": 3,
      "issue_type": "horizontal_overflow",
      "span_text": "Fair Value Accounting",
      "note": "Gerçeğe Uygun Değer Muhasebesi yan sütuna taşmış"
    }
  ],
  "summary": "Bölümde K sayfa deterministik temiz, M sayfa flagged"
}
```

QC'nin Haiku ile çalışmasının temel maliyet avantajı şudur: deterministik `clean: true` sayfalar için PNG hiç yüklenmez; PNG yükleme sadece `clean: false` sayfaların (tipik olarak %10-20) üzerinden yapılır.

## Paylaşılan Dosya Kilidi

`scripts/glossary.py` ve `scripts/cache.py` fcntl dosya kilidi kullanır; birden fazla çevirmen subagent aynı anda `glossary add` veya `cache put` çağırabilir, yarış koşulu oluşmaz. Aynı İngilizce terim farklı Türkçe karşılıklarla geldiğinde ikinci eklemeyi reddedip stderr'e uyarı yazar; koordinatörün çakışmayı çözmesi beklenir. Her çevirmen kendi `work/ch[NN]/` dizinine yazdığı için sayfa dosyalarında çakışma olmaz.
