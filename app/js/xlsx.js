/**
 * Excel-Ausgabe (.xlsx) ohne Fremdbibliothek.
 *
 * Eine .xlsx-Datei ist ein ZIP-Archiv mit XML-Dateien. Da die Tabellen klein
 * sind, werden die Eintraege unkomprimiert abgelegt (ZIP-Methode 0) - das
 * spart eine Komprimierungsbibliothek und bleibt vollstaendig lesbar.
 */

import { excel as exf, GRAU, GRUEN, GRUEN_TON, WEISS } from './farben.js';
import { faktorText } from './modelle.js';

const KRZ = (() => {
  const tabelle = new Uint32Array(256);
  for (let i = 0; i < 256; i += 1) {
    let c = i;
    for (let k = 0; k < 8; k += 1) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    tabelle[i] = c >>> 0;
  }
  return tabelle;
})();

function crc32(daten) {
  let c = 0xffffffff;
  for (let i = 0; i < daten.length; i += 1) c = KRZ[(c ^ daten[i]) & 0xff] ^ (c >>> 8);
  return (c ^ 0xffffffff) >>> 0;
}

function zipZeit(datum) {
  const zeit = ((datum.getHours() << 11) | (datum.getMinutes() << 5) | (datum.getSeconds() >> 1)) & 0xffff;
  const tag = (((datum.getFullYear() - 1980) << 9) | ((datum.getMonth() + 1) << 5) | datum.getDate()) & 0xffff;
  return { zeit, tag };
}

/** Baut ein ZIP-Archiv aus {name, text}-Eintraegen. */
export function packe(eintraege) {
  const kodierer = new TextEncoder();
  const jetzt = zipZeit(new Date());
  const teile = [];
  const verzeichnis = [];
  let versatz = 0;

  const schreibe = (laenge, werte) => {
    const puffer = new Uint8Array(laenge);
    const sicht = new DataView(puffer.buffer);
    werte.forEach(([stelle, groesse, wert]) => {
      if (groesse === 2) sicht.setUint16(stelle, wert, true);
      else sicht.setUint32(stelle, wert, true);
    });
    return puffer;
  };

  for (const eintrag of eintraege) {
    const name = kodierer.encode(eintrag.name);
    const inhalt = kodierer.encode(eintrag.text);
    const pruefsumme = crc32(inhalt);
    const kopf = schreibe(30, [
      [0, 4, 0x04034b50], [4, 2, 20], [6, 2, 0x0800], [8, 2, 0],
      [10, 2, jetzt.zeit], [12, 2, jetzt.tag], [14, 4, pruefsumme],
      [18, 4, inhalt.length], [22, 4, inhalt.length],
      [26, 2, name.length], [28, 2, 0],
    ]);
    teile.push(kopf, name, inhalt);
    const zentral = schreibe(46, [
      [0, 4, 0x02014b50], [4, 2, 20], [6, 2, 20], [8, 2, 0x0800], [10, 2, 0],
      [12, 2, jetzt.zeit], [14, 2, jetzt.tag], [16, 4, pruefsumme],
      [20, 4, inhalt.length], [24, 4, inhalt.length],
      [28, 2, name.length], [30, 2, 0], [32, 2, 0], [34, 2, 0], [36, 2, 0],
      [38, 4, 0], [42, 4, versatz],
    ]);
    verzeichnis.push(zentral, name);
    versatz += kopf.length + name.length + inhalt.length;
  }

  const verzeichnisLaenge = verzeichnis.reduce((s, t) => s + t.length, 0);
  const ende = schreibe(22, [
    [0, 4, 0x06054b50], [4, 2, 0], [6, 2, 0],
    [8, 2, eintraege.length], [10, 2, eintraege.length],
    [12, 4, verzeichnisLaenge], [16, 4, versatz], [20, 2, 0],
  ]);
  return new Blob([...teile, ...verzeichnis, ende],
    { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
}

const maskiere = (text) => String(text)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
  .replace(/"/g, '&quot;');

const STIL = { normal: 0, titel: 1, kopf: 2, euro: 3, faktor: 4, fett: 5, summe: 6, hinweis: 7, zahl: 8, klein: 9, euroHell: 10 };

// Die Farben stammen aus farben.js; der erzeugte Text ist Zeichen fuer
// Zeichen derselbe wie im Schreibtischprogramm (goae_kalkulator/excel.py) -
// siehe Testfaelle.
const STYLES = `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="2">
<numFmt numFmtId="164" formatCode="#,##0.00\\ &quot;EUR&quot;"/>
<numFmt numFmtId="165" formatCode="0.00#"/>
</numFmts>
<fonts count="6">
<font><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="15"/><color rgb="${exf(GRUEN)}"/><name val="Calibri"/></font>
<font><i/><sz val="9"/><color rgb="${exf(GRAU)}"/><name val="Calibri"/></font>
<font><b/><sz val="11"/><color rgb="${exf(WEISS)}"/><name val="Calibri"/></font>
<font><sz val="10"/><color rgb="${exf(GRAU)}"/><name val="Calibri"/></font>
</fonts>
<fills count="4">
<fill><patternFill patternType="none"/></fill>
<fill><patternFill patternType="gray125"/></fill>
<fill><patternFill patternType="solid"><fgColor rgb="${exf(GRUEN)}"/><bgColor indexed="64"/></patternFill></fill>
<fill><patternFill patternType="solid"><fgColor rgb="${exf(GRUEN_TON)}"/><bgColor indexed="64"/></patternFill></fill>
</fills>
<borders count="2">
<border><left/><right/><top/><bottom/><diagonal/></border>
<border><left/><right/><top style="thin"><color rgb="${exf(GRUEN)}"/></top><bottom/><diagonal/></border>
</borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="11">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="0" fontId="4" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1" applyAlignment="1"><alignment vertical="center" wrapText="1"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1"/>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="164" fontId="1" fillId="3" borderId="1" xfId="0" applyNumberFormat="1" applyFont="1" applyFill="1" applyBorder="1"/>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment wrapText="1"/></xf>
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center"/></xf>
<xf numFmtId="0" fontId="5" fillId="0" borderId="0" xfId="0" applyFont="1"/>
<xf numFmtId="164" fontId="5" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1"/>
</cellXfs>
<cellStyles count="1"><cellStyle name="Standard" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>`;

const spaltenname = (index) => {
  let name = '';
  let i = index + 1;
  while (i > 0) { const rest = (i - 1) % 26; name = String.fromCharCode(65 + rest) + name; i = Math.floor((i - 1) / 26); }
  return name;
};

function blattXml(zeilen, breiten) {
  const cols = breiten.map((b, i) => `<col min="${i + 1}" max="${i + 1}" width="${b}" customWidth="1"/>`).join('');
  const inhalt = zeilen.map((zeile, nr) => {
    const zellen = zeile.map((zelle, s) => {
      if (zelle === null || zelle === undefined) return '';
      const ref = `${spaltenname(s)}${nr + 1}`;
      const stil = STIL[zelle.stil ?? 'normal'] ?? 0;
      if (zelle.wert === null || zelle.wert === '') return `<c r="${ref}" s="${stil}"/>`;
      if (typeof zelle.wert === 'number') return `<c r="${ref}" s="${stil}"><v>${zelle.wert}</v></c>`;
      return `<c r="${ref}" s="${stil}" t="inlineStr"><is><t xml:space="preserve">${maskiere(zelle.wert)}</t></is></c>`;
    }).join('');
    return zellen ? `<row r="${nr + 1}">${zellen}</row>` : `<row r="${nr + 1}"/>`;
  }).join('');
  return `<?xml version="1.0" encoding="UTF-8" standalone="yes"?>`
    + `<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">`
    + `<cols>${cols}</cols><sheetData>${inhalt}</sheetData></worksheet>`;
}

const blattname = (name) => (String(name).replace(/[[\]:*?/\\]/g, ' ').trim() || 'Angebot').slice(0, 31);

/** Erzeugt die .xlsx-Datei zu einem Angebot als Blob. */
export function angebotAlsXlsx(angebot) {
  const e = (cent) => cent / 100;
  const zeilen = [
    [{ wert: angebot.name || 'Angebot', stil: 'titel' }],
    [{ wert: [angebot.patient && `Patient/in: ${angebot.patient}`, angebot.beschreibung,
      `Stand: ${new Date(angebot.geaendert).toLocaleString('de-DE')}`].filter(Boolean).join(' | '), stil: 'klein' }],
    [],
    ['Ziffer', 'Leistung', 'Anz.', 'Punkte', '1,0-fach', '2,3-fach', '3,5-fach', 'Faktor', 'Betrag', 'Begründung / Hinweis']
      .map((t) => ({ wert: t, stil: 'kopf' })),
  ];
  for (const p of angebot.positionen) {
    zeilen.push([
      { wert: p.nummer }, { wert: p.leistungstext },
      { wert: p.anzahl, stil: 'zahl' }, { wert: p.punktzahl * p.anzahl, stil: 'zahl' },
      { wert: e(p.einfachsatz), stil: 'euroHell' }, { wert: e(p.satz23), stil: 'euroHell' },
      { wert: e(p.satz35), stil: 'euroHell' },
      { wert: p.faktor / 1000, stil: 'faktor' }, { wert: e(p.betrag), stil: 'euro' },
      { wert: p.begruendung || p.hinweis(), stil: 'hinweis' },
    ]);
  }
  zeilen.push([
    { wert: 'Summe', stil: 'fett' }, { wert: `${angebot.positionen.length} Position(en)`, stil: 'fett' },
    null, { wert: angebot.punkte, stil: 'zahl' },
    { wert: e(angebot.summeEinfach), stil: 'summe' }, { wert: e(angebot.summe23), stil: 'summe' },
    { wert: e(angebot.summe35), stil: 'summe' }, null, { wert: e(angebot.summe), stil: 'summe' },
  ]);
  zeilen.push([]);
  if (angebot.zielbetrag !== null) {
    zeilen.push([{ wert: 'Zielbetrag', stil: 'fett' }, null, null, null, null, null, null, null,
      { wert: e(angebot.zielbetrag), stil: 'euro' }]);
    zeilen.push([{ wert: 'Abweichung', stil: 'fett' }, null, null, null, null, null, null, null,
      { wert: e(angebot.summe - angebot.zielbetrag), stil: 'euro' }]);
    zeilen.push([]);
  }
  for (const h of angebot.hinweise()) zeilen.push([{ wert: h, stil: 'hinweis' }]);
  zeilen.push([{ wert: 'Berechnung nach GOÄ: Punktzahl × Punktwert (0,0582873 EUR) × Faktor. '
    + 'Faktoren oberhalb des Regelsatzes sind schriftlich zu begründen (§ 12 GOÄ). Angaben ohne Gewähr.',
  stil: 'hinweis' }]);

  const blatt = blattXml(zeilen, [10, 46, 6, 8, 12, 12, 12, 9, 13, 34]);
  return packe([
    { name: '[Content_Types].xml',
      text: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        + '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        + '<Default Extension="xml" ContentType="application/xml"/>'
        + '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        + '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        + '</Types>' },
    { name: '_rels/.rels',
      text: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        + '</Relationships>' },
    { name: 'xl/workbook.xml',
      text: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        + 'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        + `<sheets><sheet name="${maskiere(blattname(angebot.name))}" sheetId="1" r:id="rId1"/></sheets></workbook>` },
    { name: 'xl/_rels/workbook.xml.rels',
      text: '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        + '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        + '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        + '</Relationships>' },
    { name: 'xl/styles.xml', text: STYLES },
    { name: 'xl/worksheets/sheet1.xml', text: blatt },
  ]);
}

/** Dateiname aus dem Angebotsnamen. */
export function dateiname(name) {
  const umlaute = { ä: 'ae', ö: 'oe', ü: 'ue', ß: 'ss', Ä: 'Ae', Ö: 'Oe', Ü: 'Ue' };
  const text = String(name || 'Angebot').replace(/[äöüßÄÖÜ]/g, (z) => umlaute[z]);
  return `${text.replace(/[^\w\s.-]/g, '').replace(/[\s_]+/g, '_').replace(/^[._-]+|[._-]+$/g, '') || 'Angebot'}.xlsx`;
}
