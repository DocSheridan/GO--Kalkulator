# Literaturdatenbank

Desktop-Programm für die gemeinsame Literatur- und Dokumentenablage der Praxis.
Artikel werden in der App hochgeladen, in einen gemeinsamen Ordner auf dem
Server kopiert und katalogisiert. Läuft **vollständig offline** und braucht nur
**Python 3.10+ mit tkinter** – keine weiteren Pakete, keine Internetverbindung.

```bash
python3 literatur.py                    # Start; beim ersten Mal wird der Datenordner erfragt
python3 literatur.py --ordner L:\Literatur
```

## Funktionen

| | |
|---|---|
| **Artikel hinzufügen** | Datei wählen (PDF, Word, Excel, Bilder …); sie wird in den Datenordner kopiert. Titel wird aus dem Dateinamen vorgeschlagen. |
| **Kategorie** (Pflicht) | Genau eine je Artikel. Vorgabe: Qualitätsmanagement, Medizin, Formulare, Sonstiges. Ohne Kategorie lässt sich nichts ablegen. |
| **Bereiche** (frei) | Beliebig viele je Artikel. Vorgabe: Qualitätsmanagement, Formulare, Infektiologie, Metabolik. |
| **Schlagworte** | Freies Feld, durch Komma getrennt; vorhandene Schlagworte lassen sich aus einer Liste einfügen. |
| **Weitere Angaben** | Autoren, Jahr, Quelle, Notiz |
| **Nachträglich bearbeiten** | Alle Angaben – auch Kategorie, Bereiche und Schlagworte – rechts ändern und speichern (Strg+S). Datei durch neue Fassung ersetzen. |
| **Anzeigen** | Reiter **Alle**, **Neues** (in den letzten 31 Tagen abgelegt) oder eine Kategorie; dazu Filter nach Bereich und Volltextsuche. Spalten per Klick sortierbar, Doppelklick öffnet die Datei. |
| **Listen pflegen** | Menü *Listen*: Kategorien und Bereiche ergänzen, umbenennen, sortieren, entfernen. Wird eine benutzte Kategorie entfernt, fragt das Programm, wohin ihre Artikel wandern. |

## Datenordner und gemeinsame Nutzung

Im Menü **Datei › Datenordner wählen** wird der Ablageort frei festgelegt –
für die gemeinsame Nutzung ein Ordner auf dem Server (Netzlaufwerk). Jeder
Arbeitsplatz wählt denselben Ordner; der Pfad wird je Benutzer lokal gemerkt
und darf an jedem Arbeitsplatz anders lauten (z. B. `L:\Literatur` oder
`\\server\praxis\Literatur`). Die Umgebungsvariable `LITERATUR_ORDNER` hat
Vorrang.

```
<Datenordner>/
├── literatur.sqlite      Katalog (Kategorien, Bereiche, Schlagworte, Angaben)
└── Artikel/              abgelegte Dateien, z. B. 00012_Hygieneplan.pdf
```

Der Katalog ist eine SQLite-Datenbank (in Python enthalten, ohne Server).
Sie wird im netzlaufwerktauglichen Modus betrieben und nur für die Dauer
einer Aktion geöffnet; schreiben zwei Arbeitsplätze gleichzeitig, wartet der
zweite kurz. **F5** holt die Änderungen der anderen Arbeitsplätze.

**Sicherung:** Den gesamten Datenordner in die Serversicherung aufnehmen.

## Installation (danach ohne Internet)

**Windows:** Python-Installationsprogramm von python.org einmalig
herunterladen (enthält tkinter) und auf jedem Arbeitsplatz installieren; das
Installationsprogramm lässt sich per USB-Stick weitergeben. Danach diesen
Ordner (Repository) z. B. nach `C:\Programme\Literaturdatenbank` kopieren und
eine Verknüpfung auf `pythonw.exe literatur.py` anlegen (ohne Konsolenfenster).

**Alternativ als einzelne .exe** – einmalig auf einem Rechner mit Internet
bauen, dann an alle Arbeitsplätze verteilen:

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name Literaturdatenbank literatur.py
# Ergebnis: dist/Literaturdatenbank.exe
```

**macOS:** Python von python.org installieren. **Linux:** `sudo apt install python3-tk`.

## Tests

```bash
python3 -m unittest tests.test_literatur
```
