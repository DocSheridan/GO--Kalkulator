"""Laden, Durchsuchen und Importieren des GOAE-Leistungskatalogs."""

from __future__ import annotations

import csv
import io
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .modelle import KLASSEN, Leistung

STANDARD_KATALOG = Path(__file__).resolve().parent.parent / "daten" / "goae_katalog.csv"

SPALTEN = ("nummer", "bezeichnung", "punktzahl", "abschnitt", "klasse",
           "regelsatz", "hoechstsatz", "herkunft")


class KatalogFehler(Exception):
    """Fehler beim Einlesen einer Katalogdatei."""


def _entziffere_trennzeichen(kopfzeile: str) -> str:
    for kandidat in (";", "\t", ","):
        if kandidat in kopfzeile:
            return kandidat
    return ";"


def _dezimal(wert: str, standard: str) -> Decimal:
    text = (wert or "").strip().replace(",", ".")
    if not text:
        return Decimal(standard)
    try:
        return Decimal(text)
    except InvalidOperation as fehler:
        raise KatalogFehler(f"Ungueltiger Zahlenwert: {wert!r}") from fehler


class Katalog:
    """Sammlung von GOAE-Leistungen, durchsuchbar nach Nummer und Text."""

    def __init__(self, leistungen: list[Leistung] | None = None, quelle: Path | None = None):
        self._nach_nummer: dict[str, Leistung] = {}
        self.quelle = quelle
        for leistung in leistungen or []:
            self._nach_nummer[leistung.nummer.upper()] = leistung

    # -- Laden ------------------------------------------------------------
    @classmethod
    def laden(cls, pfad: Path | str | None = None) -> "Katalog":
        pfad = Path(pfad) if pfad else STANDARD_KATALOG
        if not pfad.exists():
            raise KatalogFehler(f"Katalogdatei nicht gefunden: {pfad}")
        return cls.aus_text(pfad.read_text(encoding="utf-8-sig"), quelle=pfad)

    @classmethod
    def aus_text(cls, text: str, quelle: Path | None = None) -> "Katalog":
        # Kommentarzeilen (#) und Leerzeilen vor dem Parsen entfernen.
        zeilen = [z for z in text.splitlines() if z.strip() and not z.lstrip().startswith("#")]
        if not zeilen:
            raise KatalogFehler("Katalogdatei enthaelt keine Daten.")
        trenner = _entziffere_trennzeichen(zeilen[0])
        leser = csv.DictReader(io.StringIO("\n".join(zeilen)), delimiter=trenner)
        fehlend = {"nummer", "punktzahl"} - {(f or "").strip().lower() for f in (leser.fieldnames or [])}
        if fehlend:
            raise KatalogFehler(
                "Kopfzeile unvollstaendig, es fehlen: " + ", ".join(sorted(fehlend))
            )

        leistungen: list[Leistung] = []
        for nr, zeile in enumerate(leser, start=2):
            daten = {(k or "").strip().lower(): (v or "").strip() for k, v in zeile.items()}
            nummer = daten.get("nummer", "")
            if not nummer:
                continue
            try:
                punktzahl = int(Decimal(daten.get("punktzahl", "0").replace(",", ".")))
            except (InvalidOperation, ValueError) as fehler:
                raise KatalogFehler(
                    f"Zeile {nr}: Punktzahl {daten.get('punktzahl')!r} ist keine Zahl."
                ) from fehler
            klasse = (daten.get("klasse") or "aerztlich").lower()
            regel_std, hoechst_std = KLASSEN.get(klasse, KLASSEN["aerztlich"])
            leistungen.append(
                Leistung(
                    nummer=nummer,
                    bezeichnung=daten.get("bezeichnung", ""),
                    punktzahl=punktzahl,
                    abschnitt=daten.get("abschnitt", ""),
                    klasse=klasse if klasse in KLASSEN else "aerztlich",
                    regelsatz=_dezimal(daten.get("regelsatz", ""), str(regel_std)),
                    hoechstsatz=_dezimal(daten.get("hoechstsatz", ""), str(hoechst_std)),
                    herkunft=(daten.get("herkunft") or "eigen").lower(),
                    analog_zu=daten.get("analog_zu", ""),
                )
            )
        if not leistungen:
            raise KatalogFehler("Katalogdatei enthaelt keine Leistungen.")
        return cls(leistungen, quelle=quelle)

    # -- Zugriff ----------------------------------------------------------
    def __len__(self) -> int:
        return len(self._nach_nummer)

    def __iter__(self):
        return iter(self.alle())

    def __contains__(self, nummer: object) -> bool:
        return str(nummer).upper() in self._nach_nummer

    def alle(self) -> list[Leistung]:
        return sorted(self._nach_nummer.values(), key=_sortierschluessel)

    def hole(self, nummer: str) -> Leistung:
        leistung = self._nach_nummer.get(str(nummer).strip().upper())
        if leistung is None:
            raise KeyError(f"GOAE-Ziffer {nummer!r} ist im Katalog nicht enthalten.")
        return leistung

    def suche(self, begriff: str) -> list[Leistung]:
        """Sucht in Nummer und Bezeichnung (ohne Beachtung der Gross-/Kleinschreibung)."""
        text = (begriff or "").strip().lower()
        if not text:
            return self.alle()
        treffer = [
            l
            for l in self.alle()
            if text in l.nummer.lower() or text in l.bezeichnung.lower()
        ]
        # Exakte Nummerntreffer zuerst, dann die eigenen Analogziffern - sie
        # sind wenige und der Anwender sucht meist genau diese.
        treffer.sort(key=lambda l: (l.nummer.lower() != text,
                                    l.herkunft != "analog",
                                    _sortierschluessel(l)))
        return treffer

    def ergaenzen(self, andere: "Katalog") -> None:
        """Eintraege eines weiteren Katalogs uebernehmen (gleiche Nummer wird ersetzt)."""
        for leistung in andere.alle():
            self._nach_nummer[leistung.nummer.upper()] = leistung

    def speichern(self, pfad: Path | str) -> Path:
        pfad = Path(pfad)
        pfad.parent.mkdir(parents=True, exist_ok=True)
        with pfad.open("w", encoding="utf-8", newline="") as datei:
            schreiber = csv.writer(datei, delimiter=";")
            schreiber.writerow(SPALTEN)
            for l in self.alle():
                schreiber.writerow(
                    [l.nummer, l.bezeichnung, l.punktzahl, l.abschnitt, l.klasse,
                     l.regelsatz, l.hoechstsatz, l.herkunft]
                )
        return pfad


_NUMMER_MUSTER = re.compile(r"^([^\d]*)(\d*)(.*)$")


def _sortierschluessel(leistung: Leistung) -> tuple:
    """Nach Zahlenwert sortieren; ein Buchstabenzusatz folgt seiner Grundnummer.

    So steht 250a hinter 250 und vor 251; Zuschlaege mit Buchstabenpraefix
    (K 1, K 2) stehen am Ende.
    """
    praefix, ziffern, suffix = _NUMMER_MUSTER.match(leistung.nummer).groups()
    return (praefix.strip().lower(), int(ziffern) if ziffern else 0, suffix.lower())
