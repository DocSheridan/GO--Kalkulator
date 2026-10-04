"""Testfaelle der Literaturdatenbank."""

import os
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from literatur import einstellungen
from literatur.datenbank import (
    DATENBANK, NEU_TAGE, SCHEMA, STANDARD_BEREICHE, STANDARD_KATEGORIEN, STANDARD_RUBRIKEN,
    LiteraturFehler,
    Literaturdatenbank, dateiname, normiere_schlagworte,
)


class Grundlage(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp.cleanup)
        self.wurzel = Path(self._temp.name)
        self.db = Literaturdatenbank(self.wurzel / "Server" / "Literatur").einrichten()
        self.quelle = self.wurzel / "Hygieneplan 2026.pdf"
        self.quelle.write_bytes(b"%PDF-1.4 Testinhalt")

    def kategorie(self, name):
        return next(k.id for k in self.db.kategorien() if k.name == name)

    def bereich(self, name):
        return next(b.id for b in self.db.bereiche() if b.name == name)

    def anlegen(self, titel="Hygieneplan", kategorie="Qualitätsmanagement", **weitere):
        return self.db.artikel_anlegen(self.quelle, titel, self.kategorie(kategorie),
                                       **weitere)


class Einrichtung(Grundlage):
    def test_neue_datenbank_hat_vorgabelisten(self):
        self.assertEqual([k.name for k in self.db.kategorien()], list(STANDARD_KATEGORIEN))
        self.assertEqual([b.name for b in self.db.bereiche()], list(STANDARD_BEREICHE))
        self.assertTrue((self.db.ordner / DATENBANK).exists())
        self.assertTrue(self.db.dateiordner.is_dir())

    def test_erneutes_einrichten_stellt_geloeschte_vorgaben_nicht_wieder_her(self):
        self.db.bereich_loeschen(self.bereich("Metabolik"))
        Literaturdatenbank(self.db.ordner).einrichten()
        self.assertNotIn("Metabolik", [b.name for b in self.db.bereiche()])

    def test_kein_wal_modus_wegen_netzlaufwerk(self):
        with sqlite3.connect(self.db.datenbank) as roh:
            self.assertEqual(roh.execute("PRAGMA journal_mode").fetchone()[0], "delete")

    def test_neuere_schemaversion_wird_abgelehnt(self):
        with sqlite3.connect(self.db.datenbank) as roh:
            roh.execute("PRAGMA user_version = 99")
        with self.assertRaises(LiteraturFehler):
            Literaturdatenbank(self.db.ordner).einrichten()


class Ablage(Grundlage):
    def test_datei_wird_kopiert_und_katalogisiert(self):
        a = self.anlegen(bereich_ids=[self.bereich("Infektiologie")],
                         schlagworte="Hygiene; Desinfektion, hygiene", autoren="RKI",
                         jahr="2026")
        self.assertEqual(a.kategorie, "Qualitätsmanagement")
        self.assertEqual(a.bereiche, ["Infektiologie"])
        self.assertEqual(a.schlagworte, "Hygiene, Desinfektion")
        self.assertEqual(a.originalname, "Hygieneplan 2026.pdf")
        self.assertTrue(a.datei.startswith("Artikel/"))
        self.assertEqual(self.db.pfad(a).read_bytes(), self.quelle.read_bytes())
        self.assertTrue(self.quelle.exists(), "Original bleibt unangetastet")

    def test_kategorie_ist_pflicht(self):
        with self.assertRaises(LiteraturFehler):
            self.db.artikel_anlegen(self.quelle, "Ohne Kategorie", None)
        with self.assertRaises(LiteraturFehler):
            self.db.artikel_anlegen(self.quelle, "Unbekannt", 9999)
        self.assertEqual(self.db.suche(), [])
        self.assertEqual(list(self.db.dateiordner.iterdir()), [], "keine verwaiste Kopie")

    def test_titel_ist_pflicht(self):
        with self.assertRaises(LiteraturFehler):
            self.anlegen(titel="   ")

    def test_fehlende_quelldatei(self):
        with self.assertRaises(LiteraturFehler):
            self.db.artikel_anlegen(self.wurzel / "fehlt.pdf", "X", self.kategorie("Medizin"))

    def test_gleicher_titel_ergibt_getrennte_dateien(self):
        a = self.anlegen()
        b = self.anlegen()
        self.assertNotEqual(a.datei, b.datei)

    def test_nachtraeglich_bearbeiten(self):
        a = self.anlegen(schlagworte="Hygiene")
        b = self.db.artikel_aendern(
            a.id, "Hygieneplan neu", self.kategorie("Formulare"),
            bereich_ids=[self.bereich("Formulare"), self.bereich("Infektiologie")],
            schlagworte="Hygiene, Begehung")
        self.assertEqual(b.titel, "Hygieneplan neu")
        self.assertEqual(b.kategorie, "Formulare")
        self.assertEqual(b.bereiche, ["Formulare", "Infektiologie"])
        self.assertEqual(b.schlagwort_liste, ["Hygiene", "Begehung"])
        self.db.schlagworte_setzen(a.id, "Audit")
        self.assertEqual(self.db.artikel(a.id).schlagworte, "Audit")

    def test_aendern_ohne_kategorie_scheitert(self):
        a = self.anlegen()
        with self.assertRaises(LiteraturFehler):
            self.db.artikel_aendern(a.id, "X", None)
        self.assertEqual(self.db.artikel(a.id).titel, "Hygieneplan")

    def test_datei_ersetzen(self):
        a = self.anlegen()
        alt = self.db.pfad(a)
        neu = self.wurzel / "fassung2.docx"
        neu.write_bytes(b"neu")
        b = self.db.datei_ersetzen(a.id, neu)
        self.assertFalse(alt.exists())
        self.assertEqual(self.db.pfad(b).read_bytes(), b"neu")
        self.assertEqual(b.originalname, "fassung2.docx")

    def test_loeschen_entfernt_datei(self):
        a = self.anlegen()
        pfad = self.db.pfad(a)
        self.db.artikel_loeschen(a.id)
        self.assertFalse(pfad.exists())
        with self.assertRaises(LiteraturFehler):
            self.db.artikel(a.id)


class Suche(Grundlage):
    def setUp(self):
        super().setUp()
        self.hygiene = self.anlegen(bereich_ids=[self.bereich("Infektiologie")],
                                    schlagworte="Händehygiene")
        self.diabetes = self.anlegen("Diabetes Leitlinie", "Medizin",
                                     bereich_ids=[self.bereich("Metabolik")],
                                     schlagworte="HbA1c, Insulin")
        self.bogen = self.anlegen("Anamnesebogen", "Formulare")

    def titel(self, treffer):
        return sorted(a.titel for a in treffer)

    def test_alle(self):
        self.assertEqual(len(self.db.suche()), 3)

    def test_nach_kategorie(self):
        self.assertEqual(self.titel(self.db.suche(kategorie_id=self.kategorie("Medizin"))),
                         ["Diabetes Leitlinie"])
        self.assertEqual(self.db.suche(kategorie_id=self.kategorie("Sonstiges")), [])

    def test_nach_bereich(self):
        self.assertEqual(self.titel(self.db.suche(bereich_id=self.bereich("Infektiologie"))),
                         ["Hygieneplan"])

    def test_text_ohne_gross_klein_und_mit_umlauten(self):
        self.assertEqual(self.titel(self.db.suche("HÄNDE")), ["Hygieneplan"])
        self.assertEqual(self.titel(self.db.suche("insulin leitlinie")),
                         ["Diabetes Leitlinie"])
        self.assertEqual(self.db.suche("insulin anamnese"), [])
        self.assertEqual(self.titel(self.db.suche("metabolik")), ["Diabetes Leitlinie"])

    def test_neues_der_letzten_31_tage(self):
        alt = (datetime.now() - timedelta(days=NEU_TAGE + 1)).isoformat(timespec="seconds")
        knapp = (datetime.now() - timedelta(days=NEU_TAGE - 1)).isoformat(timespec="seconds")
        with sqlite3.connect(self.db.datenbank) as roh:
            roh.execute("UPDATE artikel SET angelegt = ? WHERE id = ?", (alt, self.bogen.id))
            roh.execute("UPDATE artikel SET angelegt = ? WHERE id = ?",
                        (knapp, self.diabetes.id))
        self.assertEqual(self.titel(self.db.suche(neu_seit_tagen=NEU_TAGE)),
                         ["Diabetes Leitlinie", "Hygieneplan"])
        # Spaetere Bearbeitung macht einen alten Artikel nicht wieder "neu".
        self.db.schlagworte_setzen(self.bogen.id, "Aufnahme")
        self.assertNotIn("Anamnesebogen", self.titel(self.db.suche(neu_seit_tagen=NEU_TAGE)))

    def test_schlagwortvorschlaege(self):
        self.assertEqual(self.db.schlagworte(), ["Händehygiene", "HbA1c", "Insulin"])


class Listen(Grundlage):
    def test_kategorie_ergaenzen_umbenennen_sortieren(self):
        neu = self.db.eintrag_hinzufuegen("kategorien", "  Leitlinien ")
        self.assertEqual(self.db.kategorien()[-1].name, "Leitlinien")
        with self.assertRaises(LiteraturFehler):
            self.db.eintrag_hinzufuegen("kategorien", "medizin")
        self.db.eintrag_umbenennen("kategorien", neu, "Leitlinien (AWMF)")
        self.db.eintrag_verschieben("kategorien", neu, -1)
        namen = [k.name for k in self.db.kategorien()]
        self.assertEqual(namen[-2:], ["Leitlinien (AWMF)", "Sonstiges"])

    def test_umbenennen_wirkt_auf_vorhandene_artikel(self):
        a = self.anlegen(bereich_ids=[self.bereich("Metabolik")])
        self.db.eintrag_umbenennen("bereiche", self.bereich("Metabolik"), "Stoffwechsel")
        self.db.eintrag_umbenennen("kategorien", self.kategorie("Qualitätsmanagement"), "QM")
        b = self.db.artikel(a.id)
        self.assertEqual((b.kategorie, b.bereiche), ("QM", ["Stoffwechsel"]))

    def test_leerer_oder_doppelter_name(self):
        with self.assertRaises(LiteraturFehler):
            self.db.eintrag_hinzufuegen("bereiche", " ")
        with self.assertRaises(LiteraturFehler):
            self.db.eintrag_umbenennen("bereiche", self.bereich("Formulare"), "Metabolik")

    def test_benutzte_kategorie_braucht_ersatz(self):
        a = self.anlegen()
        qm = self.kategorie("Qualitätsmanagement")
        with self.assertRaises(LiteraturFehler):
            self.db.kategorie_loeschen(qm)
        self.db.kategorie_loeschen(qm, ersatz_id=self.kategorie("Sonstiges"))
        self.assertEqual(self.db.artikel(a.id).kategorie, "Sonstiges")
        self.assertNotIn("Qualitätsmanagement", [k.name for k in self.db.kategorien()])

    def test_letzte_kategorie_bleibt(self):
        for k in self.db.kategorien()[1:]:
            self.db.kategorie_loeschen(k.id)
        with self.assertRaises(LiteraturFehler):
            self.db.kategorie_loeschen(self.db.kategorien()[0].id)

    def test_bereich_loeschen_behaelt_artikel(self):
        a = self.anlegen(bereich_ids=[self.bereich("Infektiologie"), self.bereich("Formulare")])
        self.db.bereich_loeschen(self.bereich("Infektiologie"))
        self.assertEqual(self.db.artikel(a.id).bereiche, ["Formulare"])

    def test_anzahl_je_eintrag(self):
        self.anlegen(bereich_ids=[self.bereich("Formulare")])
        self.assertEqual({k.name: k.anzahl for k in self.db.kategorien()}["Qualitätsmanagement"], 1)
        self.assertEqual({b.name: b.anzahl for b in self.db.bereiche()}["Formulare"], 1)


class Rubriken(Grundlage):
    def rubrik(self, name):
        return next(r.id for r in self.db.rubriken() if r.name == name)

    def test_qm_hat_vorgegebene_rubriken(self):
        qm = self.kategorie("Qualitätsmanagement")
        self.assertEqual([r.name for r in self.db.rubriken(qm)],
                         list(STANDARD_RUBRIKEN["Qualitätsmanagement"]))
        self.assertEqual(self.db.rubriken(self.kategorie("Medizin")), [])

    def test_artikel_mit_rubrik_ablegen_filtern_aendern(self):
        a = self.anlegen(rubrik_id=self.rubrik("Arbeitsanweisungen"))
        b = self.anlegen("Autoklav", rubrik_id=self.rubrik("Gebrauchsanleitungen"))
        self.assertEqual(a.rubrik, "Arbeitsanweisungen")
        self.assertEqual([x.titel for x in self.db.suche(
            rubrik_id=self.rubrik("Gebrauchsanleitungen"))], ["Autoklav"])
        self.assertEqual([x.titel for x in self.db.suche("einweisungen")], [])
        c = self.db.artikel_aendern(b.id, "Autoklav", b.kategorie_id,
                                    rubrik_id=self.rubrik("Einweisungen"))
        self.assertEqual(c.rubrik, "Einweisungen")
        self.assertEqual(self.db.artikel_aendern(b.id, "Autoklav", b.kategorie_id).rubrik, "")

    def test_rubrik_muss_zur_kategorie_passen(self):
        with self.assertRaises(LiteraturFehler):
            self.anlegen(kategorie="Medizin", rubrik_id=self.rubrik("Arbeitsanweisungen"))

    def test_rubriken_je_kategorie_veraenderbar(self):
        medizin = self.kategorie("Medizin")
        neu = self.db.eintrag_hinzufuegen("rubriken", "Leitlinien", medizin)
        # Gleicher Name in anderer Kategorie ist erlaubt, in derselben nicht.
        self.db.eintrag_hinzufuegen("rubriken", "Leitlinien", self.kategorie("Sonstiges"))
        with self.assertRaises(LiteraturFehler):
            self.db.eintrag_hinzufuegen("rubriken", "leitlinien", medizin)
        with self.assertRaises(LiteraturFehler):
            self.db.eintrag_hinzufuegen("rubriken", "Ohne Kategorie")
        self.db.eintrag_hinzufuegen("rubriken", "Studien", medizin)
        self.db.eintrag_verschieben("rubriken", neu, 1)
        self.assertEqual([r.name for r in self.db.rubriken(medizin)], ["Studien", "Leitlinien"])
        self.db.eintrag_umbenennen("rubriken", self.rubrik("Prozessbeschreibungen"), "Prozesse")
        self.assertIn("Prozesse", [r.name for r in self.db.rubriken()])

    def test_rubrik_loeschen_behaelt_artikel(self):
        a = self.anlegen(rubrik_id=self.rubrik("Einweisungen"))
        self.db.rubrik_loeschen(self.rubrik("Einweisungen"))
        b = self.db.artikel(a.id)
        self.assertEqual((b.kategorie, b.rubrik, b.rubrik_id), ("Qualitätsmanagement", "", None))

    def test_kategoriewechsel_beim_loeschen_entfernt_rubrik(self):
        a = self.anlegen(rubrik_id=self.rubrik("Einweisungen"))
        self.db.kategorie_loeschen(self.kategorie("Qualitätsmanagement"),
                                   self.kategorie("Sonstiges"))
        b = self.db.artikel(a.id)
        self.assertEqual((b.kategorie, b.rubrik_id), ("Sonstiges", None))
        self.assertEqual(self.db.rubriken(), [])


class Umstellung(unittest.TestCase):
    def test_datenbank_der_ersten_version_wird_ergaenzt(self):
        with tempfile.TemporaryDirectory() as temp:
            ordner = Path(temp)
            alt = SCHEMA.split("CREATE TABLE IF NOT EXISTS rubriken")[0] + \
                "CREATE TABLE IF NOT EXISTS artikel" + \
                SCHEMA.split("CREATE TABLE IF NOT EXISTS artikel", 1)[1]
            alt = alt.replace("    rubrik_id     INTEGER REFERENCES rubriken(id)"
                              " ON DELETE SET NULL,\n", "")
            with sqlite3.connect(ordner / DATENBANK) as roh:
                roh.executescript(alt)
                roh.execute("INSERT INTO kategorien (name) VALUES ('Qualitätsmanagement')")
                roh.execute("INSERT INTO artikel (titel, kategorie_id, angelegt, geaendert)"
                            " VALUES ('Alt', 1, '2025-01-01', '2025-01-01')")
                roh.execute("PRAGMA user_version = 1")
            db = Literaturdatenbank(ordner).einrichten()
            self.assertEqual(len(db.rubriken()), 5)
            self.assertEqual(db.suche()[0].rubrik_id, None)
            self.assertEqual(db.bereiche(), [], "vorhandene Listen bleiben unberuehrt")


class Hilfsfunktionen(unittest.TestCase):
    def test_schlagworte(self):
        self.assertEqual(normiere_schlagworte(" a ;b\n A,, c  d "), "a, b, c d")

    def test_dateiname(self):
        self.assertEqual(dateiname("Händehygiene: Plan/2026?"), "Haendehygiene_Plan2026")
        self.assertEqual(dateiname("???"), "artikel")

    def test_datenordner_merken(self):
        with tempfile.TemporaryDirectory() as temp:
            datei = Path(temp) / "einstellungen.json"
            with mock.patch.dict(os.environ, {}, clear=False):
                os.environ.pop("LITERATUR_ORDNER", None)
                self.assertIsNone(einstellungen.datenordner(datei))
                einstellungen.datenordner_merken(r"\\server\Literatur", datei)
                self.assertEqual(einstellungen.datenordner(datei), Path(r"\\server\Literatur"))
            with mock.patch.dict(os.environ, {"LITERATUR_ORDNER": temp}):
                self.assertEqual(einstellungen.datenordner(datei), Path(temp))


if __name__ == "__main__":
    unittest.main()
