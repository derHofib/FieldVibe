import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, ChevronDown, ChevronRight, ClipboardList, Copy, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { leistungsverzeichnisApi, leistungsverzeichnisseApi, mandantEinstellungenApi, materialApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { EmptyState } from "../../components/EmptyState";
import { SearchableSelect } from "../../components/SearchableSelect";
import { SeitenPanel } from "../../components/SeitenPanel";
import { useAuth } from "../../context/AuthContext";
import type { LeistungsverzeichnisPosition, LvKalkulationsmodus, LvMaterialPosten } from "../../types";
import { KundenZuweisung } from "./LeistungsverzeichnisPage";

function euro(wert: string | number): string {
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
        className="mb-0.5 shrink-0 p-1.5 text-ind-ink-3 hover:text-red-600 dark:hover:text-red-400"
      >
        <X size={14} strokeWidth={1.5} />
      </button>
    </div>
  );
}

/** Kern-Baustein: alle Felder einer Position (Stammdaten, Kalkulation,
 * Notiz), rekursiv wiederverwendet fuer Haupt- UND Unterpunkte -- ein
 * Unterpunkt hat schlicht keine eigenen Unterpositionen, gesteuert ueber
 * istUnterpunkt (eine Ebene tief, wie serverseitig durchgesetzt). Wird
 * sowohl als Hauptinhalt eines SeitenPanel (Hauptpunkt) als auch inline
 * innerhalb einer aufklappbaren Unterpunkt-Zeile eingesetzt -- deshalb
 * ohne eigenes Rahmen-/Panel-Chrome, nur der reine Feld-/Aktions-Block.
 * Hat die Position bereits eigene Unterpunkte, ist ihr Preis rein
 * rechnerisch deren Summe -- die Kalkulationsfelder werden dann nur
 * schreibgeschuetzt als Summen-Rechnung am unteren Ende angezeigt. */
function LvPositionFelder({
  leistungsverzeichnisId,
  position,
  elternPositionId,
  onFertig,
}: {
  leistungsverzeichnisId: string;
  position: LeistungsverzeichnisPosition | null;
  elternPositionId?: string;
  onFertig: () => void;
}) {
  const queryClient = useQueryClient();
  const istNeu = position === null;
  const istUnterpunkt = !!(position?.eltern_position_id ?? elternPositionId);

  const { data: mandantEinstellungen } = useQuery({
    queryKey: ["mandant-einstellungen"],
    queryFn: mandantEinstellungenApi.get,
    enabled: istNeu,
  });

  // Unterpositionen nur fuer bereits bestehende Hauptpunkte relevant --
  // treibt sowohl die "Unterpositionen"-Liste als auch die Sperre der
  // eigenen Kalkulationsfelder (hatUnterpunkte).
  const { data: unterpunkte } = useQuery({
    queryKey: ["leistungsverzeichnis", "unterpunkte", position?.id],
    queryFn: () => leistungsverzeichnisApi.unterpunkte(position!.id),
    enabled: !istNeu && !istUnterpunkt,
  });
  const hatUnterpunkte = !istNeu && !istUnterpunkt && !!unterpunkte?.length;
  const [neuerUnterpunktOffen, setNeuerUnterpunktOffen] = useState(false);

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
  const [lohnGemeinkosten, setLohnGemeinkosten] = useState(
    position?.lohn_gemeinkosten_prozent ?? mandantEinstellungen?.standard_lohn_gemeinkosten_prozent ?? "0",
  );
  const [materialPosten, setMaterialPosten] = useState<LvMaterialPosten[]>(position?.material_posten ?? []);
  const [materialAufschlag, setMaterialAufschlag] = useState(position?.material_aufschlag_prozent ?? "0");
  const [gewinnWagnis, setGewinnWagnis] = useState(
    position?.gewinn_wagnis_prozent ?? mandantEinstellungen?.standard_gewinn_wagnis_prozent ?? "0",
  );
  const [error, setError] = useState<string | null>(null);

  const { data: stundensaetze } = useQuery({
    queryKey: ["leistungsverzeichnis", "stundensaetze"],
    queryFn: () => leistungsverzeichnisApi.list(undefined, true),
    enabled: kalkulationsmodus === "berechnet" && !hatUnterpunkte,
  });

  const lohnBasis =
    lohnMinuten && lohnStundensatz ? (Number(lohnMinuten) / 60) * Number(lohnStundensatz) : 0;
  const lohnGesamt = lohnBasis * (1 + Number(lohnGemeinkosten || 0) / 100);
  const materialBasis = materialPosten.reduce((summe, p) => summe + Number(p.menge || 0) * Number(p.einzelpreis || 0), 0);
  const materialGesamtVorGewinn = materialBasis * (1 + Number(materialAufschlag || 0) / 100);
  const zwischensumme = lohnGesamt + materialGesamtVorGewinn;
  const gewinnFaktor = 1 + Number(gewinnWagnis || 0) / 100;
  const gesamt = zwischensumme * gewinnFaktor;

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
        lohn_gemeinkosten_prozent: kalkulationsmodus === "berechnet" ? lohnGemeinkosten : "0",
        material_posten: kalkulationsmodus === "berechnet" ? materialPosten : [],
        material_aufschlag_prozent: kalkulationsmodus === "berechnet" ? materialAufschlag : "0",
        gewinn_wagnis_prozent: kalkulationsmodus === "berechnet" ? gewinnWagnis : "0",
      };
      return istNeu
        ? leistungsverzeichnisApi.create({
            leistungsverzeichnis_id: elternPositionId ? undefined : leistungsverzeichnisId,
            eltern_position_id: elternPositionId,
            ...body,
          })
        : leistungsverzeichnisApi.update(position!.id, body);
    },
    onSuccess: () => {
      invalidieren();
      onFertig();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Position konnte nicht gespeichert werden"),
  });

  const loeschen = useMutation({
    mutationFn: () => leistungsverzeichnisApi.remove(position!.id),
    onSuccess: () => {
      invalidieren();
      onFertig();
    },
  });

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-3 gap-3">
        <div className="col-span-2">
          <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">
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
          <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">
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
            className="h-4 w-4 border-ind-line"
          />
          Als Stundenverrechnungssatz in der Zeiterfassung wählbar
        </label>
      )}

      {hatUnterpunkte ? (
        <p className="border border-ind-line-2 bg-ind-hover/40 p-3 text-sm text-ind-ink-3">
          Diese Position hat Unterpositionen -- ihr Preis ergibt sich automatisch aus deren Summe (siehe
          Summen-Rechnung unten). Um die Kalkulation zu ändern, bitte die Unterpositionen bearbeiten.
        </p>
      ) : (
        <>
          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">
              Preisermittlung
            </label>
            <div className="seg-industry flex border border-ind-line">
              {(["festpreis", "berechnet"] as LvKalkulationsmodus[]).map((modus) => (
                <button
                  key={modus}
                  onClick={() => setKalkulationsmodus(modus)}
                  className={`flex-1 px-3 py-1.5 text-xs font-semibold ${
                    kalkulationsmodus === modus
                      ? "bg-ind-field text-ind-field-ink"
                      : "text-ind-ink-2 hover:bg-ind-hover"
                  }`}
                >
                  {modus === "festpreis" ? "Festpreis" : "Berechnet (Lohn + Material)"}
                </button>
              ))}
            </div>
          </div>

          {kalkulationsmodus === "festpreis" ? (
            <div>
              <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">
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
              <div className="border border-ind-line-2 p-3">
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
                <div className="mt-2">
                  <label className="mb-1 block text-[10.5px] font-medium text-ind-ink-3">
                    Gemeinkosten (%)
                  </label>
                  <input
                    type="number"
                    step="0.1"
                    value={lohnGemeinkosten}
                    onChange={(e) => setLohnGemeinkosten(e.target.value)}
                    className="w-28 border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
                  />
                </div>
              </div>

              <div className="border border-ind-line-2 p-3">
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
                    className="flex items-center gap-1.5 px-2 py-1.5 text-xs font-medium text-ind-ink-3 hover:bg-ind-hover"
                  >
                    <Plus size={13} strokeWidth={1.5} /> Materialposten hinzufügen
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
              </div>

              <div className="border border-ind-line-2 p-3">
                <label className="mb-1 block text-[10.5px] font-medium text-ind-ink-3">
                  Gewinn/Wagnis (%)
                </label>
                <input
                  type="number"
                  step="0.1"
                  value={gewinnWagnis}
                  onChange={(e) => setGewinnWagnis(e.target.value)}
                  className="w-28 border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
                />
              </div>
            </div>
          )}
        </>
      )}

      <div>
        <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">
          Notiz
        </label>
        <textarea
          value={notiz}
          onChange={(e) => setNotiz(e.target.value)}
          rows={2}
          className="w-full resize-none border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
        />
      </div>

      {!istNeu && !istUnterpunkt && (
        <div className="space-y-2 border-t border-ind-line pt-4">
          <p className="text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">Unterpositionen</p>
          {(unterpunkte ?? []).map((u) => (
            <UnterpunktZeileAufklappbar
              key={u.id}
              leistungsverzeichnisId={leistungsverzeichnisId}
              elternPositionId={position!.id}
              position={u}
            />
          ))}
          {neuerUnterpunktOffen ? (
            <div className="border border-ind-line-2 p-3">
              <LvPositionFelder
                leistungsverzeichnisId={leistungsverzeichnisId}
                position={null}
                elternPositionId={position!.id}
                onFertig={() => setNeuerUnterpunktOffen(false)}
              />
            </div>
          ) : (
            <button
              onClick={() => setNeuerUnterpunktOffen(true)}
              className="flex w-full items-center gap-1.5 border border-dashed border-ind-line px-2 py-2 text-xs font-medium text-ind-ink-3 hover:bg-ind-hover"
            >
              <Plus size={13} strokeWidth={1.5} /> Unterpunkt hinzufügen
            </button>
          )}
        </div>
      )}

      {/* Summen-Rechnung: bei einer Position mit Unterpositionen die
       * Summe daraus, sonst -- im Modus "berechnet" -- die vollstaendige
       * Aufschluesselung. Bewusst als letzter Block vor den
       * Aktions-Buttons, siehe Komponenten-Docstring. */}
      {hatUnterpunkte ? (
        <div className="border-t border-ind-line pt-4">
          <p className="mb-1.5 text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">Summe</p>
          <div className="flex items-center justify-between border border-ind-line-2 bg-ind-hover/40 p-3 text-sm font-bold text-ind-ink">
            <span>Gesamt (Summe der Unterpositionen)</span>
            <span>{euro(position!.einzelpreis)}</span>
          </div>
        </div>
      ) : (
        kalkulationsmodus === "berechnet" && (
          <div className="border-t border-ind-line pt-4">
            <p className="mb-1.5 text-[11px] font-bold tracking-wide text-ind-ink-3 uppercase">Summe</p>
            <div className="space-y-1 border border-ind-line-2 p-3 text-xs text-ind-ink-3">
              <div className="flex justify-between">
                <span>Lohn-Basis</span>
                <span>{euro(lohnBasis)}</span>
              </div>
              <div className="flex justify-between">
                <span>+ Gemeinkosten ({lohnGemeinkosten || 0}%)</span>
                <span>{euro(lohnGesamt)}</span>
              </div>
              <div className="flex justify-between">
                <span>Material-Basis</span>
                <span>{euro(materialBasis)}</span>
              </div>
              <div className="flex justify-between">
                <span>+ Aufschlag ({materialAufschlag || 0}%)</span>
                <span>{euro(materialGesamtVorGewinn)}</span>
              </div>
              <div className="flex justify-between border-t border-ind-line-2 pt-1 font-medium text-ind-ink-2">
                <span>Zwischensumme</span>
                <span>{euro(zwischensumme)}</span>
              </div>
              <div className="flex justify-between">
                <span>+ Gewinn/Wagnis ({gewinnWagnis || 0}%)</span>
                <span>{euro(gesamt)}</span>
              </div>
              <div className="flex justify-between border-t border-ind-line-2 pt-1.5 text-sm font-bold text-ind-ink">
                <span>Gesamt</span>
                <span>{euro(gesamt)}</span>
              </div>
            </div>
          </div>
        )
      )}

      {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}

      <div className="flex items-center justify-between gap-3 border-t border-ind-line pt-4">
        {istNeu ? (
          <span />
        ) : (
          <button
            onClick={() => {
              if (window.confirm(`"${position!.bezeichnung}" wirklich löschen?`)) loeschen.mutate();
            }}
            disabled={loeschen.isPending}
            className="btn-touch text-xs font-medium text-ind-ink-3 hover:text-red-600 disabled:opacity-50 dark:hover:text-red-400"
          >
            Löschen
          </button>
        )}
        <div className="flex gap-2">
          <button onClick={onFertig} className="btn-touch btn-industry btn-industry-secondary px-4 py-2 text-sm font-semibold">
            Abbrechen
          </button>
          <button
            onClick={() => speichern.mutate()}
            disabled={!bezeichnung.trim() || speichern.isPending}
            className="btn-touch btn-industry btn-industry-primary px-4 py-2 text-sm font-semibold disabled:opacity-50"
          >
            Speichern
          </button>
        </div>
      </div>
    </div>
  );
}

/** Eine Unterposition als aufklappbare Zeile -- Klick zeigt/versteckt das
 * Bearbeiten-Formular direkt inline (kein weiteres Panel), siehe
 * Komponenten-Docstring von LvPositionFelder. */
function UnterpunktZeileAufklappbar({
  leistungsverzeichnisId,
  elternPositionId,
  position,
}: {
  leistungsverzeichnisId: string;
  elternPositionId: string;
  position: LeistungsverzeichnisPosition;
}) {
  const [offen, setOffen] = useState(false);
  return (
    <div className="border border-ind-line-2">
      <button onClick={() => setOffen((v) => !v)} className="flex w-full items-center gap-2 p-2.5 text-left">
        {offen ? (
          <ChevronDown size={14} strokeWidth={1.5} className="shrink-0 text-ind-ink-3" />
        ) : (
          <ChevronRight size={14} strokeWidth={1.5} className="shrink-0 text-ind-ink-3" />
        )}
        <span className="min-w-0 flex-1 truncate text-[13px] font-medium text-ind-ink">{position.bezeichnung}</span>
        <span className="shrink-0 text-sm font-semibold text-ind-ink">{euro(position.einzelpreis)}</span>
      </button>
      {offen && (
        <div className="border-t border-ind-line-2 p-3">
          <LvPositionFelder
            leistungsverzeichnisId={leistungsverzeichnisId}
            position={position}
            elternPositionId={elternPositionId}
            onFertig={() => setOffen(false)}
          />
        </div>
      )}
    </div>
  );
}

/** Zeile in der Positionen-Liste -- oeffnet beim Klick das rechtsseitige
 * Detail-/Bearbeiten-Panel (SeitenPanel) statt eines zentrierten Modals;
 * Unterpositionen erscheinen darin, nicht mehr als eigenes Akkordeon in
 * der Liste. */
function LvHauptpunktZeile({ leistungsverzeichnisId, position }: { leistungsverzeichnisId: string; position: LeistungsverzeichnisPosition }) {
  const [offen, setOffen] = useState(false);

  return (
    <>
      <button
        onClick={() => setOffen(true)}
        className="card-interactive flex w-full items-center gap-2 border border-ind-line bg-ind-bg p-3 text-left"
      >
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-ind-ink">
            {position.bezeichnung}
            {position.ist_stundensatz && (
              <span className="ml-2 rounded-full bg-cyan-100 px-2 py-0.5 text-[10px] font-normal text-cyan-700 dark:bg-cyan-500/10 dark:text-cyan-400">
                SVS
              </span>
            )}
          </p>
          {position.kalkulationsmodus === "berechnet" && (
            <p className="text-[11.5px] text-ind-ink-3">
              Lohn {euro(position.lohn_gesamt)} · Material {euro(position.material_gesamt)}
            </p>
          )}
        </div>
        <span className="shrink-0 text-sm font-bold text-ind-ink">
          {euro(position.einzelpreis)} / {position.einheit}
        </span>
        <ChevronRight size={16} strokeWidth={1.5} className="shrink-0 text-ind-ink-3" />
      </button>

      {offen && (
        <SeitenPanel title={position.bezeichnung} onClose={() => setOffen(false)}>
          <LvPositionFelder
            leistungsverzeichnisId={leistungsverzeichnisId}
            position={position}
            onFertig={() => setOffen(false)}
          />
        </SeitenPanel>
      )}
    </>
  );
}

/** Detailseite eines Leistungsverzeichnisses: Kopfdaten inkl.
 * Kunden-Zuweisung (M:N, siehe KundenZuweisung), Positionen/Unterpunkte
 * (eine Ebene tief) und "Duplizieren" -- kopiert das LV samt Positionen mit
 * eigener, zunaechst leerer Kunden-Zuweisung. */
export function LeistungsverzeichnisDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { hatRecht } = useAuth();
  const kannVerwalten = hatRecht("kunden", "bearbeiten");
  const [neuePosition, setNeuePosition] = useState(false);

  const { data: lv, isLoading: lvLaedt } = useQuery({
    queryKey: ["leistungsverzeichnisse", id],
    queryFn: () => leistungsverzeichnisseApi.get(id!),
  });
  const { data: positionen, isLoading: positionenLaden } = useQuery({
    queryKey: ["leistungsverzeichnis", "lv", id],
    queryFn: () => leistungsverzeichnisApi.list(undefined, false, id),
  });

  const kundenSpeichern = useMutation({
    mutationFn: (kundenIds: string[]) => leistungsverzeichnisseApi.update(id!, { kunden_ids: kundenIds }),
    onSuccess: (daten) => queryClient.setQueryData(["leistungsverzeichnisse", id], daten),
  });

  const duplizieren = useMutation({
    mutationFn: () => leistungsverzeichnisseApi.duplizieren(id!),
    onSuccess: (kopie) => {
      queryClient.invalidateQueries({ queryKey: ["leistungsverzeichnisse"] });
      navigate(`/leistungsverzeichnis/${kopie.id}`);
    },
  });

  const loeschen = useMutation({
    mutationFn: () => leistungsverzeichnisseApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["leistungsverzeichnisse"] });
      navigate("/leistungsverzeichnis");
    },
  });

  if (lvLaedt) return <p className="py-10 text-center text-sm text-ind-ink-3">Lädt…</p>;
  if (!lv) return <EmptyState icon={ClipboardList} text="Leistungsverzeichnis nicht gefunden." />;

  return (
    <div className="space-y-4">
      <div className="flex items-center gap-2">
        <button
          onClick={() => navigate("/leistungsverzeichnis")}
          className="btn-touch btn-industry btn-industry-secondary btn-industry-icon"
        >
          <ArrowLeft size={16} strokeWidth={1.5} />
        </button>
        <div className="min-w-0 flex-1">
          <h1 className="truncate text-lg font-bold text-ind-ink">{lv.name}</h1>
          {lv.beschreibung && <p className="truncate text-xs text-ind-ink-3">{lv.beschreibung}</p>}
        </div>
        {kannVerwalten && (
          <>
            <button
              onClick={() => duplizieren.mutate()}
              disabled={duplizieren.isPending}
              className="btn-touch flex items-center gap-1.5 btn-industry btn-industry-secondary px-3 py-2 text-xs font-semibold disabled:opacity-50"
            >
              <Copy size={13} strokeWidth={1.5} /> Duplizieren
            </button>
            <button
              onClick={() => {
                if (window.confirm(`"${lv.name}" samt aller Positionen wirklich löschen?`)) loeschen.mutate();
              }}
              disabled={loeschen.isPending}
              className="btn-touch btn-industry btn-industry-secondary btn-industry-icon text-ind-ink-3 hover:text-red-600 disabled:opacity-50 dark:hover:text-red-400"
            >
              <Trash2 size={15} strokeWidth={1.5} />
            </button>
          </>
        )}
      </div>

      {kannVerwalten ? (
        <div className="border border-ind-line bg-ind-bg p-3">
          <KundenZuweisung kundenIds={lv.kunden_ids} onChange={(ids) => kundenSpeichern.mutate(ids)} />
        </div>
      ) : (
        lv.kunden_ids.length > 0 && (
          <p className="text-xs text-ind-ink-3">{lv.kunden_ids.length} Kunde(n) zugewiesen</p>
        )
      )}

      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-ind-ink-3">Positionen</h2>
        {kannVerwalten && (
          <button
            onClick={() => setNeuePosition(true)}
            className="btn-touch flex items-center gap-1.5 btn-industry btn-industry-primary px-3 py-2 text-xs font-semibold"
          >
            <Plus size={14} strokeWidth={1.5} />
            Neue Position
          </button>
        )}
      </div>

      {positionenLaden ? (
        <p className="py-10 text-center text-sm text-ind-ink-3">Lädt…</p>
      ) : !positionen || positionen.length === 0 ? (
        <EmptyState icon={ClipboardList} text="Noch keine Positionen in diesem Leistungsverzeichnis." />
      ) : (
        <div className="space-y-2">
          {positionen.map((p) => (
            <LvHauptpunktZeile key={p.id} leistungsverzeichnisId={id!} position={p} />
          ))}
        </div>
      )}

      {neuePosition && (
        <SeitenPanel title="Neue Position" onClose={() => setNeuePosition(false)}>
          <LvPositionFelder leistungsverzeichnisId={id!} position={null} onFertig={() => setNeuePosition(false)} />
        </SeitenPanel>
      )}
    </div>
  );
}
