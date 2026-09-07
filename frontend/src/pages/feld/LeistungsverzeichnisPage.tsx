import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, ClipboardList, Plus, X } from "lucide-react";
import { useState } from "react";

import { kundenApi, leistungsverzeichnisApi, materialApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { EmptyState } from "../../components/EmptyState";
import { SearchableSelect } from "../../components/SearchableSelect";
import { useAuth } from "../../context/AuthContext";
import type { LeistungsverzeichnisPosition, LvKalkulationsmodus, LvMaterialPosten } from "../../types";

function euro(wert: string): string {
  return `${Number(wert).toFixed(2)} €`;
}

/** Zeile im Materialblock des Kalkulationsformulars -- entweder frei
 * eingetragen oder aus dem Material-Katalog gewaehlt (dann bleiben Menge
 * und Einzelpreis trotzdem editierbar, falls der Preis fuer diese Position
 * abweicht). */
function MaterialPostenZeile({
  posten,
  onChange,
  onEntfernen,
}: {
  posten: LvMaterialPosten;
  onChange: (posten: LvMaterialPosten) => void;
  onEntfernen: () => void;
}) {
  const { data: material } = useQuery({ queryKey: ["material-alle"], queryFn: () => materialApi.list() });

  return (
    <div className="flex flex-wrap items-end gap-2 border border-ind-line-2 p-2">
      <div className="min-w-[160px] flex-1">
        <label className="mb-1 block text-[10.5px] font-medium text-ind-ink-3">
          Bezeichnung
        </label>
        <SearchableSelect
          value=""
          onChange={(materialId) => {
            const gewaehlt = material?.find((m) => m.id === materialId);
            if (gewaehlt) {
              onChange({
                ...posten,
                bezeichnung: gewaehlt.bezeichnung,
                einzelpreis: gewaehlt.einzelpreis ?? posten.einzelpreis,
                material_id: gewaehlt.id,
              });
            }
          }}
          placeholder={posten.bezeichnung || "Aus Material-Katalog wählen…"}
          options={(material ?? []).map((m) => ({ value: m.id, label: m.bezeichnung }))}
        />
        {posten.bezeichnung && (
          <input
            value={posten.bezeichnung}
            onChange={(e) => onChange({ ...posten, bezeichnung: e.target.value, material_id: null })}
            className="mt-1 w-full border border-ind-line bg-transparent px-2 py-1 text-xs text-ind-ink"
          />
        )}
      </div>
      <div className="w-20">
        <label className="mb-1 block text-[10.5px] font-medium text-ind-ink-3">Menge</label>
        <input
          type="number"
          step="0.01"
          value={posten.menge}
          onChange={(e) => onChange({ ...posten, menge: e.target.value })}
          className="w-full border border-ind-line bg-transparent px-2 py-1 text-xs text-ind-ink"
        />
      </div>
      <div className="w-24">
        <label className="mb-1 block text-[10.5px] font-medium text-ind-ink-3">
          Einzelpreis
        </label>
        <input
          type="number"
          step="0.01"
          value={posten.einzelpreis}
          onChange={(e) => onChange({ ...posten, einzelpreis: e.target.value })}
          className="w-full border border-ind-line bg-transparent px-2 py-1 text-xs text-ind-ink"
        />
      </div>
      <button
        onClick={onEntfernen}
        className="mb-0.5 shrink-0 rounded-md p-1.5 text-slate-300 hover:text-rose-600 dark:text-stone-600 dark:hover:text-rose-400"
      >
        <X size={14} strokeWidth={2} />
      </button>
    </div>
  );
}

/** Mehrfachauswahl von Kunden -- SearchableSelect kennt nur Einzelauswahl,
 * deshalb hier: gewaehlte Kunden als entfernbare Chips, darunter dieselbe
 * SearchableSelect zum Hinzufuegen eines weiteren (leert sich nach jeder
 * Auswahl, gleiches Prinzip wie die Materialposten-Zeile). Leer = gilt fuer
 * alle Kunden. */
function KundenZuweisung({ kundenIds, onChange }: { kundenIds: string[]; onChange: (ids: string[]) => void }) {
  const { data: kunden } = useQuery({ queryKey: ["kunden-alle"], queryFn: () => kundenApi.list() });

  return (
    <div>
      <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
        Kunden-Zuweisung
      </label>
      <p className="mb-1.5 text-xs text-ind-ink-3">Leer = gilt für alle Kunden</p>
      {kundenIds.length > 0 && (
        <div className="mb-1.5 flex flex-wrap gap-1.5">
          {kundenIds.map((id) => (
            <span
              key={id}
              className="flex items-center gap-1 rounded-full bg-violet-100 py-0.5 pr-1 pl-2.5 text-xs font-medium text-violet-700 dark:bg-violet-500/10 dark:text-violet-300"
            >
              {kunden?.find((k) => k.id === id)?.name ?? "…"}
              <button
                onClick={() => onChange(kundenIds.filter((x) => x !== id))}
                className="rounded-full p-0.5 hover:bg-violet-200 dark:hover:bg-violet-500/20"
              >
                <X size={11} strokeWidth={2.5} />
              </button>
            </span>
          ))}
        </div>
      )}
      <SearchableSelect
        value=""
        onChange={(id) => {
          if (!kundenIds.includes(id)) onChange([...kundenIds, id]);
        }}
        placeholder="Kunde hinzufügen…"
        options={(kunden ?? [])
          .filter((k) => !kundenIds.includes(k.id))
          .map((k) => ({ value: k.id, label: k.name }))}
      />
    </div>
  );
}

/** Neu-Anlage (position=null) und Bearbeiten teilen sich dieses Formular.
 * elternPositionId setzt es in den Unterpunkt-Modus (kein "Stundensatz"-
 * Flag, keine eigene Kunden-Zuweisung). Hat die bearbeitete Position bereits
 * eigene Unterpunkte, ist ihr Preis rein rechnerisch die Summe daraus -- die
 * Kalkulationsfelder werden dann nur schreibgeschuetzt als Info angezeigt. */
function LvPositionFormular({
  position,
  elternPositionId,
  hatUnterpunkte,
  onClose,
}: {
  position: LeistungsverzeichnisPosition | null;
  elternPositionId?: string;
  hatUnterpunkte?: boolean;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const istNeu = position === null;
  const istUnterpunkt = !!(position?.eltern_position_id ?? elternPositionId);
  const gesperrt = !!hatUnterpunkte;

  const [bezeichnung, setBezeichnung] = useState(position?.bezeichnung ?? "");
  const [einheit, setEinheit] = useState(position?.einheit ?? "Stk");
  const [istStundensatz, setIstStundensatz] = useState(position?.ist_stundensatz ?? false);
  const [notiz, setNotiz] = useState(position?.notiz ?? "");
  const [kalkulationsmodus, setKalkulationsmodus] = useState<LvKalkulationsmodus>(
    position?.kalkulationsmodus ?? "festpreis",
  );
  const [einzelpreis, setEinzelpreis] = useState(position?.einzelpreis ?? "0");
  const [lohnMinuten, setLohnMinuten] = useState(position?.lohn_minuten?.toString() ?? "");
  const [lohnStundensatz, setLohnStundensatz] = useState(position?.lohn_stundensatz ?? "");
  const [materialPosten, setMaterialPosten] = useState<LvMaterialPosten[]>(position?.material_posten ?? []);
  const [materialAufschlag, setMaterialAufschlag] = useState(position?.material_aufschlag_prozent ?? "0");
  const [kundenIds, setKundenIds] = useState<string[]>(position?.kunden_ids ?? []);
  const [error, setError] = useState<string | null>(null);

  const { data: stundensaetze } = useQuery({
    queryKey: ["leistungsverzeichnis", "stundensaetze"],
    queryFn: () => leistungsverzeichnisApi.list(undefined, true),
    enabled: kalkulationsmodus === "berechnet",
  });

  const lohnGesamt =
    lohnMinuten && lohnStundensatz ? (Number(lohnMinuten) / 60) * Number(lohnStundensatz) : 0;
  const materialBasis = materialPosten.reduce((summe, p) => summe + Number(p.menge || 0) * Number(p.einzelpreis || 0), 0);
  const materialGesamt = materialBasis * (1 + Number(materialAufschlag || 0) / 100);

  const invalidieren = () => queryClient.invalidateQueries({ queryKey: ["leistungsverzeichnis"] });

  const speichern = useMutation({
    mutationFn: () => {
      const body = {
        bezeichnung,
        einheit,
        ist_stundensatz: istUnterpunkt ? false : istStundensatz,
        notiz: notiz || undefined,
        kalkulationsmodus,
        einzelpreis: kalkulationsmodus === "festpreis" ? einzelpreis : undefined,
        lohn_minuten: kalkulationsmodus === "berechnet" ? Number(lohnMinuten) || null : null,
        lohn_stundensatz: kalkulationsmodus === "berechnet" ? lohnStundensatz || null : null,
        material_posten: kalkulationsmodus === "berechnet" ? materialPosten : [],
        material_aufschlag_prozent: kalkulationsmodus === "berechnet" ? materialAufschlag : "0",
        kunden_ids: istUnterpunkt ? undefined : kundenIds,
      };
      return istNeu
        ? leistungsverzeichnisApi.create({ eltern_position_id: elternPositionId, ...body })
        : leistungsverzeichnisApi.update(position!.id, body);
    },
    onSuccess: () => {
      invalidieren();
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Position konnte nicht gespeichert werden"),
  });

  const loeschen = useMutation({
    mutationFn: () => leistungsverzeichnisApi.remove(position!.id),
    onSuccess: () => {
      invalidieren();
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-h-full w-full max-w-lg overflow-y-auto rounded-xl border border-slate-200 bg-white dark:border-stone-800 dark:bg-stone-900"
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 dark:border-stone-800">
          <h2 className="text-base font-bold text-ind-ink">
            {istNeu ? (istUnterpunkt ? "Neuer Unterpunkt" : "Neue Position") : "Position bearbeiten"}
          </h2>
          <button
            onClick={onClose}
            className="btn-touch flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 dark:text-stone-500 dark:hover:bg-stone-800"
          >
            <X size={16} strokeWidth={2} />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          <div className="grid grid-cols-3 gap-3">
            <div className="col-span-2">
              <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
                Bezeichnung
              </label>
              <input
                autoFocus
                value={bezeichnung}
                onChange={(e) => setBezeichnung(e.target.value)}
                placeholder={istUnterpunkt ? "z. B. Liefern und Montieren" : "z. B. Installation Wallbox"}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
                Einheit
              </label>
              <input
                value={einheit}
                onChange={(e) => setEinheit(e.target.value)}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
            </div>
          </div>

          {!istUnterpunkt && (
            <label className="flex items-center gap-2 text-sm text-ind-ink-2">
              <input
                type="checkbox"
                checked={istStundensatz}
                onChange={(e) => setIstStundensatz(e.target.checked)}
                className="h-4 w-4 rounded border-slate-300 dark:border-stone-600"
              />
              Als Stundenverrechnungssatz in der Zeiterfassung wählbar
            </label>
          )}

          {!istUnterpunkt && <KundenZuweisung kundenIds={kundenIds} onChange={setKundenIds} />}

          {gesperrt ? (
            <div className="rounded-md bg-slate-50 p-3 text-sm text-slate-500 dark:bg-stone-800/60 dark:text-stone-400">
              Diese Position hat Unterpunkte -- ihr Preis ergibt sich automatisch aus deren Summe (aktuell{" "}
              <strong className="text-ind-ink">{euro(position!.einzelpreis)}</strong>). Um die
              Kalkulation zu ändern, bitte die Unterpunkte bearbeiten.
            </div>
          ) : (
            <>
              <div>
                <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
                  Preisermittlung
                </label>
                <div className="flex gap-0.5 rounded-lg border border-slate-200 bg-slate-100 p-0.5 dark:border-stone-700 dark:bg-stone-800">
                  {(["festpreis", "berechnet"] as LvKalkulationsmodus[]).map((modus) => (
                    <button
                      key={modus}
                      onClick={() => setKalkulationsmodus(modus)}
                      className={`flex-1 rounded-md px-3 py-1.5 text-xs font-semibold ${
                        kalkulationsmodus === modus
                          ? "bg-white text-slate-800 shadow-xs dark:bg-stone-900 dark:text-stone-100"
                          : "text-slate-500 hover:text-ind-ink-2 dark:hover:text-stone-200"
                      }`}
                    >
                      {modus === "festpreis" ? "Festpreis" : "Berechnet (Lohn + Material)"}
                    </button>
                  ))}
                </div>
              </div>

              {kalkulationsmodus === "festpreis" ? (
                <div>
                  <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
                    Einzelpreis (€)
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={einzelpreis}
                    onChange={(e) => setEinzelpreis(e.target.value)}
                    className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
                  />
                </div>
              ) : (
                <div className="space-y-4">
                  <div className="rounded-lg border border-slate-200 p-3 dark:border-stone-800">
                    <p className="mb-2 text-xs font-bold text-ind-ink-2">Lohn</p>
                    <div className="grid grid-cols-2 gap-2">
                      <div>
                        <label className="mb-1 block text-[10.5px] font-medium text-ind-ink-3">
                          Zeit (Minuten)
                        </label>
                        <input
                          type="number"
                          value={lohnMinuten}
                          onChange={(e) => setLohnMinuten(e.target.value)}
                          className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
                        />
                      </div>
                      <div>
                        <label className="mb-1 block text-[10.5px] font-medium text-ind-ink-3">
                          Stundensatz (€)
                        </label>
                        <input
                          type="number"
                          step="0.01"
                          value={lohnStundensatz}
                          onChange={(e) => setLohnStundensatz(e.target.value)}
                          className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
                        />
                      </div>
                    </div>
                    {!!stundensaetze?.length && (
                      <div className="mt-2">
                        <SearchableSelect
                          value=""
                          onChange={(id) => {
                            const gewaehlt = stundensaetze.find((s) => s.id === id);
                            if (gewaehlt) setLohnStundensatz(gewaehlt.einzelpreis);
                          }}
                          placeholder="Aus Stundensatz-Katalog übernehmen…"
                          options={stundensaetze.map((s) => ({
                            value: s.id,
                            label: `${s.bezeichnung} · ${euro(s.einzelpreis)}`,
                          }))}
                        />
                      </div>
                    )}
                    <p className="mt-2 text-xs font-semibold text-ind-ink-3">
                      = {euro(lohnGesamt.toFixed(2))}
                    </p>
                  </div>

                  <div className="rounded-lg border border-slate-200 p-3 dark:border-stone-800">
                    <p className="mb-2 text-xs font-bold text-ind-ink-2">Material</p>
                    <div className="space-y-1.5">
                      {materialPosten.map((p, i) => (
                        <MaterialPostenZeile
                          key={i}
                          posten={p}
                          onChange={(neu) =>
                            setMaterialPosten((bisher) => bisher.map((x, xi) => (xi === i ? neu : x)))
                          }
                          onEntfernen={() => setMaterialPosten((bisher) => bisher.filter((_, xi) => xi !== i))}
                        />
                      ))}
                      <button
                        onClick={() =>
                          setMaterialPosten((bisher) => [
                            ...bisher,
                            { bezeichnung: "", menge: "1", einzelpreis: "0", material_id: null },
                          ])
                        }
                        className="flex items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium text-slate-400 hover:bg-slate-100 dark:text-stone-500 dark:hover:bg-stone-800/60"
                      >
                        <Plus size={13} strokeWidth={2} /> Materialposten hinzufügen
                      </button>
                    </div>
                    <div className="mt-2">
                      <label className="mb-1 block text-[10.5px] font-medium text-ind-ink-3">
                        Materialaufschlag (%)
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        value={materialAufschlag}
                        onChange={(e) => setMaterialAufschlag(e.target.value)}
                        className="w-28 border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
                      />
                    </div>
                    <p className="mt-2 text-xs font-semibold text-ind-ink-3">
                      = {euro(materialGesamt.toFixed(2))}
                    </p>
                  </div>

                  <div className="rounded-lg bg-slate-50 p-3 text-sm font-bold text-slate-800 dark:bg-stone-800/60 dark:text-stone-100">
                    Gesamt: {euro((lohnGesamt + materialGesamt).toFixed(2))}
                  </div>
                </div>
              )}
            </>
          )}

          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
              Notiz
            </label>
            <textarea
              value={notiz}
              onChange={(e) => setNotiz(e.target.value)}
              rows={2}
              className="w-full resize-none border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>

          {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
        </div>

        <div className="flex items-center justify-between gap-3 border-t border-slate-100 px-5 py-4 dark:border-stone-800">
          {istNeu ? (
            <span />
          ) : (
            <button
              onClick={() => {
                if (window.confirm(`"${position!.bezeichnung}" wirklich löschen?`)) loeschen.mutate();
              }}
              disabled={loeschen.isPending}
              className="btn-touch text-xs font-medium text-slate-400 hover:text-red-600 disabled:opacity-50 dark:text-stone-500 dark:hover:text-red-400"
            >
              Löschen
            </button>
          )}
          <div className="flex gap-2">
            <button
              onClick={onClose}
              className="btn-touch btn-industry btn-industry-secondary px-4 py-2 text-sm font-semibold"
            >
              Abbrechen
            </button>
            <button
              onClick={() => speichern.mutate()}
              disabled={!bezeichnung.trim() || speichern.isPending}
              className="btn-touch btn-clay rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
            >
              Speichern
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function LvUnterpunktZeile({ position, onEdit }: { position: LeistungsverzeichnisPosition; onEdit: () => void }) {
  return (
    <button
      onClick={onEdit}
      className="card-interactive flex w-full items-center justify-between gap-2 rounded-lg bg-slate-50 p-2.5 text-left dark:bg-stone-800/60"
    >
      <div className="min-w-0">
        <p className="truncate text-[13px] font-medium text-ind-ink">{position.bezeichnung}</p>
        {position.kalkulationsmodus === "berechnet" && (
          <p className="text-[11px] text-ind-ink-3">
            Lohn {euro(position.lohn_gesamt)} · Material {euro(position.material_gesamt)}
          </p>
        )}
      </div>
      <span className="shrink-0 text-sm font-semibold text-ind-ink">
        {euro(position.einzelpreis)}
      </span>
    </button>
  );
}

function LvHauptpunktZeile({ position }: { position: LeistungsverzeichnisPosition }) {
  const [offen, setOffen] = useState(false);
  const [panel, setPanel] = useState<
    { modus: "bearbeiten"; position: LeistungsverzeichnisPosition } | { modus: "neuer-unterpunkt" } | null
  >(null);

  const { data: unterpunkte } = useQuery({
    queryKey: ["leistungsverzeichnis", "unterpunkte", position.id],
    queryFn: () => leistungsverzeichnisApi.unterpunkte(position.id),
    enabled: offen,
  });
  const { data: kunden } = useQuery({
    queryKey: ["kunden-alle"],
    queryFn: () => kundenApi.list(),
    enabled: position.kunden_ids.length > 0,
  });
  const kundenBadge =
    position.kunden_ids.length === 0
      ? null
      : position.kunden_ids.length === 1
        ? (kunden?.find((k) => k.id === position.kunden_ids[0])?.name ?? "1 Kunde")
        : `${position.kunden_ids.length} Kunden`;

  return (
    <div className="rounded-lg bg-white shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
      <div className="flex items-center gap-2 p-3">
        <button
          onClick={() => setOffen((v) => !v)}
          className="btn-touch flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 dark:text-stone-500 dark:hover:bg-stone-800"
        >
          {offen ? <ChevronDown size={16} strokeWidth={2} /> : <ChevronRight size={16} strokeWidth={2} />}
        </button>
        <button onClick={() => setPanel({ modus: "bearbeiten", position })} className="min-w-0 flex-1 text-left">
          <p className="truncate text-sm font-semibold text-ind-ink">
            {position.bezeichnung}
            {position.ist_stundensatz && (
              <span className="ml-2 rounded-full bg-cyan-100 px-2 py-0.5 text-[10px] font-normal text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-400">
                SVS
              </span>
            )}
            {kundenBadge && (
              <span className="ml-2 rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-normal text-violet-700 dark:bg-violet-500/10 dark:text-violet-300">
                {kundenBadge}
              </span>
            )}
          </p>
          {position.kalkulationsmodus === "berechnet" && (
            <p className="text-[11.5px] text-ind-ink-3">
              Lohn {euro(position.lohn_gesamt)} · Material {euro(position.material_gesamt)}
            </p>
          )}
        </button>
        <span className="shrink-0 text-sm font-bold text-ind-ink">
          {euro(position.einzelpreis)} / {position.einheit}
        </span>
      </div>

      {offen && (
        <div className="space-y-1.5 border-t border-slate-100 p-3 dark:border-stone-800">
          {(unterpunkte ?? []).map((u) => (
            <LvUnterpunktZeile key={u.id} position={u} onEdit={() => setPanel({ modus: "bearbeiten", position: u })} />
          ))}
          <button
            onClick={() => setPanel({ modus: "neuer-unterpunkt" })}
            className="flex w-full items-center gap-1.5 rounded-lg px-2 py-2 text-xs font-medium text-slate-400 hover:bg-slate-100 dark:text-stone-500 dark:hover:bg-stone-800/60"
          >
            <Plus size={13} strokeWidth={2} /> Unterpunkt hinzufügen
          </button>
        </div>
      )}

      {panel?.modus === "bearbeiten" && (
        <LvPositionFormular
          position={panel.position}
          hatUnterpunkte={panel.position.id === position.id && !!unterpunkte?.length}
          onClose={() => setPanel(null)}
        />
      )}
      {panel?.modus === "neuer-unterpunkt" && (
        <LvPositionFormular position={null} elternPositionId={position.id} onClose={() => setPanel(null)} />
      )}
    </div>
  );
}

/** Kompletter Leistungskatalog eines Mandanten mit Kalkulator: zeigt ALLE
 * eigenstaendigen Positionen zusammen -- allgemeine (keinem Kunden
 * zugewiesen) und kundenspezifische. Hauptpunkte koennen Unterpunkte
 * bekommen (eine Ebene tief), deren Lohn/Material-Kalkulation sich
 * automatisch zum Hauptpunkt-Preis summiert (siehe app/api/routes/
 * leistungsverzeichnis.py). Eine Position kann keinem, einem oder mehreren
 * Kunden zugewiesen werden (siehe KundenZuweisung); KundeProfilePage.tsx
 * zeigt zusaetzlich eine schnelle, auf den jeweiligen Kunden gefilterte
 * Sicht. */
export function LeistungsverzeichnisPage() {
  const { hatRecht } = useAuth();
  const kannVerwalten = hatRecht("kunden", "bearbeiten");
  const [neuePosition, setNeuePosition] = useState(false);

  const { data: positionen, isLoading } = useQuery({
    queryKey: ["leistungsverzeichnis", "katalog"],
    queryFn: () => leistungsverzeichnisApi.list(),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-ind-ink">Leistungsverzeichnis</h1>
        {kannVerwalten && (
          <button
            onClick={() => setNeuePosition(true)}
            className="btn-touch flex items-center gap-1.5 rounded-lg btn-industry btn-industry-primary px-3 py-2 text-xs font-semibold"
          >
            <Plus size={14} strokeWidth={2.5} />
            Neue Position
          </button>
        )}
      </div>

      {isLoading ? (
        <p className="py-10 text-center text-sm text-ind-ink-3">Lädt…</p>
      ) : !positionen || positionen.length === 0 ? (
        <EmptyState icon={ClipboardList} text="Noch keine Positionen im Leistungsverzeichnis." />
      ) : (
        <div className="space-y-2">
          {positionen.map((p) => (
            <LvHauptpunktZeile key={p.id} position={p} />
          ))}
        </div>
      )}

      {neuePosition && <LvPositionFormular position={null} onClose={() => setNeuePosition(false)} />}
    </div>
  );
}
