import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { angeboteApi, kundenApi, rechnungenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import type { AngebotStatus, RechnungStatus } from "../../types";

const ANGEBOT_STATUS_LABEL: Record<AngebotStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

const RECHNUNG_STATUS_LABEL: Record<RechnungStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
};

export function GeschaeftPage() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"angebote" | "rechnungen">("angebote");
  const [showForm, setShowForm] = useState(false);
  const [kundeId, setKundeId] = useState("");
  const [betragNetto, setBetragNetto] = useState("");

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });
  const { data: angebote } = useQuery({ queryKey: ["angebote"], queryFn: () => angeboteApi.list() });
  const { data: rechnungen } = useQuery({ queryKey: ["rechnungen"], queryFn: () => rechnungenApi.list() });

  const createAngebotMutation = useMutation({
    mutationFn: () => angeboteApi.create({ kunde_id: kundeId }),
    onSuccess: (angebot) => {
      queryClient.invalidateQueries({ queryKey: ["angebote"] });
      navigate(`/angebote/${angebot.id}`);
    },
  });

  const createRechnungMutation = useMutation({
    mutationFn: () => rechnungenApi.create({ kunde_id: kundeId, betrag_netto: betragNetto }),
    onSuccess: (rechnung) => {
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
      navigate(`/rechnungen/${rechnung.id}`);
    },
  });

  if (currentUser && currentUser.role === "techniker") return <Navigate to="/feed" replace />;

  const nameFuer = (kundeId: string) => kunden?.find((k) => k.id === kundeId)?.name ?? "—";

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800">Geschäft</h1>

      <div className="flex gap-2 rounded-lg bg-white p-1 shadow-sm">
        <button
          onClick={() => {
            setTab("angebote");
            setShowForm(false);
          }}
          className={`btn-touch flex-1 rounded-md py-2 text-sm font-medium ${
            tab === "angebote" ? "bg-slate-900 text-white" : "text-slate-600"
          }`}
        >
          Angebote
        </button>
        <button
          onClick={() => {
            setTab("rechnungen");
            setShowForm(false);
          }}
          className={`btn-touch flex-1 rounded-md py-2 text-sm font-medium ${
            tab === "rechnungen" ? "bg-slate-900 text-white" : "text-slate-600"
          }`}
        >
          Rechnungen
        </button>
      </div>

      <button
        onClick={() => setShowForm((v) => !v)}
        className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700"
      >
        {showForm ? "Abbrechen" : tab === "angebote" ? "+ Neues Angebot" : "+ Neue Rechnung"}
      </button>

      {showForm && (
        <div className="space-y-3 rounded-lg bg-white p-4 shadow-sm">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500">Kunde</label>
            <select
              value={kundeId}
              onChange={(e) => setKundeId(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            >
              <option value="">Bitte wählen…</option>
              {kunden?.map((k) => (
                <option key={k.id} value={k.id}>
                  {k.name} ({k.kundennummer})
                </option>
              ))}
            </select>
          </div>
          {tab === "rechnungen" && (
            <div>
              <label className="mb-1 block text-xs font-medium text-slate-500">Betrag netto (EUR)</label>
              <input
                type="number"
                step="0.01"
                min="0"
                value={betragNetto}
                onChange={(e) => setBetragNetto(e.target.value)}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
            </div>
          )}
          <button
            disabled={
              !kundeId ||
              (tab === "rechnungen" && !betragNetto) ||
              createAngebotMutation.isPending ||
              createRechnungMutation.isPending
            }
            onClick={() => (tab === "angebote" ? createAngebotMutation.mutate() : createRechnungMutation.mutate())}
            className="btn-touch w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      {tab === "angebote" ? (
        <div className="space-y-2">
          {(angebote ?? []).length === 0 ? (
            <p className="text-center text-sm text-slate-400">Keine Angebote vorhanden.</p>
          ) : (
            angebote!.map((a) => (
              <button
                key={a.id}
                onClick={() => navigate(`/angebote/${a.id}`)}
                className="btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm"
              >
                <div>
                  <div className="text-xs text-slate-400">{a.angebotsnummer}</div>
                  <div className="text-sm font-medium text-slate-800">{nameFuer(a.kunde_id)}</div>
                  <div className="text-xs text-slate-500">{a.gesamt_brutto} EUR</div>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
                  {ANGEBOT_STATUS_LABEL[a.status]}
                </span>
              </button>
            ))
          )}
        </div>
      ) : (
        <div className="space-y-2">
          {(rechnungen ?? []).length === 0 ? (
            <p className="text-center text-sm text-slate-400">Keine Rechnungen vorhanden.</p>
          ) : (
            rechnungen!.map((r) => (
              <button
                key={r.id}
                onClick={() => navigate(`/rechnungen/${r.id}`)}
                className="btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm"
              >
                <div>
                  <div className="text-xs text-slate-400">{r.rechnungsnummer}</div>
                  <div className="text-sm font-medium text-slate-800">{nameFuer(r.kunde_id)}</div>
                  <div className="text-xs text-slate-500">{r.betrag_brutto} EUR</div>
                </div>
                <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600">
                  {RECHNUNG_STATUS_LABEL[r.status]}
                </span>
              </button>
            ))
          )}
        </div>
      )}
    </div>
  );
}
