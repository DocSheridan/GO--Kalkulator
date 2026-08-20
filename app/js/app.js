/** Bedienung der GOAE-Kalkulator-App. */

import {
  Angebot, MAX_FAKTOR, MIN_FAKTOR, Position,
  betragAusText, faktorAusText, faktorText, geld,
} from './modelle.js';
import { Katalog } from './katalog.js';
import { EigeneFehler, EigeneZiffern, katalogMitEigenen } from './eigene.js';
import { Angebotsverzeichnis } from './speicher.js';
import { STRATEGIEN, STRATEGIE_TEXT, optimiereFaktoren } from './zielbetrag.js';
import { angebotAlsXlsx, dateiname } from './xlsx.js';

const $ = (auswahl) => document.querySelector(auswahl);
const verzeichnis = new Angebotsverzeichnis();
const eigene = new EigeneZiffern();

let amtlich = null;   // das amtliche Verzeichnis
let katalog = null;   // amtlich, ergänzt um die eigenen Analogziffern
let angebot = new Angebot({ name: '' });
let gesichert = true;
let sucheGrenze = 40;

/* ------------------------------------------------------------ Hilfsmittel */

function melde(text, dauer = 2600) {
  const feld = $('#hinweisfeld');
  feld.textContent = text;
  feld.hidden = false;
  clearTimeout(melde.uhr);
  melde.uhr = setTimeout(() => { feld.hidden = true; }, dauer);
}

/** Ersatz fuer prompt(): in installierten Web-Apps ist prompt() teils gesperrt. */
function frage(titel, text, vorgabe = '') {
  return new Promise((fertig) => {
    const dialog = $('#dialog');
    $('#dialog-titel').textContent = titel;
    $('#dialog-text').textContent = text;
    const eingabe = $('#dialog-eingabe');
    eingabe.hidden = vorgabe === null;
    eingabe.value = vorgabe ?? '';
    const beim = () => {
      dialog.removeEventListener('close', beim);
      fertig(dialog.returnValue === 'ok' ? (vorgabe === null ? true : eingabe.value) : null);
    };
    dialog.addEventListener('close', beim);
    dialog.showModal();
    if (!eingabe.hidden) setTimeout(() => eingabe.select(), 50);
  });
}

const bestaetige = (titel, text) => frage(titel, text, null);

function wechsle(ziel) {
  for (const name of ['angebot', 'katalog', 'gespeichert']) {
    $(`#ansicht-${name}`).hidden = name !== ziel;
  }
  document.querySelectorAll('.reiter-knopf').forEach((k) => {
    k.classList.toggle('aktiv', k.dataset.wechsel === ziel);
  });
  // Die Summe gehoert zum laufenden Angebot - im Katalog waechst sie beim
  // Uebernehmen sichtbar mit, in der Ablage hat sie nichts zu suchen.
  $('#summenleiste').hidden = ziel === 'gespeichert';
  if (ziel === 'gespeichert') zeigeGespeicherte();
  if (ziel === 'katalog') setTimeout(() => $('#feld-suche').focus(), 60);
  window.scrollTo({ top: 0 });
}

/* -------------------------------------------------------------- Darstellung */

function zeichnePositionen() {
  const behaelter = $('#positionen');
  behaelter.textContent = '';
  $('#leer-hinweis').hidden = angebot.positionen.length > 0;
  $('#block-ziel').hidden = angebot.positionen.length === 0;

  angebot.positionen.forEach((p, index) => {
    const karte = document.createElement('article');
    karte.className = 'position';
    if (p.ueberHoechstsatz) karte.classList.add('fehler');
    else if (p.ueberRegelsatz && !p.begruendung) karte.classList.add('warnung');
    if (p.fixiert) karte.classList.add('fixiert');
    karte.dataset.index = String(index);

    const kopf = document.createElement('div');
    kopf.className = 'position-kopf';
    kopf.innerHTML = `<span class="ziffer">${p.nummer}</span>`
      + `<span class="legende">${maskiere(p.bezeichnung)}</span>`;
    const weg = document.createElement('button');
    weg.type = 'button';
    weg.className = 'position-loeschen';
    weg.setAttribute('aria-label', `Ziffer ${p.nummer} entfernen`);
    weg.textContent = '×';
    weg.addEventListener('click', () => {
      angebot.positionen.splice(index, 1);
      geaendert();
      melde(`Ziffer ${p.nummer} entfernt`);
    });
    kopf.append(weg);
    karte.append(kopf);

    const saetze = document.createElement('div');
    saetze.className = 'saetze';
    for (const [beschriftung, milli, betrag] of [
      ['1,0-fach', 1000, p.einfachsatz], ['2,3-fach', 2300, p.satz23], ['3,5-fach', 3500, p.satz35],
    ]) {
      const knopf = document.createElement('button');
      knopf.type = 'button';
      knopf.className = 'satz' + (p.faktor === milli ? ' aktiv' : '');
      knopf.innerHTML = `<b>${beschriftung}</b>${geld(betrag)}`;
      knopf.addEventListener('click', () => setzeFaktor(index, milli));
      saetze.append(knopf);
    }
    karte.append(saetze);

    const fuss = document.createElement('div');
    fuss.className = 'position-fuss';
    const stufe = document.createElement('div');
    stufe.className = 'stufe';
    const minus = knopfMit('−', `Faktor der Ziffer ${p.nummer} verringern`,
      () => setzeFaktor(index, p.faktor - 100));
    const eingabe = document.createElement('input');
    eingabe.type = 'text';
    eingabe.inputMode = 'decimal';
    eingabe.value = faktorText(p.faktor);
    eingabe.setAttribute('aria-label', `Faktor der Ziffer ${p.nummer}`);
    eingabe.addEventListener('change', () => {
      const wert = faktorAusText(eingabe.value);
      if (wert === null) { eingabe.value = faktorText(p.faktor); melde('Bitte eine Zahl eingeben.'); return; }
      setzeFaktor(index, wert);
    });
    const plus = knopfMit('+', `Faktor der Ziffer ${p.nummer} erhöhen`,
      () => setzeFaktor(index, p.faktor + 100));
    stufe.append(minus, eingabe, plus);

    const fix = document.createElement('button');
    fix.type = 'button';
    fix.className = 'fix-knopf';
    fix.textContent = '🔒';
    fix.setAttribute('aria-pressed', String(p.fixiert));
    fix.title = 'Faktor bei der Zielbetragsrechnung festhalten';
    fix.setAttribute('aria-label', `Ziffer ${p.nummer} ${p.fixiert ? 'freigeben' : 'fixieren'}`);
    fix.addEventListener('click', () => {
      p.fixiert = !p.fixiert;
      geaendert();
      melde(p.fixiert ? `Ziffer ${p.nummer} bleibt bei ${faktorText(p.faktor)}` : `Ziffer ${p.nummer} wird wieder angepasst`);
    });

    const betrag = document.createElement('span');
    betrag.className = 'position-betrag';
    betrag.textContent = `${geld(p.betrag)} €`;
    fuss.append(stufe, fix, betrag);
    karte.append(fuss);

    const anzahl = document.createElement('div');
    anzahl.className = 'anzahl-zeile';
    const anzahlKnopf = document.createElement('button');
    anzahlKnopf.type = 'button';
    anzahlKnopf.textContent = `${p.anzahl} ×`;
    anzahlKnopf.setAttribute('aria-label', `Anzahl der Ziffer ${p.nummer} ändern`);
    anzahlKnopf.addEventListener('click', async () => {
      const wert = await frage('Anzahl', `Wie oft wurde Ziffer ${p.nummer} erbracht?`, String(p.anzahl));
      if (wert === null) return;
      const zahl = parseInt(wert, 10);
      if (!Number.isInteger(zahl) || zahl < 1) { melde('Bitte eine ganze Zahl ab 1 eingeben.'); return; }
      p.anzahl = zahl;
      geaendert();
    });
    const begruendungKnopf = document.createElement('button');
    begruendungKnopf.type = 'button';
    begruendungKnopf.textContent = p.begruendung ? 'Begründung ändern' : 'Begründung';
    begruendungKnopf.addEventListener('click', async () => {
      const wert = await frage('Begründung nach § 12 GOÄ',
        `Warum wird Ziffer ${p.nummer} über dem Regelsatz abgerechnet?`, p.begruendung);
      if (wert === null) return;
      p.begruendung = wert.trim();
      geaendert();
    });
    anzahl.append(anzahlKnopf, ' ', begruendungKnopf,
      document.createTextNode(`  ·  ${p.punktzahl * p.anzahl} Punkte  ·  ${p.abschnitt || '–'}`));
    karte.append(anzahl);

    const hinweis = p.begruendung || p.hinweis();
    if (hinweis) {
      const zeile = document.createElement('p');
      zeile.className = 'position-hinweis' + (p.begruendung || p.gruppe ? ' neutral' : '');
      zeile.textContent = hinweis;
      karte.append(zeile);
    }
    behaelter.append(karte);
  });
}

function knopfMit(beschriftung, name, beim) {
  const knopf = document.createElement('button');
  knopf.type = 'button';
  knopf.textContent = beschriftung;
  knopf.setAttribute('aria-label', name);
  knopf.addEventListener('click', beim);
  return knopf;
}

const maskiere = (text) => String(text)
  .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function zeichneSummen() {
  $('#summe-e1').textContent = geld(angebot.summeEinfach);
  $('#summe-e23').textContent = geld(angebot.summe23);
  $('#summe-e35').textContent = geld(angebot.summe35);
  $('#summe-ist').textContent = `${geld(angebot.summe)} €`;

  const spanne = $('#ziel-spanne');
  if (angebot.positionen.length === 0) { spanne.textContent = ''; return; }
  const [unten, oben] = angebot.spanne();
  let text = `Durch Faktorwahl erreichbar: ${geld(unten)} bis ${geld(oben)} €.`;
  if (angebot.zielbetrag !== null) {
    text += ` Ziel ${geld(angebot.zielbetrag)} €, Abweichung ${geld(angebot.summe - angebot.zielbetrag)} €.`;
  }
  spanne.textContent = text;
}

function zeichneKopf() {
  const teile = [];
  if (katalog) teile.push(`${katalog.anzahl} GOÄ-Ziffern`);
  if (angebot.name) teile.push(angebot.name + (gesichert ? '' : ' •'));
  $('#kopf-unterzeile').textContent = teile.join('  ·  ');
}

function geaendert({ sichern = false } = {}) {
  gesichert = sichern;
  zeichnePositionen();
  zeichneSummen();
  zeichneKopf();
}

function setzeFaktor(index, milli) {
  const p = angebot.positionen[index];
  const wert = Math.max(MIN_FAKTOR, Math.min(MAX_FAKTOR, milli));
  if (wert !== milli) {
    melde(`Der Faktor muss zwischen ${faktorText(MIN_FAKTOR)} und ${faktorText(MAX_FAKTOR)} liegen.`);
  }
  p.faktor = wert;
  geaendert();
}

/* ------------------------------------------------------------------ Katalog */

function zeichneKatalog() {
  const begriff = $('#feld-suche').value;
  const ergebnis = katalog.suche(begriff, sucheGrenze);
  const liste = Array.isArray(ergebnis) ? ergebnis : ergebnis.liste;
  const gesamt = Array.isArray(ergebnis) ? katalog.anzahl : ergebnis.gesamt;

  $('#such-ergebnis').textContent = begriff.trim()
    ? `${gesamt} Treffer${gesamt > liste.length ? `, ${liste.length} angezeigt` : ''}`
    : `${katalog.anzahl} Ziffern im Katalog – bitte suchen`;
  $('#knopf-mehr').hidden = gesamt <= liste.length;

  const behaelter = $('#katalogliste');
  behaelter.textContent = '';
  for (const l of liste) {
    const knopf = document.createElement('button');
    knopf.type = 'button';
    knopf.className = 'katalogeintrag';
    knopf.innerHTML = `<span class="ziffer">${maskiere(l.nummer)}</span>`
      + `<span class="katalog-text"><span class="legende">${maskiere(l.bezeichnung)}</span>`
      + `<span class="katalog-saetze">${geld(betragFuer(l, 1000))} · ${geld(betragFuer(l, 2300))} · ${geld(betragFuer(l, 3500))} €`
      + (l.herkunft === 'analog'
        ? `  <span class="analog-marke">eigene Ziffer, analog ${maskiere(l.analogZu)}</span>`
        : `  <span class="klasse">${l.abschnitt} / ${l.klassenname}${l.gruppe ? ' *' : ''}</span>`)
      + '</span></span>'
      + '<span class="katalog-plus" aria-hidden="true">+</span>';
    knopf.setAttribute('aria-label', `Ziffer ${l.nummer} übernehmen`);
    knopf.addEventListener('click', () => uebernehmen(l));
    behaelter.append(knopf);
  }
}

function betragFuer(leistung, milli) {
  return new Position({ ...leistung, faktor: milli }).betrag;
}

function uebernehmen(leistung) {
  const anzahl = Math.max(1, parseInt($('#feld-anzahl').value, 10) || 1);
  const wahl = $('#feld-startfaktor').value;
  const faktor = wahl === 'regel' ? leistung.regelsatz : parseInt(wahl, 10);
  angebot.positionen.push(Position.ausLeistung(leistung, anzahl, faktor));
  geaendert();
  melde(`Ziffer ${leistung.nummer} übernommen · Summe ${geld(angebot.summe)} €`);
}

/* -------------------------------------------------- Eigene Analogziffern */

function zeichneEigene() {
  $('#eigene-anzahl').textContent = eigene.anzahl ? `(${eigene.anzahl})` : '';
  const behaelter = $('#eigene-liste');
  behaelter.textContent = '';
  const alle = eigene.alle();
  if (alle.length === 0) {
    behaelter.innerHTML = '<p class="block-hinweis">Noch keine eigenen Ziffern angelegt.</p>';
    return;
  }
  for (const l of alle) {
    const zeile = document.createElement('div');
    zeile.className = 'eigene-eintrag';
    const betrag = new Position({ ...l, faktor: l.regelsatz }).betrag;
    zeile.innerHTML = `<span class="text"><b>${maskiere(l.nummer)}</b> ${maskiere(l.bezeichnung)}`
      + `<span class="zeile2">entsprechend Nr. ${maskiere(l.analogZu)} GOÄ · ${l.punktzahl} Punkte`
      + ` · ${geld(betrag)} € beim ${faktorText(l.regelsatz)}-fachen Satz</span></span>`;
    const weg = document.createElement('button');
    weg.type = 'button';
    weg.textContent = '×';
    weg.setAttribute('aria-label', `Eigene Ziffer ${l.nummer} löschen`);
    weg.addEventListener('click', async () => {
      if (!await bestaetige('Löschen', `Eigene Ziffer „${l.nummer}“ entfernen?`)) return;
      eigene.loeschen(l.nummer);
      katalog = katalogMitEigenen(amtlich, eigene);
      zeichneEigene();
      zeichneKatalog();
      melde(`${l.nummer} gelöscht`);
    });
    zeile.append(weg);
    behaelter.append(zeile);
  }
}

function analogAnlegen() {
  const dialog = $('#analog-dialog');
  const bezeichnung = $('#analog-bezeichnung');
  const vorlage = $('#analog-vorlage');
  const nummer = $('#analog-nummer');
  const vorschau = $('#analog-vorschau');
  const fehlerfeld = $('#analog-fehler');
  bezeichnung.value = ''; vorlage.value = ''; nummer.value = '';
  vorschau.textContent = ''; fehlerfeld.hidden = true;

  // Waehrend der Eingabe zeigen, welche Ziffer herangezogen wird.
  const pruefe = () => {
    const wert = vorlage.value.trim();
    if (!nummer.dataset.geaendert) nummer.value = wert ? `A${wert}` : '';
    if (!wert) { vorschau.textContent = ''; return; }
    try {
      const l = amtlich.hole(wert);
      vorschau.textContent = `${l.bezeichnung.slice(0, 80)} · ${l.punktzahl} Punkte · `
        + `${geld(new Position({ ...l, faktor: l.regelsatz }).betrag)} € beim `
        + `${faktorText(l.regelsatz)}-fachen Satz`;
    } catch {
      vorschau.textContent = 'Diese Ziffer steht nicht im Verzeichnis.';
    }
  };
  vorlage.addEventListener('input', pruefe);
  nummer.addEventListener('input', () => { nummer.dataset.geaendert = '1'; });
  delete nummer.dataset.geaendert;

  const beim = () => {
    dialog.removeEventListener('close', beim);
    vorlage.removeEventListener('input', pruefe);
    if (dialog.returnValue !== 'ok') return;
    try {
      const l = eigene.anlegen(amtlich, bezeichnung.value, vorlage.value, nummer.value);
      katalog = katalogMitEigenen(amtlich, eigene);
      zeichneEigene();
      $('#feld-suche').value = l.nummer;
      zeichneKatalog();
      melde(`${l.nummer} angelegt · ${geld(new Position({ ...l, faktor: l.regelsatz }).betrag)} €`);
    } catch (fehler) {
      if (!(fehler instanceof EigeneFehler)) throw fehler;
      melde(fehler.message, 5000);
    }
  };
  dialog.addEventListener('close', beim);
  dialog.showModal();
}

/* -------------------------------------------------------------- Zielbetrag */

function verteile() {
  if (angebot.positionen.length === 0) { melde('Bitte zuerst Ziffern übernehmen.'); return; }
  const ziel = betragAusText($('#feld-ziel').value);
  if (ziel === null) { melde('Bitte einen Betrag eingeben, z. B. 250,00'); return; }

  const ergebnis = optimiereFaktoren(angebot.positionen, ziel, {
    strategie: $('#feld-strategie').value,
    schrittweite: parseInt($('#feld-raster').value, 10),
    nachjustieren: $('#feld-centgenau').checked,
    rechtlicheGrenzen: $('#feld-rechtlich').checked,
  });
  angebot.zielbetrag = ziel;
  geaendert();

  const meldung = $('#ziel-meldung');
  meldung.hidden = false;
  meldung.className = `meldung${ergebnis.erreicht ? ' gut' : ' warnung'}`;
  meldung.textContent = `${ergebnis.meldung} Summe ${geld(ergebnis.summe)} €.`;
}

/* -------------------------------------------------------- Sichern und Teilen */

async function speichern() {
  angebot.name = $('#feld-name').value.trim();
  angebot.patient = $('#feld-patient').value.trim();
  angebot.beschreibung = $('#feld-beschreibung').value.trim();
  if (!angebot.name) {
    const name = await frage('Name fehlt', 'Unter welchem Namen soll das Angebot gespeichert werden?', '');
    if (!name || !name.trim()) return false;
    angebot.name = name.trim();
    $('#feld-name').value = angebot.name;
  }
  verzeichnis.speichern(angebot);
  geaendert({ sichern: true });
  melde(`„${angebot.name}“ gespeichert`);
  return true;
}

async function excelTeilen() {
  if (angebot.positionen.length === 0) { melde('Das Angebot enthält keine Positionen.'); return; }
  if (!angebot.name) angebot.name = $('#feld-name').value.trim() || 'Angebot';
  const blob = angebotAlsXlsx(angebot);
  const name = dateiname(angebot.name);
  const datei = new File([blob], name, { type: blob.type });

  // Auf dem Telefon ist Teilen der natuerliche Weg (Mail, Dateien, Drive).
  if (navigator.canShare && navigator.canShare({ files: [datei] })) {
    try {
      await navigator.share({ files: [datei], title: angebot.name });
      return;
    } catch (fehler) {
      if (fehler.name === 'AbortError') return;
    }
  }
  const adresse = URL.createObjectURL(blob);
  const verweis = document.createElement('a');
  verweis.href = adresse;
  verweis.download = name;
  document.body.append(verweis);
  verweis.click();
  verweis.remove();
  setTimeout(() => URL.revokeObjectURL(adresse), 4000);
  melde(`${name} gespeichert`);
}

/* ------------------------------------------------------- Gespeicherte Liste */

function zeigeGespeicherte() {
  const behaelter = $('#angebotsliste');
  behaelter.textContent = '';
  const alle = verzeichnis.alle();
  if (alle.length === 0) {
    behaelter.innerHTML = '<div class="leerhinweis"><p><strong>Noch nichts gespeichert.</strong></p>'
      + '<p>Gespeicherte Angebote bleiben auf diesem Gerät und lassen sich jederzeit wieder öffnen.</p></div>';
    return;
  }
  for (const gespeichertesAngebot of alle) {
    const karte = document.createElement('article');
    karte.className = 'angebotskarte';
    const datum = new Date(gespeichertesAngebot.geaendert).toLocaleString('de-DE',
      { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
    karte.innerHTML = `<span class="summe">${geld(gespeichertesAngebot.summe)} €</span>`
      + `<h3>${maskiere(gespeichertesAngebot.name)}</h3>`
      + `<div class="zeile">${maskiere(gespeichertesAngebot.patient || 'ohne Patientenangabe')} · `
      + `${gespeichertesAngebot.positionen.length} Position(en) · ${datum}</div>`;
    const reihe = document.createElement('div');
    reihe.className = 'knopfreihe';

    const oeffnen = document.createElement('button');
    oeffnen.type = 'button';
    oeffnen.className = 'knopf haupt';
    oeffnen.textContent = 'Öffnen';
    oeffnen.addEventListener('click', async () => {
      if (!gesichert && !await bestaetige('Ungesicherte Änderungen',
        'Das aktuelle Angebot ist nicht gespeichert. Trotzdem öffnen?')) return;
      angebot = verzeichnis.laden(gespeichertesAngebot.id);
      fuelleFelder();
      geaendert({ sichern: true });
      wechsle('angebot');
      melde(`„${angebot.name}“ geöffnet`);
    });

    const kopie = document.createElement('button');
    kopie.type = 'button';
    kopie.className = 'knopf';
    kopie.textContent = 'Kopie';
    kopie.addEventListener('click', async () => {
      const name = await frage('Kopie anlegen', 'Name der Kopie:', `${gespeichertesAngebot.name} (Kopie)`);
      if (!name || !name.trim()) return;
      verzeichnis.kopieren(gespeichertesAngebot.id, name.trim());
      zeigeGespeicherte();
      melde('Kopie angelegt');
    });

    const weg = document.createElement('button');
    weg.type = 'button';
    weg.className = 'knopf';
    weg.textContent = 'Löschen';
    weg.addEventListener('click', async () => {
      if (!await bestaetige('Angebot löschen', `„${gespeichertesAngebot.name}“ endgültig löschen?`)) return;
      verzeichnis.loeschen(gespeichertesAngebot.id);
      zeigeGespeicherte();
      melde('Gelöscht');
    });

    reihe.append(oeffnen, kopie, weg);
    karte.append(reihe);
    behaelter.append(karte);
  }
}

function fuelleFelder() {
  $('#feld-name').value = angebot.name;
  $('#feld-patient').value = angebot.patient;
  $('#feld-beschreibung').value = angebot.beschreibung;
  $('#feld-ziel').value = angebot.zielbetrag === null ? '' : geld(angebot.zielbetrag);
  $('#ziel-meldung').hidden = true;
}

async function neuesAngebot() {
  if (!gesichert && angebot.positionen.length
      && !await bestaetige('Ungesicherte Änderungen', 'Das aktuelle Angebot ist nicht gespeichert. Verwerfen?')) return;
  angebot = new Angebot({ name: '' });
  fuelleFelder();
  geaendert({ sichern: true });
  wechsle('angebot');
}

/* ----------------------------------------------------------------- Aufbau */

function verdrahte() {
  document.querySelectorAll('[data-wechsel]').forEach((knopf) => {
    knopf.addEventListener('click', () => wechsle(knopf.dataset.wechsel));
  });
  for (const kennung of ['#feld-name', '#feld-patient', '#feld-beschreibung']) {
    $(kennung).addEventListener('input', () => {
      angebot.name = $('#feld-name').value;
      angebot.patient = $('#feld-patient').value;
      angebot.beschreibung = $('#feld-beschreibung').value;
      gesichert = false;
      zeichneKopf();
    });
  }
  const auswahl = $('#feld-strategie');
  for (const strategie of STRATEGIEN) {
    const eintrag = document.createElement('option');
    eintrag.value = strategie;
    eintrag.textContent = STRATEGIE_TEXT[strategie];
    auswahl.append(eintrag);
  }
  $('#knopf-verteilen').addEventListener('click', verteile);
  $('#feld-ziel').addEventListener('keydown', (e) => { if (e.key === 'Enter') verteile(); });
  $('#knopf-speichern').addEventListener('click', speichern);
  $('#knopf-excel').addEventListener('click', excelTeilen);
  $('#knopf-neu').addEventListener('click', neuesAngebot);
  $('#knopf-neu-2').addEventListener('click', neuesAngebot);
  $('#knopf-hilfe').addEventListener('click', zeigeHilfe);

  let uhr = null;
  $('#feld-suche').addEventListener('input', () => {
    clearTimeout(uhr);
    sucheGrenze = 40;
    uhr = setTimeout(zeichneKatalog, 120);
  });
  $('#knopf-mehr').addEventListener('click', () => { sucheGrenze += 60; zeichneKatalog(); });
  $('#knopf-eigene').addEventListener('click', () => {
    const bereich = $('#eigene-bereich');
    bereich.hidden = !bereich.hidden;
    if (!bereich.hidden) zeichneEigene();
  });
  $('#knopf-eigene-neu').addEventListener('click', analogAnlegen);

  window.addEventListener('beforeunload', (e) => {
    if (!gesichert && angebot.positionen.length) { e.preventDefault(); e.returnValue = ''; }
  });
}

function zeigeHilfe() {
  frage('Kurzanleitung',
    'Katalog: Ziffer suchen und antippen – sie wandert ins Angebot. '
    + 'Angebot: je Ziffer stehen der einfache, der 2,3- und der 3,5-fache Satz; '
    + 'antippen setzt den Faktor, das Feld dazwischen nimmt jeden Wert zwischen 1,0 und 3,5. '
    + 'Das Schloss hält eine Ziffer fest, wenn ein Gesamtpreis verteilt wird. '
    + 'Gesamtpreis vorgeben verteilt die Faktoren automatisch. '
    + 'Speichern legt das Angebot auf dem Gerät ab, Excel erzeugt eine Tabelle zum Teilen. '
    + 'Faktoren über dem Regelsatz sind nach § 12 GOÄ zu begründen und werden farbig markiert.',
    null);
}

async function starte() {
  verdrahte();
  try {
    amtlich = await Katalog.laden();
    katalog = katalogMitEigenen(amtlich, eigene);
  } catch (fehler) {
    $('#kopf-unterzeile').textContent = 'Katalog konnte nicht geladen werden';
    melde('Der Leistungskatalog konnte nicht geladen werden.', 6000);
    return;
  }
  zeichneKatalog();
  zeichneEigene();
  fuelleFelder();
  geaendert({ sichern: true });
  wechsle('angebot');

  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(() => { /* offline dann eben nicht */ });
  }
}

starte();
