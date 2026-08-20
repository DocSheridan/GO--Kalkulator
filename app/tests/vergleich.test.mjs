/**
 * Vergleicht die Faktorverteilung der App mit der des Schreibtischprogramms.
 * Die Pruefvektoren stammen aus werkzeuge/pruefvektoren.py.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Position } from '../js/modelle.js';
import { optimiereFaktoren } from '../js/zielbetrag.js';

// Unter "node --test" ist process.argv nicht verlaesslich - Pfad daher fest,
// abweichende Dateien ueber die Umgebungsvariable PRUEFVEKTOREN.
const datei = process.env.PRUEFVEKTOREN
  ?? new URL('pruefvektoren.json', import.meta.url).pathname;
const faelle = JSON.parse(readFileSync(datei, 'utf8'));
let gleich = 0;
const abweichungen = [];

for (const fall of faelle) {
  const positionen = fall.positionen.map((p) => new Position(p));
  const erg = optimiereFaktoren(positionen, fall.zielCent, {
    strategie: fall.strategie,
    schrittweite: fall.schrittweite,
    nachjustieren: fall.nachjustieren,
    rechtlicheGrenzen: fall.rechtlicheGrenzen,
  });
  const faktoren = positionen.map((p) => p.faktor);
  const passt = erg.summe === fall.erwartet.summeCent
    && JSON.stringify(faktoren) === JSON.stringify(fall.erwartet.faktoren)
    && erg.erreicht === fall.erwartet.erreicht;
  if (passt) gleich += 1;
  else if (abweichungen.length < 5) {
    abweichungen.push({
      ziel: fall.zielCent, strategie: fall.strategie, raster: fall.schrittweite,
      nachjustieren: fall.nachjustieren, rechtlich: fall.rechtlicheGrenzen,
      python: fall.erwartet, javascript: { summeCent: erg.summe, faktoren, erreicht: erg.erreicht },
      positionen: fall.positionen.map((p) => `${p.nummer}x${p.anzahl}${p.fixiert ? ' fix' : ''}`),
    });
  }
}

test(`App und Programm rechnen gleich (${faelle.length} Fälle)`, () => {
  for (const a of abweichungen) console.error(JSON.stringify(a, null, 1));
  assert.equal(gleich, faelle.length,
    `${faelle.length - gleich} Fälle weichen ab – App und Schreibtischprogramm laufen auseinander.`);
});
