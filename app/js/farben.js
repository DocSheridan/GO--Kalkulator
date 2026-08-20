/**
 * Farbschema der Praxis.
 *
 * Die drei Grundfarben sind dem Praxislogo entnommen und dort die
 * flaechenmaessig groessten deckenden Farben. Dieselbe Palette gibt es fuer
 * das Schreibtischprogramm in goae_kalkulator/farben.py und als Variablen in
 * app.css; die Uebereinstimmung wird von den Testfaellen geprueft.
 */

// -- aus dem Logo ---------------------------------------------------------
export const GRUEN = '#6C7569';        // Grün der Logofläche
export const HELLGRUEN = '#B7C4AF';    // Hellgrün des Strangs
export const GRAU = '#585857';         // Grau der Wortmarke
export const WEISS = '#FFFFFF';

// -- abgeleitet -----------------------------------------------------------
export const GRUEN_STARK = '#4D5649';  // dunkler; kleine Schrift auf hellen Flächen
export const GRUEN_TON = '#DCE4D7';    // heller Grundton, z. B. Summenzeile
export const TEXT = '#23261F';

// -- Zustände -------------------------------------------------------------
export const WARNUNG = '#9A5800';
export const FEHLER = '#A3201A';
export const GUT = '#4A6B45';

/** Wandelt #RRGGBB in die von Excel erwartete Schreibweise FFRRGGBB. */
export const excel = (farbe) => `FF${farbe.replace('#', '').toUpperCase()}`;
