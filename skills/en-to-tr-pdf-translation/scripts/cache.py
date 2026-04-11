#!/usr/bin/env python3
"""
Çeviri önbelleği: aynı cümle/ifade tekrar ettiğinde yeniden çevirme.

Anahtarlar normalize edilmiş metinle saklanır (akıllı tırnak, en-dash,
non-breaking space vb. temizlenir). Ambiguous span'lar (çok kısa,
"Figure N", "Note", tek harf kodu gibi jenerik metinler) cache'e yazılmaz
çünkü bağlam-bağımlıdırlar ve yanlış çeviri uygulanmasına yol açabilirler.

fcntl dosya kilidi: birden fazla subagent aynı anda yazabilir.

Veri formatı:
    {
      "entries": {
        "<normalized_en>": {"tr": "<turkish>", "hits": <int>,
                            "raw": "<last_raw_en>"}
      }
    }

CLI:
    python -m scripts.cache init  --path cache.json
    python -m scripts.cache put   --path cache.json --en "..." --tr "..."
    python -m scripts.cache get   --path cache.json --en "..."
    python -m scripts.cache stats --path cache.json
    python -m scripts.cache apply --path cache.json --spans spans.json --out translations.json
        (cache'te olanları translations.json'a yaz; kalan uncovered
         listesini JSON olarak stdout'a bas)
"""

from __future__ import annotations

import argparse
import contextlib
import fcntl
import json
import sys
from pathlib import Path

try:
    from .pipeline import normalize_text, is_ambiguous_span
except ImportError:
    sys.path.insert(0, str(Path(__file__).parent))
    from pipeline import normalize_text, is_ambiguous_span


@contextlib.contextmanager
def _locked_file(path: Path, mode: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, mode, encoding="utf-8")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX if "w" in mode or "+" in mode else fcntl.LOCK_SH)
        yield f
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def _empty():
    return {"entries": {}}


def load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return _empty()
    with _locked_file(p, "r") as f:
        return json.load(f)


def put(path: str, english: str, turkish: str) -> dict:
    """
    Cache'e tek giriş yaz. Ambiguous span'lar sessizce atlanır.

    Returns:
        {"stored": bool, "reason": str, "key": "<normalized>"}
    """
    key = normalize_text(english)
    if is_ambiguous_span(key):
        return {"stored": False, "reason": "ambiguous", "key": key}

    p = Path(path)
    if not p.exists():
        with _locked_file(p, "w") as f:
            json.dump(_empty(), f, ensure_ascii=False, indent=2)
    with _locked_file(p, "r+") as f:
        data = json.load(f)
        entry = data["entries"].get(key)
        if entry:
            if entry["tr"] != turkish:
                print(f"UYARI: '{key}' farklı çeviri ('{entry['tr']}' vs '{turkish}')",
                      file=sys.stderr)
            entry["hits"] = entry.get("hits", 1) + 1
            entry["raw"] = english
            reason = "updated"
        else:
            data["entries"][key] = {"tr": turkish, "hits": 1, "raw": english}
            reason = "created"
        f.seek(0)
        f.truncate()
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"stored": True, "reason": reason, "key": key}


def get(path: str, english: str) -> str | None:
    data = load(path)
    key = normalize_text(english)
    entry = data["entries"].get(key)
    return entry["tr"] if entry else None


def apply_to_spans(cache_path: str, spans_path: str, out_path: str) -> dict:
    """
    spans.json içindeki her span metnini cache'te ara. Bulunan çevirileri
    out_path'e (translations.json) yaz. Kalan benzersiz metinleri
    `uncovered` listesinde döndür — vision'a gidecek span'lar bunlardır.
    """
    data = load(cache_path)
    entries = data["entries"]

    with open(spans_path, "r", encoding="utf-8") as f:
        spans_data = json.load(f)

    translations = {}
    uncovered = []
    seen_uncovered = set()
    hit = 0
    total = len(spans_data["spans"])

    for span in spans_data["spans"]:
        raw = span["text"].strip()
        key = normalize_text(raw)
        if key in entries:
            translations[raw] = entries[key]["tr"]
            hit += 1
        else:
            if key not in seen_uncovered:
                seen_uncovered.add(key)
                uncovered.append(raw)

    out_p = Path(out_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    with open(out_p, "w", encoding="utf-8") as f:
        json.dump(translations, f, ensure_ascii=False, indent=2)

    return {
        "out": str(out_p),
        "total": total,
        "hit": hit,
        "hit_rate": round(hit / total, 3) if total else 0.0,
        "uncovered_count": len(uncovered),
        "uncovered": uncovered,
    }


def stats(path: str) -> dict:
    data = load(path)
    entries = data["entries"]
    total_hits = sum(e.get("hits", 0) for e in entries.values())
    top = sorted(entries.items(), key=lambda kv: kv[1].get("hits", 0), reverse=True)[:10]
    return {
        "total_entries": len(entries),
        "total_hits": total_hits,
        "top_10": [{"en": kv[1].get("raw", kv[0]), "hits": kv[1].get("hits", 0)} for kv in top],
    }


def main():
    ap = argparse.ArgumentParser(description="Çeviri önbelleği yönetimi")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init"); sp.add_argument("--path", required=True)
    sp = sub.add_parser("put")
    sp.add_argument("--path", required=True)
    sp.add_argument("--en", required=True)
    sp.add_argument("--tr", required=True)
    sp = sub.add_parser("get"); sp.add_argument("--path", required=True); sp.add_argument("--en", required=True)
    sp = sub.add_parser("stats"); sp.add_argument("--path", required=True)
    sp = sub.add_parser("apply")
    sp.add_argument("--path", required=True, help="Cache dosyası")
    sp.add_argument("--spans", required=True, help="spans.json")
    sp.add_argument("--out", required=True, help="translations.json çıktısı")

    args = ap.parse_args()

    if args.cmd == "init":
        Path(args.path).parent.mkdir(parents=True, exist_ok=True)
        with open(args.path, "w", encoding="utf-8") as f:
            json.dump(_empty(), f, ensure_ascii=False, indent=2)
        print(json.dumps({"path": args.path, "initialized": True}, ensure_ascii=False))
    elif args.cmd == "put":
        result = put(args.path, args.en, args.tr)
        print(json.dumps(result, ensure_ascii=False))
    elif args.cmd == "get":
        tr = get(args.path, args.en)
        print(json.dumps({"en": args.en, "tr": tr}, ensure_ascii=False))
    elif args.cmd == "stats":
        print(json.dumps(stats(args.path), ensure_ascii=False, indent=2))
    elif args.cmd == "apply":
        result = apply_to_spans(args.path, args.spans, args.out)
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
