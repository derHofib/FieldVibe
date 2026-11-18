// Office-Seite "Formulare": Vorlagen (Tabelle + Vorschau-Panel) und alle ausgefüllten
// Protokolle. Die Feld-App-Seite FormSchemasPage bleibt unverändert schmal; diese Seite
// nutzt die Desktop-Breite (Konzept docs: konzept-formulare.md, Abschnitte 3 und 4).
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarDays, CircleDot, ClipboardList, FileText, Search, Shapes, Sparkles, User as UserIcon, Archive, Plus, Tag } from "lucide-react";
import { type FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { formModulApi, formSubmissionsApi, usersApi } from "../../api/endpoints";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { StatusPille } from "../../components/apple/StatusPille";
import { AktionsMenue } from "../../components/AktionsMenue";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { filterAnwenden, sucheAnwenden, zuServerParametern } from "../../components/filter/auswerten";
import { FilterLeiste } from "../../components/filter/FilterLeiste";
import type { FilterBedingung, FilterFeld } from "../../components/filter/typen";
import { useFilterZustand } from "../../components/filter/useFilterZustand";
import { ClaudeMarke } from "../../components/formModul/ClaudeMarke";
import { Feld, FELD_KLASSE, NEU_BUTTON_KLASSE } from "../../components/FormularFeld";
import { SkeletonList } from "../../components/Skeleton";
import type { FormSchema, FormSchemaStatus, FormSubmissionUebersicht, FormSubmissionUebersichtParams } from "../../types";
import { datumServerParameter } from "../../utils/datumFilterParameter";
import { FORM_SCHEMA_STATUS_LABEL, FORM_SCHEMA_STATUS_TOKEN, LEISTUNGSTYP_LABEL } from "../../utils/formular";
import { ListeMitPanel } from "../ListeMitPanel";
import { SeitenKopf, TabellenRahmen } from "../OfficeUi";
import { AusgefuelltPanel } from "./AusgefuelltPanel";
import { AusgefuelltTabelle, Seitenwahl } from "./AusgefuelltTabelle";
import { langesDatum, relativDatum } from "./formulareUtil";
import { VorlagenVorschau } from "./VorlagenVorschau";
import { useSchemaDaten } from "./useSchemaDaten";

type Ansicht = "vorlagen" | "ausgefuellt";

const STANDARD_VORLAGEN: FilterBedingung = { feld: "status", op: "ist", wert: ["draft", "published"] };
const STANDARD_AUSGEFUELLT: FilterBedingung = { feld: "zeitraum", op: "relativ", wert: { relativ: "letzte_30" } };

const STATUS_OPTIONEN = (Object.keys(FORM_SCHEMA_STATUS_LABEL) as FormSchemaStatus[]).map((wert) => ({
  wert,
  label: FORM_SCHEMA_STATUS_LABEL[wert],
}));

/** Ob die aktuelle Statusbedingung Archiviertes einschließt (ohne Bedingung: ja). */
function archivierteSichtbar(bedingungen: FilterBedingung[]): boolean {
  const b = bedingungen.find((x) => x.feld === "status");
  if (!b) return true;
  const werte = Array.isArray(b.wert) ? b.wert : [];
  return b.op === "ist_nicht" ? !werte.includes("archived") : werte.includes("archived");
}

/** Beim ersten Öffnen einer Ansicht ohne Filter in der URL die Standardbedingung setzen
 * (wie Partner/Anfragen); danach gehört der Filter dem Nutzer, auch wenn er ihn leert. */
function useStandardFilter(aktiv: boolean, paramName: string, standard: FilterBedingung, setBedingungen: (b: FilterBedingung[]) => void) {
  const [params] = useSearchParams();
  const gesetzt = useRef(false);
  const hatParam = params.has(paramName);
  useEffect(() => {
    if (!aktiv || gesetzt.current) return;
    gesetzt.current = true;
    if (!hatParam) setBedingungen([standard]);
  }, [aktiv, hatParam, setBedingungen, standard]);
}

export function OfficeFormularePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [params, setParams] = useSearchParams();
  const ansicht: Ansicht = params.get("ansicht") === "ausgefuellt" ? "ausgefuellt" : "vorlagen";
  const [auswahlVorlage, setAuswahlVorlage] = useState<string | null>(null);
  const [auswahlProtokoll, setAuswahlProtokoll] = useState<FormSubmissionUebersicht | null>(null);
  const [seite, setSeite] = useState(1);

  const [formOffen, setFormOffen] = useState(false);
  const [name, setName] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const schemasQuery = useQuery({ queryKey: ["form-schemas"], queryFn: () => formModulApi.listSchemas() });
  const schemas = schemasQuery.data;
  const nutzer = useQuery({ queryKey: ["users", "auswahl"], queryFn: () => usersApi.auswahl(), enabled: ansicht === "ausgefuellt" });

  // --- Vorlagen: Filter clientseitig (Liste kommt vollständig) ---
  const vorlagenFelder = useMemo<FilterFeld<FormSchema>[]>(
    () => [
      { key: "status", label: "Status", typ: "auswahl", icon: CircleDot, wert: (s) => s.status, optionen: STATUS_OPTIONEN },
      {
        key: "leistungstyp",
        label: "Leistungstyp",
        typ: "auswahl",
        icon: Tag,
        wert: (s) => s.leistungstypen.map((l) => l.leistungstyp),
        optionen: Object.entries(LEISTUNGSTYP_LABEL).map(([wert, label]) => ({ wert, label })),
      },
      {
        key: "erstellt_via",
        label: "Erstellt von",
        typ: "auswahl",
        icon: Sparkles,
        wert: (s) => s.erstellt_via,
        optionen: [
          { wert: "app", label: "App" },
          { wert: "ki", label: "Claude" },
        ],
      },
    ],
    [],
  );
  const vorlagenZustand = useFilterZustand({ felder: vorlagenFelder });
  useStandardFilter(ansicht === "vorlagen", "f", STANDARD_VORLAGEN, vorlagenZustand.setBedingungen);

  const vorlagen = useMemo(
    () =>
      sucheAnwenden(
        filterAnwenden(schemas ?? [], vorlagenZustand.bedingungen, vorlagenFelder),
        vorlagenZustand.sucheVerzoegert,
        (s) => [s.name, s.beschreibung ?? ""].join(" "),
      ),
    [schemas, vorlagenZustand.bedingungen, vorlagenZustand.sucheVerzoegert, vorlagenFelder],
  );

  // --- Ausgefüllt: Filter serverseitig ---
  const ausgefuelltFelder = useMemo<FilterFeld<FormSubmissionUebersicht>[]>(
    () => [
      { key: "zeitraum", label: "Zeitraum", typ: "datum", icon: CalendarDays, operatoren: ["relativ", "zwischen", "am", "vor", "nach"] },
      {
        key: "status",
        label: "Status",
        typ: "auswahl",
        icon: CircleDot,
        operatoren: ["ist"],
        einzelwert: true,
        optionen: [
          { wert: "offen", label: "Offen", status: "arbeit" },
          { wert: "abgeschlossen", label: "Abgeschlossen", status: "erledigt" },
        ],
      },
      {
        key: "vorlage",
        label: "Vorlage",
        typ: "verknuepfung",
        icon: FileText,
        operatoren: ["ist"],
        einzelwert: true,
        optionen: (schemas ?? []).map((s) => ({ wert: s.id, label: s.name })),
      },
      {
        key: "techniker",
        label: "Techniker",
        typ: "person",
        icon: UserIcon,
        operatoren: ["ist"],
        einzelwert: true,
        optionen: (nutzer.data ?? []).map((u) => ({ wert: u.id, label: u.name })),
      },
    ],
    [schemas, nutzer.data],
  );
  const ausgefuelltZustand = useFilterZustand({ felder: ausgefuelltFelder, praefix: "a" });
  useStandardFilter(ansicht === "ausgefuellt", "af", STANDARD_AUSGEFUELLT, ausgefuelltZustand.setBedingungen);

  const erster = (b: FilterBedingung) => (Array.isArray(b.wert) ? (b.wert[0] as string | undefined) : undefined);
  const serverFilter = zuServerParametern(ausgefuelltZustand.bedingungen, {
    zeitraum: datumServerParameter,
    status: (b): Record<string, string> => (erster(b) ? { status: erster(b)! } : {}),
    vorlage: (b): Record<string, string> => (erster(b) ? { schema_id: erster(b)! } : {}),
    techniker: (b): Record<string, string> => (erster(b) ? { techniker_id: erster(b)! } : {}),
  });
  const serverSchluessel = JSON.stringify([serverFilter, ausgefuelltZustand.sucheVerzoegert]);
  useEffect(() => setSeite(1), [serverSchluessel]);

  const ausgefuellt = useQuery({
    queryKey: ["form-submissions-uebersicht", serverFilter, ausgefuelltZustand.sucheVerzoegert, seite],
    queryFn: () =>
      formSubmissionsApi.uebersicht({
        ...(serverFilter as FormSubmissionUebersichtParams),
        suche: ausgefuelltZustand.sucheVerzoegert || undefined,
        seite,
      }),
    enabled: ansicht === "ausgefuellt",
    placeholderData: (vorher) => vorher,
  });

  // --- Anlegen / Veröffentlichen ---
  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () => formModulApi.createSchema({ name: name.trim(), beschreibung: beschreibung.trim() || undefined }),
    onSuccess: (schema) => {
      queryClient.invalidateQueries({ queryKey: ["form-schemas"] });
      navigate(`/form-schemas/${schema.id}`);
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Die Vorlage konnte nicht angelegt werden"),
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    setFehler(null);
    if (!name.trim()) {
      setFehler("Bitte einen Namen angeben");
      return;
    }
    createMutation.mutate();
  }

  function ansichtWechseln(neu: Ansicht) {
    setParams(
      (prev) => {
        const n = new URLSearchParams(prev);
        if (neu === "ausgefuellt") n.set("ansicht", "ausgefuellt");
        else n.delete("ansicht");
        return n;
      },
      { replace: true },
    );
    setAuswahlVorlage(null);
    setAuswahlProtokoll(null);
  }

  const alleNichtArchiviert = (schemas ?? []).filter((s) => s.status !== "archived");
  const zaehlerVorlagen = alleNichtArchiviert.length;
  const zaehlerAusgefuellt = (schemas ?? []).reduce((summe, s) => summe + s.ausgefuellt_anzahl, 0);
  const zustand = ansicht === "vorlagen" ? vorlagenZustand : ausgefuelltZustand;
  const felder = (ansicht === "vorlagen" ? vorlagenFelder : ausgefuelltFelder) as FilterFeld<unknown>[];

  const zeigeArchiv = archivierteSichtbar(vorlagenZustand.bedingungen);
  const menue = (
    <AktionsMenue
      label="Weitere Aktionen"
      eintraege={[
        { label: "Plan-Symbole", icon: Shapes, onClick: () => navigate("/plan-symbole") },
        {
          label: "Archivierte anzeigen",
          icon: Archive,
          aktiv: zeigeArchiv,
          onClick: () => {
            if (ansicht !== "vorlagen") ansichtWechseln("vorlagen");
            // Ohne Statusbedingung gilt "alle"; mit Standardbedingung zurück zu "ohne Archiviert".
            vorlagenZustand.setBedingungen([
              ...vorlagenZustand.bedingungen.filter((b) => b.feld !== "status"),
              ...(zeigeArchiv ? [STANDARD_VORLAGEN] : []),
            ]);
          },
        },
      ]}
    />
  );

  const vorlagenPanel = auswahlVorlage ? <VorlagenPanel key={auswahlVorlage} schema={schemas?.find((s) => s.id === auswahlVorlage)} onOeffnen={() => navigate(`/form-schemas/${auswahlVorlage}`)} /> : null;
  const protokollPanel = auswahlProtokoll ? <AusgefuelltPanel key={auswahlProtokoll.id} eintrag={auswahlProtokoll} /> : null;

  const neuButton = (
    <button type="button" onClick={() => setFormOffen(true)} className={NEU_BUTTON_KLASSE}>
      <Plus size={14} strokeWidth={2.5} aria-hidden="true" />
      Neue Vorlage
    </button>
  );

  const trefferText =
    ansicht === "vorlagen"
      ? `${vorlagen.length} ${vorlagen.length === 1 ? "Vorlage" : "Vorlagen"}`
      : ausgefuellt.data
        ? `${ausgefuellt.data.gesamt.toLocaleString("de-DE")} ${ausgefuellt.data.gesamt === 1 ? "Protokoll" : "Protokolle"}`
        : undefined;

  return (
    <div>
      <SeitenKopf titel="Formulare" untertitel="Vorlagen für Protokolle, Checklisten und Arbeitsscheine und alles, was damit ausgefüllt wurde.">
        {menue}
        {neuButton}
      </SeitenKopf>

      <FilterLeiste
        felder={felder}
        zustand={zustand}
        variante="office"
        suchPlatzhalter={ansicht === "vorlagen" ? "Vorlage suchen…" : "Vorgang, Kunde oder Vorlage"}
        className="mb-4"
        vorne={
          <SegmentedControl<Ansicht>
            ariaLabel="Bereich"
            wert={ansicht}
            onChange={ansichtWechseln}
            optionen={[
              { wert: "vorlagen", label: `Vorlagen ${schemas ? zaehlerVorlagen : ""}`.trim() },
              { wert: "ausgefuellt", label: `Ausgefüllt ${schemas ? zaehlerAusgefuellt.toLocaleString("de-DE") : ""}`.trim() },
            ]}
          />
        }
        hinten={trefferText}
      />

      <AnlegenPanel offen={formOffen} titel="Neue Vorlage" onClose={() => setFormOffen(false)}>
        <form onSubmit={submit} noValidate className="space-y-3 p-4">
          <Feld label="Name" pflicht fehler={fehler}>
            {(p) => (
              <input {...p} value={name} onChange={(e) => setName(e.target.value)} placeholder="z.B. Wartungsprotokoll Heizung" autoFocus className={FELD_KLASSE} />
            )}
          </Feld>
          <Feld label="Beschreibung (optional)">
            {(p) => <input {...p} value={beschreibung} onChange={(e) => setBeschreibung(e.target.value)} className={FELD_KLASSE} />}
          </Feld>
          <button type="submit" disabled={createMutation.isPending} className={`${NEU_BUTTON_KLASSE} w-full`}>
            Anlegen & bearbeiten
          </button>
        </form>
      </AnlegenPanel>

      {ansicht === "vorlagen" ? (
        schemasQuery.isLoading ? (
          <SkeletonList count={4} />
        ) : schemasQuery.error && !schemas ? (
          <FehlerZustand fehler={schemasQuery.error} was="Die Formulare" onErneut={() => void schemasQuery.refetch()} />
        ) : !schemas || schemas.length === 0 ? (
          <EmptyState
            icon={ClipboardList}
            text="Noch keine Vorlage angelegt. Eine Vorlage legt fest, welche Daten ein Protokoll oder eine Checkliste erfasst."
            action={neuButton}
          />
        ) : vorlagen.length === 0 ? (
          <EmptyState
            icon={Search}
            text={vorlagenZustand.sucheVerzoegert ? `Nichts gefunden für „${vorlagenZustand.sucheVerzoegert}“` : "Keine Treffer für diese Filter"}
            action={
              <button type="button" onClick={vorlagenZustand.zuruecksetzen} className="btn-ap px-4 py-2 text-sekundaer">
                Filter zurücksetzen
              </button>
            }
          />
        ) : (
          <ListeMitPanel
            panelTitel="Vorschau"
            panel={vorlagenPanel}
            onSchliessen={() => setAuswahlVorlage(null)}
            liste={
              <VorlagenTabelle
                schemas={vorlagen}
                auswahlId={auswahlVorlage}
                onWaehle={(s) => setAuswahlVorlage(s.id)}
                onOeffnen={(s) => navigate(`/form-schemas/${s.id}`)}
                hervorgehoben={vorlagenZustand.bedingungen.map((b) => b.feld)}
              />
            }
          />
        )
      ) : ausgefuellt.isError && !ausgefuellt.data ? (
        <FehlerZustand fehler={ausgefuellt.error} was="Die ausgefüllten Protokolle" onErneut={() => void ausgefuellt.refetch()} />
      ) : !ausgefuellt.data ? (
        <SkeletonList count={6} />
      ) : ausgefuellt.data.eintraege.length === 0 ? (
        <EmptyState
          icon={ClipboardList}
          text={
            ausgefuelltZustand.bedingungen.length > 0 || ausgefuelltZustand.sucheVerzoegert
              ? "Keine Protokolle für diese Filter"
              : "Noch kein Protokoll ausgefüllt. Sie entstehen, sobald eine Vorlage an einem Vorgang genutzt wird."
          }
          action={
            ausgefuelltZustand.bedingungen.length > 0 || ausgefuelltZustand.sucheVerzoegert ? (
              <button type="button" onClick={ausgefuelltZustand.zuruecksetzen} className="btn-ap px-4 py-2 text-sekundaer">
                Filter zurücksetzen
              </button>
            ) : (
              neuButton
            )
          }
        />
      ) : (
        <ListeMitPanel
          panelTitel="Protokoll"
          panel={protokollPanel}
          onSchliessen={() => setAuswahlProtokoll(null)}
          liste={
            <>
              <AusgefuelltTabelle
                eintraege={ausgefuellt.data.eintraege}
                auswahlId={auswahlProtokoll?.id ?? null}
                onWaehle={setAuswahlProtokoll}
                hervorgehoben={ausgefuelltZustand.bedingungen.map((b) => (b.feld === "zeitraum" ? "datum" : b.feld))}
              />
              <Seitenwahl seite={seite} gesamt={ausgefuellt.data.gesamt} anzahl={ausgefuellt.data.eintraege.length} onSeite={setSeite} />
            </>
          }
        />
      )}
    </div>
  );
}

function VorlagenTabelle({
  schemas,
  auswahlId,
  onWaehle,
  onOeffnen,
  hervorgehoben,
}: {
  schemas: FormSchema[];
  auswahlId: string | null;
  onWaehle: (s: FormSchema) => void;
  onOeffnen: (s: FormSchema) => void;
  hervorgehoben: string[];
}) {
  const kopf = (id: string, label: string, rechts = false) => (
    <th scope="col" className={`px-3 py-2 font-medium tracking-wide uppercase ${rechts ? "text-right" : ""} ${hervorgehoben.includes(id) ? "text-tint-text" : ""}`}>
      {label}
    </th>
  );
  return (
    <TabellenRahmen>
      <table className="w-full text-left text-fliess">
        <caption className="sr-only">Formularvorlagen. Zeile wählen für die Vorschau, Eingabetaste oder Doppelklick öffnet den Baukasten.</caption>
        <thead className="text-meta text-label2">
          <tr className="border-b border-sepstrong">
            {kopf("vorlage", "Vorlage")}
            {kopf("status", "Status")}
            {kopf("felder", "Felder", true)}
            {kopf("leistungstyp", "Leistungstyp")}
            {kopf("ausgefuellt", "Ausgefüllt", true)}
            {kopf("geaendert", "Geändert")}
            {kopf("erstellt_via", "Erstellt von")}
          </tr>
        </thead>
        <tbody>
          {schemas.map((s) => {
            const gewaehlt = s.id === auswahlId;
            return (
              <tr
                key={s.id}
                tabIndex={0}
                aria-selected={gewaehlt}
                onClick={() => onWaehle(s)}
                onDoubleClick={() => onOeffnen(s)}
                onKeyDown={(ev) => {
                  if (ev.target !== ev.currentTarget) return;
                  if (ev.key === "Enter") onOeffnen(s);
                  if (ev.key === " ") {
                    ev.preventDefault();
                    onWaehle(s);
                  }
                }}
                className={`cursor-pointer border-b border-sep outline-none last:border-b-0 focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-tint ${
                  gewaehlt ? "bg-tintbg" : "hover:bg-fill"
                }`}
              >
                <td className="max-w-[340px] px-3 py-2.5">
                  <span className="block font-semibold text-label">{s.name}</span>
                  {s.beschreibung && <span className="line-clamp-2 text-sekundaer text-label2">{s.beschreibung}</span>}
                </td>
                <td className="whitespace-nowrap px-3 py-2.5">
                  <span className="inline-flex items-center gap-1.5">
                    <StatusPille status={FORM_SCHEMA_STATUS_TOKEN[s.status]} label={FORM_SCHEMA_STATUS_LABEL[s.status]} />
                    <span className="text-sekundaer text-label2">v{s.version}</span>
                  </span>
                </td>
                <td className="px-3 py-2.5 text-right tabular-nums text-label">{s.felder_anzahl}</td>
                <td className="px-3 py-2.5">
                  {s.leistungstypen.length === 0 ? (
                    <span className="text-label2">—</span>
                  ) : (
                    <span className="flex flex-wrap gap-1">
                      {s.leistungstypen.map((l) => (
                        <span key={l.leistungstyp} className="rounded-[var(--radius-ap-sm)] bg-fill px-2 py-0.5 text-meta font-semibold text-label">
                          {LEISTUNGSTYP_LABEL[l.leistungstyp] ?? l.leistungstyp}
                          {l.pflicht_vor_abschluss && " · Pflicht"}
                        </span>
                      ))}
                    </span>
                  )}
                </td>
                <td className={`px-3 py-2.5 text-right tabular-nums ${s.ausgefuellt_anzahl === 0 ? "text-label2" : "text-label"}`}>{s.ausgefuellt_anzahl}</td>
                <td className="whitespace-nowrap px-3 py-2.5 text-label2" title={langesDatum(s.updated_at)}>
                  {relativDatum(s.updated_at)}
                </td>
                <td className="whitespace-nowrap px-3 py-2.5 text-label">
                  {s.erstellt_via === "ki" ? <ClaudeMarke /> : (s.erstellt_von_name ?? "—")}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </TabellenRahmen>
  );
}

function VorlagenPanel({ schema, onOeffnen }: { schema: FormSchema | undefined; onOeffnen: () => void }) {
  const queryClient = useQueryClient();
  const [fehler, setFehler] = useState<string | null>(null);
  const { schema: detail } = useSchemaDaten(schema?.id);
  const veroeffentlichen = useMutation({
    meta: { erfolg: "Veröffentlicht" },
    mutationFn: () => formModulApi.updateSchema(schema!.id, { status: "published" }),
    onSuccess: () => {
      setFehler(null);
      queryClient.invalidateQueries({ queryKey: ["form-schemas"] });
      queryClient.invalidateQueries({ queryKey: ["form-schema", schema!.id] });
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Konnte nicht veröffentlicht werden"),
  });
  if (!schema) return null;

  const abschnitte = detail.data?.groups.length;
  return (
    <div className="space-y-3 pt-3">
      <div>
        <p className="flex flex-wrap items-center gap-x-2 text-sekundaer text-label2">
          <StatusPille status={FORM_SCHEMA_STATUS_TOKEN[schema.status]} label={FORM_SCHEMA_STATUS_LABEL[schema.status]} />
          <span>
            Version {schema.version} · {schema.felder_anzahl} Felder
            {abschnitte !== undefined && ` · ${abschnitte} ${abschnitte === 1 ? "Abschnitt" : "Abschnitte"}`}
          </span>
        </p>
        <h2 className="mt-1.5 text-titel-mobil font-bold text-label">{schema.name}</h2>
      </div>

      {schema.erstellt_via === "ki" && schema.status === "draft" && (
        <p className="rounded-[var(--radius-ap-md)] bg-st-wartet-bg p-3 text-sekundaer text-label">
          <Sparkles size={14} className="mr-1.5 inline text-st-wartet" aria-hidden="true" />
          <strong>Von Claude entworfen</strong> am {langesDatum(schema.created_at)}
          {schema.erstellt_von_name ? ` für ${schema.erstellt_von_name}` : ""}. Noch nicht veröffentlicht: Felder prüfen, Leistungstyp zuordnen, dann
          veröffentlichen.
        </p>
      )}

      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={onOeffnen} className="btn-ap-primary inline-flex h-8 items-center px-3 text-sekundaer font-semibold">
          Im Baukasten bearbeiten
        </button>
        {schema.status === "draft" && (
          <button
            type="button"
            onClick={() => veroeffentlichen.mutate()}
            disabled={veroeffentlichen.isPending}
            className="btn-ap inline-flex h-8 items-center px-3 text-sekundaer font-semibold disabled:opacity-50"
          >
            Veröffentlichen
          </button>
        )}
      </div>
      {fehler && (
        <p role="alert" className="text-sekundaer text-st-fehlt">
          {fehler}
        </p>
      )}

      <VorlagenVorschau schemaId={schema.id} />
    </div>
  );
}
