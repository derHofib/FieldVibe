import mapboxgl from "mapbox-gl";
import "mapbox-gl/dist/mapbox-gl.css";
import { useEffect, useRef } from "react";

import { useTheme } from "../context/ThemeContext";

const MAPBOX_TOKEN = import.meta.env.VITE_MAPBOX_TOKEN;

const STYLE_URL = {
  light: "mapbox://styles/mapbox/streets-v12",
  dark: "mapbox://styles/mapbox/dark-v11",
} as const;

export function MapboxMap({
  lng,
  lat,
  zoom = 14,
  className = "h-40 w-full rounded-lg",
}: {
  lng: number;
  lat: number;
  zoom?: number;
  className?: string;
}) {
  const { theme } = useTheme();
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<mapboxgl.Map | null>(null);

  useEffect(() => {
    if (!MAPBOX_TOKEN || !containerRef.current) return;
    mapboxgl.accessToken = MAPBOX_TOKEN;
    const map = new mapboxgl.Map({
      container: containerRef.current,
      style: STYLE_URL[theme],
      center: [lng, lat],
      zoom,
      // Statische Uebersichtskarte, kein Explorations-Werkzeug -- jede Form
      // von Pan/Zoom bewusst deaktiviert, sonst faengt die kleine Karte auf
      // Mobilgeraeten eine Scroll-Geste ueber der Seite ab, statt sie
      // durchzulassen (siehe Mobile-Kollisionscheck der Design-
      // Ueberarbeitung). Die Vollbild-Kartenansicht im Feed (MapboxFeedMap)
      // ist bewusst anders: dort ist Pan/Zoom das eigentliche Werkzeug.
      scrollZoom: false,
      dragPan: false,
      dragRotate: false,
      touchZoomRotate: false,
      touchPitch: false,
      doubleClickZoom: false,
    });
    map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), "top-right");
    new mapboxgl.Marker({ color: "#0284c7" }).setLngLat([lng, lat]).addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- Karte bewusst
    // nur einmal pro Koordinate neu aufbauen, siehe separater Style-Effekt
    // fuer Theme-Wechsel unten.
  }, [lng, lat, zoom]);

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
