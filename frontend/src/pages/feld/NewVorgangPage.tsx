import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";

import { kundenApi, vorgaengeApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import type { Leistungstyp, VorgangAbrechnungsart } from "../../types";

const LEISTUNGSTYPEN: { value: Leistungstyp; label: string }[] = [
  { value: "stoerung", label: "Störung" },
  { value: "installation", label: "Installation" },
  { value: "wartung", label: "Wartung" },
  { value: "pruefung", label: "Prüfung" },
  { value: "beratung", label: "Beratung" },
  { value: "planung", label: "Planung" },
];

const ABRECHNUNGSARTEN: { value: VorgangAbrechnungsart; label: string }[] = [
  { value: "aufwand", label: "Nach Aufwand" },
  { value: "pauschale", label: "Pauschale" },
  { value: "festpreis", label: "Festpreis" },
  { value: "wartungsvertrag", label: "Wartungsvertrag" },
  { value: "gewaehrleistung", label: "Gewährleistung" },
];

export function NewVorgangPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [kundeId, setKundeId] = useState("");
  const [titel, setTitel] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [leistungstyp, setLeistungstyp] = useState<Leistungstyp>("stoerung");
  const [abrechnungsart, setAbrechnungsart] = useState<VorgangAbrechnungsart>("aufwand");

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });

  const createMutation = useMutation({
    mutationFn: () =>
      vorgaengeApi.create({ kunde_id: kundeId, titel, beschreibung, abrechnungsart, leistungstyp }),
    onSuccess: (vorgang) => {
      queryClient.invalidateQueries({ queryKey: ["feed"] });
      navigate(`/vorgaenge/${vorgang.id}`);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Fehler"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!kundeId) {
      setError("Bitte einen Kunden auswählen");
      return;
    }
    createMutation.mutate();
  }

  return (
    <div className="space-y-4">
      <h1 className="text-lg font-bold text-slate-800">Neuer Vorgang</h1>
      <p className="text-sm text-slate-500">
        Foto, Zeiterfassung und QR-Scan folgen mit der Feld-Tauglichkeit (Phase 4).
      </p>

      <form onSubmit={handleSubmit} className="space-y-3 rounded-lg bg-white p-4 shadow-sm">
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Kunde</label>
          <select
            value={kundeId}
            onChange={(e) => setKundeId(e.target.value)}
            className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2"
          >
            <option value="">Bitte wählen…</option>
            {kunden?.map((k) => (
              <option key={k.id} value={k.id}>
                {k.name} ({k.kundennummer})
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Titel</label>
          <input
            required
            value={titel}
            onChange={(e) => setTitel(e.target.value)}
            className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2"
          />
        </div>

        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">Beschreibung</label>
          <textarea
            value={beschreibung}
            onChange={(e) => setBeschreibung(e.target.value)}
            rows={3}
            className="w-full resize-none rounded-md border border-slate-300 p-2"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Leistungstyp</label>
            <select
              value={leistungstyp}
              onChange={(e) => setLeistungstyp(e.target.value as Leistungstyp)}
              className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2"
            >
              {LEISTUNGSTYPEN.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Abrechnungsart</label>
            <select
              value={abrechnungsart}
              onChange={(e) => setAbrechnungsart(e.target.value as VorgangAbrechnungsart)}
              className="btn-touch w-full rounded-md border border-slate-300 px-3 py-2"
            >
              {ABRECHNUNGSARTEN.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                </option>
              ))}
            </select>
          </div>
        </div>

        {error && <p className="text-sm text-red-700">{error}</p>}

        <button
          type="submit"
          disabled={createMutation.isPending}
          className="btn-touch w-full rounded-md bg-slate-900 py-2 font-medium text-white disabled:opacity-50"
        >
          Vorgang anlegen
        </button>
      </form>
    </div>
  );
}
