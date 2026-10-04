"""Fenster-Oberflaeche der Literaturdatenbank (tkinter)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from goae_kalkulator import farben

from . import __version__, einstellungen
from .datenbank import (
    DATENBANK, NEU_TAGE, Artikel, Eintrag, LiteraturFehler, Literaturdatenbank,
    normiere_schlagworte, sortierschluessel,
)

# Werte der beiden festen Reiter - koennen nicht mit Kategorienamen kollidieren.
ALLE = "<<alle>>"
NEUES = "<<neu>>"
ALLE_BEREICHE = "Alle Bereiche"
ALLE_RUBRIKEN = "<<alle_rubriken>>"
KEINE_RUBRIK = "(keine Rubrik)"

# (Schluessel, Ueberschrift, Breite, mitwachsend)
SPALTEN = (
    ("titel", "Titel", 260, True),
    ("kategorie", "Kategorie", 130, False),
    ("rubrik", "Rubrik", 150, False),
    ("bereiche", "Bereiche", 170, True),
    ("schlagworte", "Schlagworte", 190, True),
    ("jahr", "Jahr", 52, False),
    ("angelegt", "Abgelegt", 84, False),
)

DATEITYPEN = (
    ("Alle unterstuetzten", "*.pdf *.doc *.docx *.odt *.rtf *.txt *.xls *.xlsx *.ods "
                            "*.ppt *.pptx *.png *.jpg *.jpeg *.tif *.tiff"),
    ("PDF", "*.pdf"),
    ("Word / Text", "*.doc *.docx *.odt *.rtf *.txt"),
    ("Alle Dateien", "*"),
)

HILFE = """Literaturdatenbank - Kurzanleitung

Artikel ablegen
  "Artikel hinzufuegen" (Strg+N) waehlt eine Datei aus. Sie wird in den
  gemeinsamen Datenordner kopiert und katalogisiert. Als Titel steht
  zunaechst der Dateiname; er laesst sich frei aendern und erscheint so in
  der Uebersicht. Eine Kategorie muss
  zugeordnet werden; Bereiche (Mehrfachauswahl) und Schlagworte sind frei.

Suchen und filtern
  Oben die Kategorie waehlen ("Alle" zeigt alles, "Neues" die in den
  letzten 31 Tagen abgelegten Artikel), darunter optional einen Bereich. Das Suchfeld durchsucht Titel, Autoren, Schlagworte, Notiz,
  Quelle und Dateinamen; mehrere Woerter muessen alle vorkommen.

Bearbeiten
  Einen Artikel anklicken: rechts lassen sich alle Angaben - auch Kategorie,
  Bereiche und Schlagworte - aendern und mit "Speichern" (Strg+S) sichern.
  Doppelklick oder "Oeffnen" zeigt die Datei im zugehoerigen Programm.

Listen
  Rubriken sind Unterkategorien einer Kategorie (z. B. Arbeitsanweisungen
  im Qualitaetsmanagement). Ist eine Kategorie mit Rubriken gewaehlt,
  erscheint darunter eine zweite Knopfleiste zum Filtern.
  Kategorien, Rubriken und Bereiche werden im Menue "Listen" ergaenzt, umbenannt,
  sortiert oder entfernt.

Mehrere Arbeitsplaetze
  Alle Arbeitsplaetze waehlen denselben Datenordner auf dem Server
  ("Datei > Datenordner waehlen"). F5 holt die Aenderungen der anderen."""


def oeffne_datei(pfad: Path) -> None:
    """Oeffnet die Datei mit dem Programm, das das Betriebssystem dafuer vorsieht."""
    if sys.platform.startswith("win"):
        os.startfile(pfad)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(pfad)])
    else:
        subprocess.Popen(["xdg-open", str(pfad)])


def kurzdatum(iso: str) -> str:
    """2026-10-04T12:00:00 -> 04.10.2026"""
    if len(iso) >= 10:
        return f"{iso[8:10]}.{iso[5:7]}.{iso[0:4]}"
    return iso


class ArtikelFormular(ttk.Frame):
    """Eingabefelder eines Artikels - fuer Neuanlage und Bearbeitung."""

    def __init__(self, eltern, **optionen):
        super().__init__(eltern, **optionen)
        self._kategorien: list[Eintrag] = []
        self._bereiche: list[Eintrag] = []
        self._rubriken: list[Eintrag] = []
        self._gesperrt = False
        self._stand: dict | None = None

        self.var_titel = tk.StringVar()
        self.var_autoren = tk.StringVar()
        self.var_jahr = tk.StringVar()
        self.var_quelle = tk.StringVar()
        self.var_kategorie = tk.StringVar()
        self.var_rubrik = tk.StringVar()
        self.var_schlagworte = tk.StringVar()
        self.var_vorschlag = tk.StringVar()

        zeile = 0

        def beschriftung(text: str, pflicht: bool = False) -> None:
            ttk.Label(self, text=text + (" *" if pflicht else ""),
                      style="Pflicht.TLabel" if pflicht else "TLabel").grid(
                row=zeile, column=0, sticky="nw", padx=(0, 6), pady=3)

        beschriftung("Titel", pflicht=True)
        self.feld_titel = ttk.Entry(self, textvariable=self.var_titel)
        self.feld_titel.grid(row=zeile, column=1, columnspan=2, sticky="ew", pady=3)
        zeile += 1

        beschriftung("Kategorie", pflicht=True)
        self.feld_kategorie = ttk.Combobox(self, textvariable=self.var_kategorie,
                                           state="readonly")
        self.feld_kategorie.grid(row=zeile, column=1, columnspan=2, sticky="ew", pady=3)
        self.feld_kategorie.bind("<<ComboboxSelected>>", lambda _e: self._rubriken_anbieten())
        zeile += 1

        beschriftung("Rubrik")
        self.feld_rubrik = ttk.Combobox(self, textvariable=self.var_rubrik, state="readonly")
        self.feld_rubrik.grid(row=zeile, column=1, columnspan=2, sticky="ew", pady=3)
        zeile += 1

        beschriftung("Bereiche")
        rahmen = ttk.Frame(self)
        rahmen.grid(row=zeile, column=1, columnspan=2, sticky="nsew", pady=3)
        self.liste_bereiche = tk.Listbox(
            rahmen, selectmode="multiple", exportselection=False, height=5,
            activestyle="none", selectbackground=farben.GRUEN,
            selectforeground=farben.WEISS)
        rollen = ttk.Scrollbar(rahmen, orient="vertical", command=self.liste_bereiche.yview)
        self.liste_bereiche.configure(yscrollcommand=rollen.set)
        self.liste_bereiche.pack(side="left", fill="both", expand=True)
        rollen.pack(side="left", fill="y")
        self.rowconfigure(zeile, weight=1)
        zeile += 1
        ttk.Label(self, text="Mehrfachauswahl per Klick; erneuter Klick hebt auf.",
                  style="Hinweis.TLabel").grid(row=zeile, column=1, columnspan=2, sticky="w")
        zeile += 1

        beschriftung("Schlagworte")
        ttk.Entry(self, textvariable=self.var_schlagworte).grid(
            row=zeile, column=1, sticky="ew", pady=3)
        self.feld_vorschlag = ttk.Combobox(self, textvariable=self.var_vorschlag,
                                           state="readonly", width=16)
        self.feld_vorschlag.grid(row=zeile, column=2, sticky="ew", padx=(4, 0), pady=3)
        self.feld_vorschlag.bind("<<ComboboxSelected>>", self._vorschlag_uebernehmen)
        zeile += 1
        ttk.Label(self, text="durch Komma getrennt; rechts vorhandene Schlagworte einfuegen",
                  style="Hinweis.TLabel").grid(row=zeile, column=1, columnspan=2, sticky="w")
        zeile += 1

        beschriftung("Autoren")
        ttk.Entry(self, textvariable=self.var_autoren).grid(
            row=zeile, column=1, columnspan=2, sticky="ew", pady=3)
        zeile += 1

        beschriftung("Jahr")
        ttk.Entry(self, textvariable=self.var_jahr, width=8).grid(
            row=zeile, column=1, sticky="w", pady=3)
        zeile += 1

        beschriftung("Quelle")
        ttk.Entry(self, textvariable=self.var_quelle).grid(
            row=zeile, column=1, columnspan=2, sticky="ew", pady=3)
        zeile += 1

        beschriftung("Notiz")
        self.feld_notiz = tk.Text(self, height=4, wrap="word", undo=True,
                                  font="TkDefaultFont")
        self.feld_notiz.grid(row=zeile, column=1, columnspan=2, sticky="nsew", pady=3)
        self.rowconfigure(zeile, weight=1)

        self.columnconfigure(1, weight=1)

    # -- Listen -----------------------------------------------------------
    def setze_listen(self, kategorien: list[Eintrag], bereiche: list[Eintrag],
                     schlagworte: list[str] = (), rubriken: list[Eintrag] = ()) -> None:
        """Aktualisiert die Auswahllisten und behaelt die getroffene Auswahl."""
        gewaehlt = set(self._gewaehlte_bereiche())
        kategorie = self._kategorie_id()
        rubrik = self._rubrik_id()
        self._kategorien = list(kategorien)
        self._bereiche = list(bereiche)
        self._rubriken = list(rubriken)
        self.feld_kategorie["values"] = [k.name for k in self._kategorien]
        self._setze_kategorie(kategorie)
        self._rubriken_anbieten(rubrik)
        self.liste_bereiche.delete(0, "end")
        for i, b in enumerate(self._bereiche):
            self.liste_bereiche.insert("end", b.name)
            if b.id in gewaehlt:
                self.liste_bereiche.selection_set(i)
        self.feld_vorschlag["values"] = list(schlagworte)
        self.var_vorschlag.set("+ Schlagwort")

    def _setze_kategorie(self, kategorie_id: int | None) -> None:
        name = next((k.name for k in self._kategorien if k.id == kategorie_id), "")
        self.var_kategorie.set(name)

    def _kategorie_id(self) -> int | None:
        name = self.var_kategorie.get()
        return next((k.id for k in self._kategorien if k.name == name), None)

    def _rubriken_der_kategorie(self) -> list[Eintrag]:
        kategorie = self._kategorie_id()
        return [r for r in self._rubriken if r.kategorie_id == kategorie]

    def _rubrik_id(self) -> int | None:
        name = self.var_rubrik.get()
        return next((r.id for r in self._rubriken_der_kategorie() if r.name == name), None)

    def _rubriken_anbieten(self, rubrik_id: int | None = None) -> None:
        """Rubrikauswahl passend zur Kategorie; ohne Rubriken bleibt das Feld gesperrt."""
        if rubrik_id is None:
            rubrik_id = self._rubrik_id()
        passend = self._rubriken_der_kategorie()
        self.feld_rubrik["values"] = [KEINE_RUBRIK] + [r.name for r in passend]
        name = next((r.name for r in passend if r.id == rubrik_id), KEINE_RUBRIK)
        self.var_rubrik.set(name if passend else "")
        self.feld_rubrik.configure(
            state="readonly" if passend and not self._gesperrt else "disabled")

    def _gewaehlte_bereiche(self) -> list[int]:
        return [self._bereiche[i].id for i in self.liste_bereiche.curselection()
                if i < len(self._bereiche)]

    def _vorschlag_uebernehmen(self, _ereignis=None) -> None:
        wort = self.var_vorschlag.get()
        if wort and wort != "+ Schlagwort":
            vorhanden = self.var_schlagworte.get().strip().rstrip(",")
            self.var_schlagworte.set(
                normiere_schlagworte(f"{vorhanden}, {wort}" if vorhanden else wort))
        self.var_vorschlag.set("+ Schlagwort")

    # -- Inhalt -----------------------------------------------------------
    def laden(self, artikel: Artikel | None) -> None:
        self.var_titel.set(artikel.titel if artikel else "")
        self.var_autoren.set(artikel.autoren if artikel else "")
        self.var_jahr.set(artikel.jahr if artikel else "")
        self.var_quelle.set(artikel.quelle if artikel else "")
        self.var_schlagworte.set(artikel.schlagworte if artikel else "")
        self._setze_kategorie(artikel.kategorie_id if artikel else None)
        self._rubriken_anbieten(artikel.rubrik_id if artikel else None)
        self.liste_bereiche.selection_clear(0, "end")
        if artikel:
            for i, b in enumerate(self._bereiche):
                if b.id in artikel.bereich_ids:
                    self.liste_bereiche.selection_set(i)
        self.feld_notiz.delete("1.0", "end")
        if artikel:
            self.feld_notiz.insert("1.0", artikel.notiz)
        self.feld_notiz.edit_reset()
        self._stand = self._rohwerte()

    def _rohwerte(self) -> dict:
        return {
            "titel": self.var_titel.get(),
            "kategorie_id": self._kategorie_id(),
            "rubrik_id": self._rubrik_id(),
            "bereich_ids": self._gewaehlte_bereiche(),
            "schlagworte": self.var_schlagworte.get(),
            "autoren": self.var_autoren.get(),
            "jahr": self.var_jahr.get(),
            "quelle": self.var_quelle.get(),
            "notiz": self.feld_notiz.get("1.0", "end-1c"),
        }

    def werte(self) -> dict:
        """Eingaben fuer die Datenbank; meldet fehlende Pflichtangaben."""
        werte = self._rohwerte()
        if not werte["titel"].strip():
            self.feld_titel.focus_set()
            raise LiteraturFehler("Bitte einen Titel angeben.")
        if werte["kategorie_id"] is None:
            self.feld_kategorie.focus_set()
            raise LiteraturFehler("Bitte eine Kategorie zuordnen - das ist Pflicht.")
        return werte

    def geaendert(self) -> bool:
        return self._stand is not None and self._rohwerte() != self._stand

    def sperren(self, gesperrt: bool) -> None:
        self._gesperrt = gesperrt
        zustand = "disabled" if gesperrt else "normal"
        for kind in self.winfo_children():
            if isinstance(kind, ttk.Combobox):
                kind.configure(state="disabled" if gesperrt else "readonly")
            elif isinstance(kind, (ttk.Entry, tk.Text)):
                kind.configure(state=zustand)
        self.liste_bereiche.configure(state=zustand)
        self._rubriken_anbieten()


class NeuerArtikelDialog(tk.Toplevel):
    """Datei auswaehlen, katalogisieren und im Datenordner ablegen."""

    def __init__(self, anwendung: "Anwendung", datei: str = ""):
        super().__init__(anwendung)
        self.anwendung = anwendung
        self.ergebnis: Artikel | None = None
        self.title("Artikel hinzufuegen")
        self.transient(anwendung)
        self.minsize(560, 520)
        self.var_datei = tk.StringVar(value=datei)

        inhalt = ttk.Frame(self, padding=12)
        inhalt.pack(fill="both", expand=True)

        kopf = ttk.Frame(inhalt)
        kopf.pack(fill="x", pady=(0, 8))
        ttk.Label(kopf, text="Datei *", style="Pflicht.TLabel").pack(side="left", padx=(0, 6))
        ttk.Entry(kopf, textvariable=self.var_datei).pack(side="left", fill="x", expand=True)
        ttk.Button(kopf, text="Durchsuchen...", command=self.waehlen).pack(
            side="left", padx=(6, 0))

        self.formular = ArtikelFormular(inhalt)
        self.formular.pack(fill="both", expand=True)
        db = anwendung.db
        self._titelvorschlag = ""
        self.formular.setze_listen(db.kategorien(), db.bereiche(), db.schlagworte(),
                                   db.rubriken())
        self.formular.laden(None)

        ttk.Label(inhalt, text="* Pflichtangabe", style="Hinweis.TLabel").pack(
            anchor="w", pady=(6, 0))
        knoepfe = ttk.Frame(inhalt)
        knoepfe.pack(fill="x", pady=(8, 0))
        ttk.Button(knoepfe, text="Abbrechen", command=self.destroy).pack(side="right")
        ttk.Button(knoepfe, text="Ablegen", style="Haupt.TButton",
                   command=self.ablegen).pack(side="right", padx=(0, 6))

        self.bind("<Escape>", lambda _e: self.destroy())
        if datei:
            self._titel_vorschlagen()
        self.after(50, self._anzeigen)

    def _anzeigen(self) -> None:
        self.grab_set()
        if not self.var_datei.get():
            self.waehlen()
        self.formular.feld_titel.focus_set()

    def waehlen(self) -> None:
        datei = filedialog.askopenfilename(parent=self, title="Artikel auswaehlen",
                                           filetypes=DATEITYPEN)
        if datei:
            self.var_datei.set(datei)
            self._titel_vorschlagen()

    def _titel_vorschlagen(self) -> None:
        """Titel ist zunaechst der Dateiname (ohne Endung) - frei aenderbar.

        Wird eine andere Datei gewaehlt, wandert der Vorschlag mit, solange
        der Titel nicht von Hand geaendert wurde.
        """
        titel = self.formular.var_titel.get().strip()
        if not titel or titel == self._titelvorschlag:
            self._titelvorschlag = Path(self.var_datei.get()).stem
            self.formular.var_titel.set(self._titelvorschlag)

    def ablegen(self) -> None:
        datei = self.var_datei.get().strip()
        try:
            if not datei:
                raise LiteraturFehler("Bitte zuerst eine Datei auswaehlen.")
            werte = self.formular.werte()
            self.configure(cursor="watch")
            self.update_idletasks()
            self.ergebnis = self.anwendung.db.artikel_anlegen(datei, **werte)
        except LiteraturFehler as fehler:
            self.configure(cursor="")
            messagebox.showwarning("Artikel hinzufuegen", str(fehler), parent=self)
            return
        self.destroy()


class ListenDialog(tk.Toplevel):
    """Kategorien, Rubriken oder Bereiche ergaenzen, umbenennen, sortieren, entfernen."""

    TITEL = {"kategorien": "Kategorien bearbeiten", "rubriken": "Rubriken bearbeiten",
             "bereiche": "Bereiche bearbeiten"}
    HINWEIS = {
        "kategorien": "Jeder Artikel gehoert zu genau einer Kategorie. Die Reihenfolge "
                      "bestimmt die Filterknoepfe im Hauptfenster.",
        "rubriken": "Rubriken sind Unterkategorien. Jede Kategorie hat ihre eigene "
                    "Liste; ein Artikel kann einer Rubrik seiner Kategorie angehoeren.",
        "bereiche": "Einem Artikel koennen beliebig viele Bereiche zugeordnet werden.",
    }
    NEU = {"kategorien": "Neue Kategorie:", "rubriken": "Neue Rubrik:",
           "bereiche": "Neuer Bereich:"}

    def __init__(self, anwendung: "Anwendung", tabelle: str,
                 kategorie_id: int | None = None):
        super().__init__(anwendung)
        self.anwendung = anwendung
        self.db = anwendung.db
        self.tabelle = tabelle
        self.eintraege: list[Eintrag] = []
        self.title(self.TITEL[tabelle])
        self.transient(anwendung)
        self.minsize(420, 340)

        inhalt = ttk.Frame(self, padding=12)
        inhalt.pack(fill="both", expand=True)
        ttk.Label(inhalt, text=self.HINWEIS[tabelle], wraplength=380,
                  style="Hinweis.TLabel").pack(anchor="w", pady=(0, 8))

        self.kategorien = self.db.kategorien() if tabelle == "rubriken" else []
        self.var_gruppe = tk.StringVar()
        if tabelle == "rubriken":
            zeile = ttk.Frame(inhalt)
            zeile.pack(fill="x", pady=(0, 8))
            ttk.Label(zeile, text="Kategorie").pack(side="left", padx=(0, 6))
            auswahl = ttk.Combobox(zeile, textvariable=self.var_gruppe, state="readonly",
                                   values=[k.name for k in self.kategorien])
            auswahl.pack(side="left", fill="x", expand=True)
            auswahl.bind("<<ComboboxSelected>>", lambda _e: self.laden())
            vorgabe = next((k for k in self.kategorien if k.id == kategorie_id), None)
            if vorgabe is None:
                # Sonst die erste Kategorie, die schon Rubriken hat.
                mit = {r.kategorie_id for r in self.db.rubriken()}
                vorgabe = next((k for k in self.kategorien if k.id in mit),
                               self.kategorien[0] if self.kategorien else None)
            self.var_gruppe.set(vorgabe.name if vorgabe else "")

        mitte = ttk.Frame(inhalt)
        mitte.pack(fill="both", expand=True)
        self.liste = tk.Listbox(mitte, exportselection=False, activestyle="none",
                                selectbackground=farben.GRUEN,
                                selectforeground=farben.WEISS)
        self.liste.pack(side="left", fill="both", expand=True)
        self.liste.bind("<Double-Button-1>", lambda _e: self.umbenennen())
        knoepfe = ttk.Frame(mitte)
        knoepfe.pack(side="left", fill="y", padx=(8, 0))
        for text, befehl in (("Hinzufuegen...", self.hinzufuegen),
                             ("Umbenennen...", self.umbenennen),
                             ("Nach oben", lambda: self.verschieben(-1)),
                             ("Nach unten", lambda: self.verschieben(1)),
                             ("Entfernen...", self.entfernen)):
            ttk.Button(knoepfe, text=text, command=befehl).pack(fill="x", pady=2)
        ttk.Button(inhalt, text="Schliessen", command=self.destroy).pack(
            anchor="e", pady=(10, 0))

        self.bind("<Escape>", lambda _e: self.destroy())
        self.laden()
        self.after(50, self.grab_set)

    def laden(self, auswahl_id: int | None = None) -> None:
        try:
            if self.tabelle == "kategorien":
                self.eintraege = self.db.kategorien()
            elif self.tabelle == "rubriken":
                gruppe = self._gruppe()
                self.eintraege = self.db.rubriken(gruppe) if gruppe is not None else []
            else:
                self.eintraege = self.db.bereiche()
        except LiteraturFehler as fehler:
            messagebox.showerror(self.title(), str(fehler), parent=self)
            return
        self.liste.delete(0, "end")
        for i, e in enumerate(self.eintraege):
            self.liste.insert("end", f"{e.name}   ({e.anzahl} Artikel)")
            if e.id == auswahl_id:
                self.liste.selection_set(i)
                self.liste.see(i)
        self.anwendung.listen_neu_laden()

    def _gruppe(self) -> int | None:
        """Kategorie, deren Rubriken gerade bearbeitet werden."""
        return next((k.id for k in self.kategorien if k.name == self.var_gruppe.get()), None)

    def _gewaehlt(self) -> Eintrag | None:
        auswahl = self.liste.curselection()
        if not auswahl:
            messagebox.showinfo(self.title(), "Bitte zuerst einen Eintrag markieren.",
                                parent=self)
            return None
        return self.eintraege[auswahl[0]]

    def _ausfuehren(self, aktion, auswahl_id=None) -> None:
        try:
            ergebnis = aktion()
        except LiteraturFehler as fehler:
            messagebox.showwarning(self.title(), str(fehler), parent=self)
            return
        self.laden(ergebnis if isinstance(ergebnis, int) else auswahl_id)

    def hinzufuegen(self) -> None:
        name = simpledialog.askstring(self.title(), self.NEU[self.tabelle], parent=self)
        if name:
            self._ausfuehren(
                lambda: self.db.eintrag_hinzufuegen(self.tabelle, name, self._gruppe()))

    def umbenennen(self) -> None:
        eintrag = self._gewaehlt()
        if not eintrag:
            return
        name = simpledialog.askstring(self.title(), "Neuer Name:", initialvalue=eintrag.name,
                                      parent=self)
        if name and name != eintrag.name:
            self._ausfuehren(
                lambda: self.db.eintrag_umbenennen(self.tabelle, eintrag.id, name), eintrag.id)

    def verschieben(self, richtung: int) -> None:
        eintrag = self._gewaehlt()
        if eintrag:
            self._ausfuehren(
                lambda: self.db.eintrag_verschieben(self.tabelle, eintrag.id, richtung),
                eintrag.id)

    def entfernen(self) -> None:
        eintrag = self._gewaehlt()
        if not eintrag:
            return
        if self.tabelle == "bereiche":
            text = f"Bereich {eintrag.name!r} entfernen?"
            if eintrag.anzahl:
                text += (f"\n\nEr wird bei {eintrag.anzahl} Artikel(n) ausgetragen; "
                         "die Artikel selbst bleiben erhalten.")
            if messagebox.askyesno(self.title(), text, parent=self):
                self._ausfuehren(lambda: self.db.bereich_loeschen(eintrag.id))
            return
        if self.tabelle == "rubriken":
            text = f"Rubrik {eintrag.name!r} entfernen?"
            if eintrag.anzahl:
                text += (f"\n\n{eintrag.anzahl} Artikel verlieren diese Rubrik, bleiben "
                         "aber in ihrer Kategorie erhalten.")
            if messagebox.askyesno(self.title(), text, parent=self):
                self._ausfuehren(lambda: self.db.rubrik_loeschen(eintrag.id))
            return
        ersatz_id = None
        if eintrag.anzahl:
            andere = [e for e in self.eintraege if e.id != eintrag.id]
            if not andere:
                messagebox.showwarning(self.title(),
                                       "Die letzte Kategorie kann nicht entfernt werden.",
                                       parent=self)
                return
            ersatz_id = ErsatzDialog.fragen(self, eintrag, andere)
            if ersatz_id is None:
                return
        elif not messagebox.askyesno(self.title(), f"Kategorie {eintrag.name!r} entfernen?",
                                     parent=self):
            return
        self._ausfuehren(lambda: self.db.kategorie_loeschen(eintrag.id, ersatz_id))


class ErsatzDialog(tk.Toplevel):
    """Fragt, in welche Kategorie die Artikel einer geloeschten Kategorie wandern."""

    def __init__(self, eltern, eintrag: Eintrag, andere: list[Eintrag]):
        super().__init__(eltern)
        self.andere = andere
        self.ergebnis: int | None = None
        self.title("Kategorie entfernen")
        self.transient(eltern)
        inhalt = ttk.Frame(self, padding=12)
        inhalt.pack(fill="both", expand=True)
        ttk.Label(inhalt, wraplength=340, text=(
            f"Der Kategorie {eintrag.name!r} sind {eintrag.anzahl} Artikel zugeordnet. "
            "Da jeder Artikel eine Kategorie braucht, werden sie verschoben nach:")).pack(
            anchor="w")
        self.var = tk.StringVar(value=andere[0].name)
        ttk.Combobox(inhalt, textvariable=self.var, state="readonly",
                     values=[e.name for e in andere]).pack(fill="x", pady=8)
        knoepfe = ttk.Frame(inhalt)
        knoepfe.pack(fill="x")
        ttk.Button(knoepfe, text="Abbrechen", command=self.destroy).pack(side="right")
        ttk.Button(knoepfe, text="Verschieben und entfernen",
                   command=self.bestaetigen).pack(side="right", padx=(0, 6))
        self.bind("<Escape>", lambda _e: self.destroy())

    def bestaetigen(self) -> None:
        self.ergebnis = next(e.id for e in self.andere if e.name == self.var.get())
        self.destroy()

    @classmethod
    def fragen(cls, eltern, eintrag: Eintrag, andere: list[Eintrag]) -> int | None:
        dialog = cls(eltern, eintrag, andere)
        dialog.grab_set()
        dialog.wait_window()
        return dialog.ergebnis


class Anwendung(tk.Tk):
    """Hauptfenster: Filter oben, Artikelliste links, Angaben rechts."""

    def __init__(self, db: Literaturdatenbank):
        super().__init__()
        self.db = db
        self.artikel: dict[str, Artikel] = {}
        self.kategorien: list[Eintrag] = []
        self.bereiche: list[Eintrag] = []
        self.rubriken: list[Eintrag] = []
        self.aktuell: Artikel | None = None
        self._sortierung = ("angelegt", True)
        self._auswahl_sperre = False

        self.title("Literaturdatenbank")
        self.geometry("1280x780")
        self.minsize(980, 600)
        self.protocol("WM_DELETE_WINDOW", self.beenden)

        self.var_kategorie = tk.StringVar(value=ALLE)
        self.var_bereich = tk.StringVar(value=ALLE_BEREICHE)
        self.var_rubrik = tk.StringVar(value=ALLE_RUBRIKEN)
        self.var_suche = tk.StringVar()
        self.var_status = tk.StringVar()
        self.var_datei = tk.StringVar()

        self._stil()
        self._menue()
        self._aufbau()
        self.var_suche.trace_add("write", lambda *_a: self.liste_neu_laden())
        self.neu_laden()

    # -- Aufbau -----------------------------------------------------------
    def _stil(self) -> None:
        stil = ttk.Style(self)
        try:
            stil.theme_use("clam")
        except tk.TclError:
            pass
        stil.configure("Titel.TLabel", font=("TkDefaultFont", 14, "bold"),
                       foreground=farben.GRUEN)
        stil.configure("Hinweis.TLabel", foreground=farben.GRAU,
                       font=("TkDefaultFont", 8))
        stil.configure("Pflicht.TLabel", foreground=farben.GRUEN_STARK,
                       font=("TkDefaultFont", 9, "bold"))
        stil.configure("TLabelframe.Label", foreground=farben.GRUEN)
        stil.configure("Haupt.TButton", foreground=farben.WEISS, background=farben.GRUEN)
        stil.map("Haupt.TButton", background=[("active", farben.GRUEN_STARK)])
        stil.configure("Filter.Toolbutton", padding=(10, 4))
        stil.map("Filter.Toolbutton",
                 background=[("selected", farben.GRUEN), ("active", farben.GRUEN_TON)],
                 foreground=[("selected", farben.WEISS)])
        stil.configure("Treeview.Heading", background=farben.GRUEN, foreground=farben.WEISS)
        stil.map("Treeview.Heading", background=[("active", farben.GRUEN_STARK)])
        stil.map("Treeview", background=[("selected", farben.GRUEN)],
                 foreground=[("selected", farben.WEISS)])

    def _menue(self) -> None:
        leiste = tk.Menu(self)
        datei = tk.Menu(leiste, tearoff=0)
        datei.add_command(label="Artikel hinzufuegen...", accelerator="Strg+N",
                          command=self.hinzufuegen)
        datei.add_command(label="Aenderungen speichern", accelerator="Strg+S",
                          command=self.speichern)
        datei.add_separator()
        datei.add_command(label="Datenordner waehlen...", command=self.ordner_waehlen)
        datei.add_command(label="Datenordner im Dateimanager zeigen",
                          command=lambda: self._oeffnen(self.db.ordner))
        datei.add_command(label="Aktualisieren", accelerator="F5", command=self.neu_laden)
        datei.add_separator()
        datei.add_command(label="Beenden", command=self.beenden)
        leiste.add_cascade(label="Datei", menu=datei)

        listen = tk.Menu(leiste, tearoff=0)
        listen.add_command(label="Kategorien bearbeiten...",
                           command=lambda: self.liste_bearbeiten("kategorien"))
        listen.add_command(label="Rubriken bearbeiten...",
                           command=lambda: self.liste_bearbeiten("rubriken"))
        listen.add_command(label="Bereiche bearbeiten...",
                           command=lambda: self.liste_bearbeiten("bereiche"))
        leiste.add_cascade(label="Listen", menu=listen)

        hilfe = tk.Menu(leiste, tearoff=0)
        hilfe.add_command(label="Kurzanleitung", command=self.hilfe)
        leiste.add_cascade(label="Hilfe", menu=hilfe)
        self.config(menu=leiste)

        self.bind("<Control-n>", lambda _e: self.hinzufuegen())
        self.bind("<Control-s>", lambda _e: self.speichern())
        self.bind("<F5>", lambda _e: self.neu_laden())

    def _aufbau(self) -> None:
        # -- Kopf: Titel und Hinzufuegen
        kopf = ttk.Frame(self, padding=(10, 8, 10, 0))
        kopf.pack(fill="x")
        ttk.Label(kopf, text="Literaturdatenbank", style="Titel.TLabel").pack(side="left")
        ttk.Button(kopf, text="+ Artikel hinzufuegen", style="Haupt.TButton",
                   command=self.hinzufuegen).pack(side="right")

        # -- Filter: Kategorie-Knoepfe, Bereich, Suche
        filter_ = ttk.Frame(self, padding=(10, 8, 10, 4))
        filter_.pack(fill="x")
        ttk.Label(filter_, text="Kategorie").grid(row=0, column=0, sticky="w", padx=(0, 6))
        self.kategorie_knoepfe = ttk.Frame(filter_)
        self.kategorie_knoepfe.grid(row=0, column=1, columnspan=5, sticky="w")
        # Zweite Leiste mit den Rubriken - nur sichtbar, wenn die Kategorie welche hat.
        self.rubrik_beschriftung = ttk.Label(filter_, text="Rubrik")
        self.rubrik_beschriftung.grid(row=1, column=0, sticky="w", padx=(0, 6), pady=(6, 0))
        self.rubrik_knoepfe = ttk.Frame(filter_)
        self.rubrik_knoepfe.grid(row=1, column=1, columnspan=5, sticky="w", pady=(6, 0))
        ttk.Label(filter_, text="Bereich").grid(row=2, column=0, sticky="w", padx=(0, 6),
                                                pady=(6, 0))
        self.feld_bereich = ttk.Combobox(filter_, textvariable=self.var_bereich,
                                         state="readonly", width=26)
        self.feld_bereich.grid(row=2, column=1, sticky="w", pady=(6, 0))
        self.feld_bereich.bind("<<ComboboxSelected>>", lambda _e: self.liste_neu_laden())
        ttk.Label(filter_, text="Suche").grid(row=2, column=2, sticky="w", padx=(16, 6),
                                              pady=(6, 0))
        suche = ttk.Entry(filter_, textvariable=self.var_suche, width=40)
        suche.grid(row=2, column=3, sticky="ew", pady=(6, 0))
        suche.bind("<Escape>", lambda _e: self.var_suche.set(""))
        ttk.Button(filter_, text="Filter zuruecksetzen", command=self.filter_zuruecksetzen
                   ).grid(row=2, column=4, sticky="w", padx=(8, 0), pady=(6, 0))
        filter_.columnconfigure(3, weight=1)

        # -- Statuszeile
        ttk.Label(self, textvariable=self.var_status, relief="sunken", anchor="w",
                  padding=(6, 2)).pack(fill="x", side="bottom")

        # -- Mitte: Liste | Angaben
        mitte = ttk.PanedWindow(self, orient="horizontal")
        mitte.pack(fill="both", expand=True, padx=10, pady=(4, 8))
        mitte.add(self._liste(mitte), weight=3)
        mitte.add(self._angaben(mitte), weight=2)
        # Anfangsteilung setzen, sobald die Fenstergroesse feststeht.
        self.after(80, lambda: mitte.sashpos(0, int(mitte.winfo_width() * 0.55)))

    def _liste(self, eltern) -> ttk.Frame:
        rahmen = ttk.Frame(eltern)
        self.baum = ttk.Treeview(rahmen, columns=[s[0] for s in SPALTEN], show="headings",
                                 selectmode="browse")
        for schluessel, ueberschrift, breite, wachsend in SPALTEN:
            self.baum.heading(schluessel, text=ueberschrift,
                              command=lambda s=schluessel: self.sortieren(s))
            self.baum.column(schluessel, width=breite, minwidth=40, stretch=wachsend)
        senkrecht = ttk.Scrollbar(rahmen, orient="vertical", command=self.baum.yview)
        waagerecht = ttk.Scrollbar(rahmen, orient="horizontal", command=self.baum.xview)
        self.baum.configure(yscrollcommand=senkrecht.set, xscrollcommand=waagerecht.set)
        self.baum.grid(row=0, column=0, sticky="nsew")
        senkrecht.grid(row=0, column=1, sticky="ns")
        waagerecht.grid(row=1, column=0, sticky="ew")
        rahmen.rowconfigure(0, weight=1)
        rahmen.columnconfigure(0, weight=1)
        self.baum.tag_configure("ohne_datei", foreground=farben.FEHLER)
        self.baum.bind("<<TreeviewSelect>>", self._auswahl_geaendert)
        self.baum.bind("<Double-Button-1>", lambda _e: self.datei_oeffnen())
        self.baum.bind("<Return>", lambda _e: self.datei_oeffnen())
        self.baum.bind("<Delete>", lambda _e: self.loeschen())
        return rahmen

    def _angaben(self, eltern) -> ttk.LabelFrame:
        rahmen = ttk.LabelFrame(eltern, text="Angaben zum Artikel", padding=10)
        self.formular = ArtikelFormular(rahmen)
        self.formular.pack(fill="both", expand=True)

        datei = ttk.Frame(rahmen)
        datei.pack(fill="x", pady=(8, 0))
        ttk.Label(datei, text="Datei").pack(side="left", padx=(0, 6))
        ttk.Label(datei, textvariable=self.var_datei, style="Hinweis.TLabel").pack(
            side="left", fill="x", expand=True)

        knoepfe = ttk.Frame(rahmen)
        knoepfe.pack(fill="x", pady=(8, 0))
        self.knoepfe = [
            ttk.Button(knoepfe, text="Speichern", style="Haupt.TButton",
                       command=self.speichern),
            ttk.Button(knoepfe, text="Verwerfen", command=self.verwerfen),
            ttk.Button(knoepfe, text="Oeffnen", command=self.datei_oeffnen),
            ttk.Button(knoepfe, text="Datei ersetzen...", command=self.datei_ersetzen),
            ttk.Button(knoepfe, text="Loeschen...", command=self.loeschen),
        ]
        for knopf in self.knoepfe:
            knopf.pack(side="left", padx=(0, 4))
        return rahmen

    # -- Laden ------------------------------------------------------------
    def neu_laden(self) -> None:
        """Listen und Artikel frisch aus dem Datenordner holen (F5)."""
        self.listen_neu_laden()
        self.liste_neu_laden()

    def listen_neu_laden(self) -> None:
        try:
            self.kategorien = self.db.kategorien()
            self.bereiche = self.db.bereiche()
            self.rubriken = self.db.rubriken()
            schlagworte = self.db.schlagworte()
        except LiteraturFehler as fehler:
            self.var_status.set(str(fehler))
            return
        if self.var_kategorie.get() not in {ALLE, NEUES} | {k.name for k in self.kategorien}:
            self.var_kategorie.set(ALLE)
        for kind in self.kategorie_knoepfe.winfo_children():
            kind.destroy()
        reiter = [(ALLE, "Alle"), (NEUES, "Neues")] + [(k.name, k.name)
                                                     for k in self.kategorien]
        for wert, name in reiter:
            ttk.Radiobutton(self.kategorie_knoepfe, text=name, value=wert,
                            variable=self.var_kategorie, style="Filter.Toolbutton",
                            command=self._kategorie_gewechselt).pack(side="left", padx=(0, 4))
        self._rubrik_knoepfe_aufbauen()
        self.feld_bereich["values"] = [ALLE_BEREICHE] + [b.name for b in self.bereiche]
        if self.var_bereich.get() not in self.feld_bereich["values"]:
            self.var_bereich.set(ALLE_BEREICHE)
        # Eine laufende Bearbeitung bleibt dabei erhalten.
        self.formular.setze_listen(self.kategorien, self.bereiche, schlagworte, self.rubriken)

    def _gewaehlte_kategorie(self) -> int | None:
        return next((k.id for k in self.kategorien if k.name == self.var_kategorie.get()), None)

    def _kategorie_gewechselt(self) -> None:
        self.var_rubrik.set(ALLE_RUBRIKEN)
        self._rubrik_knoepfe_aufbauen()
        self.liste_neu_laden()

    def _rubrik_knoepfe_aufbauen(self) -> None:
        for kind in self.rubrik_knoepfe.winfo_children():
            kind.destroy()
        kategorie = self._gewaehlte_kategorie()
        passend = [r for r in self.rubriken if r.kategorie_id == kategorie]
        if self.var_rubrik.get() not in {r.name for r in passend}:
            self.var_rubrik.set(ALLE_RUBRIKEN)
        if not passend:
            self.rubrik_beschriftung.grid_remove()
            self.rubrik_knoepfe.grid_remove()
            return
        self.rubrik_beschriftung.grid()
        self.rubrik_knoepfe.grid()
        for wert, name in [(ALLE_RUBRIKEN, "Alle Rubriken")] + [(r.name, r.name)
                                                                for r in passend]:
            ttk.Radiobutton(self.rubrik_knoepfe, text=name, value=wert,
                            variable=self.var_rubrik, style="Filter.Toolbutton",
                            command=self.liste_neu_laden).pack(side="left", padx=(0, 4))

    def liste_neu_laden(self) -> None:
        kategorie_id = self._gewaehlte_kategorie()
        rubrik_id = next((r.id for r in self.rubriken if r.kategorie_id == kategorie_id
                          and r.name == self.var_rubrik.get()), None)
        bereich_id = next((b.id for b in self.bereiche
                           if b.name == self.var_bereich.get()), None)
        try:
            neu = NEU_TAGE if self.var_kategorie.get() == NEUES else None
            treffer = self.db.suche(self.var_suche.get(), kategorie_id, bereich_id, neu,
                                    rubrik_id)
            gesamt = len(self.db.suche())
        except LiteraturFehler as fehler:
            self.var_status.set(str(fehler))
            return
        schluessel, absteigend = self._sortierung
        treffer.sort(key=lambda a: self._sortwert(a, schluessel), reverse=absteigend)

        self._auswahl_sperre = True
        try:
            self.baum.delete(*self.baum.get_children())
            self.artikel = {}
            for a in treffer:
                iid = str(a.id)
                self.artikel[iid] = a
                vorhanden = bool(a.datei) and self.db.pfad(a).exists()
                self.baum.insert("", "end", iid=iid, tags=() if vorhanden else ("ohne_datei",),
                                 values=(a.titel, a.kategorie, a.rubrik, ", ".join(a.bereiche),
                                         a.schlagworte, a.jahr, kurzdatum(a.angelegt)))
            if self.aktuell and str(self.aktuell.id) in self.artikel:
                self.baum.selection_set(str(self.aktuell.id))
                self.baum.see(str(self.aktuell.id))
        finally:
            self._auswahl_sperre = False

        if self.aktuell and str(self.aktuell.id) in self.artikel and not self.formular.geaendert():
            self._zeige(self.artikel[str(self.aktuell.id)])
        elif self.aktuell is None:
            self._zeige(None)

        if neu is not None:
            anzeige = f"{len(treffer)} neue Artikel (letzte {NEU_TAGE} Tage) von {gesamt}"
        elif len(treffer) != gesamt:
            anzeige = f"{len(treffer)} von {gesamt} Artikeln angezeigt"
        else:
            anzeige = f"{gesamt} Artikel"
        self.var_status.set(
            anzeige + f"  -  Datenordner: {self.db.ordner}")

    @staticmethod
    def _sortwert(artikel: Artikel, schluessel: str):
        if schluessel == "bereiche":
            return sortierschluessel(", ".join(artikel.bereiche))
        wert = getattr(artikel, schluessel)
        return sortierschluessel(wert) if isinstance(wert, str) else wert

    def sortieren(self, schluessel: str) -> None:
        alt, absteigend = self._sortierung
        self._sortierung = (schluessel, not absteigend if alt == schluessel else False)
        self.liste_neu_laden()

    def filter_zuruecksetzen(self) -> None:
        self.var_kategorie.set(ALLE)
        self.var_rubrik.set(ALLE_RUBRIKEN)
        self._rubrik_knoepfe_aufbauen()
        self.var_bereich.set(ALLE_BEREICHE)
        self.var_suche.set("")  # loest das Neuladen aus

    # -- Auswahl und Bearbeitung -----------------------------------------
    def _zeige(self, artikel: Artikel | None) -> None:
        self.aktuell = artikel
        self.formular.sperren(False)
        self.formular.laden(artikel)
        self.formular.sperren(artikel is None)
        for knopf in self.knoepfe:
            knopf.state(["disabled"] if artikel is None else ["!disabled"])
        if artikel is None:
            self.var_datei.set("Bitte links einen Artikel auswaehlen.")
        elif not artikel.datei:
            self.var_datei.set("keine Datei hinterlegt")
        elif not self.db.pfad(artikel).exists():
            self.var_datei.set(f"{artikel.datei}  (fehlt im Datenordner!)")
        else:
            self.var_datei.set(f"{artikel.originalname}  ->  {artikel.datei}")

    def _auswahl_geaendert(self, _ereignis=None) -> None:
        if self._auswahl_sperre:
            return
        auswahl = self.baum.selection()
        neu = self.artikel.get(auswahl[0]) if auswahl else None
        if self.aktuell and neu and neu.id == self.aktuell.id:
            return
        if not self._aenderungen_klaeren():
            # Zurueck zur bisherigen Zeile, ohne erneut nachzufragen.
            self._auswahl_sperre = True
            try:
                if self.aktuell and str(self.aktuell.id) in self.artikel:
                    self.baum.selection_set(str(self.aktuell.id))
            finally:
                self.after_idle(self._sperre_aufheben)
            return
        self._zeige(neu)

    def _sperre_aufheben(self) -> None:
        self._auswahl_sperre = False

    def _aenderungen_klaeren(self) -> bool:
        """Fragt bei ungespeicherten Aenderungen nach. False = abbrechen."""
        if not (self.aktuell and self.formular.geaendert()):
            return True
        antwort = messagebox.askyesnocancel(
            "Ungespeicherte Aenderungen",
            f"Die Angaben zu {self.aktuell.titel!r} wurden geaendert.\n\nSpeichern?",
            parent=self)
        if antwort is None:
            return False
        if antwort:
            return self.speichern()
        return True

    def speichern(self) -> bool:
        if self.aktuell is None:
            return True
        try:
            werte = self.formular.werte()
            self.aktuell = self.db.artikel_aendern(self.aktuell.id, **werte)
        except LiteraturFehler as fehler:
            messagebox.showwarning("Speichern", str(fehler), parent=self)
            return False
        self.formular.laden(self.aktuell)
        self.listen_neu_laden()
        self.liste_neu_laden()
        self.var_status.set(f"Gespeichert: {self.aktuell.titel}")
        return True

    def verwerfen(self) -> None:
        if self.aktuell:
            self._zeige(self.aktuell)

    def hinzufuegen(self) -> None:
        if not self._aenderungen_klaeren():
            return
        dialog = NeuerArtikelDialog(self)
        self.wait_window(dialog)
        if dialog.ergebnis:
            self.aktuell = dialog.ergebnis
            self.formular._stand = None
            self.neu_laden()
            if str(self.aktuell.id) not in self.artikel:
                self.filter_zuruecksetzen()
            self._zeige(dialog.ergebnis)
            self.var_status.set(f"Abgelegt: {dialog.ergebnis.titel}")

    def datei_oeffnen(self) -> None:
        if self.aktuell is None:
            return
        if not self.aktuell.datei:
            messagebox.showinfo("Oeffnen", "Zu diesem Artikel ist keine Datei hinterlegt.",
                                parent=self)
            return
        pfad = self.db.pfad(self.aktuell)
        if not pfad.exists():
            messagebox.showwarning("Oeffnen", f"Die Datei fehlt im Datenordner:\n{pfad}",
                                   parent=self)
            return
        self._oeffnen(pfad)

    def _oeffnen(self, pfad: Path) -> None:
        try:
            oeffne_datei(pfad)
        except OSError as fehler:
            messagebox.showerror("Oeffnen", f"{pfad} kann nicht geoeffnet werden:\n{fehler}",
                                 parent=self)

    def datei_ersetzen(self) -> None:
        if self.aktuell is None:
            return
        datei = filedialog.askopenfilename(parent=self, title="Neue Fassung auswaehlen",
                                           filetypes=DATEITYPEN)
        if not datei:
            return
        try:
            self.aktuell = self.db.datei_ersetzen(self.aktuell.id, datei)
        except LiteraturFehler as fehler:
            messagebox.showwarning("Datei ersetzen", str(fehler), parent=self)
            return
        self.liste_neu_laden()
        self.var_status.set(f"Datei ersetzt: {self.aktuell.titel}")

    def loeschen(self) -> None:
        if self.aktuell is None:
            return
        if not messagebox.askyesno(
                "Artikel loeschen",
                f"{self.aktuell.titel!r} aus der Datenbank entfernen?\n\n"
                "Die abgelegte Datei im Datenordner wird ebenfalls geloescht.",
                icon="warning", default="no", parent=self):
            return
        try:
            self.db.artikel_loeschen(self.aktuell.id)
        except LiteraturFehler as fehler:
            messagebox.showwarning("Artikel loeschen", str(fehler), parent=self)
            return
        titel = self.aktuell.titel
        self._zeige(None)
        self.neu_laden()
        self.var_status.set(f"Geloescht: {titel}")

    def liste_bearbeiten(self, tabelle: str) -> None:
        if not self._aenderungen_klaeren():
            return
        self.wait_window(ListenDialog(self, tabelle, self._gewaehlte_kategorie()))
        self.neu_laden()

    # -- Datenordner ------------------------------------------------------
    def ordner_waehlen(self) -> None:
        if not self._aenderungen_klaeren():
            return
        neu = waehle_datenordner(self, self.db.ordner)
        if neu is None:
            return
        self.db = neu
        self._zeige(None)
        self.filter_zuruecksetzen()
        self.neu_laden()

    def hilfe(self) -> None:
        fenster = tk.Toplevel(self)
        fenster.title("Kurzanleitung")
        fenster.transient(self)
        text = tk.Text(fenster, wrap="word", width=78, height=30, padx=12, pady=10,
                       font="TkDefaultFont")
        text.insert("1.0", HILFE + f"\n\nVersion {__version__}")
        text.configure(state="disabled")
        text.pack(fill="both", expand=True)
        ttk.Button(fenster, text="Schliessen", command=fenster.destroy).pack(pady=8)

    def beenden(self) -> None:
        if self._aenderungen_klaeren():
            self.destroy()


def waehle_datenordner(eltern, bisher: Path | None = None) -> Literaturdatenbank | None:
    """Fragt nach dem Datenordner, richtet ihn ein und merkt ihn sich."""
    ordner = filedialog.askdirectory(
        parent=eltern, mustexist=True, initialdir=str(bisher) if bisher else None,
        title="Datenordner der Literaturdatenbank waehlen (z. B. auf dem Server)")
    if not ordner:
        return None
    ordner = Path(ordner)
    if not (ordner / DATENBANK).exists() and not messagebox.askyesno(
            "Datenordner",
            f"In {ordner} gibt es noch keine Literaturdatenbank.\n\n"
            "Eine neue, leere Datenbank anlegen?\n\n(Fuer eine vorhandene Datenbank "
            "den Ordner waehlen, in dem die Datei literatur.sqlite liegt.)",
            parent=eltern):
        return None
    try:
        db = Literaturdatenbank(ordner).einrichten()
        einstellungen.datenordner_merken(ordner)
    except (LiteraturFehler, OSError) as fehler:
        messagebox.showerror("Datenordner", str(fehler), parent=eltern)
        return None
    return db


def starte(ordner: Path | str | None = None) -> int:
    ordner = Path(ordner) if ordner else einstellungen.datenordner()
    db = None
    if ordner is not None:
        try:
            db = Literaturdatenbank(ordner).einrichten()
        except LiteraturFehler as fehler:
            fehlermeldung = str(fehler)
        else:
            fehlermeldung = ""
    if db is None:
        wurzel = tk.Tk()
        wurzel.withdraw()
        if ordner is None:
            messagebox.showinfo(
                "Literaturdatenbank",
                "Willkommen! Bitte zuerst den Datenordner waehlen, in dem Katalog und "
                "Artikel abgelegt werden - fuer die gemeinsame Nutzung einen Ordner "
                "auf dem Server.", parent=wurzel)
        else:
            messagebox.showwarning(
                "Literaturdatenbank",
                f"{fehlermeldung}\n\nIst das Netzlaufwerk verbunden? Alternativ einen "
                "anderen Datenordner waehlen.", parent=wurzel)
        db = waehle_datenordner(wurzel, ordner)
        wurzel.destroy()
        if db is None:
            return 1
    Anwendung(db).mainloop()
    return 0
