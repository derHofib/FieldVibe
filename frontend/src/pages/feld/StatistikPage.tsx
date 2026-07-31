import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

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

export function StatistikPage() {
  const navigate = useNavigate();
  const { currentUser } = useAuth();
  const istTechniker = currentUser?.role === "techniker";
  const kannAuswaehlen = !istTechniker;

  const [technikerId, setTechnikerId] = useState<string>(istTechniker ? currentUser!.id : "");
  const [wocheMontag, setWocheMontag] = useState(() => montagDerWoche(new Date()));

  const { data: users } = useQuery({
    queryKey: ["users"],
    queryFn: usersApi.list,
    enabled: kannAuswaehlen,
  });
  const techniker = (users ?? []).filter((u) => u.role === "techniker");

  const effectiveTechnikerId = technikerId || undefined;

  const { data: statistik } = useQuery({
    queryKey: ["zeiterfassung-statistik", effectiveTechnikerId],
    queryFn: () => zeiterfassungApi.statistik(effectiveTechnikerId),
    enabled: istTechniker || !!technikerId,
  });

  const wocheEnde = new Date(wocheMontag);
  wocheEnde.setDate(wocheMontag.getDate() + 6);

  const { data: wochenEintraege } = useQuery({
    queryKey: ["zeiterfassung-woche", effectiveTechnikerId, toDateInput(wocheMontag)],
    queryFn: () =>
      zeiterfassungApi.listFuerZeitraum({
        techniker_id: effectiveTechnikerId,
        von: toDateInput(wocheMontag),
        bis: toDateInput(wocheEnde),
      }),
    enabled: istTechniker || !!technikerId,
  });

  async function exportieren() {
    const blob = await zeiterfassungApi.wochenzettelPdf(toDateInput(wocheMontag), effectiveTechnikerId);
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
    setTimeout(() => URL.revokeObjectURL(url), 30_000);
  }

  const wochensumme = (wochenEintraege ?? []).reduce(
    (summe, e) => summe + formatDauer(e.start_at, e.ende_at),
    0
  );

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800">Statistik</h1>

      {kannAuswaehlen && (
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Techniker</label>
          <select
            value={technikerId}
            onChange={(e) => setTechnikerId(e.target.value)}
            className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2"
          >
            <option value="">Bitte wählen…</option>
            {techniker.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
      )}

      {statistik && (
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-lg bg-white p-3 text-center shadow-sm">
            <div className="text-xl font-bold text-slate-800">
              {formatStundenAlsHHMM(Number(statistik.wochenstunden))}
            </div>
            <div className="text-xs text-slate-500">Std. diese Woche</div>
          </div>
          <div className="rounded-lg bg-white p-3 text-center shadow-sm">
            <div className="text-xl font-bold text-slate-800">
              {formatStundenAlsHHMM(Number(statistik.monatsstunden))}
            </div>
            <div className="text-xs text-slate-500">Std. dieser Monat</div>
          </div>
          <div className="rounded-lg bg-white p-3 text-center shadow-sm">
            <div className="text-xl font-bold text-slate-800">
              {formatStundenAlsHHMM(Number(statistik.jahresstunden))}
            </div>
            <div className="text-xs text-slate-500">Std. dieses Jahr</div>
          </div>
        </div>
      )}

      {(istTechniker || technikerId) && (
        <div className="rounded-lg bg-white p-3 shadow-sm">
          <div className="mb-2 flex items-center justify-between">
            <button
              onClick={() => {
                const vorherigeWoche = new Date(wocheMontag);
                vorherigeWoche.setDate(wocheMontag.getDate() - 7);
                setWocheMontag(vorherigeWoche);
              }}
              className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600"
            >
              ← Woche
            </button>
            <span className="text-sm font-medium text-slate-700">
              {wocheMontag.toLocaleDateString("de-DE")} – {wocheEnde.toLocaleDateString("de-DE")}
            </span>
            <button
              onClick={() => {
                const naechsteWoche = new Date(wocheMontag);
                naechsteWoche.setDate(wocheMontag.getDate() + 7);
                setWocheMontag(naechsteWoche);
              }}
              className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm text-slate-600"
            >
              Woche →
            </button>
          </div>

          {(wochenEintraege ?? []).length === 0 ? (
            <p className="text-sm text-slate-400">Keine Zeiterfassungen in dieser Woche.</p>
          ) : (
            <div className="space-y-1">
              {wochenEintraege!.map((e) => (
                <button
                  key={e.id}
                  onClick={() => navigate(`/vorgaenge/${e.vorgang_id}`)}
                  className="btn-touch flex w-full items-center justify-between rounded-md bg-slate-50 px-2 py-1.5 text-left text-sm"
                >
                  <span className="text-slate-600">
                    {new Date(e.start_at).toLocaleDateString("de-DE", { weekday: "short", day: "2-digit", month: "2-digit" })}
                    {e.taetigkeit && ` · ${e.taetigkeit}`}
                  </span>
                  <span className="shrink-0 font-medium text-slate-700">
                    {formatStundenAlsHHMM(formatDauer(e.start_at, e.ende_at))} Std.
                  </span>
                </button>
              ))}
            </div>
          )}

          <div className="mt-2 flex items-center justify-between border-t border-slate-100 pt-2">
            <span className="text-sm font-semibold text-slate-700">
              Wochensumme: {formatStundenAlsHHMM(wochensumme)} Std.
            </span>
            <button
              onClick={exportieren}
              className="btn-touch rounded-md bg-slate-900 px-3 py-1.5 text-sm font-medium text-white"
            >
              📄 Als PDF exportieren
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
