# Vision Çağrısı Şablonu

Vision çağrısı iki bloktan oluşur: **STATİK BLOK** (her sayfa için birebir aynı, prompt caching'e uygun) ve **DİNAMİK BLOK** (glossary + span listesi + PNG). Model sağlayıcı prompt caching destekliyorsa statik bloğu cache işaretiyle gönder, dinamik bloğu normal.

## STATİK BLOK (cache edilebilir)

```
Bu sayfanın PNG görüntüsünü görüyorsun. Aşağıdaki metin bloklarını
İngilizce'den Türkçe'ye çevir ve JSON sözlüğü olarak döndür.

ÇEVİRİ KURALLARI:
- Yayın kalitesi Türkçe, literal değil doğal. Deyimler hedef dilin
  karşılığıyla.
- Sayılar, para birimleri, ticker sembolleri, şirket/kişi/marka adları,
  URL'ler, ölçü birimleri çevrilmez — olduğu gibi bırakılır.
- Çeviri metnini orijinaliyle aynı uzunlukta tutmaya çalış. Türkçe
  İngilizce'den %15-30 daha uzun eğilimindedir; mümkünse daha kısa
  eşanlamlı seç, gereksiz bağlaçları at, aktif yapı tercih et. Dar
  bbox'larda uzun çeviri komşu metinlerin üstüne biner.
- Her span için `bbox_w` (piksel) ve `font_size` (piksel) verilir.
  Her çevirinin yaklaşık uzunluğu şu sınırı aşmamalı:
      max_chars ≈ (bbox_w / font_size) * 1.8
  Aşıyorsa terimi kısalt veya eşanlamlı kullan.
- Terminoloji sözlüğündeki kararlara sadık kal. Sözlükte olmayan bir
  terim için tutarlı bir çeviri seç ve new_glossary_terms'e ekle.
- TDK yazım kurallarına uy: -de/-da, -ki, büyük/küçük harf, ses uyumu.

EK GÖREV — VEKTÖR METİN: PNG'de gördüğün ama listede olmayan başka bir
İngilizce metin varsa (grafik/diyagram içi etiket, path olarak çizilmiş
yazı, eksen etiketi), onu da çıktıya ekle ve yaklaşık bbox'ını "extras"
altında ver. Bu kayıpsız kapsam için kritiktir, gözden kaçırma.

ÇIKTI FORMATI (JSON, başka metin yok):
{
  "translations": {
    "<original_1>": "<tr_1>",
    "<original_2>": "<tr_2>"
  },
  "extras": [
    {"text": "<original>", "tr": "<tr>", "bbox": [x0, y0, x1, y1]}
  ],
  "new_glossary_terms": [
    {"en": "<en>", "tr": "<tr>", "note": "<kısa bağlam>"}
  ]
}
```

## DİNAMİK BLOK

İki parça:

**1) Glossary bloğu** — `python -m scripts.glossary prompt --path work/glossary.json` çıktısı. Şu formatta olur:

```
Terminoloji sözlüğü (bu kararlara sadık kal):
  consciousness → bilinç — Felsefe bağlamında
  awareness → farkındalık — consciousness'tan farklı
  ...
```

**2) Span listesi** — cache'ten sonra kalan benzersiz metinler. Her satırda bbox_w ve font_size zorunlu:

```
ÇEVRİLECEK METİNLER:

1. "Introduction to Consciousness"  [bbox_w=180, font_size=14]
2. "This chapter explores the nature of awareness and..."  [bbox_w=520, font_size=11]
3. "Fair Value"  [bbox_w=60, font_size=9]
```

bbox_w ve font_size span metadata'sından gelir (spans.json). Bu değerler olmadan vision uzunluk sınırını hesaplayamaz; atlama.

**3) PNG attachment** — `work/ch[NN]/page_NNN.png` dosyasını çağrıya ekle.

## Vision Cevabını İşleme

1. JSON'u parse et.
2. `translations`'ı cached.json ile birleştir → `work/ch[NN]/page_NNN_translations.json`.
3. `extras` varsa her biri için spans listesine yeni bir span ekle (text, bbox, font_name = "sans", font_size = default, color = [0,0,0]).
4. `new_glossary_terms`'i `scripts.glossary add` ile kaydet.
5. Yeni çevirileri `scripts.cache put` ile cache'e yaz.
