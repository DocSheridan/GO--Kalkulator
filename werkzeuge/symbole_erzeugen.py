#!/usr/bin/env python3
"""Erzeugt die App-Symbole in den Farben der Praxis.

Die Farbwerte stammen aus dem Praxislogo (werkzeuge/praxislogo.png) und sind
dort die drei flaechenmaessig groessten deckenden Farben:

    #6C7569   Gruen der Logoflaeche      -> Untergrund des Symbols
    #FFFFFF   Weiss der Wortmarke        -> Schriftzug "GOAE"
    #B7C4AF   Hellgruen des Strangs      -> die drei Balken

Aufbau des Symbols (unveraendert gegenueber der ersten Fassung, nur neu
eingefaerbt): Schriftzug in der oberen Haelfte, darunter drei aufsteigende
Balken als Sinnbild fuer den einfachen, den 2,3- und den 3,5-fachen Satz.

    python3 werkzeuge/symbole_erzeugen.py
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# Aus dem Praxislogo entnommen - siehe Kopf dieser Datei.
GRUEN = (108, 117, 105)
WEISS = (255, 255, 255)
HELLGRUEN = (183, 196, 175)

SCHRIFTEN = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
)


def schriftart(groesse: int):
    for pfad in SCHRIFTEN:
        if Path(pfad).exists():
            return ImageFont.truetype(pfad, groesse)
    return ImageFont.load_default()


def zeichne(groesse: int, maskierbar: bool = False) -> Image.Image:
    bild = Image.new("RGBA", (groesse, groesse), (0, 0, 0, 0))
    stift = ImageDraw.Draw(bild)
    if maskierbar:
        # Maskierbare Symbole werden von Android beschnitten: Flaeche voll
        # fuellen, Inhalt in der sicheren Zone halten.
        stift.rectangle([0, 0, groesse, groesse], fill=GRUEN)
        inhalt = groesse * 0.70
    else:
        rand = groesse * 0.05
        stift.rounded_rectangle([rand, rand, groesse - rand, groesse - rand],
                                radius=groesse * 0.22, fill=GRUEN)
        inhalt = groesse * 0.86
    mitte = groesse / 2

    text = "GOÄ"
    grad = schriftart(int(inhalt * 0.34))
    kasten = stift.textbbox((0, 0), text, font=grad)
    stift.text((mitte - (kasten[2] - kasten[0]) / 2 - kasten[0],
                mitte - inhalt * 0.34 - kasten[1]), text, font=grad, fill=WEISS)

    balken_unten = mitte + inhalt * 0.33
    hoechste = inhalt * 0.30
    breite = inhalt * 0.15
    luecke = inhalt * 0.08
    start = mitte - (3 * breite + 2 * luecke) / 2
    for i, anteil in enumerate((0.34, 0.66, 1.0)):
        hoehe = hoechste * anteil
        x = start + i * (breite + luecke)
        stift.rounded_rectangle([x, balken_unten - hoehe, x + breite, balken_unten],
                                radius=breite * 0.3, fill=HELLGRUEN)
    return bild


def main(argv: list[str]) -> int:
    ziel = Path(argv[1]) if len(argv) > 1 else \
        Path(__file__).resolve().parent.parent / "app" / "symbole"
    ziel.mkdir(parents=True, exist_ok=True)
    for groesse in (180, 192, 512):
        zeichne(groesse).save(ziel / f"symbol-{groesse}.png")
    zeichne(512, maskierbar=True).save(ziel / "symbol-maskierbar-512.png")
    print(f"Symbole geschrieben nach {ziel}:")
    for datei in sorted(ziel.glob("symbol-*.png")):
        print(f"  {datei.name}  ({datei.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
