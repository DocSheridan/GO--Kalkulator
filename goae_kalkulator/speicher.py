"""Verzeichnis der gespeicherten Angebote (eine JSON-Datei je Angebot)."""

from __future__ import annotations

import json
import os
import re
from decimal import Decimal
from pathlib import Path

from .modelle import Angebot

UMLAUTE = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
}


class SpeicherFehler(Exception):
    """Fehler beim Lesen oder Schreiben eines Angebots."""


def standard_verzeichnis() -> Path:
    """Ablageort: Umgebungsvariable GOAE_ANGEBOTE oder ~/GOAE-Angebote."""
    aus_umgebung = os.environ.get("GOAE_ANGEBOTE")
    if aus_umgebung:
        return Path(aus_umgebung).expanduser()
    return Path.home() / "GOAE-Angebote"


def dateiname(name: str) -> str:
    """Erzeugt aus einem Angebotsnamen einen unbedenklichen Dateinamen."""
    text = "".join(UMLAUTE.get(z, z) for z in name.strip())
    text = re.sub(r"[^\w\s.-]", "", text, flags=re.UNICODE)
    text = re.sub(r"[\s_]+", "_", text).strip("._-")
    return text or "angebot"


class Angebotsverzeichnis:
    """Ablage fuer benannte Angebote im Dateisystem."""

    def __init__(self, pfad: Path | str | None = None):
        self.pfad = Path(pfad).expanduser() if pfad else standard_verzeichnis()

    def sicherstellen(self) -> Path:
        self.pfad.mkdir(parents=True, exist_ok=True)
        return self.pfad

    # -- Uebersicht -------------------------------------------------------
    def dateien(self) -> list[Path]:
        if not self.pfad.exists():
            return []
        return sorted(self.pfad.glob("*.json"))

    def liste(self) -> list[dict]:
        """Kurzuebersicht aller gespeicherten Angebote."""
        eintraege = []
        for datei in self.dateien():
            try:
                angebot = self._lesen(datei)
            except SpeicherFehler:
                continue
            eintraege.append(
                {
                    "name": angebot.name,
                    "datei": datei,
                    "geaendert": angebot.geaendert,
                    "positionen": len(angebot.positionen),
                    "summe": angebot.summe,
                    "patient": angebot.patient,
                    "beschreibung": angebot.beschreibung,
                }
            )
        eintraege.sort(key=lambda e: e["geaendert"], reverse=True)
        return eintraege

    def namen(self) -> list[str]:
        return [e["name"] for e in self.liste()]

    # -- Lesen / Schreiben ------------------------------------------------
    def _lesen(self, datei: Path) -> Angebot:
        try:
            daten = json.loads(datei.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as fehler:
            raise SpeicherFehler(f"{datei.name} kann nicht gelesen werden: {fehler}") from fehler
        try:
            return Angebot.from_dict(daten)
        except (KeyError, TypeError, ValueError) as fehler:
            raise SpeicherFehler(f"{datei.name} hat ein unerwartetes Format: {fehler}") from fehler

    def finde_datei(self, name: str) -> Path | None:
        """Sucht ein Angebot nach Name (bevorzugt) oder Dateiname."""
        gesucht = name.strip().lower()
        kandidat_stem = dateiname(name).lower()
        nach_stem = None
        for datei in self.dateien():
            if datei.stem.lower() == kandidat_stem:
                nach_stem = datei
            try:
                if self._lesen(datei).name.strip().lower() == gesucht:
                    return datei
            except SpeicherFehler:
                continue
        return nach_stem

    def existiert(self, name: str) -> bool:
        return self.finde_datei(name) is not None

    def laden(self, name: str) -> Angebot:
        datei = self.finde_datei(name)
        if datei is None:
            raise SpeicherFehler(f"Kein Angebot mit dem Namen {name!r} gefunden.")
        return self._lesen(datei)

    def laden_aus(self, datei: Path | str) -> Angebot:
        return self._lesen(Path(datei))

    def speichern(self, angebot: Angebot) -> Path:
        if not angebot.name.strip():
            raise SpeicherFehler("Das Angebot benoetigt einen Namen.")
        self.sicherstellen()
        angebot.beruehren()
        ziel = self.finde_datei(angebot.name) or self._freier_pfad(angebot.name)
        inhalt = json.dumps(angebot.to_dict(), ensure_ascii=False, indent=2)
        # Atomar schreiben, damit ein Absturz keine halbe Datei hinterlaesst.
        temp = ziel.with_suffix(".json.tmp")
        temp.write_text(inhalt + "\n", encoding="utf-8")
        temp.replace(ziel)
        return ziel

    def _freier_pfad(self, name: str) -> Path:
        stamm = dateiname(name)
        ziel = self.pfad / f"{stamm}.json"
        zaehler = 2
        while ziel.exists():
            ziel = self.pfad / f"{stamm}-{zaehler}.json"
            zaehler += 1
        return ziel

    def loeschen(self, name: str) -> Path:
        datei = self.finde_datei(name)
        if datei is None:
            raise SpeicherFehler(f"Kein Angebot mit dem Namen {name!r} gefunden.")
        datei.unlink()
        return datei

    def kopieren(self, name: str, neuer_name: str) -> Angebot:
        angebot = self.laden(name)
        angebot.name = neuer_name
        angebot.erstellt = angebot.geaendert
        self.speichern(angebot)
        return angebot
