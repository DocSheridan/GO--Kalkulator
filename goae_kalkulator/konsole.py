"""Menuegefuehrte Bedienung im Terminal - Alternative zur Fenster-Oberflaeche."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from .cli import Abbruch, angebot_tabelle, betrag, katalog_tabelle, position_aus
from .eigene import EigeneFehler, EigeneZiffern, katalog_mit_eigenen
from .excel import exportiere
from .katalog import Katalog, KatalogFehler
from .modelle import FAKTOR_SCHRITT, MAX_FAKTOR, MIN_FAKTOR, Angebot, faktor_text, geld
from .speicher import Angebotsverzeichnis, SpeicherFehler, dateiname
from .zielbetrag import STRATEGIEN, optimiere_faktoren

TRENNER = "=" * 78


def frage(text: str, standard: str = "") -> str:
    zusatz = f" [{standard}]" if standard else ""
    antwort = input(f"{text}{zusatz}: ").strip()
    return antwort or standard


def ja(text: str, standard: bool = False) -> bool:
    vorgabe = "J/n" if standard else "j/N"
    antwort = input(f"{text} ({vorgabe}): ").strip().lower()
    if not antwort:
        return standard
    return antwort in ("j", "ja", "y", "yes")


def kopf(titel: str) -> None:
    print(f"\n{TRENNER}\n{titel}\n{TRENNER}")


class Konsole:
    def __init__(self, katalog: Katalog, verzeichnis: Angebotsverzeichnis,
                 eigene: EigeneZiffern | None = None):
        self.amtlich = katalog
        self.eigene = eigene or EigeneZiffern(verzeichnis.pfad)
        self.katalog = katalog_mit_eigenen(katalog, self.eigene)
        self.verzeichnis = verzeichnis

    # -- Hauptmenue -------------------------------------------------------
    def lauf(self) -> int:
        kopf("GOAE-Abrechnungskalkulator")
        print(f"Katalog:     {len(self.katalog)} Ziffern ({self.katalog.quelle})")
        print(f"Angebote in: {self.verzeichnis.pfad}")
        while True:
            kopf("Hauptmenue")
            print("  1  Neues Angebot anlegen")
            print("  2  Gespeichertes Angebot oeffnen")
            print("  3  Gespeicherte Angebote auflisten")
            print("  4  GOAE-Katalog durchsuchen")
            print("  5  Alle Angebote nach Excel exportieren")
            print("  6  Eigene Analogziffern verwalten")
            print("  0  Beenden")
            wahl = input("\nAuswahl: ").strip()
            try:
                if wahl == "1":
                    self.neues_angebot()
                elif wahl == "2":
                    self.oeffne_angebot()
                elif wahl == "3":
                    self.liste()
                elif wahl == "4":
                    self.suche_katalog()
                elif wahl == "5":
                    self.export_alle()
                elif wahl == "6":
                    self.eigene_ziffern()
                elif wahl in ("0", "q", "ende"):
                    print("Auf Wiedersehen.")
                    return 0
                else:
                    print("Bitte eine der angebotenen Ziffern eingeben.")
            except (Abbruch, SpeicherFehler, KatalogFehler) as fehler:
                print(f"\n! {fehler}")
            except KeyboardInterrupt:
                print("\nAbgebrochen.")

    # -- Katalog ----------------------------------------------------------
    def suche_katalog(self) -> None:
        begriff = frage("Suchbegriff (Nummer oder Text, leer = alle)")
        treffer = self.katalog.suche(begriff)
        kopf(f"Katalogtreffer: {len(treffer)}")
        if treffer:
            print(katalog_tabelle(treffer, grenze=40))
        else:
            print("Keine passende Ziffer gefunden.")

    # -- Eigene Analogziffern ---------------------------------------------
    def eigene_ziffern(self) -> None:
        while True:
            ziffern = self.eigene.alle()
            kopf(f"Eigene Analogziffern ({len(ziffern)})")
            print("Nach § 6 Abs. 2 GOAE koennen nicht aufgefuehrte Leistungen entsprechend")
            print("einer gleichwertigen Ziffer berechnet werden. Punktzahl und Steigerungs-")
            print("klasse ergeben sich aus der herangezogenen Ziffer.")
            print(f"\nAblage: {self.eigene.datei}  (nur auf diesem Geraet)\n")
            if ziffern:
                for i, l in enumerate(ziffern, start=1):
                    print(f"  {i:>2}  {l.nummer:<10} {l.bezeichnung[:44]:<46} "
                          f"analog {l.analog_zu:<6} {geld(l.satz_2_3):>9} EUR (2,3)")
            else:
                print("  (noch keine)")
            print("\n  n  Neue Analogziffer   l  Loeschen   0  Zurueck")
            wahl = input("\nAuswahl: ").strip().lower()
            try:
                if wahl == "n":
                    self._eigene_anlegen()
                elif wahl == "l":
                    self._eigene_loeschen(ziffern)
                elif wahl in ("0", "q", ""):
                    return
            except (Abbruch, EigeneFehler) as fehler:
                print(f"\n! {fehler}")

    def _eigene_anlegen(self) -> None:
        bezeichnung = frage("Erbrachte Leistung")
        if not bezeichnung:
            return
        print("Welche Ziffer des Verzeichnisses ist gleichwertig? ('?' sucht)")
        while True:
            vorlage = input("Herangezogene Ziffer: ").strip()
            if not vorlage:
                return
            if vorlage.startswith("?"):
                treffer = self.amtlich.suche(vorlage[1:].strip())
                print(katalog_tabelle(treffer, grenze=20) if treffer else "Kein Treffer.")
                continue
            break
        nummer = frage("Eigene Nummer", f"A{vorlage}")
        leistung = self.eigene.anlegen(self.amtlich, bezeichnung, vorlage, nummer)
        self.katalog = katalog_mit_eigenen(self.amtlich, self.eigene)
        print(f"\nAngelegt: {leistung.nummer} - {leistung.punktzahl} Punkte, "
              f"{geld(leistung.einfachsatz)} / {geld(leistung.satz_2_3)} / "
              f"{geld(leistung.satz_3_5)} EUR")

    def _eigene_loeschen(self, ziffern) -> None:
        if not ziffern:
            return
        wahl = frage("Welche Nummer loeschen? (Zeilennummer oder Ziffer)")
        if not wahl:
            return
        if wahl.isdigit() and 1 <= int(wahl) <= len(ziffern):
            wahl = ziffern[int(wahl) - 1].nummer
        entfernt = self.eigene.loeschen(wahl)
        self.katalog = katalog_mit_eigenen(self.amtlich, self.eigene)
        print(f"Geloescht: {entfernt.nummer}")

    # -- Angebote ---------------------------------------------------------
    def liste(self) -> None:
        eintraege = self.verzeichnis.liste()
        kopf(f"Gespeicherte Angebote ({len(eintraege)})")
        if not eintraege:
            print("Noch nichts gespeichert.")
            return
        for i, e in enumerate(eintraege, start=1):
            print(f"  {i:>2}  {e['name'][:40]:<42} {geld(e['summe']):>10} EUR   "
                  f"{e['positionen']} Pos.  {e['geaendert']}")

    def _waehle_angebot(self) -> Angebot | None:
        eintraege = self.verzeichnis.liste()
        if not eintraege:
            print("Es sind noch keine Angebote gespeichert.")
            return None
        self.liste()
        wahl = frage("\nNummer oder Name (leer = zurueck)")
        if not wahl:
            return None
        if wahl.isdigit() and 1 <= int(wahl) <= len(eintraege):
            return self.verzeichnis.laden_aus(eintraege[int(wahl) - 1]["datei"])
        return self.verzeichnis.laden(wahl)

    def oeffne_angebot(self) -> None:
        angebot = self._waehle_angebot()
        if angebot is not None:
            self.bearbeite(angebot, gespeichert=True)

    def neues_angebot(self) -> None:
        name = frage("Name des Angebots")
        if not name:
            print("Ohne Namen kann kein Angebot angelegt werden.")
            return
        if self.verzeichnis.existiert(name) and not ja(
            f"Ein Angebot {name!r} gibt es bereits. Trotzdem weiter (wird ueberschrieben)?"
        ):
            return
        angebot = Angebot(
            name=name,
            patient=frage("Patient/in (optional)"),
            beschreibung=frage("Kurzbeschreibung (optional)"),
        )
        print("\nZiffern eingeben - Format NUMMER[xANZAHL][@FAKTOR], z.B. 3x2@2,5")
        print("Leere Eingabe beendet die Erfassung, '?' sucht im Katalog.")
        self._erfasse_ziffern(angebot)
        self.bearbeite(angebot, gespeichert=False)

    def _erfasse_ziffern(self, angebot: Angebot) -> None:
        while True:
            eingabe = input("Ziffer: ").strip()
            if not eingabe:
                return
            if eingabe.startswith("?"):
                treffer = self.katalog.suche(eingabe[1:].strip())
                print(katalog_tabelle(treffer, grenze=25) if treffer else "Kein Treffer.")
                continue
            try:
                position = position_aus(self.katalog, eingabe)
            except Abbruch as fehler:
                print(f"  ! {fehler}")
                continue
            angebot.hinzufuegen(position)
            print(f"  + {position.nummer} {position.bezeichnung[:44]} "
                  f"({position.anzahl}x, Faktor {position.faktor}) = {geld(position.betrag)} EUR")

    # -- Angebotsbearbeitung ----------------------------------------------
    def bearbeite(self, angebot: Angebot, gespeichert: bool) -> None:
        veraendert = not gespeichert
        while True:
            kopf(f"Angebot: {angebot.name}" + ("" if not veraendert else "   * ungespeichert"))
            if angebot.positionen:
                print(angebot_tabelle(angebot))
            else:
                print("(noch keine Positionen)")
            unten, oben = angebot.spanne()
            print(f"\nErreichbar durch Faktorwahl: {geld(unten)} bis {geld(oben)} EUR")
            if angebot.zielbetrag is not None:
                print(f"Zielbetrag: {geld(angebot.zielbetrag)} EUR "
                      f"(Abweichung {geld(angebot.summe - angebot.zielbetrag)} EUR)")
            print("\n  z  Ziffer(n) hinzufuegen        f  Faktor einer Position aendern")
            print("  e  Position entfernen          x  Position fixieren / freigeben")
            print("  a  Anzahl aendern              b  Begruendung erfassen")
            print("  g  Gesamtpreis vorgeben        n  Name / Patient / Beschreibung")
            print("  s  Speichern                   t  Nach Excel exportieren")
            print("  0  Zurueck zum Hauptmenue")
            wahl = input("\nAuswahl: ").strip().lower()
            try:
                if wahl == "z":
                    print("Format NUMMER[xANZAHL][@FAKTOR], leer beendet, '?' sucht.")
                    self._erfasse_ziffern(angebot)
                    veraendert = True
                elif wahl == "e":
                    veraendert = self._entferne(angebot) or veraendert
                elif wahl == "f":
                    veraendert = self._setze_faktor(angebot) or veraendert
                elif wahl == "a":
                    veraendert = self._setze_anzahl(angebot) or veraendert
                elif wahl == "x":
                    veraendert = self._fixiere(angebot) or veraendert
                elif wahl == "b":
                    veraendert = self._begruendung(angebot) or veraendert
                elif wahl == "g":
                    veraendert = self._zielbetrag(angebot) or veraendert
                elif wahl == "n":
                    angebot.name = frage("Name", angebot.name)
                    angebot.patient = frage("Patient/in", angebot.patient)
                    angebot.beschreibung = frage("Beschreibung", angebot.beschreibung)
                    veraendert = True
                elif wahl == "s":
                    pfad = self.verzeichnis.speichern(angebot)
                    veraendert = False
                    print(f"Gespeichert: {pfad}")
                elif wahl == "t":
                    self._export(angebot)
                elif wahl in ("0", "q"):
                    if veraendert and ja("Ungespeicherte Aenderungen sichern?", standard=True):
                        print(f"Gespeichert: {self.verzeichnis.speichern(angebot)}")
                    return
                else:
                    print("Unbekannte Auswahl.")
            except (Abbruch, SpeicherFehler) as fehler:
                print(f"! {fehler}")

    def _position_waehlen(self, angebot: Angebot, text: str):
        if not angebot.positionen:
            print("Das Angebot enthaelt keine Positionen.")
            return None
        wahl = frage(f"{text} (Zeilennummer #, leer = abbrechen)")
        if not wahl:
            return None
        if not wahl.isdigit() or not (1 <= int(wahl) <= len(angebot.positionen)):
            print("Bitte eine gueltige Zeilennummer aus der Spalte # eingeben.")
            return None
        return angebot.positionen[int(wahl) - 1]

    def _entferne(self, angebot: Angebot) -> bool:
        position = self._position_waehlen(angebot, "Welche Position entfernen?")
        if position is None:
            return False
        angebot.positionen.remove(position)
        print(f"Entfernt: {position.nummer} {position.bezeichnung[:40]}")
        return True

    def _setze_faktor(self, angebot: Angebot) -> bool:
        position = self._position_waehlen(angebot, "Bei welcher Position den Faktor aendern?")
        if position is None:
            return False
        print(f"  {position.nummer}: 1,0 = {geld(position.einfachsatz)} | "
              f"2,3 = {geld(position.satz_2_3)} | 3,5 = {geld(position.satz_3_5)} EUR")
        eingabe = frage("Neuer Faktor", faktor_text(position.faktor))
        wert = Decimal(eingabe.replace(",", "."))
        if not (MIN_FAKTOR <= wert <= MAX_FAKTOR):
            raise Abbruch(f"Der Faktor muss zwischen {MIN_FAKTOR} und {MAX_FAKTOR} liegen.")
        position.faktor = wert
        print(f"Neuer Betrag: {geld(position.betrag)} EUR")
        if position.hinweis():
            print(f"Hinweis: {position.hinweis()}")
        return True

    def _setze_anzahl(self, angebot: Angebot) -> bool:
        position = self._position_waehlen(angebot, "Bei welcher Position die Anzahl aendern?")
        if position is None:
            return False
        eingabe = frage("Neue Anzahl", str(position.anzahl))
        if not eingabe.isdigit() or int(eingabe) < 1:
            raise Abbruch("Die Anzahl muss eine ganze Zahl ab 1 sein.")
        position.anzahl = int(eingabe)
        return True

    def _fixiere(self, angebot: Angebot) -> bool:
        position = self._position_waehlen(angebot, "Welche Position fixieren/freigeben?")
        if position is None:
            return False
        position.fixiert = not position.fixiert
        zustand = "fixiert (bleibt bei der Zielbetragsrechnung unveraendert)" if position.fixiert \
            else "freigegeben"
        print(f"Ziffer {position.nummer} ist jetzt {zustand}.")
        return True

    def _begruendung(self, angebot: Angebot) -> bool:
        position = self._position_waehlen(angebot, "Begruendung fuer welche Position?")
        if position is None:
            return False
        position.begruendung = frage("Begruendung (§ 12 GOAE)", position.begruendung)
        return True

    def _zielbetrag(self, angebot: Angebot) -> bool:
        if not angebot.positionen:
            print("Bitte zuerst Ziffern erfassen.")
            return False
        unten, oben = angebot.spanne()
        print(f"Moeglich sind {geld(unten)} bis {geld(oben)} EUR "
              f"(Faktoren zwischen {MIN_FAKTOR} und {MAX_FAKTOR}).")
        eingabe = frage("Gewuenschter Gesamtpreis in EUR")
        if not eingabe:
            return False
        ziel = betrag(eingabe)
        print("\nVerteilung:")
        for i, s in enumerate(STRATEGIEN, start=1):
            print(f"  {i}  {s}")
        auswahl = frage("Strategie", "1")
        strategie = STRATEGIEN[int(auswahl) - 1] if auswahl.isdigit() and \
            1 <= int(auswahl) <= len(STRATEGIEN) else auswahl
        raster = frage("Faktorstufung (0,1 / 0,05 / 0,01)", "0,1")
        centgenau = ja("Falls das Raster nicht aufgeht: Betrag centgenau treffen?")
        rechtlich = ja("Hoechstsaetze der Steigerungsklassen zusaetzlich beachten "
                       "(Labor 1,3 / technisch 2,5)?")
        ergebnis = optimiere_faktoren(
            angebot.positionen, ziel, strategie=strategie, rechtliche_grenzen=rechtlich,
            schrittweite=Decimal(raster.replace(",", ".")), nachjustieren=centgenau,
        )
        angebot.zielbetrag = ziel
        print(f"\n{ergebnis}")
        for warnung in ergebnis.warnungen:
            print(f"  ! {warnung}")
        return True

    def _export(self, angebot: Angebot) -> None:
        vorgabe = self.verzeichnis.sicherstellen() / f"{dateiname(angebot.name)}.xlsx"
        ziel = frage("Zieldatei", str(vorgabe))
        pfad = exportiere(angebot, Path(ziel).expanduser())
        print(f"Excel-Datei geschrieben: {pfad}")

    def export_alle(self) -> None:
        angebote = [self.verzeichnis.laden_aus(e["datei"]) for e in self.verzeichnis.liste()]
        if not angebote:
            print("Es sind keine Angebote gespeichert.")
            return
        vorgabe = self.verzeichnis.sicherstellen() / "Angebote.xlsx"
        ziel = frage("Zieldatei", str(vorgabe))
        pfad = exportiere(angebote, Path(ziel).expanduser())
        print(f"{len(angebote)} Angebot(e) geschrieben nach {pfad}")


def starte(katalog_pfad: str | None = None, verzeichnis: str | None = None) -> int:
    katalog = Katalog.laden(katalog_pfad)
    ablage = Angebotsverzeichnis(verzeichnis)
    return Konsole(katalog, ablage, EigeneZiffern(ablage.pfad)).lauf()
