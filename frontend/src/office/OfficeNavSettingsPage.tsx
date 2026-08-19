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
          className="text-sm text-slate-500 dark:text-stone-400"
        >
          ‹ Zurück
        </button>
        <h1 className="mt-1 text-lg font-bold text-slate-800 dark:text-stone-100">
          Seitenleiste anpassen
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-stone-400">
          Wähle, welche Bereiche in deiner Office-Seitenleiste erscheinen sollen. Die Auswahl
          gilt nur für dich und ändert nichts an deinen eigentlichen Rechten.
        </p>
      </div>

      {gruppen.map(({ kategorie, seiten }) => (
        <section key={kategorie} className="space-y-2">
          <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
            {kategorie}
          </h2>
          <div className="divide-y divide-slate-100 rounded-lg bg-white shadow-xs dark:divide-stone-800 dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            {seiten.map((seite) => (
              <label
                key={seite.key}
                className="btn-touch flex cursor-pointer items-center gap-3 p-3"
              >
                <input
                  type="checkbox"
                  checked={auswahl.has(seite.key)}
                  onChange={() => toggle(seite.key)}
                  className="size-4 rounded border-slate-300 text-cyan-600 focus:ring-cyan-500 dark:border-stone-600 dark:bg-stone-800"
                />
                <IconBadge icon={seite.icon} tone={seite.tone} size="sm" />
                <span className="min-w-0 flex-1 truncate font-medium text-slate-800 dark:text-stone-100">
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
          className="btn-touch flex-1 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50 dark:bg-cyan-600 dark:hover:bg-cyan-500"
        >
          {speichernMutation.isPending ? "Speichern…" : "Speichern"}
        </button>
        <button
          onClick={zuruecksetzen}
          className="btn-touch flex items-center justify-center gap-2 rounded-lg bg-white px-4 py-2.5 text-sm font-medium text-slate-600 shadow-xs dark:bg-stone-900 dark:text-stone-300 dark:shadow-none dark:ring-1 dark:ring-stone-800"
        >
          <RotateCcw size={16} /> Alle anzeigen
        </button>
      </div>
    </div>
  );
}
