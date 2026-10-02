import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Trash2 } from "lucide-react";
import { useState } from "react";

import { ApiError } from "../../../api/client";
import { projektVorlagenApi, zeitplanApi } from "../../../api/endpoints";
import { GroupedList, GroupedListRow } from "../../../components/apple/GroupedList";
import { Sheet } from "../../../components/apple/Sheet";
import { SearchableSelect } from "../../../components/SearchableSelect";
import type { Zeitplan, ZeitplanElement } from "../../../types";
import { formatBereich, formatStraffenDelta, heuteTag, parseTag, standardBasisplanName, standardVorlagenStart } from "./zeitplanLogik";

function fehlerText(e: unknown): string {
  return e instanceof ApiError ? e.message : "Die Aktion ist fehlgeschlagen.";
}

function Fehler({ text }: { text: string | null }) {
  if (!text) return null;
  return (
    <div role="alert" className="rounded-[10px] bg-st-fehlt-bg px-3 py-2 text-sm text-st-fehlt">
      {text}
    </div>
  );
}

function Abbrechen({ onClose }: { onClose: () => void }) {
  return (
    <button type="button" onClick={onClose} className="text-[17px] text-tint-text">
      Abbrechen
    </button>
  );
}

function Aktion({ label, onClick, disabled }: { label: string; onClick: () => void; disabled?: boolean }) {
  return (
    <button type="button" onClick={onClick} disabled={disabled} className="text-[17px] font-semibold text-tint-text disabled:opacity-40">
      {label}
    </button>
  );
}

function datumDe(iso: string): string {
  return new Date(iso).toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" });
}

// --- Basisplan speichern ---------------------------------------------------------------

export function BasisplanSpeichernSheet({ projektId, onClose }: { projektId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(() => standardBasisplanName(heuteTag()));
  const speichern = useMutation({
    mutationFn: () => zeitplanApi.createBasisplan(projektId, name.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projekt-basisplaene", projektId] });
      onClose();
    },
  });
  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Basisplan speichern"
      links={<Abbrechen onClose={onClose} />}
      rechts={<Aktion label="Speichern" onClick={() => speichern.mutate()} disabled={!name.trim() || speichern.isPending} />}
    >
      <form
        className="space-y-3 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim() && !speichern.isPending) speichern.mutate();
        }}
      >
        <p className="text-sm text-label2">Hält den aktuellen Stand aller Termine als Referenz fest. Spätere Verschiebungen lassen sich dagegen vergleichen.</p>
        <label className="block text-sm text-label2">
          Name
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className="field-ap mt-1" />
        </label>
        <Fehler text={speichern.error ? fehlerText(speichern.error) : null} />
      </form>
    </Sheet>
  );
}

// --- Basispläne verwalten --------------------------------------------------------------

export function BasisplaeneVerwaltenSheet({
  projektId,
  onClose,
  onGeloescht,
}: {
  projektId: string;
  onClose: () => void;
  onGeloescht: (id: string) => void;
}) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["projekt-basisplaene", projektId], queryFn: () => zeitplanApi.basisplaene(projektId) });
  const loeschen = useMutation({
    mutationFn: (id: string) => zeitplanApi.removeBasisplan(projektId, id),
    onSuccess: (_r, id) => {
      queryClient.invalidateQueries({ queryKey: ["projekt-basisplaene", projektId] });
      onGeloescht(id);
    },
  });
  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Basispläne verwalten"
      rechts={
        <button type="button" onClick={onClose} className="text-[17px] font-semibold text-tint-text">
          Fertig
        </button>
      }
    >
      <div className="space-y-3 p-4">
        {isLoading && <p className="text-sm text-label2">Wird geladen …</p>}
        {data && data.length === 0 && <p className="text-sm text-label2">Noch kein Basisplan gespeichert.</p>}
        {data && data.length > 0 && (
          <GroupedList>
            {data.map((b, i) => (
              <GroupedListRow key={b.id} last={i === data.length - 1}>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[17px] text-label">{b.name}</p>
                  <p className="truncate text-[13px] text-label2">
                    {datumDe(b.erstellt_am)}
                    {b.erstellt_von_name ? ` · ${b.erstellt_von_name}` : ""} · {b.anzahl_elemente} Elemente
                  </p>
                </div>
                <button
                  type="button"
                  aria-label={`Basisplan ${b.name} löschen`}
                  disabled={loeschen.isPending}
                  onClick={() => {
                    if (window.confirm(`Basisplan „${b.name}“ wirklich löschen?`)) loeschen.mutate(b.id);
                  }}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] text-st-fehlt hover:bg-st-fehlt-bg"
                >
                  <Trash2 size={16} strokeWidth={2} aria-hidden="true" />
                </button>
              </GroupedListRow>
            ))}
          </GroupedList>
        )}
        <Fehler text={loeschen.error ? fehlerText(loeschen.error) : null} />
      </div>
    </Sheet>
  );
}

// --- Plan straffen ---------------------------------------------------------------------

/** Zweistufig: Auswahl des Umfangs loest sofort den Vorschau-Aufruf aus (vorschau=true, aendert
 * nichts), "Übernehmen" wiederholt ihn mit vorschau=false und liefert den neuen Zeitplan. */
export function StraffenSheet({
  projektId,
  phasen,
  onClose,
  onUebernommen,
}: {
  projektId: string;
  phasen: ZeitplanElement[];
  onClose: () => void;
  onUebernommen: (zp: Zeitplan) => void;
}) {
  const [phaseId, setPhaseId] = useState("");
  const vorschau = useQuery({
    queryKey: ["zeitplan-straffen-vorschau", projektId, phaseId],
    queryFn: () => zeitplanApi.straffen(projektId, { phase_id: phaseId || null, vorschau: true }),
    gcTime: 0,
    staleTime: 0,
    refetchOnWindowFocus: false,
    retry: false,
  });
  const uebernehmen = useMutation({
    mutationFn: () => zeitplanApi.straffen(projektId, { phase_id: phaseId || null, vorschau: false }),
    onSuccess: (antwort) => {
      if (antwort.zeitplan) onUebernommen(antwort.zeitplan);
      onClose();
    },
  });
  const aenderungen = vorschau.data?.aenderungen ?? [];
  const optionen = [{ value: "", label: "Ganzes Projekt" }, ...phasen.map((p) => ({ value: p.id, label: `Nur Phase „${p.titel}“` }))];

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Plan straffen"
      links={<Abbrechen onClose={onClose} />}
      rechts={<Aktion label="Übernehmen" onClick={() => uebernehmen.mutate()} disabled={aenderungen.length === 0 || vorschau.isFetching || uebernehmen.isPending} />}
    >
      <div className="space-y-3 p-4">
        <p className="text-sm text-label2">Zieht Schritte auf den frühesten Termin, den ihre Vorgänger zulassen. Vorab siehst du, was sich ändern würde.</p>
        <SearchableSelect value={phaseId} onChange={setPhaseId} options={optionen} placeholder="Ganzes Projekt" />

        {vorschau.isFetching && <p className="text-sm text-label2">Vorschau wird berechnet …</p>}
        {!vorschau.isFetching && vorschau.data && aenderungen.length === 0 && (
          <p className="rounded-[10px] bg-fill px-3 py-3 text-sm text-label">Nichts zu straffen – alle Schritte liegen bereits auf dem frühesten Termin.</p>
        )}
        {!vorschau.isFetching && aenderungen.length > 0 && (
          <>
            <p className="text-[13px] font-semibold text-label2">
              {aenderungen.length} {aenderungen.length === 1 ? "Änderung" : "Änderungen"}
            </p>
            <GroupedList>
              {aenderungen.map((a, i) => (
                <GroupedListRow key={a.element_id} last={i === aenderungen.length - 1}>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-[15px] text-label">{a.titel}</p>
                    <p className="text-[13px] text-label2 tabular-nums">
                      {formatBereich(a.alt_start_am, a.alt_ende_am)} → {formatBereich(a.neu_start_am, a.neu_ende_am)}
                    </p>
                  </div>
                  <span className="shrink-0 rounded-full bg-st-erledigt-bg px-2 py-0.5 text-[12px] font-semibold text-st-erledigt tabular-nums">{formatStraffenDelta(a)}</span>
                </GroupedListRow>
              ))}
            </GroupedList>
          </>
        )}
        <Fehler text={vorschau.error ? fehlerText(vorschau.error) : uebernehmen.error ? fehlerText(uebernehmen.error) : null} />
      </div>
    </Sheet>
  );
}

// --- Aus Vorlage einfügen --------------------------------------------------------------

export function VorlageEinfuegenSheet({
  projektId,
  elemente,
  onClose,
  onAngewendet,
}: {
  projektId: string;
  elemente: ZeitplanElement[];
  onClose: () => void;
  onAngewendet: (zp: Zeitplan) => void;
}) {
  const { data: vorlagen, isLoading, error } = useQuery({ queryKey: ["projekt-vorlagen"], queryFn: projektVorlagenApi.list });
  const [vorlageId, setVorlageId] = useState<string | null>(null);
  const [start, setStart] = useState(() => standardVorlagenStart(elemente, heuteTag()));
  const anwenden = useMutation({
    mutationFn: () => zeitplanApi.vorlageAnwenden(projektId, { vorlage_id: vorlageId!, start_am: start }),
    onSuccess: (zp) => {
      onAngewendet(zp);
      onClose();
    },
  });
  const gueltigerStart = /^\d{4}-\d{2}-\d{2}$/.test(start) && !Number.isNaN(parseTag(start));

  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Aus Vorlage einfügen"
      links={<Abbrechen onClose={onClose} />}
      rechts={<Aktion label="Einfügen" onClick={() => anwenden.mutate()} disabled={!vorlageId || !gueltigerStart || anwenden.isPending} />}
    >
      <div className="space-y-4 p-4">
        {isLoading && <p className="text-sm text-label2">Vorlagen werden geladen …</p>}
        {error && <Fehler text="Vorlagen konnten nicht geladen werden." />}
        {vorlagen && vorlagen.length === 0 && (
          <p className="rounded-[10px] bg-fill px-3 py-3 text-sm text-label2">
            Noch keine Vorlagen. Speichere einen bestehenden Zeitplan über „Als Vorlage speichern …“.
          </p>
        )}
        {vorlagen && vorlagen.length > 0 && (
          <GroupedList>
            {vorlagen.map((v, i) => (
              <GroupedListRow key={v.id} onClick={() => setVorlageId(v.id)} last={i === vorlagen.length - 1}>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-[17px] text-label">{v.name}</p>
                  {v.beschreibung && <p className="truncate text-[13px] text-label2">{v.beschreibung}</p>}
                  <p className="text-[13px] text-label2">
                    {v.anzahl_elemente} Schritte · {v.dauer_tage} Tage
                  </p>
                </div>
                <span
                  aria-hidden="true"
                  className={`h-5 w-5 shrink-0 rounded-full border-2 ${vorlageId === v.id ? "border-tint bg-tint-solid shadow-[inset_0_0_0_3px_var(--card)]" : "border-label3"}`}
                />
                <span className="sr-only">{vorlageId === v.id ? "Ausgewählt" : "Nicht ausgewählt"}</span>
              </GroupedListRow>
            ))}
          </GroupedList>
        )}
        <label className="block text-sm text-label2">
          Startdatum
          <input type="date" value={start} onChange={(e) => setStart(e.target.value)} className="field-ap mt-1" />
        </label>
        <Fehler text={anwenden.error ? fehlerText(anwenden.error) : null} />
      </div>
    </Sheet>
  );
}

// --- Als Vorlage speichern -------------------------------------------------------------

export function VorlageSpeichernSheet({ projektId, onClose }: { projektId: string; onClose: () => void }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const speichern = useMutation({
    mutationFn: () => projektVorlagenApi.ausProjekt(projektId, { name: name.trim(), beschreibung: beschreibung.trim() || null }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projekt-vorlagen"] });
      onClose();
    },
  });
  return (
    <Sheet
      offen
      onClose={onClose}
      titel="Als Vorlage speichern"
      links={<Abbrechen onClose={onClose} />}
      rechts={<Aktion label="Speichern" onClick={() => speichern.mutate()} disabled={!name.trim() || speichern.isPending} />}
    >
      <form
        className="space-y-3 p-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (name.trim() && !speichern.isPending) speichern.mutate();
        }}
      >
        <p className="text-sm text-label2">Übernimmt Phasen, Schritte, Meilensteine und Verbindungen als relative Termine (Tage ab Start).</p>
        <label className="block text-sm text-label2">
          Name
          <input autoFocus value={name} onChange={(e) => setName(e.target.value)} maxLength={120} className="field-ap mt-1" />
        </label>
        <label className="block text-sm text-label2">
          Beschreibung (optional)
          <textarea value={beschreibung} onChange={(e) => setBeschreibung(e.target.value)} rows={3} className="field-ap mt-1" />
        </label>
        <Fehler text={speichern.error ? fehlerText(speichern.error) : null} />
      </form>
    </Sheet>
  );
}
