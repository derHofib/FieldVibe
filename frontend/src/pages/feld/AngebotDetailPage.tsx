import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, ChevronDown, ChevronUp, FileText } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { angeboteApi, kundenApi, mandantEinstellungenApi } from "../../api/endpoints";
import { AngebotAbrechnung } from "../../components/angebot/AngebotAbrechnung";
import { AngebotLvUebernahme } from "../../components/angebot/AngebotLvUebernahme";
import { AngebotNachweis } from "../../components/angebot/AngebotNachweis";
import { AngebotPositionSheet } from "../../components/angebot/AngebotPositionSheet";
import { GueltigkeitSheet } from "../../components/angebot/GueltigkeitSheet";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { StatusPille } from "../../components/apple/StatusPille";
import { EmailSection } from "../../components/EmailSection";
import { EmptyState } from "../../components/EmptyState";
import { FehlerMeldung, Hinweiskasten } from "../../components/Hinweiskasten";
import { useAuth } from "../../context/AuthContext";
import {
  ANGEBOT_STATUS_LABEL,
  ANGEBOT_STATUS_TOKEN,
  MWST_SAETZE,
  ablaufAnzeige,
  ablaufText,
  mwstSatzWert,
  verschiebePosition,
} from "../../utils/angebot";
import { formatIsoTag, heuteIso } from "../../utils/format";
import { openPdfBlob } from "../../utils/pdf";
import type { AngebotMwstSatz, AngebotPosition, AngebotPositionstyp } from "../../types";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { DetailSkeleton } from "../../components/Skeleton";

const POSITIONSTYP_LABEL: Record<AngebotPositionstyp, string> = {
  material: "Material",
  arbeitszeit: "Arbeitszeit",
};

interface NeuePosition {
  artikelnummer: string;
  beschreibung: string;
  menge: string;
  einheit: string;
  einzelpreis: string;
  positionstyp: AngebotPositionstyp;
}

function PositionInhalt({ p }: { p: AngebotPosition }) {
  return (
    <>
      <div className="text-label">
        {p.positionstyp === "arbeitszeit" && (
          <span className="mr-1.5 border rounded-[var(--radius-ap-pill)] border-st-arbeit px-1.5 py-0.5 text-meta text-st-arbeit ">
            {POSITIONSTYP_LABEL.arbeitszeit}
          </span>
        )}
        {p.ordnungszahl && <span className="mr-1.5 text-meta text-label2">{p.ordnungszahl}</span>}
        {p.artikelnummer && <span className="mr-1.5 text-meta text-label2">{p.artikelnummer}</span>}
        {p.beschreibung}
      </div>
      <div className="text-sekundaer text-label2">
        {p.menge} {p.einheit} × {p.einzelpreis} EUR
        {p.einzelpreis_lohn !== null && p.einzelpreis_material !== null && (
          <> (Lohn {p.einzelpreis_lohn} · Material {p.einzelpreis_material})</>
        )}
      </div>
    </>
  );
}

// id optional als Prop, damit die Office-Oberflaeche diese Seite in ihrem
// Detail-Panel einbetten kann, ohne dass es einen zweiten, parallel zu
// pflegenden Nachbau braucht. Ohne Prop verhaelt sie sich wie bisher.
export function AngebotDetailPage({ id: idProp }: { id?: string } = {}) {
  const bestaetigen = useBestaetigung();
  const { id: idParam } = useParams<{ id: string }>();
  const id = idProp ?? idParam;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser, hatRecht } = useAuth();
  const kannAbrechnen = hatRecht("abrechnung", "erstellen");
  const kannLoeschen = currentUser?.role === "loesch_operativ";
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<NeuePosition>({
    artikelnummer: "",
    beschreibung: "",
    menge: "1",
    einheit: "Stk",
    einzelpreis: "0",
    positionstyp: "material",
  });
  const [lvOffen, setLvOffen] = useState(false);
  const [titelText, setTitelText] = useState<string | null>(null);
  const [bearbeitetePosition, setBearbeitetePosition] = useState<AngebotPosition | null>(null);
  const [gueltigkeitOffen, setGueltigkeitOffen] = useState(false);

  const deleteMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: () => angeboteApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["angebote"] });
      navigate("/feed");
    },
  });

  const {
    data: angebot,
    isError: angebotIstFehler,
    error: angebotFehler,
  } = useQuery({
    queryKey: ["angebot", id],
    queryFn: () => angeboteApi.get(id!),
    enabled: !!id,
    retry: false,
  });
  const { data: kunde } = useQuery({
    queryKey: ["kunde", angebot?.kunde_id],
    queryFn: () => kundenApi.get(angebot!.kunde_id),
    enabled: !!angebot,
  });
  // Die Einstellungen sind nur fuer mandant_admin lesbar; fuer alle anderen
  // erzwingt das Backend den Satz 0 % beim Kleinunternehmer ohnehin.
  const { data: einstellungen } = useQuery({
    queryKey: ["mandant-einstellungen"],
    queryFn: mandantEinstellungenApi.get,
    enabled: currentUser?.role === "mandant_admin",
    retry: false,
  });
  const kleinunternehmer = einstellungen?.firmendaten.ist_kleinunternehmer === true;
  const addPositionMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () =>
      angeboteApi.addPosition(id!, {
        artikelnummer: form.artikelnummer || undefined,
        beschreibung: form.beschreibung,
        menge: form.menge,
        einheit: form.einheit,
        einzelpreis: form.einzelpreis,
        positionstyp: form.positionstyp,
      }),
    onSuccess: () => {
      setShowForm(false);
      setForm({
        artikelnummer: "",
        beschreibung: "",
        menge: "1",
        einheit: "Stk",
        einzelpreis: "0",
        positionstyp: "material",
      });
      queryClient.invalidateQueries({ queryKey: ["angebot", id] });
    },
  });

  const addTitelMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: (ebene: 1 | 2) =>
      angeboteApi.addPosition(id!, {
        beschreibung: titelText!.trim(),
        menge: "0",
        einheit: "",
        einzelpreis: "0",
        zeilentyp: "titel",
        ebene,
      }),
    onSuccess: () => {
      setTitelText(null);
      queryClient.invalidateQueries({ queryKey: ["angebot", id] });
    },
  });

  const statusMutation = useMutation({
    meta: { erfolg: "Status geändert" },
    mutationFn: (status: string) => angeboteApi.updateStatus(id!, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["angebot", id] }),
  });

  const aktualisiert = () => {
    queryClient.invalidateQueries({ queryKey: ["angebot", id] });
    queryClient.invalidateQueries({ queryKey: ["angebote"] });
  };

  const neuOrdnenMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: (positionIds: string[]) => angeboteApi.positionenNeuOrdnen(id!, positionIds),
    onSuccess: aktualisiert,
  });

  const mwstMutation = useMutation({
    mutationFn: (satz: AngebotMwstSatz) => angeboteApi.update(id!, { mwst_satz: satz }),
    onSuccess: aktualisiert,
  });

  const pdfMutation = useMutation({
    mutationFn: () => angeboteApi.pdf(id!),
    onSuccess: openPdfBlob,
  });

  if (angebotIstFehler) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="text-sekundaer text-label2">
          ← Zurück
        </button>
        <EmptyState
          icon={Ban}
          text={
            angebotFehler instanceof ApiError && angebotFehler.status === 404
              ? "Angebot nicht gefunden oder kein Zugriff."
              : "Angebot konnte nicht geladen werden."
          }
        />
      </div>
    );
  }
  if (!angebot) return <DetailSkeleton />;

  const istEntwurf = angebot.status === "entwurf";
  const ablauf = ablaufAnzeige(angebot, heuteIso());
  const positionIds = angebot.positionen.map((p) => p.id);
  const mutationFehler = [statusMutation, neuOrdnenMutation, mwstMutation, addTitelMutation]
    .map((m) => (m.error instanceof ApiError ? m.error.message : m.isError ? "Aktion fehlgeschlagen" : null))
    .find(Boolean);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sekundaer text-label2">
          ← Zurück
        </button>
        {kannLoeschen && (
          <button
            onClick={async () => {
              if (await bestaetigen({ titel: "Angebot löschen?", text: "Es wandert in den Papierkorb.", bestaetigenLabel: "Löschen" })) {
                deleteMutation.mutate();
              }
            }}
            disabled={deleteMutation.isPending}
            className="btn-touch text-sekundaer font-medium text-st-fehlt disabled:opacity-50 "
          >
            Angebot löschen
          </button>
        )}
      </div>

      <div className="card-ap p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-meta text-label2">{angebot.angebotsnummer}</div>
            <h1 className="text-titel-mobil font-bold text-label">{kunde?.name ?? "…"}</h1>
          </div>
          <div className="flex flex-wrap justify-end gap-1.5">
            <StatusPille status={ANGEBOT_STATUS_TOKEN[angebot.status]} label={ANGEBOT_STATUS_LABEL[angebot.status]} />
            {ablauf.art === "abgelaufen" && <StatusPille status="arbeit" label="Abgelaufen" />}
          </div>
        </div>
        {angebot.gueltig_bis && (
          <p className="mt-1 text-sekundaer text-label2">
            Gültig bis {formatIsoTag(angebot.gueltig_bis)}
            {ablauf.art === "laeuft_bald_ab" && (
              <span className="font-medium text-st-arbeit"> · {ablaufText(ablauf)}</span>
            )}
            {(istEntwurf || angebot.status === "versendet") && (
              <>
                {" · "}
                <button type="button" onClick={() => setGueltigkeitOffen(true)} className="font-medium text-tint">
                  Ändern
                </button>
              </>
            )}
          </p>
        )}
        {!angebot.gueltig_bis && (istEntwurf || angebot.status === "versendet") && (
          <button type="button" onClick={() => setGueltigkeitOffen(true)} className="mt-1 text-sekundaer font-medium text-tint">
            Gültigkeit festlegen
          </button>
        )}
        <button
          onClick={() => pdfMutation.mutate()}
          disabled={pdfMutation.isPending}
          className="btn-touch mt-3 flex items-center justify-center gap-1 rounded-md bg-fill px-3 py-1.5 text-sekundaer font-medium text-label disabled:opacity-50 "
        >
          <FileText size={14} strokeWidth={2} /> PDF anzeigen
        </button>
      </div>

      {ablauf.art === "abgelaufen" && (
        <Hinweiskasten ton="warnung" titel="Angebot abgelaufen">
          <p>
            Die Gültigkeit endete am {angebot.gueltig_bis ? formatIsoTag(angebot.gueltig_bis) : "—"}. Das Angebot kann
            nicht mehr angenommen werden – auch nicht vom Kunden im Portal.
          </p>
          <button
            type="button"
            onClick={() => setGueltigkeitOffen(true)}
            className="btn-touch mt-1 rounded-md bg-fill px-3 py-1.5 text-sekundaer font-medium text-label"
          >
            Gültigkeit verlängern
          </button>
        </Hinweiskasten>
      )}

      <div className="card-ap p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-fliess font-semibold text-label2">Positionen</h2>
          {istEntwurf && (
            <div className="flex gap-3">
              <button
                onClick={() => setTitelText((t) => (t === null ? "" : null))}
                className="btn-touch text-sekundaer font-medium text-tint "
              >
                {titelText === null ? "+ Titel" : "Abbrechen"}
              </button>
              <button
                onClick={() => setShowForm((v) => !v)}
                className="btn-touch text-sekundaer font-medium text-tint "
              >
                {showForm ? "Abbrechen" : "+ Position"}
              </button>
            </div>
          )}
        </div>

        {istEntwurf && titelText !== null && (
          <div className="mb-3 flex gap-2">
            <input
              value={titelText}
              onChange={(e) => setTitelText(e.target.value)}
              placeholder="Titel, z. B. Elektro Erdgeschoss"
              aria-label="Titel"
              className="min-w-0 flex-1 border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
            <button
              disabled={!titelText.trim() || addTitelMutation.isPending}
              onClick={() => addTitelMutation.mutate(1)}
              className="btn-touch rounded-md btn-ap-primary px-3 py-1.5 text-sekundaer font-medium disabled:opacity-50"
            >
              Hinzufügen
            </button>
          </div>
        )}

        {showForm && (
          <div className="mb-3 space-y-2 border rounded-[var(--radius-ap-card)] border-sepstrong p-3">
            <button
              type="button"
              onClick={() => setLvOffen(true)}
              className="btn-touch w-full rounded-md bg-fill px-3 py-2 text-sekundaer font-medium text-tint"
            >
              Aus Leistungsverzeichnis übernehmen…
            </button>
            <div className="flex gap-1.5">
              {(["material", "arbeitszeit"] as AngebotPositionstyp[]).map((typ) => (
                <button
                  key={typ}
                  type="button"
                  onClick={() => setForm({ ...form, positionstyp: typ })}
                  className={`btn-touch rounded-md px-3 py-1.5 text-sekundaer font-medium ${
                    form.positionstyp === typ
                      ? "bg-tint-solid text-white"
                      : "bg-white text-label ring-1 ring-sep dark:bg-stone-800 "
                  }`}
                >
                  {POSITIONSTYP_LABEL[typ]}
                </button>
              ))}
            </div>
            <input
              value={form.artikelnummer}
              onChange={(e) => setForm({ ...form, artikelnummer: e.target.value })}
              placeholder="Art-Nr. (optional)"
              className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
            <input
              value={form.beschreibung}
              onChange={(e) => setForm({ ...form, beschreibung: e.target.value })}
              placeholder="Beschreibung"
              className="w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
            />
            <div className="grid grid-cols-3 gap-2">
              <input
                type="number"
                step="0.01"
                value={form.menge}
                onChange={(e) => setForm({ ...form, menge: e.target.value })}
                placeholder="Menge"
                className="border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
              />
              <input
                value={form.einheit}
                onChange={(e) => setForm({ ...form, einheit: e.target.value })}
                placeholder="Einheit"
                className="border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
              />
              <input
                type="number"
                step="0.01"
                value={form.einzelpreis}
                onChange={(e) => setForm({ ...form, einzelpreis: e.target.value })}
                placeholder="Preis"
                className="border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-2 py-1.5 text-zeile text-label"
              />
            </div>
            <button
              disabled={!form.beschreibung || addPositionMutation.isPending}
              onClick={() => addPositionMutation.mutate()}
              className="btn-touch w-full rounded-md btn-ap-primary px-3 py-1.5 text-sekundaer font-medium disabled:opacity-50"
            >
              Hinzufügen
            </button>
          </div>
        )}

        {angebot.positionen.length === 0 ? (
          <p className="text-sekundaer text-label2">Noch keine Positionen.</p>
        ) : (
          <div className="space-y-1.5">
            {angebot.positionen.map((p, index) => (
              <div
                key={p.id}
                className={`flex items-center justify-between gap-2 rounded-md bg-fill p-2 text-sekundaer ${
                  p.zeilentyp === "titel" ? "mt-2 font-semibold" : p.ordnungszahl?.includes(".") ? "ml-3" : ""
                }`}
              >
                {istEntwurf ? (
                  <button
                    type="button"
                    onClick={() => setBearbeitetePosition(p)}
                    aria-label={`Position ${p.position} bearbeiten: ${p.beschreibung}`}
                    className="min-w-0 flex-1 text-left"
                  >
                    <PositionInhalt p={p} />
                  </button>
                ) : (
                  <div className="min-w-0 flex-1">
                    <PositionInhalt p={p} />
                  </div>
                )}
                <div className="shrink-0 font-medium text-label">
                  {p.zeilentyp === "titel" ? (p.zwischensumme ? `Σ ${p.zwischensumme} EUR` : "") : `${p.gesamt} EUR`}
                </div>
                {istEntwurf && angebot.positionen.length > 1 && (
                  <div className="flex shrink-0 flex-col">
                    <button
                      type="button"
                      onClick={() => neuOrdnenMutation.mutate(verschiebePosition(positionIds, index, -1))}
                      disabled={index === 0 || neuOrdnenMutation.isPending}
                      aria-label={`Position ${p.position} nach oben`}
                      className="btn-touch p-0.5 text-label2 disabled:opacity-30"
                    >
                      <ChevronUp size={16} strokeWidth={2} />
                    </button>
                    <button
                      type="button"
                      onClick={() => neuOrdnenMutation.mutate(verschiebePosition(positionIds, index, 1))}
                      disabled={index === angebot.positionen.length - 1 || neuOrdnenMutation.isPending}
                      aria-label={`Position ${p.position} nach unten`}
                      className="btn-touch p-0.5 text-label2 disabled:opacity-30"
                    >
                      <ChevronDown size={16} strokeWidth={2} />
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
        {istEntwurf && angebot.positionen.length > 0 && (
          <p className="mt-1.5 text-meta text-label3">Position antippen zum Bearbeiten oder Löschen.</p>
        )}

        <div className="mt-3 space-y-2 border-t border-sep pt-2 text-fliess ">
          {kleinunternehmer ? (
            <Hinweiskasten ton="info">Kleinunternehmer – steuerbefreit nach § 19 UStG</Hinweiskasten>
          ) : istEntwurf ? (
            <div className="flex items-center justify-between gap-2">
              <span className="text-label2">Steuersatz</span>
              <SegmentedControl
                ariaLabel="Steuersatz"
                optionen={MWST_SAETZE}
                wert={mwstSatzWert(angebot.mwst_satz) ?? "19"}
                onChange={(satz) => mwstMutation.mutate(satz)}
                groesse="mobil"
              />
            </div>
          ) : (
            <div className="flex items-center justify-between text-label2">
              <span>Steuersatz</span>
              <span>{Number(angebot.mwst_satz)} %</span>
            </div>
          )}
          <div className="text-right">
            {Number(angebot.summe_lohn) > 0 && Number(angebot.summe_material) > 0 && (
              <div className="text-meta text-label3">
                davon Lohn {angebot.summe_lohn} EUR · Material {angebot.summe_material} EUR
              </div>
            )}
            <div className="text-label2">Netto: {angebot.gesamt_netto} EUR</div>
            <div className="font-semibold text-label">Brutto: {angebot.gesamt_brutto} EUR</div>
          </div>
        </div>
      </div>

      <AngebotNachweis angebot={angebot} />

      {angebot.status === "angenommen" && (
        <AngebotAbrechnung
          angebot={angebot}
          kannErstellen={kannAbrechnen}
          onRechnung={(rechnung) => navigate(`/rechnungen/${rechnung.id}`)}
        />
      )}

      {mutationFehler && <FehlerMeldung meldung={mutationFehler} alsKasten />}

      <EmailSection
        queryKey={["angebot-emails", id]}
        listEmails={() => angeboteApi.emails(id!)}
        sendEmail={(body) => angeboteApi.sendEmail(id!, body)}
        defaultEmpfaenger={kunde?.ansprechpartner.find((a) => a.email)?.email ?? undefined}
        betreffPflicht={false}
        hinweis="Das Angebot wird als PDF-Anhang mitgesendet."
      />

      {istEntwurf && (
        <button
          onClick={() => statusMutation.mutate("versendet")}
          disabled={statusMutation.isPending}
          className="btn-touch w-full rounded-md btn-ap-primary px-4 py-2 text-sekundaer font-medium disabled:opacity-50"
        >
          An Kunden senden
        </button>
      )}
      {angebot.status === "versendet" && (
        <div className="flex gap-2">
          <button
            onClick={() => statusMutation.mutate("angenommen")}
            disabled={statusMutation.isPending || angebot.ist_abgelaufen}
            className="btn-touch flex-1 rounded-md bg-st-erledigt-dot px-4 py-2 text-sekundaer font-medium text-white disabled:opacity-50"
          >
            Angenommen
          </button>
          <button
            onClick={() => statusMutation.mutate("abgelehnt")}
            disabled={statusMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-st-fehlt-dot px-4 py-2 text-sekundaer font-medium text-white disabled:opacity-50"
          >
            Abgelehnt
          </button>
        </div>
      )}
      {angebot.status === "angenommen" && (
        <div className="space-y-1 text-center text-fliess">
          {angebot.auftrag_vorgang_id ? (
            <>
              <p className="text-st-erledigt ">Angebot angenommen.</p>
              <Link
                to={`/vorgaenge/${angebot.auftrag_vorgang_id}`}
                className="btn-touch inline-block font-medium text-tint"
              >
                Zum Auftrag →
              </Link>
            </>
          ) : (
            <p className="text-st-erledigt ">
              Angebot angenommen – ein Reparatur-Vorgang wurde automatisch angelegt (siehe verknüpfte Mängel).
            </p>
          )}
        </div>
      )}

      {bearbeitetePosition && (
        <AngebotPositionSheet
          key={bearbeitetePosition.id}
          angebotId={angebot.id}
          position={bearbeitetePosition}
          onClose={() => setBearbeitetePosition(null)}
        />
      )}
      {lvOffen && (
        <AngebotLvUebernahme
          angebotId={angebot.id}
          kundeId={angebot.kunde_id}
          onClose={() => {
            setLvOffen(false);
            setShowForm(false);
          }}
        />
      )}
      {gueltigkeitOffen && (
        <GueltigkeitSheet
          angebotId={angebot.id}
          aktuell={angebot.gueltig_bis}
          onClose={() => setGueltigkeitOffen(false)}
        />
      )}
    </div>
  );
}
