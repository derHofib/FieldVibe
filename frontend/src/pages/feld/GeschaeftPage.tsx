import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { angeboteApi, kundenApi, materialApi, rechnungenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import type { AngebotStatus, Material, RechnungStatus } from "../../types";

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

function istUnterbestand(m: Material): boolean {
  return Number(m.bestand) <= Number(m.mindestbestand);
}

function MaterialZeile({ material }: { material: Material }) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [bestand, setBestand] = useState(material.bestand);
  const [mindestbestand, setMindestbestand] = useState(material.mindestbestand);

  const updateMutation = useMutation({
    mutationFn: () => materialApi.update(material.id, { bestand, mindestbestand }),
    onSuccess: () => {
      setEditing(false);
      queryClient.invalidateQueries({ queryKey: ["material"] });
      queryClient.invalidateQueries({ queryKey: ["stories"] });
    },
  });

  return (
    <div className="rounded-lg bg-white p-3 shadow-sm">
      <div className="flex items-center justify-between">
        <div>
          <div className="text-sm font-medium text-slate-800">{material.bezeichnung}</div>
          <div className={`text-xs ${istUnterbestand(material) ? "font-semibold text-red-600" : "text-slate-500"}`}>
            Bestand: {material.bestand} {material.einheit} (Mindestbestand {material.mindestbestand})
          </div>
          {material.einzelpreis && (
            <div className="text-xs text-slate-400">{material.einzelpreis} EUR/Einheit</div>
          )}
        </div>
        <button onClick={() => setEditing((v) => !v)} className="btn-touch text-xs font-medium text-blue-700">
          {editing ? "Abbrechen" : "Bestand ändern"}
        </button>
      </div>
      {editing && (
        <div className="mt-2 flex items-end gap-2 border-t border-slate-100 pt-2">
          <div className="flex-1">
            <label className="mb-1 block text-xs text-slate-500">Bestand</label>
            <input
              type="number"
              step="0.01"
              value={bestand}
              onChange={(e) => setBestand(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </div>
          <div className="flex-1">
            <label className="mb-1 block text-xs text-slate-500">Mindestbestand</label>
            <input
              type="number"
              step="0.01"
              value={mindestbestand}
              onChange={(e) => setMindestbestand(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1 text-sm"
            />
          </div>
          <button
            onClick={() => updateMutation.mutate()}
            disabled={updateMutation.isPending}
            className="btn-touch rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            Speichern
          </button>
        </div>
      )}
    </div>
  );
}

export function GeschaeftPage() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"angebote" | "rechnungen" | "material">("angebote");
  const [showForm, setShowForm] = useState(false);
  const [kundeId, setKundeId] = useState("");
  const [betragNetto, setBetragNetto] = useState("");
  const [materialForm, setMaterialForm] = useState({
    bezeichnung: "",
    einheit: "Stk",
    bestand: "0",
    mindestbestand: "0",
    einzelpreis: "",
  });

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });
  const { data: angebote } = useQuery({ queryKey: ["angebote"], queryFn: () => angeboteApi.list() });
  const { data: rechnungen } = useQuery({ queryKey: ["rechnungen"], queryFn: () => rechnungenApi.list() });
  const { data: material } = useQuery({ queryKey: ["material"], queryFn: () => materialApi.list() });

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

  const createMaterialMutation = useMutation({
    mutationFn: () =>
      materialApi.create({
        bezeichnung: materialForm.bezeichnung,
        einheit: materialForm.einheit,
        bestand: materialForm.bestand,
        mindestbestand: materialForm.mindestbestand,
        einzelpreis: materialForm.einzelpreis || undefined,
      }),
    onSuccess: () => {
      setShowForm(false);
      setMaterialForm({ bezeichnung: "", einheit: "Stk", bestand: "0", mindestbestand: "0", einzelpreis: "" });
      queryClient.invalidateQueries({ queryKey: ["material"] });
      queryClient.invalidateQueries({ queryKey: ["stories"] });
    },
  });

  if (currentUser && currentUser.role === "techniker") return <Navigate to="/feed" replace />;

  const nameFuer = (kundeId: string) => kunden?.find((k) => k.id === kundeId)?.name ?? "—";

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800">Geschäft</h1>

      <div className="flex gap-2 rounded-lg bg-white p-1 shadow-sm">
        {(["angebote", "rechnungen", "material"] as const).map((t) => (
          <button
            key={t}
            onClick={() => {
              setTab(t);
              setShowForm(false);
            }}
            className={`btn-touch flex-1 rounded-md py-2 text-sm font-medium capitalize ${
              tab === t ? "bg-slate-900 text-white" : "text-slate-600"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      <button
        onClick={() => setShowForm((v) => !v)}
        className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700"
      >
        {showForm
          ? "Abbrechen"
          : tab === "angebote"
            ? "+ Neues Angebot"
            : tab === "rechnungen"
              ? "+ Neue Rechnung"
              : "+ Neues Material"}
      </button>

      {showForm && tab !== "material" && (
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

      {showForm && tab === "material" && (
        <div className="space-y-3 rounded-lg bg-white p-4 shadow-sm">
          <input
            value={materialForm.bezeichnung}
            onChange={(e) => setMaterialForm({ ...materialForm, bezeichnung: e.target.value })}
            placeholder="Bezeichnung"
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          />
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-xs text-slate-500">Einheit</label>
              <input
                value={materialForm.einheit}
                onChange={(e) => setMaterialForm({ ...materialForm, einheit: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500">Einzelpreis (EUR, optional)</label>
              <input
                type="number"
                step="0.01"
                value={materialForm.einzelpreis}
                onChange={(e) => setMaterialForm({ ...materialForm, einzelpreis: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500">Bestand</label>
              <input
                type="number"
                step="0.01"
                value={materialForm.bestand}
                onChange={(e) => setMaterialForm({ ...materialForm, bestand: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs text-slate-500">Mindestbestand</label>
              <input
                type="number"
                step="0.01"
                value={materialForm.mindestbestand}
                onChange={(e) => setMaterialForm({ ...materialForm, mindestbestand: e.target.value })}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
            </div>
          </div>
          <button
            disabled={!materialForm.bezeichnung || createMaterialMutation.isPending}
            onClick={() => createMaterialMutation.mutate()}
            className="btn-touch w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      {tab === "angebote" && (
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
      )}

      {tab === "rechnungen" && (
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

      {tab === "material" && (
        <div className="space-y-2">
          {(material ?? []).length === 0 ? (
            <p className="text-center text-sm text-slate-400">Kein Material erfasst.</p>
          ) : (
            material!.map((m) => <MaterialZeile key={m.id} material={m} />)
          )}
        </div>
      )}
    </div>
  );
}
