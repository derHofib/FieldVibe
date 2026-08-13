import { useQuery } from "@tanstack/react-query";
import { Clock, FileText } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import { EmptyState } from "../../components/EmptyState";
import { ZeiterfassungTagesliste } from "../../components/ZeiterfassungTagesliste";
import { usersApi, zeiterfassungApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import { montagDerWoche, toDateInput } from "../../utils/zeiterfassung";

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

  if (!darf) {
    return <EmptyState icon={Clock} text="Keine Berechtigung für diese Seite." />;
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">Team-Zeiten</h1>

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
        <div className="rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
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
            <ZeiterfassungTagesliste
              eintraege={wochenEintraege!}
              onEintragKlick={(vorgangId) => navigate(`/vorgaenge/${vorgangId}`)}
            />
          )}

          <div className="mt-2 flex items-center justify-end border-t border-slate-100 pt-2 dark:border-stone-800">
            <button
              onClick={exportieren}
              className="btn-touch flex items-center gap-1.5 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white"
            >
              <FileText size={15} strokeWidth={2} /> Als PDF exportieren
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
