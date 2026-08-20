/** Laden und Durchsuchen des GOAE-Leistungskatalogs. */

import { KLASSEN } from './modelle.js';

export class Katalog {
  constructor(leistungen, kopf = {}) {
    this.leistungen = leistungen;
    this.stand = kopf.stand ?? '';
    this.quelle = kopf.quelle ?? '';
    this.nachNummer = new Map(leistungen.map((l) => [l.nummer.toUpperCase(), l]));
  }

  static async laden(pfad = 'daten/goae_katalog.json') {
    const antwort = await fetch(pfad);
    if (!antwort.ok) throw new Error(`Katalog nicht ladbar (${antwort.status})`);
    return Katalog.ausJson(await antwort.json());
  }

  static ausJson(inhalt) {
    const leistungen = inhalt.ziffern.map(
      ([nummer, bezeichnung, punktzahl, abschnitt, klasse, regelsatz, hoechstsatz, gruppe]) => ({
        nummer, bezeichnung, punktzahl, abschnitt, klasse, regelsatz, hoechstsatz,
        gruppe: gruppe === 1,
        klassenname: KLASSEN[klasse]?.name ?? klasse,
        // Kleingeschrieben vorhalten - die Suche laeuft ueber 2 711 Eintraege
        // und soll auf dem Telefon bei jedem Tastendruck fluessig bleiben.
        suchtext: `${nummer} ${bezeichnung}`.toLowerCase(),
      }),
    );
    return new Katalog(leistungen, inhalt);
  }

  get anzahl() { return this.leistungen.length; }

  hole(nummer) {
    const treffer = this.nachNummer.get(String(nummer).trim().toUpperCase());
    if (!treffer) throw new Error(`GOÄ-Ziffer ${nummer} ist im Katalog nicht enthalten.`);
    return treffer;
  }

  /** Sucht in Nummer und Legende; exakte Nummerntreffer stehen vorn. */
  suche(begriff, grenze = 80) {
    const text = String(begriff ?? '').trim().toLowerCase();
    if (!text) return this.leistungen.slice(0, grenze);
    const worte = text.split(/\s+/);
    const treffer = [];
    for (const l of this.leistungen) {
      if (worte.every((w) => l.suchtext.includes(w))) treffer.push(l);
    }
    treffer.sort((a, b) => {
      const genauA = a.nummer.toLowerCase() === text ? 0 : 1;
      const genauB = b.nummer.toLowerCase() === text ? 0 : 1;
      return genauA - genauB;
    });
    return { gesamt: treffer.length, liste: treffer.slice(0, grenze) };
  }
}
