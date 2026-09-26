import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Link2, MapPin, Plus, Users, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import {
  anlagenApi,
  kundenApi,
  projektAufgabenApi,
  standorteApi,
  usersApi,
  vorgaengeApi,
} from "../../api/endpoints";
import { SearchableSelect } from "../../components/SearchableSelect";
import { SymbolKachel, type KachelFarbe } from "../../components/apple/SymbolKachel";
import type { ChecklistenPunkt, ProjektAufgabe, ProjektAufgabePrioritaet, ProjektSpalte } from "../../types";

const PRIORITAET_OPTIONEN: { wert: ProjektAufgabePrioritaet; label: string }[] = [
  { wert: "niedrig", label: "Niedrig" },
  { wert: "mittel", label: "Mittel" },
  { wert: "hoch", label: "Hoch" },
];

const PRIORITAET_AKTIV_KLASSE: Record<ProjektAufgabePrioritaet, string> = {
  niedrig: "bg-card text-label shadow-[0_1px_3px_rgba(0,0,0,.12)]",
  mittel: "bg-card text-st-arbeit shadow-[0_1px_3px_rgba(0,0,0,.12)]",
  hoch: "bg-card text-st-fehlt shadow-[0_1px_3px_rgba(0,0,0,.12)]",
};

/** Kompakte Verknuepfungszeile fuer Vorgang/Anlage/Kunde/Standort -- zeigt
 * entweder die gewaehlte Verknuepfung als Chip (mit Klick zum Navigieren)
 * oder eine SearchableSelect zum Aendern. Rein referenziell, kein
 * Status-Sync in irgendeine Richtung. */
function VerknuepfungsZeile({
  icon: Icon,
  farbe,
  label,
  anzeige,
  onEntfernen,
  route,
  navigate,
  suchOptionen,
  onWaehlen,
  platzhalter,
  extraAktion,
}: {
  icon: typeof Link2;
  farbe: KachelFarbe;
  label: string;
  anzeige: string | null | undefined;
  onEntfernen: () => void;
  route: string | null;
  navigate: (route: string) => void;
  suchOptionen: { value: string; label: string }[];
  onWaehlen: (id: string) => void;
  platzhalter: string;
  extraAktion?: ReactNode;
}) {
  return (
    <div>
      <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">{label}</label>
      {anzeige ? (
        <div className="flex items-center gap-2.5 rounded-md bg-fill px-2.5 py-2">
          <SymbolKachel icon={Icon} farbe={farbe} groesse={26} />
          <button
            onClick={() => route && navigate(route)}
            disabled={!route}
            className="min-w-0 flex-1 truncate text-left text-xs font-bold text-label"
          >
            {anzeige}
          </button>
          <button
            onClick={onEntfernen}
            title="Verknüpfung entfernen"
            className="shrink-0 rounded-md p-1 text-label3 hover:bg-card"
          >
            <X size={14} strokeWidth={2} aria-hidden="true" />
          </button>
        </div>
      ) : (
        <>
          <SearchableSelect value="" onChange={onWaehlen} placeholder={platzhalter} options={suchOptionen} />
          {extraAktion}
        </>
      )}
    </div>
  );
}

/** Neu-Anlage (aufgabe=null) und Bearbeiten teilen sich dieses Panel --
 * unterscheiden sich nur im Titel/Speichern-Verhalten und darin, dass beim
 * Bearbeiten zusaetzlich "Loeschen" und (fuer eigenstaendige Aufgaben) die
 * Unteraufgaben-Liste erscheinen. projektId fehlt -> private Aufgabe (kein
 * Kanban-Board, keine Spalte -- siehe app/models/projekt.py). */
export function ProjektAufgabeDetailPanel({
  projektId,
  spalten,
  aufgabe,
  vorbelegteSpalteId,
  vorbelegteElternId,
  onClose,
}: {
  projektId?: string;
  spalten: ProjektSpalte[];
  aufgabe: ProjektAufgabe | null;
  vorbelegteSpalteId?: string;
  vorbelegteElternId?: string;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const istNeu = aufgabe === null;
  const istPrivat = !projektId;
  const istEigenstaendig = !(aufgabe?.eltern_aufgabe_id ?? vorbelegteElternId);

  const [titel, setTitel] = useState(aufgabe?.titel ?? "");
  const [beschreibung, setBeschreibung] = useState(aufgabe?.beschreibung ?? "");
  const [spalteId, setSpalteId] = useState(aufgabe?.spalte_id ?? vorbelegteSpalteId ?? spalten[0]?.id ?? "");
  const [faelligkeitAm, setFaelligkeitAm] = useState(aufgabe?.faelligkeit_am ?? "");
  const [prioritaet, setPrioritaet] = useState<ProjektAufgabePrioritaet>(aufgabe?.prioritaet ?? "mittel");
  const [zugewiesenAn, setZugewiesenAn] = useState(aufgabe?.zugewiesen_an ?? "");
  const [erledigt, setErledigt] = useState(!!aufgabe?.erledigt_am);
  const [vorgangId, setVorgangId] = useState(aufgabe?.vorgang_id ?? "");
  const [anlageId, setAnlageId] = useState(aufgabe?.anlage_id ?? "");
  const [kundeId, setKundeId] = useState(aufgabe?.kunde_id ?? "");
  const [standortId, setStandortId] = useState(aufgabe?.standort_id ?? "");
  const [checkliste, setCheckliste] = useState<ChecklistenPunkt[]>(aufgabe?.checkliste ?? []);
  const [neuerPunkt, setNeuerPunkt] = useState("");
  const [neueUnteraufgabe, setNeueUnteraufgabe] = useState("");

  const { data: users } = useQuery({ queryKey: ["users"], queryFn: () => usersApi.list() });
  const { data: alleVorgaenge } = useQuery({ queryKey: ["vorgaenge-alle"], queryFn: () => vorgaengeApi.list() });
  const { data: alleKunden } = useQuery({ queryKey: ["kunden-alle"], queryFn: () => kundenApi.list() });
  const { data: alleAnlagen } = useQuery({ queryKey: ["anlagen-alle"], queryFn: () => anlagenApi.list() });
  const { data: alleStandorte } = useQuery({ queryKey: ["standorte-alle"], queryFn: () => standorteApi.list() });
  const { data: verknuepfterVorgang } = useQuery({
    queryKey: ["vorgang", vorgangId],
    queryFn: () => vorgaengeApi.get(vorgangId),
    enabled: !!vorgangId && vorgangId !== aufgabe?.vorgang_id,
  });
  const { data: verknuepfterKunde } = useQuery({
    queryKey: ["kunde", verknuepfterVorgang?.kunde_id],
    queryFn: () => kundenApi.get(verknuepfterVorgang!.kunde_id),
    enabled: !!verknuepfterVorgang?.kunde_id,
  });
  const { data: unteraufgaben } = useQuery({
    queryKey: ["projekt-aufgaben", "unteraufgaben", aufgabe?.id],
    queryFn: () => projektAufgabenApi.list({ eltern_aufgabe_id: aufgabe!.id }),
    enabled: !istNeu && istEigenstaendig,
  });

  const vorgangAnzeige =
    vorgangId === aufgabe?.vorgang_id
      ? (aufgabe?.vorgang_vorgangsnummer ?? null)
      : (alleVorgaenge?.find((v) => v.id === vorgangId)?.vorgangsnummer ?? null);
  const kundeAnzeige =
    kundeId === aufgabe?.kunde_id ? aufgabe?.kunde_name : alleKunden?.find((k) => k.id === kundeId)?.name;
  const anlageAnzeige =
    anlageId === aufgabe?.anlage_id
      ? aufgabe?.anlage_name
      : alleAnlagen?.find((a) => a.id === anlageId)?.bezeichnung;
  const standortAnzeige =
    standortId === aufgabe?.standort_id
      ? aufgabe?.standort_name
      : alleStandorte?.find((s) => s.id === standortId)?.bezeichnung;
  const vorgangVorschau = vorgangAnzeige
    ? verknuepfterKunde?.name || aufgabe?.vorgang_kunde_name
      ? `${vorgangAnzeige} · ${verknuepfterKunde?.name ?? aufgabe?.vorgang_kunde_name}`
      : vorgangAnzeige
    : null;

  const invalidateBoard = () => {
    queryClient.invalidateQueries({ queryKey: ["projekt-aufgaben"] });
  };

  const speichern = useMutation({
    mutationFn: () => {
      const body = {
        spalte_id: istPrivat ? undefined : spalteId || undefined,
        titel,
        beschreibung: beschreibung || undefined,
        faelligkeit_am: faelligkeitAm || null,
        prioritaet,
        zugewiesen_an: zugewiesenAn || null,
        erledigt,
        vorgang_id: vorgangId || null,
        anlage_id: anlageId || null,
        kunde_id: kundeId || null,
        standort_id: standortId || null,
        checkliste,
      };
      return istNeu
        ? projektAufgabenApi.create({
            projekt_id: projektId,
            eltern_aufgabe_id: vorbelegteElternId,
            ...body,
          })
        : projektAufgabenApi.update(aufgabe!.id, body);
    },
    onSuccess: () => {
      invalidateBoard();
      onClose();
    },
  });

  const loeschen = useMutation({
    mutationFn: () => projektAufgabenApi.remove(aufgabe!.id),
    onSuccess: () => {
      invalidateBoard();
      onClose();
    },
  });

  const unteraufgabeErstellen = useMutation({
    mutationFn: (titelText: string) =>
      projektAufgabenApi.create({
        projekt_id: aufgabe?.projekt_id ?? undefined,
        eltern_aufgabe_id: aufgabe!.id,
        titel: titelText,
      }),
    onSuccess: () => {
      setNeueUnteraufgabe("");
      queryClient.invalidateQueries({ queryKey: ["projekt-aufgaben", "unteraufgaben", aufgabe?.id] });
      invalidateBoard();
    },
  });

  const unteraufgabeUmschalten = useMutation({
    mutationFn: ({ id, erledigt: neu }: { id: string; erledigt: boolean }) =>
      projektAufgabenApi.update(id, { erledigt: neu }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projekt-aufgaben", "unteraufgaben", aufgabe?.id] });
      invalidateBoard();
    },
  });

  const unteraufgabeLoeschen = useMutation({
    mutationFn: (id: string) => projektAufgabenApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["projekt-aufgaben", "unteraufgaben", aufgabe?.id] });
      invalidateBoard();
    },
  });

  const checklistePunktHinzufuegen = () => {
    if (!neuerPunkt.trim()) return;
    setCheckliste((bisher) => [...bisher, { text: neuerPunkt.trim(), erledigt: false }]);
    setNeuerPunkt("");
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/35 p-6"
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="max-h-full w-full max-w-xl overflow-y-auto rounded-xl border-[0.5px] border-sepstrong bg-card"
      >
        <div className="flex items-start justify-between gap-3 border-b-[0.5px] border-sep px-5 py-4">
          <div className="flex flex-1 items-start gap-2.5">
            {!istNeu && (
              <input
                type="checkbox"
                checked={erledigt}
                onChange={(e) => setErledigt(e.target.checked)}
                title="Als erledigt markieren"
                className="mt-1.5 h-4 w-4 shrink-0 rounded border-sepstrong text-tint"
              />
            )}
            <input
              value={titel}
              onChange={(e) => setTitel(e.target.value)}
              placeholder="Titel der Aufgabe"
              className={`w-full border-none bg-transparent p-0 text-base font-bold outline-none ${
                erledigt ? "text-label3 line-through" : "text-label"
              }`}
            />
          </div>
          <button
            onClick={onClose}
            className="btn-touch flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-label2 hover:bg-fill"
          >
            <X size={16} strokeWidth={2} />
          </button>
        </div>

        <div className="space-y-4 px-5 py-4">
          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">
              Beschreibung
            </label>
            <textarea
              value={beschreibung}
              onChange={(e) => setBeschreibung(e.target.value)}
              rows={3}
              className="w-full resize-none field-ap h-auto py-1.5 text-sm"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">
                Fälligkeit
              </label>
              <input
                type="date"
                value={faelligkeitAm}
                onChange={(e) => setFaelligkeitAm(e.target.value)}
                className="w-full field-ap h-auto py-1.5 text-sm"
              />
            </div>
            <div>
              <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">
                Priorität
              </label>
              <div className="flex gap-0.5 rounded-lg bg-fill p-0.5">
                {PRIORITAET_OPTIONEN.map((option) => (
                  <button
                    key={option.wert}
                    onClick={() => setPrioritaet(option.wert)}
                    className={`flex-1 rounded-md px-2 py-1.5 text-xs font-semibold ${
                      prioritaet === option.wert
                        ? PRIORITAET_AKTIV_KLASSE[option.wert]
                        : "text-label2 hover:text-label"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {!istPrivat && istEigenstaendig && (
            <div>
              <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">
                Spalte
              </label>
              <select
                value={spalteId}
                onChange={(e) => setSpalteId(e.target.value)}
                className="w-full field-ap h-auto py-1.5 text-sm"
              >
                {spalten.map((spalte) => (
                  <option key={spalte.id} value={spalte.id}>
                    {spalte.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">
              Zuständiger
            </label>
            <SearchableSelect
              value={zugewiesenAn}
              onChange={setZugewiesenAn}
              placeholder="Nicht zugewiesen"
              options={(users ?? []).map((u) => ({ value: u.id, label: u.name }))}
            />
          </div>

          {/* Rein referenzielle Schnellzugriffe -- kein Status-Sync in
              irgendeine Richtung, siehe app/models/projekt.py. */}
          <VerknuepfungsZeile
            icon={Link2}
            farbe="blue"
            label="Verknüpfter Vorgang"
            anzeige={vorgangVorschau}
            onEntfernen={() => setVorgangId("")}
            route={vorgangId ? `/vorgaenge/${vorgangId}` : null}
            navigate={navigate}
            suchOptionen={(alleVorgaenge ?? []).map((v) => ({
              value: v.id,
              label: `${v.vorgangsnummer} · ${v.titel}`,
            }))}
            onWaehlen={setVorgangId}
            platzhalter="Vorgang suchen…"
            // Nur fuer bereits gespeicherte Aufgaben (aufgabe.id noetig, um den
            // neuen Vorgang nach dem Anlegen zurueck zu verknuepfen -- siehe
            // NewVorgangPage.tsx, aufgabe_id-Query-Param). Titel/Kunde/Anlage/
            // Standort werden vorbelegt, damit sie nicht doppelt erfasst werden.
            extraAktion={
              !istNeu ? (
                <button
                  type="button"
                  onClick={() => {
                    const params = new URLSearchParams();
                    if (kundeId) params.set("kunde_id", kundeId);
                    if (anlageId) params.set("anlage_id", anlageId);
                    if (standortId) params.set("standort_id", standortId);
                    if (titel) params.set("titel", titel);
                    if (beschreibung) params.set("beschreibung", beschreibung);
                    params.set("aufgabe_id", aufgabe!.id);
                    navigate(`/neu?${params.toString()}`);
                  }}
                  className="mt-1.5 text-xs font-medium text-tint hover:underline"
                >
                  + Neuen Vorgang aus dieser Aufgabe anlegen
                </button>
              ) : undefined
            }
          />

          <VerknuepfungsZeile
            icon={Users}
            farbe="green"
            label="Verknüpfter Kunde"
            anzeige={kundeAnzeige}
            onEntfernen={() => setKundeId("")}
            route={kundeId ? `/kunden/${kundeId}` : null}
            navigate={navigate}
            suchOptionen={(alleKunden ?? []).map((k) => ({ value: k.id, label: k.name }))}
            onWaehlen={setKundeId}
            platzhalter="Kunde suchen…"
          />

          <VerknuepfungsZeile
            icon={Building2}
            farbe="orange"
            label="Verknüpfte Anlage"
            anzeige={anlageAnzeige}
            onEntfernen={() => setAnlageId("")}
            route={anlageId ? `/anlagen/${anlageId}` : null}
            navigate={navigate}
            suchOptionen={(alleAnlagen ?? []).map((a) => ({ value: a.id, label: a.bezeichnung }))}
            onWaehlen={setAnlageId}
            platzhalter="Anlage suchen…"
          />

          <VerknuepfungsZeile
            icon={MapPin}
            farbe="red"
            label="Verknüpfter Standort"
            anzeige={standortAnzeige}
            onEntfernen={() => setStandortId("")}
            route={standortId ? `/standorte/${standortId}` : null}
            navigate={navigate}
            suchOptionen={(alleStandorte ?? []).map((s) => ({ value: s.id, label: s.bezeichnung }))}
            onWaehlen={setStandortId}
            platzhalter="Standort suchen…"
          />

          <div>
            <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">
              Checkliste{checkliste.length > 0 && ` · ${checkliste.filter((p) => p.erledigt).length}/${checkliste.length}`}
            </label>
            <div className="space-y-0.5">
              {checkliste.map((punkt, index) => (
                <div key={index} className="flex items-center gap-2 py-1">
                  <input
                    type="checkbox"
                    checked={punkt.erledigt}
                    onChange={() =>
                      setCheckliste((bisher) =>
                        bisher.map((p, i) => (i === index ? { ...p, erledigt: !p.erledigt } : p)),
                      )
                    }
                    className="h-4 w-4 rounded border-sepstrong text-tint"
                  />
                  <span
                    className={`flex-1 text-sm ${
                      punkt.erledigt
                        ? "text-label3 line-through"
                        : "text-label"
                    }`}
                  >
                    {punkt.text}
                  </span>
                  <button
                    onClick={() => setCheckliste((bisher) => bisher.filter((_, i) => i !== index))}
                    className="shrink-0 rounded-md p-1 text-label3 hover:text-st-fehlt"
                  >
                    <X size={13} strokeWidth={2} />
                  </button>
                </div>
              ))}
              <div className="flex items-center gap-2 py-1">
                <Plus size={14} strokeWidth={2} className="shrink-0 text-label2" />
                <input
                  value={neuerPunkt}
                  onChange={(e) => setNeuerPunkt(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") {
                      e.preventDefault();
                      checklistePunktHinzufuegen();
                    }
                  }}
                  onBlur={checklistePunktHinzufuegen}
                  placeholder="Punkt hinzufügen"
                  className="flex-1 border-none bg-transparent p-0 text-sm text-label2 outline-none placeholder:text-label3"
                />
              </div>
            </div>
          </div>

          {!istNeu && istEigenstaendig && (
            <div>
              <label className="mb-1.5 block text-[11px] font-bold tracking-wide text-label3 uppercase">
                Unteraufgaben
                {unteraufgaben && unteraufgaben.length > 0 &&
                  ` · ${unteraufgaben.filter((u) => u.erledigt_am).length}/${unteraufgaben.length}`}
              </label>
              <div className="space-y-0.5">
                {(unteraufgaben ?? []).map((u) => (
                  <div key={u.id} className="flex items-center gap-2 py-1">
                    <input
                      type="checkbox"
                      checked={!!u.erledigt_am}
                      onChange={() => unteraufgabeUmschalten.mutate({ id: u.id, erledigt: !u.erledigt_am })}
                      className="h-4 w-4 rounded border-sepstrong text-tint"
                    />
                    <span
                      className={`flex-1 text-sm ${
                        u.erledigt_am
                          ? "text-label3 line-through"
                          : "text-label"
                      }`}
                    >
                      {u.titel}
                    </span>
                    <button
                      onClick={() => unteraufgabeLoeschen.mutate(u.id)}
                      className="shrink-0 rounded-md p-1 text-label3 hover:text-st-fehlt"
                    >
                      <X size={13} strokeWidth={2} />
                    </button>
                  </div>
                ))}
                <div className="flex items-center gap-2 py-1">
                  <Plus size={14} strokeWidth={2} className="shrink-0 text-label2" />
                  <input
                    value={neueUnteraufgabe}
                    onChange={(e) => setNeueUnteraufgabe(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter" && neueUnteraufgabe.trim()) {
                        e.preventDefault();
                        unteraufgabeErstellen.mutate(neueUnteraufgabe.trim());
                      }
                    }}
                    placeholder="Unteraufgabe hinzufügen"
                    className="flex-1 border-none bg-transparent p-0 text-sm text-label2 outline-none placeholder:text-label3"
                  />
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="flex items-center justify-between gap-3 border-t-[0.5px] border-sep px-5 py-4">
          {istNeu ? (
            <span />
          ) : (
            <button
              onClick={() => {
                if (window.confirm("Aufgabe wirklich löschen?")) loeschen.mutate();
              }}
              disabled={loeschen.isPending}
              className="text-xs font-medium text-label2 hover:text-st-fehlt disabled:opacity-50"
            >
              Aufgabe löschen
            </button>
          )}
          <div className="flex gap-2">
            <button onClick={onClose} className="btn-ap">
              Abbrechen
            </button>
            <button
              onClick={() => speichern.mutate()}
              disabled={!titel.trim() || (!istPrivat && istEigenstaendig && !spalteId) || speichern.isPending}
              className="btn-ap-primary"
            >
              Speichern
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
