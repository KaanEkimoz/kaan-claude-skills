"""
Pipeline helpers: sayfa render, span çıkarma, paragraf gruplama, sembol
normalize, kalibrasyon, ambiguous span tespiti.

CLI script'leri (extract_page.py, overlay_page.py, cache.py) bu modülü
kullanır; doğrudan agent context'ine girmez.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

# fitz (PyMuPDF) ve PIL yalnızca render gerektiren fonksiyonlarda lazy
# import edilir — bu sayede cache.py gibi yardımcı CLI'lar fitz yüklü
# olmadan da çalışabilir (sadece normalize_text / is_ambiguous_span
# kullanırlar).


SYMBOL_MAP = {
    "\u2019": "'",   # sağ tek tırnak
    "\u2018": "'",   # sol tek tırnak
    "\u201c": '"',   # sol çift tırnak
    "\u201d": '"',   # sağ çift tırnak
    "\u2013": "-",   # en-dash
    "\u2014": "-",   # em-dash
    "\u00a0": " ",   # non-breaking space
    "\u2026": "...", # horizontal ellipsis
}


# Ambiguous span blocklist: bu kalıplara uyan span'lar cache'e yazılmaz.
# Sebep: çok kısa / bağlam-bağımlı / jenerik metinler farklı sayfalarda
# farklı anlama gelebilir, körü körüne cache'lenmeleri yanlış çeviri
# uygulanmasına yol açar.
_AMBIGUOUS_PATTERNS = [
    re.compile(r"^\s*$"),
    re.compile(r"^[\W\d]+$"),                      # sadece noktalama/sayı
    re.compile(r"^(fig(ure)?|table|chapter|section|note|page)\s*[\d.]+\s*$", re.I),
    re.compile(r"^[ivxlcdmIVXLCDM]+\.?$"),         # i, ii, iv, ...
    re.compile(r"^\(?[a-zA-Z]\)?\.?$"),            # A., (a), b, ...
    re.compile(r"^\d+\.?$"),                       # 1, 2, 3.
    re.compile(r"^see\s+(also|page|figure|table).*$", re.I),
]

_MIN_CACHE_LEN = 4  # 4 karakterden kısa metinler cache'e girmez


def normalize_text(text: str) -> str:
    """Özel Unicode karakterleri standart ASCII karşılıklarına çevir ve
    fazla boşlukları tek boşluğa indir."""
    for bad, good in SYMBOL_MAP.items():
        text = text.replace(bad, good)
    return " ".join(text.split())


def is_ambiguous_span(text: str) -> bool:
    """Bu metin cache'e yazılmalı mı? False → yazılsın, True → yazılmasın."""
    t = text.strip()
    if len(t) < _MIN_CACHE_LEN:
        return True
    for pat in _AMBIGUOUS_PATTERNS:
        if pat.match(t):
            return True
    return False


# Varsayılan gruplama eşikleri. Kalibrasyon bu değerleri PDF'e özgü
# olarak günceller.
DEFAULT_GROUPING = {
    "x_close": 20.0,          # sol kenar aynı sütun eşiği (PNG pikseli)
    "y_adjacent_factor": 0.9, # bitişik satır eşik çarpanı (font_size'a oran)
}


def load_grouping_config(path: str | None) -> dict:
    """Disk'ten gruplama eşiklerini yükle; yoksa veya path None ise
    varsayılanı döndür."""
    if not path:
        return dict(DEFAULT_GROUPING)
    p = Path(path)
    if not p.exists():
        return dict(DEFAULT_GROUPING)
    with open(p, "r", encoding="utf-8") as f:
        data = json.load(f)
    cfg = dict(DEFAULT_GROUPING)
    cfg.update(data)
    return cfg


def save_grouping_config(path: str, cfg: dict):
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def render_and_extract(pdf_path: str, page_num: int, dpi: int = 150,
                       grouping: dict | None = None):
    """
    Sayfayı PNG olarak render et ve metin span'larını bbox + font + renk
    bilgisiyle birlikte çıkar.

    Returns:
        (PIL.Image, list[dict]) — render edilmiş sayfa ve span listesi.
        Her span: {text, bbox, font_name, font_size, color}
    """
    import fitz  # PyMuPDF (lazy)
    from PIL import Image

    doc = fitz.open(pdf_path)
    page = doc[page_num]
    scale = dpi / 72

    mat = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=mat)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)

    spans = []
    for block in page.get_text("dict")["blocks"]:
        if block.get("type") != 0:
            continue
        for line in block["lines"]:
            for span in line["spans"]:
                if not span["text"].strip():
                    continue
                x0, y0, x1, y1 = [v * scale for v in span["bbox"]]
                c = span["color"]
                spans.append({
                    "text": span["text"],
                    "bbox": [x0, y0, x1, y1],
                    "font_name": span["font"],
                    "font_size": span["size"] * scale,
                    "color": [(c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF],
                })

    cfg = grouping or DEFAULT_GROUPING
    spans = group_line_spans_into_paragraphs(
        spans,
        x_close=cfg.get("x_close", DEFAULT_GROUPING["x_close"]),
        y_adjacent_factor=cfg.get("y_adjacent_factor", DEFAULT_GROUPING["y_adjacent_factor"]),
    )
    doc.close()
    return img, spans


def group_line_spans_into_paragraphs(spans: list[dict],
                                     x_close: float = 20.0,
                                     y_adjacent_factor: float = 0.9) -> list[dict]:
    """
    Aynı paragrafa ait ardışık satır-span'larını tek bir span'a birleştir.
    Aynı font/boyut/renkte ve dikey olarak bitişik span'lar birleşir.

    Eşikler kalibrasyon tarafından güncellenebilir:
      x_close:            sol kenar fark sınırı (piksel)
      y_adjacent_factor:  alt-üst mesafesi font_size'ın kaç katına kadar
                          bitişik sayılır
    """
    if not spans:
        return spans

    result = []
    i = 0
    while i < len(spans):
        span = spans[i]
        group = [span]
        j = i + 1
        while j < len(spans):
            nxt = spans[j]
            same_font = nxt["font_name"] == span["font_name"]
            same_size = abs(nxt["font_size"] - span["font_size"]) < 0.5
            same_color = nxt["color"] == span["color"]
            x_close_ok = abs(nxt["bbox"][0] - span["bbox"][0]) < x_close
            vertical_gap = nxt["bbox"][1] - spans[j - 1]["bbox"][3]
            y_adjacent = 0 < vertical_gap < span["font_size"] * y_adjacent_factor
            if same_font and same_size and same_color and x_close_ok and y_adjacent:
                group.append(nxt)
                j += 1
            else:
                break

        if len(group) == 1:
            result.append(span)
        else:
            merged_text = " ".join(s["text"].rstrip("-") for s in group)
            merged_bbox = [
                min(s["bbox"][0] for s in group),
                min(s["bbox"][1] for s in group),
                max(s["bbox"][2] for s in group),
                max(s["bbox"][3] for s in group),
            ]
            merged = dict(span)
            merged["text"] = merged_text
            merged["bbox"] = merged_bbox
            result.append(merged)
        i = j

    return result


def calibrate_grouping(pdf_path: str, sample_pages: list[int],
                       dpi: int = 150) -> dict:
    """
    Örnek sayfalar üzerinde paragraf gruplama eşiklerini optimize et.

    Her (x_close, y_adjacent_factor) kombinasyonunu dene; en çok
    uzun-paragraf (birden fazla satırı olan) birleşmesi üreten ve aynı
    zamanda çok sayıda kısa parça bırakmayan değerleri seç.

    Returns:
        {"x_close": float, "y_adjacent_factor": float, "score": float,
         "sample_pages": [...]}
    """
    import fitz  # PyMuPDF (lazy)

    candidates_x = [15.0, 20.0, 25.0, 30.0, 35.0]
    candidates_y = [0.8, 0.9, 1.0, 1.1, 1.2, 1.4]

    doc = fitz.open(pdf_path)
    per_page_raw = []
    for p in sample_pages:
        if p < 0 or p >= len(doc):
            continue
        scale = dpi / 72
        page = doc[p]
        raw = []
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                for span in line["spans"]:
                    if not span["text"].strip():
                        continue
                    x0, y0, x1, y1 = [v * scale for v in span["bbox"]]
                    c = span["color"]
                    raw.append({
                        "text": span["text"],
                        "bbox": [x0, y0, x1, y1],
                        "font_name": span["font"],
                        "font_size": span["size"] * scale,
                        "color": [(c >> 16) & 0xFF, (c >> 8) & 0xFF, c & 0xFF],
                    })
        per_page_raw.append(raw)
    doc.close()

    best = None
    for xc in candidates_x:
        for yf in candidates_y:
            merge_score = 0.0
            fragment_penalty = 0.0
            for raw in per_page_raw:
                grouped = group_line_spans_into_paragraphs(
                    raw, x_close=xc, y_adjacent_factor=yf)
                for s in grouped:
                    h = s["bbox"][3] - s["bbox"][1]
                    if h > s["font_size"] * 1.8:
                        merge_score += 1.0
                short_spans = sum(
                    1 for s in grouped
                    if len(s["text"]) < 60 and s["bbox"][3] - s["bbox"][1] < s["font_size"] * 1.3
                )
                fragment_penalty += short_spans * 0.15

            score = merge_score - fragment_penalty
            if best is None or score > best["score"]:
                best = {
                    "x_close": xc,
                    "y_adjacent_factor": yf,
                    "score": score,
                    "sample_pages": sample_pages,
                }

    if best is None:
        return {"x_close": DEFAULT_GROUPING["x_close"],
                "y_adjacent_factor": DEFAULT_GROUPING["y_adjacent_factor"],
                "score": 0.0, "sample_pages": sample_pages}
    return best


def lookup_translation(span_text: str, translations: dict) -> str | None:
    """
    Span metnine karşılık gelen Türkçe çeviriyi bul.

    Sıra:
      1. Tam eşleşme (orijinal karakterlerle)
      2. Normalize edilmiş eşleşme (akıllı tırnak vb.)
      3. None → çeviri yok, span dokunulmadan bırakılır
    """
    raw = span_text.strip()
    if raw in translations:
        return translations[raw]
    normalized = normalize_text(raw)
    if normalized in translations:
        return translations[normalized]
    return None
