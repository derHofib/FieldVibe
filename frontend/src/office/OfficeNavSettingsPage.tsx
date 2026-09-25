import { useEffect, useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { RotateCcw } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { usersApi } from "../api/endpoints";
import { IconBadge } from "../components/IconBadge";
import { useAuth } from "../context/AuthContext";
import { NAV_KATEGORIE_REIHENFOLGE, sichtbareNavSeiten } from "../config/navSeiten";
import type { OfficeNavPraeferenz } from "../types";

export function OfficeNavSettingsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser, hatRecht } = useAuth();

  const sichtbar = sichtbareNavSeiten(currentUser, hatRecht);
  const gespeicherteAuswahl = currentUser?.office_nav_items?.items;
  // null (nichts gespeichert) -> alles ausgewaehlt, wie die Sidebar es heute
  // ohne Praeferenz zeigt. Lokaler Zwischenstand, damit die Checkboxen erst
  // beim "Speichern" tatsaechlich uebernommen werden statt bei jedem Klick
  // einzeln zu speichern.
  const [auswahl, setAuswahl] = useState<Set<string>>(
    new Set(gespeicherteAuswahl ?? sichtbar.map((s) => s.key)),
  );

  // Falls /me nachlaedt (z.B. direkter Aufruf dieser Seite ohne warmen
  // Cache), den lokalen Zwischenstand einmalig auf den echten Serverstand
  // nachziehen.
  useEffect(() => {
    setAuswahl(new Set(gespeicherteAuswahl ?? sichtbar.map((s) => s.key)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentUser?.id]);

  const speichernMutation = useMutation({
    mutationFn: (praeferenz: OfficeNavPraeferenz) => usersApi.updateOwnOfficeNav(praeferenz),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });

  const toggle = (key: string) => {
    setAuswahl((bisher) => {
      const naechste = new Set(bisher);
      if (naechste.has(key)) naechste.delete(key);
      else naechste.add(key);
      return naechste;
    });
  };

  const speichern = () => {
    // Wenn wirklich alle sichtbaren Seiten ausgewaehlt sind, als "null"
    // speichern (Standardauswahl) statt einer expliziten Vollliste -- dann
    // tauchen spaeter neu hinzukommende Seiten automatisch mit auf, statt
    // stillschweigend zu fehlen.
    const istAlles = sichtbar.every((s) => auswahl.has(s.key)) && auswahl.size === sichtbar.length;
    speichernMutation.mutate({ items: istAlles ? null : Array.from(auswahl) });
  };

  const zuruecksetzen = () => {
    setAuswahl(new Set(sichtbar.map((s) => s.key)));
    speichernMutation.mutate({ items: null });
  };

  const gruppen = NAV_KATEGORIE_REIHENFOLGE.map((kategorie) => ({
    kategorie,
    seiten: sichtbar.filter((seite) => seite.kategorie === kategorie),
  })).filter((gruppe) => gruppe.seiten.length > 0);

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <button
          onClick={() => navigate(-1)}
          className="text-sm text-label2"
        >
          ‹ Zurück
        </button>
        <h1 className="mt-1 text-lg font-bold text-label">
          Seitenleiste anpassen
        </h1>
        <p className="mt-1 text-sm text-label2">
          Wähle, welche Bereiche in deiner Office-Seitenleiste erscheinen sollen. Die Auswahl
          gilt nur für dich und ändert nichts an deinen eigentlichen Rechten.
        </p>
      </div>

      {gruppen.map(({ kategorie, seiten }) => (
        <section key={kategorie} className="space-y-2">
          <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-label2">
            {kategorie}
          </h2>
          <div className="divide-y divide-sep rounded-lg bg-white shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 ">
            {seiten.map((seite) => (
              <label
                key={seite.key}
                className="btn-touch flex cursor-pointer items-center gap-3 p-3"
              >
                <input
                  type="checkbox"
                  checked={auswahl.has(seite.key)}
                  onChange={() => toggle(seite.key)}
                  className="size-4 rounded border-sep text-cyan-600 focus:ring-cyan-500 dark:bg-stone-800"
                />
                <IconBadge icon={seite.icon} tone={seite.tone} size="sm" />
                <span className="min-w-0 flex-1 truncate font-medium text-label">
                  {seite.label}
                </span>
              </label>
            ))}
          </div>
        </section>
      ))}

      <div className="flex flex-wrap gap-3">
        <button
          onClick={speichern}
          disabled={speichernMutation.isPending}
          className="btn-ap-primary flex-1"
        >
          {speichernMutation.isPending ? "Speichern…" : "Speichern"}
        </button>
        <button
          onClick={zuruecksetzen}
          className="btn-touch flex items-center justify-center gap-2 rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-label shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 "
        >
          <RotateCcw size={16} /> Alle anzeigen
        </button>
      </div>
    </div>
  );
}
