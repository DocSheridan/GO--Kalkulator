/**
 * Eigene Analogziffern - nur auf diesem Geraet.
 *
 * Nach § 6 Abs. 2 GOAE duerfen Leistungen, die im Gebuehrenverzeichnis nicht
 * aufgefuehrt sind, entsprechend einer gleichwertigen Ziffer berechnet werden.
 * Punktzahl und Steigerungsklasse ergeben sich aus der herangezogenen Ziffer;
 * nach § 12 Abs. 4 GOAE ist die herangezogene Nummer auf der Rechnung
 * anzugeben.
 *
 * Die Sammlung gehoert dem Anwender und liegt wie die Angebote im Speicher
 * des Geraets - sie verlaesst es nicht und ueberlebt jede Aktualisierung des
 * amtlichen Katalogs.
 */

import { Katalog } from './katalog.js';

const SCHLUESSEL = 'goae.eigene.v1';

// Erlaubte eigene Nummern - wie im Schreibtischprogramm.
const NUMMER_MUSTER = /^[A-Za-z0-9][A-Za-z0-9 .-]{0,15}$/;

export class EigeneFehler extends Error {}

export class EigeneZiffern {
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

  static _zuLeistung(e) {
    return {
      nummer: e.nummer,
      bezeichnung: e.bezeichnung,
      punktzahl: e.punktzahl,
      abschnitt: e.abschnitt ?? '',
      klasse: e.klasse ?? 'a',
      regelsatz: e.regelsatz ?? 2300,
      hoechstsatz: e.hoechstsatz ?? 3500,
      gruppe: false,
      herkunft: 'analog',
      analogZu: e.analog_zu ?? '',
    };
  }

  alle() {
    return this._lesen().map(EigeneZiffern._zuLeistung);
  }

  get anzahl() { return this._lesen().length; }

  /**
   * @param {Katalog} amtlich  der amtliche Katalog (ohne eigene Ziffern)
   * @param {string} bezeichnung  die tatsaechlich erbrachte Leistung
   * @param {string} analogZu  herangezogene Ziffer des Verzeichnisses
   * @param {string} nummer  eigene Nummer; leer = "A" + herangezogene Nummer
   */
  anlegen(amtlich, bezeichnung, analogZu, nummer = '') {
    const text = String(bezeichnung ?? '').trim().replace(/\s+/g, ' ');
    if (!text) throw new EigeneFehler('Die Leistung braucht eine Bezeichnung.');

    let vorlage;
    try {
      vorlage = amtlich.hole(analogZu);
    } catch {
      throw new EigeneFehler(`Die herangezogene Ziffer „${analogZu}“ steht nicht im Katalog.`);
    }

    const eigeneNummer = (String(nummer ?? '').trim() || `A${vorlage.nummer}`);
    if (!NUMMER_MUSTER.test(eigeneNummer)) {
      throw new EigeneFehler(
        `„${eigeneNummer}“ ist als Nummer nicht geeignet – erlaubt sind Buchstaben, Ziffern, `
        + 'Leerzeichen, Punkt und Bindestrich (bis 16 Zeichen).',
      );
    }
    if (amtlich.nachNummer.has(eigeneNummer.toUpperCase())) {
      throw new EigeneFehler(`Die Nummer „${eigeneNummer}“ ist im amtlichen Verzeichnis vergeben.`);
    }
    const liste = this._lesen();
    if (liste.some((e) => e.nummer.toUpperCase() === eigeneNummer.toUpperCase())) {
      throw new EigeneFehler(`Eine eigene Ziffer „${eigeneNummer}“ gibt es bereits.`);
    }

    const eintrag = {
      nummer: eigeneNummer,
      bezeichnung: text,
      punktzahl: vorlage.punktzahl,
      analog_zu: vorlage.nummer,
      abschnitt: vorlage.abschnitt,
      klasse: vorlage.klasse,
      regelsatz: vorlage.regelsatz,
      hoechstsatz: vorlage.hoechstsatz,
    };
    liste.push(eintrag);
    this._schreiben(liste);
    return EigeneZiffern._zuLeistung(eintrag);
  }

  loeschen(nummer) {
    const gesucht = String(nummer).trim().toUpperCase();
    const liste = this._lesen();
    const uebrig = liste.filter((e) => e.nummer.toUpperCase() !== gesucht);
    if (uebrig.length === liste.length) {
      throw new EigeneFehler(`Eigene Ziffer „${nummer}“ ist nicht vorhanden.`);
    }
    this._schreiben(uebrig);
  }
}

/** Legt die eigenen Ziffern ueber den amtlichen Katalog (nur im Speicher). */
export function katalogMitEigenen(amtlich, eigene) {
  const zusammen = new Katalog(
    [...amtlich.leistungen, ...eigene.alle().map(aufbereiten)],
    { stand: amtlich.stand, quelle: amtlich.quelle },
  );
  return zusammen;
}

function aufbereiten(l) {
  return {
    ...l,
    klassenname: { a: 'aerztlich', t: 'technisch', l: 'labor' }[l.klasse] ?? l.klasse,
    suchtext: `${l.nummer} ${l.bezeichnung}`.toLowerCase(),
  };
}
