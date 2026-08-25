"""Kommandozeile des GOAE-Abrechnungskalkulators."""

from __future__ import annotations

import argparse
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .eigene import EigeneFehler, EigeneZiffern, katalog_mit_eigenen
from .excel import exportiere
from .katalog import Katalog, KatalogFehler, STANDARD_KATALOG
from .modelle import MAX_FAKTOR, MIN_FAKTOR, Angebot, Position, faktor_text, geld
from .speicher import Angebotsverzeichnis, SpeicherFehler
from .zielbetrag import STRATEGIEN, optimiere_faktoren

# Eigene Analogziffern duerfen frei benannt sein (A-AKU, "Praxis 1"), deshalb
# wird die Angabe von rechts zerlegt: erst der Faktor hinter "@", dann die
# Anzahl hinter einem abschliessenden "x". Alles davor ist die Nummer.
ANZAHL_MUSTER = re.compile(r"^(?P<nummer>.*[^\sx*])\s*[x*]\s*(?P<anzahl>\d+)$", re.IGNORECASE)
NUMMER_MUSTER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .\-]{0,15}$")


class Abbruch(Exception):
    """Vom Anwender verursachter, verstaendlich meldbarer Fehler."""


# -- Hilfsfunktionen ------------------------------------------------------

def betrag(text: str) -> Decimal:
    """Wandelt eine Eingabe wie '1.234,50' oder '1234.5' in einen Decimal um."""
    roh = str(text).strip().replace("EUR", "").replace("€", "").strip()
    if roh.count(",") == 1 and (roh.rfind(",") > roh.rfind(".")):
        roh = roh.replace(".", "").replace(",", ".")
    else:
        roh = roh.replace(",", "")
    try:
        return Decimal(roh).quantize(Decimal("0.01"))
    except InvalidOperation as fehler:
        raise Abbruch(f"{text!r} ist kein gueltiger Geldbetrag.") from fehler


def zerlege_ziffer(text: str) -> tuple[str, int, Decimal | None]:
    """'3x2@2,5' -> ('3', 2, Decimal('2.5')); auch 'A-AKU' oder 'K 2'."""
    rest = str(text or "").strip()
    if not rest:
        raise Abbruch("Es wurde keine Ziffer angegeben.")

    faktorwert = None
    if "@" in rest:
        rest, _, roh = rest.rpartition("@")
        roh = roh.strip().replace(",", ".")
        try:
            faktorwert = Decimal(roh)
        except InvalidOperation as fehler:
            raise Abbruch(f"{roh!r} ist kein gueltiger Faktor.") from fehler
        if not (MIN_FAKTOR <= faktorwert <= MAX_FAKTOR):
            raise Abbruch(f"Der Faktor muss zwischen {MIN_FAKTOR} und {MAX_FAKTOR} liegen.")

    anzahl = 1
    treffer = ANZAHL_MUSTER.match(rest.strip())
    if treffer:
        rest = treffer.group("nummer")
        anzahl = int(treffer.group("anzahl"))
        if anzahl < 1:
            raise Abbruch("Die Anzahl muss mindestens 1 betragen.")

    nummer = rest.strip()
    if not NUMMER_MUSTER.match(nummer):
        raise Abbruch(
            f"{text!r} ist keine gueltige Angabe. Erwartet: NUMMER[xANZAHL][@FAKTOR], "
            "z.B. 3x2@2,5"
        )
    return nummer, anzahl, faktorwert


def tabelle(kopf: list[str], zeilen: list[list[str]], rechts: set[int] | None = None) -> str:
    rechts = rechts or set()
    breiten = [len(k) for k in kopf]
    for zeile in zeilen:
        for i, feld in enumerate(zeile):
            breiten[i] = max(breiten[i], len(str(feld)))

    def formatiere(felder: list[str]) -> str:
        teile = []
        for i, feld in enumerate(felder):
            teile.append(str(feld).rjust(breiten[i]) if i in rechts else str(feld).ljust(breiten[i]))
        return "  ".join(teile).rstrip()

    linien = [formatiere(kopf), "  ".join("-" * b for b in breiten)]
    linien += [formatiere(z) for z in zeilen]
    return "\n".join(linien)


def angebot_tabelle(angebot: Angebot) -> str:
    zeilen = []
    for i, p in enumerate(angebot.positionen, start=1):
        marke = "  (fix)" if p.fixiert else ""
        zeilen.append([
            str(i), p.nummer, p.bezeichnung[:44], str(p.anzahl),
            geld(p.einfachsatz), geld(p.satz_2_3), geld(p.satz_3_5),
            f"{faktor_text(p.faktor)}{marke}", geld(p.betrag),
        ])
    zeilen.append([
        "", "", f"SUMME ({len(angebot.positionen)} Positionen)", "",
        geld(angebot.summe_einfach), geld(angebot.summe_2_3), geld(angebot.summe_3_5),
        "", geld(angebot.summe),
    ])
    kopf = ["#", "Ziffer", "Leistung", "Anz", "1,0-fach", "2,3-fach", "3,5-fach", "Faktor", "Betrag"]
    text = tabelle(kopf, zeilen, rechts={0, 3, 4, 5, 6, 8})
    hinweise = angebot.hinweise()
    if hinweise:
        text += "\n\nHinweise:\n" + "\n".join(f"  - {h}" for h in hinweise)
    return text


def katalog_tabelle(leistungen, grenze: int | None = None) -> str:
    gekuerzt = leistungen[:grenze] if grenze else leistungen
    zeilen = [
        [l.nummer, l.bezeichnung[:52], str(l.punktzahl),
         geld(l.einfachsatz), geld(l.satz_2_3), geld(l.satz_3_5),
         (f"analog {l.analog_zu}" if l.herkunft == "analog"
          else f"{l.abschnitt} / {l.klasse}" + (" *" if l.herkunft == "sammel" else ""))]
        for l in gekuerzt
    ]
    text = tabelle(
        ["Ziffer", "Leistung", "Punkte", "1,0-fach", "2,3-fach", "3,5-fach", "Abschn./Klasse"],
        zeilen, rechts={2, 3, 4, 5},
    )
    if any(l.herkunft == "sammel" for l in gekuerzt):
        text += "\n* Punktzahl stammt aus der Ueberschrift einer Sammelposition."
    if grenze and len(leistungen) > grenze:
        text += f"\n... {len(leistungen) - grenze} weitere Treffer (Suchbegriff eingrenzen)"
    return text


def lade_amtlichen_katalog(pfad: str | None) -> Katalog:
    """Nur das amtliche Verzeichnis, ohne die eigenen Ziffern."""
    try:
        return Katalog.laden(pfad)
    except KatalogFehler as fehler:
        raise Abbruch(str(fehler)) from fehler


def lade_katalog(pfad: str | None, verzeichnis: str | None = None) -> Katalog:
    """Amtlicher Katalog, ergaenzt um die eigenen Analogziffern."""
    katalog = lade_amtlichen_katalog(pfad)
    try:
        return katalog_mit_eigenen(katalog, EigeneZiffern(verzeichnis))
    except EigeneFehler as fehler:
        raise Abbruch(str(fehler)) from fehler


def position_aus(katalog: Katalog, angabe: str) -> Position:
    nummer, anzahl, faktorwert = zerlege_ziffer(angabe)
    try:
        leistung = katalog.hole(nummer)
    except KeyError as fehler:
        raise Abbruch(str(fehler).strip("'")) from fehler
    return Position.aus_leistung(leistung, anzahl=anzahl, faktorwert=faktorwert)


# -- Befehle --------------------------------------------------------------

def befehl_katalog(args) -> int:
    katalog = lade_katalog(args.katalog, args.verzeichnis)
    treffer = katalog.suche(args.suche or "")
    if not treffer:
        print(f"Keine Ziffer passt zu {args.suche!r}.")
        return 1
    print(katalog_tabelle(treffer, grenze=None if args.alle else 40))
    print(f"\n{len(treffer)} von {len(katalog)} Ziffern | Katalog: {katalog.quelle}")
    return 0


def befehl_liste(args) -> int:
    verzeichnis = Angebotsverzeichnis(args.verzeichnis)
    eintraege = verzeichnis.liste()
    if not eintraege:
        print(f"Noch keine Angebote gespeichert unter {verzeichnis.pfad}")
        return 0
    zeilen = [
        [e["name"][:38], e["patient"][:20], str(e["positionen"]), geld(e["summe"]), e["geaendert"]]
        for e in eintraege
    ]
    print(tabelle(["Angebot", "Patient/in", "Pos.", "Summe", "Geaendert"], zeilen, rechts={2, 3}))
    print(f"\n{len(eintraege)} Angebot(e) in {verzeichnis.pfad}")
    return 0


def befehl_zeige(args) -> int:
    verzeichnis = Angebotsverzeichnis(args.verzeichnis)
    try:
        angebot = verzeichnis.laden(args.name)
    except SpeicherFehler as fehler:
        raise Abbruch(str(fehler)) from fehler
    print(f"Angebot: {angebot.name}")
    if angebot.patient:
        print(f"Patient/in: {angebot.patient}")
    if angebot.beschreibung:
        print(f"Beschreibung: {angebot.beschreibung}")
    if angebot.zielbetrag is not None:
        print(f"Zielbetrag: {geld(angebot.zielbetrag)} EUR")
    print(f"Zuletzt geaendert: {angebot.geaendert}\n")
    print(angebot_tabelle(angebot))
    return 0


def befehl_neu(args) -> int:
    katalog = lade_katalog(args.katalog, args.verzeichnis)
    verzeichnis = Angebotsverzeichnis(args.verzeichnis)
    if verzeichnis.existiert(args.name) and not args.ueberschreiben:
        raise Abbruch(
            f"Es gibt bereits ein Angebot {args.name!r}. "
            "Mit --ueberschreiben ersetzen oder einen anderen Namen waehlen."
        )
    angebot = Angebot(name=args.name, patient=args.patient or "", beschreibung=args.beschreibung or "")
    for angabe in args.ziffer:
        angebot.hinzufuegen(position_aus(katalog, angabe))
    if not angebot.positionen:
        raise Abbruch("Bitte mindestens eine Ziffer angeben (-z 1 -z 8 ...).")
    if args.ziel:
        angebot.zielbetrag = betrag(args.ziel)
        ergebnis = optimiere_faktoren(
            angebot.positionen, angebot.zielbetrag,
            strategie=args.strategie, rechtliche_grenzen=args.rechtliche_grenzen,
        )
        print(ergebnis, "\n")
    pfad = verzeichnis.speichern(angebot)
    print(angebot_tabelle(angebot))
    print(f"\nGespeichert: {pfad}")
    return 0


def befehl_bearbeiten(args) -> int:
    katalog = lade_katalog(args.katalog, args.verzeichnis)
    verzeichnis = Angebotsverzeichnis(args.verzeichnis)
    try:
        angebot = verzeichnis.laden(args.name)
    except SpeicherFehler as fehler:
        raise Abbruch(str(fehler)) from fehler

    for angabe in args.ziffer:
        angebot.hinzufuegen(position_aus(katalog, angabe))
    for nummer in args.entferne:
        passend = [p for p in angebot.positionen if p.nummer == nummer]
        if not passend:
            raise Abbruch(f"Ziffer {nummer} ist im Angebot nicht enthalten.")
        angebot.positionen.remove(passend[-1])
    for zuweisung in args.faktor:
        nummer, _, wert = zuweisung.partition("=")
        if not wert:
            raise Abbruch(f"Erwartet wird NUMMER=FAKTOR, erhalten: {zuweisung!r}")
        neuer = Decimal(wert.replace(",", "."))
        if not (MIN_FAKTOR <= neuer <= MAX_FAKTOR):
            raise Abbruch(f"Der Faktor muss zwischen {MIN_FAKTOR} und {MAX_FAKTOR} liegen.")
        getroffen = [p for p in angebot.positionen if p.nummer == nummer.strip()]
        if not getroffen:
            raise Abbruch(f"Ziffer {nummer} ist im Angebot nicht enthalten.")
        for p in getroffen:
            p.faktor = neuer
    for nummer in args.fixiere:
        for p in angebot.positionen:
            if p.nummer == nummer:
                p.fixiert = True
    for nummer in args.loese:
        for p in angebot.positionen:
            if p.nummer == nummer:
                p.fixiert = False
    if args.patient is not None:
        angebot.patient = args.patient
    if args.beschreibung is not None:
        angebot.beschreibung = args.beschreibung

    pfad = verzeichnis.speichern(angebot)
    print(angebot_tabelle(angebot))
    print(f"\nGespeichert: {pfad}")
    return 0


def befehl_ziel(args) -> int:
    verzeichnis = Angebotsverzeichnis(args.verzeichnis)
    try:
        angebot = verzeichnis.laden(args.name)
    except SpeicherFehler as fehler:
        raise Abbruch(str(fehler)) from fehler
    ziel = betrag(args.betrag)
    ergebnis = optimiere_faktoren(
        angebot.positionen, ziel,
        strategie=args.strategie,
        min_faktor=Decimal(str(args.min_faktor).replace(",", ".")),
        max_faktor=Decimal(str(args.max_faktor).replace(",", ".")),
        rechtliche_grenzen=args.rechtliche_grenzen,
        schrittweite=Decimal(str(args.schrittweite).replace(",", ".")),
        nachjustieren=args.centgenau,
    )
    angebot.zielbetrag = ziel
    print(angebot_tabelle(angebot))
    print()
    print(f"Erreichbarer Bereich: {geld(ergebnis.min_summe)} bis {geld(ergebnis.max_summe)} EUR")
    print(ergebnis)
    for warnung in ergebnis.warnungen:
        print(f"  ! {warnung}")
    if args.probe:
        print("\n(Probelauf - nichts gespeichert)")
        return 0
    pfad = verzeichnis.speichern(angebot)
    print(f"\nGespeichert: {pfad}")
    return 0


def befehl_excel(args) -> int:
    verzeichnis = Angebotsverzeichnis(args.verzeichnis)
    try:
        if args.alle:
            angebote = [verzeichnis.laden(n) for n in verzeichnis.namen()]
        else:
            if not args.name:
                raise Abbruch("Bitte einen Angebotsnamen angeben oder --alle verwenden.")
            angebote = [verzeichnis.laden(n) for n in args.name]
    except SpeicherFehler as fehler:
        raise Abbruch(str(fehler)) from fehler
    if not angebote:
        raise Abbruch("Es sind keine Angebote zum Export vorhanden.")
    if args.ausgabe:
        ziel = Path(args.ausgabe)
    elif len(angebote) == 1:
        from .speicher import dateiname
        ziel = verzeichnis.sicherstellen() / f"{dateiname(angebote[0].name)}.xlsx"
    else:
        ziel = verzeichnis.sicherstellen() / "Angebote.xlsx"
    pfad = exportiere(angebote if len(angebote) > 1 else angebote[0], ziel)
    print(f"Excel-Datei geschrieben: {pfad}")
    return 0


def befehl_loeschen(args) -> int:
    verzeichnis = Angebotsverzeichnis(args.verzeichnis)
    try:
        pfad = verzeichnis.loeschen(args.name)
    except SpeicherFehler as fehler:
        raise Abbruch(str(fehler)) from fehler
    print(f"Geloescht: {pfad}")
    return 0


def befehl_eigene_liste(args) -> int:
    eigene = EigeneZiffern(args.verzeichnis)
    ziffern = eigene.alle()
    if not ziffern:
        print(f"Noch keine eigenen Ziffern in {eigene.datei}")
        return 0
    zeilen = [
        [l.nummer, l.bezeichnung[:46], l.analog_zu, str(l.punktzahl),
         geld(l.einfachsatz), geld(l.satz_2_3), geld(l.satz_3_5), l.klasse]
        for l in ziffern
    ]
    print(tabelle(["Nummer", "Leistung", "analog zu", "Punkte",
                   "1,0-fach", "2,3-fach", "3,5-fach", "Klasse"],
                  zeilen, rechts={3, 4, 5, 6}))
    print(f"\n{len(ziffern)} eigene Ziffer(n) in {eigene.datei}")
    return 0


def befehl_eigene_neu(args) -> int:
    katalog = lade_amtlichen_katalog(args.katalog)
    eigene = EigeneZiffern(args.verzeichnis)
    try:
        leistung = eigene.anlegen(
            katalog, bezeichnung=args.bezeichnung, analog_zu=args.analog_zu,
            nummer=args.nummer,
        )
    except EigeneFehler as fehler:
        raise Abbruch(str(fehler)) from fehler
    vorlage = katalog.hole(args.analog_zu)
    print(f"Angelegt: {leistung.nummer}  {leistung.bezeichnung}")
    print(f"  entsprechend Nr. {leistung.analog_zu} ({vorlage.bezeichnung[:50]})")
    print(f"  {leistung.punktzahl} Punkte, Klasse {leistung.klasse} "
          f"(Regelsatz {faktor_text(leistung.regelsatz)}, "
          f"Hoechstsatz {faktor_text(leistung.hoechstsatz)})")
    print(f"  {geld(leistung.einfachsatz)} / {geld(leistung.satz_2_3)} / "
          f"{geld(leistung.satz_3_5)} EUR")
    print(f"\nGespeichert in {eigene.datei}")
    return 0


def befehl_eigene_loeschen(args) -> int:
    eigene = EigeneZiffern(args.verzeichnis)
    try:
        entfernt = eigene.loeschen(args.nummer)
    except EigeneFehler as fehler:
        raise Abbruch(str(fehler)) from fehler
    print(f"Geloescht: {entfernt.nummer}  {entfernt.bezeichnung}")
    return 0


def befehl_katalog_import(args) -> int:
    try:
        neu = Katalog.laden(args.datei)
    except KatalogFehler as fehler:
        raise Abbruch(str(fehler)) from fehler
    ziel = Path(args.ziel) if args.ziel else STANDARD_KATALOG
    if not args.ersetzen and ziel.exists():
        vorhanden = Katalog.laden(ziel)
        vorhanden.ergaenzen(neu)
        neu = vorhanden
    neu.speichern(ziel)
    print(f"{len(neu)} Ziffern geschrieben nach {ziel}")
    return 0


def befehl_gui(args) -> int:
    from .gui import starte
    return starte(katalog_pfad=args.katalog, verzeichnis=args.verzeichnis)


def befehl_konsole(args) -> int:
    from .konsole import starte
    return starte(katalog_pfad=args.katalog, verzeichnis=args.verzeichnis)


# -- Argumentzerlegung ----------------------------------------------------

def baue_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="kalkulator",
        description="GOAE-Abrechnungskalkulator - Leistungspakete kalkulieren, "
                    "speichern und nach Excel exportieren.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Beispiele:\n"
            "  kalkulator katalog beratung\n"
            "  kalkulator neu \"Check-up Basis\" -z 1 -z 8 -z 650 -z 410x2\n"
            "  kalkulator ziel \"Check-up Basis\" 250,00\n"
            "  kalkulator excel \"Check-up Basis\"\n"
            "  kalkulator konsole      (menuegefuehrte Bedienung)\n"
            "  kalkulator gui          (Fenster-Oberflaeche)\n"
        ),
    )
    parser.add_argument("--katalog", help="abweichende Katalogdatei (CSV)")
    parser.add_argument("--verzeichnis", help="Ablageordner der Angebote")
    unter = parser.add_subparsers(dest="befehl")

    p = unter.add_parser("katalog", help="GOAE-Ziffern anzeigen und durchsuchen")
    p.add_argument("suche", nargs="?", help="Suchbegriff (Nummer oder Text)")
    p.add_argument("--alle", action="store_true", help="Ausgabe nicht auf 40 Zeilen begrenzen")
    p.set_defaults(funktion=befehl_katalog)

    p = unter.add_parser("liste", help="gespeicherte Angebote auflisten")
    p.set_defaults(funktion=befehl_liste)

    p = unter.add_parser("zeige", help="ein gespeichertes Angebot anzeigen")
    p.add_argument("name")
    p.set_defaults(funktion=befehl_zeige)

    p = unter.add_parser("neu", help="neues Angebot anlegen und speichern")
    p.add_argument("name")
    p.add_argument("-z", "--ziffer", action="append", default=[],
                   metavar="NR[xANZ][@FAKTOR]", help="GOAE-Ziffer, mehrfach angebbar")
    p.add_argument("--patient", help="Name der Patientin / des Patienten")
    p.add_argument("--beschreibung")
    p.add_argument("--ziel", help="Gesamtpreis, auf den die Faktoren verteilt werden")
    p.add_argument("--strategie", choices=STRATEGIEN, default="proportional")
    p.add_argument("--rechtliche-grenzen", action="store_true",
                   help="Hoechstsatz der Steigerungsklasse zusaetzlich beachten")
    p.add_argument("--ueberschreiben", action="store_true")
    p.set_defaults(funktion=befehl_neu)

    p = unter.add_parser("bearbeiten", help="gespeichertes Angebot aendern")
    p.add_argument("name")
    p.add_argument("-z", "--ziffer", action="append", default=[], metavar="NR[xANZ][@FAKTOR]")
    p.add_argument("--entferne", action="append", default=[], metavar="NR")
    p.add_argument("--faktor", action="append", default=[], metavar="NR=WERT")
    p.add_argument("--fixiere", action="append", default=[], metavar="NR")
    p.add_argument("--loese", action="append", default=[], metavar="NR")
    p.add_argument("--patient")
    p.add_argument("--beschreibung")
    p.set_defaults(funktion=befehl_bearbeiten)

    p = unter.add_parser("ziel", help="Faktoren auf einen Gesamtpreis verteilen")
    p.add_argument("name")
    p.add_argument("betrag", help="gewuenschte Gesamtsumme, z.B. 250,00")
    p.add_argument("--strategie", choices=STRATEGIEN, default="proportional")
    p.add_argument("--min-faktor", dest="min_faktor", default=str(MIN_FAKTOR))
    p.add_argument("--max-faktor", dest="max_faktor", default=str(MAX_FAKTOR))
    p.add_argument("--rechtliche-grenzen", action="store_true")
    p.add_argument("--schrittweite", default="0.1",
                   help="Raster der Faktoren, Vorgabe 0,1 (Zehntelschritte)")
    p.add_argument("--centgenau", action="store_true",
                   help="notfalls feinere Faktoren zulassen, um den Betrag exakt zu treffen")
    p.add_argument("--probe", action="store_true", help="nur rechnen, nicht speichern")
    p.set_defaults(funktion=befehl_ziel)

    p = unter.add_parser("excel", help="Angebot(e) als .xlsx exportieren")
    p.add_argument("name", nargs="*")
    p.add_argument("--alle", action="store_true", help="alle gespeicherten Angebote exportieren")
    p.add_argument("-o", "--ausgabe", help="Zieldatei")
    p.set_defaults(funktion=befehl_excel)

    p = unter.add_parser("loeschen", help="gespeichertes Angebot entfernen")
    p.add_argument("name")
    p.set_defaults(funktion=befehl_loeschen)

    p = unter.add_parser("eigene", help="eigene Analogziffern verwalten (§ 6 Abs. 2 GOAE)")
    eigen_unter = p.add_subparsers(dest="unterbefehl")
    q = eigen_unter.add_parser("liste", help="eigene Ziffern anzeigen")
    q.set_defaults(funktion=befehl_eigene_liste)
    q = eigen_unter.add_parser("neu", help="Analogziffer anlegen")
    q.add_argument("bezeichnung", help="die tatsaechlich erbrachte Leistung")
    q.add_argument("analog_zu", metavar="ANALOG-ZU",
                   help="herangezogene Ziffer des Gebuehrenverzeichnisses")
    q.add_argument("--nummer", help="eigene Nummer (Vorgabe: A + herangezogene Nummer)")
    q.set_defaults(funktion=befehl_eigene_neu)
    q = eigen_unter.add_parser("loeschen", help="eigene Ziffer entfernen")
    q.add_argument("nummer")
    q.set_defaults(funktion=befehl_eigene_loeschen)
    p.set_defaults(funktion=befehl_eigene_liste)

    p = unter.add_parser("katalog-import", help="fremde GOAE-Ziffern aus CSV uebernehmen")
    p.add_argument("datei")
    p.add_argument("--ziel", help="Zielkatalog (Vorgabe: mitgelieferter Katalog)")
    p.add_argument("--ersetzen", action="store_true", help="vorhandenen Katalog ersetzen")
    p.set_defaults(funktion=befehl_katalog_import)

    p = unter.add_parser("konsole", help="menuegefuehrte Bedienung im Terminal")
    p.set_defaults(funktion=befehl_konsole)

    p = unter.add_parser("gui", help="Fenster-Oberflaeche starten")
    p.set_defaults(funktion=befehl_gui)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = baue_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "funktion", None):
        # Ohne Befehl: Oberflaeche starten, ersatzweise die Konsole.
        try:
            import tkinter  # noqa: F401
        except ImportError:
            print("Keine Fenster-Oberflaeche verfuegbar (Modul tkinter fehlt) - "
                  "es wird die menuegefuehrte Konsole gestartet.\n")
            return befehl_konsole(args)
        return befehl_gui(args)
    try:
        return args.funktion(args)
    except Abbruch as fehler:
        print(f"Fehler: {fehler}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nAbgebrochen.")
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
