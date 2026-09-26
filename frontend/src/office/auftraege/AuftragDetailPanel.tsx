import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { auftraegeApi, kundenApi, projekteApi, vorgaengeApi } from "../../api/endpoints";
import { SearchableSelect } from "../../components/SearchableSelect";
import { EmptyState } from "../../components/EmptyState";
import { ZeitSummenBlock } from "../../components/ZeitSummenBlock";
import { SeitenPanel } from "../../components/apple/SeitenPanel";
import { STATUS_BADGE, STATUS_LABEL } from "../../config/vorgangDarstellung";
import type { Auftrag, AuftragStatus } from "../../types";
import { AUFTRAG_STATUS_LABEL } from "./AuftraegeTabelle";
import { Layers } from "lucide-react";

const AUFTRAG_STATUS_OPTIONEN: AuftragStatus[] = ["offen", "in_arbeit", "abgeschlossen", "storniert"];

/** Detailinhalt fuer das rechte SeitenPanel -- Stammdaten + Status
 * editierbar, Projekt/Kunde-Zuordnung per SearchableSelect aenderbar
 * (rein referenziell, siehe app/models/auftrag.py), darunter die
 * verknuepften Vorgaenge (auftrag_id-Filter). */
export function AuftragDetailPanel({ auftrag, onClose }: { auftrag: Auftrag; onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [titel, setTitel] = useState(auftrag.titel);

  const { data: aktuell } = useQuery({
    queryKey: ["auftraege", auftrag.id],
    queryFn: () => auftraegeApi.get(auftrag.id),
    initialData: auftrag,
  });

  const { data: projekte } = useQuery({ queryKey: ["projekte"], queryFn: () => projekteApi.list() });
  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });

  const { data: vorgaenge } = useQuery({
    queryKey: ["vorgaenge", "auftrag", auftrag.id],
    queryFn: () => vorgaengeApi.list({ auftrag_id: auftrag.id }),
  });

  const aktualisieren = useMutation({
    mutationFn: (body: Parameters<typeof auftraegeApi.update>[1]) => auftraegeApi.update(auftrag.id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auftraege"] });
      queryClient.invalidateQueries({ queryKey: ["auftraege", auftrag.id] });
    },
  });

  const loeschen = useMutation({
    mutationFn: () => auftraegeApi.remove(auftrag.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auftraege"] });
      onClose();
    },
  });

  const projektName = projekte?.find((p) => p.id === aktuell?.projekt_id)?.name;
  const kundeName = aktuell?.kunde_name ?? kunden?.find((k) => k.id === aktuell?.kunde_id)?.name;

  return (
    <SeitenPanel offen titel={aktuell?.titel ?? auftrag.titel} onClose={onClose}>
      <div className="space-y-5 p-4">
        <div>
          <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">Titel</label>
          <input
            value={titel}
            onChange={(e) => setTitel(e.target.value)}
            onBlur={() => titel.trim() && titel !== aktuell?.titel && aktualisieren.mutate({ titel: titel.trim() })}
            className="field-ap"
          />
        </div>

        <div>
          <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">Status</label>
          <select
            value={aktuell?.status ?? auftrag.status}
            onChange={(e) => aktualisieren.mutate({ status: e.target.value as AuftragStatus })}
            className="field-ap"
          >
            {AUFTRAG_STATUS_OPTIONEN.map((s) => (
              <option key={s} value={s}>
                {AUFTRAG_STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </div>

        <div>
          <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">Projekt</label>
          <SearchableSelect
            value={aktuell?.projekt_id ?? ""}
            onChange={(v) => aktualisieren.mutate({ projekt_id: v || null })}
            placeholder="Kein Projekt"
            options={(projekte ?? []).map((p) => ({ value: p.id, label: p.name }))}
          />
          {projektName && <p className="mt-1 text-xs text-label2">{projektName}</p>}
        </div>

        <div>
          <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">Kunde</label>
          <SearchableSelect
            value={aktuell?.kunde_id ?? ""}
            onChange={(v) => aktualisieren.mutate({ kunde_id: v || null })}
            placeholder="Kein Kunde"
            options={(kunden ?? []).map((k) => ({ value: k.id, label: k.name }))}
          />
          {kundeName && <p className="mt-1 text-xs text-label2">{kundeName}</p>}
        </div>

        <div>
          <div className="mb-1.5 flex items-center justify-between">
            <label className="block text-[11px] font-bold tracking-wide text-label3 uppercase">
              Vorgänge ({vorgaenge?.length ?? 0})
            </label>
            <button
              onClick={() => navigate(`/neu?auftrag_id=${auftrag.id}`)}
              className="text-xs font-medium text-tint hover:underline"
            >
              + Neuer Vorgang
            </button>
          </div>
          {!vorgaenge || vorgaenge.length === 0 ? (
            <EmptyState icon={Layers} text="Noch kein Vorgang zugeordnet." />
          ) : (
            <div className="space-y-1.5">
              {vorgaenge.map((v) => (
                <button
                  key={v.id}
                  onClick={() => navigate(`/vorgaenge/${v.id}`)}
                  className="flex w-full items-center justify-between gap-2 border border-sepstrong px-2.5 py-2 text-left text-sm hover:bg-fill"
                >
                  <span className="min-w-0 flex-1 truncate text-label">
                    {v.vorgangsnummer} · {v.titel}
                  </span>
                  <span className={`shrink-0 rounded-[var(--radius-ap-pill)] px-2 py-0.5 text-[11px] font-semibold ${STATUS_BADGE[v.status]}`}>
                    {STATUS_LABEL[v.status]}
                  </span>
                </button>
              ))}
            </div>
          )}
        </div>

        <ZeitSummenBlock filter={{ auftrag_id: auftrag.id }} />

        <div className="border-t border-sep pt-4">
          <button
            onClick={() => {
              if (window.confirm(`Auftrag "${aktuell?.titel ?? auftrag.titel}" wirklich löschen?`)) {
                loeschen.mutate();
              }
            }}
            disabled={loeschen.isPending}
            className="btn-touch text-sm font-medium text-st-fehlt"
          >
            Auftrag löschen
          </button>
        </div>
      </div>
    </SeitenPanel>
  );
}
