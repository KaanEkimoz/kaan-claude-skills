# Bilinen Tuzaklar

Beklenmedik bir durum fark edildiğinde bu dosyaya bak.

## 1. Paragraf Satır Satır İngilizce Kalmış

**Belirti**: Bir paragrafın satırları tek tek İngilizce, çevresi Türkçe.

**Sebep**: PyMuPDF paragrafı her satırı ayrı span olarak döndürür; `group_line_spans_into_paragraphs` birleştirmedi. Cache lookup paragraf-seviyesinde çalışıyor, satır-seviyesinde bulamıyor.

**Çözüm**: `work/grouping.json` içindeki eşikler yetersiz. Kalibrasyonu yeniden çalıştır:

```bash
python -m scripts.extract_page --pdf book.pdf --page <sorunlu_sayfa> \
    --out-dir work/calib --calibrate --save-config work/grouping.json
```

Sorunlu sayfa üzerinde yeni eşikler üretilir. Alternatif manuel yol: `grouping.json` içinde `x_close` değerini 20 → 25-30, `y_adjacent_factor`'u 0.9 → 1.1-1.2 aralığına çek.

## 2. Özel Sembol Yüzünden Span Atlandı

**Belirti**: Paragrafın ortasında bir iki cümle İngilizce, çevresi Türkçe.

**Sebep**: Span metninde akıllı tırnak (" "), en-dash (–), non-breaking space gibi karakterler var; cache anahtarı tam eşleşmiyor.

**Çözüm**: `cache.py`'nin normalize fonksiyonu bu karakterleri zaten temizler. Normalize kapsamı dışında bir karakter varsa `pipeline.py`'deki `SYMBOL_MAP`'e ekle, sayfayı yeniden çalıştır.

## 3. Vektör Grafik Metni Yakalanmadı

**Belirti**: Bir diyagram/akış şeması/grafik içindeki etiketler İngilizce kalmış, grafik dışı her şey Türkçe.

**Sebep**: Etiketler PDF'te path (vektör çizim) olarak yazılmış, TrueType span değil. `get_text("dict")` bunları çıkarmaz. Vision adımının `extras` alanıyla yakalaması gerekirdi ama yakalamadı.

**Çözüm**: Vision çağrısında span listesini yollarken EK GÖREV satırını vurgula. Model hâlâ kaçırıyorsa o sayfayı kullanıcıya manuel not olarak bildir (vektör grafik metin listesinin bir parçası).

## 4. Son Çareye Düşmüş Küçük Font

**Belirti**: Bir span belirgin şekilde küçük fontla yazılmış, qc.json'da `small_font` olarak işaretli.

**Sebep**: `fit_text_in_bbox` tüm kombinasyonlarda başarısız — çeviri çok uzun, kelime sarma da sığmıyor.

**Çözüm**: Glossary'de o terimin karşılığını kısalt, `overlay_page.py`'yi sadece o sayfa için tekrar çalıştır (yeni qc.json üretilir).
