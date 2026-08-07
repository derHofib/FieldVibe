import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { useEffect, useRef } from "react";

import { useTheme } from "../context/ThemeContext";

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

const STYLE_URL = {
  light: "mapbox://styles/mapbox/streets-v12",
  dark: "mapbox://styles/mapbox/dark-v11",
} as const;

const SOURCE_ID = "vorgaenge";
const VIEWPORT_STORAGE_KEY = "fieldvibe:feed-karte-viewport";

interface GespeicherterViewport {
  center: [number, number];
  zoom: number;
}

function ladeGespeichertenViewport(): GespeicherterViewport | null {
  try {
    const raw = localStorage.getItem(VIEWPORT_STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    if (
      Array.isArray(parsed.center) &&
      parsed.center.length === 2 &&
      typeof parsed.zoom === "number"
    ) {
      return parsed as GespeicherterViewport;
    }
    return null;
  } catch {
    return null;
  }
}

function speichereViewport(map: mapboxgl.Map): void {
  const center = map.getCenter();
  const viewport: GespeicherterViewport = { center: [center.lng, center.lat], zoom: map.getZoom() };
  try {
    localStorage.setItem(VIEWPORT_STORAGE_KEY, JSON.stringify(viewport));
  } catch {
    // localStorage kann in seltenen Faellen (privater Modus, voller Speicher)
    // fehlschlagen -- das Merken des Kartenausschnitts ist ein reines
    // Komfort-Feature, kein Grund die Karte abstuerzen zu lassen.
  }
}

export interface FeedMapPunkt {
  id: string;
  lng: number;
  lat: number;
  farbe: string;
}

function punkteAlsGeojson(punkte: FeedMapPunkt[]): GeoJSON.FeatureCollection<GeoJSON.Point> {
  return {
    type: "FeatureCollection",
    features: punkte.map((p) => ({
      type: "Feature",
      properties: { id: p.id, farbe: p.farbe },
      geometry: { type: "Point", coordinates: [p.lng, p.lat] },
    })),
  };
}

export function MapboxFeedMap({
  punkte,
  onPunktClick,
  className = "h-full w-full",
}: {
  punkte: FeedMapPunkt[];
  onPunktClick: (id: string) => void;
  className?: string;
}) {
  const { theme } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);
  const punkteRef = useRef(punkte);
  punkteRef.current = punkte;
  const onPunktClickRef = useRef(onPunktClick);
  onPunktClickRef.current = onPunktClick;

  const gespeicherterViewportRef = useRef(ladeGespeichertenViewport());
  const autoFitErledigtRef = useRef(false);

  useEffect(() => {
    if (!MAPBOX_TOKEN || !containerRef.current) return;
    mapboxgl.accessToken = MAPBOX_TOKEN;
    const gespeichert = gespeicherterViewportRef.current;
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: STYLE_URL[theme],
      center: gespeichert?.center ?? [10.4515, 51.1657],
      zoom: gespeichert?.zoom ?? 5,
    });
    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(
      new mapboxgl.GeolocateControl({
        positionOptions: { enableHighAccuracy: true },
        trackUserLocation: true,
        showUserHeading: true,
      }),
      "top-right",
    );
    // Kartenausschnitt merken, damit Techniker/Disponenten nicht bei jedem
    // Wechsel in die Kartenansicht wieder auf ihre bevorzugte Region zoomen
    // muessen -- nur bei echtem Ende der Bewegung speichern, nicht bei jedem
    // Zwischenschritt.
    map.on("moveend", () => speichereViewport(map));

    // Quelle/Layer leben im Style und verschwinden bei jedem setStyle()
    // (Theme-Wechsel) -- deshalb hier wiederholbar statt nur beim ersten
    // "load" registriert, siehe Theme-Effekt unten.
    function ensureLayers() {
      if (map.getSource(SOURCE_ID)) return;
      map.addSource(SOURCE_ID, {
        type: "geojson",
        data: punkteAlsGeojson(punkteRef.current),
        cluster: true,
        clusterMaxZoom: 14,
        clusterRadius: 40,
      });
      map.addLayer({
        id: "cluster-circle",
        type: "circle",
        source: SOURCE_ID,
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#0284c7",
          "circle-radius": ["step", ["get", "point_count"], 16, 10, 20, 25, 26],
          "circle-opacity": 0.9,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
        },
      });
      map.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: SOURCE_ID,
        filter: ["has", "point_count"],
        layout: { "text-field": "{point_count_abbreviated}", "text-size": 12, "text-font": ["DIN Pro Bold", "Arial Unicode MS Bold"] },
        paint: { "text-color": "#ffffff" },
      });
      map.addLayer({
        id: "unclustered-point",
        type: "circle",
        source: SOURCE_ID,
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": ["get", "farbe"],
          "circle-radius": 8,
          "circle-stroke-width": 2,
          "circle-stroke-color": "#ffffff",
        },
      });
    }

    map.on("style.load", ensureLayers);

    map.on("click", "unclustered-point", (e) => {
      const id = e.features?.[0]?.properties?.id as string | undefined;
      if (id) onPunktClickRef.current(id);
    });
    map.on("click", "cluster-circle", (e) => {
      const feature = e.features?.[0];
      const clusterId = feature?.properties?.cluster_id as number | undefined;
      const source = map.getSource(SOURCE_ID) as mapboxgl.GeoJSONSource | undefined;
      if (clusterId === undefined || !source || feature?.geometry.type !== "Point") return;
      source.getClusterExpansionZoom(clusterId, (err, zoom) => {
        if (err || zoom == null || feature.geometry.type !== "Point") return;
        map.easeTo({ center: feature.geometry.coordinates as [number, number], zoom });
      });
    });
    for (const layer of ["unclustered-point", "cluster-circle"]) {
      map.on("mouseenter", layer, () => {
        map.getCanvas().style.cursor = "pointer";
      });
      map.on("mouseleave", layer, () => {
        map.getCanvas().style.cursor = "";
      });
    }

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Karte einmalig
    // aufbauen, Style-Wechsel und Daten-Updates laufen ueber eigene Effekte.
  }, []);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    function updateData() {
      if (!map) return;
      const source = map.getSource(SOURCE_ID) as mapboxgl.GeoJSONSource | undefined;
      if (!source) return;
      source.setData(punkteAlsGeojson(punkte));
      // Nur einmalig automatisch auf alle Punkte zoomen, und gar nicht, wenn
      // bereits ein gemerkter Kartenausschnitt geladen wurde -- sonst wuerde
      // jede weitere Seite, die beim Wechsel in die Kartenansicht nachgeladen
      // wird, den vom Nutzer gewaehlten (oder gemerkten) Ausschnitt ueberschreiben.
      if (punkte.length > 0 && !autoFitErledigtRef.current && !gespeicherterViewportRef.current) {
        autoFitErledigtRef.current = true;
        const bounds = new mapboxgl.LngLatBounds();
        punkte.forEach((p) => bounds.extend([p.lng, p.lat]));
        map.fitBounds(bounds, { padding: 48, maxZoom: 15, duration: 0 });
      }
    }
    if (map.isStyleLoaded()) updateData();
    else map.once("style.load", updateData);
  }, [punkte]);

  useEffect(() => {
    mapRef.current?.setStyle(STYLE_URL[theme]);
  }, [theme]);

  if (!MAPBOX_TOKEN) {
    return (
      <div
        className={`flex items-center justify-center border border-dashed border-slate-300 bg-slate-50 text-center text-xs text-slate-400 dark:border-stone-700 dark:bg-stone-800/60 dark:text-stone-500 ${className}`}
      >
        Karte nicht verfügbar (kein Mapbox-Token konfiguriert)
      </div>
    );
  }

  return <div ref={containerRef} className={`bg-slate-100 dark:bg-stone-800 ${className}`} />;
}
