import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Repeat } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { anlagenApi, standorteApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import type { Adresse } from "../../types";

const STATUS_BADGE: Record<string, string> = {
  neu: "bg-blue-100 text-blue-800 dark:bg-blue-500/15 dark:text-blue-300",
  geplant: "bg-purple-100 text-purple-800 dark:bg-purple-500/15 dark:text-purple-300",
  in_arbeit: "bg-amber-100 text-amber-800 dark:bg-amber-500/15 dark:text-amber-300",
  wartet_kunde: "bg-orange-100 text-orange-800 dark:bg-orange-500/15 dark:text-orange-300",
  abgeschlossen: "bg-green-100 text-green-800 dark:bg-green-500/15 dark:text-green-300",
  abgerechnet: "bg-slate-200 text-slate-700 dark:bg-slate-700 dark:text-slate-300",
  storniert: "bg-slate-100 text-slate-400 dark:bg-slate-800 dark:text-slate-500",
};

function AdresseBearbeiten({
  standortId,
  adresse,
  kannVerwalten,
}: {
  standortId: string;
  adresse: Adresse;
  kannVerwalten: boolean;
}) {
  const queryClient = useQueryClient();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [form, setForm] = useState({
    strasse: adresse.strasse ?? "",
    plz: adresse.plz ?? "",
    ort: adresse.ort ?? "",
  });

  const speichernMutation = useMutation({
    mutationFn: () =>
      standorteApi.update(standortId, {
        adresse: { strasse: form.strasse || undefined, plz: form.plz || undefined, ort: form.ort || undefined },
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["standort-profil", standortId] });
      setBearbeiten(false);
    },
  });

  if (!bearbeiten) {
    const zeile = [adresse.strasse, [adresse.plz, adresse.ort].filter(Boolean).join(" ")]
      .filter(Boolean)
      .join(", ");
    if (!zeile && !kannVerwalten) return null;
    return (
      <div className="mt-1 flex items-center gap-2">
        {zeile ? (
          <p className="text-sm text-slate-500 dark:text-slate-400">{zeile}</p>
        ) : (
          kannVerwalten && <p className="text-sm text-slate-400 dark:text-slate-500">Keine Adresse hinterlegt.</p>
        )}
        {kannVerwalten && (
          <button
            onClick={() => {
              setForm({ strasse: adresse.strasse ?? "", plz: adresse.plz ?? "", ort: adresse.ort ?? "" });
              setBearbeiten(true);
            }}
            className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
          >
            Bearbeiten
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="mt-2 space-y-2 rounded-md bg-slate-50 p-2 dark:bg-slate-800/60">
      <input
        value={form.strasse}
        onChange={(e) => setForm({ ...form, strasse: e.target.value })}
        placeholder="Straße + Hausnr."
        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
      />
      <div className="grid grid-cols-2 gap-2">
        <input
          value={form.plz}
          onChange={(e) => setForm({ ...form, plz: e.target.value })}
          placeholder="PLZ"
          className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        <input
          value={form.ort}
          onChange={(e) => setForm({ ...form, ort: e.target.value })}
          placeholder="Ort"
          className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
      </div>
      <div className="flex gap-2">
        <button
          onClick={() => speichernMutation.mutate()}
          disabled={speichernMutation.isPending}
          className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => setBearbeiten(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-1.5 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-300"
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}

function AnlagenVerwaltung({
  standortId,
  kundeId,
  vorhandeneAnlageIds,
  kannVerwalten,
}: {
  standortId: string;
  kundeId: string;
  vorhandeneAnlageIds: Set<string>;
  kannVerwalten: boolean;
}) {
  const queryClient = useQueryClient();
  const [modus, setModus] = useState<"keine" | "neu" | "zuordnen">("keine");
  const [bezeichnung, setBezeichnung] = useState("");
  const [anlagentyp, setAnlagentyp] = useState("");
  const [zuordnenId, setZuordnenId] = useState("");
  const [error, setError] = useState<string | null>(null);

  const { data: kundenAnlagen } = useQuery({
    queryKey: ["anlagen", kundeId],
    queryFn: () => anlagenApi.list(kundeId),
    enabled: modus === "zuordnen",
  });
  const zuordenbar = (kundenAnlagen ?? []).filter((a) => !vorhandeneAnlageIds.has(a.id));

  function reset() {
    setModus("keine");
    setBezeichnung("");
    setAnlagentyp("");
    setZuordnenId("");
    setError(null);
  }

  const invalidate = () =>
    queryClient.invalidateQueries({ queryKey: ["standort-profil", standortId] });

  const neuMutation = useMutation({
    mutationFn: () =>
      anlagenApi.create({ kunde_id: kundeId, standort_id: standortId, bezeichnung, anlagentyp: anlagentyp || undefined }),
    onSuccess: () => {
      invalidate();
      reset();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Anlage konnte nicht angelegt werden"),
  });

  const zuordnenMutation = useMutation({
    mutationFn: () => anlagenApi.update(zuordnenId, { standort_id: standortId }),
    onSuccess: () => {
      invalidate();
      reset();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Anlage konnte nicht zugeordnet werden"),
  });

  function handleSubmitNeu(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!bezeichnung.trim()) {
      setError("Bitte eine Bezeichnung eingeben");
      return;
    }
    neuMutation.mutate();
  }

  if (!kannVerwalten) return null;

  if (modus === "keine") {
    return (
      <div className="flex gap-3">
        <button onClick={() => setModus("neu")} className="btn-touch text-xs text-blue-700 underline dark:text-blue-400">
          + Neue Anlage anlegen
        </button>
        <button
          onClick={() => setModus("zuordnen")}
          className="btn-touch text-xs text-blue-700 underline dark:text-blue-400"
        >
          Bestehende Anlage zuordnen
        </button>
      </div>
    );
  }

  if (modus === "neu") {
    return (
      <form onSubmit={handleSubmitNeu} className="space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
        <input
          autoFocus
          value={bezeichnung}
          onChange={(e) => setBezeichnung(e.target.value)}
          placeholder="Bezeichnung"
          className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        <input
          value={anlagentyp}
          onChange={(e) => setAnlagentyp(e.target.value)}
          placeholder="Typ (optional)"
          className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
        <div className="flex gap-2">
          <button
            type="submit"
            disabled={neuMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
          <button
            type="button"
            onClick={reset}
            className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-300"
          >
            Abbrechen
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="space-y-2 rounded-lg bg-slate-50 p-3 dark:bg-slate-800/60">
      {zuordenbar.length === 0 ? (
        <p className="text-sm text-slate-400 dark:text-slate-500">
          Keine weiteren Anlagen dieses Kunden verfügbar.
        </p>
      ) : (
        <select
          value={zuordnenId}
          onChange={(e) => setZuordnenId(e.target.value)}
          className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        >
          <option value="">Anlage wählen…</option>
          {zuordenbar.map((a) => (
            <option key={a.id} value={a.id}>
              {a.bezeichnung}
            </option>
          ))}
        </select>
      )}
      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
      <div className="flex gap-2">
        <button
          disabled={!zuordnenId || zuordnenMutation.isPending}
          onClick={() => zuordnenMutation.mutate()}
          className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Zuordnen
        </button>
        <button
          type="button"
          onClick={reset}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700 dark:border-slate-700 dark:text-slate-300"
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}

export function StandortDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { hatRecht } = useAuth();
  const kannVerwalten = hatRecht("kunden", "bearbeiten");
  const kannLoeschen = hatRecht("kunden", "loeschen");

  const { data: profil, isLoading } = useQuery({
    queryKey: ["standort-profil", id],
    queryFn: () => standorteApi.profil(id!),
    enabled: !!id,
  });

  const toggleAktivMutation = useMutation({
    mutationFn: () => standorteApi.update(id!, { aktiv: !profil!.aktiv }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["standort-profil", id] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => standorteApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["standorte"] });
      navigate("/feed");
    },
  });

  if (isLoading || !profil) return <p className="text-center text-slate-500 dark:text-slate-400">Lädt…</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-slate-400">
          ← Zurück
        </button>
        {kannLoeschen && (
          <button
            onClick={() => {
              if (window.confirm("Standort wirklich löschen? Verknüpfte Daten wandern in den Papierkorb.")) {
                deleteMutation.mutate();
              }
            }}
            disabled={deleteMutation.isPending}
            className="btn-touch text-sm font-medium text-red-700 disabled:opacity-50 dark:text-red-400"
          >
            Standort löschen
          </button>
        )}
      </div>

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <div className="flex items-start justify-between">
          <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">{profil.bezeichnung}</h1>
          {kannVerwalten && (
            <button
              onClick={() => toggleAktivMutation.mutate()}
              disabled={toggleAktivMutation.isPending}
              className="btn-touch shrink-0 rounded-md bg-slate-100 px-3 py-1.5 text-xs font-semibold text-slate-700 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300"
            >
              {profil.aktiv ? "Deaktivieren" : "Aktivieren"}
            </button>
          )}
        </div>
        {!profil.aktiv && (
          <span className="mt-1 inline-block rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-700 dark:text-slate-300">
            inaktiv
          </span>
        )}
        {profil.kunde && (
          <button
            onClick={() => navigate(`/kunden/${profil.kunde!.id}`)}
            className="mt-1 block text-sm text-blue-700 underline-offset-2 hover:underline dark:text-blue-400"
          >
            {profil.kunde.name}
          </button>
        )}
        <AdresseBearbeiten standortId={id!} adresse={profil.adresse} kannVerwalten={kannVerwalten} />
      </div>

      <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
        <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-slate-400">Auswertung</h2>
        {Object.keys(profil.vorgaenge_nach_status).length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-slate-500">Noch keine Vorgänge an diesem Standort.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {Object.entries(profil.vorgaenge_nach_status).map(([status, anzahl]) => (
              <span
                key={status}
                className={`rounded-full px-2 py-1 text-xs font-semibold ${
                  STATUS_BADGE[status] ?? "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                }`}
              >
                {anzahl}× {status}
              </span>
            ))}
          </div>
        )}
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-slate-400">Assets an diesem Standort</h2>
        {profil.anlagen.length === 0 ? (
          <p className="mb-2 text-sm text-slate-400 dark:text-slate-500">Keine Assets an diesem Standort.</p>
        ) : (
          <div className="mb-2 space-y-2">
            {profil.anlagen.map((a) => (
              <button
                key={a.id}
                onClick={() => navigate(`/anlagen/${a.id}`)}
                className={`card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800 ${
                  a.aktiv ? "" : "opacity-60"
                }`}
              >
                <div>
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-100">{a.bezeichnung}</div>
                  {a.anlagentyp && <div className="text-xs text-slate-400 dark:text-slate-500">{a.anlagentyp}</div>}
                </div>
                {!a.aktiv && (
                  <span className="rounded-full bg-slate-200 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-700 dark:text-slate-300">
                    inaktiv
                  </span>
                )}
              </button>
            ))}
          </div>
        )}
        <AnlagenVerwaltung
          standortId={id!}
          kundeId={profil.kunde_id}
          vorhandeneAnlageIds={new Set(profil.anlagen.map((a) => a.id))}
          kannVerwalten={kannVerwalten}
        />
      </div>

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-500 dark:text-slate-400">Vorgänge an diesem Standort</h2>
        {profil.vorgaenge.length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-slate-500">Keine Vorgänge.</p>
        ) : (
          <div className="space-y-2">
            {profil.vorgaenge.map((v) => (
              <button
                key={v.id}
                onClick={() => navigate(`/vorgaenge/${v.id}`)}
                className={`card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800 ${
                  v.status === "storniert" ? "opacity-60 grayscale" : ""
                }`}
              >
                <div>
                  <div className="text-xs text-slate-400 dark:text-slate-500">
                    {v.vorgangsnummer}
                    {v.dauerauftrag_id && (
                      <>
                        {" · "}
                        <Repeat size={11} strokeWidth={2} className="inline text-amber-500" />
                      </>
                    )}
                  </div>
                  <div className="text-sm font-medium text-slate-800 dark:text-slate-100">{v.titel}</div>
                </div>
                <span className={`rounded-full px-2 py-1 text-xs font-semibold ${STATUS_BADGE[v.status]}`}>
                  {v.status}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
