import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, ChevronDown, FileText, ListChecks, X } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import {
  angeboteApi,
  kundenApi,
  leistungsverzeichnisApi,
  mandantEinstellungenApi,
  rechnungenApi,
} from "../../api/endpoints";
import type { RechnungPosition, RechnungPositionQuelle, RechnungPositionVorschlag } from "../../types";
import { EmailSection } from "../../components/EmailSection";
import { EmptyState } from "../../components/EmptyState";
import { FehlerMeldung, Hinweiskasten } from "../../components/Hinweiskasten";
import { GutschriftSheet } from "../../components/rechnung/GutschriftSheet";
import { RechnungSummen } from "../../components/rechnung/RechnungSummen";
import { SteuerAuswahl } from "../../components/rechnung/SteuerAuswahl";
import { VorgangHinzufuegen } from "../../components/rechnung/VorgangHinzufuegen";
import { SearchableSelect } from "../../components/SearchableSelect";
import { StatusBadge } from "../../components/StatusBadge";
import { useAuth } from "../../context/AuthContext";
import { RECHNUNG_STATUS_LABEL } from "../../utils/buchhaltung";
import { downloadBlob } from "../../utils/download";
import { formatEuro, heuteIso } from "../../utils/format";
import { openPdfBlob } from "../../utils/pdf";
import { gruppierePositionen } from "../../utils/rechnungAbrechnung";
import {
  RECHNUNGSART_LABEL,
  RECHNUNGSART_TONE,
  istAbzugsposition,
  kannGutschriftErstellen,
  offenAnzeige,
  offenLabel,
  rechnungsartVon,
} from "../../utils/rechnungsart";
import {
  optionZuFelder,
  positionZuEingabe,
  steuerKurzlabel,
  validiereSteuer,
  vorbelegung,
  type SteuerEingabe,
} from "../../utils/steuer";
import type { RechnungZahlungsart } from "../../types";

const VORSCHLAG_QUELLE_LABEL: Record<RechnungPositionQuelle, string> = {
  material: "Material",
  leistung: "Leistungsverzeichnis",
  zeit: "Zeiterfassung",
  fahrzeit: "Fahrzeit",
  fahrtkosten: "Fahrtkosten",
};

/** Vorschlagsbox fuer Rechnungen mit Vorgangsbezug -- fasst bereits am
 * Vorgang erfasstes Material und abrechenbare Zeiterfassung zusammen, die
 * der Nutzer gezielt als Positionen uebernimmt statt alles freihand
 * einzutippen. Reiner Vorschlag ohne Nebenwirkung, bis "Übernehmen"
 * gedrueckt wird -- legt dann ganz normal ueber addPosition echte
 * RechnungPosition-Zeilen an. */
function PositionsVorschlaege({ rechnungId, vorgangId }: { rechnungId: string; vorgangId: string }) {
  const queryClient = useQueryClient();
  const [ausgewaehlt, setAusgewaehlt] = useState<Set<number>>(new Set());

  const { data: vorschlaege } = useQuery({
    queryKey: ["rechnung-vorschlaege", rechnungId],
    queryFn: () => rechnungenApi.positionsvorschlaege(rechnungId),
  });

  const uebernehmenMutation = useMutation({
    mutationFn: async () => {
      const gewaehlte = (vorschlaege ?? []).filter((_, i) => ausgewaehlt.has(i));
      for (const v of gewaehlte) {
        await rechnungenApi.addPosition(rechnungId, {
          beschreibung: v.beschreibung,
          menge: v.menge,
          einheit: v.einheit,
          einzelpreis: v.einzelpreis,
          quelle: v.quelle,
          lv_position_id: v.lv_position_id,
          material_id: v.material_id,
        });
      }
    },
    onSuccess: () => {
      setAusgewaehlt(new Set());
      queryClient.invalidateQueries({ queryKey: ["rechnung", rechnungId] });
    },
  });

  const toggle = (i: number) =>
    setAusgewaehlt((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  if (!vorgangId || (vorschlaege && vorschlaege.length === 0)) return null;

  return (
    <div className="mb-3 rounded-lg border border-dashed border-cyan-200 bg-cyan-50/60 p-3 dark:border-cyan-500/30 dark:bg-cyan-500/10">
      <div className="mb-2 flex items-center gap-1.5">
        <ListChecks size={13} strokeWidth={2} className="text-cyan-700 dark:text-cyan-300" />
        <p className="text-xs font-bold text-cyan-800 dark:text-cyan-200">Vorschläge aus dem Vorgang</p>
      </div>
      <div className="space-y-1.5">
        {(vorschlaege ?? []).map((v: RechnungPositionVorschlag, i) => (
          <label key={i} className="flex items-center gap-2 rounded-md bg-card px-2 py-1.5 text-sm">
            <input
              type="checkbox"
              checked={ausgewaehlt.has(i)}
              onChange={() => toggle(i)}
              className="h-3.5 w-3.5"
            />
            <span className="flex-1 text-label">
              {v.beschreibung}, {v.menge} {v.einheit} × {v.einzelpreis} EUR
            </span>
            <span className="border border-sep px-2 py-0.5 text-[10px] font-semibold text-label2">
              {VORSCHLAG_QUELLE_LABEL[v.quelle]}
            </span>
          </label>
        ))}
      </div>
      <button
        disabled={ausgewaehlt.size === 0 || uebernehmenMutation.isPending}
        onClick={() => uebernehmenMutation.mutate()}
        className="btn-touch mt-2 rounded-md btn-ap-primary px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
      >
        Übernehmen
      </button>
    </div>
  );
}

/** Einzelpreis im Entwurf inline editierbar; gespeichert wird bei Enter/Blur,
 * nur wenn sich der Wert geaendert hat. */
function EinzelpreisFeld({
  wert,
  disabled,
  onSpeichern,
}: {
  wert: string;
  disabled: boolean;
  onSpeichern: (neu: string) => void;
}) {
  const [text, setText] = useState(wert);
  useEffect(() => setText(wert), [wert]);
  const speichern = () => {
    if (text === "" || Number(text) === Number(wert)) {
      setText(wert);
      return;
    }
    onSpeichern(text);
  };
  return (
    <input
      type="number"
      step="0.01"
      min="0"
      value={text}
      disabled={disabled}
      aria-label="Einzelpreis (EUR)"
      onChange={(e) => setText(e.target.value)}
      onBlur={speichern}
      onKeyDown={(e) => {
        if (e.key === "Enter") e.currentTarget.blur();
      }}
      className="w-20 border border-sep bg-transparent px-1.5 py-0.5 text-right text-xs text-label disabled:opacity-50"
    />
  );
}

const ZAHLUNGSART_OPTIONEN: { value: RechnungZahlungsart; label: string }[] = [
  { value: "ueberweisung", label: "Überweisung" },
  { value: "bar", label: "Bar" },
  { value: "karte", label: "Karte" },
  { value: "lastschrift", label: "Lastschrift" },
  { value: "sonstiges", label: "Sonstiges" },
];

// id optional als Prop, damit die Office-Oberflaeche diese Seite in ihrem
// Detail-Panel einbetten kann, ohne dass es einen zweiten, parallel zu
// pflegenden Nachbau braucht. Ohne Prop verhaelt sie sich wie bisher.
export function RechnungDetailPage({ id: idProp }: { id?: string } = {}) {
  const { id: idParam } = useParams<{ id: string }>();
  const id = idProp ?? idParam;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser, hatRecht } = useAuth();
  const kannLoeschen = currentUser?.role === "loesch_operativ";
  const kannAbrechnen = hatRecht("abrechnung", "erstellen");
  const [gutschriftOffen, setGutschriftOffen] = useState(false);
  const [showForm, setShowForm] = useState(false);
  const [showVorgang, setShowVorgang] = useState(false);
  const [form, setForm] = useState({ beschreibung: "", menge: "1", einheit: "Stk", einzelpreis: "0" });
  const [lvAuswahl, setLvAuswahl] = useState("");
  const [steuerNeu, setSteuerNeu] = useState<SteuerEingabe | null>(null);
  const [steuerBearbeitung, setSteuerBearbeitung] = useState<{ positionId: string; eingabe: SteuerEingabe } | null>(null);
  const [showZahlungForm, setShowZahlungForm] = useState(false);
  const [zahlungBetrag, setZahlungBetrag] = useState("");
  const [zahlungDatum, setZahlungDatum] = useState(heuteIso());
  const [zahlungsart, setZahlungsart] = useState<RechnungZahlungsart | "">("");

  const deleteMutation = useMutation({
    mutationFn: () => rechnungenApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
      navigate("/feed");
    },
  });

  const {
    data: rechnung,
    isError: rechnungIstFehler,
    error: rechnungFehler,
  } = useQuery({
    queryKey: ["rechnung", id],
    queryFn: () => rechnungenApi.get(id!),
    enabled: !!id,
    retry: false,
  });
  const { data: kunde } = useQuery({
    queryKey: ["kunde", rechnung?.kunde_id],
    queryFn: () => kundenApi.get(rechnung!.kunde_id),
    enabled: !!rechnung,
  });
  // Die Einstellungen sind nur für mandant_admin lesbar; für alle anderen
  // erkennt die Seite den Kleinunternehmer an den bereits erzwungenen
  // Positionen (kleinunternehmer_aus_positionen weiter unten).
  const { data: einstellungen } = useQuery({
    queryKey: ["mandant-einstellungen"],
    queryFn: mandantEinstellungenApi.get,
    enabled: currentUser?.role === "mandant_admin",
    retry: false,
  });
  const { data: leistungsverzeichnis } = useQuery({
    queryKey: ["leistungsverzeichnis", rechnung?.kunde_id],
    queryFn: () => leistungsverzeichnisApi.list(rechnung!.kunde_id),
    enabled: showForm && !!rechnung,
  });
  const { data: storniertRechnung } = useQuery({
    queryKey: ["rechnung", rechnung?.storniert_rechnung_id],
    queryFn: () => rechnungenApi.get(rechnung!.storniert_rechnung_id!),
    enabled: !!rechnung?.storniert_rechnung_id,
  });

  const { data: bezugRechnung } = useQuery({
    queryKey: ["rechnung", rechnung?.bezug_rechnung_id],
    queryFn: () => rechnungenApi.get(rechnung!.bezug_rechnung_id!),
    enabled: !!rechnung?.bezug_rechnung_id,
  });
  // Abschläge stehen am Angebot; ohne Leserecht dort bleibt der Button
  // sichtbar und der Server entscheidet (409 mit Klartext).
  const anrechenbarPruefen =
    !!rechnung &&
    rechnung.status === "entwurf" &&
    !!rechnung.angebot_id &&
    (rechnungsartVon(rechnung) === "rechnung" || rechnungsartVon(rechnung) === "schluss");
  const { data: bezugAngebot, isError: bezugAngebotFehler } = useQuery({
    queryKey: ["angebot", rechnung?.angebot_id],
    queryFn: () => angeboteApi.get(rechnung!.angebot_id!),
    enabled: anrechenbarPruefen,
    retry: false,
  });

  const kleinunternehmer =
    einstellungen?.firmendaten.ist_kleinunternehmer === true ||
    (rechnung?.positionen ?? []).some((p) => p.steuer_grund === "kleinunternehmer_19");

  const statusMutation = useMutation({
    mutationFn: (status: string) => rechnungenApi.updateStatus(id!, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rechnung", id] }),
  });

  const stornoMutation = useMutation({
    mutationFn: () => rechnungenApi.storno(id!),
    onSuccess: (storno) => {
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
      navigate(`/rechnungen/${storno.id}`);
    },
  });

  const anrechnenMutation = useMutation({
    mutationFn: () => rechnungenApi.abschlaegeAnrechnen(id!),
    onSuccess: (aktualisiert) => {
      queryClient.setQueryData(["rechnung", id], aktualisiert);
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
      queryClient.invalidateQueries({ queryKey: ["angebot", aktualisiert.angebot_id] });
    },
  });

  const addPositionMutation = useMutation({
    mutationFn: () =>
      rechnungenApi.addPosition(id!, {
        beschreibung: form.beschreibung,
        menge: form.menge,
        einheit: form.einheit,
        einzelpreis: form.einzelpreis,
        ...(kleinunternehmer || !steuerNeu ? {} : optionZuFelder(steuerNeu.option, steuerNeu.text)),
      }),
    onSuccess: () => {
      setShowForm(false);
      setSteuerNeu(null);
      setForm({ beschreibung: "", menge: "1", einheit: "Stk", einzelpreis: "0" });
      setLvAuswahl("");
      queryClient.invalidateQueries({ queryKey: ["rechnung", id] });
    },
  });

  const removePositionMutation = useMutation({
    mutationFn: (positionId: string) => rechnungenApi.removePosition(id!, positionId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rechnung", id] }),
  });

  const updatePositionMutation = useMutation({
    mutationFn: ({ positionId, einzelpreis }: { positionId: string; einzelpreis: string }) =>
      rechnungenApi.updatePosition(id!, positionId, { einzelpreis }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rechnung", id] }),
  });

  const steuerSpeichernMutation = useMutation({
    mutationFn: ({ positionId, eingabe }: { positionId: string; eingabe: SteuerEingabe }) =>
      rechnungenApi.updatePosition(id!, positionId, optionZuFelder(eingabe.option, eingabe.text)),
    onSuccess: () => {
      setSteuerBearbeitung(null);
      queryClient.invalidateQueries({ queryKey: ["rechnung", id] });
    },
  });

  const pdfMutation = useMutation({
    mutationFn: () => rechnungenApi.pdf(id!),
    onSuccess: openPdfBlob,
  });

  const xmlMutation = useMutation({
    mutationFn: () => rechnungenApi.xml(id!),
    onSuccess: (blob) => downloadBlob(blob, "factur-x.xml"),
  });

  const addZahlungMutation = useMutation({
    mutationFn: () =>
      rechnungenApi.addZahlung(id!, {
        betrag: zahlungBetrag,
        datum: zahlungDatum,
        zahlungsart: zahlungsart || undefined,
      }),
    onSuccess: () => {
      setShowZahlungForm(false);
      setZahlungBetrag("");
      setZahlungsart("");
      queryClient.invalidateQueries({ queryKey: ["rechnung", id] });
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
    },
  });

  const stornoZahlungMutation = useMutation({
    mutationFn: (zahlungId: string) => rechnungenApi.stornoZahlung(id!, zahlungId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rechnung", id] });
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
    },
  });

  if (rechnungIstFehler) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        <EmptyState
          icon={Ban}
          text={
            rechnungFehler instanceof ApiError && rechnungFehler.status === 404
              ? "Rechnung nicht gefunden oder kein Zugriff."
              : "Rechnung konnte nicht geladen werden."
          }
        />
      </div>
    );
  }
  if (!rechnung) return <p className="text-center text-label2">Lädt…</p>;

  const art = rechnungsartVon(rechnung);
  const istGutschrift = art === "gutschrift";
  const angerechneteIds = new Set((rechnung.angerechnete_abschlaege ?? []).map((a) => a.rechnung_id));
  const hatAnrechenbare =
    anrechenbarPruefen &&
    (bezugAngebotFehler ||
      (!!bezugAngebot &&
        (!bezugAngebot.schlussrechnung_id || bezugAngebot.schlussrechnung_id === rechnung.id) &&
        (bezugAngebot.abschlaege ?? []).some((a) => a.status !== "entwurf" && !angerechneteIds.has(a.rechnung_id))));
  const kannGutschrift = kannAbrechnen && kannGutschriftErstellen(rechnung);
  const { ohneVorgang, gruppen } = gruppierePositionen(rechnung.positionen, rechnung.vorgaenge ?? []);
  const renderPosition = (p: RechnungPosition) => {
    const bearbeitet = steuerBearbeitung?.positionId === p.id ? steuerBearbeitung : null;
    // Abzugspositionen kommen aus der Anrechnung; der Server lehnt Änderungen ab (409),
    // nur Entfernen (hebt die Anrechnung auf) ist im Entwurf erlaubt.
    const abzug = istAbzugsposition(p);
    return (
            <div key={p.id} className="space-y-1.5">
              <div className="flex items-center justify-between rounded-md bg-fill p-2 text-sm">
                <div>
                  <div className="text-label">
                    {abzug && (
                      <span className="mr-1.5 inline-block rounded-[var(--radius-ap-pill)] bg-fill2 px-2 py-0.5 text-xs font-medium text-label">
                        Abzug
                      </span>
                    )}
                    {p.beschreibung}
                  </div>
                  <div className="flex items-center gap-1 text-xs text-label2">
                    {p.menge} {p.einheit} ×{" "}
                    {rechnung.status === "entwurf" && !abzug ? (
                      <EinzelpreisFeld
                        wert={p.einzelpreis}
                        disabled={updatePositionMutation.isPending}
                        onSpeichern={(einzelpreis) =>
                          updatePositionMutation.mutate({ positionId: p.id, einzelpreis })
                        }
                      />
                    ) : (
                      p.einzelpreis
                    )}{" "}
                    EUR
                  </div>
                  <div className="mt-1">
                    {rechnung.status === "entwurf" && !kleinunternehmer && !abzug ? (
                      <button
                        type="button"
                        onClick={() =>
                          setSteuerBearbeitung(
                            bearbeitet
                              ? null
                              : {
                                  positionId: p.id,
                                  eingabe: positionZuEingabe(p) ?? vorbelegung(rechnung.mwst_satz),
                                },
                          )
                        }
                        aria-expanded={!!bearbeitet}
                        aria-label={`Steuer ändern: ${steuerKurzlabel(p)}`}
                        className="btn-touch inline-flex items-center gap-1 rounded-[var(--radius-ap-pill)] bg-fill px-2 py-0.5 text-xs font-medium text-label"
                      >
                        Steuer: {steuerKurzlabel(p)}
                        <ChevronDown size={12} strokeWidth={2} aria-hidden="true" />
                      </button>
                    ) : (
                      <span
                        title={p.steuer_grund_text ?? undefined}
                        className="inline-flex items-center rounded-[var(--radius-ap-pill)] bg-fill2 px-2 py-0.5 text-xs font-medium text-label"
                      >
                        Steuer: {steuerKurzlabel(p)}
                      </span>
                    )}
                  </div>
                  {rechnung.status === "entwurf" && p.steuer_kategorie === "E" && !p.steuer_grund && (
                    <div className="mt-0.5 text-xs font-medium text-st-arbeit">
                      Steuergrund fehlt – vor dem Versand angeben
                    </div>
                  )}
                  {abzug && rechnung.status === "entwurf" && (
                    <div className="mt-0.5 text-xs text-label2">Entfernen hebt die Anrechnung auf.</div>
                  )}
                  {(p.quelle === "zeit" || p.quelle === "fahrzeit") && Number(p.einzelpreis) === 0 && (
                    <div className="mt-0.5 text-xs font-medium text-st-arbeit">
                      {p.quelle === "fahrzeit"
                        ? "Fahrzeit-Satz fehlt – in den Einstellungen hinterlegen"
                        : "Stundensatz fehlt"}
                    </div>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <div className="font-medium text-label">{p.gesamt} EUR</div>
                  {rechnung.status === "entwurf" && (
                    <button
                      onClick={() => removePositionMutation.mutate(p.id)}
                      disabled={removePositionMutation.isPending}
                      title={abzug ? "Abzug entfernen – Anrechnung wird aufgehoben" : "Position entfernen"}
                      aria-label={
                        abzug ? `Abzug entfernen: ${p.beschreibung} – Anrechnung wird aufgehoben` : "Position entfernen"
                      }
                      className="btn-touch p-1 text-label2 hover:text-st-fehlt disabled:opacity-50"
                    >
                      <X size={14} strokeWidth={2} />
                    </button>
                  )}
                </div>
              </div>
              {bearbeitet && (
                <div className="card-ap space-y-2 p-3">
                  <SteuerAuswahl
                    wert={bearbeitet.eingabe}
                    onChange={(eingabe) => setSteuerBearbeitung({ positionId: p.id, eingabe })}
                    kunde={kunde}
                    leistungsdatum={rechnung.leistungsdatum}
                  />
                  {steuerSpeichernMutation.isError && (
                    <FehlerMeldung
                      alsKasten
                      meldung={
                        steuerSpeichernMutation.error instanceof ApiError
                          ? steuerSpeichernMutation.error.message
                          : "Steuer konnte nicht gespeichert werden"
                      }
                    />
                  )}
                  <div className="flex gap-2">
                    <button
                      type="button"
                      disabled={!!validiereSteuer(bearbeitet.eingabe) || steuerSpeichernMutation.isPending}
                      onClick={() =>
                        steuerSpeichernMutation.mutate({ positionId: p.id, eingabe: bearbeitet.eingabe })
                      }
                      className="btn-touch flex-1 rounded-md btn-ap-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                    >
                      Steuer speichern
                    </button>
                    <button
                      type="button"
                      onClick={() => {
                        steuerSpeichernMutation.reset();
                        setSteuerBearbeitung(null);
                      }}
                      className="btn-touch px-2 text-sm font-medium text-label2"
                    >
                      Abbrechen
                    </button>
                  </div>
                </div>
              )}
            </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        {kannLoeschen && (
          <button
            onClick={() => {
              if (window.confirm("Rechnung wirklich löschen? Sie wandert in den Papierkorb.")) {
                deleteMutation.mutate();
              }
            }}
            disabled={deleteMutation.isPending}
            className="btn-touch text-sm font-medium text-st-fehlt disabled:opacity-50 "
          >
            Rechnung löschen
          </button>
        )}
      </div>

      {rechnung.ist_storno && (
        <div className="rounded-lg bg-st-arbeit-bg p-3 text-sm text-st-arbeit ">
          Diese Rechnung storniert{" "}
          {storniertRechnung ? (
            <button
              onClick={() => navigate(`/rechnungen/${storniertRechnung.id}`)}
              className="btn-touch underline-offset-2 hover:underline"
            >
              {storniertRechnung.rechnungsnummer}
            </button>
          ) : (
            "eine andere Rechnung"
          )}
          .
        </div>
      )}

      {rechnung.xml_object_key && (
        <div className="rounded-lg bg-st-erledigt-bg p-3 text-sm text-st-erledigt ">
          ZUGFeRD-Rechnung — diese PDF enthält eine eingebettete E-Rechnungs-XML.
        </div>
      )}

      <div className="card-ap p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-label2">{rechnung.rechnungsnummer}</div>
            <h1 className="text-lg font-bold text-label">{kunde?.name ?? "…"}</h1>
          </div>
          <div className="flex flex-wrap items-start justify-end gap-1.5">
            {art !== "rechnung" && <StatusBadge label={RECHNUNGSART_LABEL[art]} tone={RECHNUNGSART_TONE[art]} />}
            <span className="border border-sep px-2 py-1 text-xs font-semibold text-label">
              {RECHNUNG_STATUS_LABEL[rechnung.status]}
            </span>
          </div>
        </div>
        {istGutschrift && (
          <div className="mt-2 space-y-0.5 text-sm">
            {rechnung.gutschrift_grund && (
              <p className="text-label">
                <span className="text-label2">Grund: </span>
                {rechnung.gutschrift_grund}
              </p>
            )}
            {rechnung.bezug_rechnung_id && (
              <p className="text-label2">
                Zu Rechnung{" "}
                <Link to={`/rechnungen/${rechnung.bezug_rechnung_id}`} className="font-medium text-tint-text">
                  {bezugRechnung?.rechnungsnummer ?? "anzeigen"}
                </Link>
              </p>
            )}
          </div>
        )}
        {rechnung.leistungsdatum && (
          <p className="mt-1 text-xs text-label2">
            Leistungsdatum {new Date(rechnung.leistungsdatum).toLocaleDateString("de-DE")}
          </p>
        )}
        {rechnung.faellig_am && (
          <p className="mt-1 text-xs text-label2">
            Fällig am {new Date(rechnung.faellig_am).toLocaleDateString("de-DE")}
          </p>
        )}
        {rechnung.mahnstufe > 0 && (
          <p className="mt-1 text-xs font-semibold text-st-fehlt ">
            {rechnung.mahnstufe}. Mahnung
            {rechnung.letzte_mahnung_am &&
              ` am ${new Date(rechnung.letzte_mahnung_am).toLocaleDateString("de-DE")}`}
          </p>
        )}

        <RechnungSummen rechnung={rechnung} />
        {rechnung.status !== "entwurf" && rechnung.status !== "storniert" && (
          <div className="mt-1 text-right text-xs text-label2">
            {istGutschrift ? (
              <>
                Guthaben: {offenAnzeige(rechnung.offener_betrag)} EUR
              </>
            ) : (
              <>
                Bezahlt: {rechnung.bezahlter_betrag} EUR · {offenLabel(rechnung.offener_betrag)}:{" "}
                {offenAnzeige(rechnung.offener_betrag)} EUR
              </>
            )}
          </div>
        )}

        <div className="mt-3 flex items-center gap-2">
          <button
            onClick={() => pdfMutation.mutate()}
            disabled={pdfMutation.isPending}
            className="btn-touch flex items-center justify-center gap-1 rounded-md bg-fill px-3 py-1.5 text-sm font-medium text-label disabled:opacity-50 "
          >
            <FileText size={14} strokeWidth={2} /> PDF anzeigen
          </button>
          {rechnung.xml_object_key && (
            <button
              onClick={() => xmlMutation.mutate()}
              disabled={xmlMutation.isPending}
              className="btn-touch flex items-center justify-center gap-1 rounded-md bg-fill px-3 py-1.5 text-sm font-medium text-label disabled:opacity-50 "
            >
              <FileText size={14} strokeWidth={2} /> XML herunterladen
            </button>
          )}
        </div>
      </div>

      {art === "schluss" && (rechnung.angerechnete_abschlaege ?? []).length > 0 && (
        <div className="card-ap p-4">
          <h2 className="mb-2 text-sm font-semibold text-label2">Angerechnete Abschlagsrechnungen</h2>
          <ul className="space-y-1.5">
            {(rechnung.angerechnete_abschlaege ?? []).map((a) => (
              <li key={a.rechnung_id}>
                <Link
                  to={`/rechnungen/${a.rechnung_id}`}
                  className="btn-touch flex items-center justify-between gap-2 rounded-md bg-fill p-2 text-sm"
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-label">{a.rechnungsnummer}</span>
                    <span className="block text-xs text-label2">vom {new Date(a.datum).toLocaleDateString("de-DE")}</span>
                  </span>
                  <span className="shrink-0 tabular-nums font-medium text-label">{formatEuro(a.netto)} netto</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {(rechnung.gutschriften ?? []).length > 0 && (
        <div className="card-ap p-4">
          <h2 className="mb-2 text-sm font-semibold text-label2">Gutschriften</h2>
          <ul className="space-y-1.5">
            {(rechnung.gutschriften ?? []).map((g) => (
              <li key={g.rechnung_id}>
                <Link
                  to={`/rechnungen/${g.rechnung_id}`}
                  className="btn-touch flex items-center justify-between gap-2 rounded-md bg-fill p-2 text-sm"
                >
                  <span className="truncate font-medium text-label">{g.rechnungsnummer}</span>
                  <span className="shrink-0 tabular-nums font-medium text-st-fehlt">{formatEuro(g.brutto)}</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      <div className="card-ap p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-label2">Positionen</h2>
          {rechnung.status === "entwurf" && (
            <div className="flex flex-wrap items-center justify-end gap-3">
              {hatAnrechenbare && kannAbrechnen && (
                <button
                  type="button"
                  onClick={() => anrechnenMutation.mutate()}
                  disabled={anrechnenMutation.isPending}
                  className="btn-touch text-xs font-medium text-tint-text disabled:opacity-50"
                >
                  Abschläge anrechnen
                </button>
              )}
              <button
                onClick={() => setShowVorgang(true)}
                className="btn-touch text-xs font-medium text-tint-text"
              >
                + Vorgang
              </button>
              <button
                onClick={() => {
                  setSteuerNeu(vorbelegung(rechnung.mwst_satz));
                  setShowForm((v) => !v);
                }}
                className="btn-touch text-xs font-medium text-tint-text"
              >
                {showForm ? "Abbrechen" : "+ Position"}
              </button>
            </div>
          )}
        </div>

        {anrechnenMutation.isError && (
          <div className="mb-2">
            <FehlerMeldung
              alsKasten
              meldung={
                anrechnenMutation.error instanceof ApiError
                  ? anrechnenMutation.error.message
                  : "Abschläge konnten nicht angerechnet werden"
              }
            />
          </div>
        )}

        {rechnung.status === "entwurf" && rechnung.vorgang_id && (
          <PositionsVorschlaege rechnungId={id!} vorgangId={rechnung.vorgang_id} />
        )}

        {showForm && (
          <div className="mb-3 space-y-2 border border-sepstrong p-3">
            {(leistungsverzeichnis ?? []).length > 0 && (
              <div>
                <label className="mb-1 block text-xs font-medium text-label">
                  Aus Leistungsverzeichnis wählen (optional)
                </label>
                <SearchableSelect
                  value={lvAuswahl}
                  onChange={(v) => {
                    setLvAuswahl(v);
                    const position = (leistungsverzeichnis ?? []).find((p) => p.id === v);
                    if (position) {
                      setForm({
                        beschreibung: position.bezeichnung,
                        menge: "1",
                        einheit: position.einheit,
                        einzelpreis: position.einzelpreis,
                      });
                    }
                  }}
                  placeholder="Position wählen…"
                  options={(leistungsverzeichnis ?? []).map((p) => ({
                    value: p.id,
                    label: p.bezeichnung,
                    sublabel: `${p.einzelpreis} €/${p.einheit}`,
                  }))}
                />
              </div>
            )}
            <input
              value={form.beschreibung}
              onChange={(e) => setForm({ ...form, beschreibung: e.target.value })}
              placeholder="Beschreibung"
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            <div className="grid grid-cols-3 gap-2">
              <input
                type="number"
                step="0.01"
                value={form.menge}
                onChange={(e) => setForm({ ...form, menge: e.target.value })}
                placeholder="Menge"
                className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <input
                value={form.einheit}
                onChange={(e) => setForm({ ...form, einheit: e.target.value })}
                placeholder="Einheit"
                className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <input
                type="number"
                step="0.01"
                value={form.einzelpreis}
                onChange={(e) => setForm({ ...form, einzelpreis: e.target.value })}
                placeholder="Preis"
                className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
            </div>
            {kleinunternehmer ? (
              <Hinweiskasten ton="info">Kleinunternehmer – steuerbefreit nach § 19 UStG</Hinweiskasten>
            ) : (
              steuerNeu && (
                <div>
                  <label className="mb-1 block text-xs font-medium text-label2">Steuer</label>
                  <SteuerAuswahl
                    wert={steuerNeu}
                    onChange={setSteuerNeu}
                    kunde={kunde}
                    leistungsdatum={rechnung.leistungsdatum}
                  />
                </div>
              )
            )}
            {addPositionMutation.isError && (
              <FehlerMeldung
                alsKasten
                meldung={
                  addPositionMutation.error instanceof ApiError
                    ? addPositionMutation.error.message
                    : "Position konnte nicht angelegt werden"
                }
              />
            )}
            <button
              disabled={
                !form.beschreibung ||
                addPositionMutation.isPending ||
                (!kleinunternehmer && !!steuerNeu && !!validiereSteuer(steuerNeu))
              }
              onClick={() => addPositionMutation.mutate()}
              className="btn-touch w-full rounded-md btn-ap-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Hinzufügen
            </button>
          </div>
        )}

        {updatePositionMutation.isError && (
          <p className="mb-2 text-xs text-st-fehlt">
            {updatePositionMutation.error instanceof ApiError
              ? updatePositionMutation.error.message
              : "Preis konnte nicht gespeichert werden"}
          </p>
        )}

        {kleinunternehmer && !showForm && (
          <div className="mb-2">
            <Hinweiskasten ton="info">Kleinunternehmer – steuerbefreit nach § 19 UStG</Hinweiskasten>
          </div>
        )}

        {rechnung.positionen.length === 0 ? (
          <p className="text-sm text-label2">
            Keine eigenen Positionen -- Betrag wurde als Gesamtsumme angelegt.
          </p>
        ) : (
          <div className="space-y-1.5">
            {ohneVorgang.map(renderPosition)}
            {gruppen.map((g) => (
              <div key={g.vorgang.id} className="space-y-1.5 pt-2">
                <p className="text-[13px] font-semibold tracking-wide text-label2">
                  {g.vorgang.vorgangsnummer} · {g.vorgang.titel}
                </p>
                {g.positionen.map(renderPosition)}
                <div className="text-right text-xs font-semibold text-label">Zwischensumme: {g.zwischensumme} EUR</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {!istGutschrift &&
        (rechnung.status === "versendet" ||
          rechnung.status === "teilweise_bezahlt" ||
          rechnung.status === "bezahlt") && (
        <div className="card-ap p-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-label2">Zahlungen</h2>
            {(rechnung.status === "versendet" || rechnung.status === "teilweise_bezahlt") && (
              <button
                onClick={() => {
                  setZahlungBetrag(rechnung.offener_betrag);
                  setShowZahlungForm((v) => !v);
                }}
                className="btn-touch text-xs font-medium text-tint "
              >
                {showZahlungForm ? "Abbrechen" : "+ Zahlung"}
              </button>
            )}
          </div>

          {showZahlungForm && (
            <div className="mb-3 space-y-2 border border-sepstrong p-3">
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="number"
                  step="0.01"
                  value={zahlungBetrag}
                  onChange={(e) => setZahlungBetrag(e.target.value)}
                  placeholder="Betrag"
                  className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                />
                <input
                  type="date"
                  value={zahlungDatum}
                  onChange={(e) => setZahlungDatum(e.target.value)}
                  max={heuteIso()}
                  className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                />
              </div>
              <select
                value={zahlungsart}
                onChange={(e) => setZahlungsart(e.target.value as RechnungZahlungsart | "")}
                className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              >
                <option value="">Zahlungsart (optional)</option>
                {ZAHLUNGSART_OPTIONEN.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              {addZahlungMutation.isError && (
                <p className="text-xs text-st-fehlt ">
                  Zahlung übersteigt den offenen Betrag oder ist ungültig.
                </p>
              )}
              <button
                disabled={!zahlungBetrag || addZahlungMutation.isPending}
                onClick={() => addZahlungMutation.mutate()}
                className="btn-touch w-full rounded-md btn-ap-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
              >
                Zahlung erfassen
              </button>
            </div>
          )}

          {rechnung.zahlungen.length === 0 ? (
            <p className="text-sm text-label2">Noch keine Zahlung erfasst.</p>
          ) : (
            <div className="space-y-1.5">
              {(() => {
                const bereitsStorniert = new Set(
                  rechnung.zahlungen.map((z) => z.storniert_zahlung_id).filter((v): v is string => v !== null),
                );
                return rechnung.zahlungen.map((z) => (
                  <div
                    key={z.id}
                    className="flex items-center justify-between rounded-md bg-fill p-2 text-sm"
                  >
                    <span className="text-label2">
                      {new Date(z.datum).toLocaleDateString("de-DE")}
                      {z.zahlungsart && ` · ${z.zahlungsart}`}
                    </span>
                    <div className="flex items-center gap-2">
                      <span
                        className={`font-medium ${
                          Number(z.betrag) < 0
                            ? "text-st-fehlt "
                            : "text-label"
                        }`}
                      >
                        {z.betrag} EUR
                      </span>
                      {Number(z.betrag) > 0 && rechnung.status !== "storniert" && !bereitsStorniert.has(z.id) && (
                        <button
                          onClick={() => {
                            if (window.confirm("Diese Zahlung stornieren?")) stornoZahlungMutation.mutate(z.id);
                          }}
                          disabled={stornoZahlungMutation.isPending}
                          className="btn-touch text-xs text-label2 underline-offset-2 hover:underline disabled:opacity-50"
                        >
                          Storno
                        </button>
                      )}
                    </div>
                  </div>
                ));
              })()}
            </div>
          )}
        </div>
      )}

      {rechnung.status === "entwurf" && (
        <VorgangHinzufuegen
          rechnungId={id!}
          kundeId={rechnung.kunde_id}
          offen={showVorgang}
          onClose={() => setShowVorgang(false)}
        />
      )}

      <EmailSection
        queryKey={["rechnung-emails", id]}
        listEmails={() => rechnungenApi.emails(id!)}
        sendEmail={(body) => rechnungenApi.sendEmail(id!, body)}
        defaultEmpfaenger={kunde?.ansprechpartner.find((a) => a.email)?.email ?? undefined}
        betreffPflicht={false}
        hinweis="Die Rechnung wird als PDF-Anhang mitgesendet."
      />

      {statusMutation.isError && (
        <FehlerMeldung
          alsKasten
          meldung={
            statusMutation.error instanceof ApiError
              ? statusMutation.error.message
              : "Status konnte nicht geändert werden"
          }
        />
      )}

      {stornoMutation.isError && (
        <FehlerMeldung
          alsKasten
          meldung={
            stornoMutation.error instanceof ApiError ? stornoMutation.error.message : "Stornierung fehlgeschlagen"
          }
        />
      )}

      {rechnung.status === "entwurf" && (
        <div className="flex gap-2">
          <button
            onClick={() => statusMutation.mutate("versendet")}
            disabled={statusMutation.isPending}
            className="btn-touch flex-1 rounded-md btn-ap-primary px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            An Kunden senden
          </button>
          <button
            onClick={() => statusMutation.mutate("storniert")}
            disabled={statusMutation.isPending}
            className="btn-touch rounded-md bg-fill px-4 py-2 text-sm font-medium text-label disabled:opacity-50 "
          >
            Stornieren
          </button>
        </div>
      )}
      {kannGutschrift && (
        <button
          type="button"
          onClick={() => setGutschriftOffen(true)}
          className="btn-touch w-full btn-ap px-4 py-2 text-sm font-medium"
        >
          Gutschrift erstellen
        </button>
      )}
      {(rechnung.status === "versendet" || rechnung.status === "teilweise_bezahlt") && (
        <div className="flex gap-2">
          {!istGutschrift && (
            <button
              onClick={() => statusMutation.mutate("bezahlt")}
              disabled={statusMutation.isPending}
              className="btn-touch flex-1 rounded-md bg-st-erledigt-dot px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              Als bezahlt markieren
            </button>
          )}
          <button
            onClick={() => {
              if (window.confirm("Diese Rechnung stornieren? Es wird eine Stornorechnung mit eigener Nummer erzeugt."))
                stornoMutation.mutate();
            }}
            disabled={stornoMutation.isPending}
            className={`btn-touch rounded-md bg-fill px-4 py-2 text-sm font-medium text-label disabled:opacity-50 ${
              istGutschrift ? "flex-1" : ""
            }`}
          >
            Stornieren
          </button>
        </div>
      )}
      {rechnung.status === "bezahlt" && !rechnung.ist_storno && (
        <button
          onClick={() => {
            if (window.confirm("Diese bereits bezahlte Rechnung stornieren? Es wird eine Stornorechnung mit eigener Nummer erzeugt."))
              stornoMutation.mutate();
          }}
          disabled={stornoMutation.isPending}
          className="btn-touch w-full rounded-md bg-fill px-4 py-2 text-sm font-medium text-label disabled:opacity-50 "
        >
          Stornieren
        </button>
      )}

      {gutschriftOffen && (
        <GutschriftSheet
          rechnung={rechnung}
          onClose={() => setGutschriftOffen(false)}
          onErstellt={(gutschrift) => {
            setGutschriftOffen(false);
            navigate(`/rechnungen/${gutschrift.id}`);
          }}
        />
      )}
    </div>
  );
}
