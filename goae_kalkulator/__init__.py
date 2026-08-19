"""GOAE-Abrechnungskalkulator.

Kalkulation privataerztlicher Leistungspakete nach der Gebuehrenordnung
fuer Aerzte (GOAE): Angebote aus mehreren GOAE-Ziffern zusammenstellen,
Faktoren frei waehlen oder automatisch auf einen Zielbetrag hin verteilen,
Angebote speichern, wieder aufrufen und nach Excel exportieren.
"""

from .modelle import Leistung, Position, Angebot, PUNKTWERT
from .katalog import Katalog
from .speicher import Angebotsverzeichnis
from .zielbetrag import optimiere_faktoren, Optimierungsergebnis

__all__ = [
    "Leistung",
    "Position",
    "Angebot",
    "PUNKTWERT",
    "Katalog",
    "Angebotsverzeichnis",
    "optimiere_faktoren",
    "Optimierungsergebnis",
]

__version__ = "1.0.0"
