# GOÄ-Abrechnungskalkulator

Kalkulation privatärztlicher Leistungspakete nach der Gebührenordnung für Ärzte
(GOÄ): Angebote aus mehreren GOÄ-Ziffern zusammenstellen, benennen, speichern,
wieder aufrufen und als Excel-Datei ausgeben.

Zu jeder Ziffer werden **der einfache, der 2,3-fache und der 3,5-fache Satz**
nebeneinander angezeigt. Der Abrechnungsfaktor lässt sich je Ziffer frei wählen –
oder man gibt den **gewünschten Gesamtpreis** vor und das Programm verteilt die
Faktoren automatisch so, dass die Summe erreicht wird. Kein Faktor wird dabei
kleiner als 1,0 oder größer als 3,5.

Das Programm braucht **nur Python 3.10 oder neuer** – keine weiteren Pakete,
auch nicht für den Excel-Export.

## Start

```bash
python3 kalkulator.py            # Fenster-Oberfläche
python3 kalkulator.py konsole    # menügeführt im Terminal
python3 kalkulator.py --help     # alle Befehle der Kommandozeile
```

Fehlt `tkinter` (unter Debian/Ubuntu: `sudo apt install python3-tk`), startet
automatisch die menügeführte Konsole.

## Bedienung der Oberfläche

| Bereich | Funktion |
|---|---|
| **links** | GOÄ-Katalog durchsuchen; Doppelklick übernimmt eine Ziffer in das Angebot |
| **rechts** | Positionen des Angebots mit 1,0-/2,3-/3,5-fachem Satz, Faktor und Betrag |
| **unten links** | Summen aller vier Spalten |
| **unten rechts** | Gesamtpreis vorgeben und Faktoren automatisch verteilen |

* **Faktor ändern:** Doppelklick auf die Zelle *Faktor* (oder *Anzahl*).
* **Position fixieren:** eine fixierte Ziffer behält ihren Faktor, wenn der
  Gesamtpreis neu verteilt wird – nützlich für Ziffern, die zwingend zum
  Regelsatz abgerechnet werden.
* **Farbige Zeilen:** orange = Faktor über dem Regelsatz, Begründung nach § 12
  GOÄ nötig; rot = Faktor über dem Höchstsatz der Steigerungsklasse.

## Gesamtpreis vorgeben

Der gewünschte Endpreis wird eingetragen, das Programm sucht die passenden
Faktoren. Drei Verteilungsarten stehen zur Wahl:

| Strategie | Wirkung |
|---|---|
| `proportional` (Vorgabe) | hebt oder senkt die vorhandenen Faktoren gleichmäßig |
| `einheitlich` | setzt für alle Ziffern denselben Faktor |
| `regelsatz` | verteilt als gemeinsames Vielfaches des jeweiligen Regelsatzes |

Gerechnet wird in **Zehntelschritten** (0,1), wie in der Abrechnung üblich; 0,05
und 0,01 sind wählbar. Stößt eine Ziffer an 1,0 oder 3,5, übernehmen die übrigen
den Rest. Liegt der Wunschpreis außerhalb des erreichbaren Bereichs, meldet das
Programm die tatsächliche Spanne und setzt die Faktoren an den Anschlag.

Bleibt im Zehntelraster ein Rest von wenigen Cent, weist das Programm ihn aus.
Die Option **„Betrag centgenau treffen"** (`--centgenau`) zieht dann einzelne
Faktoren feiner nach. Manche Summen sind allerdings prinzipiell nicht
darstellbar: Die GOÄ rundet den Betrag **je einzelner Leistung** auf volle Cent;
bei Anzahl 3 sind daher nur Vielfache von drei Cent erreichbar. In diesem Fall
nennt das Programm den nächstmöglichen Betrag und sagt, dass es feiner nicht geht.

## Kommandozeile

```bash
# Katalog durchsuchen
python3 kalkulator.py katalog beratung

# Angebot anlegen: Ziffer[xAnzahl][@Faktor]
python3 kalkulator.py neu "Check-up Basis" -z 1 -z 8 -z 650 -z 410x2 -z 3511@1,15

# Gesamtpreis vorgeben
python3 kalkulator.py ziel "Check-up Basis" 150,00
python3 kalkulator.py ziel "Check-up Basis" 150,00 --centgenau --strategie einheitlich
python3 kalkulator.py ziel "Check-up Basis" 150,00 --probe      # nur rechnen

# Verwalten und ausgeben
python3 kalkulator.py liste
python3 kalkulator.py zeige "Check-up Basis"
python3 kalkulator.py bearbeiten "Check-up Basis" -z 3 --faktor 1=2,5 --entferne 3511
python3 kalkulator.py excel "Check-up Basis"
python3 kalkulator.py excel --alle -o /pfad/Angebote.xlsx
python3 kalkulator.py loeschen "Check-up Basis"
```

## Ablage der Angebote

Jedes Angebot liegt als lesbare JSON-Datei in `~/GOÄ-Angebote` (anpassbar über
die Umgebungsvariable `GOAE_ANGEBOTE` oder `--verzeichnis`). Der Excel-Export
erzeugt je Angebot ein Tabellenblatt mit allen Sätzen, Faktoren, Beträgen und
Summen; werden mehrere Angebote exportiert, kommt ein Übersichtsblatt hinzu.

## Leistungskatalog

Der Katalog ist eine gewöhnliche CSV-Datei: `daten/goae_katalog.csv`
(Trennzeichen `;`, Zeilen mit `#` sind Kommentare).

```
nummer;bezeichnung;punktzahl;abschnitt;klasse;regelsatz;hoechstsatz
1;Beratung - auch mittels Fernsprecher;80;B;aerztlich;2.3;3.5
```

`klasse` steuert die Steigerungsklasse nach § 5 GOÄ und damit die Warnhinweise:

| Klasse | Regelsatz | Höchstsatz |
|---|---|---|
| `aerztlich` | 2,3 | 3,5 |
| `technisch` (Abschnitte A, E, O) | 1,8 | 2,5 |
| `labor` (Abschnitt M) | 1,15 | 1,3 |

Eigene Ziffern lassen sich direkt in die Datei eintragen oder importieren:

```bash
python3 kalkulator.py katalog-import meine_ziffern.csv
```

In der Oberfläche geht das über *Katalog → Ziffern aus CSV ergänzen*.

> **Wichtig:** Der mitgelieferte Katalog ist ein **Startdatensatz zum sofortigen
> Arbeiten und keine amtliche Quelle.** Punktzahlen und Legenden sind vor dem
> produktiven Einsatz gegen die amtliche GOÄ zu prüfen bzw. durch den eigenen,
> vollständigen Katalog zu ersetzen.

## Rechengrundlage

```
Betrag je Leistung = Punktzahl × Punktwert × Faktor     (auf volle Cent gerundet)
Punktwert = 0,0582873 € (5,82873 Cent, § 5 Abs. 1 GOÄ)
```

Kontrollwerte: Ziffer 1 (80 Punkte) → 4,66 € / 10,72 € / 16,32 €;
Ziffer 3 (150 Punkte) → 8,74 € / 20,11 € / 30,60 €;
Ziffer 8 (260 Punkte) → 15,15 € / 34,86 € / 53,04 €.

Ein Faktor über dem Regelsatz ist nach § 12 GOÄ schriftlich zu begründen; das
Programm weist darauf hin und nimmt die Begründung je Position auf. Sie
erscheint im Excel-Export.

## Aufbau

```
kalkulator.py                 Startprogramm
goae_kalkulator/
  modelle.py                  Leistung, Position, Angebot, Betragsrechnung
  katalog.py                  Katalog laden, durchsuchen, importieren
  zielbetrag.py               Faktorverteilung auf einen Gesamtpreis
  speicher.py                 Angebotsverzeichnis (JSON)
  excel.py                    .xlsx-Ausgabe ohne Fremdpakete
  gui.py                      Fenster-Oberfläche (tkinter)
  konsole.py                  menügeführte Bedienung
  cli.py                      Kommandozeile
daten/goae_katalog.csv        Leistungskatalog
tests/test_kalkulator.py      Testfälle
```

## Tests

```bash
python3 -m unittest discover -s tests -v
```

## Haftungsausschluss

Das Programm unterstützt die Kalkulation, ersetzt aber keine
abrechnungsrechtliche Prüfung. Die Zulässigkeit von Faktorwahl,
Steigerungsbegründung und Ziffernkombination (Zielleistungsprinzip,
Ausschlüsse, Analogziffern) ist eigenverantwortlich zu prüfen. Angaben ohne
Gewähr.
