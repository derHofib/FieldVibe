import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Check, ClipboardCopy, Download, ExternalLink, Lightbulb, Trash2, X } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, useNavigate } from "react-router-dom";

import { fehlerberichteApi } from "../../api/endpoints";
import type { FehlerberichtDetail, FehlerberichtStatus, FehlerberichtUpdate } from "../../types";
import { downloadBlob } from "../../utils/download";
import { SegmentedControl } from "../apple/SegmentedControl";
import { FehlerStatusPille, SchweregradBadge } from "./Badges";
import { KontextTabs } from "./KontextTabs";
import { FEHLER_STATUS, datumZeit, istHttpUrl, kurzCommit, statusLabel } from "./darstellung";

function Abschnitt({ titel, children }: { titel: string; children: ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-semibold text-label2 uppercase">{titel}</h3>
      {children}
    </section>
  );
}

function Text({ titel, text }: { titel: string; text: string | null }) {
  if (!text) return null;
  return (
    <Abschnitt titel={titel}>
      <p className="card-ap whitespace-pre-wrap break-words p-3 text-[15px] text-label">{text}</p>
    </Abschnitt>
  );
}

function Screenshots({ detail }: { detail: FehlerberichtDetail }) {
  const { screenshot_annotiert_url: annotiert, screenshot_original_url: original } = detail;
  const [ansicht, setAnsicht] = useState<"annotiert" | "original">(annotiert ? "annotiert" : "original");
  const url = ansicht === "annotiert" ? annotiert : original;
  if (!annotiert && !original) return null;
  return (
    <Abschnitt titel="Screenshot">
      {annotiert && original && (
        <SegmentedControl
          ariaLabel="Screenshot-Variante"
          wert={ansicht}
          onChange={setAnsicht}
          optionen={[
            { wert: "annotiert", label: "Annotiert" },
            { wert: "original", label: "Original" },
          ]}
        />
      )}
      {url && (
        <a href={url} target="_blank" rel="noopener noreferrer" className="block" title="In voller Größe öffnen">
          <img
            src={url}
            alt={`Screenshot (${ansicht})`}
            className="max-h-[70vh] w-full rounded-[var(--radius-ap-card)] bg-fill object-contain"
          />
        </a>
      )}
    </Abschnitt>
  );
}

function Loesung({
  detail,
  kannBearbeiten,
  speichern,
  speichertGerade,
}: {
  detail: FehlerberichtDetail;
  kannBearbeiten: boolean;
  speichern: (body: FehlerberichtUpdate) => void;
  speichertGerade: boolean;
}) {
  const [notiz, setNotiz] = useState(detail.loesungsnotiz ?? "");
  const [commit, setCommit] = useState(detail.fix_commit ?? "");
  const [pr, setPr] = useState(detail.fix_pr_url ?? "");
  const geaendert =
    notiz !== (detail.loesungsnotiz ?? "") || commit !== (detail.fix_commit ?? "") || pr !== (detail.fix_pr_url ?? "");

  return (
    <Abschnitt titel="Lösung">
      <form
        className="card-ap space-y-3 p-3"
        onSubmit={(e) => {
          e.preventDefault();
          speichern({ loesungsnotiz: notiz.trim() || null, fix_commit: commit.trim() || null, fix_pr_url: pr.trim() || null });
        }}
      >
        <label className="block text-sm font-medium text-label">
          Lösungsnotiz
          <textarea
            value={notiz}
            onChange={(e) => setNotiz(e.target.value)}
            disabled={!kannBearbeiten}
            rows={4}
            maxLength={20000}
            className="field-ap mt-1"
          />
        </label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block text-sm font-medium text-label">
            Fix-Commit
            <input
              value={commit}
              onChange={(e) => setCommit(e.target.value)}
              disabled={!kannBearbeiten}
              maxLength={200}
              className="field-ap mt-1 font-mono"
            />
          </label>
          <label className="block text-sm font-medium text-label">
            PR-Link
            <input
              value={pr}
              onChange={(e) => setPr(e.target.value)}
              disabled={!kannBearbeiten}
              maxLength={1000}
              inputMode="url"
              className="field-ap mt-1"
            />
          </label>
        </div>
        {detail.fix_pr_url && istHttpUrl(detail.fix_pr_url) && (
          <a
            href={detail.fix_pr_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-sm font-medium text-tint-text"
          >
            <ExternalLink size={14} strokeWidth={2} aria-hidden="true" />
            Pull Request öffnen
          </a>
        )}
        {kannBearbeiten && (
          <div>
            <button type="submit" disabled={!geaendert || speichertGerade} className="btn-touch btn-ap btn-ap-primary px-4 py-2">
              Lösung speichern
            </button>
          </div>
        )}
      </form>
    </Abschnitt>
  );
}

function DuplikatBereich({
  detail,
  kannBearbeiten,
  speichern,
  detailPfad,
}: {
  detail: FehlerberichtDetail;
  kannBearbeiten: boolean;
  speichern: (body: FehlerberichtUpdate) => void;
  detailPfad: (id: string) => string;
}) {
  const [eingabe, setEingabe] = useState("");
  // Auswahl aus den juengsten Berichten (datalist) ODER freie ID-Eingabe.
  const { data: kandidaten } = useQuery({
    queryKey: ["fehlerberichte", "duplikat-kandidaten", detail.mandant_id, detail.art],
    queryFn: () => fehlerberichteApi.liste({ mandant_id: detail.mandant_id, art: detail.art, limit: 100 }),
    enabled: kannBearbeiten,
  });
  const id = eingabe.trim();
  const gueltig = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(id) && id !== detail.id;

  return (
    <Abschnitt titel="Duplikat">
      {detail.duplikat_von_id && (
        <p className="text-sm text-label">
          Duplikat von{" "}
          <Link to={detailPfad(detail.duplikat_von_id)} className="font-medium text-tint-text underline">
            {detail.duplikat_von_id.slice(0, 8)}
          </Link>
          {kannBearbeiten && (
            <button
              type="button"
              onClick={() => speichern({ duplikat_von_id: null })}
              className="ml-3 text-sm font-medium text-label2 underline"
            >
              Verknüpfung entfernen
            </button>
          )}
        </p>
      )}
      {kannBearbeiten && (
        <form
          className="flex flex-col gap-2 sm:flex-row"
          onSubmit={(e) => {
            e.preventDefault();
            if (gueltig) speichern({ duplikat_von_id: id, status: "duplikat" });
          }}
        >
          <input
            value={eingabe}
            onChange={(e) => setEingabe(e.target.value)}
            list="fehlerbericht-kandidaten"
            placeholder="Bericht-ID oder Titel wählen"
            aria-label="Original-Bericht"
            className="field-ap font-mono"
          />
          <datalist id="fehlerbericht-kandidaten">
            {(kandidaten ?? [])
              .filter((k) => k.id !== detail.id)
              .map((k) => (
                <option key={k.id} value={k.id}>
                  {k.titel}
                </option>
              ))}
          </datalist>
          <button type="submit" disabled={!gueltig} className="btn-touch btn-ap shrink-0 px-4 py-2">
            Als Duplikat markieren
          </button>
        </form>
      )}
    </Abschnitt>
  );
}

/** Detailansicht eines Fehlerberichts -- von Super-Admin (/bugfixes/:id) und
 * Office (/fehlerberichte/:id) gemeinsam genutzt. Rechte kommen als Props,
 * damit die Komponente selbst nichts ueber Rollen wissen muss. */
export function FehlerberichtDetailAnsicht({
  id,
  mitMandant,
  kannBearbeiten,
  kannLoeschen,
  ideenVerwalten = false,
  listenPfad,
  detailPfad,
}: {
  id: string;
  mitMandant: boolean;
  kannBearbeiten: boolean;
  kannLoeschen: boolean;
  /** Status/Lösung von Ideen darf nur das FieldVibe-Team (Super-Admin) ändern. */
  ideenVerwalten?: boolean;
  listenPfad: string;
  detailPfad: (id: string) => string;
}) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [hinweis, setHinweis] = useState<string | null>(null);

  const { data: detail, isLoading, isError } = useQuery({
    queryKey: ["fehlerberichte", "detail", id],
    queryFn: () => fehlerberichteApi.detail(id),
  });

  const aendern = useMutation({
    mutationFn: (body: FehlerberichtUpdate) => fehlerberichteApi.aendern(id, body),
    onSuccess: (neu) => {
      queryClient.setQueryData(["fehlerberichte", "detail", id], neu);
      void queryClient.invalidateQueries({ queryKey: ["fehlerberichte", "liste"] });
      void queryClient.invalidateQueries({ queryKey: ["fehlerberichte", "zaehler"] });
      setHinweis(null);
    },
    onError: (e: Error) => setHinweis(e.message),
  });

  const loeschen = useMutation({
    mutationFn: () => fehlerberichteApi.loeschen(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["fehlerberichte"] });
      navigate(listenPfad);
    },
    onError: (e: Error) => setHinweis(e.message),
  });

  async function bundleHolen(): Promise<string | null> {
    try {
      return await fehlerberichteApi.aiBundle(id);
    } catch (e) {
      setHinweis(e instanceof Error ? e.message : "AI-Bundle konnte nicht geladen werden.");
      return null;
    }
  }

  async function bundleKopieren() {
    const text = await bundleHolen();
    if (text === null) return;
    try {
      await navigator.clipboard.writeText(text);
      setHinweis("AI-Bundle in die Zwischenablage kopiert.");
    } catch {
      setHinweis("Zwischenablage nicht verfügbar – bitte stattdessen herunterladen.");
    }
  }

  async function bundleHerunterladen() {
    const text = await bundleHolen();
    if (text !== null) downloadBlob(new Blob([text], { type: "text/markdown;charset=utf-8" }), `fehlerbericht-${id.slice(0, 8)}.md`);
  }

  const idee = detail?.art === "idee";
  const darfAendern = kannBearbeiten && (!idee || ideenVerwalten);

  const zurueck = (
    <Link to={idee ? `${listenPfad}?art=idee` : listenPfad} className="inline-flex items-center gap-1 text-sm font-medium text-tint-text">
      <ArrowLeft size={14} strokeWidth={2} aria-hidden="true" />
      {idee ? "Alle Ideen" : "Alle Fehlerberichte"}
    </Link>
  );

  if (isLoading) return <p className="text-label2">Lädt…</p>;
  if (isError || !detail) {
    return (
      <div className="space-y-2">
        {zurueck}
        <p className="text-st-fehlt">Bericht nicht gefunden.</p>
      </div>
    );
  }

  const felder: [string, ReactNode][] = [
    [idee ? "Priorität" : "Schweregrad", <SchweregradBadge key="s" schweregrad={detail.schweregrad} />],
    ...(mitMandant ? ([["Mandant", detail.mandant_name ?? "–"]] as [string, ReactNode][]) : []),
    ["Melder", detail.melder_name ?? "–"],
    ["Gemeldet am", datumZeit(detail.created_at)],
    ...(detail.freigegeben_am ? ([["Freigegeben am", datumZeit(detail.freigegeben_am)]] as [string, ReactNode][]) : []),
    ["App-Version", detail.app_version ?? "–"],
    ["Commit", <span key="c" className="font-mono" title={detail.commit_sha ?? undefined}>{kurzCommit(detail.commit_sha)}</span>],
    ["Route", <span key="r" className="font-mono break-all">{detail.route ?? "–"}</span>],
  ];

  return (
    <div className="space-y-5">
      {zurueck}

      <header className="card-ap space-y-3 p-4">
        <h2 className="flex items-start gap-2 text-xl font-semibold break-words text-label">
          {idee && <Lightbulb size={20} strokeWidth={2} className="mt-1 shrink-0 text-tone-amber" aria-label="Idee" role="img" />}
          <span className="min-w-0">{detail.titel}</span>
        </h2>
        {darfAendern ? (
          <div className="overflow-x-auto">
            <SegmentedControl<FehlerberichtStatus>
              ariaLabel="Status"
              wert={detail.status}
              onChange={(status) => aendern.mutate({ status })}
              optionen={FEHLER_STATUS.map((s) => ({ wert: s, label: statusLabel(s, detail.art) }))}
            />
          </div>
        ) : (
          <FehlerStatusPille status={detail.status} art={detail.art} />
        )}
        {idee && darfAendern && detail.status === "neu" && (
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={aendern.isPending}
              onClick={() => aendern.mutate({ status: "gesichtet" })}
              className="btn-touch btn-ap btn-ap-primary inline-flex items-center gap-1.5 px-4 py-2"
            >
              <Check size={16} strokeWidth={2} aria-hidden="true" />
              Freigeben
            </button>
            <button
              type="button"
              disabled={aendern.isPending}
              onClick={() => aendern.mutate({ status: "abgelehnt" })}
              className="btn-touch btn-ap inline-flex items-center gap-1.5 px-4 py-2"
            >
              <X size={16} strokeWidth={2} aria-hidden="true" />
              Ablehnen
            </button>
          </div>
        )}
        {idee && darfAendern && (
          <p className="text-sm text-label2">Freigegebene Ideen setzt Claude beim nächsten Lauf als Pull Request um.</p>
        )}
        {idee && !darfAendern && (
          <p className="text-sm text-label2">Ideen werden vom FieldVibe-Team geprüft und freigegeben.</p>
        )}
        <dl className="grid gap-x-6 gap-y-2 sm:grid-cols-2">
          {felder.map(([label, wert]) => (
            <div key={label} className="flex items-baseline gap-2 text-sm">
              <dt className="w-24 shrink-0 text-label2">{label}</dt>
              <dd className="min-w-0 text-label">{wert}</dd>
            </div>
          ))}
        </dl>
        <div className="flex flex-wrap gap-2 pt-1">
          <button type="button" onClick={bundleKopieren} className="btn-touch btn-ap inline-flex items-center gap-1.5 px-3 py-2 text-sm">
            <ClipboardCopy size={14} strokeWidth={2} aria-hidden="true" />
            AI-Bundle kopieren
          </button>
          <button type="button" onClick={bundleHerunterladen} className="btn-touch btn-ap inline-flex items-center gap-1.5 px-3 py-2 text-sm">
            <Download size={14} strokeWidth={2} aria-hidden="true" />
            AI-Bundle herunterladen
          </button>
          {kannLoeschen && (
            <button
              type="button"
              onClick={() => {
                if (window.confirm(`${idee ? "Idee" : "Fehlerbericht"} "${detail.titel}" endgültig löschen?`)) loeschen.mutate();
              }}
              className="btn-touch btn-ap inline-flex items-center gap-1.5 px-3 py-2 text-sm text-st-fehlt hover:bg-st-fehlt-bg"
            >
              <Trash2 size={14} strokeWidth={2} aria-hidden="true" />
              Löschen
            </button>
          )}
        </div>
        {hinweis && (
          <p role="status" className="text-sm text-label2">
            {hinweis}
          </p>
        )}
      </header>

      <Text titel={idee ? "Was soll sich ändern?" : "Beschreibung"} text={detail.beschreibung} />
      <Text titel={idee ? "Warum / Nutzen" : "Erwartet"} text={detail.erwartet} />
      {!idee && <Text titel="Schritte" text={detail.schritte} />}
      <Screenshots detail={detail} />

      <Abschnitt titel="Kontext">
        <KontextTabs kontext={detail.kontext} />
      </Abschnitt>

      {/* key: Formularfelder neu initialisieren, sobald der Server andere Werte liefert */}
      <Loesung
        key={detail.updated_at}
        detail={detail}
        kannBearbeiten={darfAendern}
        speichern={(body) => aendern.mutate(body)}
        speichertGerade={aendern.isPending}
      />
      <DuplikatBereich
        key={`d-${detail.updated_at}`}
        detail={detail}
        kannBearbeiten={darfAendern}
        speichern={(body) => aendern.mutate(body)}
        detailPfad={detailPfad}
      />
    </div>
  );
}
