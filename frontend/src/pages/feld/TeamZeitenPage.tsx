import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, Clock, FileText } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import { EmptyState } from "../../components/EmptyState";
import { usersApi, zeiterfassungApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { formatStundenAlsHHMM } from "../../utils/duration";

function montagDerWoche(datum: Date): Date {
  const tag = datum.getDay();
  const diffZuMontag = tag === 0 ? -6 : 1 - tag;
  const montag = new Date(datum);
  montag.setDate(datum.getDate() + diffZuMontag);
  montag.setHours(0, 0, 0, 0);
  return montag;
}

function toDateInput(d: Date): string {
  return d.toISOString().slice(0, 10);
}

function formatDauer(startAt: string, endeAt: string | null): number {
  if (!endeAt) return 0;
  return (new Date(endeAt).getTime() - new Date(startAt).getTime()) / 1000 / 3600;
}

const KATEGORIE_LABEL: Record<string, string> = {
  verwaltung: "Verwaltung",
  fahrzeit: "Fahrzeit",
  schulung: "Schulung",
  urlaub: "Urlaub",
  krankheit: "Krankheit",
  sonstiges: "Sonstiges",
};

function FreigabeListe() {
  const queryClient = useQueryClient();
  const { data: offene } = useQuery({
    queryKey: ["zeiterfassung-unfreigegeben"],
    queryFn: zeiterfassungApi.unfreigegeben,
  });
  const { data: users } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
  const namenById = new Map((users ?? []).map((u) => [u.id, u.name]));

  async function freigeben(id: string) {
    await zeiterfassungApi.freigeben(id);
    await queryClient.invalidateQueries({ queryKey: ["zeiterfassung-unfreigegeben"] });
  }

  if (!offene || offene.length === 0) return null;

  return (
    <section className="rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
      <h2 className="mb-2 text-sm font-semibold text-slate-700 dark:text-stone-300">
        Zur Freigabe ({offene.length})
      </h2>
      <div className="space-y-1.5">
        {offene.map((e) => (
          <div
            key={e.id}
            className="flex items-center justify-between gap-2 rounded-md bg-slate-50 px-2 py-1.5 text-sm dark:bg-stone-800/60"
          >
            <span className="min-w-0 truncate text-slate-600 dark:text-stone-300">
              <span className="font-medium">{namenById.get(e.techniker_id) ?? "?"}</span>
              {" · "}
              {e.vorgang_id ? "Auftrag" : KATEGORIE_LABEL[e.kategorie] ?? e.kategorie}
              {" · "}
              {new Date(e.start_at).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}
              {" · "}
              {formatStundenAlsHHMM(formatDauer(e.start_at, e.ende_at))} Std.
            </span>
            <button
              onClick={() => freigeben(e.id)}
              className="btn-touch flex shrink-0 items-center gap-1 rounded-md bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-400"
            >
              <CheckCircle2 size={13} strokeWidth={2} /> Freigeben
            </button>
          </div>
        ))}
      </div>
    </section>
  );
}

export function TeamZeitenPage() {
  const navigate = useNavigate();
  const { hatRecht } = useAuth();
  const darf = hatRecht("mitarbeiterverwaltung", "bearbeiten");

  const [technikerId, setTechnikerId] = useState<string>("");
  const [wocheMontag, setWocheMontag] = useState(() => montagDerWoche(new Date()));

  const { data: users } = useQuery({ queryKey: ["users"], queryFn: usersApi.list, enabled: darf });
  const techniker = (users ?? []).filter((u) => u.nur_zugewiesene_kunden);

  const wocheEnde = new Date(wocheMontag);
  wocheEnde.setDate(wocheMontag.getDate() + 6);

  const { data: wochenEintraege } = useQuery({
    queryKey: ["zeiterfassung-woche-team", technikerId, toDateInput(wocheMontag)],
    queryFn: () =>
      zeiterfassungApi.listFuerZeitraum({
        techniker_id: technikerId,
        von: toDateInput(wocheMontag),
        bis: toDateInput(wocheEnde),
      }),
    enabled: darf && !!technikerId,
  });

  async function exportieren() {
    const blob = await zeiterfassungApi.wochenzettelPdf(toDateInput(wocheMontag), technikerId);
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  }

  const wochensumme = (wochenEintraege ?? []).reduce(
    (summe, e) => summe + formatDauer(e.start_at, e.ende_at),
    0
  );

  if (!darf) {
    return <EmptyState icon={Clock} text="Keine Berechtigung für diese Seite." />;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">Team-Zeiten</h1>

      <FreigabeListe />

      <div>
        <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-stone-300">
          Techniker
        </label>
        <select
          value={technikerId}
          onChange={(e) => setTechnikerId(e.target.value)}
          className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2 dark:border-stone-700 dark:bg-stone-900 dark:text-stone-100"
        >
          <option value="">Bitte wählen…</option>
          {techniker.map((t) => (
            <option key={t.id} value={t.id}>
              {t.name}
            </option>
          ))}
        </select>
      </div>

      {technikerId && (
        <div className="rounded-lg bg-white p-3 shadow-sm dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <div className="mb-2 flex items-center justify-between">
            <button
              onClick={() => {
                const vorherigeWoche = new Date(wocheMontag);
                vorherigeWoche.setDate(wocheMontag.getDate() - 7);
                setWocheMontag(vorherigeWoche);
              }}
              className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            >
              ← Woche
            </button>
            <span className="text-sm font-medium text-slate-700 dark:text-stone-300">
              {wocheMontag.toLocaleDateString("de-DE")} – {wocheEnde.toLocaleDateString("de-DE")}
            </span>
            <button
              onClick={() => {
                const naechsteWoche = new Date(wocheMontag);
                naechsteWoche.setDate(wocheMontag.getDate() + 7);
                setWocheMontag(naechsteWoche);
              }}
              className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600 dark:bg-stone-800 dark:text-stone-300"
            >
              Woche →
            </button>
          </div>

          {(wochenEintraege ?? []).length === 0 ? (
            <EmptyState icon={Clock} text="Keine Zeiterfassungen in dieser Woche." />
          ) : (
            <div className="space-y-1">
              {wochenEintraege!.map((e) => (
                <button
                  key={e.id}
                  onClick={() => e.vorgang_id && navigate(`/vorgaenge/${e.vorgang_id}`)}
                  disabled={!e.vorgang_id}
                  className="card-interactive btn-touch flex w-full items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-left text-sm disabled:cursor-default dark:bg-stone-800/60"
                >
                  <span className="text-slate-600 dark:text-stone-300">
                    {new Date(e.start_at).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" })}
                    {" · "}
                    <span className="font-medium">
                      {e.vorgang_id ? "Auftrag" : KATEGORIE_LABEL[e.kategorie] ?? e.kategorie}
                    </span>
                    {e.taetigkeit && ` · ${e.taetigkeit}`}
                  </span>
                  <span className="shrink-0 font-medium text-slate-700 dark:text-stone-300">
                    {formatStundenAlsHHMM(formatDauer(e.start_at, e.ende_at))} Std.
                  </span>
                </button>
              ))}
            </div>
          )}

          <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2 dark:border-stone-800">
            <span className="text-sm font-semibold text-slate-700 dark:text-stone-300">
              Wochensumme: {formatStundenAlsHHMM(wochensumme)} Std.
            </span>
            <button
              onClick={exportieren}
              className="btn-touch flex items-center gap-1.5 rounded-md btn-clay bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white"
            >
              <FileText size={15} strokeWidth={2} /> Als PDF exportieren
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
