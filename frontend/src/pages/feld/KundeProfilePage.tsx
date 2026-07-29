import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { anlagenApi, dauerauftraegeApi, kundenApi, usersApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { useAuth } from "../../context/AuthContext";
import type { Anlage, User } from "../../types";

const STATUS_BADGE: Record<string, string> = {
  neu: "bg-blue-100 text-blue-800",
  geplant: "bg-purple-100 text-purple-800",
  in_arbeit: "bg-amber-100 text-amber-800",
  wartet_kunde: "bg-orange-100 text-orange-800",
  abgeschlossen: "bg-green-100 text-green-800",
  abgerechnet: "bg-slate-200 text-slate-700",
  storniert: "bg-red-100 text-red-800",
};

function TechnikerZuweisung({ kundeId, zugewiesen }: { kundeId: string; zugewiesen: User[] }) {
  const queryClient = useQueryClient();
  const [bearbeiten, setBearbeiten] = useState(false);
  const [auswahl, setAuswahl] = useState<string[]>([]);

  const { data: alleUser } = useQuery({
    queryKey: ["users"],
    queryFn: usersApi.list,
    enabled: bearbeiten,
  });
  const techniker = alleUser?.filter((u) => u.role === "techniker") ?? [];

  const speichernMutation = useMutation({
    mutationFn: () => kundenApi.technikerSetzen(kundeId, auswahl),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kundeId] });
      setBearbeiten(false);
    },
  });

  function toggle(userId: string) {
    setAuswahl((prev) =>
      prev.includes(userId) ? prev.filter((id) => id !== userId) : [...prev, userId]
    );
  }

  if (!bearbeiten) {
    return (
      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-500">Zugewiesene Techniker</h2>
        {zugewiesen.length === 0 ? (
          <p className="text-sm text-slate-400">Kein Techniker zugewiesen.</p>
        ) : (
          <div className="flex flex-wrap gap-1">
            {zugewiesen.map((t) => (
              <span key={t.id} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                {t.name}
              </span>
            ))}
          </div>
        )}
        <button
          onClick={() => {
            setAuswahl(zugewiesen.map((t) => t.id));
            setBearbeiten(true);
          }}
          className="btn-touch mt-2 text-xs text-blue-700 underline"
        >
          Bearbeiten
        </button>
      </div>
    );
  }

  return (
    <div className="rounded-lg bg-slate-50 p-3">
      <h2 className="mb-2 text-sm font-semibold text-slate-500">Zugewiesene Techniker</h2>
      {techniker.length === 0 ? (
        <p className="text-sm text-slate-400">Keine Techniker in diesem Mandanten angelegt.</p>
      ) : (
        <div className="space-y-1">
          {techniker.map((u) => (
            <label key={u.id} className="btn-touch flex items-center gap-2 text-sm text-slate-700">
              <input
                type="checkbox"
                checked={auswahl.includes(u.id)}
                onChange={() => toggle(u.id)}
              />
              {u.name}
            </label>
          ))}
        </div>
      )}
      <div className="mt-2 flex gap-2">
        <button
          onClick={() => speichernMutation.mutate()}
          disabled={speichernMutation.isPending}
          className="btn-touch flex-1 rounded-md bg-slate-900 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => setBearbeiten(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700"
        >
          Abbrechen
        </button>
      </div>
    </div>
  );
}

function NeueAnlage({ kundeId }: { kundeId: string }) {
  const queryClient = useQueryClient();
  const [zeigen, setZeigen] = useState(false);
  const [bezeichnung, setBezeichnung] = useState("");
  const [anlagentyp, setAnlagentyp] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      anlagenApi.create({ kunde_id: kundeId, bezeichnung, anlagentyp: anlagentyp || undefined }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kundeId] });
      setZeigen(false);
      setBezeichnung("");
      setAnlagentyp("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Anlage konnte nicht angelegt werden"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!bezeichnung.trim()) {
      setError("Bitte eine Bezeichnung eingeben");
      return;
    }
    createMutation.mutate();
  }

  if (!zeigen) {
    return (
      <button onClick={() => setZeigen(true)} className="btn-touch text-xs text-blue-700 underline">
        + Neue Anlage anlegen
      </button>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2 rounded-lg bg-slate-50 p-3">
      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">Bezeichnung</label>
        <input
          autoFocus
          value={bezeichnung}
          onChange={(e) => setBezeichnung(e.target.value)}
          className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700">Typ (optional)</label>
        <input
          value={anlagentyp}
          onChange={(e) => setAnlagentyp(e.target.value)}
          placeholder="z.B. Hauptverteilung, PV-Anlage, Wallbox"
          className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2"
        />
      </div>
      {error && <p className="text-sm text-red-700">{error}</p>}
      <div className="flex gap-2">
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="btn-touch flex-1 rounded-md bg-slate-900 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          Anlegen
        </button>
        <button
          type="button"
          onClick={() => setZeigen(false)}
          className="btn-touch flex-1 rounded-md border border-slate-300 py-2 text-sm font-medium text-slate-700"
        >
          Abbrechen
        </button>
      </div>
    </form>
  );
}

function DauerauftraegeUebersicht({ kundeId }: { kundeId: string }) {
  const navigate = useNavigate();
  const { data: dauerauftraege } = useQuery({
    queryKey: ["dauerauftraege", kundeId],
    queryFn: () => dauerauftraegeApi.list(kundeId),
  });

  return (
    <div>
      <h2 className="mb-2 text-sm font-semibold text-slate-500">Dauer-Aufträge</h2>
      {!dauerauftraege || dauerauftraege.length === 0 ? (
        <p className="text-sm text-slate-400">Keine Dauer-Aufträge.</p>
      ) : (
        <div className="space-y-2">
          {dauerauftraege.map((d) => (
            <button
              key={d.id}
              onClick={() => navigate(`/dauerauftraege/${d.id}`)}
              className="btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm"
            >
              <div>
                <div className="text-sm font-medium text-slate-800">{d.titel}</div>
                <div className="text-xs text-slate-400">
                  alle {d.intervall_tage} Tage · nächste Fälligkeit {d.naechste_faelligkeit_am}
                </div>
              </div>
              {!d.aktiv && (
                <span className="rounded-full bg-slate-200 px-2 py-1 text-xs text-slate-600">
                  pausiert
                </span>
              )}
            </button>
          ))}
        </div>
      )}
      <button
        onClick={() => navigate(`/dauerauftraege/neu?kunde_id=${kundeId}`)}
        className="btn-touch mt-2 text-xs text-blue-700 underline"
      >
        + Neuen Dauer-Auftrag anlegen
      </button>
    </div>
  );
}

export function KundeProfilePage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const [anlageFilter, setAnlageFilter] = useState("");

  const { data: profil, isLoading } = useQuery({
    queryKey: ["kunde-profil", id],
    queryFn: () => kundenApi.profil(id!),
    enabled: !!id,
  });

  const anlageNameById = useMemo(
    () => new Map((profil?.anlagen ?? []).map((a: Anlage) => [a.id, a.bezeichnung])),
    [profil?.anlagen]
  );
  const sichtbareVorgaenge = useMemo(
    () =>
      anlageFilter
        ? (profil?.vorgaenge ?? []).filter((v) => v.anlage_id === anlageFilter)
        : profil?.vorgaenge ?? [],
    [profil?.vorgaenge, anlageFilter]
  );

  if (isLoading || !profil) return <p className="text-center text-slate-500">Lädt…</p>;

  const kannVerwalten =
    currentUser?.role === "mandant_admin" || currentUser?.role === "disponent";

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500">
        ← Zurück
      </button>

      <div className="rounded-lg bg-white p-4 shadow-sm">
        <div className="text-xs text-slate-400">{profil.kundennummer}</div>
        <h1 className="text-lg font-bold text-slate-800">{profil.name}</h1>
        {profil.typ && <span className="text-sm text-slate-500">{profil.typ}</span>}
        {profil.tags.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1">
            {profil.tags.map((t) => (
              <span key={t.id} className="rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600">
                #{t.label}
              </span>
            ))}
          </div>
        )}
      </div>

      {kannVerwalten && <TechnikerZuweisung kundeId={id!} zugewiesen={profil.techniker} />}

      <div>
        <h2 className="mb-2 text-sm font-semibold text-slate-500">Anlagen</h2>
        {profil.anlagen.length === 0 ? (
          <p className="text-sm text-slate-400">Keine Anlagen.</p>
        ) : (
          <div className="space-y-2">
            {profil.anlagen.map((a) => (
              <button
                key={a.id}
                onClick={() => navigate(`/anlagen/${a.id}`)}
                className="btn-touch block w-full rounded-lg bg-white p-3 text-left shadow-sm"
              >
                <div className="text-sm font-medium text-slate-800">{a.bezeichnung}</div>
                {a.anlagentyp && <div className="text-xs text-slate-400">{a.anlagentyp}</div>}
              </button>
            ))}
          </div>
        )}
        {kannVerwalten && (
          <div className="mt-2">
            <NeueAnlage kundeId={id!} />
          </div>
        )}
      </div>

      {kannVerwalten && <DauerauftraegeUebersicht kundeId={id!} />}

      <div>
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500">Vorgänge</h2>
          {profil.anlagen.length > 0 && (
            <select
              value={anlageFilter}
              onChange={(e) => setAnlageFilter(e.target.value)}
              className="btn-touch rounded-md border border-slate-300 px-2 py-1 text-xs"
            >
              <option value="">Alle Anlagen</option>
              {profil.anlagen.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.bezeichnung}
                </option>
              ))}
            </select>
          )}
        </div>
        {sichtbareVorgaenge.length === 0 ? (
          <p className="text-sm text-slate-400">Keine Vorgänge.</p>
        ) : (
          <div className="space-y-2">
            {sichtbareVorgaenge.map((v) => (
              <button
                key={v.id}
                onClick={() => navigate(`/vorgaenge/${v.id}`)}
                className="btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm"
              >
                <div>
                  <div className="text-xs text-slate-400">
                    {v.vorgangsnummer}
                    {v.anlage_id && anlageNameById.get(v.anlage_id) && ` · ${anlageNameById.get(v.anlage_id)}`}
                    {v.dauerauftrag_id && " · 🔁"}
                  </div>
                  <div className="text-sm font-medium text-slate-800">{v.titel}</div>
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
