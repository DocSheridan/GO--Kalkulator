#!/usr/bin/env python3
"""Startprogramm der Literaturdatenbank.

    python3 literatur.py                       Fenster-Oberflaeche
    python3 literatur.py --ordner /pfad        mit diesem Datenordner starten

Ohne --ordner wird der zuletzt gewaehlte Datenordner verwendet; beim ersten
Start fragt das Programm danach.
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))



def main() -> int:
    parser = argparse.ArgumentParser(description="Literaturdatenbank der Praxis")
    parser.add_argument("--ordner", help="Datenordner (z. B. auf dem Server)")
    args = parser.parse_args()
    try:
        import tkinter  # noqa: F401
    except ImportError:
        print("Die Literaturdatenbank braucht tkinter (unter Debian/Ubuntu: "
              "sudo apt install python3-tk).", file=sys.stderr)
        return 1
    from literatur.gui import starte
    return starte(args.ordner)


if __name__ == "__main__":
    raise SystemExit(main())
