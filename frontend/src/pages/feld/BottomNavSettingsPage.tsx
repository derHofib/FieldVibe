import { useMutation, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronUp, Plus, RotateCcw, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { usersApi } from "../../api/endpoints";
import { IconBadge } from "../../components/IconBadge";
import { useAuth } from "../../context/AuthContext";
import {
  MANDATORY_KEYS,
  type NavKategorie,
  effektiveNavKeys,
  sichtbareNavSeiten,
} from "../../config/navSeiten";

const KATEGORIE_REIHENFOLGE: NavKategorie[] = ["Arbeit", "Finanzen", "Kommunikation", "Verwaltung"];

export function BottomNavSettingsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser, hatRecht } = useAuth();

  const sichtbar = sichtbareNavSeiten(currentUser, hatRecht);
  const sichtbarByKey = new Map(sichtbar.map((seite) => [seite.key, seite]));
  const gewaehlteKeys = effektiveNavKeys(currentUser?.bottom_nav_items ?? null, sichtbar);

  const speichernMutation = useMutation({
    mutationFn: (items: string[] | null) => usersApi.updateOwnBottomNav(items),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
    },
  });

  const speichern = (naechsteKeys: string[]) => speichernMutation.mutate(naechsteKeys);

  const hinzufuegen = (key: string) => speichern([...gewaehlteKeys, key]);
  const entfernen = (key: string) => {
    // Feed/Profil bleiben Pflicht -- der Entfernen-Button ist fuer sie
    // ohnehin ausgeblendet, dieser Schutz greift nur bei direktem Aufruf.
    if (MANDATORY_KEYS.includes(key)) return;
    speichern(gewaehlteKeys.filter((k) => k !== key));
  };
  const verschieben = (index: number, richtung: -1 | 1) => {
    const ziel = index + richtung;
    if (ziel < 0 || ziel >= gewaehlteKeys.length) return;
    const naechste = [...gewaehlteKeys];
    [naechste[index], naechste[ziel]] = [naechste[ziel], naechste[index]];
    speichern(naechste);
  };
  const zuruecksetzen = () => speichernMutation.mutate(null);

  const verfuegbareNachKategorie = KATEGORIE_REIHENFOLGE.map((kategorie) => ({
    kategorie,
    seiten: sichtbar.filter((s) => s.kategorie === kategorie && !gewaehlteKeys.includes(s.key)),
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
          Feed und Profil sind immer Teil der Leiste, lassen sich aber wie jeder andere Punkt
          verschieben. Nur der Neu-Button bleibt fix in der Mitte. Wähle darüber hinaus aus,
          welche weiteren Seiten erscheinen, und in welcher Reihenfolge.
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
          Sichtbar in der Leiste
        </h2>
        {gewaehlteKeys.length === 0 && (
          <p className="rounded-lg bg-white p-4 text-sm text-slate-500 shadow-sm dark:bg-stone-900 dark:text-stone-400 dark:shadow-none dark:ring-1 dark:ring-stone-800">
            Noch keine weiteren Seiten ausgewählt.
          </p>
        )}
        {gewaehlteKeys.map((key, index) => {
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
                onClick={() => verschieben(index, -1)}
                disabled={index === 0}
                aria-label={`${seite.label} nach oben`}
                className="btn-touch flex items-center justify-center text-slate-400 disabled:opacity-30 dark:text-stone-500"
              >
                <ChevronUp size={18} />
              </button>
              <button
                onClick={() => verschieben(index, 1)}
                disabled={index === gewaehlteKeys.length - 1}
                aria-label={`${seite.label} nach unten`}
                className="btn-touch flex items-center justify-center text-slate-400 disabled:opacity-30 dark:text-stone-500"
              >
                <ChevronDown size={18} />
              </button>
              {!MANDATORY_KEYS.includes(key) && (
                <button
                  onClick={() => entfernen(key)}
                  aria-label={`${seite.label} entfernen`}
                  className="btn-touch flex items-center justify-center text-rose-500"
                >
                  <X size={18} />
                </button>
              )}
            </div>
          );
        })}
      </section>

      {verfuegbareNachKategorie.map(({ kategorie, seiten }) => (
        <section key={kategorie} className="space-y-2">
          <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
            {kategorie}
          </h2>
          {seiten.map((seite) => (
            <button
              key={seite.key}
              onClick={() => hinzufuegen(seite.key)}
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
