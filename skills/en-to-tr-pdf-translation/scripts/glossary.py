#!/usr/bin/env python3
"""
Terminoloji sözlüğü: paylaşılan, kilit korumalı, JSON tabanlı.

Birden fazla çevirmen subagent aynı glossary.json'u aynı anda güncelleyebilir.
fcntl ile dosya kilidi kullanarak yazma yarışlarını önler.

Veri formatı:
    {
      "terms": {
        "consciousness": {"tr": "bilinç", "note": "Felsefe bağlamında"},
        "awareness": {"tr": "farkındalık", "note": "consciousness'tan farklı"}
      },
      "meta": {"last_updated": "2026-04-11T..."}
    }

CLI:
    python -m scripts.glossary init   --path glossary.json
    python -m scripts.glossary add    --path glossary.json --en "consciousness" --tr "bilinç" --note "Felsefe"
    python -m scripts.glossary get    --path glossary.json --en "consciousness"
    python -m scripts.glossary list   --path glossary.json
    python -m scripts.glossary stats  --path glossary.json
    python -m scripts.glossary prompt --path glossary.json    # vision prompt'a eklenecek format (düz metin)

Stdout davranışı:
    - `prompt` dışındaki tüm komutlar JSON basar (agent parse edebilsin diye).
    - `prompt` komutu vision prompt'a doğrudan gömülmek üzere DÜZ METİN basar.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import sys
from pathlib import Path


@contextlib.contextmanager
def _locked_file(path: Path, mode: str):
    """
    Dosya kilidi (POSIX). Yazma modunda exclusive lock.
    Birden fazla subagent aynı anda glossary'yi güncelleyebilir; kilit
    sayesinde yarış koşulu oluşmaz.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    f = open(path, mode, encoding="utf-8")
    try:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX if "w" in mode or "+" in mode else fcntl.LOCK_SH)
        yield f
    finally:
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)
        f.close()


def _empty():
    return {"terms": {}, "meta": {"last_updated": None}}


def load(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        return _empty()
    with _locked_file(p, "r") as f:
        return json.load(f)


def save(path: str, data: dict):
    p = Path(path)
    data["meta"]["last_updated"] = dt.datetime.now(dt.timezone.utc).isoformat()
    with _locked_file(p, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def init(path: str) -> dict:
    p = Path(path)
    if p.exists():
        return {"path": path, "initialized": False, "reason": "exists"}
    save(path, _empty())
    return {"path": path, "initialized": True}


def add(path: str, english: str, turkish: str, note: str = "") -> dict:
    """
    Tek bir terimi atomik olarak ekle. Yarış koşulunu önlemek için
    read-modify-write tek kilit altında yapılır.

    Returns:
        {"stored": bool, "reason": "created" | "conflict" | "duplicate",
         "en": ..., "tr": ...}
    """
    p = Path(path)
    if not p.exists():
        save(path, _empty())
    with _locked_file(p, "r+") as f:
        data = json.load(f)
        if english in data["terms"]:
            existing = data["terms"][english]
            if existing["tr"] != turkish:
                return {
                    "stored": False,
                    "reason": "conflict",
                    "en": english,
                    "existing_tr": existing["tr"],
                    "attempted_tr": turkish,
                }
            return {"stored": False, "reason": "duplicate", "en": english, "tr": turkish}
        data["terms"][english] = {"tr": turkish, "note": note}
        data["meta"]["last_updated"] = dt.datetime.now(dt.timezone.utc).isoformat()
        f.seek(0)
        f.truncate()
        json.dump(data, f, ensure_ascii=False, indent=2)
    return {"stored": True, "reason": "created", "en": english, "tr": turkish}


def get(path: str, english: str) -> str | None:
    data = load(path)
    entry = data["terms"].get(english)
    return entry["tr"] if entry else None


def list_terms(path: str) -> dict:
    data = load(path)
    terms = data["terms"]
    return {
        "path": path,
        "count": len(terms),
        "terms": [
            {"en": en, "tr": entry["tr"], "note": entry.get("note", "")}
            for en, entry in terms.items()
        ],
    }


def stats(path: str) -> dict:
    data = load(path)
    terms = data["terms"]
    with_notes = sum(1 for e in terms.values() if e.get("note"))
    return {
        "path": path,
        "total_terms": len(terms),
        "with_notes": with_notes,
        "last_updated": data.get("meta", {}).get("last_updated"),
    }


def as_prompt_block(path: str, max_terms: int = 100) -> str:
    """
    Vision prompt'a gömülmek üzere glossary'yi kısa bir format olarak döndür.
    İngilizce → Türkçe eşleşmelerinin listesi. Sözlük büyürse son değişen
    terimler öncelikli.
    """
    data = load(path)
    terms = data["terms"]
    if not terms:
        return "(Terminoloji sözlüğü henüz boş.)"
    lines = ["Terminoloji sözlüğü (bu kararlara sadık kal):"]
    for en, entry in list(terms.items())[:max_terms]:
        note = f" — {entry['note']}" if entry.get("note") else ""
        lines.append(f"  {en} → {entry['tr']}{note}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser(description="Terminoloji sözlüğü yönetimi")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("init"); sp.add_argument("--path", required=True)
    sp = sub.add_parser("add")
    sp.add_argument("--path", required=True)
    sp.add_argument("--en", required=True)
    sp.add_argument("--tr", required=True)
    sp.add_argument("--note", default="")
    sp = sub.add_parser("get"); sp.add_argument("--path", required=True); sp.add_argument("--en", required=True)
    sp = sub.add_parser("list"); sp.add_argument("--path", required=True)
    sp = sub.add_parser("stats"); sp.add_argument("--path", required=True)
    sp = sub.add_parser("prompt"); sp.add_argument("--path", required=True); sp.add_argument("--max", type=int, default=100)

    args = ap.parse_args()

    if args.cmd == "init":
        print(json.dumps(init(args.path), ensure_ascii=False))
    elif args.cmd == "add":
        result = add(args.path, args.en, args.tr, args.note)
        print(json.dumps(result, ensure_ascii=False))
    elif args.cmd == "get":
        tr = get(args.path, args.en)
        print(json.dumps({"en": args.en, "tr": tr}, ensure_ascii=False))
    elif args.cmd == "list":
        print(json.dumps(list_terms(args.path), ensure_ascii=False, indent=2))
    elif args.cmd == "stats":
        print(json.dumps(stats(args.path), ensure_ascii=False, indent=2))
    elif args.cmd == "prompt":
        # Düz metin: vision prompt'a doğrudan gömülecek.
        print(as_prompt_block(args.path, max_terms=args.max))


if __name__ == "__main__":
    main()
