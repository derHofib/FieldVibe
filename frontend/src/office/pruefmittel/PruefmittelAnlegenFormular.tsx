import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { pruefmittelApi } from "../../api/endpoints";
import { Select } from "../../components/apple/Select";
import { FELD_KLASSE, Feld } from "../../components/FormularFeld";
import type { Pruefmittel, UserAuswahl } from "../../types";

export function PruefmittelAnlegenFormular({
  nutzer,
  onAngelegt,
}: {
  nutzer: UserAuswahl[];
  onAngelegt: (p: Pruefmittel) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({ bezeichnung: "", seriennummer: "", zugewiesenAn: "", intervallMonate: "12" });

  const anlegen = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () =>
      pruefmittelApi.create({
        bezeichnung: form.bezeichnung,
        seriennummer: form.seriennummer || undefined,
        zugewiesen_an: form.zugewiesenAn || undefined,
        kalibrierintervall_monate: Number(form.intervallMonate),
      }),
    onSuccess: (p) => {
      void queryClient.invalidateQueries({ queryKey: ["pruefmittel"] });
      onAngelegt(p);
    },
  });

  return (
    <form
      className="space-y-3 p-4"
      onSubmit={(e) => {
        e.preventDefault();
        anlegen.mutate();
      }}
    >
      <Feld label="Bezeichnung" pflicht>
        {(p) => (
          <input
            {...p}
            value={form.bezeichnung}
            onChange={(e) => setForm({ ...form, bezeichnung: e.target.value })}
            className={FELD_KLASSE}
            placeholder="z.B. Installationstester Gossen Metrahit"
          />
        )}
      </Feld>
      <Feld label="Seriennummer">
        {(p) => (
          <input {...p} value={form.seriennummer} onChange={(e) => setForm({ ...form, seriennummer: e.target.value })} className={FELD_KLASSE} />
        )}
      </Feld>
      <Feld label="Zugewiesen an">
        {(p) => (
          <Select {...p} value={form.zugewiesenAn} onChange={(e) => setForm({ ...form, zugewiesenAn: e.target.value })}>
            <option value="">Niemand</option>
            {nutzer.map((u) => (
              <option key={u.id} value={u.id}>
                {u.name}
              </option>
            ))}
          </Select>
        )}
      </Feld>
      <Feld label="Kalibrierintervall (Monate)" pflicht>
        {(p) => (
          <input
            {...p}
            type="number"
            min={1}
            value={form.intervallMonate}
            onChange={(e) => setForm({ ...form, intervallMonate: e.target.value })}
            className={FELD_KLASSE}
          />
        )}
      </Feld>
      <button
        type="submit"
        disabled={!form.bezeichnung.trim() || Number(form.intervallMonate) < 1 || anlegen.isPending}
        className="btn-touch btn-ap-primary w-full px-4 disabled:opacity-50"
      >
        Anlegen
      </button>
    </form>
  );
}
