#!/usr/bin/env python3
"""
CLI: Tek bir PDF sayfasını PNG olarak render et ve span'larını JSON'a yaz.

Kullanım:
    # Tek sayfa çıkarma (normal kullanım)
    python -m scripts.extract_page \
        --pdf book.pdf \
        --page 42 \
        --out-dir work/ch01/ \
        --config work/grouping.json

    # Paragraf gruplama eşiklerini kalibre et (Aşama 0)
    python -m scripts.extract_page \
        --pdf book.pdf \
        --page 0 \
        --out-dir work/calib \
        --calibrate \
        --save-config work/grouping.json

Çıktılar:
    <out-dir>/page_NNNN.png          150 DPI render
    <out-dir>/page_NNNN_spans.json   metin blokları metadata'sıyla

Stdout JSON:
    Normal mod: {"png", "spans", "span_count", "grouping"}
    Kalibrasyon modu: {"calibrated": true, "grouping": {...},
                       "config_path": "...", "sample_pages": [...]}
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    from .pipeline import (
        render_and_extract,
        load_grouping_config,
        save_grouping_config,
        calibrate_grouping,
        DEFAULT_GROUPING,
    )
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from pipeline import (
        render_and_extract,
        load_grouping_config,
        save_grouping_config,
        calibrate_grouping,
        DEFAULT_GROUPING,
    )


def main():
    ap = argparse.ArgumentParser(description="PDF sayfasını PNG + spans.json olarak çıkar")
    ap.add_argument("--pdf", required=True, help="Kaynak PDF dosyası")
    ap.add_argument("--page", type=int, required=True, help="Sayfa numarası (0-tabanlı). "
                                                             "Kalibrasyon modunda başlangıç sayfası.")
    ap.add_argument("--out-dir", required=True, help="Çıktı dizini")
    ap.add_argument("--dpi", type=int, default=150, help="Render DPI (varsayılan 150)")
    ap.add_argument("--config", help="Gruplama eşikleri JSON dosyası (load_grouping_config ile okunur)")
    ap.add_argument("--calibrate", action="store_true",
                    help="Kalibrasyon modu: --page'den başlayarak birkaç örnek sayfada "
                         "x_close ve y_adjacent_factor eşiklerini optimize et")
    ap.add_argument("--calibrate-samples", type=int, default=3,
                    help="Kalibrasyon modunda kaç sayfa örneklensin (varsayılan 3)")
    ap.add_argument("--save-config", help="Kalibrasyon modunda bulunan eşikleri bu dosyaya yaz")
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.calibrate:
        sample_pages = list(range(args.page, args.page + args.calibrate_samples))
        result = calibrate_grouping(args.pdf, sample_pages, dpi=args.dpi)
        grouping = {
            "x_close": result["x_close"],
            "y_adjacent_factor": result["y_adjacent_factor"],
        }
        config_path = args.save_config
        if config_path:
            save_grouping_config(config_path, grouping)
        # Kalibrasyonun örnek ilk sayfasını da diske yaz (inceleme için)
        img, spans = render_and_extract(args.pdf, args.page, dpi=args.dpi,
                                        grouping=grouping)
        png_path = out_dir / f"page_{args.page:04d}.png"
        spans_path = out_dir / f"page_{args.page:04d}_spans.json"
        img.save(png_path, "PNG")
        with open(spans_path, "w", encoding="utf-8") as f:
            json.dump({
                "pdf": args.pdf,
                "page": args.page,
                "dpi": args.dpi,
                "image_size": [img.width, img.height],
                "grouping": grouping,
                "spans": spans,
            }, f, ensure_ascii=False, indent=2)
        print(json.dumps({
            "calibrated": True,
            "grouping": grouping,
            "score": result.get("score", 0),
            "sample_pages": sample_pages,
            "config_path": config_path,
            "preview_png": str(png_path),
            "preview_spans": str(spans_path),
        }, ensure_ascii=False))
        return

    grouping = load_grouping_config(args.config) if args.config else dict(DEFAULT_GROUPING)

    img, spans = render_and_extract(args.pdf, args.page, dpi=args.dpi, grouping=grouping)

    png_path = out_dir / f"page_{args.page:04d}.png"
    spans_path = out_dir / f"page_{args.page:04d}_spans.json"

    img.save(png_path, "PNG")
    with open(spans_path, "w", encoding="utf-8") as f:
        json.dump({
            "pdf": args.pdf,
            "page": args.page,
            "dpi": args.dpi,
            "image_size": [img.width, img.height],
            "grouping": grouping,
            "spans": spans,
        }, f, ensure_ascii=False, indent=2)

    print(json.dumps({
        "png": str(png_path),
        "spans": str(spans_path),
        "span_count": len(spans),
        "grouping": grouping,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
