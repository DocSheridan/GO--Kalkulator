/**
 * Angaben zum Programm - Urheberrecht und Impressum.
 *
 * Dieselben Angaben stehen fuer das Schreibtischprogramm in
 * goae_kalkulator/angaben.py; dass sie uebereinstimmen, pruefen die
 * Testfaelle.
 */

// Der Vermerk wird zweiteilig geführt, weil der Zusatz kleiner gesetzt wird -
// in der App, auf dem Ausdruck und in der Excel-Tabelle. Wo keine Schriftgrade
// möglich sind, dient COPYRIGHT als schlichte Zusammensetzung.
export const COPYRIGHT_HAUPT = '© 2026 Dr. med. Raimar Lorrmann D. O.';
export const COPYRIGHT_ZUSATZ = '(DAAO)';
export const COPYRIGHT = `${COPYRIGHT_HAUPT} ${COPYRIGHT_ZUSATZ}`;
export const PRAXIS = 'Die Hausärzte im Sheridan';

/**
 * Ein Impressum nach § 5 DDG nennt ladungsfähige Anschrift und Kontakt, für
 * Ärzte zusätzlich Berufsbezeichnung, zuständige Kammer und Aufsichtsbehörde.
 */
export const IMPRESSUM = {
  verantwortlich: 'Raimar Lorrmann',
  praxis: PRAXIS,
  anschrift: 'Max-Josef-Metzger-Straße 3a, 86157 Augsburg',
  kontakt: 'praxis@hausaerzte-sheridan.de',
  berufsbezeichnung: 'Arzt (verliehen in der Bundesrepublik Deutschland)',
  kammer: 'Bayerische Landesärztekammer',
  aufsicht: 'Bayerische Landesärztekammer',
};
