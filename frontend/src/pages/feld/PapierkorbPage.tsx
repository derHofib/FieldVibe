import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { papierkorbApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { ApiError } from "../../api/client";
import type { PapierkorbEintrag, PapierkorbEntityTyp } from "../../types";

// Muss mit ENTITY_REGISTRY in backend/app/services/papierkorb_service.py
// uebereinstimmen.
const ENTITY_TYP_LABEL: Record<PapierkorbEntityTyp, string> = {
  kunde: "Kunde",
  anlage: "Anlage",
  vertrag: "Vertrag",
  vorgang: "Vorgang",
  standort: "Standort",
  termin: "Termin",
  pruefzyklus: "Prüfzyklus",
  pruefmittel: "Prüfmittel",
  lieferant: "Lieferant",
  material: "Material",
  material_bedarf: "Materialbedarf",
  bestellung: "Bestellung",
  dauerauftrag: "Dauerauftrag",
  dauerauftrag_ziel: "Dauerauftrag-Ziel",
  mangel: "Mangel",
  angebot: "Angebot",
  rechnung: "Rechnung",
  inventurzyklus: "Inventurzyklus",
  fahrzeug_zuweisung: "Fahrzeug-Zuweisung",
  tag: "Tag",
  vorgang_anfrage: "Auftragsanfrage",
};

function formatDatum(iso: string): string {
  return new Date(iso).toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
}

function anzeigeName(eintrag: PapierkorbEintrag): string {
  if (eintrag.titel) return eintrag.titel;
  return `${ENTITY_TYP_LABEL[eintrag.entity_typ]} ${eintrag.id.slice(0, 8)}`;
}

export function PapierkorbPage() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [filter, setFilter] = useState<PapierkorbEntityTyp | "">("");
  const [fehler, setFehler] = useState<string | null>(null);

  const istOperativ = currentUser?.role === "loesch_operativ";

  const { data: eintraege, isLoading } = useQuery({
    queryKey: ["papierkorb", filter],
    queryFn: () => papierkorbApi.list(filter || undefined),
  });

  const restoreMutation = useMutation({
    mutationFn: (eintrag: PapierkorbEintrag) =>
      papierkorbApi.wiederherstellen(eintrag.entity_typ, eintrag.id),
    onSuccess: () => {
      setFehler(null);
      queryClient.invalidateQueries({ queryKey: ["papierkorb"] });
    },
    onError: () => setFehler("Wiederherstellen fehlgeschlagen"),
  });

  const purgeMutation = useMutation({
    mutationFn: (eintrag: PapierkorbEintrag) =>
      papierkorbApi.endgueltigLoeschen(eintrag.entity_typ, eintrag.id),
    onSuccess: () => {
      setFehler(null);
      queryClient.invalidateQueries({ queryKey: ["papierkorb"] });
    },
    onError: (err) =>
      setFehler(
        err instanceof ApiError
          ? err.message
          : "Endgültiges Löschen fehlgeschlagen -- vermutlich verweisen noch andere Daten darauf.",
      ),
  });

  // Nur die beiden Papierkorb-Rollen duerfen diese Seite sehen (siehe
  // app/api/routes/papierkorb.py) -- alle anderen landen wieder im Feed.
  if (
    currentUser &&
    currentUser.role !== "loesch_ansicht" &&
    currentUser.role !== "loesch_operativ"
  ) {
    return <Navigate to="/feed" replace />;
  }

  return (
    <div className="mx-auto max-w-3xl space-y-4 p-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-stone-400">
          ← Zurück
        </button>
        <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">Papierkorb</h1>
      </div>

      <p className="text-sm text-slate-500 dark:text-stone-400">
        {istOperativ
          ? "Gelöschte Datensätze können hier wiederhergestellt oder endgültig entfernt werden."
          : "Nur-Ansicht: Wiederherstellen und endgültiges Löschen sind der Rolle „Papierkorb (operativ)“ vorbehalten."}
      </p>

      {fehler && <p className="text-sm text-red-700 dark:text-red-400">{fehler}</p>}

      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-stone-300">
          Nach Typ filtern
        </label>
        <select
          value={filter}
          onChange={(e) => setFilter(e.target.value as PapierkorbEntityTyp | "")}
          className="btn-touch rounded-md border border-slate-300 bg-white px-3 py-2 text-slate-800 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
        >
          <option value="">Alle Typen</option>
          {Object.entries(ENTITY_TYP_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <p className="text-slate-500 dark:text-stone-400">Lädt…</p>
      ) : !eintraege || eintraege.length === 0 ? (
        <p className="rounded-lg bg-white p-4 text-sm text-slate-500 shadow-sm dark:bg-stone-900 dark:text-stone-400">
          Der Papierkorb ist leer.
        </p>
      ) : (
        <ul className="space-y-2">
          {eintraege.map((eintrag) => (
            <li
              key={`${eintrag.entity_typ}-${eintrag.id}`}
              className="flex items-center justify-between gap-3 rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600 dark:bg-stone-800 dark:text-stone-300">
                    {ENTITY_TYP_LABEL[eintrag.entity_typ]}
                  </span>
                  <span className="truncate font-medium text-slate-800 dark:text-stone-100">
                    {anzeigeName(eintrag)}
                  </span>
                </div>
                <p className="mt-0.5 text-xs text-slate-500 dark:text-stone-400">
                  Gelöscht am {formatDatum(eintrag.geloescht_am)}
                  {eintrag.geloescht_von_name ? ` von ${eintrag.geloescht_von_name}` : ""}
                </p>
              </div>
              {istOperativ && (
                <div className="flex shrink-0 gap-2">
                  <button
                    onClick={() => restoreMutation.mutate(eintrag)}
                    disabled={restoreMutation.isPending}
                    className="btn-touch rounded-md bg-cyan-50 px-3 py-2 text-xs font-semibold text-cyan-700 hover:bg-cyan-100 disabled:opacity-50 dark:bg-cyan-500/10 dark:text-cyan-300"
                  >
                    Wiederherstellen
                  </button>
                  <button
                    onClick={() => {
                      if (
                        window.confirm(
                          `„${anzeigeName(eintrag)}“ endgültig löschen? Das kann nicht rückgängig gemacht werden.`,
                        )
                      ) {
                        purgeMutation.mutate(eintrag);
                      }
                    }}
                    disabled={purgeMutation.isPending}
                    className="btn-touch rounded-md bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:opacity-50 dark:bg-red-500/10 dark:text-red-300"
                  >
                    Endgültig löschen
                  </button>
                </div>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
