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
* holt die Punktzahl von Nummern, die zu einer Sammelposition gehoeren, aus
  dem Verzeichnistext

Zu den Sammelpositionen
-----------------------
Das Gebuehrenverzeichnis fuehrt viele Laborleistungen als Sammelposition: Eine
Ueberschrift ohne eigene Nummer traegt die Punktzahl, darunter folgt nach dem
Wort "Katalog" eine Liste von Nummern, die alle mit dieser Punktzahl berechnet
werden. Beispiel:

    Untersuchung folgender Messgroessen ..., je Messgroesse   70   7,98
    Katalog  3512 Alpha-Amylase  3513 Gamma-GT  3514 Glukose  ...

Fuer diese Nummern enthaelt die Tabellenaufbereitung des Pakets keine
Punktzahl. Sie wird deshalb aus dem Volltext der Anlage geholt: vom Eintrag
rueckwaerts bis zum naechsten "Katalog", davor stehen Punktzahl und DM-Betrag
der Ueberschrift.

Nummern, die sich so nicht aufloesen lassen, werden nicht uebernommen, sondern
gemeldet - geraten wird nichts.

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

# Punktzahl und DM-Betrag einer Sammelueberschrift, unmittelbar vor "Katalog".
# Der Betrag steht mal mit Komma, mal mit Punkt, gelegentlich als "285,--".
SAMMEL_MUSTER = re.compile(r"(\d{1,5})\s+[\d.]+[.,](?:\d{2}|--)\s+Katalog\s*$")

# Innerhalb eines Sammelblocks: "<Nummer>[.H4] <Bezeichnung>"
BLOCK_EINTRAG = re.compile(r"(?<![\w.])(\d{3,4})(?:\.(H\d?))?\s+(?=[A-ZÄÖÜ])")

# Eintrag mit Hoechstwert-Kennzeichen an der Nummer und eigenem Preis:
#   "3562.H1 Cholesterin 40 4,56"
# Die Tabellenaufbereitung des Pakets verliert alle Nummern mit Zusatz.
MIT_KENNZEICHEN = re.compile(
    r"(?<![\w.])(\d{3,4})\.(H\d?)\s+([A-ZÄÖÜ].{2,190}?)\s+(\d{1,5})\s+"
    r"[\d.]+[.,](?:\d{2}|--)(?=\s)")

# "Fuer die mit H1 gekennzeichneten Untersuchungen ist der Hoechstwert nach
# Nummer 3541.H zu beachten."
KENNZEICHEN_ZUORDNUNG = re.compile(
    r"mit (H\d?) gekennzeichneten Untersuchungen ist der Höchstwert "
    r"nach Nummer ([\d.H]+)")

# Ende eines Sammelblocks: die naechste Ueberschrift mit Punktzahl und Betrag.
BLOCK_ENDE = re.compile(r"\d{1,5}\s+[\d.]+[.,](?:\d{2}|--)")

# "<Punktzahl> <DM-Betrag>" am Ende einer Leistungsbeschreibung.
PREIS_MUSTER = re.compile(r"(?<![\d.,])(\d{1,5})\s+[\d.]+[.,](?:\d{2}|--)")

# Beginn des naechsten Verzeichniseintrags.
NAECHSTER_EINTRAG = re.compile(r"(?<![\w.,])\d{1,4}(?:\.[A-Z]\d?)?\s+[A-ZÄÖÜ]")

# Zuschlaege, die als Hundertsatz der Bezugsleistung berechnet werden und
# deshalb keine eigene Punktzahl haben (§ ... "v.H. des einfachen
# Gebuehrensatzes der betreffenden Leistung").
HUNDERTSATZ = {"441": "100 v.H. des einfachen Gebuehrensatzes, hoechstens 132 DM",
               "5298": "25 v.H. des einfachen Gebuehrensatzes"}


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


def lies_quelle(quelle: Path) -> tuple[dict, list[dict], str]:
    """Liefert Kopfangaben, die Tabellenzeilen und den Volltext der Anlage."""
    daten = json.loads(quelle.read_text(encoding="utf-8"))
    goae = next((p for p in daten.get("scheduleData", [])
                 if p.get("scheduleId") == "de-goae"), None)
    if goae is None:
        raise SystemExit("In der Quelldatei ist kein GOAE-Gebuehrenverzeichnis enthalten.")
    anlage = next((a.get("text", "") for a in goae.get("ruleSections", [])
                   if a.get("reference") == "Anlage"), "")
    if not anlage:
        raise SystemExit("Der Volltext der Anlage fehlt in der Quelldatei.")
    return goae, goae["feeRows"], anlage


class Volltext:
    """Findet Punktzahlen im laufenden Text der Anlage.

    Der Text folgt der Dokumentreihenfolge; ein mitwandernder Zeiger verhindert,
    dass ein Querverweis im Fliesstext ("nach Nummer 3511") mit dem Eintrag
    selbst verwechselt wird.
    """

    def __init__(self, text: str):
        self.text = text
        self.zeiger = 0

    def stelle_von(self, code: str, bezeichnung: str) -> int | None:
        marke = f"{code} {bezeichnung[:38]}"
        stelle = self.text.find(marke, self.zeiger)
        if stelle < 0:
            stelle = self.text.find(marke)
        if stelle < 0:
            return None
        self.zeiger = stelle + len(marke)
        return stelle

    def punktzahl_am_eintrag(self, stelle: int, code: str) -> int | None:
        """Punktzahl hinter der Leistungsbeschreibung dieses Eintrags.

        Gesucht wird "<Punktzahl> <DM-Betrag>" - der Betrag ist zwingend, sonst
        wuerde in einer Sammelliste die naechste Nummer als Punktzahl gelesen
        ("4020 Cortisol 4021 Follitropin ..." ergaebe 4021 Punkte). Das Fenster
        endet am naechsten Eintrag, damit kein fremder Preis einwandert; die
        Beschreibungen der Aufbereitung sind teils gekuerzt, weshalb nicht von
        ihrer Laenge ausgegangen werden kann.
        """
        fenster = self.text[stelle:stelle + 420]
        # Hinter der eigenen Nummer beginnen, sonst gilt sie selbst als
        # naechster Eintrag ("K 1 Zuschlag ..." -> Fenster nach zwei Zeichen zu).
        ab = len(code) + 1
        for schranke in (fenster.find("Katalog"), NAECHSTER_EINTRAG.search(fenster, ab)):
            grenze = schranke if isinstance(schranke, int) else (
                schranke.start() if schranke else -1)
            if grenze > 0:
                fenster = fenster[:grenze]
        treffer = PREIS_MUSTER.search(fenster)
        return int(treffer.group(1)) if treffer else None

    def punktzahl_der_sammelposition(self, stelle: int) -> int | None:
        """Punktzahl der Ueberschrift, zu der dieser Eintrag gehoert."""
        davor = self.text[max(0, stelle - 4000):stelle]
        anker = davor.rfind("Katalog")
        if anker < 0:
            return None
        treffer = SAMMEL_MUSTER.search(davor[:anker + len("Katalog")])
        return int(treffer.group(1)) if treffer else None

    def hoechstwerte(self) -> dict[str, str]:
        """Ordnet jedem Kennzeichen die Nummer seines Hoechstwerts zu."""
        return {m.group(1): m.group(2) for m in KENNZEICHEN_ZUORDNUNG.finditer(self.text)}

    def fehlende_mit_preis(self, bekannt: set[str]) -> list[tuple[str, str, int, str]]:
        """Eintraege, deren Nummer ein Hoechstwert-Kennzeichen traegt.

        Sie stehen mit eigener Punktzahl im Verzeichnis (3562.H1 Cholesterin
        40 4,56), fehlen in der Tabellenaufbereitung aber vollstaendig - und
        damit zentrale Laborziffern wie Cholesterin, Kreatinin oder GOT.
        """
        gefunden: dict[str, tuple[str, int, str]] = {}
        for m in MIT_KENNZEICHEN.finditer(self.text):
            nummer = m.group(1)
            if nummer in bekannt or nummer in gefunden:
                continue
            gefunden[nummer] = (saeubere(m.group(3)), int(m.group(4)), m.group(2))
        return [(nr, bez, p, kz) for nr, (bez, p, kz) in sorted(gefunden.items())]

    def fehlende_nummern(self, bekannt: set[str]) -> list[tuple[str, str, int, str]]:
        """Nummern in Sammelbloecken, die in der Tabellenaufbereitung fehlen.

        Das Paket streicht den Hoechstwert-Zusatz (4022.H4 -> 4022) und verliert
        dabei einige Eintraege ganz - hier werden sie nachgetragen.
        """
        gefunden: dict[str, tuple[str, int, str]] = {}
        for anker in re.finditer(r"\bKatalog\b", self.text):
            rest = self.text[anker.end():anker.end() + 4000]
            # Punktzahl der Ueberschrift genau dieses Blocks.
            kopf = SAMMEL_MUSTER.search(self.text[max(0, anker.start() - 300):anker.end()])
            if kopf is None:
                continue
            punkte = int(kopf.group(1))
            schluss = BLOCK_ENDE.search(rest)
            block = rest[:schluss.start() if schluss else 3000]
            stellen = list(BLOCK_EINTRAG.finditer(block))
            for i, m in enumerate(stellen):
                nummer = m.group(1)
                if nummer in bekannt or nummer in gefunden:
                    continue
                bis = stellen[i + 1].start() if i + 1 < len(stellen) else len(block)
                bezeichnung = saeubere(block[m.end():bis])
                if bezeichnung:
                    gefunden[nummer] = (bezeichnung, punkte, m.group(2) or "")
        return [(nr, bez, p, kz) for nr, (bez, p, kz) in sorted(gefunden.items())]


def baue_eintraege(zeilen: list[dict], anlage: str) -> tuple[list[dict], dict, list[str]]:
    volltext = Volltext(anlage)
    zuordnung = volltext.hoechstwerte()
    eintraege: list[dict] = []
    gesehen: set[str] = set()
    zaehler = {"direkt": 0, "sammel": 0, "nachgetragen": 0}
    offen: list[str] = []

    def aufnehmen(code: str, bezeichnung: str, punktzahl: int, herkunft: str,
                  kennzeichen: str = "") -> None:
        abschnitt, _titel = abschnitt_fuer(code)
        klasse, regelsatz, hoechstsatz = klasse_fuer(code, abschnitt)
        gesehen.add(code)
        zaehler[herkunft] += 1
        eintraege.append({
            "nummer": code, "bezeichnung": bezeichnung, "punktzahl": int(punktzahl),
            "abschnitt": abschnitt, "klasse": klasse,
            "regelsatz": regelsatz, "hoechstsatz": hoechstsatz,
            "herkunft": "direkt" if herkunft == "direkt" else "sammel",
            # Nummer des Hoechstwerts, dem diese Leistung zugeordnet ist.
            "hoechstwert": zuordnung.get(kennzeichen, "") if kennzeichen else "",
        })

    for zeile in zeilen:
        code = saeubere(str(zeile.get("code") or ""))
        bezeichnung = saeubere(str(zeile.get("description") or ""))
        if not code or code in gesehen:
            continue

        if zeile.get("points"):
            aufnehmen(code, bezeichnung, int(zeile["points"]), "direkt")
            volltext.stelle_von(code, bezeichnung)      # Zeiger mitfuehren
            continue

        stelle = volltext.stelle_von(code, bezeichnung)
        if stelle is None:
            offen.append(f"{code} (im Volltext nicht gefunden)")
            continue
        if code in HUNDERTSATZ:
            offen.append(f"{code}: {HUNDERTSATZ[code]} - keine Punktzahl")
            continue
        # Zuerst die Sammelueberschrift - sie ist eindeutig; erst danach der
        # Preis am Eintrag selbst, den die Aufbereitung gelegentlich verliert.
        punkte = volltext.punktzahl_der_sammelposition(stelle)
        if punkte is not None:
            aufnehmen(code, bezeichnung, punkte, "sammel")
            continue
        punkte = volltext.punktzahl_am_eintrag(stelle, code)
        if punkte is not None:
            aufnehmen(code, bezeichnung, punkte, "direkt")
            continue
        offen.append(f"{code} {bezeichnung[:52]}")

    # Was die Tabellenaufbereitung verloren hat, aus dem Volltext nachtragen.
    for nummer, bezeichnung, punkte, kennzeichen in volltext.fehlende_mit_preis(gesehen):
        aufnehmen(nummer, bezeichnung, punkte, "direkt", kennzeichen)
        zaehler["direkt"] -= 1
        zaehler["nachgetragen"] += 1
    for nummer, bezeichnung, punkte, kennzeichen in volltext.fehlende_nummern(gesehen):
        aufnehmen(nummer, bezeichnung, punkte, "sammel", kennzeichen)
        zaehler["sammel"] -= 1
        zaehler["nachgetragen"] += 1

    eintraege.sort(key=lambda e: (zahl(e["nummer"]) or 0, e["nummer"]))
    return eintraege, zaehler, offen


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
#   herkunft      direkt = Punktzahl steht im Verzeichnis bei dieser Nummer
#                 sammel = Nummer gehoert zu einer Sammelposition; die Punktzahl
#                          steht in deren Ueberschrift ("... je Messgroesse 70
#                          7,98 Katalog 3512 ... 3514 Glukose ...")
#   hoechstwert   Nummer des Hoechstwerts, dem die Leistung zugeordnet ist
#                 (im Verzeichnis als Zusatz an der Nummer: 3562.H1 -> 3541.H).
#                 Leer, wenn kein Hoechstwert gilt.
"""
    ziel.parent.mkdir(parents=True, exist_ok=True)
    with ziel.open("w", encoding="utf-8", newline="") as datei:
        datei.write(kopf)
        schreiber = csv.DictWriter(
            datei, delimiter=";",
            fieldnames=["nummer", "bezeichnung", "punktzahl", "abschnitt", "klasse",
                        "regelsatz", "hoechstsatz", "herkunft", "hoechstwert"],
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
    goae, zeilen, anlage = lies_quelle(quelle)
    eintraege, zaehler, offen = baue_eintraege(zeilen, anlage)
    schreibe(eintraege, ziel, goae)
    print(f"{len(eintraege)} Ziffern geschrieben nach {ziel}")
    print(f"  Punktzahl im Verzeichnis bei der Nummer selbst: {zaehler['direkt']}")
    print(f"  Punktzahl aus der Ueberschrift der Sammelposition: {zaehler['sammel']}")
    print(f"  aus dem Volltext nachgetragen (fehlten in der Aufbereitung): "
          f"{zaehler['nachgetragen']}")
    if offen:
        print(f"  nicht uebernommen, weil keine Punktzahl feststellbar: {len(offen)}")
        for eintrag in offen:
            print(f"    {eintrag}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
