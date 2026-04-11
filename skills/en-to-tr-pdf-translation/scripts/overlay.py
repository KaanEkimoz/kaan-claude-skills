"""
Overlay işlemleri: arka plan örnekleme, font eşleştirme, metin sığdırma
ve çevirilerin PNG üzerine yazılması. Saf Python; agent reasoning'i
gerektirmez. CLI overlay_page.py bu modülü çağırır.

Bu modüldeki fonksiyonlar overlay sırasında deterministik QC verisi
döndürür: hangi span son çareye düştü, hangi fontun Bold/Italic varyantı
bulunamadı, hangi span'lar kelime sarmaya gitti. overlay_page.py bu
verileri page_NNN_qc.json'a yazar ve QC subagent'ı bu dosyayı doğrudan
okur.
"""

from __future__ import annotations

import textwrap

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter


DEFAULT_FALLBACK_FONT = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"

FONT_MAP = {
    ("sans",  False, False): "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ("sans",  True,  False): "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    ("sans",  False, True):  "/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf",
    ("sans",  True,  True):  "/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf",
    ("serif", False, False): "/usr/share/fonts/truetype/liberation/LiberationSerif-Regular.ttf",
    ("serif", True,  False): "/usr/share/fonts/truetype/liberation/LiberationSerif-Bold.ttf",
    ("serif", False, True):  "/usr/share/fonts/truetype/liberation/LiberationSerif-Italic.ttf",
    ("serif", True,  True):  "/usr/share/fonts/truetype/liberation/LiberationSerif-BoldItalic.ttf",
    ("mono",  False, False): "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    ("mono",  True,  False): "/usr/share/fonts/truetype/liberation/LiberationMono-Bold.ttf",
}


def sample_background(img: Image.Image, x0, y0, x1, y1):
    """Bbox çevresindeki border şeridinden medyan arka plan rengini örnekle."""
    arr = np.array(img)
    h, w = arr.shape[:2]
    border = []
    pad = 4
    for y in range(max(0, int(y0) - pad), min(h, int(y1) + pad)):
        for x in [max(0, int(x0) - pad), min(w - 1, int(x1) + pad)]:
            border.append(arr[y, x])
    for x in range(max(0, int(x0) - pad), min(w, int(x1) + pad)):
        for y in [max(0, int(y0) - pad), min(h - 1, int(y1) + pad)]:
            border.append(arr[y, x])
    if not border:
        return (255, 255, 255)
    return tuple(int(v) for v in np.median(border, axis=0))


def blur_inpaint(img: Image.Image, x0, y0, x1, y1, radius: int = 15):
    """Gradient/fotoğraf üstü metin için fallback in-place inpaint."""
    region = img.crop((int(x0), int(y0), int(x1), int(y1)))
    region = region.filter(ImageFilter.GaussianBlur(radius))
    img.paste(region, (int(x0), int(y0)))


def classify_font(font_name: str) -> tuple[str, bool, bool]:
    """Font adından (family, is_bold, is_italic) üçlüsünü türet."""
    lower = font_name.lower()
    is_bold = any(k in lower for k in ["bold", "black", "heavy"])
    is_italic = any(k in lower for k in ["italic", "oblique"])
    base = lower.split("+")[-1]
    if any(k in base for k in ["times", "serif", "georgia", "garamond", "cambria", "book antiqua"]):
        family = "serif"
    elif any(k in base for k in ["mono", "courier", "consolas"]):
        family = "mono"
    else:
        family = "sans"
    return family, is_bold, is_italic


def find_best_font(font_name: str, font_size: float):
    """
    Orijinal font adına en yakın sistem fontunu bul.

    Returns:
        (font, variant_ok) — variant_ok False ise orijinal Bold/Italic
        varyantı FONT_MAP'te bulunamadı, Regular fallback kullanıldı.
        Bu bilgi qc.json'a missing_font_variant olarak yazılır.
    """
    family, is_bold, is_italic = classify_font(font_name)
    wanted_key = (family, is_bold, is_italic)
    wanted_path = FONT_MAP.get(wanted_key)
    variant_requested = is_bold or is_italic
    variant_ok = (wanted_path is not None) or (not variant_requested)
    path = wanted_path or FONT_MAP.get((family, False, False)) or DEFAULT_FALLBACK_FONT
    try:
        return ImageFont.truetype(path, max(6, int(font_size))), variant_ok
    except Exception:
        return ImageFont.load_default(), False


def _text_width(font, text: str) -> float:
    if hasattr(font, "getlength"):
        return font.getlength(text)
    return font.getbbox(text)[2]


def _line_height(font, fallback: float) -> float:
    if hasattr(font, "getbbox"):
        return font.getbbox("Ay")[3]
    return fallback


def fit_text_in_bbox(draw, text, x0, y0, x1, y1, font_name, orig_size, fg_color):
    """
    Türkçe çeviriyi bbox'a sığdır. Katmanlı fallback:
      1) Orijinal boyut, tek satır
      2) Boyut adım adım küçült, tek satır
      3) 2 veya 3 satır kelime sarma + boyut küçültme
      4) Son çare: çok küçük fontla yaz

    Returns:
        {
          "fit_step": "single" | "shrunk" | "wrapped_2" | "wrapped_3" | "fallback",
          "font_size": int,
          "line_count": int,
          "draw_bbox": [x0, y0, x1_drawn, y1_drawn],
          "variant_ok": bool
        }
    """
    bbox_w = x1 - x0
    bbox_h = y1 - y0
    orig_size = int(orig_size)

    # Deneme 1 & 2: tek satır, boyut küçültme
    for idx, size in enumerate(range(orig_size, max(6, orig_size - 12), -1)):
        font, variant_ok = find_best_font(font_name, size)
        if _text_width(font, text) <= bbox_w and _line_height(font, size) <= bbox_h:
            draw.text((x0, y0), text, fill=tuple(fg_color), font=font)
            width_drawn = _text_width(font, text)
            lh = _line_height(font, size)
            return {
                "fit_step": "single" if idx == 0 else "shrunk",
                "font_size": size,
                "line_count": 1,
                "draw_bbox": [x0, y0, x0 + width_drawn, y0 + lh],
                "variant_ok": variant_ok,
            }

    # Deneme 3: kelime sarma, 2 veya 3 satır
    for n_lines in (2, 3):
        for size in range(orig_size, max(6, orig_size - 8), -1):
            font, variant_ok = find_best_font(font_name, size)
            lh = _line_height(font, size)
            if lh * n_lines > bbox_h * 1.1:
                continue
            avg_w = _text_width(font, "M") or size * 0.6
            chars_per_line = max(1, int(bbox_w / avg_w))
            lines = textwrap.wrap(text, width=chars_per_line)
            if len(lines) <= n_lines and all(_text_width(font, l) <= bbox_w for l in lines):
                for i, line in enumerate(lines):
                    draw.text((x0, y0 + i * lh), line, fill=tuple(fg_color), font=font)
                max_w = max(_text_width(font, l) for l in lines)
                return {
                    "fit_step": f"wrapped_{len(lines)}",
                    "font_size": size,
                    "line_count": len(lines),
                    "draw_bbox": [x0, y0, x0 + max_w, y0 + lh * len(lines)],
                    "variant_ok": variant_ok,
                }

    # Son çare: çok küçük font
    fallback_size = max(6, orig_size - 10)
    font, variant_ok = find_best_font(font_name, fallback_size)
    draw.text((x0, y0), text, fill=tuple(fg_color), font=font)
    width_drawn = _text_width(font, text)
    lh = _line_height(font, fallback_size)
    return {
        "fit_step": "fallback",
        "font_size": fallback_size,
        "line_count": 1,
        "draw_bbox": [x0, y0, x0 + width_drawn, y0 + lh],
        "variant_ok": variant_ok,
    }


def overlay_translations(img: Image.Image, spans: list[dict], translations: dict):
    """
    Her span için: çeviri bul → arka planı örnekle → orijinali sil →
    Türkçeyi sığdır. Çevirisi olmayan span dokunulmadan bırakılır.

    Returns:
        (img, fit_reports) — fit_reports her overlay'lenmiş span için
        fit_text_in_bbox çıktısı + span_idx + text. overlay_page.py bu
        listeyi bbox çakışma testine sokar ve qc.json'u üretir.
    """
    try:
        from .pipeline import lookup_translation
    except ImportError:
        from pipeline import lookup_translation

    draw = ImageDraw.Draw(img)
    fit_reports = []
    for idx, span in enumerate(spans):
        x0, y0, x1, y1 = span["bbox"]
        translated = lookup_translation(span["text"], translations)
        if translated is None:
            continue

        bg = sample_background(img, x0, y0, x1, y1)
        draw.rectangle([x0 - 2, y0 - 2, x1 + 2, y1 + 2], fill=bg)
        report = fit_text_in_bbox(draw, translated, x0, y0, x1, y1,
                                  span["font_name"], span["font_size"], span["color"])
        report["span_idx"] = idx
        report["text"] = span["text"]
        report["translated"] = translated
        report["orig_bbox"] = [x0, y0, x1, y1]
        fit_reports.append(report)

    return img, fit_reports
