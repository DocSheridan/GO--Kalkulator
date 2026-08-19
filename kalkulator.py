#!/usr/bin/env python3
"""Startprogramm des GOAE-Abrechnungskalkulators.

Ohne Argumente oeffnet sich die Fenster-Oberflaeche; fehlt tkinter, wird
auf die menuegefuehrte Konsole ausgewichen.

    python3 kalkulator.py                      Fenster-Oberflaeche
    python3 kalkulator.py konsole              menuegefuehrt im Terminal
    python3 kalkulator.py --help               alle Befehle
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from goae_kalkulator.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
