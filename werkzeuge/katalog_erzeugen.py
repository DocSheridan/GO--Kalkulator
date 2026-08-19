#!/usr/bin/env python3
"""Erzeugt daten/goae_katalog.csv aus dem amtlichen GOAE-Text.

Datenquelle
-----------
Gebuehrenordnung fuer Aerzte (GOAE), amtliche Fassung von "Gesetze im
Internet" (Bundesministerium der Justiz), Datei BJNR015220982.xml aus
https://www.gesetze-im-internet.de/go__1982/xml.zip

Als maschinenlesbare Aufbereitung dieses XML dient das npm-Paket
@fin.cx/fee-schedules (MIT), Datei .onlygit/fee-schedules.json:

    npm pack @fin.cx/fee-schedules
    tar xzf fin.cx-fee-schedules-*.tgz
    python3 werkzeuge/katalog_erzeugen.py package/.onlygit/fee-schedules.json

Der Gesetzestext selbst ist ein amtliches Werk und nach § 5 UrhG
gemeinfrei.

Was das Skript tut
------------------
* liest alle Zeilen des Gebuehrenverzeichnisses (Nummer, Legende, Punktzahl)
* ordnet jeder Nummer ihren Abschnitt B bis P ueber die amtlichen
  Nummernbereiche der Inhaltsuebersicht zu
* leitet daraus die Steigerungsklasse nach § 5 GOAE ab:
    - Abschnitt M und Nummer 437 (§ 5 Abs. 4): 1,15 / 1,3
    - Abschnitte A, E und O       (§ 5 Abs. 3): 1,8  / 2,5
    - alle uebrigen               (§ 5 Abs. 2): 2,3  / 3,5
  Abschnitt A ist kein eigener Nummernbereich, sondern die im
  Gebuehrenverzeichnis unter "A. Gebuehren in besonderen Faellen"
  namentlich aufgezaehlten Nummern; diese Liste steht unten.
* uebernimmt Nummern, deren Punktzahl im gedruckten Verzeichnis in einer
  verbundenen Zelle fuer eine Gruppe gilt (typisch im Basislabor), mit der
  Punktzahl des Gruppeneintrags und kennzeichnet sie als "gruppe".

Die Betragsspalte des amtlichen Verzeichnisses ist noch in DM angegeben
(0,114 DM je Punkt) und wird deshalb nicht uebernommen - der Eurobetrag
ergibt sich nach § 5 Abs. 1 GOAE aus Punktzahl x 0,0582873 EUR x Faktor.
"""

from __future__ import annotations

import csv
import json
import re
import sys
from pathlib import Path

# Amtliche Nummernbereiche der Abschnitte laut Inhaltsuebersicht der Anlage.
ABSCHNITTE: list[tuple[int, int, str, str]] = [
    (1, 109, "B", "Grundleistungen und allgemeine Leistungen"),
    (200, 449, "C", "Nichtgebietsbezogene Sonderleistungen"),
    (450, 498, "D", "Anaesthesieleistungen"),
    (500, 569, "E", "Physikalisch-medizinische Leistungen"),
    (600, 793, "F", "Innere Medizin, Kinderheilkunde, Dermatologie"),
    (800, 887, "G", "Neurologie, Psychiatrie und Psychotherapie"),
    (1001, 1168, "H", "Geburtshilfe und Gynaekologie"),
    (1200, 1386, "I", "Augenheilkunde"),
    (1400, 1639, "J", "Hals-, Nasen-, Ohrenheilkunde"),
    (1700, 1860, "K", "Urologie"),
    (2000, 3321, "L", "Chirurgie, Orthopaedie"),
    (3500, 4787, "M", "Laboratoriumsuntersuchungen"),
    (4800, 4873, "N", "Histologie, Zytologie und Zytogenetik"),
    (5000, 5855, "O", "Strahlendiagnostik, Nuklearmedizin, MRT, Strahlentherapie"),
    (6000, 6018, "P", "Sektionsleistungen"),
]

# "A. Gebuehren in besonderen Faellen": Fuer diese Leistungen duerfen Gebuehren
# nur bis zum Zweieinhalbfachen bemessen werden (Wortlaut des Verzeichnisses).
ABSCHNITT_A: set[int] = set()
for _bereich in [
    (2, 2), (56, 56),                                   # Abschnitt B
    (250, 250), (402, 402), (403, 403),                 # Abschnitt C
    (602, 602), (605, 617), (620, 624), (635, 647),     # Abschnitt F
    (650, 651), (653, 654), (657, 661), (665, 666),
    (725, 726), (759, 761),
    (855, 857),                                         # Abschnitt G
    (1001, 1002),                                       # Abschnitt H
    (1255, 1257), (1259, 1260), (1262, 1263), (1268, 1270),   # Abschnitt I
    (1401, 1401), (1403, 1406), (1558, 1560),           # Abschnitt J
    (4850, 4873),                                       # Abschnitt N
]:
    ABSCHNITT_A.update(range(_bereich[0], _bereich[1] + 1))

# Nummer 250a wird in Abschnitt A ebenfalls genannt (Buchstabenzusatz).
ABSCHNITT_A_TEXT: set[str] = {"250a"}

# Steigerungsklassen nach § 5 GOAE: (Klassenname, Regelsatz, Hoechstsatz)
KLASSE_AERZTLICH = ("aerztlich", "2.3", "3.5")   # § 5 Abs. 2
KLASSE_TECHNISCH = ("technisch", "1.8", "2.5")   # § 5 Abs. 3 (Abschnitte A, E, O)
KLASSE_LABOR = ("labor", "1.15", "1.3")          # § 5 Abs. 4 (Abschnitt M, Nr. 437)

# Groesster Nummernabstand, ueber den eine Gruppenpunktzahl noch uebernommen
# wird. Verhindert, dass eine Punktzahl ueber einen Sprung in der
# Dokumentreihenfolge hinweg auf voellig andere Leistungen uebertragen wird.
MAX_GRUPPENABSTAND = 120


def zahl(code: str) -> int | None:
    treffer = re.match(r"^(\d+)", code.strip())
    return int(treffer.group(1)) if treffer else None


def abschnitt_fuer(code: str) -> tuple[str, str]:
    nummer = zahl(code)
    if nummer is None:
        return "B", "Grundleistungen und allgemeine Leistungen"   # Zuschlaege K 1 / K 2
    for von, bis, buchstabe, titel in ABSCHNITTE:
        if von <= nummer <= bis:
            return buchstabe, titel
    return "", ""


def klasse_fuer(code: str, abschnitt: str) -> tuple[str, str, str]:
    nummer = zahl(code)
    if abschnitt == "M" or nummer == 437:
        return KLASSE_LABOR
    if abschnitt in ("E", "O"):
        return KLASSE_TECHNISCH
    if (nummer is not None and nummer in ABSCHNITT_A) or code.strip() in ABSCHNITT_A_TEXT:
        return KLASSE_TECHNISCH
    return KLASSE_AERZTLICH


def saeubere(text: str) -> str:
    """Mehrfache Leerzeichen und Umbrueche zu einfachen Leerzeichen."""
    return re.sub(r"\s+", " ", (text or "").replace("­", "")).strip()


def lies_zeilen(quelle: Path) -> list[dict]:
    daten = json.loads(quelle.read_text(encoding="utf-8"))
    plaene = daten.get("scheduleData", [])
    goae = next((p for p in plaene if p.get("scheduleId") == "de-goae"), None)
    if goae is None:
        raise SystemExit("In der Quelldatei ist kein GOAE-Gebuehrenverzeichnis enthalten.")
    return goae, goae["feeRows"]


def baue_eintraege(zeilen: list[dict]) -> tuple[list[dict], dict[str, int]]:
    eintraege: list[dict] = []
    gesehen: set[str] = set()
    zaehler = {"eigen": 0, "gruppe": 0, "verworfen": 0}
    letzte_punktzahl: int | None = None
    letzte_nummer: int | None = None
    letzter_abschnitt: str = ""

    for zeile in zeilen:
        code = saeubere(str(zeile.get("code") or ""))
        if not code:
            continue
        bezeichnung = saeubere(str(zeile.get("description") or ""))
        punktzahl = zeile.get("points")
        abschnitt, _titel = abschnitt_fuer(code)
        nummer = zahl(code)

        if punktzahl:
            herkunft = "eigen"
            letzte_punktzahl, letzte_nummer, letzter_abschnitt = int(punktzahl), nummer, abschnitt
        else:
            # Punktzahl steht im gedruckten Verzeichnis in einer verbundenen
            # Zelle beim Gruppeneintrag - nur uebernehmen, wenn die Nummer
            # unmittelbar dazugehoert.
            passend = (
                letzte_punktzahl is not None
                and nummer is not None
                and letzte_nummer is not None
                and abschnitt == letzter_abschnitt
                and 0 < nummer - letzte_nummer <= MAX_GRUPPENABSTAND
            )
            if not passend:
                zaehler["verworfen"] += 1
                continue
            punktzahl, herkunft = letzte_punktzahl, "gruppe"

        if code in gesehen:
            zaehler["verworfen"] += 1
            continue
        gesehen.add(code)

        klasse, regelsatz, hoechstsatz = klasse_fuer(code, abschnitt)
        zaehler[herkunft] += 1
        eintraege.append({
            "nummer": code,
            "bezeichnung": bezeichnung,
            "punktzahl": int(punktzahl),
            "abschnitt": abschnitt,
            "klasse": klasse,
            "regelsatz": regelsatz,
            "hoechstsatz": hoechstsatz,
            "herkunft": herkunft,
        })

    eintraege.sort(key=lambda e: (zahl(e["nummer"]) or 0, e["nummer"]))
    return eintraege, zaehler


def schreibe(eintraege: list[dict], ziel: Path, goae: dict) -> None:
    quelle = goae.get("source", {})
    kopf = f"""\
# GOAE-Leistungskatalog fuer den Abrechnungskalkulator
#
# Quelle: {quelle.get('title', 'Gebuehrenordnung fuer Aerzte')} ({quelle.get('officialAbbreviation', 'GOAE')})
#   amtliche Fassung von "{quelle.get('name', 'Gesetze im Internet')}"
#   {quelle.get('pageUrl', '')}
#   Datei {quelle.get('sourceFileName', '')}, abgerufen {quelle.get('retrievedAt', '')}
# Stand: {goae.get('edition', '')}
#
# Erzeugt mit werkzeuge/katalog_erzeugen.py - nicht von Hand aendern.
# Eigene Ziffern gehoeren in eine zusaetzliche Datei und werden mit
#   kalkulator.py katalog-import <datei.csv>
# eingespielt.
#
# Der Eurobetrag ergibt sich nach § 5 Abs. 1 GOAE aus
#   Punktzahl x 0,0582873 EUR x Steigerungsfaktor.
# Die Betragsspalte des amtlichen Verzeichnisses ist noch in DM gefuehrt und
# daher hier nicht enthalten.
#
# Spalten:
#   nummer        GOAE-Nummer
#   bezeichnung   Leistungslegende (Leerzeichen normiert, sonst unveraendert)
#   punktzahl     Punktzahl nach dem Gebuehrenverzeichnis
#   abschnitt     Abschnitt B bis P des Gebuehrenverzeichnisses
#   klasse        Steigerungsklasse nach § 5 GOAE:
#                   aerztlich  Abs. 2  - Regelsatz 2,3   Hoechstsatz 3,5
#                   technisch  Abs. 3  - Regelsatz 1,8   Hoechstsatz 2,5
#                              (Abschnitte A, E und O)
#                   labor      Abs. 4  - Regelsatz 1,15  Hoechstsatz 1,3
#                              (Abschnitt M und Nummer 437)
#   regelsatz     Schwellenwert; darueber ist eine Begruendung noetig (§ 12 GOAE)
#   hoechstsatz   Hoechstsatz der Steigerungsklasse
#   herkunft      eigen  = Punktzahl steht bei dieser Nummer
#                 gruppe = Punktzahl gilt im Verzeichnis fuer eine Gruppe von
#                          Nummern (verbundene Zelle) und wurde uebernommen
"""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with ziel.open("w", encoding="utf-8", newline="") as datei:
        datei.write(kopf)
        schreiber = csv.DictWriter(
            datei, delimiter=";",
            fieldnames=["nummer", "bezeichnung", "punktzahl", "abschnitt", "klasse",
                        "regelsatz", "hoechstsatz", "herkunft"],
        )
        schreiber.writeheader()
        schreiber.writerows(eintraege)


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(__doc__)
        return 1
    quelle = Path(argv[1])
    ziel = Path(argv[2]) if len(argv) > 2 else \
        Path(__file__).resolve().parent.parent / "daten" / "goae_katalog.csv"
    goae, zeilen = lies_zeilen(quelle)
    eintraege, zaehler = baue_eintraege(zeilen)
    schreibe(eintraege, ziel, goae)
    print(f"{len(eintraege)} Ziffern geschrieben nach {ziel}")
    print(f"  davon mit eigener Punktzahl: {zaehler['eigen']}")
    print(f"  aus Gruppeneintrag uebernommen: {zaehler['gruppe']}")
    print(f"  ohne zuordenbare Punktzahl uebergangen: {zaehler['verworfen']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
