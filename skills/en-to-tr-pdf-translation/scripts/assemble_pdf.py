#!/usr/bin/env python3
"""
CLI: Overlay'lı PNG'leri tek bir PDF'e birleştir.

Kullanım:
    python -m scripts.assemble_pdf \
        --pages-dir work/ch01/ \
        --pattern "page_*_tr.png" \
        --out output/bolum_01.pdf
    python -m scripts.assemble_pdf \
        --pages-dirs work/ch01 work/ch02 work/ch03 \
        --pattern "page_*_tr.png" \
        --out output/ceviri_final.pdf \
        --page-numbers

Her PNG tam sayfa olarak eklenir. DPI varsayılanı 150; PNG'lerin bu DPI'da
render edildiği varsayılır (extract_page.py varsayılanıyla aynı).
"""

from __future__ import annotations

import argparse
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas as rl_canvas
from PIL import Image


def _find_pngs(pages_dirs, pattern):
    paths = []
    for d in pages_dirs:
        paths.extend(sorted(Path(d).glob(pattern)))
    return paths


def _number_pages(canvas_obj, page_num, total):
    canvas_obj.saveState()
    canvas_obj.setFont("Helvetica", 9)
    canvas_obj.drawCentredString(
        canvas_obj._pagesize[0] / 2,
        0.5 * 28,  # 0.5 cm'lik dipte
        f"{page_num} / {total}",
    )
    canvas_obj.restoreState()


def assemble(pages_dirs, pattern, out_path, dpi=150, page_numbers=False):
    pngs = _find_pngs(pages_dirs, pattern)
    if not pngs:
        raise SystemExit(f"Hiç PNG bulunamadı: {pages_dirs} / {pattern}")

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    c = rl_canvas.Canvas(str(out_path), pagesize=A4)

    for i, png in enumerate(pngs, start=1):
        img = Image.open(png)
        img_w, img_h = img.size
        page_w = img_w * 72 / dpi
        page_h = img_h * 72 / dpi
        c.setPageSize((page_w, page_h))
        c.drawImage(str(png), 0, 0, width=page_w, height=page_h)
        if page_numbers:
            _number_pages(c, i, len(pngs))
        c.showPage()

    c.save()
    print(f"Birleştirildi: {len(pngs)} sayfa → {out_path}")


def main():
    ap = argparse.ArgumentParser(description="Overlay'lı PNG'leri PDF'e birleştir")
    group = ap.add_mutually_exclusive_group(required=True)
    group.add_argument("--pages-dir", help="Tek bir dizin")
    group.add_argument("--pages-dirs", nargs="+", help="Birden fazla dizin (bölüm sırasıyla)")
    ap.add_argument("--pattern", default="page_*_tr.png", help="PNG dosya deseni")
    ap.add_argument("--out", required=True, help="Çıktı PDF")
    ap.add_argument("--dpi", type=int, default=150)
    ap.add_argument("--page-numbers", action="store_true", help="Alt orta sayfa numarası ekle")
    args = ap.parse_args()

    dirs = [args.pages_dir] if args.pages_dir else args.pages_dirs
    assemble(dirs, args.pattern, args.out, dpi=args.dpi, page_numbers=args.page_numbers)


if __name__ == "__main__":
    main()
