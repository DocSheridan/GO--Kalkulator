"""Angaben zum Programm - Urheberrecht und Impressum.

Dieselben Angaben stehen fuer die Smartphone-App in app/js/app.js; dass sie
uebereinstimmen, pruefen die Testfaelle.
"""

# Der Vermerk wird zweiteilig gefuehrt, weil der Zusatz kleiner gesetzt wird -
# in der App, auf dem Ausdruck und in der Excel-Tabelle. Wo keine Schriftgrade
# moeglich sind, dient COPYRIGHT als schlichte Zusammensetzung.
COPYRIGHT_HAUPT = "© 2026 Dr. med. Raimar Lorrmann D. O."
COPYRIGHT_ZUSATZ = "(DAAO)"
COPYRIGHT = f"{COPYRIGHT_HAUPT} {COPYRIGHT_ZUSATZ}"

# Ein Impressum nach § 5 DDG nennt ladungsfaehige Anschrift und Kontakt, fuer
# Aerzte zusaetzlich Berufsbezeichnung, zustaendige Kammer und Aufsichtsbehoerde.
IMPRESSUM = {
    "verantwortlich": "Raimar Lorrmann",
    "praxis": "Die Hausärzte im Sheridan",
    "anschrift": "Max-Josef-Metzger-Straße 3a, 86157 Augsburg",
    "kontakt": "praxis@hausaerzte-sheridan.de",
    "berufsbezeichnung": "Arzt (verliehen in der Bundesrepublik Deutschland)",
    "kammer": "Bayerische Landesärztekammer",
    "aufsicht": "Bayerische Landesärztekammer",
}
