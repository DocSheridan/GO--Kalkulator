"""Ablage der Literaturdatenbank in einem frei waehlbaren Datenordner.

Der Datenordner liegt typischerweise auf dem Praxisserver und wird von allen
Arbeitsplaetzen gemeinsam genutzt. Er enthaelt

    literatur.sqlite    Katalog: Artikel, Kategorien, Bereiche, Schlagworte
    Artikel/            die hochgeladenen Dateien (PDF, Word, Bilder ...)

SQLite laeuft ohne Server und ohne Internet. Auf Netzlaufwerken wird bewusst
das klassische Rollback-Journal verwendet - der WAL-Modus funktioniert auf
Freigaben nicht zuverlaessig. Jede Aktion oeffnet eine eigene, kurze
Verbindung, damit kein Arbeitsplatz die Datenbank dauerhaft sperrt.
"""

from __future__ import annotations

import re
import shutil
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

DATENBANK = "literatur.sqlite"
DATEIORDNER = "Artikel"
SCHEMA_VERSION = 1

STANDARD_KATEGORIEN = ("Qualitätsmanagement", "Medizin", "Formulare", "Sonstiges")
STANDARD_BEREICHE = ("Qualitätsmanagement", "Formulare", "Infektiologie", "Metabolik")

# Zeitraum des Reiters "Neues".
NEU_TAGE = 31

# Wie lange auf einen anderen Arbeitsplatz gewartet wird, der gerade schreibt.
WARTEZEIT_SEKUNDEN = 20

UMLAUTE = {
    "ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss",
    "Ä": "Ae", "Ö": "Oe", "Ü": "Ue",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS kategorien (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    position  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS bereiche (
    id        INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE COLLATE NOCASE,
    position  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS artikel (
    id            INTEGER PRIMARY KEY,
    titel         TEXT NOT NULL,
    autoren       TEXT NOT NULL DEFAULT '',
    jahr          TEXT NOT NULL DEFAULT '',
    quelle        TEXT NOT NULL DEFAULT '',
    schlagworte   TEXT NOT NULL DEFAULT '',
    notiz         TEXT NOT NULL DEFAULT '',
    datei         TEXT NOT NULL DEFAULT '',
    originalname  TEXT NOT NULL DEFAULT '',
    kategorie_id  INTEGER NOT NULL REFERENCES kategorien(id) ON DELETE RESTRICT,
    angelegt      TEXT NOT NULL,
    geaendert     TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS artikel_bereiche (
    artikel_id  INTEGER NOT NULL REFERENCES artikel(id) ON DELETE CASCADE,
    bereich_id  INTEGER NOT NULL REFERENCES bereiche(id) ON DELETE CASCADE,
    PRIMARY KEY (artikel_id, bereich_id)
);
CREATE INDEX IF NOT EXISTS artikel_kategorie ON artikel(kategorie_id);
CREATE INDEX IF NOT EXISTS artikel_bereiche_bereich ON artikel_bereiche(bereich_id);
"""

# Tabellen der beiden veraenderbaren Listen.
LISTEN = {"kategorien", "bereiche"}


class LiteraturFehler(Exception):
    """Fehler, der dem Anwender als Meldung angezeigt wird."""


@dataclass
class Eintrag:
    """Ein Element der Kategorien- oder Bereichsliste."""

    id: int
    name: str
    anzahl: int = 0          # zugeordnete Artikel


@dataclass
class Artikel:
    id: int
    titel: str
    kategorie_id: int
    kategorie: str = ""
    autoren: str = ""
    jahr: str = ""
    quelle: str = ""
    schlagworte: str = ""
    notiz: str = ""
    datei: str = ""          # relativ zum Datenordner, mit "/" getrennt
    originalname: str = ""
    angelegt: str = ""
    geaendert: str = ""
    bereich_ids: list[int] = field(default_factory=list)
    bereiche: list[str] = field(default_factory=list)

    @property
    def schlagwort_liste(self) -> list[str]:
        return zerlege_schlagworte(self.schlagworte)

    def suchtext(self) -> str:
        return " ".join((
            self.titel, self.autoren, self.jahr, self.quelle, self.schlagworte,
            self.notiz, self.originalname, self.kategorie, " ".join(self.bereiche),
        )).casefold()


def zerlege_schlagworte(text: str) -> list[str]:
    """Trennt an Komma, Semikolon und Zeilenumbruch; Doppelte fallen weg."""
    gesehen: set[str] = set()
    ergebnis = []
    for teil in re.split(r"[,;\n]+", text or ""):
        wort = " ".join(teil.split())
        if wort and wort.casefold() not in gesehen:
            gesehen.add(wort.casefold())
            ergebnis.append(wort)
    return ergebnis


def normiere_schlagworte(text: str) -> str:
    return ", ".join(zerlege_schlagworte(text))


def dateiname(text: str, laenge: int = 60) -> str:
    """Unbedenklicher Dateiname - auch fuer Windows-Freigaben."""
    text = "".join(UMLAUTE.get(z, z) for z in text.strip())
    text = re.sub(r"[^\w\s.-]", "", text, flags=re.ASCII)
    text = re.sub(r"[\s_]+", "_", text).strip("._-")
    return text[:laenge].rstrip("._-") or "artikel"


def sortierschluessel(text: str) -> str:
    """Deutsche Sortierung: Umlaute wie ae/oe/ue, ohne Gross-/Kleinschreibung."""
    return "".join(UMLAUTE.get(z, z) for z in text).casefold()


def jetzt() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Literaturdatenbank:
    """Zugriff auf Katalog und Dateien eines Datenordners."""

    def __init__(self, ordner: Path | str):
        self.ordner = Path(ordner).expanduser()
        self.datenbank = self.ordner / DATENBANK
        self.dateiordner = self.ordner / DATEIORDNER

    # -- Verbindung -------------------------------------------------------
    def einrichten(self) -> "Literaturdatenbank":
        """Legt Ordner und Tabellen an; neue Datenbanken erhalten die Vorgabelisten."""
        try:
            self.ordner.mkdir(parents=True, exist_ok=True)
            self.dateiordner.mkdir(exist_ok=True)
        except OSError as fehler:
            raise LiteraturFehler(
                f"Der Datenordner {self.ordner} ist nicht erreichbar: {fehler}") from fehler
        with self._verbindung() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > SCHEMA_VERSION:
                raise LiteraturFehler(
                    "Die Datenbank stammt aus einer neueren Programmversion. "
                    "Bitte das Programm auf diesem Arbeitsplatz aktualisieren.")
            db.executescript(SCHEMA)
            if version == 0:
                if not db.execute("SELECT 1 FROM kategorien").fetchone():
                    self._vorgaben(db, "kategorien", STANDARD_KATEGORIEN)
                if not db.execute("SELECT 1 FROM bereiche").fetchone():
                    self._vorgaben(db, "bereiche", STANDARD_BEREICHE)
                db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        return self

    @staticmethod
    def _vorgaben(db: sqlite3.Connection, tabelle: str, namen) -> None:
        db.executemany(f"INSERT INTO {tabelle} (name, position) VALUES (?, ?)",
                       [(n, i) for i, n in enumerate(namen)])

    @contextmanager
    def _verbindung(self):
        """Kurze Verbindung: am Ende bestaetigt (oder verworfen) und geschlossen."""
        try:
            db = sqlite3.connect(self.datenbank, timeout=WARTEZEIT_SEKUNDEN)
        except sqlite3.Error as fehler:
            raise LiteraturFehler(
                f"Die Datenbank {self.datenbank} kann nicht geoeffnet werden: {fehler}"
            ) from fehler
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys = ON")
            db.execute("PRAGMA journal_mode = DELETE")
            yield db
            db.commit()
        except sqlite3.OperationalError as fehler:
            db.rollback()
            if "locked" in str(fehler) or "busy" in str(fehler):
                raise LiteraturFehler(
                    "Die Datenbank wird gerade von einem anderen Arbeitsplatz "
                    "bearbeitet. Bitte in einem Moment erneut versuchen.") from fehler
            raise LiteraturFehler(f"Datenbankfehler: {fehler}") from fehler
        except sqlite3.DatabaseError as fehler:
            db.rollback()
            raise LiteraturFehler(f"Datenbankfehler: {fehler}") from fehler
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    # -- Kategorien und Bereiche -----------------------------------------
    def kategorien(self) -> list[Eintrag]:
        return self._liste("kategorien", "SELECT COUNT(*) FROM artikel WHERE kategorie_id = l.id")

    def bereiche(self) -> list[Eintrag]:
        return self._liste(
            "bereiche", "SELECT COUNT(*) FROM artikel_bereiche WHERE bereich_id = l.id")

    def _liste(self, tabelle: str, zaehlung: str) -> list[Eintrag]:
        with self._verbindung() as db:
            zeilen = db.execute(
                f"SELECT l.id, l.name, ({zaehlung}) AS anzahl FROM {tabelle} l "
                "ORDER BY l.position, l.name COLLATE NOCASE").fetchall()
        return [Eintrag(z["id"], z["name"], z["anzahl"]) for z in zeilen]

    @staticmethod
    def _pruefe_liste(tabelle: str) -> str:
        if tabelle not in LISTEN:
            raise ValueError(f"Unbekannte Liste {tabelle!r}")
        return tabelle

    @staticmethod
    def _pruefe_name(name: str) -> str:
        name = " ".join((name or "").split())
        if not name:
            raise LiteraturFehler("Der Name darf nicht leer sein.")
        return name

    def eintrag_hinzufuegen(self, tabelle: str, name: str) -> int:
        tabelle = self._pruefe_liste(tabelle)
        name = self._pruefe_name(name)
        with self._verbindung() as db:
            if db.execute(f"SELECT 1 FROM {tabelle} WHERE name = ?", (name,)).fetchone():
                raise LiteraturFehler(f"{name!r} steht bereits in der Liste.")
            position = db.execute(
                f"SELECT COALESCE(MAX(position), -1) + 1 FROM {tabelle}").fetchone()[0]
            return db.execute(f"INSERT INTO {tabelle} (name, position) VALUES (?, ?)",
                              (name, position)).lastrowid

    def eintrag_umbenennen(self, tabelle: str, eintrag_id: int, name: str) -> None:
        tabelle = self._pruefe_liste(tabelle)
        name = self._pruefe_name(name)
        with self._verbindung() as db:
            doppelt = db.execute(f"SELECT 1 FROM {tabelle} WHERE name = ? AND id <> ?",
                                 (name, eintrag_id)).fetchone()
            if doppelt:
                raise LiteraturFehler(f"{name!r} steht bereits in der Liste.")
            db.execute(f"UPDATE {tabelle} SET name = ? WHERE id = ?", (name, eintrag_id))

    def eintrag_verschieben(self, tabelle: str, eintrag_id: int, richtung: int) -> None:
        """Rueckt einen Eintrag um eine Stelle nach oben (-1) oder unten (+1)."""
        tabelle = self._pruefe_liste(tabelle)
        with self._verbindung() as db:
            ids = [z[0] for z in db.execute(
                f"SELECT id FROM {tabelle} ORDER BY position, name COLLATE NOCASE")]
            if eintrag_id not in ids:
                return
            alt = ids.index(eintrag_id)
            neu = max(0, min(len(ids) - 1, alt + richtung))
            ids.insert(neu, ids.pop(alt))
            db.executemany(f"UPDATE {tabelle} SET position = ? WHERE id = ?",
                           [(i, e) for i, e in enumerate(ids)])

    def kategorie_loeschen(self, kategorie_id: int, ersatz_id: int | None = None) -> None:
        """Entfernt eine Kategorie; ihre Artikel wandern in die Ersatzkategorie.

        Da jeder Artikel eine Kategorie haben muss, ist der Ersatz Pflicht,
        sobald der Kategorie noch Artikel zugeordnet sind.
        """
        with self._verbindung() as db:
            anzahl = db.execute("SELECT COUNT(*) FROM artikel WHERE kategorie_id = ?",
                                (kategorie_id,)).fetchone()[0]
            if anzahl:
                if ersatz_id is None or ersatz_id == kategorie_id:
                    raise LiteraturFehler(
                        f"Der Kategorie sind noch {anzahl} Artikel zugeordnet. "
                        "Bitte eine andere Kategorie fuer diese Artikel waehlen.")
                if not db.execute("SELECT 1 FROM kategorien WHERE id = ?",
                                  (ersatz_id,)).fetchone():
                    raise LiteraturFehler("Die gewaehlte Ersatzkategorie gibt es nicht mehr.")
                db.execute("UPDATE artikel SET kategorie_id = ?, geaendert = ? "
                           "WHERE kategorie_id = ?", (ersatz_id, jetzt(), kategorie_id))
            elif db.execute("SELECT COUNT(*) FROM kategorien").fetchone()[0] <= 1:
                raise LiteraturFehler("Die letzte Kategorie kann nicht geloescht werden.")
            db.execute("DELETE FROM kategorien WHERE id = ?", (kategorie_id,))

    def bereich_loeschen(self, bereich_id: int) -> None:
        """Entfernt einen Bereich; die Artikel selbst bleiben erhalten."""
        with self._verbindung() as db:
            db.execute("DELETE FROM bereiche WHERE id = ?", (bereich_id,))

    # -- Artikel ----------------------------------------------------------
    def artikel_anlegen(self, quelldatei: Path | str | None, titel: str, kategorie_id: int,
                        bereich_ids=(), schlagworte: str = "", autoren: str = "",
                        jahr: str = "", quelle: str = "", notiz: str = "") -> Artikel:
        """Katalogisiert einen neuen Artikel und kopiert seine Datei in den Datenordner."""
        titel = self._pruefe_titel(titel)
        quell = Path(quelldatei) if quelldatei else None
        if quell is not None and not quell.is_file():
            raise LiteraturFehler(f"Die Datei {quell} wurde nicht gefunden.")
        zeit = jetzt()
        kopie: Path | None = None
        try:
            with self._verbindung() as db:
                self._pruefe_kategorie(db, kategorie_id)
                artikel_id = db.execute(
                    "INSERT INTO artikel (titel, autoren, jahr, quelle, schlagworte, notiz,"
                    " originalname, kategorie_id, angelegt, geaendert)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (titel, autoren.strip(), jahr.strip(), quelle.strip(),
                     normiere_schlagworte(schlagworte), notiz.strip(),
                     quell.name if quell else "", kategorie_id, zeit, zeit)).lastrowid
                self._setze_bereiche(db, artikel_id, bereich_ids)
                if quell is not None:
                    kopie = self._kopiere(quell, artikel_id, titel)
                    db.execute("UPDATE artikel SET datei = ? WHERE id = ?",
                               (self._relativ(kopie), artikel_id))
        except BaseException:
            # Ohne Katalogeintrag soll auch keine verwaiste Kopie zurueckbleiben.
            if kopie is not None:
                kopie.unlink(missing_ok=True)
            raise
        return self.artikel(artikel_id)

    def artikel_aendern(self, artikel_id: int, titel: str, kategorie_id: int,
                        bereich_ids=(), schlagworte: str = "", autoren: str = "",
                        jahr: str = "", quelle: str = "", notiz: str = "") -> Artikel:
        titel = self._pruefe_titel(titel)
        with self._verbindung() as db:
            self._pruefe_kategorie(db, kategorie_id)
            geaendert = db.execute(
                "UPDATE artikel SET titel = ?, autoren = ?, jahr = ?, quelle = ?,"
                " schlagworte = ?, notiz = ?, kategorie_id = ?, geaendert = ? WHERE id = ?",
                (titel, autoren.strip(), jahr.strip(), quelle.strip(),
                 normiere_schlagworte(schlagworte), notiz.strip(), kategorie_id,
                 jetzt(), artikel_id)).rowcount
            if not geaendert:
                raise LiteraturFehler(
                    "Der Artikel wurde inzwischen von einem anderen Arbeitsplatz geloescht.")
            self._setze_bereiche(db, artikel_id, bereich_ids)
        return self.artikel(artikel_id)

    def schlagworte_setzen(self, artikel_id: int, schlagworte: str) -> None:
        with self._verbindung() as db:
            db.execute("UPDATE artikel SET schlagworte = ?, geaendert = ? WHERE id = ?",
                       (normiere_schlagworte(schlagworte), jetzt(), artikel_id))

    def datei_ersetzen(self, artikel_id: int, quelldatei: Path | str) -> Artikel:
        """Hinterlegt eine neue Fassung der Datei; die alte wird entfernt."""
        quell = Path(quelldatei)
        if not quell.is_file():
            raise LiteraturFehler(f"Die Datei {quell} wurde nicht gefunden.")
        alt = self.artikel(artikel_id)
        kopie = self._kopiere(quell, artikel_id, alt.titel)
        try:
            with self._verbindung() as db:
                db.execute("UPDATE artikel SET datei = ?, originalname = ?, geaendert = ?"
                           " WHERE id = ?", (self._relativ(kopie), quell.name, jetzt(),
                                             artikel_id))
        except BaseException:
            kopie.unlink(missing_ok=True)
            raise
        if alt.datei and self.pfad(alt) != kopie:
            self.pfad(alt).unlink(missing_ok=True)
        return self.artikel(artikel_id)

    def artikel_loeschen(self, artikel_id: int, datei_loeschen: bool = True) -> None:
        artikel = self.artikel(artikel_id)
        with self._verbindung() as db:
            db.execute("DELETE FROM artikel WHERE id = ?", (artikel_id,))
        if datei_loeschen and artikel.datei:
            try:
                self.pfad(artikel).unlink(missing_ok=True)
            except OSError:
                pass  # z. B. am anderen Arbeitsplatz geoeffnet; Eintrag ist trotzdem weg

    def artikel(self, artikel_id: int) -> Artikel:
        treffer = self._lade("WHERE a.id = ?", (artikel_id,))
        if not treffer:
            raise LiteraturFehler("Der Artikel ist nicht (mehr) vorhanden.")
        return treffer[0]

    def suche(self, text: str = "", kategorie_id: int | None = None,
              bereich_id: int | None = None, neu_seit_tagen: int | None = None,
              ) -> list[Artikel]:
        """Alle Artikel, wahlweise nach Kategorie, Bereich und Suchbegriffen gefiltert.

        neu_seit_tagen beschraenkt auf Artikel, die in diesem Zeitraum
        abgelegt wurden (Reiter "Neues").

        Mehrere Suchwoerter muessen alle vorkommen - in Titel, Autoren,
        Schlagworten, Notiz, Quelle, Dateiname, Kategorie oder Bereich.
        """
        bedingungen, werte = [], []
        if kategorie_id is not None:
            bedingungen.append("a.kategorie_id = ?")
            werte.append(kategorie_id)
        if bereich_id is not None:
            bedingungen.append(
                "EXISTS (SELECT 1 FROM artikel_bereiche x"
                " WHERE x.artikel_id = a.id AND x.bereich_id = ?)")
            werte.append(bereich_id)
        if neu_seit_tagen is not None:
            grenze = datetime.now() - timedelta(days=neu_seit_tagen)
            bedingungen.append("a.angelegt >= ?")
            werte.append(grenze.isoformat(timespec="seconds"))
        wo = ("WHERE " + " AND ".join(bedingungen)) if bedingungen else ""
        artikel = self._lade(wo, werte)
        woerter = text.casefold().split()
        if woerter:
            artikel = [a for a in artikel if all(w in a.suchtext() for w in woerter)]
        return artikel

    def schlagworte(self) -> list[str]:
        """Alle vergebenen Schlagworte, alphabetisch - als Vorschlagsliste."""
        with self._verbindung() as db:
            texte = [z[0] for z in db.execute("SELECT schlagworte FROM artikel")]
        return sorted(set(zerlege_schlagworte(", ".join(texte))), key=sortierschluessel)

    def pfad(self, artikel: Artikel) -> Path:
        return self.ordner.joinpath(*artikel.datei.split("/"))

    # -- intern -----------------------------------------------------------
    def _lade(self, wo: str, werte) -> list[Artikel]:
        with self._verbindung() as db:
            zeilen = db.execute(
                "SELECT a.*, k.name AS kategorie FROM artikel a"
                f" JOIN kategorien k ON k.id = a.kategorie_id {wo}"
                " ORDER BY a.angelegt DESC, a.id DESC", list(werte)).fetchall()
            zuordnung: dict[int, list[tuple[int, str]]] = {}
            for z in db.execute(
                    "SELECT x.artikel_id, b.id, b.name FROM artikel_bereiche x"
                    " JOIN bereiche b ON b.id = x.bereich_id"
                    " ORDER BY b.position, b.name COLLATE NOCASE"):
                zuordnung.setdefault(z[0], []).append((z[1], z[2]))
        ergebnis = []
        for z in zeilen:
            bereiche = zuordnung.get(z["id"], [])
            ergebnis.append(Artikel(
                id=z["id"], titel=z["titel"], kategorie_id=z["kategorie_id"],
                kategorie=z["kategorie"], autoren=z["autoren"], jahr=z["jahr"],
                quelle=z["quelle"], schlagworte=z["schlagworte"], notiz=z["notiz"],
                datei=z["datei"], originalname=z["originalname"],
                angelegt=z["angelegt"], geaendert=z["geaendert"],
                bereich_ids=[b[0] for b in bereiche], bereiche=[b[1] for b in bereiche]))
        return ergebnis

    @staticmethod
    def _pruefe_titel(titel: str) -> str:
        titel = " ".join((titel or "").split())
        if not titel:
            raise LiteraturFehler("Bitte einen Titel angeben.")
        return titel

    @staticmethod
    def _pruefe_kategorie(db: sqlite3.Connection, kategorie_id) -> None:
        if kategorie_id is None:
            raise LiteraturFehler("Bitte eine Kategorie zuordnen - das ist Pflicht.")
        if not db.execute("SELECT 1 FROM kategorien WHERE id = ?", (kategorie_id,)).fetchone():
            raise LiteraturFehler("Die gewaehlte Kategorie gibt es nicht mehr.")

    @staticmethod
    def _setze_bereiche(db: sqlite3.Connection, artikel_id: int, bereich_ids) -> None:
        db.execute("DELETE FROM artikel_bereiche WHERE artikel_id = ?", (artikel_id,))
        # Inzwischen geloeschte Bereiche stillschweigend uebergehen.
        db.executemany(
            "INSERT OR IGNORE INTO artikel_bereiche (artikel_id, bereich_id)"
            " SELECT ?, id FROM bereiche WHERE id = ?",
            [(artikel_id, b) for b in dict.fromkeys(bereich_ids)])

    def _kopiere(self, quell: Path, artikel_id: int, titel: str) -> Path:
        """Kopiert die Datei unter einem eindeutigen Namen in den Dateiordner."""
        endung = quell.suffix.lower()
        stamm = f"{artikel_id:05d}_{dateiname(titel)}"
        ziel = self.dateiordner / f"{stamm}{endung}"
        zaehler = 2
        while ziel.exists():
            ziel = self.dateiordner / f"{stamm}-{zaehler}{endung}"
            zaehler += 1
        try:
            self.dateiordner.mkdir(parents=True, exist_ok=True)
            shutil.copy2(quell, ziel)
        except OSError as fehler:
            ziel.unlink(missing_ok=True)
            raise LiteraturFehler(f"Die Datei konnte nicht abgelegt werden: {fehler}") from fehler
        return ziel

    def _relativ(self, pfad: Path) -> str:
        return pfad.relative_to(self.ordner).as_posix()
