import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronRight, ClipboardList, Copy, Plus, Settings2, X } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { kundenApi, leistungsverzeichnisseApi, mandantEinstellungenApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { EmptyState } from "../../components/EmptyState";
import { SearchableSelect } from "../../components/SearchableSelect";
import { useAuth } from "../../context/AuthContext";
import type { Leistungsverzeichnis } from "../../types";

/** Mehrfachauswahl von Kunden -- SearchableSelect kennt nur Einzelauswahl,
 * deshalb hier: gewaehlte Kunden als entfernbare Chips, darunter dieselbe
 * SearchableSelect zum Hinzufuegen eines weiteren. Leer = gilt fuer alle
 * Kunden. Auch von LeistungsverzeichnisDetailPage.tsx verwendet. */
export function KundenZuweisung({ kundenIds, onChange }: { kundenIds: string[]; onChange: (ids: string[]) => void }) {
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

function LvFormular({ onClose }: { onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [kundenIds, setKundenIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const erstellen = useMutation({
    mutationFn: () =>
      leistungsverzeichnisseApi.create({ name, beschreibung: beschreibung || undefined, kunden_ids: kundenIds }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["leistungsverzeichnisse"] });
      onClose();
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Leistungsverzeichnis konnte nicht angelegt werden"),
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/35 p-4" onClick={onClose}>
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-h-full w-full max-w-md overflow-y-auto rounded-xl border border-slate-200 bg-white dark:border-stone-800 dark:bg-stone-900"
      >
        <div className="flex items-center justify-between gap-3 border-b border-slate-100 px-5 py-4 dark:border-stone-800">
          <h2 className="text-base font-bold text-ind-ink">Neues Leistungsverzeichnis</h2>
          <button
            onClick={onClose}
            className="btn-touch flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 dark:text-stone-500 dark:hover:bg-stone-800"
          >
            <X size={16} strokeWidth={2} />
          </button>
        </div>
        <div className="space-y-4 px-5 py-4">
          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
              Name
            </label>
            <input
              autoFocus
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="z. B. Wartungsvertraege, Standardleistungen"
              className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-slate-400 uppercase dark:text-stone-500">
              Beschreibung
            </label>
            <textarea
              value={beschreibung}
              onChange={(e) => setBeschreibung(e.target.value)}
              rows={2}
              className="w-full resize-none border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
          </div>
          <KundenZuweisung kundenIds={kundenIds} onChange={setKundenIds} />
          {error && <p className="text-sm text-red-700 dark:text-red-400">{error}</p>}
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-100 px-5 py-4 dark:border-stone-800">
          <button onClick={onClose} className="btn-touch btn-industry btn-industry-secondary px-4 py-2 text-sm font-semibold">
            Abbrechen
          </button>
          <button
            onClick={() => erstellen.mutate()}
            disabled={!name.trim() || erstellen.isPending}
            className="btn-touch btn-clay rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-semibold text-white disabled:opacity-50"
          >
            Anlegen
          </button>
        </div>
      </div>
    </div>
  );
}

function LvZeile({ lv, kannVerwalten }: { lv: Leistungsverzeichnis; kannVerwalten: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: kunden } = useQuery({
    queryKey: ["kunden-alle"],
    queryFn: () => kundenApi.list(),
    enabled: lv.kunden_ids.length > 0,
  });
  const kundenBadge =
    lv.kunden_ids.length === 0
      ? "Alle Kunden"
      : lv.kunden_ids.length === 1
        ? (kunden?.find((k) => k.id === lv.kunden_ids[0])?.name ?? "1 Kunde")
        : `${lv.kunden_ids.length} Kunden`;

  const duplizieren = useMutation({
    mutationFn: () => leistungsverzeichnisseApi.duplizieren(lv.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["leistungsverzeichnisse"] }),
  });

  return (
    <div className="card-interactive flex items-center gap-2 rounded-lg bg-white p-3 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
      <button onClick={() => navigate(`/leistungsverzeichnis/${lv.id}`)} className="min-w-0 flex-1 text-left">
        <p className="truncate text-sm font-semibold text-ind-ink">{lv.name}</p>
        <p className="truncate text-xs text-ind-ink-3">
          {lv.beschreibung && <span>{lv.beschreibung} · </span>}
          <span
            className={
              lv.kunden_ids.length === 0
                ? "text-ind-ink-3"
                : "font-medium text-violet-700 dark:text-violet-300"
            }
          >
            {kundenBadge}
          </span>
        </p>
      </button>
      {kannVerwalten && (
        <button
          onClick={() => duplizieren.mutate()}
          disabled={duplizieren.isPending}
          title="Duplizieren"
          className="btn-touch flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 disabled:opacity-50 dark:text-stone-500 dark:hover:bg-stone-800"
        >
          <Copy size={15} strokeWidth={2} />
        </button>
      )}
      <button
        onClick={() => navigate(`/leistungsverzeichnis/${lv.id}`)}
        className="btn-touch flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-slate-400 dark:text-stone-500"
      >
        <ChevronRight size={16} strokeWidth={2} />
      </button>
    </div>
  );
}

function StandardKalkulation() {
  const queryClient = useQueryClient();
  const { data: einstellungen } = useQuery({
    queryKey: ["mandant-einstellungen"],
    queryFn: mandantEinstellungenApi.get,
  });
  const [offen, setOffen] = useState(false);
  const [gemeinkosten, setGemeinkosten] = useState(einstellungen?.standard_lohn_gemeinkosten_prozent ?? "0");
  const [gewinnWagnis, setGewinnWagnis] = useState(einstellungen?.standard_gewinn_wagnis_prozent ?? "0");

  const speichern = useMutation({
    mutationFn: () =>
      mandantEinstellungenApi.update({
        standard_lohn_gemeinkosten_prozent: gemeinkosten,
        standard_gewinn_wagnis_prozent: gewinnWagnis,
      }),
    onSuccess: (daten) => {
      queryClient.setQueryData(["mandant-einstellungen"], daten);
      setOffen(false);
    },
  });

  if (!einstellungen) return null;

  return (
    <div className="rounded-lg border border-slate-200 bg-white dark:border-stone-800 dark:bg-stone-900">
      <button
        onClick={() => {
          setGemeinkosten(einstellungen.standard_lohn_gemeinkosten_prozent);
          setGewinnWagnis(einstellungen.standard_gewinn_wagnis_prozent);
          setOffen((v) => !v);
        }}
        className="btn-touch flex w-full items-center gap-2 px-3 py-2.5 text-left"
      >
        <Settings2 size={15} strokeWidth={2} className="shrink-0 text-slate-400 dark:text-stone-500" />
        <span className="flex-1 text-xs font-semibold text-ind-ink-2">
          Standard-Kalkulation für neue Positionen
        </span>
        <span className="text-xs text-ind-ink-3">
          Gemeinkosten {einstellungen.standard_lohn_gemeinkosten_prozent}% · Gewinn/Wagnis{" "}
          {einstellungen.standard_gewinn_wagnis_prozent}%
        </span>
      </button>
      {offen && (
        <div className="space-y-3 border-t border-slate-100 px-3 py-3 dark:border-stone-800">
          <p className="text-xs text-ind-ink-3">
            Vorbelegung für neu angelegte Positionen im Modus "Berechnet". Gilt nicht rückwirkend für bereits
            angelegte Positionen.
          </p>
          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="mb-1 block text-[10.5px] font-medium text-ind-ink-3">
                Lohn-Gemeinkosten (%)
              </label>
              <input
                type="number"
                step="0.1"
                value={gemeinkosten}
                onChange={(e) => setGemeinkosten(e.target.value)}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
            </div>
            <div>
              <label className="mb-1 block text-[10.5px] font-medium text-ind-ink-3">Gewinn/Wagnis (%)</label>
              <input
                type="number"
                step="0.1"
                value={gewinnWagnis}
                onChange={(e) => setGewinnWagnis(e.target.value)}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
            </div>
          </div>
          <button
            onClick={() => speichern.mutate()}
            disabled={speichern.isPending}
            className="btn-touch btn-clay rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-1.5 text-xs font-semibold text-white disabled:opacity-50"
          >
            Speichern
          </button>
        </div>
      )}
    </div>
  );
}

/** Uebersichtsseite: Liste aller Leistungsverzeichnisse eines Mandanten.
 * Ein LV buendelt Positionen/Unterpunkte (siehe
 * LeistungsverzeichnisDetailPage.tsx) und traegt selbst die
 * Kunden-Zuweisung -- eine Position kennt ihren Kunden nur noch indirekt
 * ueber ihr LV (siehe app/models/leistungsverzeichnis.py). */
export function LeistungsverzeichnisPage() {
  const { hatRecht } = useAuth();
  const kannVerwalten = hatRecht("kunden", "bearbeiten");
  const [neuesLv, setNeuesLv] = useState(false);

  const { data: lvs, isLoading } = useQuery({
    queryKey: ["leistungsverzeichnisse"],
    queryFn: () => leistungsverzeichnisseApi.list(),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-ind-ink">Leistungsverzeichnisse</h1>
        {kannVerwalten && (
          <button
            onClick={() => setNeuesLv(true)}
            className="btn-touch flex items-center gap-1.5 rounded-lg btn-industry btn-industry-primary px-3 py-2 text-xs font-semibold"
          >
            <Plus size={14} strokeWidth={2.5} />
            Neues Leistungsverzeichnis
          </button>
        )}
      </div>

      {kannVerwalten && <StandardKalkulation />}

      {isLoading ? (
        <p className="py-10 text-center text-sm text-ind-ink-3">Lädt…</p>
      ) : !lvs || lvs.length === 0 ? (
        <EmptyState icon={ClipboardList} text="Noch keine Leistungsverzeichnisse angelegt." />
      ) : (
        <div className="space-y-2">
          {lvs.map((lv) => (
            <LvZeile key={lv.id} lv={lv} kannVerwalten={kannVerwalten} />
          ))}
        </div>
      )}

      {neuesLv && <LvFormular onClose={() => setNeuesLv(false)} />}
    </div>
  );
}
