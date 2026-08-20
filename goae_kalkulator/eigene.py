"""Eigene Analogziffern - nur auf dem Geraet des jeweiligen Anwenders.

Nach § 6 Abs. 2 GOAE duerfen Leistungen, die im Gebuehrenverzeichnis nicht
aufgefuehrt sind, entsprechend einer nach Art, Kosten- und Zeitaufwand
gleichwertigen Ziffer berechnet werden. Die Punktzahl und die
Steigerungsklasse ergeben sich dabei aus der herangezogenen Ziffer; nach
§ 12 Abs. 4 GOAE ist die Leistung auf der Rechnung verstaendlich zu
beschreiben und die herangezogene Nummer anzugeben.

Diese Ziffern gehoeren dem einzelnen Anwender und nicht dem Programm. Sie
liegen deshalb neben den Angeboten im persoenlichen Ablageordner und nicht
im mitgelieferten Katalog - so ueberlebt die eigene Sammlung jede
Aktualisierung des amtlichen Verzeichnisses.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from .katalog import Katalog
from .modelle import Leistung
from .speicher import standard_verzeichnis

DATEINAME = "eigene_ziffern.json"

# Zulaessige eigene Nummern: Buchstaben, Ziffern, Bindestrich, Punkt.
NUMMER_MUSTER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 .\-]{0,15}$")


class EigeneFehler(Exception):
    """Fehler beim Anlegen oder Lesen einer eigenen Ziffer."""


class EigeneZiffern:
    """Verwaltet die Analogziffern eines Anwenders."""

    def __init__(self, pfad: Path | str | None = None):
        ordner = Path(pfad).expanduser() if pfad else standard_verzeichnis()
        self.datei = ordner / DATEINAME if ordner.suffix != ".json" else Path(ordner)

    # -- Lesen und Schreiben ---------------------------------------------
    def _lesen(self) -> list[dict]:
        if not self.datei.exists():
            return []
        try:
            daten = json.loads(self.datei.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as fehler:
            raise EigeneFehler(
                f"{self.datei} kann nicht gelesen werden: {fehler}"
            ) from fehler
        return daten if isinstance(daten, list) else []

    def _schreiben(self, eintraege: list[dict]) -> None:
        self.datei.parent.mkdir(parents=True, exist_ok=True)
        inhalt = json.dumps(eintraege, ensure_ascii=False, indent=2)
        temp = self.datei.with_suffix(".json.tmp")
        temp.write_text(inhalt + "\n", encoding="utf-8")
        temp.replace(self.datei)

    # -- Zugriff ----------------------------------------------------------
    def alle(self) -> list[Leistung]:
        return [self._zu_leistung(e) for e in self._lesen()]

    def __len__(self) -> int:
        return len(self._lesen())

    @staticmethod
    def _zu_leistung(eintrag: dict) -> Leistung:
        return Leistung(
            nummer=eintrag["nummer"],
            bezeichnung=eintrag["bezeichnung"],
            punktzahl=int(eintrag["punktzahl"]),
            abschnitt=eintrag.get("abschnitt", ""),
            klasse=eintrag.get("klasse", "aerztlich"),
            regelsatz=Decimal(str(eintrag.get("regelsatz", "2.3"))),
            hoechstsatz=Decimal(str(eintrag.get("hoechstsatz", "3.5"))),
            herkunft="analog",
            analog_zu=eintrag.get("analog_zu", ""),
        )

    def hole(self, nummer: str) -> Leistung:
        gesucht = str(nummer).strip().upper()
        for eintrag in self._lesen():
            if eintrag["nummer"].upper() == gesucht:
                return self._zu_leistung(eintrag)
        raise EigeneFehler(f"Eigene Ziffer {nummer!r} ist nicht vorhanden.")

    # -- Anlegen und Aendern ----------------------------------------------
    def anlegen(
        self,
        katalog: Katalog,
        bezeichnung: str,
        analog_zu: str,
        nummer: str | None = None,
    ) -> Leistung:
        """Legt eine Analogziffer an.

        bezeichnung  die tatsaechlich erbrachte Leistung
        analog_zu    die herangezogene Ziffer des Gebuehrenverzeichnisses
        nummer       eigene Nummer; ohne Angabe "A" + herangezogene Nummer

        Punktzahl und Steigerungsklasse werden von der herangezogenen Ziffer
        uebernommen und sind nicht frei waehlbar: § 6 Abs. 2 GOAE laesst die
        Berechnung "entsprechend" einer gleichwertigen Leistung zu - die
        Gebuehr ist damit die jener Leistung.
        """
        bezeichnung = " ".join(str(bezeichnung).split())
        if not bezeichnung:
            raise EigeneFehler("Die Leistung braucht eine Bezeichnung.")
        try:
            vorlage = katalog.hole(analog_zu)
        except KeyError as fehler:
            raise EigeneFehler(
                f"Die herangezogene Ziffer {analog_zu!r} steht nicht im Katalog."
            ) from fehler

        nummer = (nummer or f"A{vorlage.nummer}").strip()
        if not NUMMER_MUSTER.match(nummer):
            raise EigeneFehler(
                f"{nummer!r} ist als Nummer nicht geeignet - erlaubt sind Buchstaben, "
                "Ziffern, Leerzeichen, Punkt und Bindestrich (bis 16 Zeichen)."
            )
        if nummer in katalog:
            raise EigeneFehler(
                f"Die Nummer {nummer!r} ist im amtlichen Verzeichnis bereits vergeben."
            )
        eintraege = self._lesen()
        if any(e["nummer"].upper() == nummer.upper() for e in eintraege):
            raise EigeneFehler(f"Eine eigene Ziffer {nummer!r} gibt es bereits.")

        eintraege.append({
            "nummer": nummer,
            "bezeichnung": bezeichnung,
            "punktzahl": vorlage.punktzahl,
            "analog_zu": vorlage.nummer,
            "abschnitt": vorlage.abschnitt,
            "klasse": vorlage.klasse,
            "regelsatz": str(vorlage.regelsatz),
            "hoechstsatz": str(vorlage.hoechstsatz),
        })
        self._schreiben(eintraege)
        return self._zu_leistung(eintraege[-1])

    def loeschen(self, nummer: str) -> Leistung:
        gesucht = str(nummer).strip().upper()
        eintraege = self._lesen()
        uebrig = [e for e in eintraege if e["nummer"].upper() != gesucht]
        if len(uebrig) == len(eintraege):
            raise EigeneFehler(f"Eigene Ziffer {nummer!r} ist nicht vorhanden.")
        entfernt = next(e for e in eintraege if e["nummer"].upper() == gesucht)
        self._schreiben(uebrig)
        return self._zu_leistung(entfernt)


def katalog_mit_eigenen(katalog: Katalog, eigene: EigeneZiffern) -> Katalog:
    """Legt die eigenen Ziffern ueber den amtlichen Katalog.

    Der mitgelieferte Katalog bleibt unberuehrt; die Zusammenfuehrung
    geschieht nur im Arbeitsspeicher.
    """
    zusammen = Katalog(katalog.alle(), quelle=katalog.quelle)
    for leistung in eigene.alle():
        zusammen.ergaenzen(Katalog([leistung]))
    return zusammen
