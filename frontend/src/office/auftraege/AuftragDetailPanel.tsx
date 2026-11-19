import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCheck, ChevronDown, ClipboardList, Clock, Folder, Pencil, Plus, Trash2 } from "lucide-react";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client";
import { auftraegeApi, kundenApi, projekteApi, vorgaengeApi, zeiterfassungApi } from "../../api/endpoints";
import { AktionsMenue } from "../../components/AktionsMenue";
import { EmptyState } from "../../components/EmptyState";
import { PulldownMenu } from "../../components/apple/PulldownMenu";
import { SeitenPanel } from "../../components/apple/SeitenPanel";
import { StatusPille } from "../../components/apple/StatusPille";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { SearchableSelect } from "../../components/SearchableSelect";
import { ZeitSummenBlock } from "../../components/ZeitSummenBlock";
import { VorgangStatusPille } from "../../components/VorgangStatusPille";
import { BezugAufgabenAbschnitt } from "../../pages/feld/aufgaben/BezugAufgabenAbschnitt";
import { ABSCHNITT_AKTION, Abschnitt } from "../../pages/feld/vorgang/Abschnitt";
import { CHIP_BUTTON, CHIP_NEUTRAL, ChipPopover } from "../../pages/feld/vorgang/VorgangKopf";
import type { Auftrag, AuftragStatus } from "../../types";
import { formatDatum } from "../../utils/format";
import { auftragStatusZuToken, istVorgangErledigt, projektLink } from "../../utils/verknuepfung";
import { AUFTRAG_STATUS_LABEL } from "./AuftraegeTabelle";

const AUFTRAG_STATUS_OPTIONEN: AuftragStatus[] = ["offen", "in_arbeit", "abgeschlossen", "storniert"];

/** Detailinhalt für das rechte SeitenPanel: Kopf nach Muster des Vorgangs (Pfad, Typ, Titel, Kunde, Chips,
 * Aktionen), darunter Vorgänge, Beschreibung und Details. Projekt wechselt der Chip, der Server zieht die
 * Vorgänge des Auftrags mit. */
export function AuftragDetailPanel({ auftrag, onClose }: { auftrag: Auftrag; onClose: () => void }) {
  const bestaetigen = useBestaetigung();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [titelBearbeiten, setTitelBearbeiten] = useState(false);
  const [titel, setTitel] = useState(auftrag.titel);
  const [beschreibungBearbeiten, setBeschreibungBearbeiten] = useState(false);
  const [beschreibung, setBeschreibung] = useState(auftrag.beschreibung ?? "");
  const [kundeBearbeiten, setKundeBearbeiten] = useState(false);

  const { data: geladen } = useQuery({
    queryKey: ["auftraege", auftrag.id],
    queryFn: () => auftraegeApi.get(auftrag.id),
    initialData: auftrag,
  });
  const aktuell = geladen ?? auftrag;

  const { data: projekte } = useQuery({ queryKey: ["projekte"], queryFn: () => projekteApi.list() });
  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list(), enabled: kundeBearbeiten });
  const { data: vorgaenge } = useQuery({
    queryKey: ["vorgaenge", "auftrag", auftrag.id],
    queryFn: () => vorgaengeApi.list({ auftrag_id: auftrag.id, limit: "200" }),
  });
  // Gleicher Schlüssel wie im ZeitSummenBlock unten, der Request wird geteilt.
  const { data: zeitSummen } = useQuery({
    queryKey: ["zeiterfassung-summen", { auftrag_id: auftrag.id }],
    queryFn: () => zeiterfassungApi.summen({ auftrag_id: auftrag.id }),
  });

  const aktualisieren = useMutation({
    mutationFn: (body: Parameters<typeof auftraegeApi.update>[1]) => auftraegeApi.update(auftrag.id, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auftraege"] });
      queryClient.invalidateQueries({ queryKey: ["vorgaenge"] });
      queryClient.invalidateQueries({ queryKey: ["projekte"] });
      setTitelBearbeiten(false);
      setBeschreibungBearbeiten(false);
      setKundeBearbeiten(false);
    },
  });

  const loeschen = useMutation({
    mutationFn: () => auftraegeApi.remove(auftrag.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["auftraege"] });
      onClose();
    },
  });

  const projektName = aktuell.projekt_name ?? projekte?.find((p) => p.id === aktuell.projekt_id)?.name ?? null;
  const gesamt = aktuell.vorgaenge_gesamt ?? vorgaenge?.length ?? 0;
  const erledigt = aktuell.vorgaenge_erledigt ?? vorgaenge?.filter((v) => istVorgangErledigt(v.status)).length ?? 0;
  const zeitStunden = zeitSummen
    ? Object.values(zeitSummen).reduce((summe, s) => summe + Number(s.arbeitszeit_stunden || 0), 0)
    : null;
  const fehler = aktualisieren.error instanceof ApiError ? aktualisieren.error.message : aktualisieren.isError ? "Speichern fehlgeschlagen." : null;

  const projektChipInhalt = (
    <>
      <Folder size={13} strokeWidth={1.5} aria-hidden="true" />
      <span className="text-label2">Projekt</span>
      <span className={projektName ? "" : "text-label2"}>{projektName ?? "Kein Projekt"}</span>
    </>
  );

  return (
    <SeitenPanel
      offen
      titel={aktuell.titel}
      onClose={onClose}
      aktionen={
        <AktionsMenue
          label="Weitere Aktionen"
          eintraege={[
            { label: "Titel bearbeiten", icon: Pencil, onClick: () => { setTitel(aktuell.titel); setTitelBearbeiten(true); } },
            "trenner",
            {
              label: "Auftrag löschen",
              icon: Trash2,
              destruktiv: true,
              disabled: loeschen.isPending,
              onClick: async () => {
                if (await bestaetigen({ titel: `Auftrag "${aktuell.titel}" löschen?`, bestaetigenLabel: "Löschen" })) {
                  loeschen.mutate();
                }
              },
            },
          ]}
        />
      }
    >
      <div className="space-y-4 p-4">
        <div className="space-y-2">
          {projektName && aktuell.projekt_id && (
            <button
              type="button"
              onClick={() => navigate(projektLink(aktuell.projekt_id!))}
              className="inline-flex items-center gap-1.5 text-sekundaer text-tint-text underline-offset-2 hover:underline"
            >
              <Folder size={13} strokeWidth={1.5} aria-hidden="true" />
              Projekt {projektName}
            </button>
          )}
          <div className="flex items-center gap-2">
            <span className="text-meta font-semibold tracking-wide text-label2 uppercase">Auftrag</span>
            <StatusPille status={auftragStatusZuToken(aktuell.status)} label={AUFTRAG_STATUS_LABEL[aktuell.status]} />
          </div>
          {titelBearbeiten ? (
            <div className="flex gap-2">
              <input
                aria-label="Titel"
                autoFocus
                value={titel}
                onChange={(e) => setTitel(e.target.value)}
                className="field-ap flex-1"
              />
              <button type="button" onClick={() => setTitelBearbeiten(false)} className="btn-touch btn-ap px-3 text-sekundaer">
                Abbrechen
              </button>
              <button
                type="button"
                disabled={!titel.trim() || aktualisieren.isPending}
                onClick={() => aktualisieren.mutate({ titel: titel.trim() })}
                className="btn-touch btn-ap-primary px-3 text-sekundaer"
              >
                Speichern
              </button>
            </div>
          ) : (
            <h1 className="font-heading text-titel-mobil font-bold text-label">{aktuell.titel}</h1>
          )}
          {aktuell.kunde_id && aktuell.kunde_name && (
            <button
              type="button"
              onClick={() => navigate(`/kunden/${aktuell.kunde_id}`)}
              className="block text-fliess text-tint-text underline-offset-2 hover:underline"
            >
              {aktuell.kunde_name}
            </button>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <ChipPopover
            label="Projekt ändern"
            chip={({ offen, toggeln }) => (
              <button type="button" onClick={toggeln} aria-haspopup="dialog" aria-expanded={offen} className={CHIP_BUTTON}>
                {projektChipInhalt}
                <ChevronDown size={13} strokeWidth={2} aria-hidden="true" />
              </button>
            )}
          >
            {(schliessen) => (
              <SearchableSelect
                value={aktuell.projekt_id ?? ""}
                onChange={(v) => {
                  aktualisieren.mutate({ projekt_id: v || null });
                  schliessen();
                }}
                placeholder="Projekt wählen…"
                options={[{ value: "", label: "Kein Projekt" }, ...(projekte ?? []).map((p) => ({ value: p.id, label: p.name }))]}
              />
            )}
          </ChipPopover>
          <span className={CHIP_NEUTRAL}>
            <CheckCheck size={13} strokeWidth={1.5} aria-hidden="true" />
            {erledigt} / {gesamt} Vorgänge erledigt
          </span>
          {zeitStunden != null && zeitStunden > 0 && (
            <span className={CHIP_NEUTRAL}>
              <Clock size={13} strokeWidth={1.5} aria-hidden="true" />
              <span className="text-label2">Zeit</span>
              {(Math.round(zeitStunden * 10) / 10).toLocaleString("de-DE")} h
            </span>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => navigate(`/neu?auftrag_id=${auftrag.id}`)}
            className="btn-touch btn-ap-primary inline-flex items-center gap-1.5 px-3 text-sekundaer"
          >
            <Plus size={14} strokeWidth={2.5} aria-hidden="true" /> Vorgang
          </button>
          <PulldownMenu
            ariaLabel="Status ändern"
            items={AUFTRAG_STATUS_OPTIONEN.map((s) => ({
              label: AUFTRAG_STATUS_LABEL[s],
              aktiv: s === aktuell.status,
              onSelect: () => aktualisieren.mutate({ status: s }),
            }))}
            trigger={({ offen, toggeln, triggerRef }) => (
              <button
                ref={triggerRef}
                type="button"
                onClick={toggeln}
                aria-haspopup="menu"
                aria-expanded={offen}
                className="btn-touch btn-ap inline-flex items-center gap-1.5 px-3 text-sekundaer"
              >
                Status ändern <ChevronDown size={13} strokeWidth={2} aria-hidden="true" />
              </button>
            )}
          />
        </div>

        {fehler && (
          <p role="alert" className="text-sekundaer text-st-fehlt">
            {fehler}
          </p>
        )}

        <Abschnitt
          titel="Vorgänge"
          aktion={
            <button type="button" onClick={() => navigate(`/neu?auftrag_id=${auftrag.id}`)} className={ABSCHNITT_AKTION}>
              + Vorgang
            </button>
          }
        >
          {!vorgaenge || vorgaenge.length === 0 ? (
            <EmptyState icon={ClipboardList} text="Noch kein Vorgang zugeordnet." />
          ) : (
            <ul className="divide-y-[0.5px] divide-sep">
              {vorgaenge.map((v) => (
                <li key={v.id}>
                  <button
                    type="button"
                    onClick={() => navigate(`/vorgaenge/${v.id}/vollbild`)}
                    className="flex w-full items-center gap-3 py-2 text-left text-fliess hover:bg-fill"
                  >
                    <span className="shrink-0 text-label2">{v.vorgangsnummer}</span>
                    <span className="min-w-0 flex-1 truncate text-label">{v.titel}</span>
                    <span className="hidden shrink-0 text-sekundaer text-label2 sm:inline">{v.zugewiesener_name ?? "—"}</span>
                    <VorgangStatusPille status={v.status} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </Abschnitt>

        <BezugAufgabenAbschnitt auftragId={auftrag.id} />

        <Abschnitt
          titel="Beschreibung"
          aktion={
            !beschreibungBearbeiten ? (
              <button
                type="button"
                onClick={() => {
                  setBeschreibung(aktuell.beschreibung ?? "");
                  setBeschreibungBearbeiten(true);
                }}
                className={ABSCHNITT_AKTION}
              >
                Bearbeiten
              </button>
            ) : undefined
          }
        >
          {beschreibungBearbeiten ? (
            <div className="space-y-2">
              <textarea aria-label="Beschreibung" value={beschreibung} onChange={(e) => setBeschreibung(e.target.value)} rows={4} className="field-ap" />
              <div className="flex justify-end gap-2">
                <button type="button" onClick={() => setBeschreibungBearbeiten(false)} className="btn-touch btn-ap px-3 text-sekundaer">
                  Abbrechen
                </button>
                <button
                  type="button"
                  disabled={aktualisieren.isPending}
                  onClick={() => aktualisieren.mutate({ beschreibung: beschreibung.trim() })}
                  className="btn-touch btn-ap-primary px-3 text-sekundaer"
                >
                  Speichern
                </button>
              </div>
            </div>
          ) : aktuell.beschreibung ? (
            <p className="whitespace-pre-line text-fliess text-label">{aktuell.beschreibung}</p>
          ) : (
            <p className="text-fliess text-label2">Keine Beschreibung.</p>
          )}
        </Abschnitt>

        <Abschnitt
          titel="Details"
          aktion={
            !kundeBearbeiten ? (
              <button type="button" onClick={() => setKundeBearbeiten(true)} className={ABSCHNITT_AKTION}>
                Kunde ändern
              </button>
            ) : undefined
          }
        >
          {kundeBearbeiten ? (
            <div className="space-y-2">
              <SearchableSelect
                value={aktuell.kunde_id ?? ""}
                onChange={(v) => aktualisieren.mutate({ kunde_id: v || null })}
                placeholder="Kein Kunde"
                options={[{ value: "", label: "Kein Kunde" }, ...(kunden ?? []).map((k) => ({ value: k.id, label: k.name }))]}
              />
              <div className="flex justify-end">
                <button type="button" onClick={() => setKundeBearbeiten(false)} className="btn-touch btn-ap px-3 text-sekundaer">
                  Abbrechen
                </button>
              </div>
            </div>
          ) : (
            <dl className="space-y-1.5 text-fliess">
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-label2">Kunde</dt>
                <dd className="text-right font-medium text-label">{aktuell.kunde_name ?? "—"}</dd>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-label2">Erstellt am</dt>
                <dd className="text-right font-medium text-label">{formatDatum(aktuell.created_at)}</dd>
              </div>
            </dl>
          )}
        </Abschnitt>

        <ZeitSummenBlock filter={{ auftrag_id: auftrag.id }} />
      </div>
    </SeitenPanel>
  );
}
