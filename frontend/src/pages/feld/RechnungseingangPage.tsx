import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { eingangsrechnungenApi, lieferantenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { istModulAktiv } from "../../utils/module";
import type { EingangsrechnungKategorie, EingangsrechnungStatus } from "../../types";

const STATUS_LABEL: Record<EingangsrechnungStatus, string> = {
  entwurf: "Entwurf",
  offen: "Offen",
  bezahlt: "Bezahlt",
  storniert: "Storniert",
};

const KATEGORIE_LABEL: Record<EingangsrechnungKategorie, string> = {
  wareneinkauf: "Wareneinkauf",
  betriebskosten: "Betriebskosten",
  miete: "Miete",
  personal: "Personal",
  fahrzeug: "Fahrzeug",
  versicherung: "Versicherung",
  sonstiges: "Sonstiges",
};

export function RechnungseingangPage() {
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const abrechnungAktiv = istModulAktiv(currentUser, "abrechnung");
  const kannSehen = hatRecht("abrechnung", "sehen");
  const kannErstellen = hatRecht("abrechnung", "erstellen");

  const [showForm, setShowForm] = useState(false);
  const [statusFilter, setStatusFilter] = useState("");
  const [form, setForm] = useState({
    lieferantId: "",
    lieferantName: "",
    rechnungsnummerLieferant: "",
    rechnungsdatum: new Date().toISOString().slice(0, 10),
    faelligAm: "",
    betragNetto: "",
    kategorie: "",
    skontoProzent: "",
    skontoTage: "",
  });
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: eingangsrechnungen } = useQuery({
    queryKey: ["eingangsrechnungen", statusFilter],
    queryFn: () => eingangsrechnungenApi.list(statusFilter ? { status: statusFilter } : {}),
    enabled: abrechnungAktiv && kannSehen,
  });
  const { data: lieferanten } = useQuery({
    queryKey: ["lieferanten"],
    queryFn: () => lieferantenApi.list(),
    enabled: abrechnungAktiv && kannSehen,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      eingangsrechnungenApi.create({
        lieferant_id: form.lieferantId || null,
        lieferant_name: form.lieferantId ? undefined : form.lieferantName,
        rechnungsnummer_lieferant: form.rechnungsnummerLieferant,
        rechnungsdatum: form.rechnungsdatum,
        faellig_am: form.faelligAm || undefined,
        betrag_netto: form.betragNetto || "0",
        kategorie: form.kategorie || undefined,
        skonto_prozent: form.skontoProzent || undefined,
        skonto_tage: form.skontoTage ? Number(form.skontoTage) : undefined,
      }),
    onSuccess: (eingangsrechnung) => {
      setShowForm(false);
      setForm({
        lieferantId: "",
        lieferantName: "",
        rechnungsnummerLieferant: "",
        rechnungsdatum: new Date().toISOString().slice(0, 10),
        skontoProzent: "",
        skontoTage: "",
        faelligAm: "",
        betragNetto: "",
        kategorie: "",
      });
      setFehler(null);
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
      navigate(`/rechnungseingang/${eingangsrechnung.id}`);
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Anlegen fehlgeschlagen"),
  });

  if (!abrechnungAktiv || !kannSehen) return <Navigate to="/geschaeft" replace />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">Rechnungseingang</h1>
        {kannErstellen && (
          <button
            onClick={() => setShowForm((v) => !v)}
            className="btn-touch rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white"
          >
            {showForm ? "Abbrechen" : "+ Neu"}
          </button>
        )}
      </div>

      {showForm && (
        <div className="space-y-2 rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
          <select
            value={form.lieferantId}
            onChange={(e) => setForm({ ...form, lieferantId: e.target.value })}
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          >
            <option value="">Lieferant manuell eintragen…</option>
            {(lieferanten ?? []).map((l) => (
              <option key={l.id} value={l.id}>
                {l.name}
              </option>
            ))}
          </select>
          {!form.lieferantId && (
            <input
              value={form.lieferantName}
              onChange={(e) => setForm({ ...form, lieferantName: e.target.value })}
              placeholder="Name des Ausstellers"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          )}
          <input
            value={form.rechnungsnummerLieferant}
            onChange={(e) => setForm({ ...form, rechnungsnummerLieferant: e.target.value })}
            placeholder="Rechnungsnummer (vom Aussteller)"
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
          <div className="grid grid-cols-2 gap-2">
            <label className="text-xs text-slate-500 dark:text-slate-400">
              Rechnungsdatum
              <input
                type="date"
                value={form.rechnungsdatum}
                onChange={(e) => setForm({ ...form, rechnungsdatum: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </label>
            <label className="text-xs text-slate-500 dark:text-slate-400">
              Fällig am
              <input
                type="date"
                value={form.faelligAm}
                onChange={(e) => setForm({ ...form, faelligAm: e.target.value })}
                className="mt-1 w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
              />
            </label>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="number"
              step="0.01"
              value={form.betragNetto}
              onChange={(e) => setForm({ ...form, betragNetto: e.target.value })}
              placeholder="Betrag netto"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <select
              value={form.kategorie}
              onChange={(e) => setForm({ ...form, kategorie: e.target.value })}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              <option value="">Kategorie…</option>
              {Object.entries(KATEGORIE_LABEL).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <input
              type="number"
              step="0.01"
              value={form.skontoProzent}
              onChange={(e) => setForm({ ...form, skontoProzent: e.target.value })}
              placeholder="Skonto %"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <input
              type="number"
              step="1"
              value={form.skontoTage}
              onChange={(e) => setForm({ ...form, skontoTage: e.target.value })}
              placeholder="Skonto-Frist (Tage)"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          {fehler && <p className="text-xs text-red-600 dark:text-red-400">{fehler}</p>}
          <button
            disabled={
              !form.rechnungsnummerLieferant ||
              !form.rechnungsdatum ||
              (!form.lieferantId && !form.lieferantName) ||
              createMutation.isPending
            }
            onClick={() => createMutation.mutate()}
            className="btn-touch w-full rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      )}

      <div className="flex gap-2 text-xs">
        {(["", "entwurf", "offen", "bezahlt", "storniert"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={`btn-touch rounded-full px-3 py-1 font-medium ${
              statusFilter === s
                ? "bg-cyan-600 text-white"
                : "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300"
            }`}
          >
            {s === "" ? "Alle" : STATUS_LABEL[s]}
          </button>
        ))}
      </div>

      <div className="space-y-2">
        {(eingangsrechnungen ?? []).length === 0 && (
          <p className="text-sm text-slate-400 dark:text-slate-500">Keine Eingangsrechnungen.</p>
        )}
        {(eingangsrechnungen ?? []).map((e) => (
          <button
            key={e.id}
            onClick={() => navigate(`/rechnungseingang/${e.id}`)}
            className="btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
          >
            <div>
              <div className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                {e.lieferant_name}
              </div>
              <div className="text-xs text-slate-400 dark:text-slate-500">
                {e.rechnungsnummer_lieferant} · {new Date(e.rechnungsdatum).toLocaleDateString("de-DE")}
                {e.kategorie && ` · ${KATEGORIE_LABEL[e.kategorie]}`}
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm font-medium text-slate-700 dark:text-slate-300">
                {e.betrag_brutto} EUR
              </div>
              <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {STATUS_LABEL[e.status]}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
