/** Testfaelle des Rechenkerns der App. Aufruf: node --test app/tests/ */
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import {
  Angebot, MAX_FAKTOR, MIN_FAKTOR, Position,
  betragAusText, betragCent, faktorAusText, faktorText, geld,
} from '../js/modelle.js';
import { Katalog } from '../js/katalog.js';
import { Angebotsverzeichnis } from '../js/speicher.js';
import { optimiereFaktoren } from '../js/zielbetrag.js';
import { EigeneFehler, EigeneZiffern, katalogMitEigenen } from '../js/eigene.js';
import { angebotAlsXlsx, dateiname } from '../js/xlsx.js';

const wurzel = new URL('..', import.meta.url).pathname;
const katalog = Katalog.ausJson(JSON.parse(readFileSync(`${wurzel}daten/goae_katalog.json`, 'utf8')));

const leistung = (nummer, punkte, extra = {}) => ({
  nummer, bezeichnung: `Leistung ${nummer}`, punktzahl: punkte, abschnitt: 'B',
  klasse: 'a', regelsatz: 2300, hoechstsatz: 3500, gruppe: false, ...extra,
});

test('bekannte GOÄ-Beträge', () => {
  for (const [punkte, einfach, zweiDrei, dreiFuenf] of [
    [80, 466, 1072, 1632], [150, 874, 2011, 3060], [260, 1515, 3486, 5304],
  ]) {
    assert.equal(betragCent(punkte, 1000), einfach);
    assert.equal(betragCent(punkte, 2300), zweiDrei);
    assert.equal(betragCent(punkte, 3500), dreiFuenf);
  }
});

test('Anzahl vervielfacht den gerundeten Einzelbetrag', () => {
  const p = new Position({ ...leistung('1', 80), anzahl: 3, faktor: 2300 });
  assert.equal(p.betrag, 3 * 1072);
});

test('Darstellung von Beträgen und Faktoren', () => {
  assert.equal(geld(123450), '1.234,50');
  assert.equal(geld(5), '0,05');
  assert.equal(geld(-1072), '-10,72');
  assert.equal(faktorText(2300), '2,3');
  assert.equal(faktorText(3359), '3,359');
  assert.equal(faktorText(1000), '1,0');
});

test('Eingaben werden nachsichtig gelesen', () => {
  assert.equal(betragAusText('250'), 25000);
  assert.equal(betragAusText('250,50'), 25050);
  assert.equal(betragAusText('1.234,50'), 123450);
  assert.equal(betragAusText('1234.50 €'), 123450);
  assert.equal(betragAusText('viel'), null);
  assert.equal(faktorAusText('2,5'), 2500);
  assert.equal(faktorAusText('x'), null);
});

test('Hinweise nach § 12 GOÄ', () => {
  const p = new Position({ ...leistung('1', 80), faktor: 2800 });
  assert.match(p.hinweis(), /Begründung/);
  p.begruendung = 'erhöhter Zeitaufwand';
  assert.equal(p.hinweis(), '');
  const labor = new Position({ ...leistung('3511', 50, { klasse: 'l', regelsatz: 1150, hoechstsatz: 1300 }), faktor: 2000 });
  assert.match(labor.hinweis(), /Höchstsatz/);
});

test('Summen und Spanne eines Angebots', () => {
  const a = new Angebot({ name: 'Test' });
  a.positionen.push(new Position({ ...leistung('1', 80), faktor: 2300 }));
  a.positionen.push(new Position({ ...leistung('8', 260), anzahl: 2, faktor: 2300 }));
  assert.equal(a.summeEinfach, 466 + 2 * 1515);
  assert.equal(a.summe23, 1072 + 2 * 3486);
  assert.equal(a.summe35, 1632 + 2 * 5304);
  assert.equal(a.punkte, 80 + 520);
  a.positionen[0].fixiert = true;
  const [unten, oben] = a.spanne();
  assert.equal(unten, 1072 + 2 * 1515);
  assert.equal(oben, 1072 + 2 * 5304);
});

test('mitgelieferter Katalog', () => {
  assert.ok(katalog.anzahl > 2700);
  assert.equal(katalog.hole('1').punktzahl, 80);
  assert.equal(katalog.hole('3511').klasse, 'l');
  assert.equal(katalog.hole('437').klasse, 'l');   // § 5 Abs. 4 nennt Nr. 437
  assert.equal(katalog.hole('650').klasse, 't');   // in Abschnitt A genannt
  assert.equal(katalog.hole('652').klasse, 'a');
  assert.equal(katalog.suche('gibtesnicht').gesamt, 0);
  assert.equal(katalog.suche('1').liste[0].nummer, '1');
  assert.throws(() => katalog.hole('99999'));
});

test('Punktzahlen aus Sammelpositionen', () => {
  // Diese Werte waren einmal falsch - sie stammen aus der Überschrift der
  // Sammelposition, nicht von der davorstehenden Nummer.
  for (const [nummer, punkte] of [
    ['3504', 60], ['3514', 70], ['4030', 250], ['4022', 250], ['4023', 250],
    ['4031', 250], ['4032', 250], ['4705', 120], ['4640', 250], ['K 1', 120],
  ]) {
    assert.equal(katalog.hole(nummer).punktzahl, punkte, `Ziffer ${nummer}`);
  }
  assert.equal(katalog.hole('3514').herkunft, 'sammel');
});

test('TSH ergibt den erwarteten Betrag', () => {
  const tsh = katalog.hole('4030');
  const p = new Position({ ...tsh, faktor: 1150 });
  assert.equal(geld(new Position({ ...tsh, faktor: 1000 }).betrag), '14,57');
  assert.equal(geld(p.betrag), '16,76');
  assert.equal(tsh.klasse, 'l');
});

test('Hundertsatz-Zuschläge sind nicht enthalten', () => {
  // 441 und 5298 werden als Hundertsatz der Bezugsleistung berechnet.
  for (const nummer of ['441', '5298']) assert.throws(() => katalog.hole(nummer));
});

test('Suche über mehrere Wörter', () => {
  const treffer = katalog.suche('ultraschall organs');
  assert.ok(treffer.gesamt >= 1);
  assert.ok(treffer.liste.some((l) => l.nummer === '410'));
});

test('Zielbetrag wird centgenau erreicht', () => {
  // Erreichbar sind mit diesen vier Ziffern rund 40,33 bis 141,17 EUR.
  for (const ziel of [6000, 9999, 12345, 14000]) {
    const positionen = ['1', '8', '650', '410'].map(
      (nr) => Position.ausLeistung(katalog.hole(nr)),
    );
    const erg = optimiereFaktoren(positionen, ziel, { nachjustieren: true });
    assert.equal(erg.summe, ziel, `Ziel ${ziel}: ${erg.meldung}`);
    assert.ok(erg.erreicht);
  }
});

test('Faktoren bleiben immer zwischen 1,0 und 3,5', () => {
  for (const ziel of [1000, 6000, 15000, 100000, 100]) {
    const positionen = ['1', '8', '650', '410'].map((nr) => Position.ausLeistung(katalog.hole(nr)));
    optimiereFaktoren(positionen, ziel);
    for (const p of positionen) {
      assert.ok(p.faktor >= MIN_FAKTOR && p.faktor <= MAX_FAKTOR, `${p.nummer}: ${p.faktor}`);
    }
  }
});

test('fixierte Positionen bleiben unverändert', () => {
  const positionen = ['1', '8', '650', '410'].map((nr) => Position.ausLeistung(katalog.hole(nr)));
  positionen[0].faktor = 1700;
  positionen[0].fixiert = true;
  const erg = optimiereFaktoren(positionen, 12000, { nachjustieren: true });
  assert.equal(positionen[0].faktor, 1700);
  assert.ok(erg.erreicht, erg.meldung);
});

test('unerreichbare Zielbeträge werden gemeldet', () => {
  const positionen = [Position.ausLeistung(katalog.hole('1'))];
  const hoch = optimiereFaktoren(positionen, 500000);
  assert.equal(hoch.erreicht, false);
  assert.match(hoch.meldung, /zu hoch/);
  assert.equal(positionen[0].faktor, MAX_FAKTOR);
  const niedrig = optimiereFaktoren(positionen, 10);
  assert.match(niedrig.meldung, /zu niedrig/);
  assert.equal(positionen[0].faktor, MIN_FAKTOR);
});

test('gesetzliche Höchstsätze werden beachtet', () => {
  const positionen = ['1', '3511', '650'].map((nr) => Position.ausLeistung(katalog.hole(nr)));
  optimiereFaktoren(positionen, 4500, { rechtlicheGrenzen: true });
  assert.ok(positionen[1].faktor <= 1300);
  assert.ok(positionen[2].faktor <= 2500);
});

test('Zehntelraster liefert Zehntelfaktoren', () => {
  const positionen = ['1', '8', '410'].map((nr) => Position.ausLeistung(katalog.hole(nr)));
  optimiereFaktoren(positionen, 12000);
  for (const p of positionen) assert.equal(p.faktor % 100, 0, `${p.nummer}: ${p.faktor}`);
});

test('Ablage: speichern, laden, kopieren, löschen', () => {
  const speicher = new Map();
  const verzeichnis = new Angebotsverzeichnis({
    getItem: (k) => speicher.get(k) ?? null,
    setItem: (k, v) => speicher.set(k, v),
  });
  const a = new Angebot({ name: 'Mein Angebot', patient: 'Frau Muster' });
  a.positionen.push(Position.ausLeistung(katalog.hole('1')));
  verzeichnis.speichern(a);
  assert.equal(verzeichnis.alle().length, 1);
  const geladen = verzeichnis.laden(a.id);
  assert.equal(geladen.patient, 'Frau Muster');
  assert.equal(geladen.summe, a.summe);

  a.positionen.push(Position.ausLeistung(katalog.hole('8')));
  verzeichnis.speichern(a);
  assert.equal(verzeichnis.alle().length, 1, 'kein zweiter Eintrag beim erneuten Speichern');
  assert.equal(verzeichnis.laden(a.id).positionen.length, 2);

  verzeichnis.kopieren(a.id, 'Kopie');
  assert.equal(verzeichnis.alle().length, 2);
  verzeichnis.loeschen(a.id);
  assert.equal(verzeichnis.alle().length, 1);
  assert.equal(verzeichnis.alle()[0].name, 'Kopie');
});

test('beschädigte Ablage blockiert nicht', () => {
  const verzeichnis = new Angebotsverzeichnis({ getItem: () => '{kein json', setItem: () => {} });
  assert.deepEqual(verzeichnis.alle(), []);
});

test('Excel-Datei ist ein gültiges ZIP mit den erwarteten Teilen', async () => {
  const a = new Angebot({ name: 'Excel & <Test>', patient: 'Muster' });
  a.positionen.push(Position.ausLeistung(katalog.hole('1')));
  a.zielbetrag = 1000;
  const puffer = Buffer.from(await angebotAlsXlsx(a).arrayBuffer());
  assert.equal(puffer.readUInt32LE(0), 0x04034b50, 'ZIP-Signatur');
  const text = puffer.toString('latin1');
  for (const teil of ['[Content_Types].xml', 'xl/workbook.xml', 'xl/styles.xml',
    'xl/worksheets/sheet1.xml']) {
    assert.ok(text.includes(teil), `${teil} fehlt`);
  }
  assert.ok(text.includes('&amp;'), 'Sonderzeichen maskiert');
  assert.equal(dateiname('Vorsorge für Männer / 2026'), 'Vorsorge_fuer_Maenner_2026.xlsx');
});

/* ------------------------------------------------- Eigene Analogziffern */

/** Ablage im Arbeitsspeicher - ersetzt localStorage in den Testfällen. */
function ablage() {
  const inhalt = new Map();
  return { getItem: (k) => inhalt.get(k) ?? null, setItem: (k, v) => inhalt.set(k, v) };
}

test('Analogziffer übernimmt die Werte der herangezogenen Ziffer', () => {
  const eigene = new EigeneZiffern(ablage());
  const vorlage = katalog.hole('1800');
  const neu = eigene.anlegen(katalog, 'Stoßwellentherapie', '1800');
  assert.equal(neu.nummer, 'A1800');
  assert.equal(neu.analogZu, '1800');
  assert.equal(neu.punktzahl, vorlage.punktzahl);
  assert.equal(neu.klasse, vorlage.klasse);
  assert.equal(neu.regelsatz, vorlage.regelsatz);
  assert.equal(neu.herkunft, 'analog');
});

test('eigene Nummer und Bereinigung der Bezeichnung', () => {
  const eigene = new EigeneZiffern(ablage());
  const neu = eigene.anlegen(katalog, '  Akupunktur,   30 Minuten ', '269', 'A-AKU');
  assert.equal(neu.nummer, 'A-AKU');
  assert.equal(neu.bezeichnung, 'Akupunktur, 30 Minuten');
});

test('abgelehnte Eingaben', () => {
  const eigene = new EigeneZiffern(ablage());
  eigene.anlegen(katalog, 'Erste', '1800');
  for (const [text, vorlage, nummer] of [
    ['', '1800', ''], ['Zweite', '99999', ''], ['Zweite', '1800', ''],
    ['Zweite', '1800', '1'], ['Zweite', '1800', 'A/B;C'], ['Zweite', '1800', 'A'.repeat(20)],
  ]) {
    assert.throws(() => eigene.anlegen(katalog, text, vorlage, nummer), EigeneFehler,
      `${text}/${vorlage}/${nummer}`);
  }
});

test('löschen, unabhängig von Groß- und Kleinschreibung', () => {
  const eigene = new EigeneZiffern(ablage());
  eigene.anlegen(katalog, 'Stoßwellentherapie', '1800');
  eigene.loeschen('a1800');
  assert.equal(eigene.anzahl, 0);
  assert.throws(() => eigene.loeschen('A1800'), EigeneFehler);
});

test('Überlagerung lässt den amtlichen Katalog unberührt', () => {
  const eigene = new EigeneZiffern(ablage());
  eigene.anlegen(katalog, 'Stoßwellentherapie', '1800');
  const vorher = katalog.anzahl;
  const zusammen = katalogMitEigenen(katalog, eigene);
  assert.equal(zusammen.anzahl, vorher + 1);
  assert.equal(katalog.anzahl, vorher, 'der amtliche Katalog wurde verändert');
  assert.throws(() => katalog.hole('A1800'));
  assert.equal(zusammen.hole('A1800').analogZu, '1800');
});

test('eigene Ziffern stehen in der Suche vorn', () => {
  const eigene = new EigeneZiffern(ablage());
  eigene.anlegen(katalog, 'Stoßwellentherapie', '1800');
  const zusammen = katalogMitEigenen(katalog, eigene);
  assert.equal(zusammen.suche('stoßwellen').liste[0].nummer, 'A1800');
});

test('Rechnungsvermerk nach § 12 Abs. 4 GOÄ', () => {
  const eigene = new EigeneZiffern(ablage());
  const neu = eigene.anlegen(katalog, 'Stoßwellentherapie', '1800');
  const p = Position.ausLeistung(neu);
  assert.equal(p.analogvermerk, 'entsprechend Nr. 1800 GOÄ');
  assert.equal(p.leistungstext, 'Stoßwellentherapie, entsprechend Nr. 1800 GOÄ');
  const ohne = Position.ausLeistung(katalog.hole('1'));
  assert.equal(ohne.analogvermerk, '');
  assert.equal(ohne.leistungstext, ohne.bezeichnung);
});

test('Analogziffer übersteht das Speichern eines Angebots', () => {
  const eigene = new EigeneZiffern(ablage());
  const neu = eigene.anlegen(katalog, 'Stoßwellentherapie', '1800');
  const a = new Angebot({ name: 'Privat' });
  a.positionen.push(Position.ausLeistung(neu));
  const kopie = new Angebot(JSON.parse(JSON.stringify(a.toJSON())));
  assert.equal(kopie.positionen[0].analogZu, '1800');
  assert.equal(kopie.positionen[0].leistungstext, a.positionen[0].leistungstext);
});

test('Excel trägt den Analogvermerk', async () => {
  const eigene = new EigeneZiffern(ablage());
  const neu = eigene.anlegen(katalog, 'Stoßwellentherapie', '1800');
  const a = new Angebot({ name: 'Privat' });
  a.positionen.push(Position.ausLeistung(neu));
  const puffer = Buffer.from(await angebotAlsXlsx(a).arrayBuffer());
  assert.ok(puffer.toString('utf8').includes('entsprechend Nr. 1800 GO'));
});
