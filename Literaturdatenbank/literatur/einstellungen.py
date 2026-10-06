"""Einstellungen je Arbeitsplatz - vor allem: wo liegt der Datenordner?

Die Einstellung liegt lokal beim Benutzer, nicht im Datenordner selbst:
Jeder Arbeitsplatz kann die gemeinsame Ablage unter einem anderen Pfad
erreichen (z. B. Laufwerk L: unter Windows, /Volumes/Praxis auf dem Mac).

Die Umgebungsvariable LITERATUR_ORDNER hat Vorrang vor der Einstellung.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

DATEINAME = "einstellungen.json"


def einstellungsdatei() -> Path:
    if sys.platform.startswith("win"):
        basis = Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming")
    elif sys.platform == "darwin":
        basis = Path.home() / "Library" / "Application Support"
    else:
        basis = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return basis / "Literaturdatenbank" / DATEINAME


def lesen(datei: Path | None = None) -> dict:
    datei = datei or einstellungsdatei()
    try:
        daten = json.loads(datei.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return daten if isinstance(daten, dict) else {}


def schreiben(daten: dict, datei: Path | None = None) -> None:
    datei = datei or einstellungsdatei()
    datei.parent.mkdir(parents=True, exist_ok=True)
    temp = datei.with_suffix(".tmp")
    temp.write_text(json.dumps(daten, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temp.replace(datei)


def datenordner(datei: Path | None = None) -> Path | None:
    """Gewaehlter Datenordner oder None, solange noch keiner festgelegt ist."""
    aus_umgebung = os.environ.get("LITERATUR_ORDNER")
    if aus_umgebung:
        return Path(aus_umgebung).expanduser()
    wert = lesen(datei).get("datenordner")
    return Path(wert) if wert else None


def datenordner_merken(ordner: Path | str, datei: Path | None = None) -> None:
    daten = lesen(datei)
    daten["datenordner"] = str(Path(ordner))
    schreiben(daten, datei)
