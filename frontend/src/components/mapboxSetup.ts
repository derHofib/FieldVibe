import mapboxgl from "mapbox-gl";

// mapbox-gl 3.x (geprueft an 3.28.1) hat keine Option, die Nutzungsdaten-
// Telemetrie abzuschalten: Ziel ist config.EVENTS_URL, ein Getter aus API_URL,
// und der Payload hat "enabled.telemetry" fest auf false. Ein Ueberschreiben
// von EVENTS_URL wuerde zusaetzlich den Session-Aufruf (api.mapbox.com/
// map-sessions) abschalten, der an derselben Bedingung haengt und im
// SDK-Quelltext als abrechnungsrelevant markiert ist. Deshalb wird nur der
// Events-Host auf Fetch-Ebene verworfen; Style-, Tile- und Session-Requests
// an api.mapbox.com bleiben unberuehrt.
const EVENTS_HOST = /^events\.mapbox\.c(om|n)$/i;

type FetchEingabe = Parameters<typeof fetch>[0];

export function istMapboxEventsRequest(eingabe: FetchEingabe): boolean {
  try {
    const url =
      typeof eingabe === "string" ? eingabe : eingabe instanceof URL ? eingabe.href : eingabe.url;
    return EVENTS_HOST.test(new URL(url, globalThis.location?.href).hostname);
  } catch {
    return false;
  }
}

// Modul-Flag statt Marker am fetch: andere Module (bugreport/netzwerk.ts)
// wickeln fetch ebenfalls ein, ein Marker waere dann nicht mehr sichtbar und
// jede neu gemountete Karte wuerde eine weitere Schicht anhaengen.
let sperreAktiv = false;

/** Idempotent; muss vor dem ersten `new mapboxgl.Map(...)` laufen. */
export function sperreMapboxTelemetrie(): void {
  if (sperreAktiv) return;
  sperreAktiv = true;
  const original = globalThis.fetch;
  globalThis.fetch = (eingabe, init) =>
    istMapboxEventsRequest(eingabe)
      // 204 statt Fehler: mapbox-gl wertet !ok als Fehlschlag und wuerde
      // Konsolenrauschen erzeugen.
      ? Promise.resolve(new Response(null, { status: 204 }))
      : original(eingabe, init);
}

export function richteMapboxEin(token: string): void {
  sperreMapboxTelemetrie();
  mapboxgl.accessToken = token;
}
