"""Farbschema der Praxis.

Die drei Grundfarben sind dem Praxislogo entnommen (werkzeuge/praxislogo.png)
und dort die flaechenmaessig groessten deckenden Farben. Die uebrigen Werte
sind daraus abgeleitet.

Dieselbe Palette gibt es fuer die Smartphone-App in app/js/farben.js und als
Variablen in app/css. Dass die drei Fassungen uebereinstimmen, prueft
tests/test_kalkulator.py - sonst faellt ein Auseinanderlaufen erst auf, wenn
Ausdruck und Bildschirm nebeneinander liegen.
"""

# -- aus dem Logo ---------------------------------------------------------
GRUEN = "#6C7569"          # Gruen der Logoflaeche
HELLGRUEN = "#B7C4AF"      # Hellgruen des Strangs
GRAU = "#585857"           # Grau der Wortmarke
WEISS = "#FFFFFF"

# -- abgeleitet -----------------------------------------------------------
GRUEN_STARK = "#4D5649"    # dunkler; fuer kleine Schrift auf hellen Flaechen
GRUEN_TON = "#DCE4D7"      # heller Grundton, z.B. Summenzeile der Tabelle
TEXT = "#23261F"

# -- Zustaende ------------------------------------------------------------
WARNUNG = "#9A5800"        # Faktor ueber dem Regelsatz
FEHLER = "#A3201A"         # Faktor ueber dem Hoechstsatz
GUT = "#4A6B45"


def excel(farbe: str) -> str:
    """Wandelt #RRGGBB in die von Excel erwartete Schreibweise FFRRGGBB."""
    return "FF" + farbe.lstrip("#").upper()
