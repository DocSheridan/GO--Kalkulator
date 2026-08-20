"""Fenster-Oberflaeche des GOAE-Abrechnungskalkulators (tkinter)."""

from __future__ import annotations

import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

try:
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
except ImportError:  # pragma: no cover - nur ohne installiertes tkinter
    tk = None

from . import farben
from .cli import betrag
from .excel import exportiere
from .katalog import Katalog, KatalogFehler
from .modelle import (
    FAKTOR_SCHRITT, MAX_FAKTOR, MIN_FAKTOR, Angebot, Position, faktor_text, geld,
)
from .speicher import Angebotsverzeichnis, SpeicherFehler, dateiname
from .zielbetrag import STRATEGIEN, optimiere_faktoren

STRATEGIE_TEXT = {
    "proportional": "Proportional - vorhandene Faktoren skalieren",
    "einheitlich": "Einheitlich - ein Faktor fuer alle Ziffern",
    "regelsatz": "Regelsatzbezogen - Vielfaches des Regelsatzes",
}
TEXT_STRATEGIE = {v: k for k, v in STRATEGIE_TEXT.items()}

# (Schluessel, Ueberschrift, Breite, Ausrichtung, mitwachsend)
KATALOG_SPALTEN = (
    ("nummer", "Ziffer", 56, "w", False),
    ("bezeichnung", "Leistung", 220, "w", True),
    ("punkte", "Punkte", 60, "e", False),
    ("e1", "1,0-fach", 72, "e", False),
    ("e23", "2,3-fach", 72, "e", False),
    ("e35", "3,5-fach", 72, "e", False),
    ("klasse", "Abschn./Klasse", 108, "w", False),
)
POSITION_SPALTEN = (
    ("nummer", "Ziffer", 56, "w", False),
    ("bezeichnung", "Leistung", 210, "w", True),
    ("anzahl", "Anz.", 46, "e", False),
    ("e1", "1,0-fach", 72, "e", False),
    ("e23", "2,3-fach", 72, "e", False),
    ("e35", "3,5-fach", 72, "e", False),
    ("faktor", "Faktor", 68, "e", False),
    ("betrag", "Betrag", 84, "e", False),
    ("hinweis", "Begruendung / Hinweis", 170, "w", True),
)


class Anwendung(tk.Tk):
    """Hauptfenster: Katalog links, Angebot rechts, Kalkulation unten."""

    def __init__(self, katalog: Katalog, verzeichnis: Angebotsverzeichnis):
        super().__init__()
        self.katalog = katalog
        self.verzeichnis = verzeichnis
        self.angebot = Angebot(name="Neues Angebot")
        self.veraendert = False
        self._bearbeitung: tk.Entry | None = None

        self.title("GOAE-Abrechnungskalkulator")
        self.geometry("1380x840")
        self.minsize(1040, 700)
        self.protocol("WM_DELETE_WINDOW", self.beenden)

        self.var_status = tk.StringVar(value=f"{len(self.katalog)} GOAE-Ziffern geladen.")
        self.var_name = tk.StringVar(value=self.angebot.name)
        self.var_patient = tk.StringVar()
        self.var_beschreibung = tk.StringVar()
        self.var_suche = tk.StringVar()
        self.var_anzahl = tk.StringVar(value="1")
        self.var_startfaktor = tk.StringVar(value="Regelsatz")
        self.var_ziel = tk.StringVar()
        self.var_strategie = tk.StringVar(value=STRATEGIE_TEXT["proportional"])
        self.var_rechtlich = tk.BooleanVar(value=False)
        self.var_raster = tk.StringVar(value="0,1")
        self.var_centgenau = tk.BooleanVar(value=False)
        self.var_spanne = tk.StringVar(value="")
        self.summen = {s: tk.StringVar(value="0,00 EUR") for s in ("e1", "e23", "e35", "ist", "ziel")}

        self._menue()
        self._aufbau()
        self._fuelle_katalog()
        self._aktualisiere()

    # -- Aufbau -----------------------------------------------------------
    def _menue(self) -> None:
        leiste = tk.Menu(self)
        datei = tk.Menu(leiste, tearoff=0)
        datei.add_command(label="Neues Angebot", accelerator="Strg+N", command=self.neu)
        datei.add_command(label="Angebot oeffnen...", accelerator="Strg+O", command=self.oeffnen)
        datei.add_command(label="Speichern", accelerator="Strg+S", command=self.speichern)
        datei.add_command(label="Speichern unter...", command=self.speichern_unter)
        datei.add_separator()
        datei.add_command(label="Nach Excel exportieren...", accelerator="Strg+E",
                          command=self.excel_export)
        datei.add_command(label="Alle Angebote nach Excel...", command=self.excel_export_alle)
        datei.add_separator()
        datei.add_command(label="Ablageordner oeffnen", command=self.zeige_ordner)
        datei.add_command(label="Beenden", command=self.beenden)
        leiste.add_cascade(label="Datei", menu=datei)

        katalog = tk.Menu(leiste, tearoff=0)
        katalog.add_command(label="Katalogdatei laden...", command=self.katalog_laden)
        katalog.add_command(label="Ziffern aus CSV ergaenzen...", command=self.katalog_ergaenzen)
        leiste.add_cascade(label="Katalog", menu=katalog)

        hilfe = tk.Menu(leiste, tearoff=0)
        hilfe.add_command(label="Kurzanleitung", command=self.hilfe)
        leiste.add_cascade(label="Hilfe", menu=hilfe)
        self.config(menu=leiste)

        self.bind("<Control-n>", lambda _e: self.neu())
        self.bind("<Control-o>", lambda _e: self.oeffnen())
        self.bind("<Control-s>", lambda _e: self.speichern())
        self.bind("<Control-e>", lambda _e: self.excel_export())

    def _aufbau(self) -> None:
        stil = ttk.Style(self)
        try:
            stil.theme_use("clam")
        except tk.TclError:
            pass
        # Farben der Praxis - dieselbe Palette wie Excel-Ausgabe und App.
        stil.configure("Summe.TLabel", font=("TkDefaultFont", 11, "bold"),
                       foreground=farben.GRAU)
        stil.configure("Gross.TLabel", font=("TkDefaultFont", 14, "bold"),
                       foreground=farben.GRUEN)
        # Von "clam" ignoriert, greift aber auf Themen, die es beachten.
        stil.configure("TLabelframe.Label", foreground=farben.GRUEN)
        stil.configure("Treeview.Heading", background=farben.GRUEN,
                       foreground=farben.WEISS)
        stil.map("Treeview.Heading", background=[("active", farben.GRUEN_STARK)])
        stil.map("Treeview",
                 background=[("selected", farben.GRUEN)],
                 foreground=[("selected", farben.WEISS)])

        # -- Kopfbereich: Angebotsdaten
        kopf = ttk.LabelFrame(self, text="Angebot")
        kopf.pack(fill="x", padx=8, pady=(8, 4))
        ttk.Label(kopf, text="Name").grid(row=0, column=0, sticky="w", padx=(6, 2), pady=6)
        ttk.Entry(kopf, textvariable=self.var_name, width=26).grid(
            row=0, column=1, sticky="ew", padx=(0, 12), pady=6)
        ttk.Label(kopf, text="Patient/in").grid(row=0, column=2, sticky="w", padx=(0, 2))
        ttk.Entry(kopf, textvariable=self.var_patient, width=18).grid(
            row=0, column=3, sticky="ew", padx=(0, 12))
        ttk.Label(kopf, text="Beschreibung").grid(row=0, column=4, sticky="w", padx=(0, 2))
        ttk.Entry(kopf, textvariable=self.var_beschreibung, width=24).grid(
            row=0, column=5, sticky="ew", padx=(0, 12))
        # Die Eingabefelder teilen sich den freien Platz, die Knoepfe bleiben rechts.
        kopf.columnconfigure(1, weight=3)
        kopf.columnconfigure(3, weight=2)
        kopf.columnconfigure(5, weight=4)
        knoepfe = ttk.Frame(kopf)
        knoepfe.grid(row=1, column=0, columnspan=6, sticky="e", padx=6, pady=(0, 6))
        ttk.Button(knoepfe, text="Neu", command=self.neu).pack(side="left", padx=2)
        ttk.Button(knoepfe, text="Oeffnen", command=self.oeffnen).pack(side="left", padx=2)
        ttk.Button(knoepfe, text="Speichern", command=self.speichern).pack(side="left", padx=2)
        ttk.Button(knoepfe, text="Excel", command=self.excel_export).pack(side="left", padx=2)
        for var in (self.var_name, self.var_patient, self.var_beschreibung):
            var.trace_add("write", lambda *_a: self._markiere_veraendert())

        # -- Mitte: Katalog | Positionen
        mitte = ttk.PanedWindow(self, orient="horizontal")
        mitte.pack(fill="both", expand=True, padx=8, pady=4)
        mitte.add(self._katalog_bereich(mitte), weight=2)
        mitte.add(self._positions_bereich(mitte), weight=3)
        # Anfangsteilung setzen, sobald die Fenstergroesse feststeht.
        self.after(80, lambda: self._teile(mitte))

        # -- Fuss: Statuszeile ganz unten, darueber Summen und Zielbetrag.
        # Bei side="bottom" landet das zuerst gepackte Element ganz unten.
        ttk.Label(self, textvariable=self.var_status, relief="sunken", anchor="w",
                  padding=(6, 2)).pack(fill="x", side="bottom")
        self._summen_bereich()

    @staticmethod
    def _tabelle(eltern, spalten, **einstellungen) -> tuple[ttk.Frame, "ttk.Treeview"]:
        """Treeview mit senkrechtem und waagerechtem Rollbalken.

        Ohne den waagerechten Rollbalken sind die rechten Spalten (Faktor,
        Betrag) in einem schmalen Fenster weder sichtbar noch erreichbar.
        """
        rahmen = ttk.Frame(eltern)
        baum = ttk.Treeview(rahmen, columns=[s[0] for s in spalten], show="headings",
                            **einstellungen)
        senkrecht = ttk.Scrollbar(rahmen, orient="vertical", command=baum.yview)
        waagerecht = ttk.Scrollbar(rahmen, orient="horizontal", command=baum.xview)
        baum.configure(yscrollcommand=senkrecht.set, xscrollcommand=waagerecht.set)
        baum.grid(row=0, column=0, sticky="nsew")
        senkrecht.grid(row=0, column=1, sticky="ns")
        waagerecht.grid(row=1, column=0, sticky="ew")
        rahmen.rowconfigure(0, weight=1)
        rahmen.columnconfigure(0, weight=1)
        for schluessel, titel, breite, anker, waechst in spalten:
            baum.heading(schluessel, text=titel, anchor=anker)
            baum.column(schluessel, width=breite, minwidth=40, anchor=anker, stretch=waechst)
        return rahmen, baum

    def _katalog_bereich(self, eltern) -> ttk.Frame:
        rahmen = ttk.LabelFrame(eltern, text="GOAE-Katalog")
        suchzeile = ttk.Frame(rahmen)
        suchzeile.pack(fill="x", padx=6, pady=6)
        ttk.Label(suchzeile, text="Suche").pack(side="left")
        eingabe = ttk.Entry(suchzeile, textvariable=self.var_suche)
        eingabe.pack(side="left", fill="x", expand=True, padx=6)
        eingabe.bind("<KeyRelease>", lambda _e: self._fuelle_katalog())
        ttk.Button(suchzeile, text="Zuruecksetzen",
                   command=lambda: (self.var_suche.set(""), self._fuelle_katalog())).pack(side="left")

        fuss = ttk.Frame(rahmen)
        fuss.pack(side="bottom", fill="x", padx=6, pady=6)

        tabelle, self.baum_katalog = self._tabelle(rahmen, KATALOG_SPALTEN,
                                                  selectmode="extended")
        tabelle.pack(side="top", fill="both", expand=True, padx=6, pady=(0, 4))
        self.baum_katalog.bind("<Double-1>", lambda _e: self.uebernehmen())
        self.baum_katalog.bind("<Return>", lambda _e: self.uebernehmen())
        ttk.Label(fuss, text="Anzahl").pack(side="left")
        ttk.Spinbox(fuss, from_=1, to=99, width=4, textvariable=self.var_anzahl).pack(
            side="left", padx=(4, 10))
        ttk.Label(fuss, text="Faktor").pack(side="left")
        ttk.Combobox(fuss, textvariable=self.var_startfaktor, width=10, state="readonly",
                     values=("Regelsatz", "1,0", "2,3", "3,5")).pack(side="left", padx=4)
        ttk.Button(fuss, text="In das Angebot uebernehmen", command=self.uebernehmen).pack(
            side="right")
        return rahmen

    def _positions_bereich(self, eltern) -> ttk.Frame:
        rahmen = ttk.LabelFrame(eltern, text="Positionen des Angebots")
        # Werkzeugleiste zuerst anlegen, damit sie bei wenig Platz erhalten
        # bleibt und stattdessen die Tabelle schrumpft.
        werkzeuge = ttk.Frame(rahmen)
        werkzeuge.pack(side="bottom", fill="x", padx=6, pady=(0, 6))
        zeile1 = ttk.Frame(werkzeuge)
        zeile1.pack(fill="x")
        ttk.Button(zeile1, text="Entfernen", command=self.entfernen).pack(side="left", padx=2)
        ttk.Button(zeile1, text="Faktor...", command=self.faktor_setzen).pack(side="left", padx=2)
        ttk.Button(zeile1, text="Anzahl...", command=self.anzahl_setzen).pack(side="left", padx=2)
        ttk.Button(zeile1, text="Begruendung...", command=self.begruendung_setzen).pack(
            side="left", padx=2)
        ttk.Button(zeile1, text="Fixieren / Freigeben", command=self.fixieren).pack(
            side="left", padx=2)
        zeile2 = ttk.Frame(werkzeuge)
        zeile2.pack(fill="x", pady=(4, 0))
        ttk.Label(zeile2, text="Alle Faktoren auf").pack(side="left", padx=(2, 4))
        for wert in ("1,0", "2,3", "3,5"):
            ttk.Button(zeile2, text=wert, width=5,
                       command=lambda w=wert: self.alle_faktoren(w)).pack(side="left", padx=1)
        ttk.Label(zeile2, text="Doppelklick auf Faktor oder Anzahl bearbeitet die Zelle").pack(
            side="right", padx=2)

        tabelle, self.baum_positionen = self._tabelle(rahmen, POSITION_SPALTEN,
                                                     selectmode="browse")
        tabelle.pack(side="top", fill="both", expand=True, padx=6, pady=(6, 4))
        self.baum_positionen.tag_configure("warnung", foreground=farben.WARNUNG)
        self.baum_positionen.tag_configure("fehler", foreground=farben.FEHLER)
        self.baum_positionen.tag_configure("fixiert", background=farben.GRUEN_TON)
        self.baum_positionen.bind("<Double-1>", self._zelle_bearbeiten)
        self.baum_positionen.bind("<Delete>", lambda _e: self.entfernen())
        return rahmen

    def _summen_bereich(self) -> None:
        rahmen = ttk.Frame(self)
        rahmen.pack(fill="x", padx=8, pady=(0, 8), side="bottom")

        summen = ttk.LabelFrame(rahmen, text="Summen")
        summen.pack(side="left", fill="y", expand=False, padx=(0, 6))
        for spalte, (schluessel, titel) in enumerate(
            (("e1", "einfacher Satz"), ("e23", "2,3-facher Satz"),
             ("e35", "3,5-facher Satz"), ("ist", "kalkuliert"))
        ):
            ttk.Label(summen, text=titel).grid(row=0, column=spalte, padx=14, pady=(6, 0))
            ttk.Label(summen, textvariable=self.summen[schluessel],
                      style="Gross.TLabel" if schluessel == "ist" else "Summe.TLabel").grid(
                row=1, column=spalte, padx=12, pady=(0, 8))

        ziel = ttk.LabelFrame(rahmen, text="Gesamtpreis vorgeben - Faktoren automatisch verteilen")
        ziel.pack(side="left", fill="both", expand=True)

        ttk.Label(ziel, text="Zielbetrag EUR").grid(row=0, column=0, sticky="w", padx=6, pady=(6, 2))
        eingabe = ttk.Entry(ziel, textvariable=self.var_ziel, width=12)
        eingabe.grid(row=0, column=1, sticky="w", padx=4, pady=(6, 2))
        eingabe.bind("<Return>", lambda _e: self.verteile())
        ttk.Button(ziel, text="Faktoren verteilen", command=self.verteile).grid(
            row=0, column=2, sticky="e", padx=6, pady=(6, 2))

        # Eigene Zeile: sonst wird die Auswahlliste in schmalen Fenstern
        # bis zur Unlesbarkeit zusammengedrueckt.
        ttk.Label(ziel, text="Verteilung").grid(row=1, column=0, sticky="w", padx=6)
        ttk.Combobox(ziel, textvariable=self.var_strategie, state="readonly",
                     values=[STRATEGIE_TEXT[s] for s in STRATEGIEN]).grid(
            row=1, column=1, columnspan=2, sticky="ew", padx=4, pady=2)

        stufung = ttk.Frame(ziel)
        stufung.grid(row=2, column=0, columnspan=3, sticky="w", padx=6)
        ttk.Label(stufung, text="Faktorstufung").pack(side="left")
        ttk.Combobox(stufung, textvariable=self.var_raster, state="readonly", width=6,
                     values=("0,1", "0,05", "0,01")).pack(side="left", padx=(4, 12))
        ttk.Checkbutton(
            stufung, variable=self.var_centgenau,
            text="Betrag centgenau treffen").pack(side="left")
        ttk.Checkbutton(
            ziel, variable=self.var_rechtlich,
            text="Hoechstsaetze der Steigerungsklassen beachten (Labor 1,3 / technisch 2,5)",
        ).grid(row=3, column=0, columnspan=3, sticky="w", padx=6)
        ttk.Label(ziel, textvariable=self.var_spanne, wraplength=520, justify="left").grid(
            row=4, column=0, columnspan=3, sticky="w", padx=6, pady=(2, 6))
        ziel.columnconfigure(2, weight=1)

    def _teile(self, geteilt) -> None:
        """Trennlinie so setzen, dass die Positionstabelle vollstaendig sichtbar ist."""
        try:
            breite = geteilt.winfo_width()
            if breite > 400:
                geteilt.sashpos(0, max(340, breite - 800))
        except tk.TclError:
            pass

    # -- Darstellung ------------------------------------------------------
    def _fuelle_katalog(self) -> None:
        self.baum_katalog.delete(*self.baum_katalog.get_children())
        for leistung in self.katalog.suche(self.var_suche.get()):
            self.baum_katalog.insert(
                "", "end", iid=leistung.nummer,
                values=(leistung.nummer, leistung.bezeichnung, leistung.punktzahl,
                        geld(leistung.einfachsatz), geld(leistung.satz_2_3),
                        geld(leistung.satz_3_5),
                        f"{leistung.abschnitt} / {leistung.klasse}"
                        + (" *" if leistung.herkunft == "gruppe" else "")),
            )

    def _aktualisiere(self) -> None:
        auswahl = self.baum_positionen.selection()
        self.baum_positionen.delete(*self.baum_positionen.get_children())
        for i, p in enumerate(self.angebot.positionen):
            marken = []
            if p.ueber_hoechstsatz:
                marken.append("fehler")
            elif p.ueber_regelsatz and not p.begruendung:
                marken.append("warnung")
            if p.fixiert:
                marken.append("fixiert")
            self.baum_positionen.insert(
                "", "end", iid=str(i),
                values=(p.nummer, p.bezeichnung, p.anzahl,
                        geld(p.einfachsatz), geld(p.satz_2_3), geld(p.satz_3_5),
                        faktor_text(p.faktor) + (" *" if p.fixiert else ""),
                        geld(p.betrag), p.begruendung or p.hinweis()),
                tags=tuple(marken),
            )
        for iid in auswahl:
            if self.baum_positionen.exists(iid):
                self.baum_positionen.selection_set(iid)

        self.summen["e1"].set(f"{geld(self.angebot.summe_einfach)} EUR")
        self.summen["e23"].set(f"{geld(self.angebot.summe_2_3)} EUR")
        self.summen["e35"].set(f"{geld(self.angebot.summe_3_5)} EUR")
        self.summen["ist"].set(f"{geld(self.angebot.summe)} EUR")
        if self.angebot.positionen:
            unten, oben = self.angebot.spanne()
            text = (f"Durch Faktorwahl erreichbar: {geld(unten)} bis {geld(oben)} EUR "
                    f"(Faktoren {MIN_FAKTOR} bis {MAX_FAKTOR})")
            if self.angebot.zielbetrag is not None:
                abweichung = self.angebot.summe - self.angebot.zielbetrag
                text += (f"\nZiel {geld(self.angebot.zielbetrag)} EUR, "
                         f"Abweichung {geld(abweichung)} EUR")
            self.var_spanne.set(text)
        else:
            self.var_spanne.set("Bitte zuerst Ziffern aus dem Katalog uebernehmen.")
        titel = f"GOAE-Abrechnungskalkulator - {self.angebot.name}"
        self.title(titel + (" *" if self.veraendert else ""))

    def _markiere_veraendert(self) -> None:
        self.angebot.name = self.var_name.get()
        self.angebot.patient = self.var_patient.get()
        self.angebot.beschreibung = self.var_beschreibung.get()
        self.veraendert = True
        self.title(f"GOAE-Abrechnungskalkulator - {self.angebot.name} *")

    def _melde(self, text: str) -> None:
        self.var_status.set(text)

    def _gewaehlte_position(self) -> Position | None:
        auswahl = self.baum_positionen.selection()
        if not auswahl:
            self._melde("Bitte zuerst eine Position in der Liste auswaehlen.")
            return None
        return self.angebot.positionen[int(auswahl[0])]

    # -- Positionen -------------------------------------------------------
    def uebernehmen(self) -> None:
        auswahl = self.baum_katalog.selection()
        if not auswahl:
            self._melde("Bitte im Katalog eine Ziffer auswaehlen.")
            return
        try:
            anzahl = max(1, int(self.var_anzahl.get()))
        except ValueError:
            anzahl = 1
        wahl = self.var_startfaktor.get()
        faktorwert = None if wahl == "Regelsatz" else Decimal(wahl.replace(",", "."))
        for nummer in auswahl:
            leistung = self.katalog.hole(nummer)
            self.angebot.hinzufuegen(
                Position.aus_leistung(leistung, anzahl=anzahl, faktorwert=faktorwert))
        self.veraendert = True
        self._aktualisiere()
        self._melde(f"{len(auswahl)} Ziffer(n) uebernommen.")

    def entfernen(self) -> None:
        position = self._gewaehlte_position()
        if position is None:
            return
        self.angebot.positionen.remove(position)
        self.veraendert = True
        self._aktualisiere()
        self._melde(f"Ziffer {position.nummer} entfernt.")

    def fixieren(self) -> None:
        position = self._gewaehlte_position()
        if position is None:
            return
        position.fixiert = not position.fixiert
        self.veraendert = True
        self._aktualisiere()
        self._melde(
            f"Ziffer {position.nummer} " +
            ("wird bei der Zielbetragsrechnung nicht mehr veraendert."
             if position.fixiert else "wird wieder mit angepasst.")
        )

    def faktor_setzen(self) -> None:
        position = self._gewaehlte_position()
        if position is None:
            return
        wert = self._frage_wert(
            "Faktor", f"Faktor fuer Ziffer {position.nummer}\n"
            f"(zulaessig {MIN_FAKTOR} bis {MAX_FAKTOR}, Regelsatz {faktor_text(position.regelsatz)})",
            faktor_text(position.faktor))
        if wert is None:
            return
        self._setze_faktor(position, wert)

    def anzahl_setzen(self) -> None:
        position = self._gewaehlte_position()
        if position is None:
            return
        wert = self._frage_wert("Anzahl", f"Anzahl fuer Ziffer {position.nummer}",
                                str(position.anzahl))
        if wert is None:
            return
        self._setze_anzahl(position, wert)

    def begruendung_setzen(self) -> None:
        position = self._gewaehlte_position()
        if position is None:
            return
        wert = self._frage_wert(
            "Begruendung",
            f"Begruendung nach § 12 GOAE fuer Ziffer {position.nummer}", position.begruendung)
        if wert is None:
            return
        position.begruendung = wert
        self.veraendert = True
        self._aktualisiere()

    def alle_faktoren(self, wert: str) -> None:
        if not self.angebot.positionen:
            return
        faktorwert = Decimal(wert.replace(",", "."))
        geaendert = 0
        for p in self.angebot.positionen:
            if not p.fixiert:
                p.faktor = faktorwert
                geaendert += 1
        self.veraendert = True
        self._aktualisiere()
        self._melde(f"{geaendert} Position(en) auf Faktor {wert} gesetzt "
                    f"(fixierte Positionen blieben unveraendert).")

    def _setze_faktor(self, position: Position, text: str) -> None:
        try:
            neu = Decimal(text.replace(",", "."))
        except InvalidOperation:
            messagebox.showerror("Ungueltige Eingabe", f"{text!r} ist keine Zahl.", parent=self)
            return
        if not (MIN_FAKTOR <= neu <= MAX_FAKTOR):
            messagebox.showerror(
                "Faktor ausserhalb der Spanne",
                f"Der Faktor muss zwischen {MIN_FAKTOR} und {MAX_FAKTOR} liegen.", parent=self)
            return
        position.faktor = neu
        self.veraendert = True
        self._aktualisiere()
        self._melde(f"Ziffer {position.nummer}: Faktor {faktor_text(position.faktor)} "
                    f"= {geld(position.betrag)} EUR")

    def _setze_anzahl(self, position: Position, text: str) -> None:
        if not text.strip().isdigit() or int(text) < 1:
            messagebox.showerror("Ungueltige Eingabe",
                                 "Die Anzahl muss eine ganze Zahl ab 1 sein.", parent=self)
            return
        position.anzahl = int(text)
        self.veraendert = True
        self._aktualisiere()

    def _frage_wert(self, titel: str, text: str, vorgabe: str) -> str | None:
        from tkinter import simpledialog
        return simpledialog.askstring(titel, text, initialvalue=vorgabe, parent=self)

    def _zelle_bearbeiten(self, ereignis) -> None:
        """Doppelklick auf Faktor oder Anzahl: Wert direkt in der Zelle aendern."""
        # identify_region meldet ausserhalb des sichtbaren Bereichs "nothing";
        # massgeblich sind Zeile und Spalte unter dem Mauszeiger.
        if self.baum_positionen.identify_region(ereignis.x, ereignis.y) == "heading":
            return
        zeile = self.baum_positionen.identify_row(ereignis.y)
        spalte = self.baum_positionen.identify_column(ereignis.x)
        if not zeile or not spalte:
            return
        namen = [s[0] for s in POSITION_SPALTEN]
        index = int(spalte[1:]) - 1
        if not (0 <= index < len(namen)):
            return
        position = self.angebot.positionen[int(zeile)]
        feld = namen[index]
        if feld not in ("faktor", "anzahl", "hinweis"):
            return
        if feld == "hinweis":
            self.baum_positionen.selection_set(zeile)
            self.begruendung_setzen()
            return

        kasten = self.baum_positionen.bbox(zeile, spalte)
        if not kasten:
            return
        x, y, breite, hoehe = kasten
        aktuell = faktor_text(position.faktor) if feld == "faktor" else str(position.anzahl)
        eingabe = tk.Entry(self.baum_positionen, justify="right")
        eingabe.insert(0, aktuell)
        eingabe.select_range(0, "end")
        eingabe.place(x=x, y=y, width=breite, height=hoehe)
        eingabe.focus_set()
        self._bearbeitung = eingabe

        def uebernehmen(_ereignis=None) -> None:
            text = eingabe.get()
            eingabe.destroy()
            self._bearbeitung = None
            if feld == "faktor":
                self._setze_faktor(position, text)
            else:
                self._setze_anzahl(position, text)

        def verwerfen(_ereignis=None) -> None:
            eingabe.destroy()
            self._bearbeitung = None

        eingabe.bind("<Return>", uebernehmen)
        eingabe.bind("<FocusOut>", uebernehmen)
        eingabe.bind("<Escape>", verwerfen)

    # -- Zielbetrag -------------------------------------------------------
    def verteile(self) -> None:
        if not self.angebot.positionen:
            messagebox.showinfo("Keine Positionen",
                                "Bitte zuerst Ziffern in das Angebot uebernehmen.", parent=self)
            return
        text = self.var_ziel.get().strip()
        if not text:
            messagebox.showinfo("Zielbetrag fehlt",
                                "Bitte den gewuenschten Gesamtpreis eintragen.", parent=self)
            return
        try:
            ziel = betrag(text)
        except Exception as fehler:
            messagebox.showerror("Ungueltiger Betrag", str(fehler), parent=self)
            return
        ergebnis = optimiere_faktoren(
            self.angebot.positionen, ziel,
            strategie=TEXT_STRATEGIE.get(self.var_strategie.get(), "proportional"),
            rechtliche_grenzen=self.var_rechtlich.get(),
            schrittweite=Decimal(self.var_raster.get().replace(",", ".")),
            nachjustieren=self.var_centgenau.get(),
        )
        self.angebot.zielbetrag = ziel
        self.veraendert = True
        self._aktualisiere()
        self._melde(f"{ergebnis.meldung} Summe {geld(ergebnis.summe)} EUR.")
        if not ergebnis.erreicht:
            messagebox.showwarning(
                "Zielbetrag nicht exakt erreichbar",
                f"{ergebnis.meldung}\n\n"
                f"Erreichbar sind {geld(ergebnis.min_summe)} bis {geld(ergebnis.max_summe)} EUR.\n"
                f"Errechnete Summe: {geld(ergebnis.summe)} EUR "
                f"(Abweichung {geld(ergebnis.abweichung)} EUR).\n\n"
                "Ein feineres Faktorraster oder das Haekchen "
                "\"Betrag centgenau treffen\" schliesst kleine Restbetraege.",
                parent=self)

    # -- Datei ------------------------------------------------------------
    def _darf_verwerfen(self) -> bool:
        if not self.veraendert:
            return True
        antwort = messagebox.askyesnocancel(
            "Aenderungen sichern?",
            f"Das Angebot {self.angebot.name!r} enthaelt ungesicherte Aenderungen.\n"
            "Sollen sie gespeichert werden?", parent=self)
        if antwort is None:
            return False
        if antwort:
            return self.speichern()
        return True

    def neu(self) -> None:
        if not self._darf_verwerfen():
            return
        self.angebot = Angebot(name="Neues Angebot")
        self.var_name.set(self.angebot.name)
        self.var_patient.set("")
        self.var_beschreibung.set("")
        self.var_ziel.set("")
        self.veraendert = False
        self._aktualisiere()
        self._melde("Neues Angebot angelegt.")

    def _uebernimm(self, angebot: Angebot) -> None:
        self.angebot = angebot
        self.var_name.set(angebot.name)
        self.var_patient.set(angebot.patient)
        self.var_beschreibung.set(angebot.beschreibung)
        self.var_ziel.set(str(angebot.zielbetrag) if angebot.zielbetrag is not None else "")
        self.veraendert = False
        self._aktualisiere()

    def oeffnen(self) -> None:
        if not self._darf_verwerfen():
            return
        eintraege = self.verzeichnis.liste()
        if not eintraege:
            messagebox.showinfo(
                "Verzeichnis leer",
                f"Unter {self.verzeichnis.pfad} ist noch kein Angebot gespeichert.", parent=self)
            return
        Auswahlfenster(self, eintraege)

    def lade_datei(self, pfad: Path) -> None:
        try:
            self._uebernimm(self.verzeichnis.laden_aus(pfad))
        except SpeicherFehler as fehler:
            messagebox.showerror("Angebot nicht lesbar", str(fehler), parent=self)
            return
        self._melde(f"Geladen: {self.angebot.name}")

    def speichern(self) -> bool:
        self.angebot.name = self.var_name.get().strip()
        self.angebot.patient = self.var_patient.get()
        self.angebot.beschreibung = self.var_beschreibung.get()
        if not self.angebot.name:
            messagebox.showerror("Name fehlt", "Bitte einen Namen fuer das Angebot vergeben.",
                                 parent=self)
            return False
        try:
            pfad = self.verzeichnis.speichern(self.angebot)
        except SpeicherFehler as fehler:
            messagebox.showerror("Speichern fehlgeschlagen", str(fehler), parent=self)
            return False
        self.veraendert = False
        self._aktualisiere()
        self._melde(f"Gespeichert: {pfad}")
        return True

    def speichern_unter(self) -> None:
        from tkinter import simpledialog
        name = simpledialog.askstring("Speichern unter", "Neuer Name des Angebots:",
                                      initialvalue=self.angebot.name, parent=self)
        if not name:
            return
        self.var_name.set(name)
        self.angebot.name = name
        self.speichern()

    def excel_export(self) -> None:
        if not self.angebot.positionen:
            messagebox.showinfo("Nichts zu exportieren",
                                "Das Angebot enthaelt keine Positionen.", parent=self)
            return
        ziel = filedialog.asksaveasfilename(
            parent=self, title="Angebot als Excel-Datei speichern", defaultextension=".xlsx",
            initialdir=str(self.verzeichnis.sicherstellen()),
            initialfile=f"{dateiname(self.angebot.name)}.xlsx",
            filetypes=[("Excel-Arbeitsmappe", "*.xlsx")])
        if not ziel:
            return
        pfad = exportiere(self.angebot, ziel)
        self._melde(f"Excel-Datei geschrieben: {pfad}")
        messagebox.showinfo("Export abgeschlossen", f"Die Datei wurde erstellt:\n{pfad}",
                            parent=self)

    def excel_export_alle(self) -> None:
        angebote = [self.verzeichnis.laden_aus(e["datei"]) for e in self.verzeichnis.liste()]
        if not angebote:
            messagebox.showinfo("Verzeichnis leer", "Es sind keine Angebote gespeichert.",
                                parent=self)
            return
        ziel = filedialog.asksaveasfilename(
            parent=self, title="Alle Angebote exportieren", defaultextension=".xlsx",
            initialdir=str(self.verzeichnis.sicherstellen()), initialfile="Angebote.xlsx",
            filetypes=[("Excel-Arbeitsmappe", "*.xlsx")])
        if not ziel:
            return
        pfad = exportiere(angebote, ziel)
        messagebox.showinfo("Export abgeschlossen",
                            f"{len(angebote)} Angebot(e) geschrieben:\n{pfad}", parent=self)

    def zeige_ordner(self) -> None:
        messagebox.showinfo(
            "Ablageordner",
            f"Die Angebote liegen als JSON-Dateien in:\n{self.verzeichnis.sicherstellen()}\n\n"
            "Der Ordner laesst sich ueber die Umgebungsvariable GOAE_ANGEBOTE aendern.",
            parent=self)

    # -- Katalog ----------------------------------------------------------
    def katalog_laden(self) -> None:
        pfad = filedialog.askopenfilename(parent=self, title="Katalogdatei waehlen",
                                          filetypes=[("CSV-Datei", "*.csv"), ("Alle Dateien", "*")])
        if not pfad:
            return
        try:
            self.katalog = Katalog.laden(pfad)
        except KatalogFehler as fehler:
            messagebox.showerror("Katalog nicht lesbar", str(fehler), parent=self)
            return
        self._fuelle_katalog()
        self._melde(f"Katalog geladen: {len(self.katalog)} Ziffern aus {pfad}")

    def katalog_ergaenzen(self) -> None:
        pfad = filedialog.askopenfilename(parent=self, title="Ziffern aus CSV ergaenzen",
                                          filetypes=[("CSV-Datei", "*.csv"), ("Alle Dateien", "*")])
        if not pfad:
            return
        try:
            self.katalog.ergaenzen(Katalog.laden(pfad))
        except KatalogFehler as fehler:
            messagebox.showerror("Katalog nicht lesbar", str(fehler), parent=self)
            return
        self._fuelle_katalog()
        self._melde(f"Katalog ergaenzt: jetzt {len(self.katalog)} Ziffern.")

    def hilfe(self) -> None:
        messagebox.showinfo(
            "Kurzanleitung",
            "1. Links im Katalog suchen, Ziffer auswaehlen und uebernehmen "
            "(Doppelklick genuegt).\n"
            "2. Rechts stehen je Ziffer der einfache, der 2,3-fache und der 3,5-fache Satz.\n"
            "3. Der Faktor laesst sich frei zwischen 1,0 und 3,5 waehlen - Doppelklick auf "
            "die Zelle.\n"
            "4. Alternativ unten den gewuenschten Gesamtpreis eintragen: die Faktoren werden "
            "automatisch so verteilt, dass die Summe erreicht wird - in Zehntelschritten, "
            "wie in der Abrechnung ueblich. Bleibt dabei ein Restbetrag von wenigen Cent, "
            "hilft eine feinere Stufung.\n"
            "5. Einzelne Positionen lassen sich fixieren; sie bleiben dann unveraendert.\n"
            "6. Speichern legt das Angebot im Ablageordner ab, Excel erzeugt eine "
            ".xlsx-Datei.\n\n"
            "Faktoren oberhalb des Regelsatzes sind nach § 12 GOAE schriftlich zu begruenden; "
            "solche Zeilen werden farblich hervorgehoben.",
            parent=self)

    def beenden(self) -> None:
        if self._darf_verwerfen():
            self.destroy()


class Auswahlfenster(tk.Toplevel):
    """Liste der gespeicherten Angebote zum Oeffnen, Kopieren und Loeschen."""

    def __init__(self, eltern: Anwendung, eintraege: list[dict]):
        super().__init__(eltern)
        self.eltern = eltern
        self.eintraege = eintraege
        self.title("Gespeicherte Angebote")
        self.geometry("820x420")
        self.transient(eltern)
        self.grab_set()

        spalten = ("name", "patient", "positionen", "summe", "geaendert")
        titel = ("Angebot", "Patient/in", "Pos.", "Summe", "Zuletzt geaendert")
        breiten = (250, 150, 50, 100, 160)
        self.baum = ttk.Treeview(self, columns=spalten, show="headings", selectmode="browse")
        for schluessel, text, breite in zip(spalten, titel, breiten):
            self.baum.heading(schluessel, text=text)
            self.baum.column(schluessel, width=breite,
                             anchor="e" if schluessel in ("positionen", "summe") else "w")
        for i, e in enumerate(eintraege):
            self.baum.insert("", "end", iid=str(i),
                             values=(e["name"], e["patient"], e["positionen"],
                                     f"{geld(e['summe'])} EUR", e["geaendert"]))
        self.baum.pack(fill="both", expand=True, padx=8, pady=8)
        self.baum.bind("<Double-1>", lambda _e: self.oeffnen())
        if eintraege:
            self.baum.selection_set("0")

        leiste = ttk.Frame(self)
        leiste.pack(fill="x", padx=8, pady=(0, 8))
        ttk.Button(leiste, text="Oeffnen", command=self.oeffnen).pack(side="left", padx=2)
        ttk.Button(leiste, text="Kopie anlegen", command=self.kopieren).pack(side="left", padx=2)
        ttk.Button(leiste, text="Loeschen", command=self.loeschen).pack(side="left", padx=2)
        ttk.Button(leiste, text="Abbrechen", command=self.destroy).pack(side="right", padx=2)

    def _gewaehlt(self) -> dict | None:
        auswahl = self.baum.selection()
        return self.eintraege[int(auswahl[0])] if auswahl else None

    def oeffnen(self) -> None:
        eintrag = self._gewaehlt()
        if eintrag is None:
            return
        self.destroy()
        self.eltern.lade_datei(eintrag["datei"])

    def kopieren(self) -> None:
        from tkinter import simpledialog
        eintrag = self._gewaehlt()
        if eintrag is None:
            return
        name = simpledialog.askstring("Kopie anlegen", "Name der Kopie:",
                                      initialvalue=f"{eintrag['name']} (Kopie)", parent=self)
        if not name:
            return
        self.eltern.verzeichnis.kopieren(eintrag["name"], name)
        self.destroy()
        self.eltern.oeffnen()

    def loeschen(self) -> None:
        eintrag = self._gewaehlt()
        if eintrag is None:
            return
        if not messagebox.askyesno(
            "Angebot loeschen", f"Soll das Angebot {eintrag['name']!r} geloescht werden?",
            parent=self
        ):
            return
        self.eltern.verzeichnis.loeschen(eintrag["name"])
        self.destroy()
        self.eltern.oeffnen()


def starte(katalog_pfad: str | None = None, verzeichnis: str | None = None) -> int:
    if tk is None:
        print(
            "Die Fenster-Oberflaeche benoetigt das Python-Modul tkinter.\n"
            "  Windows/macOS: in der Installation von python.org bereits enthalten\n"
            "  Debian/Ubuntu: sudo apt install python3-tk\n"
            "  Fedora:        sudo dnf install python3-tkinter\n\n"
            "Alternativ laeuft die menuegefuehrte Konsole:  python3 kalkulator.py konsole",
            file=sys.stderr,
        )
        return 3
    katalog = Katalog.laden(katalog_pfad)
    Anwendung(katalog, Angebotsverzeichnis(verzeichnis)).mainloop()
    return 0
