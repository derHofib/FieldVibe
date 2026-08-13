import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Pencil, Plus, RotateCcw, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { usersApi } from "../../api/endpoints";
import { IconBadge } from "../../components/IconBadge";
import { useAuth } from "../../context/AuthContext";
import {
  LINKS_SLOT_ANZAHL,
  type NavKategorie,
  type NavSeite,
  effektiveLinks,
  effektiveRotunde,
  sichtbareNavSeiten,
} from "../../config/navSeiten";
import type { BottomNavPraeferenz } from "../../types";

const KATEGORIE_REIHENFOLGE: NavKategorie[] = ["Arbeit", "Finanzen", "Kommunikation", "Verwaltung"];

// Waehrend ein fester Platz links bearbeitet wird, zeigt die Seite darunter
// eine Auswahlliste speziell fuer diesen Platz (statt fuer die Rotunde).
type BearbeiteterPlatz = { index: number } | null;

export function BottomNavSettingsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser, hatRecht } = useAuth();
  const [bearbeiteterPlatz, setBearbeiteterPlatz] = useState<BearbeiteterPlatz>(null);

  const sichtbar = sichtbareNavSeiten(currentUser, hatRecht);
  const sichtbarByKey = new Map(sichtbar.map((seite) => [seite.key, seite]));
  const linksKeys = effektiveLinks(currentUser?.bottom_nav_items?.links, sichtbar);
  const rotundeKeys = effektiveRotunde(currentUser?.bottom_nav_items?.rotunde, sichtbar);
  // Eine Seite darf nicht gleichzeitig fest und in der Rotunde stecken --
  // beide Auswahllisten unten blenden bereits verwendete Seiten deshalb aus.
  const belegteKeys = new Set([...linksKeys, ...rotundeKeys]);

  const speichernMutation = useMutation({
    mutationFn: (praeferenz: BottomNavPraeferenz) => usersApi.updateOwnBottomNav(praeferenz),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });

  const speichern = (naechsteLinks: string[], naechsteRotunde: string[]) =>
    speichernMutation.mutate({ links: naechsteLinks, rotunde: naechsteRotunde });
  const zuruecksetzen = () => speichernMutation.mutate({ links: null, rotunde: null });

  const platzWaehlen = (index: number, key: string) => {
    const naechsteLinks = [...linksKeys];
    naechsteLinks[index] = key;
    speichern(naechsteLinks, rotundeKeys);
    setBearbeiteterPlatz(null);
  };

  const rotundeHinzufuegen = (key: string) => speichern(linksKeys, [...rotundeKeys, key]);
  const rotundeEntfernen = (key: string) =>
    speichern(
      linksKeys,
      rotundeKeys.filter((k) => k !== key),
    );
  const rotundeVerschieben = (index: number, richtung: -1 | 1) => {
    const ziel = index + richtung;
    if (ziel < 0 || ziel >= rotundeKeys.length) return;
    const naechste = [...rotundeKeys];
    [naechste[index], naechste[ziel]] = [naechste[ziel], naechste[index]];
    speichern(linksKeys, naechste);
  };

  const verfuegbareSeiten = (ausschluss: Set<string>) =>
    KATEGORIE_REIHENFOLGE.map((kategorie) => ({
      kategorie,
      seiten: sichtbar.filter((s) => s.kategorie === kategorie && !ausschluss.has(s.key)),
    })).filter((gruppe) => gruppe.seiten.length > 0);

  return (
    <div className="space-y-6">
      <div>
        <button
          onClick={() => navigate("/einstellungen")}
          className="text-sm text-slate-500 dark:text-stone-400"
        >
          ‹ Einstellungen
        </button>
        <h1 className="mt-1 text-lg font-bold text-slate-800 dark:text-stone-100">
          Menüleiste anpassen
        </h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-stone-400">
          Links vom Neu-Button stehen 2 feste Icons, rechts davon eine wischbare Rotunde mit
          deinen Schnellzugriffen.
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
          Feste Icons (links vom Neu-Button)
        </h2>
        {Array.from({ length: LINKS_SLOT_ANZAHL }).map((_, index) => {
          const seite: NavSeite | undefined = sichtbarByKey.get(linksKeys[index] ?? "");
          return (
            <div
              key={index}
              className="flex items-center gap-3 rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
            >
              {seite ? (
                <>
                  <IconBadge icon={seite.icon} tone={seite.tone} size="sm" />
                  <span className="min-w-0 flex-1 truncate font-medium text-slate-800 dark:text-stone-100">
                    {seite.label}
                  </span>
                </>
              ) : (
                <span className="min-w-0 flex-1 text-slate-400 dark:text-stone-500">
                  Seite wählen…
                </span>
              )}
              <button
                onClick={() => setBearbeiteterPlatz({ index })}
                aria-label={seite ? `${seite.label} ändern` : `Platz ${index + 1} belegen`}
                className="btn-touch flex items-center justify-center text-slate-400 dark:text-stone-500"
              >
                <Pencil size={18} />
              </button>
            </div>
          );
        })}
      </section>

      {bearbeiteterPlatz && (
        <section className="space-y-2">
          <div className="flex items-center justify-between px-1">
            <h2 className="text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
              Platz {bearbeiteterPlatz.index + 1} belegen mit …
            </h2>
            <button
              onClick={() => setBearbeiteterPlatz(null)}
              className="text-xs font-medium text-slate-400 dark:text-stone-500"
            >
              Abbrechen
            </button>
          </div>
          {verfuegbareSeiten(
            new Set([...belegteKeys].filter((key) => key !== linksKeys[bearbeiteterPlatz.index])),
          ).map(({ kategorie, seiten }) => (
            <div key={kategorie} className="space-y-2">
              <h3 className="px-1 text-[11px] font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
                {kategorie}
              </h3>
              {seiten.map((seite) => (
                <button
                  key={seite.key}
                  onClick={() => platzWaehlen(bearbeiteterPlatz.index, seite.key)}
                  className="card-interactive btn-touch flex w-full items-center gap-3 rounded-lg bg-white p-3 text-left shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
                >
                  <IconBadge icon={seite.icon} tone={seite.tone} size="sm" active={false} />
                  <span className="min-w-0 flex-1 truncate font-medium text-slate-700 dark:text-stone-200">
                    {seite.label}
                  </span>
                </button>
              ))}
            </div>
          ))}
        </section>
      )}

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
          Rotunde (wischbar, rechts vom Neu-Button)
        </h2>
        {rotundeKeys.length === 0 && (
          <p className="rounded-lg bg-white p-4 text-sm text-slate-500 shadow-sm dark:bg-stone-900 dark:text-stone-400 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            Noch keine Schnellzugriffe ausgewählt.
          </p>
        )}
        {rotundeKeys.map((key, index) => {
          const seite = sichtbarByKey.get(key);
          if (!seite) return null;
          return (
            <div
              key={key}
              className="flex items-center gap-3 rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
            >
              <IconBadge icon={seite.icon} tone={seite.tone} size="sm" />
              <span className="min-w-0 flex-1 truncate font-medium text-slate-800 dark:text-stone-100">
                {seite.label}
              </span>
              <button
                onClick={() => rotundeVerschieben(index, -1)}
                disabled={index === 0}
                aria-label={`${seite.label} nach oben`}
                className="btn-touch flex items-center justify-center text-slate-400 disabled:opacity-30 dark:text-stone-500"
              >
                <ChevronUp size={18} />
              </button>
              <button
                onClick={() => rotundeVerschieben(index, 1)}
                disabled={index === rotundeKeys.length - 1}
                aria-label={`${seite.label} nach unten`}
                className="btn-touch flex items-center justify-center text-slate-400 disabled:opacity-30 dark:text-stone-500"
              >
                <ChevronDown size={18} />
              </button>
              <button
                onClick={() => rotundeEntfernen(key)}
                aria-label={`${seite.label} entfernen`}
                className="btn-touch flex items-center justify-center text-rose-500"
              >
                <X size={18} />
              </button>
            </div>
          );
        })}
      </section>

      {!bearbeiteterPlatz &&
        verfuegbareSeiten(belegteKeys).map(({ kategorie, seiten }) => (
          <section key={kategorie} className="space-y-2">
            <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
              {kategorie}
            </h2>
            {seiten.map((seite) => (
              <button
                key={seite.key}
                onClick={() => rotundeHinzufuegen(seite.key)}
                className="card-interactive btn-touch flex w-full items-center gap-3 rounded-lg bg-white p-3 text-left shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
              >
                <IconBadge icon={seite.icon} tone={seite.tone} size="sm" active={false} />
                <span className="min-w-0 flex-1 truncate font-medium text-slate-700 dark:text-stone-200">
                  {seite.label}
                </span>
                <Plus size={18} className="shrink-0 text-slate-300 dark:text-stone-600" />
              </button>
            ))}
          </section>
        ))}

      <button
        onClick={zuruecksetzen}
        className="btn-touch flex w-full items-center justify-center gap-2 rounded-lg bg-white py-2.5 text-sm font-medium text-slate-600 shadow-sm dark:bg-stone-900 dark:text-stone-300 dark:shadow-none dark:ring-1 dark:ring-stone-800"
      >
        <RotateCcw size={16} /> Auf Standard zurücksetzen
      </button>
    </div>
  );
}
