/**
 * Rechenkern nach GOAE - bewusst ohne Fliesskomma.
 *
 * Geldbetraege sind ganzzahlige Cent, Steigerungsfaktoren ganzzahlige
 * Tausendstel (2,3 wird zu 2300). Fliesskomma wuerde hier zu Abweichungen
 * fuehren, die sich ueber ein Angebot aufsummieren; mit Ganzzahlen stimmen
 * die Betraege exakt mit dem Schreibtischprogramm ueberein.
 */

/** Punktwert nach § 5 Abs. 1 GOAE: 5,82873 Cent, hier in Einheiten von 10^-7 EUR. */
export const PUNKTWERT_E7 = 582873;

/** Faktoren werden als Tausendstel gefuehrt. */
export const FAKTOR_EINHEIT = 1000;
export const MIN_FAKTOR = 1000;   // 1,0
export const MAX_FAKTOR = 3500;   // 3,5
export const FAKTOR_SCHRITT = 100;   // uebliche Zehntelstufung
export const FAKTOR_RASTER = 1;      // feinste darstellbare Stufe (0,001)

export const KLASSEN = {
  a: { name: 'aerztlich', regelsatz: 2300, hoechstsatz: 3500 },
  t: { name: 'technisch', regelsatz: 1800, hoechstsatz: 2500 },
  l: { name: 'labor', regelsatz: 1150, hoechstsatz: 1300 },
};

/**
 * Betrag einer einzelnen Leistung in Cent.
 * Punktzahl x Punktwert x Faktor, kaufmaennisch auf volle Cent gerundet
 * (§ 5 Abs. 1 Satz 4 GOAE: ab 0,5 aufrunden).
 */
export function betragCent(punktzahl, faktorMilli) {
  const roh = punktzahl * PUNKTWERT_E7 * faktorMilli;   // Einheit 10^-10 EUR
  return Math.floor((roh + 50000000) / 100000000);
}

/** Deutsche Schreibweise eines Cent-Betrags: 1.234,50 */
export function geld(cent) {
  const negativ = cent < 0;
  const wert = Math.abs(cent);
  const ganz = String(Math.floor(wert / 100));
  const rest = String(wert % 100).padStart(2, '0');
  const mitPunkten = ganz.replace(/\B(?=(\d{3})+(?!\d))/g, '.');
  return `${negativ ? '-' : ''}${mitPunkten},${rest}`;
}

/** Faktor lesbar ausgeben: 2300 -> "2,3", 3359 -> "3,359" */
export function faktorText(milli) {
  let text = (milli / 1000).toFixed(3).replace(/0+$/, '');
  if (text.endsWith('.')) text += '0';
  return text.replace('.', ',');
}

/** Eingabe wie "2,5" oder "2.5" in Tausendstel wandeln; null bei Unsinn. */
export function faktorAusText(text) {
  const roh = String(text ?? '').trim().replace(',', '.');
  if (!/^\d+(\.\d+)?$/.test(roh)) return null;
  return Math.round(parseFloat(roh) * 1000);
}

/** Eingabe wie "1.234,50" oder "250" in Cent wandeln; null bei Unsinn. */
export function betragAusText(text) {
  let roh = String(text ?? '').replace(/[€\s]|EUR/g, '').trim();
  if (!roh) return null;
  if (roh.lastIndexOf(',') > roh.lastIndexOf('.')) {
    roh = roh.replace(/\./g, '').replace(',', '.');
  } else {
    roh = roh.replace(/,/g, '');
  }
  if (!/^\d+(\.\d+)?$/.test(roh)) return null;
  return Math.round(parseFloat(roh) * 100);
}

/** Eine Abrechnungsziffer innerhalb eines Angebots. */
export class Position {
  constructor(daten) {
    this.nummer = daten.nummer;
    this.bezeichnung = daten.bezeichnung ?? '';
    this.punktzahl = daten.punktzahl;
    this.anzahl = daten.anzahl ?? 1;
    this.faktor = daten.faktor ?? daten.regelsatz ?? 2300;
    this.fixiert = daten.fixiert ?? false;
    this.abschnitt = daten.abschnitt ?? '';
    this.klasse = daten.klasse ?? 'a';
    this.regelsatz = daten.regelsatz ?? 2300;
    this.hoechstsatz = daten.hoechstsatz ?? 3500;
    this.begruendung = daten.begruendung ?? '';
    this.gruppe = daten.gruppe ?? false;
  }

  static ausLeistung(leistung, anzahl = 1, faktor = null) {
    return new Position({
      nummer: leistung.nummer,
      bezeichnung: leistung.bezeichnung,
      punktzahl: leistung.punktzahl,
      anzahl,
      faktor: faktor ?? leistung.regelsatz,
      abschnitt: leistung.abschnitt,
      klasse: leistung.klasse,
      regelsatz: leistung.regelsatz,
      hoechstsatz: leistung.hoechstsatz,
      gruppe: leistung.gruppe,
    });
  }

  betragBei(faktorMilli) {
    return betragCent(this.punktzahl, faktorMilli) * this.anzahl;
  }

  get betrag() { return this.betragBei(this.faktor); }
  get einfachsatz() { return this.betragBei(1000); }
  get satz23() { return this.betragBei(2300); }
  get satz35() { return this.betragBei(3500); }

  get ueberRegelsatz() { return this.faktor > this.regelsatz; }
  get ueberHoechstsatz() { return this.faktor > this.hoechstsatz; }

  hinweis() {
    if (this.ueberHoechstsatz) {
      return `Faktor über Höchstsatz ${faktorText(this.hoechstsatz)} (${KLASSEN[this.klasse]?.name ?? this.klasse})`;
    }
    if (this.ueberRegelsatz && !this.begruendung) {
      return 'Begründung erforderlich (über Regelsatz)';
    }
    if (this.gruppe) {
      return 'Punktzahl gilt im Verzeichnis für eine Gruppe von Nummern';
    }
    return '';
  }

  toJSON() {
    return {
      nummer: this.nummer, bezeichnung: this.bezeichnung, punktzahl: this.punktzahl,
      anzahl: this.anzahl, faktor: this.faktor, fixiert: this.fixiert,
      abschnitt: this.abschnitt, klasse: this.klasse, regelsatz: this.regelsatz,
      hoechstsatz: this.hoechstsatz, begruendung: this.begruendung, gruppe: this.gruppe,
    };
  }
}

/** Ein benanntes Leistungspaket. */
export class Angebot {
  constructor(daten = {}) {
    this.id = daten.id ?? `a${Date.now()}${Math.random().toString(36).slice(2, 7)}`;
    this.name = daten.name ?? '';
    this.patient = daten.patient ?? '';
    this.beschreibung = daten.beschreibung ?? '';
    this.zielbetrag = daten.zielbetrag ?? null;
    this.erstellt = daten.erstellt ?? new Date().toISOString();
    this.geaendert = daten.geaendert ?? this.erstellt;
    this.positionen = (daten.positionen ?? []).map((p) => new Position(p));
  }

  get summe() { return this.positionen.reduce((s, p) => s + p.betrag, 0); }
  get summeEinfach() { return this.positionen.reduce((s, p) => s + p.einfachsatz, 0); }
  get summe23() { return this.positionen.reduce((s, p) => s + p.satz23, 0); }
  get summe35() { return this.positionen.reduce((s, p) => s + p.satz35, 0); }
  get punkte() { return this.positionen.reduce((s, p) => s + p.punktzahl * p.anzahl, 0); }

  /** Erreichbarer Summenbereich; fixierte Positionen zaehlen mit ihrem Betrag. */
  spanne(minFaktor = MIN_FAKTOR, maxFaktor = MAX_FAKTOR) {
    let unten = 0, oben = 0;
    for (const p of this.positionen) {
      if (p.fixiert) { unten += p.betrag; oben += p.betrag; }
      else { unten += p.betragBei(minFaktor); oben += p.betragBei(maxFaktor); }
    }
    return [unten, oben];
  }

  hinweise() {
    return this.positionen
      .map((p) => [p, p.hinweis()])
      .filter(([, h]) => h)
      .map(([p, h]) => `Ziffer ${p.nummer}: ${h}`);
  }

  toJSON() {
    return {
      id: this.id, name: this.name, patient: this.patient,
      beschreibung: this.beschreibung, zielbetrag: this.zielbetrag,
      erstellt: this.erstellt, geaendert: this.geaendert,
      positionen: this.positionen.map((p) => p.toJSON()),
    };
  }
}
