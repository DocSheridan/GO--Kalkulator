/**
 * Ablage der Angebote auf dem Geraet.
 *
 * localStorage genuegt: Angebote sind wenige Kilobyte gross, und die Daten
 * sollen das Telefon nicht verlassen.
 */

import { Angebot } from './modelle.js';

const SCHLUESSEL = 'goae.angebote.v1';

export class Angebotsverzeichnis {
  constructor(ablage = globalThis.localStorage) {
    this.ablage = ablage;
  }

  _lesen() {
    try {
      const roh = this.ablage.getItem(SCHLUESSEL);
      const daten = roh ? JSON.parse(roh) : [];
      return Array.isArray(daten) ? daten : [];
    } catch {
      return [];
    }
  }

  _schreiben(liste) {
    this.ablage.setItem(SCHLUESSEL, JSON.stringify(liste));
  }

  /** Alle Angebote, zuletzt geaendertes zuerst. */
  alle() {
    return this._lesen()
      .map((d) => new Angebot(d))
      .sort((a, b) => String(b.geaendert).localeCompare(String(a.geaendert)));
  }

  laden(id) {
    const daten = this._lesen().find((d) => d.id === id);
    return daten ? new Angebot(daten) : null;
  }

  nameVergeben(name, ausserId = null) {
    const gesucht = name.trim().toLowerCase();
    return this._lesen().some((d) => d.id !== ausserId && (d.name ?? '').trim().toLowerCase() === gesucht);
  }

  speichern(angebot) {
    if (!angebot.name.trim()) throw new Error('Das Angebot braucht einen Namen.');
    angebot.geaendert = new Date().toISOString();
    const liste = this._lesen();
    const stelle = liste.findIndex((d) => d.id === angebot.id);
    if (stelle >= 0) liste[stelle] = angebot.toJSON();
    else liste.push(angebot.toJSON());
    this._schreiben(liste);
    return angebot;
  }

  loeschen(id) {
    this._schreiben(this._lesen().filter((d) => d.id !== id));
  }

  kopieren(id, neuerName) {
    const vorlage = this.laden(id);
    if (!vorlage) throw new Error('Angebot nicht gefunden.');
    const kopie = new Angebot({ ...vorlage.toJSON(), id: undefined, name: neuerName });
    kopie.erstellt = new Date().toISOString();
    return this.speichern(kopie);
  }
}
