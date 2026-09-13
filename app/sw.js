/**
 * Offlinebetrieb: die App laeuft ohne Netz weiter.
 *
 * Der Katalog und die Programmdateien werden bei der Installation abgelegt.
 * Beim Aendern der Version wird der alte Bestand verworfen.
 */

const VERSION = 'goae-v6';
const BESTAND = [
  './',
  './index.html',
  './app.css',
  './manifest.webmanifest',
  './js/angaben.js',
  './js/app.js',
  './js/eigene.js',
  './js/farben.js',
  './js/modelle.js',
  './js/katalog.js',
  './js/speicher.js',
  './js/zielbetrag.js',
  './js/xlsx.js',
  './daten/goae_katalog.json',
  './symbole/symbol-192.png',
  './symbole/symbol-512.png',
];

self.addEventListener('install', (ereignis) => {
  ereignis.waitUntil(
    caches.open(VERSION).then((lager) => lager.addAll(BESTAND)).then(() => self.skipWaiting()),
  );
});

self.addEventListener('activate', (ereignis) => {
  ereignis.waitUntil(
    caches.keys()
      .then((namen) => Promise.all(namen.filter((n) => n !== VERSION).map((n) => caches.delete(n))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener('fetch', (ereignis) => {
  if (ereignis.request.method !== 'GET') return;
  ereignis.respondWith(
    caches.match(ereignis.request).then((gefunden) => gefunden || fetch(ereignis.request)
      .then((antwort) => {
        // Erfolgreich geladene eigene Dateien nachtraeglich aufnehmen.
        if (antwort.ok && new URL(ereignis.request.url).origin === self.location.origin) {
          const kopie = antwort.clone();
          caches.open(VERSION).then((lager) => lager.put(ereignis.request, kopie));
        }
        return antwort;
      })
      .catch(() => caches.match('./index.html'))),
  );
});
