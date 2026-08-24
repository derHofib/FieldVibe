import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { Navigate, useNavigate } from "react-router-dom";

import { navKategorienApi } from "../api/endpoints";
import { ApiError } from "../api/client";
import { IconBadge } from "../components/IconBadge";
import { useAuth } from "../context/AuthContext";
import { NAV_KATEGORIE_REIHENFOLGE, NAV_SEITEN } from "../config/navSeiten";
import type { NavKategorienRead } from "../types";

interface LokaleKategorie {
  localId: string;
  name: string;
}

const OHNE_KATEGORIE = "__ohne__";

export function OfficeNavKategorienPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();

  const { data, isLoading } = useQuery({
    queryKey: ["nav-kategorien"],
    queryFn: () => navKategorienApi.get(),
  });

  const [kategorien, setKategorien] = useState<LokaleKategorie[]>([]);
  const [zuordnungen, setZuordnungen] = useState<Record<string, string>>({});
  const [fehler, setFehler] = useState<string | null>(null);
  // Verhindert, dass ein spaeterer Refetch (z.B. nach dem Speichern) den
  // gerade bearbeiteten Zwischenstand ueberschreibt.
  const [initialisiert, setInitialisiert] = useState(false);

  useEffect(() => {
    if (!data || initialisiert) return;
    if (data.kategorien.length === 0) {
      // Noch nie angepasst -- mit den heutigen Standardkategorien vorbelegen,
      // damit die Seite nicht leer startet.
      const lokale = NAV_KATEGORIE_REIHENFOLGE.map((name) => ({
        localId: crypto.randomUUID(),
        name: name as string,
      }));
      setKategorien(lokale);
      const nameZuLocalId = new Map(lokale.map((k) => [k.name, k.localId]));
      const zu: Record<string, string> = {};
      for (const seite of NAV_SEITEN) {
        const localId = nameZuLocalId.get(seite.kategorie);
        if (localId) zu[seite.key] = localId;
      }
      setZuordnungen(zu);
    } else {
      const lokale = data.kategorien.map((k) => ({ localId: crypto.randomUUID(), name: k.name }));
      setKategorien(lokale);
      const nameZuLocalId = new Map(lokale.map((k) => [k.name, k.localId]));
      const zu: Record<string, string> = {};
      for (const [navKey, kategorieName] of Object.entries(data.zuordnungen)) {
        const localId = nameZuLocalId.get(kategorieName);
        if (localId) zu[navKey] = localId;
      }
      setZuordnungen(zu);
    }
    setInitialisiert(true);
  }, [data, initialisiert]);

  const speichernMutation = useMutation({
    mutationFn: (body: NavKategorienRead) => navKategorienApi.set(body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["nav-kategorien"] });
      navigate(-1);
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Fehler beim Speichern"),
  });

  if (currentUser && currentUser.role !== "mandant_admin") {
    return <Navigate to="/vorgaenge" replace />;
  }

  function kategorieUmbenennen(localId: string, name: string) {
    setKategorien((bisher) => bisher.map((k) => (k.localId === localId ? { ...k, name } : k)));
  }

  function kategorieVerschieben(index: number, richtung: -1 | 1) {
    setKategorien((bisher) => {
      const ziel = index + richtung;
      if (ziel < 0 || ziel >= bisher.length) return bisher;
      const kopie = [...bisher];
      [kopie[index], kopie[ziel]] = [kopie[ziel], kopie[index]];
      return kopie;
    });
  }

  function kategorieLoeschen(localId: string) {
    setKategorien((bisher) => bisher.filter((k) => k.localId !== localId));
    // Zuvor zugeordnete Punkte werden nicht geloescht, sondern landen als
    // "Nicht zugeordnet" -- der Admin sieht sie unten und weist neu zu,
    // statt dass sie kommentarlos verschwinden.
    setZuordnungen((bisher) => {
      const naechste = { ...bisher };
      for (const key of Object.keys(naechste)) {
        if (naechste[key] === localId) delete naechste[key];
      }
      return naechste;
    });
  }

  function kategorieHinzufuegen() {
    setKategorien((bisher) => [...bisher, { localId: crypto.randomUUID(), name: "Neue Kategorie" }]);
  }

  function speichern() {
    setFehler(null);
    const namen = kategorien.map((k) => k.name.trim());
    if (namen.some((n) => n.length === 0)) {
      setFehler("Kategorie-Namen dürfen nicht leer sein.");
      return;
    }
    if (new Set(namen).size !== namen.length) {
      setFehler("Kategorie-Namen müssen eindeutig sein.");
      return;
    }
    const localIdZuName = new Map(kategorien.map((k) => [k.localId, k.name.trim()]));
    const zuordnungenPayload: Record<string, string> = {};
    for (const [navKey, localId] of Object.entries(zuordnungen)) {
      const name = localIdZuName.get(localId);
      if (name) zuordnungenPayload[navKey] = name;
    }
    speichernMutation.mutate({
      kategorien: kategorien.map((k, i) => ({ name: k.name.trim(), reihenfolge: i })),
      zuordnungen: zuordnungenPayload,
    });
  }

  if (isLoading || !initialisiert) {
    return <p className="p-4 text-sm text-slate-500 dark:text-stone-400">Lädt…</p>;
  }

  return (
    <div className="mx-auto max-w-2xl space-y-6">
      <div>
        <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-stone-400">
          ‹ Zurück
        </button>
        <h1 className="mt-1 text-lg font-bold text-slate-800 dark:text-stone-100">Menü-Kategorien</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-stone-400">
          Bestimmt, wie die Office-Seitenleiste gruppiert. Gilt für alle Nutzer dieses Mandanten.
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
          Kategorien
        </h2>
        <div className="divide-y divide-slate-100 rounded-lg bg-white shadow-xs dark:divide-stone-800 dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          {kategorien.map((k, i) => (
            <div key={k.localId} className="flex items-center gap-2 p-3">
              <input
                value={k.name}
                onChange={(e) => kategorieUmbenennen(k.localId, e.target.value)}
                className="min-w-0 flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
              <button
                onClick={() => kategorieVerschieben(i, -1)}
                disabled={i === 0}
                aria-label="Nach oben"
                className="btn-touch rounded-md p-1.5 text-slate-400 disabled:opacity-30 dark:text-stone-500"
              >
                <ArrowUp size={16} />
              </button>
              <button
                onClick={() => kategorieVerschieben(i, 1)}
                disabled={i === kategorien.length - 1}
                aria-label="Nach unten"
                className="btn-touch rounded-md p-1.5 text-slate-400 disabled:opacity-30 dark:text-stone-500"
              >
                <ArrowDown size={16} />
              </button>
              <button
                onClick={() => kategorieLoeschen(k.localId)}
                aria-label="Kategorie löschen"
                className="btn-touch rounded-md p-1.5 text-red-600 dark:text-red-400"
              >
                <Trash2 size={16} />
              </button>
            </div>
          ))}
        </div>
        <button
          onClick={kategorieHinzufuegen}
          className="btn-touch flex items-center gap-1.5 rounded-md px-2 py-1.5 text-sm font-medium text-blue-700 dark:text-blue-400"
        >
          <Plus size={16} /> Kategorie hinzufügen
        </button>
      </section>

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-stone-500">
          Zuordnung
        </h2>
        <div className="divide-y divide-slate-100 rounded-lg bg-white shadow-xs dark:divide-stone-800 dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          {NAV_SEITEN.map((seite) => (
            <div key={seite.key} className="flex items-center gap-3 p-3">
              <IconBadge icon={seite.icon} tone={seite.tone} size="sm" />
              <span className="min-w-0 flex-1 truncate font-medium text-slate-800 dark:text-stone-100">
                {seite.label}
              </span>
              <select
                value={zuordnungen[seite.key] ?? OHNE_KATEGORIE}
                onChange={(e) =>
                  setZuordnungen((bisher) => {
                    const wert = e.target.value;
                    if (wert === OHNE_KATEGORIE) {
                      const { [seite.key]: _entfernt, ...rest } = bisher;
                      return rest;
                    }
                    return { ...bisher, [seite.key]: wert };
                  })
                }
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              >
                <option value={OHNE_KATEGORIE}>Nicht zugeordnet</option>
                {kategorien.map((k) => (
                  <option key={k.localId} value={k.localId}>
                    {k.name}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      </section>

      {fehler && <p className="text-sm text-red-700 dark:text-red-400">{fehler}</p>}

      <button
        onClick={speichern}
        disabled={speichernMutation.isPending}
        className="btn-touch w-full rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white disabled:opacity-50 dark:bg-cyan-600 dark:hover:bg-cyan-500"
      >
        {speichernMutation.isPending ? "Speichern…" : "Speichern"}
      </button>
    </div>
  );
}
