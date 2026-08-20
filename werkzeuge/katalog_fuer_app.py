#!/usr/bin/env python3
"""Erzeugt app/daten/goae_katalog.json aus daten/goae_katalog.csv.

Die App rechnet ausschliesslich in Ganzzahlen, damit die Betraege exakt
denen des Schreibtischprogramms entsprechen (Fliesskomma waere hier
unbrauchbar). Deshalb stehen die Faktoren als Tausendstel in der Datei:
2,3 wird zu 2300.

Das Format ist bewusst knapp gehalten - eine Liste von Listen statt
Objekten -, weil die Datei auf dem Telefon dauerhaft vorgehalten wird.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from goae_kalkulator.katalog import Katalog

KLASSENKUERZEL = {"aerztlich": "a", "technisch": "t", "labor": "l"}


def main(argv: list[str]) -> int:
    quelle = Path(argv[1]) if len(argv) > 1 else None
    ziel = Path(argv[2]) if len(argv) > 2 else \
        Path(__file__).resolve().parent.parent / "app" / "daten" / "goae_katalog.json"
    katalog = Katalog.laden(quelle)

    ziffern = [
        [
            l.nummer,
            l.bezeichnung,
            l.punktzahl,
            l.abschnitt,
            KLASSENKUERZEL.get(l.klasse, "a"),
            int(l.regelsatz * 1000),
            int(l.hoechstsatz * 1000),
            1 if l.herkunft == "gruppe" else 0,
        ]
        for l in katalog.alle()
    ]
    inhalt = {
        "hinweis": "Erzeugt mit werkzeuge/katalog_fuer_app.py - nicht von Hand aendern.",
        "quelle": "Gebuehrenordnung fuer Aerzte, amtliche Fassung, Gesetze im Internet",
        "stand": "zuletzt geaendert durch Art. 3b G v. 19.7.2023 I Nr. 197",
        # Punktwert 0,0582873 EUR als Ganzzahl in Einheiten von 10^-7 EUR.
        "punktwert_e7": 582873,
        "spalten": ["nummer", "bezeichnung", "punktzahl", "abschnitt", "klasse",
                    "regelsatz", "hoechstsatz", "gruppe"],
        "ziffern": ziffern,
    }
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(json.dumps(inhalt, ensure_ascii=False, separators=(",", ":")) + "\n",
                    encoding="utf-8")
    print(f"{len(ziffern)} Ziffern geschrieben nach {ziel} "
          f"({ziel.stat().st_size / 1024:.0f} kB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
