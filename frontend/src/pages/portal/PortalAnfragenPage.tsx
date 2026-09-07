import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquareText } from "lucide-react";
import { useState, type FormEvent } from "react";

import { kundenportalApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import type { Leistungstyp, VorgangAnfrageStatus } from "../../types";

const LEISTUNGSTYPEN: { value: Leistungstyp; label: string }[] = [
  { value: "stoerung", label: "Störung" },
  { value: "installation", label: "Installation" },
  { value: "wartung", label: "Wartung" },
  { value: "pruefung", label: "Prüfung" },
  { value: "beratung", label: "Beratung" },
  { value: "planung", label: "Planung" },
];

const STATUS_LABEL: Record<VorgangAnfrageStatus, string> = {
  offen: "In Prüfung",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

const STATUS_BADGE: Record<VorgangAnfrageStatus, string> = {
  offen: "border border-amber-400 text-amber-700 dark:border-amber-600 dark:text-amber-300",
  angenommen: "border border-green-400 text-green-700 dark:border-green-600 dark:text-green-300",
  abgelehnt: "border border-slate-300 text-slate-500 dark:border-stone-700 dark:text-stone-400",
};

function NeueAnfrage() {
  const queryClient = useQueryClient();
  const [zeigen, setZeigen] = useState(false);
  const [titel, setTitel] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [leistungstyp, setLeistungstyp] = useState<Leistungstyp>("stoerung");
  const [standortId, setStandortId] = useState("");
  const [anlageId, setAnlageId] = useState("");
  const [zeigeNeuerStandort, setZeigeNeuerStandort] = useState(false);
  const [neuerStandortName, setNeuerStandortName] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: standorte } = useQuery({
    queryKey: ["portal-standorte"],
    queryFn: kundenportalApi.standorte,
    enabled: zeigen,
  });
  const { data: anlagen } = useQuery({
    queryKey: ["portal-anlagen"],
    queryFn: kundenportalApi.anlagen,
    enabled: zeigen,
  });
  const anlagenFuerStandort = (anlagen ?? []).filter((a) => !standortId || a.standort_id === standortId);

  const neuerStandortMutation = useMutation({
    mutationFn: () => kundenportalApi.standortAnlegen({ bezeichnung: neuerStandortName }),
    onSuccess: (standort) => {
      queryClient.invalidateQueries({ queryKey: ["portal-standorte"] });
      setStandortId(standort.id);
      setZeigeNeuerStandort(false);
      setNeuerStandortName("");
    },
  });

  const createMutation = useMutation({
    mutationFn: () =>
      kundenportalApi.anfrageAnlegen({
        titel,
        beschreibung: beschreibung || undefined,
        leistungstyp,
        standort_id: standortId || undefined,
        anlage_id: anlageId || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal-anfragen"] });
      setZeigen(false);
      setTitel("");
      setBeschreibung("");
      setStandortId("");
      setAnlageId("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Anfrage konnte nicht gesendet werden"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!titel.trim()) {
      setError("Bitte einen Titel eingeben");
      return;
    }
    createMutation.mutate();
  }

  if (!zeigen) {
    return (
      <button
        onClick={() => setZeigen(true)}
        className="btn-touch w-full rounded-lg btn-industry btn-industry-primary py-3 text-sm font-medium"
      >
        + Neue Auftragsanfrage stellen
      </button>
    );
  }

  return (
    <form
      onSubmit={handleSubmit}
      className="space-y-3 border border-ind-line bg-ind-bg p-4"
    >
      <p className="text-xs text-ind-ink-3">
        Ihre Anfrage wird von uns geprüft und in einen Auftrag übernommen, sobald sie bestätigt ist.
      </p>
      <div>
        <label className="mb-1 block text-sm font-medium text-ind-ink-2">Titel</label>
        <input
          autoFocus
          value={titel}
          onChange={(e) => setTitel(e.target.value)}
          className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
        />
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium text-ind-ink-2">Beschreibung</label>
        <textarea
          value={beschreibung}
          onChange={(e) => setBeschreibung(e.target.value)}
          rows={3}
          className="w-full resize-none border border-ind-line bg-transparent p-2 text-ind-ink"
        />
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium text-ind-ink-2">Art</label>
        <select
          value={leistungstyp}
          onChange={(e) => setLeistungstyp(e.target.value as Leistungstyp)}
          className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
        >
          {LEISTUNGSTYPEN.map((l) => (
            <option key={l.value} value={l.value}>
              {l.label}
            </option>
          ))}
        </select>
      </div>

      {(standorte ?? []).length > 0 && (
        <div>
          <label className="mb-1 block text-sm font-medium text-ind-ink-2">
            Standort (optional)
          </label>
          <select
            value={standortId}
            onChange={(e) => {
              setStandortId(e.target.value);
              setAnlageId("");
            }}
            className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
          >
            <option value="">Kein Standort</option>
            {standorte?.filter((s) => s.aktiv).map((s) => (
              <option key={s.id} value={s.id}>
                {s.bezeichnung}
              </option>
            ))}
          </select>
        </div>
      )}

      {!zeigeNeuerStandort ? (
        <button
          type="button"
          onClick={() => setZeigeNeuerStandort(true)}
          className="btn-touch text-xs text-blue-700 underline dark:text-blue-400"
        >
          + Neuen Standort anlegen
        </button>
      ) : (
        <div className="flex gap-2">
          <input
            value={neuerStandortName}
            onChange={(e) => setNeuerStandortName(e.target.value)}
            placeholder="Bezeichnung (z.B. Filiale Nord)"
            className="btn-touch flex-1 border border-ind-line bg-transparent px-3 py-2 text-sm text-ind-ink"
          />
          <button
            type="button"
            disabled={!neuerStandortName.trim() || neuerStandortMutation.isPending}
            onClick={() => neuerStandortMutation.mutate()}
            className="btn-touch shrink-0 rounded-md bg-slate-800 px-3 py-2 text-xs font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      {anlagenFuerStandort.length > 0 && (
        <div>
          <label className="mb-1 block text-sm font-medium text-ind-ink-2">
            Anlage (optional)
          </label>
          <select
            value={anlageId}
            onChange={(e) => setAnlageId(e.target.value)}
            className="btn-touch w-full border border-ind-line bg-transparent px-3 py-2 text-ind-ink"
          >
            <option value="">Keine Anlage</option>
            {anlagenFuerStandort.filter((a) => a.aktiv).map((a) => (
              <option key={a.id} value={a.id}>
                {a.bezeichnung}
              </option>
            ))}
          </select>
        </div>
      )}

      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}

      <div className="flex gap-2">
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="btn-touch flex-1 rounded-md btn-industry btn-industry-primary py-2 text-sm font-medium disabled:opacity-50"
        >
          Anfrage senden
        </button>
        <button
          type="button"
          onClick={() => setZeigen(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-stone-700 dark:text-stone-300"
        >
          Abbrechen
        </button>
      </div>
    </form>
  );
}

export function PortalAnfragenPage() {
  const { data: anfragen, isLoading } = useQuery({
    queryKey: ["portal-anfragen"],
    queryFn: kundenportalApi.anfragen,
  });

  return (
    <div className="space-y-3">
      <h1 className="text-lg font-bold text-ind-ink">Ihre Auftragsanfragen</h1>
      <NeueAnfrage />

      {isLoading ? (
        <SkeletonList count={3} />
      ) : !anfragen || anfragen.length === 0 ? (
        <EmptyState icon={MessageSquareText} text="Noch keine Anfragen gestellt." />
      ) : (
        <div className="space-y-2">
          {anfragen.map((a) => (
            <div
              key={a.id}
              className="border border-ind-line bg-ind-bg p-4"
            >
              <div className="flex items-start justify-between">
                <div className="font-medium text-ind-ink">{a.titel}</div>
                <span className={`px-2 py-1 text-xs font-semibold ${STATUS_BADGE[a.status]}`}>
                  {STATUS_LABEL[a.status]}
                </span>
              </div>
              {a.beschreibung && (
                <p className="mt-1 text-sm text-ind-ink-3">{a.beschreibung}</p>
              )}
              {a.ablehnungsgrund && (
                <p className="mt-1 text-xs text-ind-ink-3">Grund: {a.ablehnungsgrund}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
