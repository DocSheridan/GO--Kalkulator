"""Start per Doppelklick unter Windows - ohne Konsolenfenster.

Gleichbedeutend mit "python literatur.py"; setzt eine Python-Installation
von python.org voraus.
"""

import runpy
from pathlib import Path

runpy.run_path(str(Path(__file__).resolve().parent / "literatur.py"), run_name="__main__")
