import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";

import { ApiError } from "../../../api/client";
import { auftraegeApi, projekteApi, vorgaengeApi } from "../../../api/endpoints";
import { SearchableSelect } from "../../../components/SearchableSelect";
import type { Vorgang } from "../../../types";
import { auftraegeFuerProjekt, auftragGewaehlt, projektGewaehlt, type ZuordnungsWahl } from "../../../utils/verknuepfung";

/** Kleines Panel unter dem "…"-Menü: Projekt und Auftrag eines Vorgangs ändern. Die Listen laden erst
 * beim Öffnen. Gespeichert wird immer das Paar, damit der Server die Kette prüfen kann (widersprüchlich
 * → 400, eigenständig → 409; beides wird als Text angezeigt). */
export function ZuordnungPanel({ vorgang, onSchliessen }: { vorgang: Vorgang; onSchliessen: () => void }) {
  const queryClient = useQueryClient();
  const wurzel = useRef<HTMLDivElement>(null);
  const [wahl, setWahl] = useState<ZuordnungsWahl>({
    projektId: vorgang.projekt_id ?? "",
    auftragId: vorgang.auftrag_id ?? "",
  });
  const [fehler, setFehler] = useState<string | null>(null);

  const { data: projekte } = useQuery({ queryKey: ["projekte"], queryFn: () => projekteApi.list() });
  const { data: auftraege } = useQuery({ queryKey: ["auftraege"], queryFn: () => auftraegeApi.list() });
  const alleAuftraege = auftraege ?? [];

  useEffect(() => {
    const aussen = (e: MouseEvent) => {
      if (wurzel.current && !wurzel.current.contains(e.target as Node)) onSchliessen();
    };
    const taste = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.stopPropagation(); // Esc soll ein umgebendes Seitenpanel nicht mitschließen
      onSchliessen();
    };
    document.addEventListener("mousedown", aussen);
    document.addEventListener("keydown", taste);
    return () => {
      document.removeEventListener("mousedown", aussen);
      document.removeEventListener("keydown", taste);
    };
  }, [onSchliessen]);

  const speichern = useMutation({
    mutationFn: () =>
      vorgaengeApi.update(vorgang.id, { projekt_id: wahl.projektId || null, auftrag_id: wahl.auftragId || null }),
    onSuccess: () => {
      for (const key of [["vorgang", vorgang.id], ["vorgang-events", vorgang.id], ["vorgang-verknuepfung", vorgang.id], ["feed"], ["vorgaenge"], ["projekte"], ["auftraege"]]) {
        queryClient.invalidateQueries({ queryKey: key });
      }
      onSchliessen();
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  const geaendert = wahl.projektId !== (vorgang.projekt_id ?? "") || wahl.auftragId !== (vorgang.auftrag_id ?? "");

  return (
    <div
      ref={wurzel}
      role="dialog"
      aria-label="Zuordnung ändern"
      className="absolute top-full right-0 z-40 mt-1 w-80 max-w-[calc(100vw-1.5rem)] space-y-2 rounded-[10px] border-[0.5px] p-3"
      style={{ backgroundColor: "var(--menu)", borderColor: "var(--sepstrong)", boxShadow: "0 10px 30px rgba(0,0,0,.22)" }}
    >
      <h2 className="text-meta font-semibold tracking-wide text-label2 uppercase">Zuordnung ändern</h2>
      <div>
        <label htmlFor="zuordnung-projekt" className="mb-1 block text-meta font-semibold tracking-wide text-label2 uppercase">
          Projekt
        </label>
        <SearchableSelect
          id="zuordnung-projekt"
          value={wahl.projektId}
          onChange={(v) => setWahl((alt) => projektGewaehlt(alleAuftraege, alt, v))}
          placeholder="Kein Projekt"
          options={[{ value: "", label: "Kein Projekt" }, ...(projekte ?? []).map((p) => ({ value: p.id, label: p.name }))]}
        />
      </div>
      <div>
        <label htmlFor="zuordnung-auftrag" className="mb-1 block text-meta font-semibold tracking-wide text-label2 uppercase">
          Auftrag
        </label>
        <SearchableSelect
          id="zuordnung-auftrag"
          value={wahl.auftragId}
          onChange={(v) => setWahl((alt) => auftragGewaehlt(alleAuftraege, alt, v))}
          placeholder="Kein Auftrag"
          options={[
            { value: "", label: "Kein Auftrag" },
            ...auftraegeFuerProjekt(alleAuftraege, wahl.projektId).map((a) => ({ value: a.id, label: a.titel })),
          ]}
        />
      </div>
      <p className="text-meta text-label2">Nur Aufträge aus dem gewählten Projekt. Wer einen Auftrag wählt, bekommt dessen Projekt automatisch.</p>
      {fehler && (
        <p role="alert" className="text-sekundaer text-st-fehlt">
          {fehler}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button type="button" onClick={onSchliessen} className="btn-touch btn-ap px-3 text-sekundaer">
          Abbrechen
        </button>
        <button
          type="button"
          onClick={() => {
            setFehler(null);
            speichern.mutate();
          }}
          disabled={!geaendert || speichern.isPending}
          className="btn-touch btn-ap-primary px-3 text-sekundaer"
        >
          Speichern
        </button>
      </div>
    </div>
  );
}
