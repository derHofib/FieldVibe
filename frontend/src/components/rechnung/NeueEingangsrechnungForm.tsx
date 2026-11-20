import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { ApiError } from "../../api/client";
import { eingangsrechnungenApi, lieferantenApi } from "../../api/endpoints";
import type { Eingangsrechnung } from "../../types";
import { heuteIso } from "../../utils/format";
import { Select } from "../apple/Select";
import { EINGANG_KATEGORIE_LABEL as KATEGORIE_LABEL } from "./rechnungenFilter";


/** Anlegeformular für den Inhalt eines AnlegenPanel (Feld-App und Office). Die Seite entscheidet über `onAngelegt`, wohin es danach geht. */
export function NeueEingangsrechnungForm({
  onAngelegt,
}: {
  onAngelegt: (eingangsrechnung: Eingangsrechnung) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    lieferantId: "",
    lieferantName: "",
    rechnungsnummerLieferant: "",
    rechnungsdatum: heuteIso(),
    faelligAm: "",
    betragNetto: "",
    kategorie: "",
    skontoProzent: "",
    skontoTage: "",
  });
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: lieferanten } = useQuery({
    queryKey: ["lieferanten"],
    queryFn: () => lieferantenApi.list(),
  });

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
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
      setFehler(null);
      queryClient.invalidateQueries({ queryKey: ["eingangsrechnungen"] });
      onAngelegt(eingangsrechnung);
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Anlegen fehlgeschlagen"),
  });

  return (
    <div className="space-y-2 p-4">
      <Select
        value={form.lieferantId}
        onChange={(e) => setForm({ ...form, lieferantId: e.target.value })}
      >
        <option value="">Lieferant manuell eintragen…</option>
        {(lieferanten ?? []).map((l) => (
          <option key={l.id} value={l.id}>
            {l.name}
          </option>
        ))}
      </Select>
      {!form.lieferantId && (
        <input
          value={form.lieferantName}
          onChange={(e) => setForm({ ...form, lieferantName: e.target.value })}
          placeholder="Name des Ausstellers"
          className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
        />
      )}
      <input
        value={form.rechnungsnummerLieferant}
        onChange={(e) => setForm({ ...form, rechnungsnummerLieferant: e.target.value })}
        placeholder="Rechnungsnummer (vom Aussteller)"
        className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
      />
      <div className="grid grid-cols-2 gap-2">
        <label className="text-meta text-label2">
          Rechnungsdatum
          <input
            type="date"
            value={form.rechnungsdatum}
            onChange={(e) => setForm({ ...form, rechnungsdatum: e.target.value })}
            className="mt-1 w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
          />
        </label>
        <label className="text-sekundaer text-label2">
          Fällig am
          <input
            type="date"
            value={form.faelligAm}
            onChange={(e) => setForm({ ...form, faelligAm: e.target.value })}
            className="mt-1 w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
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
          className="border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
        />
        <Select
          className="w-auto"
          value={form.kategorie}
          onChange={(e) => setForm({ ...form, kategorie: e.target.value })}
          groesse="kompakt"
        >
          <option value="">Kategorie…</option>
          {Object.entries(KATEGORIE_LABEL).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </Select>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <input
          type="number"
          step="0.01"
          value={form.skontoProzent}
          onChange={(e) => setForm({ ...form, skontoProzent: e.target.value })}
          placeholder="Skonto %"
          className="border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
        />
        <input
          type="number"
          step="1"
          value={form.skontoTage}
          onChange={(e) => setForm({ ...form, skontoTage: e.target.value })}
          placeholder="Skonto-Frist (Tage)"
          className="border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
        />
      </div>
      {fehler && <p className="text-sekundaer text-st-fehlt ">{fehler}</p>}
      <button
        disabled={
          !form.rechnungsnummerLieferant ||
          !form.rechnungsdatum ||
          (!form.lieferantId && !form.lieferantName) ||
          createMutation.isPending
        }
        onClick={() => createMutation.mutate()}
        className="btn-touch w-full rounded-md btn-ap-primary px-3 py-1.5 text-sekundaer font-medium disabled:opacity-50"
      >
        Anlegen
      </button>
    </div>
  );
}
