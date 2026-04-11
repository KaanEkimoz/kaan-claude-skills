# kaan-claude-skills

Custom Claude Cowork skills by [@kaanusta](https://github.com/kaanusta).

## Skills

### en-to-tr-pdf-translation

Translates English book PDFs to Turkish at publication quality.

**What it does:**
- Extracts text spans from each PDF page with layout metadata
- Translates using Claude vision (EN → TR), preserving fonts, colors and positions
- Overlays translated text on the original page images
- Runs QC to detect overflow, missing font variants, and small-font issues
- Assembles all translated pages into a final PDF

**Multi-agent pipeline:**
- **Koordinatör** (Sonnet) — orchestrates chapter subagents in parallel
- **Çevirmen** (Opus, one per chapter) — translates and overlays each page
- **QC** (Haiku, one per chapter) — quality-checks deterministically, then visually for flagged pages

**Requirements:**
```
pip install pymupdf pillow reportlab
```

**Usage:**
Load the skill in Claude Cowork, then ask:
> "Bu PDF'i Türkçe'ye çevir" (and attach your English PDF)

## License

MIT
