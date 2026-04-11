# Çakışma Kontrolü

Türkçe çeviri genellikle İngilizceden %15-30 daha uzundur, bu yüzden çakışma en kritik hata kaynağıdır. Pipeline içi otomatik güvenceler:

- **`fit_text_in_bbox`**: Sırayla orijinal boyut → boyut küçült → 2-3 satır sar → son çare (çok küçük font). Her adım bbox dışına taşmaz. Son çareye düşen span'lar qc.json içinde `small_font` olarak flag edilir.
- **`sample_background` + 2px padding**: Orijinal metin silinirken sadece span'ın kendi bbox'ı kapatılır; komşu alana dokunulmaz.
- **Vision uzunluk kuralı**: Model her span'ın `bbox_w / font_size × 1.8` karakter sınırına uyar.
- **Deterministik çakışma testi**: `overlay_page.py` tüm span'lar overlay'lendikten sonra bbox kesişim testini çalıştırır ve `horizontal_overlap` / `vertical_overlap` issue'larını qc.json'a yazar.

## 5 Çakışma Tipi (QC Adımında Kontrol Et)

qc.json `clean: false` ise her flagged span için aşağıdaki tablodan teşhis et ve çözümü uygula.

| Tip | Belirti | Çözüm |
|---|---|---|
| `horizontal_overlap` | Uzayan etiket yan sütuna/grafiğe/komşu bloğa taşmış | translations.json'da o terimi kısalt, glossary'de kararı güncelle, `overlay_page.py`'yi yeniden çalıştır |
| `vertical_overlap` | Sarılan satırlar alt paragrafın/başlığın üstüne oturmuş | Aynı çözüm — çeviriyi kısalt; nadiren o span'ın bbox'ını manuel yükselt |
| `missing_font_variant` | Cümlenin bir kısmı Bold/Italic, diğeri Regular | `scripts/overlay.py` içindeki `FONT_MAP`'a o font ailesinin ilgili varyantını ekle, sayfayı yeniden overlay'le |
| `color_halo` | Silinmiş metin alanının etrafında gradient/fotoğraf arka planda dikdörtgen halka | O span için `blur_inpaint` fallback'ine düş; gradient ağırlıklı sayfalarda toptan blur |
| `small_font` | Bir span belirgin şekilde küçük fontla, neredeyse okunmaz | Çeviriyi ciddi kısalt, glossary'de daha kısa karşılık seç, sayfayı yeniden overlay'le |

`horizontal_overlap`, `vertical_overlap` ve `small_font` `overlay_page.py` tarafından deterministik olarak tespit edilir ve qc.json'a yazılır; QC subagent bunları doğrudan okur. `missing_font_variant` ve `color_halo` modelin görsel karşılaştırmasıyla flag edilir (qc.json'a deterministik yazılmaz, Haiku PNG'ye bakarken işaretler).
