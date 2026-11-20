import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { MessageSquareText } from "lucide-react";
import { Plus, ShieldCheck, X } from "lucide-react";
import { useState, type FormEvent } from "react";

import { kundenportalApi } from "../../api/endpoints";
import { ApiError } from "../../api/client";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { VOR_ORT_ROLLEN, VOR_ORT_ROLLE_LABEL, type Leistungstyp, type VorgangAnfrageStatus, type VorOrtRolle } from "../../types";
import {
  PORTAL_ANONYMISIERUNG_MONATE,
  PORTAL_MAX_KONTAKTE,
  baueKontakteBody,
  leererPortalKontakt,
  validierePortalKontakte,
  type PortalKontaktFormular,
} from "../../utils/portalAnfrage";
import { FehlerZustand } from "../../components/FehlerZustand";
import { Select } from "../../components/apple/Select";
import { useKundenAuth } from "../../context/KundenAuthContext";
import { standortBegriff } from "../../utils/vorOrt";

const LEISTUNGSTYPEN: { value: Leistungstyp; label: string }[] = [
  { value: "stoerung", label: "Störung" },
  { value: "installation", label: "Installation" },
  { value: "wartung", label: "Wartung" },
  { value: "pruefung", label: "Prüfung" },
  { value: "beratung", label: "Beratung" },
  { value: "planung", label: "Planung" },
];

const STATUS_LABEL: Record<VorgangAnfrageStatus, string> = {
  offen: "In Prüfung",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

const STATUS_BADGE: Record<VorgangAnfrageStatus, string> = {
  offen: "border rounded-[var(--radius-ap-pill)] border-st-arbeit text-st-arbeit ",
  angenommen: "border rounded-[var(--radius-ap-pill)] border-st-erledigt text-st-erledigt ",
  abgelehnt: "border rounded-[var(--radius-ap-pill)] border-sep text-label2 ",
};

const KONTAKT_FELD = "btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-label";

/** Ansprechpartner vor Ort (z. B. Mieter/in): bis zu fünf, je Name oder Telefon Pflicht; leere Zeilen werden nicht gesendet. */
function KontakteVorOrtEingabe({
  liste,
  fehler,
  onChange,
}: {
  liste: PortalKontaktFormular[];
  fehler: Record<number, string>;
  onChange: (liste: PortalKontaktFormular[]) => void;
}) {
  const aendere = (i: number, teil: Partial<PortalKontaktFormular>) =>
    onChange(liste.map((k, j) => (j === i ? { ...k, ...teil } : k)));
  return (
    <fieldset className="space-y-3">
      <legend className="mb-1 text-meta font-semibold uppercase tracking-wide text-label2">Ansprechpartner vor Ort</legend>
      {liste.map((k, i) => (
        <div key={i} className="space-y-2 rounded-[var(--radius-ap-card)] bg-fill p-3">
          {liste.length > 1 && (
            <div className="flex justify-end">
              <button
                type="button"
                onClick={() => onChange(liste.filter((_, j) => j !== i))}
                aria-label={`Kontakt ${i + 1} entfernen`}
                className="btn-touch p-1 text-label2"
              >
                <X size={16} strokeWidth={2} aria-hidden="true" />
              </button>
            </div>
          )}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor={`portal-kontakt-name-${i}`} className="mb-1 block text-sekundaer text-label2">Name</label>
              <input id={`portal-kontakt-name-${i}`} value={k.name} maxLength={200} onChange={(e) => aendere(i, { name: e.target.value })} className={KONTAKT_FELD} />
            </div>
            <div>
              <label htmlFor={`portal-kontakt-rolle-${i}`} className="mb-1 block text-sekundaer text-label2">Rolle</label>
              <Select flaeche="transparent" id={`portal-kontakt-rolle-${i}`} value={k.rolle} onChange={(e) => aendere(i, { rolle: e.target.value as VorOrtRolle })}>
                {VOR_ORT_ROLLEN.map((r) => (
                  <option key={r} value={r}>
                    {VOR_ORT_ROLLE_LABEL[r]}
                  </option>
                ))}
              </Select>
            </div>
            <div>
              <label htmlFor={`portal-kontakt-telefon-${i}`} className="mb-1 block text-sekundaer text-label2">Telefon</label>
              <input id={`portal-kontakt-telefon-${i}`} type="tel" value={k.telefon} maxLength={50} onChange={(e) => aendere(i, { telefon: e.target.value })} className={KONTAKT_FELD} />
            </div>
            <div>
              <label htmlFor={`portal-kontakt-erreichbar-${i}`} className="mb-1 block text-sekundaer text-label2">Erreichbar</label>
              <input id={`portal-kontakt-erreichbar-${i}`} value={k.erreichbarkeit} maxLength={200} placeholder="z. B. nachmittags" onChange={(e) => aendere(i, { erreichbarkeit: e.target.value })} className={KONTAKT_FELD} />
            </div>
          </div>
          <div>
            <label htmlFor={`portal-kontakt-hinweis-${i}`} className="mb-1 block text-sekundaer text-label2">Hinweis</label>
            <input id={`portal-kontakt-hinweis-${i}`} value={k.hinweis} maxLength={500} placeholder="z. B. Zugang, Klingel defekt" onChange={(e) => aendere(i, { hinweis: e.target.value })} className={KONTAKT_FELD} />
          </div>
          {fehler[i] && (
            <p role="alert" className="text-sekundaer text-st-fehlt">
              {fehler[i]}
            </p>
          )}
        </div>
      ))}
      {liste.length < PORTAL_MAX_KONTAKTE && (
        <button
          type="button"
          onClick={() => onChange([...liste, leererPortalKontakt()])}
          className="btn-touch flex items-center gap-1.5 text-fliess font-medium text-tint-text"
        >
          <Plus size={16} strokeWidth={2} aria-hidden="true" />
          Weiteren Kontakt hinzufügen
        </button>
      )}
      <div className="flex items-start gap-2 rounded-[var(--radius-ap-md)] bg-st-neu-bg p-3 text-sekundaer text-st-neu">
        <ShieldCheck size={16} strokeWidth={2} className="mt-px shrink-0" aria-hidden="true" />
        <p>
          Die Kontaktdaten nutzen wir nur für diesen Einsatz und anonymisieren sie {PORTAL_ANONYMISIERUNG_MONATE} Monate nach dem
          letzten Einsatz. Bitte informieren Sie die Person, dass Sie die Daten an uns weitergeben.
        </p>
      </div>
    </fieldset>
  );
}

function NeueAnfrage() {
  const queryClient = useQueryClient();
  const { currentKunde } = useKundenAuth();
  const standortWort = standortBegriff(currentKunde?.kunde_typ);
  const [zeigen, setZeigen] = useState(false);
  const [titel, setTitel] = useState("");
  const [beschreibung, setBeschreibung] = useState("");
  const [leistungstyp, setLeistungstyp] = useState<Leistungstyp>("stoerung");
  const [standortId, setStandortId] = useState("");
  const [anlageId, setAnlageId] = useState("");
  const [zeigeNeuerStandort, setZeigeNeuerStandort] = useState(false);
  const [neuerStandortName, setNeuerStandortName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [titelFehler, setTitelFehler] = useState<string | null>(null);
  const [zeichen, setZeichen] = useState("");
  const [einheit, setEinheit] = useState("");
  const [kontakte, setKontakte] = useState<PortalKontaktFormular[]>([leererPortalKontakt()]);
  const [kontaktFehler, setKontaktFehler] = useState<Record<number, string>>({});
  const [standortFehler, setStandortFehler] = useState<string | null>(null);

  const { data: standorte } = useQuery({
    queryKey: ["portal-standorte"],
    queryFn: kundenportalApi.standorte,
    enabled: zeigen,
  });
  const { data: anlagen } = useQuery({
    queryKey: ["portal-anlagen"],
    queryFn: kundenportalApi.anlagen,
    enabled: zeigen,
  });
  const anlagenFuerStandort = (anlagen ?? []).filter((a) => !standortId || a.standort_id === standortId);

  const neuerStandortMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () => kundenportalApi.standortAnlegen({ bezeichnung: neuerStandortName }),
    onSuccess: (standort) => {
      queryClient.invalidateQueries({ queryKey: ["portal-standorte"] });
      setStandortId(standort.id);
      setZeigeNeuerStandort(false);
      setNeuerStandortName("");
    },
  });

  const createMutation = useMutation({
    meta: { erfolg: "Anfrage gesendet" },
    mutationFn: () =>
      kundenportalApi.anfrageAnlegen({
        titel,
        beschreibung: beschreibung || undefined,
        leistungstyp,
        standort_id: standortId || undefined,
        anlage_id: anlageId || undefined,
        kunden_referenz: zeichen.trim() || undefined,
        einheit: einheit.trim() || undefined,
        vor_ort_kontakte: baueKontakteBody(kontakte),
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal-anfragen"] });
      setZeigen(false);
      setTitel("");
      setBeschreibung("");
      setStandortId("");
      setAnlageId("");
      setZeichen("");
      setEinheit("");
      setKontakte([leererPortalKontakt()]);
      setKontaktFehler({});
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Anfrage konnte nicht gesendet werden"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!titel.trim()) {
      setTitelFehler("Bitte einen Titel eingeben.");
      return;
    }
    setTitelFehler(null);
    const kFehler = validierePortalKontakte(kontakte);
    setKontaktFehler(kFehler);
    if (Object.keys(kFehler).length > 0) return;
    createMutation.mutate();
  }

  return (
    <>
      <button onClick={() => setZeigen(true)} className="btn-touch btn-ap-primary w-full rounded-lg py-3 text-sekundaer font-medium">
        + Neue Anfrage
      </button>
      <AnlegenPanel offen={zeigen} titel="Neue Anfrage" onClose={() => setZeigen(false)}>
        <form onSubmit={handleSubmit} className="space-y-3 p-4">
          <p className="text-sekundaer text-label2">
            Ihre Anfrage wird von uns geprüft und in einen Auftrag übernommen, sobald sie bestätigt ist.
          </p>
          <div>
            <label htmlFor="portal-anfrage-titel" className="mb-1 block text-fliess font-medium text-label">
              Titel <span aria-hidden="true" className="text-st-fehlt">*</span>
            </label>
            <input
              id="portal-anfrage-titel"
              autoFocus
              value={titel}
              onChange={(e) => setTitel(e.target.value)}
              aria-invalid={!!titelFehler}
              aria-describedby={titelFehler ? "portal-anfrage-titel-fehler" : undefined}
              className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-label"
            />
            {titelFehler && (
              <p id="portal-anfrage-titel-fehler" role="alert" className="mt-1 text-sekundaer text-st-fehlt">
                {titelFehler}
              </p>
            )}
          </div>
          <div>
            <label htmlFor="portal-anfrage-beschreibung" className="mb-1 block text-fliess font-medium text-label">
              Beschreibung
            </label>
            <textarea
              id="portal-anfrage-beschreibung"
              value={beschreibung}
              onChange={(e) => setBeschreibung(e.target.value)}
              rows={3}
              className="w-full resize-none border rounded-[var(--radius-ap-input)] border-sep bg-transparent p-2 text-label"
            />
          </div>
          <div>
            <label htmlFor="portal-anfrage-art" className="mb-1 block text-fliess font-medium text-label">
              Art
            </label>
            <Select
              id="portal-anfrage-art"
              value={leistungstyp}
              onChange={(e) => setLeistungstyp(e.target.value as Leistungstyp)}
            >
              {LEISTUNGSTYPEN.map((l) => (
                <option key={l.value} value={l.value}>
                  {l.label}
                </option>
              ))}
            </Select>
          </div>

          {(standorte ?? []).length > 0 && (
            <div>
              <label htmlFor="portal-anfrage-standort" className="mb-1 block text-fliess font-medium text-label">
                {standortWort} (optional)
              </label>
              <Select
                id="portal-anfrage-standort"
                value={standortId}
                onChange={(e) => {
                  setStandortId(e.target.value);
                  setAnlageId("");
                }}
              >
                <option value="">{standortWort === "Liegenschaft" ? "Keine Liegenschaft" : "Kein Standort"}</option>
                {standorte?.filter((s) => s.aktiv).map((s) => (
                  <option key={s.id} value={s.id}>
                    {s.bezeichnung}
                  </option>
                ))}
              </Select>
            </div>
          )}

          {!zeigeNeuerStandort ? (
            <button
              type="button"
              onClick={() => setZeigeNeuerStandort(true)}
              className="btn-touch btn-ap px-4 py-2 text-sekundaer font-medium"
            >
              {standortWort === "Liegenschaft" ? "+ Neue Liegenschaft" : "+ Neuer Standort"}
            </button>
          ) : (
            <div>
              <label htmlFor="portal-anfrage-neuer-standort" className="mb-1 block text-fliess font-medium text-label">
                {standortWort === "Liegenschaft" ? "Neue Liegenschaft" : "Neuer Standort"} <span aria-hidden="true" className="text-st-fehlt">*</span>
              </label>
              <div className="flex gap-2">
                <input
                  id="portal-anfrage-neuer-standort"
                  value={neuerStandortName}
                  onChange={(e) => setNeuerStandortName(e.target.value)}
                  placeholder="z.B. Filiale Nord"
                  aria-invalid={!!standortFehler}
                  aria-describedby={standortFehler ? "portal-anfrage-standort-fehler" : undefined}
                  className="btn-touch flex-1 border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-zeile text-label"
                />
                <button
                  type="button"
                  disabled={neuerStandortMutation.isPending}
                  onClick={() => {
                    if (!neuerStandortName.trim()) {
                      setStandortFehler("Bitte eine Bezeichnung eingeben.");
                      return;
                    }
                    setStandortFehler(null);
                    neuerStandortMutation.mutate();
                  }}
                  className="btn-touch btn-ap shrink-0 px-4 py-2 text-sekundaer font-medium"
                >
                  Anlegen
                </button>
              </div>
              {standortFehler && (
                <p id="portal-anfrage-standort-fehler" role="alert" className="mt-1 text-sekundaer text-st-fehlt">
                  {standortFehler}
                </p>
              )}
            </div>
          )}

          {anlagenFuerStandort.length > 0 && (
            <div>
              <label htmlFor="portal-anfrage-anlage" className="mb-1 block text-fliess font-medium text-label">
                Anlage (optional)
              </label>
              <Select
                id="portal-anfrage-anlage"
                value={anlageId}
                onChange={(e) => setAnlageId(e.target.value)}
              >
                <option value="">Keine Anlage</option>
                {anlagenFuerStandort.filter((a) => a.aktiv).map((a) => (
                  <option key={a.id} value={a.id}>
                    {a.bezeichnung}
                  </option>
                ))}
              </Select>
            </div>
          )}

          <div className="grid grid-cols-2 gap-3">
            <div>
              <label htmlFor="portal-anfrage-zeichen" className="mb-1 block text-fliess font-medium text-label">
                Ihr Zeichen (optional)
              </label>
              <input
                id="portal-anfrage-zeichen"
                value={zeichen}
                maxLength={200}
                onChange={(e) => setZeichen(e.target.value)}
                className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-label"
              />
            </div>
            <div>
              <label htmlFor="portal-anfrage-einheit" className="mb-1 block text-fliess font-medium text-label">
                Einheit / Lage
              </label>
              <input
                id="portal-anfrage-einheit"
                value={einheit}
                maxLength={200}
                placeholder="z. B. Whg. 3, 2. OG links"
                onChange={(e) => setEinheit(e.target.value)}
                className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-label"
              />
            </div>
          </div>

          <KontakteVorOrtEingabe liste={kontakte} fehler={kontaktFehler} onChange={setKontakte} />

          {error && <p role="alert" className="text-fliess text-st-fehlt">{error}</p>}

          <button
            type="submit"
            disabled={createMutation.isPending}
            className="btn-touch btn-ap-primary w-full rounded-md py-2 text-sekundaer font-medium"
          >
            Anfrage senden
          </button>
        </form>
      </AnlegenPanel>
    </>
  );
}

export function PortalAnfragenPage() {
  const { data: anfragen, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["portal-anfragen"],
    queryFn: kundenportalApi.anfragen,
  });

  return (
    <div className="space-y-3">
      <h1 className="text-titel-mobil font-bold text-label">Ihre Anfragen</h1>
      <NeueAnfrage />

      {isLoading ? (
        <SkeletonList count={3} />
      ) : ladeFehler && !anfragen ? (
        <FehlerZustand fehler={ladeFehler} was="Die Anfragen" onErneut={() => void neuLaden()} />
      ) : !anfragen || anfragen.length === 0 ? (
        <EmptyState icon={MessageSquareText} text="Noch keine Anfragen gestellt." />
      ) : (
        <div className="space-y-2">
          {anfragen.map((a) => (
            <div
              key={a.id}
              className="card-ap p-4"
            >
              <div className="flex items-start justify-between">
                <div className="font-medium text-label">{a.titel}</div>
                <span className={`px-2 py-1 text-sekundaer font-semibold ${STATUS_BADGE[a.status]}`}>
                  {STATUS_LABEL[a.status]}
                </span>
              </div>
              {a.beschreibung && (
                <p className="mt-1 text-sekundaer text-label2">{a.beschreibung}</p>
              )}
              {a.ablehnungsgrund && (
                <>
                  <p className="mt-1 text-sekundaer text-label2">Grund: {a.ablehnungsgrund}</p>
                  <p className="mt-1 text-sekundaer text-label2">
                    Bei Fragen wenden Sie sich gerne direkt an uns, oder stellen Sie eine neue Anfrage.
                  </p>
                </>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
