"""Automatische Verteilung der Steigerungsfaktoren auf einen Zielbetrag.

Gesucht sind Faktoren f_i je Abrechnungsziffer, so dass die Summe der
Einzelbetraege einem vorgegebenen Gesamtpreis entspricht.  Dabei gilt
stets 1,0 <= f_i <= 3,5 (bzw. engere, selbst gesetzte Grenzen); fixierte
Positionen bleiben unveraendert.

Vorgehen:
 1. Skalierung: ein gemeinsamer Parameter lambda wird per Intervall-
    halbierung so bestimmt, dass die Summe den Zielbetrag trifft.  Da jeder
    Einzelfaktor an seinen Grenzen abgeschnitten wird, laeuft das auf eine
    Umverteilung hinaus: Ziffern, die an die Grenze stossen, bleiben dort,
    die uebrigen tragen den Rest.
 2. Rasterung: die Faktoren werden auf die Anzeigegenauigkeit (0,01)
    gerundet.
 3. Feinabgleich: der verbleibende Restbetrag wird auf die Ziffern verteilt,
    die ihn am besten aufnehmen koennen.  Gerechnet wird im ueblichen Raster
    von 0,1 Faktorpunkten; laesst sich der Zielbetrag darin nicht centgenau
    darstellen, wird die verbleibende Abweichung ausgewiesen.  Auf Wunsch
    schliesst ein zweiter Durchgang die Luecke mit feineren Faktoren.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable, Sequence

from .modelle import (
    FAKTOR_RASTER, FAKTOR_SCHRITT, MAX_FAKTOR, MIN_FAKTOR, PUNKTWERT, Position,
    euro, geld, faktor as _runde_faktor,
)

STRATEGIEN = ("proportional", "einheitlich", "regelsatz")


@dataclass
class Optimierungsergebnis:
    """Ergebnis einer Zielbetrags-Kalkulation."""

    zielbetrag: Decimal
    summe: Decimal
    faktoren: list[Decimal]
    strategie: str
    min_summe: Decimal
    max_summe: Decimal
    meldung: str = ""
    angewendet: bool = False
    warnungen: list[str] = field(default_factory=list)

    @property
    def abweichung(self) -> Decimal:
        return self.summe - self.zielbetrag

    @property
    def erreicht(self) -> bool:
        return self.abweichung == Decimal("0.00")

    def __str__(self) -> str:
        vorzeichen = "+" if self.abweichung >= 0 else "-"
        zeile = (
            f"Ziel {geld(self.zielbetrag)} EUR -> erreicht {geld(self.summe)} EUR "
            f"(Abweichung {vorzeichen}{geld(abs(self.abweichung))} EUR)"
        )
        return f"{zeile}\n{self.meldung}" if self.meldung else zeile


def _text(wert: Decimal) -> str:
    """Rasterangabe lesbar ausgeben: 0,1 statt 0.100."""
    text = f"{wert.normalize():f}"
    return text.replace(".", ",")


def _grenzen(
    position: Position,
    min_faktor: Decimal,
    max_faktor: Decimal,
    rechtliche_grenzen: bool,
) -> tuple[Decimal, Decimal]:
    unten, oben = min_faktor, max_faktor
    if rechtliche_grenzen:
        oben = min(oben, position.hoechstsatz)
        unten = min(unten, oben)
    return unten, oben


def _startwert(position: Position, strategie: str) -> Decimal:
    if strategie == "regelsatz":
        return position.regelsatz
    if strategie == "einheitlich":
        return Decimal("1")
    start = position.faktor
    return start if start > 0 else Decimal("1")


def _klemme(wert: Decimal, unten: Decimal, oben: Decimal) -> Decimal:
    return max(unten, min(oben, wert))


def optimiere_faktoren(
    positionen: Sequence[Position] | Iterable[Position],
    zielbetrag: Decimal | float | str,
    *,
    strategie: str = "proportional",
    min_faktor: Decimal = MIN_FAKTOR,
    max_faktor: Decimal = MAX_FAKTOR,
    rechtliche_grenzen: bool = False,
    schrittweite: Decimal = FAKTOR_SCHRITT,
    nachjustieren: bool = False,
    anwenden: bool = True,
) -> Optimierungsergebnis:
    """Verteilt die Faktoren so, dass der Zielbetrag moeglichst genau erreicht wird.

    positionen        Positionen des Angebots (fixierte bleiben unveraendert)
    zielbetrag        gewuenschte Gesamtsumme in Euro
    strategie         'proportional' (vorhandene Faktoren skalieren),
                      'einheitlich'  (ein gemeinsamer Faktor fuer alle),
                      'regelsatz'    (Vielfaches des jeweiligen Regelsatzes)
    min_faktor/max_faktor  harte Grenzen, Vorgabe 1,0 bis 3,5
    rechtliche_grenzen     zusaetzlich den Hoechstsatz der Steigerungsklasse
                           beachten (Labor 1,3 / technische Leistungen 2,5)
    schrittweite      Raster der Faktoren, Vorgabe 0,1 (Zehntelschritte)
    nachjustieren     falls das Raster den Betrag nicht centgenau hergibt,
                      einzelne Faktoren feiner setzen
    anwenden          Faktoren direkt in die Positionen schreiben
    """
    if strategie not in STRATEGIEN:
        raise ValueError(f"Unbekannte Strategie {strategie!r}, erlaubt: {', '.join(STRATEGIEN)}")

    positionen = list(positionen)
    ziel = euro(zielbetrag)
    schrittweite = Decimal(str(schrittweite))
    if schrittweite < FAKTOR_RASTER:
        schrittweite = FAKTOR_RASTER
    # normalize() erhaelt die Stufung: 0,1 bleibt Zehntel, nicht Tausendstel.
    schrittweite = schrittweite.normalize()
    min_faktor = _runde_faktor(min_faktor)
    max_faktor = _runde_faktor(max_faktor)
    if min_faktor > max_faktor:
        raise ValueError("Der Mindestfaktor darf nicht groesser als der Hoechstfaktor sein.")

    variabel = [p for p in positionen if not p.fixiert]
    fest = [p for p in positionen if p.fixiert]
    fest_summe = sum((p.betrag for p in fest), Decimal("0.00"))

    grenzen = [_grenzen(p, min_faktor, max_faktor, rechtliche_grenzen) for p in variabel]
    min_summe = fest_summe + sum(
        (p.betrag_bei(g[0]) for p, g in zip(variabel, grenzen)), Decimal("0.00")
    )
    max_summe = fest_summe + sum(
        (p.betrag_bei(g[1]) for p, g in zip(variabel, grenzen)), Decimal("0.00")
    )

    warnungen: list[str] = []

    def ergebnis(faktoren: list[Decimal], meldung: str) -> Optimierungsergebnis:
        summe = fest_summe + sum(
            (p.betrag_bei(f) for p, f in zip(variabel, faktoren)), Decimal("0.00")
        )
        if anwenden:
            for p, f in zip(variabel, faktoren):
                p.faktor = f
        # Faktoren in der Reihenfolge aller Positionen zurueckgeben.
        alle: list[Decimal] = []
        lauf = iter(faktoren)
        for p in positionen:
            alle.append(p.faktor if p.fixiert else next(lauf))
        return Optimierungsergebnis(
            zielbetrag=ziel,
            summe=summe,
            faktoren=alle,
            strategie=strategie,
            min_summe=min_summe,
            max_summe=max_summe,
            meldung=meldung,
            angewendet=anwenden,
            warnungen=warnungen,
        )

    if not variabel:
        return ergebnis(
            [],
            "Keine veraenderbaren Positionen vorhanden - alle Ziffern sind fixiert."
            if positionen
            else "Das Angebot enthaelt keine Positionen.",
        )

    # -- Zielbetrag ausserhalb des erreichbaren Bereichs ---------------------
    if ziel < min_summe:
        warnungen.append(
            f"Zielbetrag liegt unter dem Minimum von {geld(min_summe)} EUR "
            f"(alle Faktoren am unteren Anschlag)."
        )
        return ergebnis(
            [g[0] for g in grenzen],
            f"Zielbetrag {geld(ziel)} EUR ist zu niedrig; "
            f"erreichbar sind mindestens {geld(min_summe)} EUR.",
        )
    if ziel > max_summe:
        warnungen.append(
            f"Zielbetrag liegt ueber dem Maximum von {geld(max_summe)} EUR "
            f"(alle Faktoren am oberen Anschlag)."
        )
        return ergebnis(
            [g[1] for g in grenzen],
            f"Zielbetrag {geld(ziel)} EUR ist zu hoch; "
            f"erreichbar sind hoechstens {geld(max_summe)} EUR.",
        )

    # -- Schritt 1: gemeinsamen Skalierungsfaktor per Bisektion suchen -------
    grob = schrittweite
    starts = [_startwert(p, strategie) for p in variabel]

    def faktoren_bei(lam: float) -> list[Decimal]:
        skala = Decimal(str(lam))
        return [
            _klemme((start * skala).quantize(grob, rounding=ROUND_HALF_UP), g[0], g[1])
            for start, g in zip(starts, grenzen)
        ]

    def summe_bei(lam: float) -> Decimal:
        return fest_summe + sum(
            (p.betrag_bei(f) for p, f in zip(variabel, faktoren_bei(lam))), Decimal("0.00")
        )

    unten, oben = 0.0, 10.0
    for _ in range(120):
        mitte = (unten + oben) / 2
        if summe_bei(mitte) < ziel:
            unten = mitte
        else:
            oben = mitte
    faktoren = faktoren_bei((unten + oben) / 2)

    # -- Schritt 2/3: Restbetrag im gewaehlten Raster feinverteilen ----------
    faktoren, rest = _feinabgleich(variabel, faktoren, grenzen, ziel - fest_summe, grob)

    # Im Zehntelraster geht der Betrag nicht immer centgenau auf. Auf Wunsch
    # schliessen feinere Faktoren die Luecke.
    nachgezogen = 0
    if rest != 0 and nachjustieren and grob > FAKTOR_RASTER:
        vorher = list(faktoren)
        faktoren, rest = _feinabgleich(
            variabel, faktoren, grenzen, ziel - fest_summe, FAKTOR_RASTER
        )
        nachgezogen = sum(1 for a, b in zip(vorher, faktoren) if a != b)

    if rest == 0:
        meldung = f"Zielbetrag exakt erreicht (Strategie: {strategie})."
        if nachgezogen:
            meldung += (f" {nachgezogen} Faktor(en) wurden dafuer feiner als "
                        f"{_text(grob)} gesetzt.")
    else:
        abweichung = f"{'+' if -rest >= 0 else '-'}{geld(abs(rest))}"
        meldung = (f"Naechstmoeglicher Betrag im Faktorraster {_text(grob)}: "
                   f"Abweichung {abweichung} EUR.")
        if not nachjustieren and _ist_centgenau_moeglich(
            variabel, faktoren, grenzen, ziel - fest_summe
        ):
            meldung += " Mit feineren Faktoren waere der Betrag exakt zu treffen."
            warnungen.append(
                f"Im Raster {_text(grob)} bleibt ein Rest von {abweichung} EUR - "
                f"eine feinere Stufung schliesst ihn."
            )
        else:
            meldung += (" Feiner geht es nicht: die Einzelbetraege werden je Leistung "
                        "auf volle Cent gerundet, so dass nicht jede Summe darstellbar ist.")
            warnungen.append(
                f"Der Zielbetrag ist mit diesen Ziffern nicht centgenau darstellbar; "
                f"es bleibt eine Abweichung von {abweichung} EUR."
            )

    am_anschlag = sum(1 for f, g in zip(faktoren, grenzen) if f in (g[0], g[1]))
    if am_anschlag:
        warnungen.append(
            f"{am_anschlag} von {len(faktoren)} Faktoren liegen an der Grenze "
            f"({min_faktor} bzw. {max_faktor})."
        )
    return ergebnis(faktoren, meldung)


def _ist_centgenau_moeglich(
    positionen: list[Position],
    faktoren: list[Decimal],
    grenzen: list[tuple[Decimal, Decimal]],
    ziel_variabel: Decimal,
) -> bool:
    """Probelauf im feinsten Raster - liesse sich der Betrag damit genau treffen?"""
    _, rest = _feinabgleich(positionen, faktoren, grenzen, ziel_variabel, FAKTOR_RASTER)
    return rest == 0


def _feinabgleich(
    positionen: list[Position],
    faktoren: list[Decimal],
    grenzen: list[tuple[Decimal, Decimal]],
    ziel_variabel: Decimal,
    raster: Decimal,
) -> tuple[list[Decimal], Decimal]:
    """Schliesst den Rundungsrest, indem einzelne Faktoren gezielt nachgesetzt werden.

    Fuer jede Ziffer laesst sich der Faktor ausrechnen, mit dem sie den noch
    fehlenden Betrag genau aufnehmen wuerde.  Geprueft werden der so
    ermittelte Wert und seine unmittelbaren Nachbarn im Raster; uebernommen
    wird der Kandidat, der den Restbetrag am weitesten verkleinert.  Ein
    einzelner Rasterschritt aendert den gerundeten Betrag mitunter gar nicht -
    deshalb wird gerechnet statt schrittweise getastet.
    """
    faktoren = list(faktoren)
    betraege = [p.betrag_bei(f) for p, f in zip(positionen, faktoren)]
    rest = ziel_variabel - sum(betraege, Decimal("0.00"))

    for _ in range(200):
        if rest == 0:
            break
        bester = None  # (verbesserung, index, faktor, betrag, rest)
        for i, (p, (lo, hi)) in enumerate(zip(positionen, grenzen)):
            teiler = Decimal(p.punktzahl) * PUNKTWERT * Decimal(p.anzahl)
            if teiler == 0:
                continue
            # Faktor, mit dem diese Ziffer den fehlenden Betrag genau traefe.
            roh = (betraege[i] + rest) / teiler
            mitte = roh.quantize(raster, rounding=ROUND_HALF_UP)
            for versatz in range(-3, 4):
                kandidat = _klemme(mitte + versatz * raster, lo, hi)
                if kandidat == faktoren[i]:
                    continue
                neuer_betrag = p.betrag_bei(kandidat)
                neuer_rest = rest - (neuer_betrag - betraege[i])
                verbesserung = abs(rest) - abs(neuer_rest)
                if verbesserung > 0 and (bester is None or verbesserung > bester[0]):
                    bester = (verbesserung, i, kandidat, neuer_betrag, neuer_rest)
        if bester is None:
            break
        _, i, faktoren[i], betraege[i], rest = bester
    return faktoren, rest
