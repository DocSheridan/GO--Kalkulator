"""Datenmodell und Betragsberechnung nach GOAE."""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Any

# Punktwert nach § 5 Abs. 1 GOAE: 5,82873 Cent je Punkt.
PUNKTWERT = Decimal("0.0582873")

# Vom Anwender gewuenschte Anzeigespalten (einfacher Satz, Regelsatz, Hoechstsatz).
ANZEIGE_FAKTOREN = (Decimal("1.0"), Decimal("2.3"), Decimal("3.5"))

# Harte Grenzen fuer die automatische Faktorverteilung.
MIN_FAKTOR = Decimal("1.0")
MAX_FAKTOR = Decimal("3.5")

# Steigerungsklassen nach § 5 GOAE: (Regelhoechstsatz, Hoechstsatz).
KLASSEN: dict[str, tuple[Decimal, Decimal]] = {
    "aerztlich": (Decimal("2.3"), Decimal("3.5")),
    "technisch": (Decimal("1.8"), Decimal("2.5")),
    "labor": (Decimal("1.15"), Decimal("1.3")),
}


def euro(wert: Decimal | float | str) -> Decimal:
    """Kaufmaennisch auf volle Cent runden."""
    return Decimal(str(wert)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# Uebliche Abstufung der Steigerungsfaktoren in der Praxis: Zehntelschritte.
FAKTOR_SCHRITT = Decimal("0.1")

# Feinste darstellbare Stufe. Wird nur gebraucht, wenn ein Zielbetrag auf den
# Cent genau getroffen werden soll und Zehntelschritte dafuer zu grob sind.
FAKTOR_RASTER = Decimal("0.001")


def faktor(wert: Decimal | float | str) -> Decimal:
    """Faktor auf die feinste zulaessige Stufe normieren."""
    return Decimal(str(wert)).quantize(FAKTOR_RASTER, rounding=ROUND_HALF_UP)


def faktor_text(wert: Decimal) -> str:
    """Faktor lesbar ausgeben: 2,3 statt 2,300 - aber 3,359 bleibt vollstaendig."""
    text = f"{Decimal(str(wert)):.3f}".rstrip("0")
    if text.endswith("."):
        text += "0"
    return text.replace(".", ",")


def geld(wert: Decimal) -> str:
    """Deutsche Schreibweise eines Geldbetrags: 1.234,50."""
    text = f"{Decimal(str(wert)):,.2f}"
    return text.replace(",", "#").replace(".", ",").replace("#", ".")


def betrag_fuer(punktzahl: int, faktorwert: Decimal) -> Decimal:
    """Einzelbetrag einer Leistung: Punktzahl x Punktwert x Faktor."""
    return euro(Decimal(punktzahl) * PUNKTWERT * Decimal(str(faktorwert)))


@dataclass(frozen=True)
class Leistung:
    """Ein Eintrag des GOAE-Katalogs."""

    nummer: str
    bezeichnung: str
    punktzahl: int
    abschnitt: str = ""
    klasse: str = "aerztlich"
    regelsatz: Decimal = Decimal("2.3")
    hoechstsatz: Decimal = Decimal("3.5")
    # "eigen" = Punktzahl steht bei dieser Nummer, "gruppe" = sie gilt im
    # Verzeichnis fuer eine Gruppe von Nummern (verbundene Zelle).
    herkunft: str = "eigen"

    @property
    def einfachsatz(self) -> Decimal:
        return betrag_fuer(self.punktzahl, Decimal("1.0"))

    @property
    def satz_2_3(self) -> Decimal:
        return betrag_fuer(self.punktzahl, Decimal("2.3"))

    @property
    def satz_3_5(self) -> Decimal:
        return betrag_fuer(self.punktzahl, Decimal("3.5"))

    def betrag(self, faktorwert: Decimal) -> Decimal:
        return betrag_fuer(self.punktzahl, faktorwert)


@dataclass
class Position:
    """Eine Abrechnungsziffer innerhalb eines Angebots."""

    nummer: str
    bezeichnung: str
    punktzahl: int
    anzahl: int = 1
    faktor: Decimal = Decimal("2.3")
    fixiert: bool = False
    abschnitt: str = ""
    klasse: str = "aerztlich"
    regelsatz: Decimal = Decimal("2.3")
    hoechstsatz: Decimal = Decimal("3.5")
    begruendung: str = ""
    herkunft: str = "eigen"

    def __post_init__(self) -> None:
        self.faktor = faktor(self.faktor)
        self.regelsatz = faktor(self.regelsatz)
        self.hoechstsatz = faktor(self.hoechstsatz)
        self.anzahl = int(self.anzahl)
        self.punktzahl = int(self.punktzahl)

    # -- Betraege ---------------------------------------------------------
    @property
    def einzelbetrag(self) -> Decimal:
        """Betrag einer einzelnen Leistungserbringung beim gesetzten Faktor."""
        return betrag_fuer(self.punktzahl, self.faktor)

    @property
    def betrag(self) -> Decimal:
        """Gesamtbetrag der Position (Einzelbetrag x Anzahl)."""
        return self.einzelbetrag * self.anzahl

    @property
    def basis(self) -> Decimal:
        """Ungerundeter Betrag je Faktoreinheit - Rechengroesse der Optimierung."""
        return Decimal(self.punktzahl) * PUNKTWERT * Decimal(self.anzahl)

    def betrag_bei(self, faktorwert: Decimal | float | str) -> Decimal:
        """Gesamtbetrag der Position bei einem beliebigen Faktor."""
        return betrag_fuer(self.punktzahl, Decimal(str(faktorwert))) * self.anzahl

    @property
    def einfachsatz(self) -> Decimal:
        return self.betrag_bei(Decimal("1.0"))

    @property
    def satz_2_3(self) -> Decimal:
        return self.betrag_bei(Decimal("2.3"))

    @property
    def satz_3_5(self) -> Decimal:
        return self.betrag_bei(Decimal("3.5"))

    # -- Plausibilitaet ---------------------------------------------------
    @property
    def ueber_regelsatz(self) -> bool:
        """Faktor oberhalb des Schwellenwerts - Begruendung nach § 12 GOAE noetig."""
        return self.faktor > self.regelsatz

    @property
    def ueber_hoechstsatz(self) -> bool:
        """Faktor oberhalb des Hoechstsatzes der Steigerungsklasse."""
        return self.faktor > self.hoechstsatz

    def hinweis(self) -> str:
        if self.ueber_hoechstsatz:
            return f"Faktor > Hoechstsatz {faktor_text(self.hoechstsatz)} ({self.klasse})"
        if self.ueber_regelsatz and not self.begruendung:
            return "Begruendung erforderlich (> Regelsatz)"
        if self.herkunft == "gruppe":
            return "Punktzahl gilt im Verzeichnis fuer eine Gruppe von Nummern"
        return ""

    # -- Serialisierung ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "nummer": self.nummer,
            "bezeichnung": self.bezeichnung,
            "punktzahl": self.punktzahl,
            "anzahl": self.anzahl,
            "faktor": str(self.faktor),
            "fixiert": self.fixiert,
            "abschnitt": self.abschnitt,
            "klasse": self.klasse,
            "regelsatz": str(self.regelsatz),
            "hoechstsatz": str(self.hoechstsatz),
            "begruendung": self.begruendung,
            "herkunft": self.herkunft,
        }

    @classmethod
    def from_dict(cls, daten: dict[str, Any]) -> "Position":
        return cls(
            nummer=str(daten["nummer"]),
            bezeichnung=daten.get("bezeichnung", ""),
            punktzahl=int(daten["punktzahl"]),
            anzahl=int(daten.get("anzahl", 1)),
            faktor=Decimal(str(daten.get("faktor", "2.3"))),
            fixiert=bool(daten.get("fixiert", False)),
            abschnitt=daten.get("abschnitt", ""),
            klasse=daten.get("klasse", "aerztlich"),
            regelsatz=Decimal(str(daten.get("regelsatz", "2.3"))),
            hoechstsatz=Decimal(str(daten.get("hoechstsatz", "3.5"))),
            begruendung=daten.get("begruendung", ""),
            herkunft=daten.get("herkunft", "eigen"),
        )

    @classmethod
    def aus_leistung(
        cls, leistung: Leistung, anzahl: int = 1, faktorwert: Decimal | None = None
    ) -> "Position":
        return cls(
            nummer=leistung.nummer,
            bezeichnung=leistung.bezeichnung,
            punktzahl=leistung.punktzahl,
            anzahl=anzahl,
            faktor=faktorwert if faktorwert is not None else leistung.regelsatz,
            abschnitt=leistung.abschnitt,
            klasse=leistung.klasse,
            regelsatz=leistung.regelsatz,
            hoechstsatz=leistung.hoechstsatz,
            herkunft=leistung.herkunft,
        )


def _jetzt() -> str:
    return _dt.datetime.now().replace(microsecond=0).isoformat(sep=" ")


@dataclass
class Angebot:
    """Ein benanntes Leistungspaket aus mehreren GOAE-Ziffern."""

    name: str
    positionen: list[Position] = field(default_factory=list)
    beschreibung: str = ""
    patient: str = ""
    erstellt: str = field(default_factory=_jetzt)
    geaendert: str = field(default_factory=_jetzt)
    zielbetrag: Decimal | None = None

    # -- Positionen -------------------------------------------------------
    def hinzufuegen(self, position: Position) -> Position:
        self.positionen.append(position)
        return position

    def entfernen(self, index: int) -> Position:
        return self.positionen.pop(index)

    # -- Summen -----------------------------------------------------------
    @property
    def summe(self) -> Decimal:
        return sum((p.betrag for p in self.positionen), Decimal("0.00"))

    @property
    def summe_einfach(self) -> Decimal:
        return sum((p.einfachsatz for p in self.positionen), Decimal("0.00"))

    @property
    def summe_2_3(self) -> Decimal:
        return sum((p.satz_2_3 for p in self.positionen), Decimal("0.00"))

    @property
    def summe_3_5(self) -> Decimal:
        return sum((p.satz_3_5 for p in self.positionen), Decimal("0.00"))

    @property
    def punkte(self) -> int:
        return sum(p.punktzahl * p.anzahl for p in self.positionen)

    def spanne(
        self, min_f: Decimal = MIN_FAKTOR, max_f: Decimal = MAX_FAKTOR
    ) -> tuple[Decimal, Decimal]:
        """Erreichbarer Summenbereich unter Beruecksichtigung fixierter Positionen."""
        unten = Decimal("0.00")
        oben = Decimal("0.00")
        for p in self.positionen:
            if p.fixiert:
                unten += p.betrag
                oben += p.betrag
            else:
                unten += p.betrag_bei(min_f)
                oben += p.betrag_bei(max_f)
        return unten, oben

    def hinweise(self) -> list[str]:
        meldungen = []
        for p in self.positionen:
            h = p.hinweis()
            if h:
                meldungen.append(f"Ziffer {p.nummer}: {h}")
        return meldungen

    # -- Serialisierung ---------------------------------------------------
    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "beschreibung": self.beschreibung,
            "patient": self.patient,
            "erstellt": self.erstellt,
            "geaendert": self.geaendert,
            "zielbetrag": str(self.zielbetrag) if self.zielbetrag is not None else None,
            "positionen": [p.to_dict() for p in self.positionen],
        }

    @classmethod
    def from_dict(cls, daten: dict[str, Any]) -> "Angebot":
        ziel = daten.get("zielbetrag")
        return cls(
            name=daten["name"],
            positionen=[Position.from_dict(p) for p in daten.get("positionen", [])],
            beschreibung=daten.get("beschreibung", ""),
            patient=daten.get("patient", ""),
            erstellt=daten.get("erstellt", _jetzt()),
            geaendert=daten.get("geaendert", _jetzt()),
            zielbetrag=Decimal(str(ziel)) if ziel not in (None, "") else None,
        )

    def beruehren(self) -> None:
        self.geaendert = _jetzt()
