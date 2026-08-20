# GOÄ-Kalkulator als Smartphone-App

Dieselbe Kalkulation wie das Schreibtischprogramm, für iPhone und Android.
Eine Codebasis, kein Store-Konto nötig, läuft offline.

Die App ist eine **installierbare Web-App (PWA)**: Sie wird einmal im Browser
geöffnet und auf den Startbildschirm gelegt. Danach startet sie wie jede andere
App – eigenes Symbol, eigenes Fenster ohne Browserleiste, kein Netz nötig.

## Auf das Telefon bringen

Die Dateien müssen über **https** erreichbar sein (oder über `localhost`);
andernfalls verweigern iOS und Android den Offlinebetrieb.

### Über GitHub Pages (eingerichtet)

Die Veröffentlichung läuft automatisch: `.github/workflows/pages.yml` führt bei
jeder Änderung an `app/` erst die Tests aus und stellt die App anschließend
bereit unter

**https://docsheridan.github.io/GO--Kalkulator/**

Der Umweg über einen Arbeitsablauf ist nötig, weil die Branch-Einstellung von
GitHub Pages nur `/` oder `/docs` als Quellordner anbietet – `app/` lässt sich
so nicht veröffentlichen, und die Dateien sollten nicht doppelt im Repository
liegen.

Einmalig war dafür unter *Settings → Pages → Build and deployment* als **Source**
„GitHub Actions" einzustellen. Diesen Schritt kann der Arbeitsablauf nicht selbst
erledigen: Sein Token darf veröffentlichen, aber die Pages-Seite nicht erstmalig
anlegen. Wird das Repository einmal geforkt oder neu aufgesetzt, ist der Schritt
zu wiederholen.

Wird der Branch später umbenannt oder nach `main` überführt, ist der
Branch-Name oben in `pages.yml` anzupassen.

### Auf eigenem Webspace

Den Ordner `app/` vollständig hochladen. Es wird nichts serverseitig
ausgeführt – reine statische Dateien.

### Zum Ausprobieren am Rechner

```bash
cd app && python3 -m http.server 8099
```

Dann `http://localhost:8099` im Browser öffnen.

### Installieren

| Gerät | Weg |
|---|---|
| **iPhone / iPad** | Seite in **Safari** öffnen (nicht Chrome), *Teilen* → *Zum Home-Bildschirm* |
| **Android** | Seite in Chrome öffnen, Menü → *App installieren* bzw. der eingeblendete Hinweis |

## Bedienung

Drei Bereiche über die Leiste am unteren Rand:

- **Katalog** – Ziffer oder Leistung suchen, antippen übernimmt sie ins
  Angebot. Anzahl und Startfaktor lassen sich vorher einstellen.
- **Angebot** – je Ziffer stehen der einfache, der 2,3- und der 3,5-fache Satz
  als antippbare Felder; das Feld dazwischen nimmt jeden Faktor zwischen 1,0
  und 3,5. Das Schloss hält eine Ziffer fest, wenn ein Gesamtpreis verteilt
  wird. Darunter: Gesamtpreis vorgeben, speichern, als Excel-Tabelle teilen.
- **Gespeichert** – abgelegte Angebote öffnen, kopieren, löschen.

Die Leiste über den Reitern zeigt durchgehend die vier Summen.

Zeilen mit einem Faktor über dem Regelsatz sind orange markiert (Begründung
nach § 12 GOÄ nötig), über dem Höchstsatz der Steigerungsklasse rot.

## Excel weitergeben

*Excel* erzeugt die `.xlsx`-Datei auf dem Gerät und öffnet das
Teilen-Menü – von dort in Mail, Dateien, Drive oder direkt in eine
Tabellen-App. Fehlt die Teilen-Funktion, wird die Datei heruntergeladen.

## Erscheinungsbild

Symbol und Oberfläche verwenden die Farben der Praxis, ausgelesen aus
`werkzeuge/praxislogo.png`:

| Farbe | Verwendung |
|---|---|
| `#6C7569` Grün der Logofläche | Kopfzeile, Summen, Hauptknöpfe, Ziffernnummern |
| `#B7C4AF` Hellgrün des Strangs | Balken im Symbol, Markenton im dunklen Erscheinungsbild |
| `#585857` Grau der Wortmarke | Nebentexte |

Die App folgt der Einstellung des Geräts und erscheint hell oder dunkel. Alle
Farbpaare erreichen die Kontrastwerte für Fließtext (mindestens 4,5:1); kleine
Schrift auf Eingabeflächen nutzt deshalb den kräftigeren Ton `#4D5649`.

Das Symbol wird erzeugt mit:

```bash
python3 werkzeuge/symbole_erzeugen.py
```

Ändern sich die Praxisfarben, genügt es, `werkzeuge/praxislogo.png` zu
ersetzen, die Farbwerte im Kopf des Skripts sowie die Variablen in `app.css`
anzupassen und das Skript erneut laufen zu lassen. Nach jeder Symboländerung
ist die Version in `sw.js` zu erhöhen – sonst zeigen bereits installierte
Geräte weiter das alte Symbol aus ihrem Zwischenspeicher.

## Wo die Daten liegen

Angebote und Patientenangaben werden **ausschließlich auf dem Gerät**
gespeichert (`localStorage` des Browsers). Es gibt keine Serververbindung,
keine Anmeldung, keine Auswertung.

Zwei Dinge, die daraus folgen:

- Die Ablage ist **nicht verschlüsselt** und nicht durch ein eigenes Passwort
  geschützt – sie hängt am Gerätecode. Für Patientenangaben genügen deshalb
  Kürzel oder eine Fallnummer; ein voller Name muss nicht hinein.
- Wer die Website-Daten des Browsers löscht oder die App vom Startbildschirm
  entfernt, verliert die gespeicherten Angebote. Wichtige Angebote vorher als
  Excel-Datei sichern.

## Rechnet die App wie das Programm?

Ja, und das wird geprüft. Beide Fassungen rechnen ohne Fließkomma – Beträge in
ganzen Cent, Faktoren in Tausendsteln – und suchen den Skalierungsparameter
ganzzahlig. `werkzeuge/pruefvektoren.py` rechnet 200 zufällige, reproduzierbare
Fälle mit dem Python-Programm; `app/tests/vergleich.test.mjs` spielt sie in
JavaScript nach und verlangt Übereinstimmung **in jedem einzelnen Faktor**,
nicht nur in der Summe.

## Tests

```bash
cd app && node --test        # 18 Testfälle, keine Installation nötig
```

Nach Änderungen am Katalog:

```bash
python3 werkzeuge/katalog_fuer_app.py   # app/daten/goae_katalog.json neu erzeugen
python3 werkzeuge/pruefvektoren.py      # Prüfvektoren neu rechnen
```

## Aufbau

```
app/
  index.html                 Aufbau der Oberfläche
  app.css                    Gestaltung, hell und dunkel
  manifest.webmanifest       Angaben für die Installation
  sw.js                      Offlinebetrieb
  js/modelle.js              Betragsrechnung, Position, Angebot
  js/katalog.js              Katalog laden und durchsuchen
  js/zielbetrag.js           Faktorverteilung auf einen Gesamtpreis
  js/speicher.js             Ablage auf dem Gerät
  js/xlsx.js                 Excel-Ausgabe ohne Fremdbibliothek
  js/app.js                  Bedienung
  daten/goae_katalog.json    2 711 GOÄ-Ziffern (aus daten/goae_katalog.csv)
  symbole/                   App-Symbole
  tests/                     Testfälle und Prüfvektoren
```

Kein Bauschritt, kein npm, keine Fremdbibliothek. Die `package.json` steht nur
da, damit Node beim Testen die ES-Module lädt.

## Später in den App Store?

Falls die App einmal über App Store und Play Store verteilt werden soll, lässt
sich dieser Ordner mit **Capacitor** ohne Umschreiben in native Projekte
verpacken:

```bash
npm install @capacitor/core @capacitor/cli
npx cap init "GOÄ-Kalkulator" de.praxis.goaekalkulator --web-dir=app
npx cap add ios && npx cap add android
```

Dafür braucht es dann einen Mac mit Xcode, ein Apple-Entwicklerkonto
(kostenpflichtig) und ein Google-Play-Konto. Für den Eigengebrauch in der
Praxis ist der Weg über den Startbildschirm der deutlich kürzere.
