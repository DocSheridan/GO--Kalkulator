#!/usr/bin/env python3
"""Erzeugt Pruefvektoren fuer den Abgleich zwischen Programm und App.

Die Smartphone-App rechnet die Faktorverteilung in JavaScript nach. Damit
beide Fassungen nicht auseinanderlaufen, werden hier zufaellige, aber mit
festem Startwert reproduzierbare Faelle aus dem Python-Programm gerechnet
und samt Ergebnis abgelegt. Die App spielt sie nach:

    python3 werkzeuge/pruefvektoren.py
    node app/tests/vergleich.mjs app/tests/pruefvektoren.json

Erwartet wird Uebereinstimmung in jedem einzelnen Faktor - nicht nur in der
Summe.
"""

import json
import random
import sys
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from goae_kalkulator import Angebot, Katalog, Position, optimiere_faktoren

KUERZEL = {"aerztlich": "a", "technisch": "t", "labor": "l"}
STARTWERT = 2026
ANZAHL = 200


def main(argv: list[str]) -> int:
    ziel = Path(argv[1]) if len(argv) > 1 else \
        Path(__file__).resolve().parent.parent / "app" / "tests" / "pruefvektoren.json"
    katalog = Katalog.laden()
    ziffern = katalog.alle()
    random.seed(STARTWERT)

    faelle = []
    while len(faelle) < ANZAHL:
        positionen, roh = [], []
        for leistung in random.sample(ziffern, random.randint(1, 7)):
            anzahl = random.randint(1, 3)
            position = Position.aus_leistung(leistung, anzahl=anzahl)
            positionen.append(position)
            roh.append({
                "nummer": leistung.nummer, "punktzahl": leistung.punktzahl, "anzahl": anzahl,
                "faktor": int(position.faktor * 1000), "klasse": KUERZEL[leistung.klasse],
                "regelsatz": int(leistung.regelsatz * 1000),
                "hoechstsatz": int(leistung.hoechstsatz * 1000), "fixiert": False,
            })
        for i in random.sample(range(len(positionen)), random.randint(0, len(positionen) // 2)):
            positionen[i].fixiert = True
            roh[i]["fixiert"] = True

        unten, oben = Angebot(name="x", positionen=positionen).spanne()
        if oben <= unten:
            continue
        ziel_betrag = (unten + (oben - unten) * Decimal(str(random.random()))).quantize(Decimal("0.01"))
        strategie = random.choice(("proportional", "einheitlich", "regelsatz"))
        raster = random.choice((Decimal("0.1"), Decimal("0.05"), Decimal("0.01")))
        nachjustieren = random.choice((True, False))
        rechtlich = random.choice((True, False))
        ergebnis = optimiere_faktoren(
            positionen, ziel_betrag, strategie=strategie, schrittweite=raster,
            nachjustieren=nachjustieren, rechtliche_grenzen=rechtlich,
        )
        faelle.append({
            "positionen": roh,
            "zielCent": int(ziel_betrag * 100),
            "strategie": strategie,
            "schrittweite": int(raster * 1000),
            "nachjustieren": nachjustieren,
            "rechtlicheGrenzen": rechtlich,
            "erwartet": {
                "summeCent": int(ergebnis.summe * 100),
                "faktoren": [int(p.faktor * 1000) for p in positionen],
                "erreicht": ergebnis.erreicht,
            },
        })

    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(faelle, separators=(",", ":")) + "\n", encoding="utf-8")
    print(f"{len(faelle)} Pruefvektoren geschrieben nach {ziel} "
          f"({ziel.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
