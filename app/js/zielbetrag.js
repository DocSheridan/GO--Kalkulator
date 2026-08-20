/**
 * Verteilt die Steigerungsfaktoren auf einen vorgegebenen Gesamtpreis.
 *
 * Wortgleich zur Fassung des Schreibtischprogramms, nur in Ganzzahlen:
 *  1. Skalierung - ein gemeinsamer Parameter lambda wird per
 *     Intervallhalbierung gesucht. Faktoren, die an 1,0 oder 3,5 stossen,
 *     bleiben dort, die uebrigen tragen den Rest.
 *  2. Rasterung auf die gewaehlte Faktorstufung (Vorgabe 0,1).
 *  3. Feinabgleich - fuer jede Ziffer wird der Faktor ausgerechnet, mit dem
 *     sie den noch fehlenden Betrag genau aufnaehme, und der beste Kandidat
 *     uebernommen. Ein einzelner Rasterschritt aendert den gerundeten Betrag
 *     mitunter gar nicht, deshalb wird gerechnet statt getastet.
 */

import {
  FAKTOR_RASTER, FAKTOR_SCHRITT, MAX_FAKTOR, MIN_FAKTOR, PUNKTWERT_E7, geld, faktorText,
} from './modelle.js';

export const STRATEGIEN = ['proportional', 'einheitlich', 'regelsatz'];

export const STRATEGIE_TEXT = {
  proportional: 'Proportional – vorhandene Faktoren skalieren',
  einheitlich: 'Einheitlich – ein Faktor für alle Ziffern',
  regelsatz: 'Regelsatzbezogen – Vielfaches des Regelsatzes',
};

const klemme = (wert, unten, oben) => Math.max(unten, Math.min(oben, wert));

/** Skalierungsparameter in Milliardsteln - siehe optimiereFaktoren. */
const EINS_E9 = 1000000000;

/** Ganzzahlige Division mit kaufmaennischer Rundung (ab 0,5 aufwaerts). */
function teileKaufmaennisch(zaehler, nenner) {
  if (zaehler < 0) return -Math.floor((-2 * zaehler + nenner) / (2 * nenner));
  return Math.floor((2 * zaehler + nenner) / (2 * nenner));
}

function grenzen(position, minFaktor, maxFaktor, rechtlicheGrenzen) {
  let unten = minFaktor;
  let oben = maxFaktor;
  if (rechtlicheGrenzen) {
    oben = Math.min(oben, position.hoechstsatz);
    unten = Math.min(unten, oben);
  }
  return [unten, oben];
}

function startwert(position, strategie) {
  if (strategie === 'regelsatz') return position.regelsatz;
  if (strategie === 'einheitlich') return 1000;
  return position.faktor > 0 ? position.faktor : 1000;
}

/**
 * @param {Position[]} positionen
 * @param {number} zielCent
 * @param {object} einstellungen  strategie, minFaktor, maxFaktor,
 *                                rechtlicheGrenzen, schrittweite, nachjustieren, anwenden
 */
export function optimiereFaktoren(positionen, zielCent, einstellungen = {}) {
  const {
    strategie = 'proportional',
    minFaktor = MIN_FAKTOR,
    maxFaktor = MAX_FAKTOR,
    rechtlicheGrenzen = false,
    nachjustieren = false,
    anwenden = true,
  } = einstellungen;
  const raster = Math.max(FAKTOR_RASTER, einstellungen.schrittweite ?? FAKTOR_SCHRITT);

  if (!STRATEGIEN.includes(strategie)) throw new Error(`Unbekannte Strategie: ${strategie}`);
  if (minFaktor > maxFaktor) throw new Error('Mindestfaktor größer als Höchstfaktor.');

  const variabel = positionen.filter((p) => !p.fixiert);
  const festSumme = positionen.filter((p) => p.fixiert).reduce((s, p) => s + p.betrag, 0);
  const spanne = variabel.map((p) => grenzen(p, minFaktor, maxFaktor, rechtlicheGrenzen));
  const minSumme = festSumme + variabel.reduce((s, p, i) => s + p.betragBei(spanne[i][0]), 0);
  const maxSumme = festSumme + variabel.reduce((s, p, i) => s + p.betragBei(spanne[i][1]), 0);
  const warnungen = [];

  const ergebnis = (faktoren, meldung) => {
    const summe = festSumme + variabel.reduce((s, p, i) => s + p.betragBei(faktoren[i]), 0);
    if (anwenden) variabel.forEach((p, i) => { p.faktor = faktoren[i]; });
    return {
      zielbetrag: zielCent, summe, abweichung: summe - zielCent,
      erreicht: summe === zielCent, minSumme, maxSumme, strategie, meldung, warnungen,
      faktoren,
    };
  };

  if (variabel.length === 0) {
    return ergebnis([], positionen.length
      ? 'Alle Ziffern sind fixiert – es bleibt nichts zu verteilen.'
      : 'Das Angebot enthält keine Positionen.');
  }
  if (zielCent < minSumme) {
    warnungen.push(`Zielbetrag liegt unter dem Minimum von ${geld(minSumme)} EUR.`);
    return ergebnis(spanne.map((g) => g[0]),
      `Zielbetrag ${geld(zielCent)} EUR ist zu niedrig; erreichbar sind mindestens ${geld(minSumme)} EUR.`);
  }
  if (zielCent > maxSumme) {
    warnungen.push(`Zielbetrag liegt über dem Maximum von ${geld(maxSumme)} EUR.`);
    return ergebnis(spanne.map((g) => g[1]),
      `Zielbetrag ${geld(zielCent)} EUR ist zu hoch; erreichbar sind höchstens ${geld(maxSumme)} EUR.`);
  }

  // Schritt 1: gemeinsamen Skalierungsfaktor per Intervallhalbierung suchen.
  // Der Parameter wird als Ganzzahl in Milliardsteln gefuehrt, damit die Suche
  // ohne Fliesskomma auskommt und Schritt fuer Schritt dieselben Faktoren
  // liefert wie das Schreibtischprogramm.
  const starts = variabel.map((p) => startwert(p, strategie));
  const faktorenBei = (lambdaE9) => starts.map(
    (start, i) => klemme(
      teileKaufmaennisch(start * lambdaE9, EINS_E9 * raster) * raster,
      spanne[i][0], spanne[i][1],
    ),
  );
  const summeBei = (lambdaE9) => {
    const f = faktorenBei(lambdaE9);
    return festSumme + variabel.reduce((s, p, i) => s + p.betragBei(f[i]), 0);
  };
  let unten = 0;
  let oben = 10 * EINS_E9;
  while (oben - unten > 1) {
    const mitte = Math.floor((unten + oben) / 2);
    if (summeBei(mitte) < zielCent) unten = mitte; else oben = mitte;
  }
  let faktoren = faktorenBei(oben);

  // Schritt 2/3: Restbetrag verteilen.
  let rest;
  [faktoren, rest] = feinabgleich(variabel, faktoren, spanne, zielCent - festSumme, raster);

  let nachgezogen = 0;
  if (rest !== 0 && nachjustieren && raster > FAKTOR_RASTER) {
    const vorher = faktoren.slice();
    [faktoren, rest] = feinabgleich(variabel, faktoren, spanne, zielCent - festSumme, FAKTOR_RASTER);
    nachgezogen = faktoren.filter((f, i) => f !== vorher[i]).length;
  }

  let meldung;
  if (rest === 0) {
    meldung = 'Zielbetrag exakt erreicht.';
    if (nachgezogen) {
      meldung += ` ${nachgezogen} Faktor(en) wurden dafür feiner als ${faktorText(raster)} gesetzt.`;
    }
  } else {
    const abweichung = `${-rest >= 0 ? '+' : '−'}${geld(Math.abs(rest))}`;
    meldung = `Nächstmöglicher Betrag im Faktorraster ${faktorText(raster)}: Abweichung ${abweichung} EUR.`;
    const [, feinRest] = feinabgleich(variabel, faktoren, spanne, zielCent - festSumme, FAKTOR_RASTER);
    if (!nachjustieren && feinRest === 0) {
      meldung += ' Mit feineren Faktoren wäre der Betrag exakt zu treffen.';
      warnungen.push(`Im Raster ${faktorText(raster)} bleibt ein Rest von ${abweichung} EUR.`);
    } else {
      meldung += ' Feiner geht es nicht: die Einzelbeträge werden je Leistung auf volle Cent'
        + ' gerundet, so dass nicht jede Summe darstellbar ist.';
      warnungen.push(`Der Zielbetrag ist mit diesen Ziffern nicht centgenau darstellbar (${abweichung} EUR).`);
    }
  }
  return ergebnis(faktoren, meldung);
}

function feinabgleich(positionen, faktorenEin, spanne, zielVariabel, raster) {
  const faktoren = faktorenEin.slice();
  const betraege = positionen.map((p, i) => p.betragBei(faktoren[i]));
  let rest = zielVariabel - betraege.reduce((s, b) => s + b, 0);

  for (let runde = 0; runde < 200 && rest !== 0; runde += 1) {
    let bester = null;
    for (let i = 0; i < positionen.length; i += 1) {
      const p = positionen[i];
      const nenner = p.punktzahl * PUNKTWERT_E7 * p.anzahl;
      if (nenner === 0) continue;
      // Faktor (in Tausendsteln), mit dem diese Ziffer den fehlenden Betrag
      // genau traefe - ganzzahlig gerechnet, damit das Ergebnis Zeichen fuer
      // Zeichen dem des Schreibtischprogramms entspricht.
      const zaehler = (betraege[i] + rest) * 100000000;
      const nennerRaster = nenner * raster;
      const mitte = teileKaufmaennisch(zaehler, nennerRaster) * raster;
      for (let versatz = -3; versatz <= 3; versatz += 1) {
        const kandidat = klemme(mitte + versatz * raster, spanne[i][0], spanne[i][1]);
        if (kandidat === faktoren[i]) continue;
        const neuerBetrag = p.betragBei(kandidat);
        const neuerRest = rest - (neuerBetrag - betraege[i]);
        const verbesserung = Math.abs(rest) - Math.abs(neuerRest);
        if (verbesserung > 0 && (bester === null || verbesserung > bester.verbesserung)) {
          bester = { verbesserung, i, kandidat, neuerBetrag, neuerRest };
        }
      }
    }
    if (bester === null) break;
    faktoren[bester.i] = bester.kandidat;
    betraege[bester.i] = bester.neuerBetrag;
    rest = bester.neuerRest;
  }
  return [faktoren, rest];
}
