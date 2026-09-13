"""Testfaelle des GOAE-Abrechnungskalkulators."""

import contextlib
import io
import re
import sys
import tempfile
import unittest
import zipfile
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from goae_kalkulator import angaben, farben
from goae_kalkulator.cli import betrag, main, zerlege_ziffer, Abbruch
from goae_kalkulator.eigene import EigeneFehler, EigeneZiffern, katalog_mit_eigenen
from goae_kalkulator.excel import exportiere
from goae_kalkulator.katalog import Katalog, KatalogFehler
from goae_kalkulator.modelle import (
    FAKTOR_SCHRITT, MAX_FAKTOR, MIN_FAKTOR, Angebot, Leistung, Position, faktor_text, geld,
)
from goae_kalkulator.speicher import Angebotsverzeichnis, SpeicherFehler, dateiname
from goae_kalkulator.zielbetrag import optimiere_faktoren, STRATEGIEN


def leistung(nummer="1", punkte=80, klasse="aerztlich", regel="2.3", hoechst="3.5"):
    return Leistung(nummer, f"Testleistung {nummer}", punkte, "B", klasse,
                    Decimal(regel), Decimal(hoechst))


class TestBetragsrechnung(unittest.TestCase):
    """Punktzahl x Punktwert x Faktor, kaufmaennisch auf den Cent gerundet."""

    def test_bekannte_betraege(self):
        # Allgemein gelaeufige GOAE-Betraege fuer Nr. 1, 3 und 8.
        for punkte, einfach, zweikommadrei, dreikommafuenf in [
            (80, "4.66", "10.72", "16.32"),
            (150, "8.74", "20.11", "30.60"),
            (260, "15.15", "34.86", "53.04"),
        ]:
            l = leistung(punkte=punkte)
            self.assertEqual(l.einfachsatz, Decimal(einfach))
            self.assertEqual(l.satz_2_3, Decimal(zweikommadrei))
            self.assertEqual(l.satz_3_5, Decimal(dreikommafuenf))

    def test_anzahl_vervielfacht_den_gerundeten_einzelbetrag(self):
        p = Position.aus_leistung(leistung(punkte=80), anzahl=3, faktorwert=Decimal("2.3"))
        self.assertEqual(p.einzelbetrag, Decimal("10.72"))
        self.assertEqual(p.betrag, Decimal("32.16"))

    def test_faktor_wird_auf_drei_stellen_normiert(self):
        p = Position.aus_leistung(leistung(), faktorwert=Decimal("2.3456"))
        self.assertEqual(p.faktor, Decimal("2.346"))

    def test_darstellung(self):
        self.assertEqual(geld(Decimal("1234.5")), "1.234,50")
        self.assertEqual(faktor_text(Decimal("2.300")), "2,3")
        self.assertEqual(faktor_text(Decimal("3.359")), "3,359")
        self.assertEqual(faktor_text(Decimal("1.000")), "1,0")


class TestHinweise(unittest.TestCase):
    def test_ueber_regelsatz_verlangt_begruendung(self):
        p = Position.aus_leistung(leistung(), faktorwert=Decimal("2.8"))
        self.assertTrue(p.ueber_regelsatz)
        self.assertIn("Begruendung", p.hinweis())
        p.begruendung = "erhoehter Zeitaufwand"
        self.assertEqual(p.hinweis(), "")

    def test_ueber_hoechstsatz_der_klasse(self):
        p = Position.aus_leistung(leistung(klasse="labor", regel="1.15", hoechst="1.3"),
                                  faktorwert=Decimal("2.0"))
        self.assertTrue(p.ueber_hoechstsatz)
        self.assertIn("Hoechstsatz", p.hinweis())


class TestAngebot(unittest.TestCase):
    def setUp(self):
        self.angebot = Angebot(name="Paket")
        self.angebot.hinzufuegen(Position.aus_leistung(leistung("1", 80)))
        self.angebot.hinzufuegen(Position.aus_leistung(leistung("8", 260), anzahl=2))

    def test_summen_der_anzeigespalten(self):
        self.assertEqual(self.angebot.summe_einfach, Decimal("4.66") + Decimal("30.30"))
        self.assertEqual(self.angebot.summe_2_3, Decimal("10.72") + Decimal("69.72"))
        self.assertEqual(self.angebot.summe_3_5, Decimal("16.32") + Decimal("106.08"))
        self.assertEqual(self.angebot.summe, self.angebot.summe_2_3)

    def test_punkte(self):
        self.assertEqual(self.angebot.punkte, 80 + 520)

    def test_spanne_beruecksichtigt_fixierte_positionen(self):
        self.angebot.positionen[0].fixiert = True
        self.angebot.positionen[0].faktor = Decimal("3.0")
        unten, oben = self.angebot.spanne()
        fest = self.angebot.positionen[0].betrag
        self.assertEqual(unten, fest + Decimal("30.30"))
        self.assertEqual(oben, fest + Decimal("106.08"))

    def test_serialisierung_ist_verlustfrei(self):
        self.angebot.zielbetrag = Decimal("99.90")
        self.angebot.positionen[0].begruendung = "Test"
        kopie = Angebot.from_dict(self.angebot.to_dict())
        self.assertEqual(kopie.summe, self.angebot.summe)
        self.assertEqual(kopie.zielbetrag, Decimal("99.90"))
        self.assertEqual(kopie.positionen[0].begruendung, "Test")


class TestKatalog(unittest.TestCase):
    def setUp(self):
        self.katalog = Katalog.laden()

    def test_mitgelieferter_katalog_laedt(self):
        self.assertGreater(len(self.katalog), 20)
        self.assertIn("1", self.katalog)
        self.assertEqual(self.katalog.hole("1").punktzahl, 80)

    def test_suche_nach_nummer_und_text(self):
        self.assertTrue(any(l.nummer == "1" for l in self.katalog.suche("1")))
        self.assertTrue(self.katalog.suche("beratung"))
        self.assertEqual(self.katalog.suche("gibtesnicht"), [])

    def test_exakter_nummerntreffer_steht_vorn(self):
        self.assertEqual(self.katalog.suche("50")[0].nummer, "50")

    def test_unbekannte_ziffer(self):
        with self.assertRaises(KeyError):
            self.katalog.hole("99999")

    def test_import_mit_komma_und_tabulator(self):
        text = "nummer\tbezeichnung\tpunktzahl\tklasse\tregelsatz\n" \
               "9001\tEigene Leistung\t250\taerztlich\t2,3\n"
        eigen = Katalog.aus_text(text)
        self.assertEqual(eigen.hole("9001").punktzahl, 250)
        self.assertEqual(eigen.hole("9001").regelsatz, Decimal("2.3"))

    def test_kommentarzeilen_werden_uebersprungen(self):
        text = "# Kommentar\n\nnummer;bezeichnung;punktzahl\n7000;Test;100\n"
        self.assertEqual(len(Katalog.aus_text(text)), 1)

    def test_fehlerhafte_datei(self):
        with self.assertRaises(KatalogFehler):
            Katalog.aus_text("bezeichnung;punkte\nTest;100\n")
        with self.assertRaises(KatalogFehler):
            Katalog.aus_text("nummer;punktzahl\n1;keinezahl\n")

    def test_ergaenzen_ersetzt_gleiche_nummer(self):
        vorher = len(self.katalog)
        self.katalog.ergaenzen(Katalog.aus_text("nummer;bezeichnung;punktzahl\n1;Neu;999\n"))
        self.assertEqual(len(self.katalog), vorher)
        self.assertEqual(self.katalog.hole("1").punktzahl, 999)


class TestMitgelieferterKatalog(unittest.TestCase):
    """Prueft den aus dem amtlichen GOAE-Text erzeugten Katalog."""

    @classmethod
    def setUpClass(cls):
        cls.katalog = Katalog.laden()

    def test_umfang(self):
        # Das Gebuehrenverzeichnis umfasst rund 2 800 bepunktete Nummern.
        self.assertGreater(len(self.katalog), 2700)

    def test_bekannte_betraege(self):
        for nummer, punkte, einfach, satz23, satz35 in [
            ("1", 80, "4.66", "10.72", "16.32"),
            ("3", 150, "8.74", "20.11", "30.60"),
            ("8", 260, "15.15", "34.86", "53.04"),
            ("5", 80, "4.66", "10.72", "16.32"),
        ]:
            l = self.katalog.hole(nummer)
            self.assertEqual(l.punktzahl, punkte, f"Ziffer {nummer}")
            self.assertEqual(l.einfachsatz, Decimal(einfach), f"Ziffer {nummer}")
            self.assertEqual(l.satz_2_3, Decimal(satz23), f"Ziffer {nummer}")
            self.assertEqual(l.satz_3_5, Decimal(satz35), f"Ziffer {nummer}")

    def test_abschnittsgrenzen(self):
        for nummer, abschnitt in [("1", "B"), ("109", "B"), ("200", "C"), ("449", "C"),
                                  ("450", "D"), ("500", "E"), ("600", "F"), ("800", "G"),
                                  ("1001", "H"), ("1200", "I"), ("1400", "J"), ("1700", "K"),
                                  ("2000", "L"), ("3500", "M"), ("4800", "N"), ("5000", "O"),
                                  ("6000", "P")]:
            self.assertEqual(self.katalog.hole(nummer).abschnitt, abschnitt, f"Ziffer {nummer}")

    def test_steigerungsklassen_nach_paragraf_5(self):
        """§ 5 Abs. 3: Abschnitte A, E, O -> 1,8/2,5; Abs. 4: Abschnitt M und Nr. 437."""
        erwartet = {
            "1": "aerztlich",     # Abs. 2
            "2": "technisch",     # in Abschnitt A namentlich genannt
            "56": "technisch",    # in Abschnitt A namentlich genannt
            "250": "technisch",   # in Abschnitt A namentlich genannt
            "250a": "technisch",  # in Abschnitt A namentlich genannt
            "410": "aerztlich",   # Sonographie: nicht in Abschnitt A
            "437": "labor",       # Abs. 4 nennt Nummer 437 ausdruecklich
            "500": "technisch",   # Abschnitt E
            "650": "technisch",   # in Abschnitt A namentlich genannt
            "652": "aerztlich",   # nicht in Abschnitt A
            "3511": "labor",      # Abschnitt M
            "4800": "aerztlich",  # Abschnitt N, Histologie
            "4850": "technisch",  # Abschnitt N, Zytologie: in Abschnitt A genannt
            "5000": "technisch",  # Abschnitt O
            "6000": "aerztlich",  # Abschnitt P
        }
        for nummer, klasse in erwartet.items():
            l = self.katalog.hole(nummer)
            self.assertEqual(l.klasse, klasse, f"Ziffer {nummer}")

    def test_saetze_passen_zur_klasse(self):
        paare = {"aerztlich": (Decimal("2.3"), Decimal("3.5")),
                 "technisch": (Decimal("1.8"), Decimal("2.5")),
                 "labor": (Decimal("1.15"), Decimal("1.3"))}
        for l in self.katalog:
            self.assertEqual((l.regelsatz, l.hoechstsatz), paare[l.klasse], f"Ziffer {l.nummer}")

    def test_jede_ziffer_hat_punktzahl_und_legende(self):
        for l in self.katalog:
            self.assertGreater(l.punktzahl, 0, f"Ziffer {l.nummer}")
            self.assertTrue(l.bezeichnung.strip(), f"Ziffer {l.nummer}")
            self.assertIn(l.herkunft, ("direkt", "sammel"), f"Ziffer {l.nummer}")

    def test_buchstabenzusatz_sortiert_hinter_der_grundnummer(self):
        nummern = [l.nummer for l in self.katalog]
        self.assertEqual(nummern[nummern.index("250"):nummern.index("250") + 3],
                         ["250", "250a", "251"])

    def test_sammelposition_wird_gekennzeichnet(self):
        """Nr. 3514 (Glukose) steht in einer Sammelposition mit eigener Punktzahl."""
        glukose = self.katalog.hole("3514")
        self.assertEqual(glukose.herkunft, "sammel")
        self.assertEqual(glukose.punktzahl, 70)
        # Nicht die Punktzahl der davorstehenden Nummer 3511 (50 Punkte).
        self.assertNotEqual(glukose.punktzahl, self.katalog.hole("3511").punktzahl)
        position = Position.aus_leistung(glukose, faktorwert=Decimal("1.15"))
        self.assertIn("Sammelposition", position.hinweis())

    def test_punktzahlen_aus_sammelpositionen(self):
        """Diese Werte waren einmal falsch - sie stammen aus der Ueberschrift
        der Sammelposition, nicht von der davorstehenden Nummer."""
        for nummer, punkte, bezeichnung in [
            ("3504", 60, "Erythrozyten"),
            ("3514", 70, "Glukose"),
            ("4030", 250, "Thyreoidea stimulierendes Hormon (TSH)"),
            ("4022", 250, "Freies Trijodthyronin (fT3)"),
            ("4023", 250, "Freies Thyroxin (fT4)"),
            ("4031", 250, "Thyroxin"),
            ("4032", 250, "Trijodthyronin"),
            ("4705", 120, "Aspergillus"),
            ("4640", 250, "Adeno-Viren"),
            ("K 1", 120, "Zuschlag zu Untersuchungen"),
        ]:
            l = self.katalog.hole(nummer)
            self.assertEqual(l.punktzahl, punkte, f"Ziffer {nummer}")
            self.assertIn(bezeichnung[:20], l.bezeichnung, f"Ziffer {nummer}")

    def test_tsh_ergibt_den_erwarteten_betrag(self):
        tsh = self.katalog.hole("4030")
        self.assertEqual(tsh.einfachsatz, Decimal("14.57"))
        self.assertEqual(tsh.betrag(Decimal("1.15")), Decimal("16.76"))
        self.assertEqual(tsh.klasse, "labor")

    def test_hundertsatz_zuschlaege_sind_nicht_enthalten(self):
        """441 und 5298 werden als Hundertsatz der Bezugsleistung berechnet und
        haben keine Punktzahl - sie duerfen nicht mit einer erfundenen im
        Katalog stehen."""
        for nummer in ("441", "5298"):
            self.assertNotIn(nummer, self.katalog)

    def test_zuschlagsziffern_mit_leerzeichen(self):
        self.assertEqual(zerlege_ziffer("K 2"), ("K 2", 1, None))
        self.assertEqual(self.katalog.hole("K 2").punktzahl, 120)


class TestZielbetrag(unittest.TestCase):
    def bau(self):
        angebot = Angebot(name="Ziel")
        for nummer, punkte in (("1", 80), ("8", 260), ("650", 253), ("410", 200)):
            angebot.hinzufuegen(Position.aus_leistung(leistung(nummer, punkte)))
        return angebot

    def test_zielbetrag_wird_centgenau_getroffen(self):
        """Mit erlaubter Nachjustierung stimmt der Betrag exakt."""
        # Erreichbar sind mit diesen vier Ziffern rund 46,22 bis 161,77 EUR.
        for ziel in ("60.00", "99.99", "123.45", "150.00", "161.00"):
            angebot = self.bau()
            ergebnis = optimiere_faktoren(angebot.positionen, ziel, nachjustieren=True)
            self.assertEqual(angebot.summe, ergebnis.summe)
            self.assertTrue(ergebnis.erreicht, f"{ziel}: {ergebnis.meldung}")
            self.assertEqual(ergebnis.summe, Decimal(ziel))

    def test_zehntelraster_kommt_dem_zielbetrag_sehr_nahe(self):
        """Vorgabe sind Zehntelschritte; ein Restbetrag von wenigen Cent bleibt moeglich."""
        for ziel in ("60.00", "99.99", "123.45", "150.00", "161.00"):
            angebot = self.bau()
            ergebnis = optimiere_faktoren(angebot.positionen, ziel)
            self.assertLessEqual(abs(ergebnis.abweichung), Decimal("0.20"),
                                 f"{ziel}: {ergebnis.meldung}")
            for p in angebot.positionen:
                self.assertEqual(p.faktor, p.faktor.quantize(Decimal("0.1")),
                                 f"Ziffer {p.nummer}: {p.faktor} liegt nicht im Zehntelraster")

    def test_feineres_raster_ist_waehlbar(self):
        angebot = self.bau()
        optimiere_faktoren(angebot.positionen, "123.45", schrittweite=Decimal("0.01"))
        for p in angebot.positionen:
            self.assertEqual(p.faktor, p.faktor.quantize(Decimal("0.01")))

    def test_faktoren_bleiben_in_der_spanne(self):
        for ziel in ("50.00", "100.00", "161.00", "1000.00", "10.00"):
            angebot = self.bau()
            optimiere_faktoren(angebot.positionen, ziel)
            for p in angebot.positionen:
                self.assertGreaterEqual(p.faktor, MIN_FAKTOR, f"{ziel} / Ziffer {p.nummer}")
                self.assertLessEqual(p.faktor, MAX_FAKTOR, f"{ziel} / Ziffer {p.nummer}")

    def test_alle_strategien_treffen_den_zielbetrag(self):
        for strategie in STRATEGIEN:
            angebot = self.bau()
            ergebnis = optimiere_faktoren(angebot.positionen, "120.00", strategie=strategie,
                                          nachjustieren=True)
            self.assertTrue(ergebnis.erreicht, f"{strategie}: {ergebnis.meldung}")

    def test_einheitliche_strategie_liefert_einen_faktor(self):
        angebot = self.bau()
        optimiere_faktoren(angebot.positionen, "120.00", strategie="einheitlich")
        faktoren = {p.faktor for p in angebot.positionen}
        # Der Feinabgleich darf einzelne Ziffern um einen Rasterschritt nachziehen.
        self.assertLessEqual(max(faktoren) - min(faktoren), Decimal("0.2"))

    def test_zu_hoher_zielbetrag_endet_am_oberen_anschlag(self):
        angebot = self.bau()
        ergebnis = optimiere_faktoren(angebot.positionen, "5000.00")
        self.assertFalse(ergebnis.erreicht)
        self.assertEqual(ergebnis.summe, ergebnis.max_summe)
        self.assertTrue(all(p.faktor == MAX_FAKTOR for p in angebot.positionen))
        self.assertIn("zu hoch", ergebnis.meldung)

    def test_zu_niedriger_zielbetrag_endet_am_unteren_anschlag(self):
        angebot = self.bau()
        ergebnis = optimiere_faktoren(angebot.positionen, "1.00")
        self.assertFalse(ergebnis.erreicht)
        self.assertEqual(ergebnis.summe, ergebnis.min_summe)
        self.assertTrue(all(p.faktor == MIN_FAKTOR for p in angebot.positionen))
        self.assertIn("zu niedrig", ergebnis.meldung)

    def test_fixierte_positionen_bleiben_unveraendert(self):
        angebot = self.bau()
        angebot.positionen[0].faktor = Decimal("1.7")
        angebot.positionen[0].fixiert = True
        ergebnis = optimiere_faktoren(angebot.positionen, "120.00", nachjustieren=True)
        self.assertEqual(angebot.positionen[0].faktor, Decimal("1.700"))
        self.assertTrue(ergebnis.erreicht, ergebnis.meldung)
        self.assertEqual(angebot.summe, Decimal("120.00"))

    def test_nur_fixierte_positionen(self):
        angebot = self.bau()
        for p in angebot.positionen:
            p.fixiert = True
        ergebnis = optimiere_faktoren(angebot.positionen, "120.00")
        self.assertIn("fixiert", ergebnis.meldung)

    def test_leeres_angebot(self):
        ergebnis = optimiere_faktoren([], "100.00")
        self.assertIn("keine Positionen", ergebnis.meldung)

    def test_engere_grenzen_werden_beachtet(self):
        angebot = self.bau()
        optimiere_faktoren(angebot.positionen, "100.00",
                           min_faktor=Decimal("1.5"), max_faktor=Decimal("2.5"))
        for p in angebot.positionen:
            self.assertGreaterEqual(p.faktor, Decimal("1.5"))
            self.assertLessEqual(p.faktor, Decimal("2.5"))

    def test_rechtliche_grenzen_der_steigerungsklassen(self):
        angebot = Angebot(name="Klassen")
        angebot.hinzufuegen(Position.aus_leistung(leistung("1", 80)))
        angebot.hinzufuegen(Position.aus_leistung(
            leistung("3511", 30, klasse="labor", regel="1.15", hoechst="1.3")))
        angebot.hinzufuegen(Position.aus_leistung(
            leistung("650", 253, klasse="technisch", regel="1.8", hoechst="2.5")))
        optimiere_faktoren(angebot.positionen, "45.00", rechtliche_grenzen=True)
        nach_nummer = {p.nummer: p for p in angebot.positionen}
        self.assertLessEqual(nach_nummer["3511"].faktor, Decimal("1.3"))
        self.assertLessEqual(nach_nummer["650"].faktor, Decimal("2.5"))

    def test_nachjustierung_schliesst_die_luecke(self):
        angebot = Angebot(name="Fein")
        angebot.hinzufuegen(Position.aus_leistung(leistung("1", 80)))
        grob = optimiere_faktoren(angebot.positionen, "9.37", anwenden=False)
        fein = optimiere_faktoren(angebot.positionen, "9.37", nachjustieren=True, anwenden=False)
        self.assertNotEqual(grob.abweichung, Decimal("0.00"))
        self.assertIn("Faktorraster", grob.meldung)
        self.assertTrue(fein.erreicht, fein.meldung)

    def test_meldung_verweist_auf_feinere_stufung(self):
        angebot = Angebot(name="Fein")
        angebot.hinzufuegen(Position.aus_leistung(leistung("1", 80)))
        ergebnis = optimiere_faktoren(angebot.positionen, "9.37", anwenden=False)
        self.assertFalse(ergebnis.erreicht)
        self.assertIn("feineren Faktoren", ergebnis.meldung)

    def test_nicht_darstellbarer_betrag_wird_als_solcher_gemeldet(self):
        """Bei Anzahl 3 wird der Einzelbetrag gerundet und verdreifacht -
        erreichbar sind dann nur Vielfache von drei Cent."""
        angebot = Angebot(name="Dreifach")
        angebot.hinzufuegen(Position.aus_leistung(leistung("3541", 40), anzahl=3))
        ergebnis = optimiere_faktoren(angebot.positionen, "13.00", nachjustieren=True)
        self.assertFalse(ergebnis.erreicht)
        self.assertEqual(abs(ergebnis.abweichung), Decimal("0.01"))
        self.assertIn("Feiner geht es nicht", ergebnis.meldung)

    def test_vorgabe_ist_das_zehntelraster(self):
        self.assertEqual(FAKTOR_SCHRITT, Decimal("0.1"))

    def test_probelauf_veraendert_nichts(self):
        angebot = self.bau()
        vorher = [p.faktor for p in angebot.positionen]
        optimiere_faktoren(angebot.positionen, "180.00", anwenden=False)
        self.assertEqual([p.faktor for p in angebot.positionen], vorher)

    def test_unbekannte_strategie(self):
        with self.assertRaises(ValueError):
            optimiere_faktoren([], "10.00", strategie="wuenschdirwas")


class TestSpeicher(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.verzeichnis = Angebotsverzeichnis(self.ordner.name)

    def tearDown(self):
        self.ordner.cleanup()

    def bau(self, name="Mein Angebot"):
        angebot = Angebot(name=name, patient="Frau Muster")
        angebot.hinzufuegen(Position.aus_leistung(leistung("1", 80)))
        return angebot

    def test_speichern_und_laden(self):
        angebot = self.bau()
        pfad = self.verzeichnis.speichern(angebot)
        self.assertTrue(pfad.exists())
        geladen = self.verzeichnis.laden("Mein Angebot")
        self.assertEqual(geladen.patient, "Frau Muster")
        self.assertEqual(geladen.summe, angebot.summe)

    def test_erneutes_speichern_legt_keine_zweite_datei_an(self):
        angebot = self.bau()
        self.verzeichnis.speichern(angebot)
        angebot.hinzufuegen(Position.aus_leistung(leistung("8", 260)))
        self.verzeichnis.speichern(angebot)
        self.assertEqual(len(self.verzeichnis.dateien()), 1)
        self.assertEqual(len(self.verzeichnis.laden("Mein Angebot").positionen), 2)

    def test_umlaute_und_sonderzeichen_im_namen(self):
        angebot = self.bau("Vorsorge für Männer / 2026")
        self.verzeichnis.speichern(angebot)
        geladen = self.verzeichnis.laden("Vorsorge für Männer / 2026")
        self.assertEqual(geladen.name, "Vorsorge für Männer / 2026")
        self.assertEqual(dateiname("Vorsorge für Männer / 2026"), "Vorsorge_fuer_Maenner_2026")

    def test_liste_und_loeschen(self):
        self.verzeichnis.speichern(self.bau("A"))
        self.verzeichnis.speichern(self.bau("B"))
        self.assertEqual(sorted(self.verzeichnis.namen()), ["A", "B"])
        self.verzeichnis.loeschen("A")
        self.assertEqual(self.verzeichnis.namen(), ["B"])

    def test_kopieren(self):
        self.verzeichnis.speichern(self.bau("Original"))
        self.verzeichnis.kopieren("Original", "Kopie")
        self.assertEqual(sorted(self.verzeichnis.namen()), ["Kopie", "Original"])

    def test_fehlende_datei(self):
        with self.assertRaises(SpeicherFehler):
            self.verzeichnis.laden("gibtesnicht")

    def test_beschaedigte_datei_blockiert_die_liste_nicht(self):
        self.verzeichnis.speichern(self.bau("Heil"))
        (Path(self.ordner.name) / "kaputt.json").write_text("{kein json", encoding="utf-8")
        self.assertEqual(self.verzeichnis.namen(), ["Heil"])

    def test_name_ohne_inhalt(self):
        with self.assertRaises(SpeicherFehler):
            self.verzeichnis.speichern(Angebot(name="   "))


class TestExcel(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.angebot = Angebot(name="Excel-Test", patient="Herr Beispiel")
        self.angebot.hinzufuegen(Position.aus_leistung(leistung("1", 80)))
        self.angebot.hinzufuegen(Position.aus_leistung(leistung("8", 260), anzahl=2))
        self.angebot.zielbetrag = Decimal("100.00")

    def tearDown(self):
        self.ordner.cleanup()

    def test_datei_ist_eine_gueltige_arbeitsmappe(self):
        pfad = exportiere(self.angebot, Path(self.ordner.name) / "test.xlsx")
        self.assertTrue(pfad.exists())
        with zipfile.ZipFile(pfad) as archiv:
            namen = archiv.namelist()
            for teil in ("[Content_Types].xml", "_rels/.rels", "xl/workbook.xml",
                         "xl/styles.xml", "xl/worksheets/sheet1.xml"):
                self.assertIn(teil, namen)
            blatt = archiv.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("Excel-Test", blatt)
        self.assertIn("Herr Beispiel", blatt)
        self.assertIn("3,5-fach", blatt)

    def test_endung_wird_ergaenzt(self):
        pfad = exportiere(self.angebot, Path(self.ordner.name) / "ohne_endung")
        self.assertEqual(pfad.suffix, ".xlsx")

    def test_mehrere_angebote_erhalten_ein_uebersichtsblatt(self):
        zweites = Angebot(name="Zweites")
        zweites.hinzufuegen(Position.aus_leistung(leistung("3", 150)))
        pfad = exportiere([self.angebot, zweites], Path(self.ordner.name) / "alle.xlsx")
        with zipfile.ZipFile(pfad) as archiv:
            self.assertIn("xl/worksheets/sheet3.xml", archiv.namelist())
            self.assertIn("Uebersicht", archiv.read("xl/workbook.xml").decode())

    def test_sonderzeichen_werden_maskiert(self):
        self.angebot.beschreibung = 'Paket "A" & <B>'
        pfad = exportiere(self.angebot, Path(self.ordner.name) / "sonder.xlsx")
        with zipfile.ZipFile(pfad) as archiv:
            blatt = archiv.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("&amp;", blatt)
        self.assertIn("&lt;B&gt;", blatt)

    def test_blattnamen_werden_gekuerzt_und_bereinigt(self):
        lang = Angebot(name="Ein sehr langer Angebotsname mit [Klammern]/Schraegstrich")
        lang.hinzufuegen(Position.aus_leistung(leistung()))
        pfad = exportiere(lang, Path(self.ordner.name) / "lang.xlsx")
        with zipfile.ZipFile(pfad) as archiv:
            workbook = archiv.read("xl/workbook.xml").decode()
        self.assertNotIn("[", workbook.split('name="')[1].split('"')[0])


class TestEigeneZiffern(unittest.TestCase):
    """Analogziffern nach § 6 Abs. 2 GOAE - nur auf dem Geraet des Anwenders."""

    @classmethod
    def setUpClass(cls):
        cls.katalog = Katalog.laden()

    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.eigene = EigeneZiffern(self.ordner.name)

    def tearDown(self):
        self.ordner.cleanup()

    def test_anlegen_uebernimmt_die_werte_der_vorlage(self):
        vorlage = self.katalog.hole("1800")
        neu = self.eigene.anlegen(self.katalog, "Stosswellentherapie", "1800")
        self.assertEqual(neu.nummer, "A1800")
        self.assertEqual(neu.analog_zu, "1800")
        self.assertEqual(neu.punktzahl, vorlage.punktzahl)
        self.assertEqual(neu.klasse, vorlage.klasse)
        self.assertEqual(neu.regelsatz, vorlage.regelsatz)
        self.assertEqual(neu.hoechstsatz, vorlage.hoechstsatz)
        self.assertEqual(neu.satz_2_3, vorlage.satz_2_3)
        self.assertEqual(neu.herkunft, "analog")

    def test_eigene_nummer(self):
        neu = self.eigene.anlegen(self.katalog, "Akupunktur", "269", nummer="A-AKU")
        self.assertEqual(neu.nummer, "A-AKU")

    def test_die_ablage_ueberdauert_einen_neustart(self):
        self.eigene.anlegen(self.katalog, "Stosswellentherapie", "1800")
        wieder = EigeneZiffern(self.ordner.name)
        self.assertEqual(len(wieder), 1)
        self.assertEqual(wieder.hole("A1800").bezeichnung, "Stosswellentherapie")

    def test_abgelehnte_eingaben(self):
        self.eigene.anlegen(self.katalog, "Erste", "1800")
        for text, vorlage, nummer in [
            ("", "1800", None),                    # ohne Bezeichnung
            ("Zweite", "99999", None),             # Vorlage gibt es nicht
            ("Zweite", "1800", None),              # Nummer schon vergeben (eigene)
            ("Zweite", "1800", "1"),               # Nummer amtlich vergeben
            ("Zweite", "1800", "A/B;C"),           # unzulaessige Zeichen
            ("Zweite", "1800", "A" * 20),          # zu lang
        ]:
            with self.assertRaises(EigeneFehler, msg=f"{text!r}/{vorlage}/{nummer}"):
                self.eigene.anlegen(self.katalog, text, vorlage, nummer=nummer)

    def test_loeschen(self):
        self.eigene.anlegen(self.katalog, "Stosswellentherapie", "1800")
        self.eigene.loeschen("a1800")            # Gross-/Kleinschreibung egal
        self.assertEqual(len(self.eigene), 0)
        with self.assertRaises(EigeneFehler):
            self.eigene.loeschen("A1800")

    def test_ueberlagerung_laesst_den_amtlichen_katalog_unberuehrt(self):
        self.eigene.anlegen(self.katalog, "Stosswellentherapie", "1800")
        vorher = len(self.katalog)
        zusammen = katalog_mit_eigenen(self.katalog, self.eigene)
        self.assertEqual(len(zusammen), vorher + 1)
        self.assertEqual(len(self.katalog), vorher, "der amtliche Katalog wurde veraendert")
        self.assertNotIn("A1800", self.katalog)
        self.assertIn("A1800", zusammen)

    def test_eigene_ziffern_stehen_in_der_suche_vorn(self):
        self.eigene.anlegen(self.katalog, "Stosswellentherapie", "1800")
        zusammen = katalog_mit_eigenen(self.katalog, self.eigene)
        treffer = zusammen.suche("stosswellen")
        self.assertEqual(treffer[0].nummer, "A1800")

    def test_rechnungsvermerk_nach_paragraf_12(self):
        neu = self.eigene.anlegen(self.katalog, "Stosswellentherapie", "1800")
        position = Position.aus_leistung(neu)
        self.assertEqual(position.analogvermerk, "entsprechend Nr. 1800 GOAE")
        self.assertEqual(position.leistungstext,
                         "Stosswellentherapie, entsprechend Nr. 1800 GOAE")

    def test_analogziffer_uebersteht_das_speichern_eines_angebots(self):
        neu = self.eigene.anlegen(self.katalog, "Stosswellentherapie", "1800")
        angebot = Angebot(name="Privat")
        angebot.hinzufuegen(Position.aus_leistung(neu))
        kopie = Angebot.from_dict(angebot.to_dict())
        self.assertEqual(kopie.positionen[0].analog_zu, "1800")
        self.assertEqual(kopie.positionen[0].leistungstext, angebot.positionen[0].leistungstext)

    def test_datei_der_eigenen_ziffern_stoert_die_angebotsliste_nicht(self):
        verzeichnis = Angebotsverzeichnis(self.ordner.name)
        angebot = Angebot(name="Ein Angebot")
        angebot.hinzufuegen(Position.aus_leistung(self.katalog.hole("1")))
        verzeichnis.speichern(angebot)
        self.eigene.anlegen(self.katalog, "Stosswellentherapie", "1800")
        self.assertEqual(verzeichnis.namen(), ["Ein Angebot"])

    def test_excel_traegt_den_analogvermerk(self):
        neu = self.eigene.anlegen(self.katalog, "Stosswellentherapie", "1800")
        angebot = Angebot(name="Privat")
        angebot.hinzufuegen(Position.aus_leistung(neu))
        pfad = exportiere(angebot, Path(self.ordner.name) / "analog.xlsx")
        with zipfile.ZipFile(pfad) as archiv:
            blatt = archiv.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("entsprechend Nr. 1800 GOAE", blatt)


class TestFarbschema(unittest.TestCase):
    """Ein Farbschema, drei Fassungen - sie duerfen nicht auseinanderlaufen."""

    WURZEL = Path(__file__).resolve().parent.parent

    def test_palette_stimmt_in_python_und_javascript_ueberein(self):
        aus_python = {
            name: wert for name, wert in vars(farben).items()
            if name.isupper() and isinstance(wert, str)
        }
        quelle = (self.WURZEL / "app" / "js" / "farben.js").read_text(encoding="utf-8")
        aus_js = dict(re.findall(r"export const ([A-Z_]+) = '(#[0-9A-Fa-f]{6})'", quelle))
        self.assertEqual(aus_python, aus_js,
                         "farben.py und app/js/farben.js weichen voneinander ab")

    def test_stylesheet_der_app_verwendet_dieselben_farben(self):
        quelle = (self.WURZEL / "app" / "js" / "xlsx.js").read_text(encoding="utf-8")
        # Im Vorlagentext stehen Platzhalter; gepruefte Groesse sind die
        # verwendeten Farbnamen, nicht die eingesetzten Werte.
        verwendet = set(re.findall(r"\$\{exf\(([A-Z_]+)\)\}", quelle))
        erwartet = set(re.findall(r"farben\.excel\(farben\.([A-Z_]+)\)",
                                  (self.WURZEL / "goae_kalkulator" / "excel.py").read_text(encoding="utf-8")))
        self.assertEqual(verwendet, erwartet,
                         "Die Excel-Ausgaben von Programm und App nutzen verschiedene Farben")

    @staticmethod
    def _variablen(css: str, ab: int) -> dict[str, str]:
        """Liest die Variablen des Blocks, der bei `ab` beginnt."""
        block = css[ab:css.index("}", ab)]
        return {n: w.upper() for n, w in re.findall(r"--([a-z0-9-]+): (#[0-9a-fA-F]{6});", block)}

    def test_helles_erscheinungsbild_nutzt_die_palette(self):
        css = (self.WURZEL / "app" / "app.css").read_text(encoding="utf-8")
        hell = self._variablen(css, css.index(":root {"))
        for name, wert in [("marke", farben.GRUEN), ("marke-stark", farben.GRUEN_STARK),
                           ("text-leise", farben.GRAU), ("text", farben.TEXT),
                           ("warnung", farben.WARNUNG), ("fehler", farben.FEHLER),
                           ("gut", farben.GUT)]:
            self.assertEqual(hell.get(name), wert.upper(),
                             f"--{name} im hellen Erscheinungsbild passt nicht zur Palette")

    def test_dunkles_erscheinungsbild_dreht_den_markenton(self):
        """Auf dunklem Grund traegt das Hellgruen des Strangs, nicht das Flaechengruen."""
        css = (self.WURZEL / "app" / "app.css").read_text(encoding="utf-8")
        dunkel = self._variablen(css, css.index("prefers-color-scheme: dark"))
        self.assertEqual(dunkel.get("marke"), farben.HELLGRUEN.upper())

    def test_excel_schreibweise(self):
        self.assertEqual(farben.excel("#6C7569"), "FF6C7569")
        self.assertEqual(farben.excel("6c7569"), "FF6C7569")

    def test_erzeugte_tabelle_traegt_die_praxisfarben(self):
        angebot = Angebot(name="Farbprobe")
        angebot.hinzufuegen(Position.aus_leistung(leistung()))
        with tempfile.TemporaryDirectory() as ordner:
            pfad = exportiere(angebot, Path(ordner) / "farbe.xlsx")
            with zipfile.ZipFile(pfad) as archiv:
                stile = archiv.read("xl/styles.xml").decode()
        self.assertIn(farben.excel(farben.GRUEN), stile)
        self.assertIn(farben.excel(farben.GRUEN_TON), stile)
        self.assertNotIn("FF1F4E79", stile, "alter Blauton noch enthalten")


class TestAngaben(unittest.TestCase):
    """Urheberrecht und Impressum - in Programm und App wortgleich."""

    WURZEL = Path(__file__).resolve().parent.parent

    def test_impressum_stimmt_in_beiden_fassungen_ueberein(self):
        quelle = (self.WURZEL / "app" / "js" / "angaben.js").read_text(encoding="utf-8")
        aus_js = dict(re.findall(r"^  (\w+): '(.*?)',$", quelle, re.M))
        aus_js["praxis"] = re.search(r"export const PRAXIS = '(.*?)'", quelle).group(1)
        self.assertEqual(angaben.IMPRESSUM, aus_js)
        self.assertEqual(angaben.COPYRIGHT,
                         re.search(r"export const COPYRIGHT = '(.*?)'", quelle).group(1))

    def test_urheberrechtsvermerk_steht_auf_der_tabelle(self):
        angebot = Angebot(name="Vermerk")
        angebot.hinzufuegen(Position.aus_leistung(leistung()))
        with tempfile.TemporaryDirectory() as ordner:
            pfad = exportiere(angebot, Path(ordner) / "vermerk.xlsx")
            with zipfile.ZipFile(pfad) as archiv:
                blatt = archiv.read("xl/worksheets/sheet1.xml").decode()
        self.assertIn("Raimar Lorrmann", blatt)
        self.assertIn(angaben.IMPRESSUM["praxis"], blatt)


class TestKommandozeile(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()

    def tearDown(self):
        self.ordner.cleanup()

    def test_zifferangaben(self):
        self.assertEqual(zerlege_ziffer("3"), ("3", 1, None))
        self.assertEqual(zerlege_ziffer("3x2"), ("3", 2, None))
        self.assertEqual(zerlege_ziffer("410x2@2,5"), ("410", 2, Decimal("2.5")))
        self.assertEqual(zerlege_ziffer(" A619 "), ("A619", 1, None))
        # Frei benannte Analogziffern
        self.assertEqual(zerlege_ziffer("A-AKU"), ("A-AKU", 1, None))
        self.assertEqual(zerlege_ziffer("A-AKUx2@2,5"), ("A-AKU", 2, Decimal("2.5")))
        self.assertEqual(zerlege_ziffer("K 2"), ("K 2", 1, None))
        for falsch in ("", "A/B;C", "3@9", "3@0,5", "3@viel"):
            with self.assertRaises(Abbruch, msg=falsch):
                zerlege_ziffer(falsch)

    def test_betragseingaben(self):
        self.assertEqual(betrag("250"), Decimal("250.00"))
        self.assertEqual(betrag("250,50"), Decimal("250.50"))
        self.assertEqual(betrag("1.234,50"), Decimal("1234.50"))
        self.assertEqual(betrag("1234.50 EUR"), Decimal("1234.50"))
        with self.assertRaises(Abbruch):
            betrag("viel")

    def _lauf(self, *argumente):
        """Ruft die Kommandozeile auf und unterdrueckt dabei ihre Ausgabe."""
        puffer = io.StringIO()
        with contextlib.redirect_stdout(puffer), contextlib.redirect_stderr(puffer):
            return main(["--verzeichnis", self.ordner.name, *argumente])

    def test_ablauf_anlegen_ziel_export(self):
        self.assertEqual(self._lauf("neu", "Paket", "-z", "1", "-z", "8", "-z", "410x2"), 0)
        self.assertEqual(self._lauf("liste"), 0)
        self.assertEqual(self._lauf("zeige", "Paket"), 0)
        self.assertEqual(self._lauf("ziel", "Paket", "120,00", "--centgenau"), 0)
        verzeichnis = Angebotsverzeichnis(self.ordner.name)
        self.assertEqual(verzeichnis.laden("Paket").summe, Decimal("120.00"))
        self.assertEqual(self._lauf("excel", "Paket"), 0)
        self.assertTrue((Path(self.ordner.name) / "Paket.xlsx").exists())

    def test_bearbeiten(self):
        self._lauf("neu", "Paket", "-z", "1")
        self.assertEqual(self._lauf("bearbeiten", "Paket", "-z", "8", "--faktor", "1=3,0"), 0)
        angebot = Angebotsverzeichnis(self.ordner.name).laden("Paket")
        self.assertEqual(len(angebot.positionen), 2)
        self.assertEqual(angebot.positionen[0].faktor, Decimal("3.0"))
        self.assertEqual(self._lauf("bearbeiten", "Paket", "--entferne", "8"), 0)
        self.assertEqual(len(Angebotsverzeichnis(self.ordner.name).laden("Paket").positionen), 1)

    def test_doppelter_name_wird_abgelehnt(self):
        self._lauf("neu", "Paket", "-z", "1")
        self.assertEqual(self._lauf("neu", "Paket", "-z", "3"), 2)
        self.assertEqual(self._lauf("neu", "Paket", "-z", "3", "--ueberschreiben"), 0)

    def test_unbekannte_ziffer_meldet_fehler(self):
        self.assertEqual(self._lauf("neu", "Paket", "-z", "99999"), 2)

    def test_loeschen(self):
        self._lauf("neu", "Paket", "-z", "1")
        self.assertEqual(self._lauf("loeschen", "Paket"), 0)
        self.assertEqual(self._lauf("loeschen", "Paket"), 2)

    def test_katalog_import(self):
        quelle = Path(self.ordner.name) / "eigene.csv"
        quelle.write_text("nummer;bezeichnung;punktzahl\n9001;Eigene Leistung;400\n",
                          encoding="utf-8")
        ziel = Path(self.ordner.name) / "katalog.csv"
        self.assertEqual(self._lauf("katalog-import", str(quelle), "--ziel", str(ziel)), 0)
        self.assertIn("9001", Katalog.laden(ziel))

    def test_katalog_anzeige(self):
        self.assertEqual(self._lauf("katalog", "beratung"), 0)
        self.assertEqual(self._lauf("katalog", "gibtesnicht"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
