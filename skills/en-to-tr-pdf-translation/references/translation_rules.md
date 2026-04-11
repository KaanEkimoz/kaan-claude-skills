# Çeviri Kuralları — Türkçe Yayın Kalitesi

## Temel İlke

Yayın çevirisi, birebir değil. Türkçe okuyucu kitabı sanki orijinali Türkçe yazılmış gibi okumalı. Literal çeviriden kaçın; anlamı koru, doğal Türkçe söz dizimini kullan (SON: Özne-Nesne-Yüklem). Devrik cümle sadece vurgu gerekiyorsa.

## Eksiksizlik

Hiçbir kelime, cümle, paragraf veya detay atlanmaz. Çevrilecekler: dipnotlar, başlıklar, alt başlıklar, tablo hücre metinleri, sayfa üstü/altı notları, kutu başlıkları, grafik eksen etiketleri, görsel içindeki metin ve altyazılar.

## Doğal Türkçe (Idiomatic)

Deyim ve kalıp ifadeler literal değil hedef dilin kendi karşılığıyla çevrilir ("hit the nail on the head" → "tam isabetli bir tespit", "a piece of cake" → "çocuk oyuncağı"). Kalıp bir deyim olduğunu fark ettiğinde Türkçede dolaşımda olan karşılığını kullan; yoksa anlamı koruyan doğal bir ifade tercih et.

## Çevrilmeyenler

Aşağıdakiler olduğu gibi bırakılır; etraflarındaki İngilizce metin çevrilir, kendileri değil:

- Sayılar, ondalık ve yüzdeler: 42, 3.14, $1,000, %15
- Para birimleri ve ticker sembolleri: $, €, ₺, BTC, AAPL, BRK.B
- Şirket / kişi / marka adları: Apple, Meta, Warren Buffett, iPhone
- URL, e-posta, dosya yolu
- Ölçü birimleri: kg, mph, °C, MW
- Kimyasal formüller, matematiksel semboller

## Kısaltmalar

1. Türkçede yerleşik karşılık varsa onu kullan (ABD, BM, AB, NATO).
2. Yerleşik karşılık yoksa ilk geçtiği yerde İngilizce açılımı parantez içinde ver, sonrasında aynı kısaltmayla devam et: "EBIT (Earnings Before Interest and Taxes)" ilk kez, sonra sadece "EBIT".
3. Anlamlı Türkçe kısaltma türetilebiliyorsa onu kullan: "EPS" → "HBK (Hisse Başına Kazanç)".

Her kısaltma kararı glossary'ye eklenir ve kitap boyunca tutarlı kalır.

## Terminoloji Tutarlılığı

`scripts/glossary.py` tek kaynaktır. Her yeni kavram kararı glossary'ye eklenir:

```bash
python -m scripts.glossary add --path work/glossary.json \
    --en "consciousness" --tr "bilinç" --note "Felsefe bağlamında"
```

Vision prompt'una her sayfa için `glossary prompt` çıktısı gömülür.

## PDF Çevirisine Özel TDK Noktaları

Bu tuzaklar PDF çevirisinde sık problem yaratır; diğer TDK kurallarını model zaten bilir:

- Sayıların ardından kesme işareti: `2020'de`, `1929'da` (yanlış: `2020. de`).
- -de/-da bulunma hali bitişik (`evde`), bağlaç olanı ayrı (`Ben de`).
- Tire ve kısa çizgi ayrımı: birleşik kelime `-`, sayfa aralığı `–` (en-dash) veya "ila".
- Ses uyumu ve ünsüz yumuşaması: `kitap` + -ı → `kitabı` (p → b).
- Türkçe karakterlerin doğru kullanımı: ç, ğ, ı, İ, ö, ş, ü.

## Uzunluk Dengesi

Türkçe çeviri genellikle İngilizceden %15-30 daha uzundur. PDF'in bbox'ları dar olduğu için overflow riski yüksek. Öncelik sırası:

1. Daha kısa eşanlamlı seç.
2. Gereksiz bağlaçları at ("ve", "ile").
3. Adjective + noun yerine tek bileşik terim seç.
4. Pasif yerine aktif.

Vision prompt'unda her span için `bbox_w` ve `font_size` zorunlu olarak verilir; modelin uzunluk sınırına uyması beklenir (max_chars ≈ bbox_w / font_size × 1.8). Uyum sağlanmazsa `fit_text_in_bbox` sırayla küçültme → kelime sarma → son çare küçük font adımlarına düşer; son adımdaki span'lar `page_NNN_qc.json` içinde `small_font` olarak flag edilir ve QC aşamasında düzeltilir.
