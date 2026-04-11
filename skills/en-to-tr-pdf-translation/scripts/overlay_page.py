#!/usr/bin/env python3
"""
CLI: Çeviri sözlüğüyle bir sayfa PNG'sinin üstüne Türkçe metni overlay et
ve deterministik QC raporu (page_NNN_qc.json) üret.

Kullanım:
    python -m scripts.overlay_page \
        --png work/ch01/page_042.png \
        --spans work/ch01/page_042_spans.json \
        --translations work/ch01/page_042_translations.json \
        --out work/ch01/page_042_tr.png \
        --qc-out work/ch01/page_042_qc.json

translations.json formatı: {"orijinal metin": "türkçe metin", ...}

Çevirisi olmayan span dokunulmadan bırakılır.

Stdout JSON:
    {"out", "qc", "covered", "total", "clean", "issue_count", "issues_by_type"}

qc.json formatı:
    {
      "page": "<png_basename>",
      "total_spans": N,
      "overlaid_spans": M,
      "clean": bool,
      "issues": [
        {"type": "small_font" | "wrapped_lines" | "horizontal_overlap" |
                 "vertical_overlap" | "missing_font_variant",
         "span_idx": int, "text": "...", "translated": "...",
         "orig_bbox": [x0,y0,x1,y1], "draw_bbox": [...], "note": "..."}
      ]
    }
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from PIL import Image

try:
    from .overlay import overlay_translations
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from overlay import overlay_translations


def _bboxes_overlap(a, b, tol: float = 1.0) -> bool:
    """İki bbox'ın kesişimi var mı? tol = küçük sayısal pay."""
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    return not (ax1 - tol <= bx0 or bx1 - tol <= ax0 or
                ay1 - tol <= by0 or by1 - tol <= ay0)


def _build_qc(fit_reports: list[dict], spans: list[dict]) -> dict:
    """
    fit_reports + spans üzerinden deterministik QC issue listesi üret.

    Tespit edilen tipler:
      - small_font           (fit_step == "fallback")
      - wrapped_lines        (fit_step in "wrapped_2", "wrapped_3")
      - missing_font_variant (variant_ok False)
      - horizontal_overlap   (draw_bbox başka bir span'ın orig_bbox'ıyla
                              yatay kesişim; aynı satırda)
      - vertical_overlap     (draw_bbox bir alt/üst komşunun bbox'ına
                              dikey taşma)
    """
    issues = []

    # Span bbox listesi: overlap testi için tüm orijinal bbox'ları kullan.
    span_bboxes = [s["bbox"] for s in spans]

    for report in fit_reports:
        idx = report["span_idx"]
        orig_bbox = report["orig_bbox"]
        draw_bbox = report["draw_bbox"]
        text = report["text"]
        translated = report["translated"]

        # small_font
        if report["fit_step"] == "fallback":
            issues.append({
                "type": "small_font",
                "span_idx": idx,
                "text": text,
                "translated": translated,
                "orig_bbox": orig_bbox,
                "draw_bbox": draw_bbox,
                "note": "fit_text_in_bbox son çareye düştü",
            })

        # wrapped_lines
        if report["fit_step"] in ("wrapped_2", "wrapped_3"):
            issues.append({
                "type": "wrapped_lines",
                "span_idx": idx,
                "text": text,
                "translated": translated,
                "orig_bbox": orig_bbox,
                "draw_bbox": draw_bbox,
                "note": f"Çeviri {report['line_count']} satıra sarıldı",
            })

        # missing_font_variant
        if not report.get("variant_ok", True):
            issues.append({
                "type": "missing_font_variant",
                "span_idx": idx,
                "text": text,
                "translated": translated,
                "orig_bbox": orig_bbox,
                "draw_bbox": draw_bbox,
                "note": "Bold/Italic varyantı bulunamadı, Regular'a düşüldü",
            })

        # horizontal/vertical overlap: draw_bbox başka bir span'ın orig_bbox'ı
        # ile orijinal bbox'ın dışına taşmış kesişim yaratıyor mu?
        dx0, dy0, dx1, dy1 = draw_bbox
        ox0, oy0, ox1, oy1 = orig_bbox
        horizontal_spill = dx1 > ox1 + 1
        vertical_spill = dy1 > oy1 + 1

        if horizontal_spill or vertical_spill:
            for other_idx, other_bbox in enumerate(span_bboxes):
                if other_idx == idx:
                    continue
                if _bboxes_overlap(draw_bbox, other_bbox):
                    # orig_bbox ile zaten kesişiyorsa pas geç (yanyana span
                    # doğal kesişim)
                    if _bboxes_overlap(orig_bbox, other_bbox, tol=2.0):
                        continue
                    issue_type = "horizontal_overlap" if horizontal_spill else "vertical_overlap"
                    issues.append({
                        "type": issue_type,
                        "span_idx": idx,
                        "text": text,
                        "translated": translated,
                        "orig_bbox": orig_bbox,
                        "draw_bbox": draw_bbox,
                        "overlaps_with_idx": other_idx,
                        "note": f"Çeviri komşu span'ın (idx {other_idx}) bbox'ına taştı",
                    })
                    break

    return issues


def main():
    ap = argparse.ArgumentParser(description="PNG üzerine Türkçe çevirileri overlay et")
    ap.add_argument("--png", required=True, help="Kaynak sayfa PNG'si")
    ap.add_argument("--spans", required=True, help="extract_page.py'nin ürettiği spans.json")
    ap.add_argument("--translations", required=True, help="{orijinal: türkçe} sözlüğü (JSON)")
    ap.add_argument("--out", required=True, help="Çıktı PNG yolu")
    ap.add_argument("--qc-out", help="Deterministik QC JSON çıktısı (page_NNN_qc.json). "
                                     "Verilmezse --out yanına page_*_qc.json olarak yazılır.")
    args = ap.parse_args()

    img = Image.open(args.png).convert("RGB")

    with open(args.spans, "r", encoding="utf-8") as f:
        spans_data = json.load(f)
    spans = spans_data["spans"]

    with open(args.translations, "r", encoding="utf-8") as f:
        translations = json.load(f)

    result_img, fit_reports = overlay_translations(img, spans, translations)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    result_img.save(out_path, "PNG")

    issues = _build_qc(fit_reports, spans)

    if args.qc_out:
        qc_path = Path(args.qc_out)
    else:
        # page_042_tr.png → page_042_qc.json
        stem = out_path.stem
        if stem.endswith("_tr"):
            stem = stem[:-3]
        qc_path = out_path.parent / f"{stem}_qc.json"

    qc_path.parent.mkdir(parents=True, exist_ok=True)
    qc_doc = {
        "page": Path(args.png).stem,
        "total_spans": len(spans),
        "overlaid_spans": len(fit_reports),
        "clean": len(issues) == 0,
        "issues": issues,
    }
    with open(qc_path, "w", encoding="utf-8") as f:
        json.dump(qc_doc, f, ensure_ascii=False, indent=2)

    issues_by_type = {}
    for issue in issues:
        issues_by_type[issue["type"]] = issues_by_type.get(issue["type"], 0) + 1

    print(json.dumps({
        "out": str(out_path),
        "qc": str(qc_path),
        "covered": len(fit_reports),
        "total": len(spans),
        "clean": qc_doc["clean"],
        "issue_count": len(issues),
        "issues_by_type": issues_by_type,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
