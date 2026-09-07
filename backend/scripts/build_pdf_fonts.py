#!/usr/bin/env python
"""Сборка шрифтов для PDF из пакетов npm.

Зачем: reportlab умеет встраивать только TTF, а @fontsource поставляет
woff2, да ещё разрезанными по подмножествам (latin, cyrillic, …).
Скрипт склеивает нужные подмножества в один TTF на начертание.

Отдельная сложность — таджикские буквы (ғ ӣ қ ӯ ҳ ҷ): в Manrope их нет,
поэтому брендбук и требует пару с Noto Sans. Недостающие глифы берутся
из Noto, подрезанного ровно до этих букв, с приведением unitsPerEm к
метрике Manrope — иначе буквы окажутся вдвое мельче остального текста.

Запуск (нужен установленный frontend/node_modules):

    pip install "fonttools[woff]"
    python scripts/build_pdf_fonts.py

Результат — app/assets/fonts/*.ttf, они коммитятся в репозиторий:
на сервере node_modules нет, а образ должен собираться без интернета.
Шрифты распространяются по SIL OFL, см. app/assets/fonts/LICENSE.md.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fontTools import subset
from fontTools.merge import Merger
from fontTools.ttLib import TTFont
from fontTools.ttLib.scaleUpem import scale_upem

ROOT = Path(__file__).resolve().parent.parent
NPM = ROOT.parent / "frontend" / "node_modules" / "@fontsource"
OUT = ROOT / "app" / "assets" / "fonts"

#: Подмножества, покрывающие русский, таджикский и латиницу.
SUBSETS = ("latin", "latin-ext", "cyrillic", "cyrillic-ext")

#: Буквы, которых нет в Manrope. Берём их из Noto Sans.
TAJIK = "ғҒӣӢқҚӯӮҳҲҷҶ"

#: (семейство npm, вес, имя итогового файла)
TARGETS = [
    ("manrope", "400", "Manrope-Regular.ttf"),
    ("manrope", "700", "Manrope-Bold.ttf"),
    ("jetbrains-mono", "400", "JetBrainsMono-Regular.ttf"),
    ("jetbrains-mono", "600", "JetBrainsMono-SemiBold.ttf"),
]


def unpack(family: str, sub: str, weight: str, tmp: Path) -> Path | None:
    src = NPM / family / "files" / f"{family}-{sub}-{weight}-normal.woff2"
    if not src.exists():
        return None
    font = TTFont(src)
    font.flavor = None
    out = tmp / f"{family}-{sub}-{weight}.ttf"
    font.save(out)
    return out


def tajik_patch(tmp: Path, units_per_em: int) -> Path:
    """Noto Sans, подрезанный до таджикских букв и приведённый к метрике."""
    source = unpack("noto-sans", "cyrillic-ext", "400", tmp)
    if source is None:
        raise SystemExit("Не найден @fontsource/noto-sans — выполните npm install")

    options = subset.Options(glyph_names=False, notdef_outline=True)
    font = subset.load_font(str(source), options)
    subsetter = subset.Subsetter(options=options)
    subsetter.populate(text=TAJIK)
    subsetter.subset(font)
    trimmed = tmp / "noto-tajik.ttf"
    subset.save_font(font, str(trimmed), options)

    scaled = TTFont(trimmed)
    if scaled["head"].unitsPerEm != units_per_em:
        scale_upem(scaled, units_per_em)
    result = tmp / "noto-tajik-scaled.ttf"
    scaled.save(result)
    return result


def build(family: str, weight: str, filename: str, tmp: Path) -> None:
    parts = [p for s in SUBSETS if (p := unpack(family, s, weight, tmp))]
    if not parts:
        raise SystemExit(f"Нет подмножеств {family} {weight} — выполните npm install")

    units_per_em = TTFont(parts[0])["head"].unitsPerEm
    parts.append(tajik_patch(tmp, units_per_em))

    merged = Merger().merge([str(p) for p in parts])
    target = OUT / filename
    merged.save(target)

    missing = [c for c in TAJIK if ord(c) not in TTFont(target).getBestCmap()]
    if missing:
        raise SystemExit(f"{filename}: не хватает глифов {''.join(missing)}")
    print(f"{filename}: {target.stat().st_size // 1024} КБ")


def main() -> int:
    if not NPM.exists():
        print("Не найден frontend/node_modules — выполните npm install", file=sys.stderr)
        return 1

    OUT.mkdir(parents=True, exist_ok=True)
    tmp = OUT / ".tmp"
    tmp.mkdir(exist_ok=True)
    try:
        for family, weight, filename in TARGETS:
            build(family, weight, filename, tmp)
    finally:
        for leftover in tmp.glob("*"):
            leftover.unlink()
        tmp.rmdir()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
