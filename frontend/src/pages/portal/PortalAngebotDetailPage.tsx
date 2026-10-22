import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { kundenportalApi } from "../../api/endpoints";
import { Hinweiskasten } from "../../components/Hinweiskasten";
import { SkeletonCard } from "../../components/Skeleton";
import { useKundenAuth } from "../../context/KundenAuthContext";
import { datumZeit, widerrufFristLetzterTag } from "../../utils/portalAngebot";
import { openPdfBlob } from "../../utils/pdf";
import type { PortalAngebot, PortalVerbraucherschutz } from "../../types";
import { BelehrungBlock } from "./BelehrungBlock";
import { ANGEBOT_STATUS_BADGE, ANGEBOT_STATUS_ERKLAERUNG, ANGEBOT_STATUS_LABEL } from "./status";
import { bestaetigen } from "../../components/apple/BestaetigungsDialog";

/** Button-Loesung (§ 312j Abs. 3 BGB): Zusammenfassung, Belehrung, Kenntnisnahme
 * und der Button mit dem gesetzlich vorgegebenen Wortlaut. */
function VerbindlichBeauftragen({
  angebot,
  verbraucher,
  onBeauftragen,
  onAblehnen,
  laeuft,
}: {
  angebot: PortalAngebot;
  verbraucher: PortalVerbraucherschutz;
  onBeauftragen: () => void;
  onAblehnen: () => void;
  laeuft: boolean;
}) {
  const [kenntnis, setKenntnis] = useState(false);

  return (
    <>
      <section aria-labelledby="zusammenfassung-titel" className="card-ap space-y-2 p-4">
        <h2 id="zusammenfassung-titel" className="text-sm font-semibold text-label">
          Zusammenfassung Ihrer Beauftragung
        </h2>
        <dl className="space-y-1 text-sm">
          <div>
            <dt className="text-label2">Leistung</dt>
            <dd className="text-label">{angebot.positionen.map((p) => p.beschreibung).join(", ")}</dd>
          </div>
          <div>
            <dt className="text-label2">Gesamtpreis (brutto, inkl. MwSt.)</dt>
            <dd className="font-semibold text-label">{angebot.gesamt_brutto} EUR</dd>
          </div>
          {angebot.gueltig_bis && (
            <div>
              <dt className="text-label2">Angebot gültig bis</dt>
              <dd className="text-label">{new Date(angebot.gueltig_bis).toLocaleDateString("de-DE")}</dd>
            </div>
          )}
        </dl>
        <p className="text-xs text-label2">
          Ausführungstermin und Zahlungsziel ergeben sich aus dem Angebot und der späteren Rechnung.
        </p>
      </section>

      <BelehrungBlock daten={verbraucher} />

      <div className="card-ap space-y-3 p-4">
        <label className="flex items-start gap-3 text-sm text-label">
          <input
            type="checkbox"
            checked={kenntnis}
            onChange={(e) => setKenntnis(e.target.checked)}
            className="mt-0.5 h-5 w-5 shrink-0"
          />
          <span>Ich habe die Widerrufsbelehrung gelesen und zur Kenntnis genommen.</span>
        </label>
        <button
          type="button"
          onClick={onBeauftragen}
          disabled={!kenntnis || laeuft || angebot.ist_abgelaufen}
          aria-describedby="beauftragen-hinweis"
          className="btn-touch btn-ap-primary w-full px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          Zahlungspflichtig beauftragen
        </button>
        <p id="beauftragen-hinweis" className="text-xs text-label2">
          Mit Klick auf diesen Button beauftragen Sie die Leistung verbindlich und sind zur Zahlung
          verpflichtet.
          {!kenntnis && " Bitte bestätigen Sie zuerst die Kenntnisnahme der Widerrufsbelehrung."}
        </p>
        <button
          type="button"
          onClick={onAblehnen}
          disabled={laeuft}
          className="btn-touch btn-ap w-full px-4 py-2 text-sm font-medium text-st-fehlt disabled:opacity-50"
        >
          Ablehnen
        </button>
      </div>
    </>
  );
}

function WiderrufBereich({ angebot, verbraucher }: { angebot: PortalAngebot; verbraucher?: PortalVerbraucherschutz }) {
  const frist = angebot.widerruf_frist_bis;
  if (!frist) return null;
  return (
    <>
      <section aria-labelledby="widerruf-titel" className="card-ap space-y-3 p-4">
        <h2 id="widerruf-titel" className="text-sm font-semibold text-label">
          Ihr Widerrufsrecht
        </h2>
        <p className="text-sm text-label">
          Sie können diesen Vertrag bis zum {widerrufFristLetzterTag(frist)} ohne Angabe von Gründen widerrufen.
        </p>
        {angebot.widerruf_moeglich ? (
          <Link
            to={`/portal/angebote/${angebot.id}/widerruf`}
            className="btn-touch btn-ap-capsule btn-ap-capsule-primary inline-flex w-full items-center justify-center px-4 text-sm font-semibold"
          >
            Vertrag widerrufen
          </Link>
        ) : (
          angebot.widerruf_hinweis && <Hinweiskasten ton="warnung">{angebot.widerruf_hinweis}</Hinweiskasten>
        )}
      </section>
      {verbraucher && <BelehrungBlock daten={verbraucher} offen={false} />}
    </>
  );
}

export function PortalAngebotDetailPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentKunde } = useKundenAuth();
  const [fehler, setFehler] = useState<string | null>(null);
  const meldeFehler = (err: unknown) => {
    setFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.");
    // Z. B. geaenderte Fassung/Belehrung: aktuellen Stand nachladen.
    queryClient.invalidateQueries({ queryKey: ["portal-angebot", id] });
    queryClient.invalidateQueries({ queryKey: ["portal-verbraucherschutz"] });
  };

  const { data: angebot } = useQuery({
    queryKey: ["portal-angebot", id],
    queryFn: () => kundenportalApi.angebot(id!),
    enabled: !!id,
  });
  const braucheBelehrung = !!angebot && (angebot.verbraucherschutz || angebot.widerruf_frist_bis !== null);
  const { data: verbraucher } = useQuery({
    queryKey: ["portal-verbraucherschutz"],
    queryFn: kundenportalApi.verbraucherschutz,
    enabled: braucheBelehrung,
  });
  const b2cAblauf = !!angebot && angebot.status === "versendet" && angebot.verbraucherschutz && !!verbraucher?.belehrung;

  const antwortMutation = useMutation({
    mutationFn: (status: "angenommen" | "abgelehnt") =>
      kundenportalApi.antwortAufAngebot(
        id!,
        status,
        b2cAblauf && verbraucher?.belehrung
          ? { belehrung_version: verbraucher.belehrung.version, fassung_sha256: angebot!.fassung_sha256 }
          : undefined,
      ),
    onSuccess: () => {
      setFehler(null);
      queryClient.invalidateQueries({ queryKey: ["portal-angebot", id] });
      queryClient.invalidateQueries({ queryKey: ["portal-angebote"] });
    },
    onError: meldeFehler,
  });

  const pdfMutation = useMutation({
    mutationFn: () => kundenportalApi.angebotPdf(id!),
    onSuccess: openPdfBlob,
    onError: meldeFehler,
  });

  if (!angebot) return <SkeletonCard />;

  async function ablehnen() {
    if (await bestaetigen("Angebot wirklich ablehnen? Der Betrieb wird darüber benachrichtigt.")) {
      antwortMutation.mutate("abgelehnt");
    }
  }

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="btn-touch text-sm text-label2">
        ← Zurück
      </button>

      <div className="card-ap p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-label2">Angebot Nr. {angebot.angebotsnummer}</div>
            <h1 className="text-lg font-bold text-label">Ihr Angebot</h1>
          </div>
          <span className={`px-2 py-1 text-xs font-semibold ${ANGEBOT_STATUS_BADGE[angebot.status]}`}>
            {ANGEBOT_STATUS_LABEL[angebot.status]}
          </span>
        </div>
        <p className="mt-1 text-xs text-label2">{ANGEBOT_STATUS_ERKLAERUNG[angebot.status]}</p>
        {angebot.gueltig_bis && (
          <p className="mt-1 text-xs text-label2">
            Gültig bis {new Date(angebot.gueltig_bis).toLocaleDateString("de-DE")}
          </p>
        )}
        <button
          onClick={() => pdfMutation.mutate()}
          disabled={pdfMutation.isPending}
          className="btn-touch mt-3 flex items-center justify-center gap-1 rounded-md bg-fill px-3 py-1.5 text-sm font-medium text-label disabled:opacity-50 "
        >
          <FileText size={14} strokeWidth={2} aria-hidden="true" />{" "}
          {pdfMutation.isPending ? "PDF wird geladen…" : "PDF anzeigen"}
        </button>
      </div>

      {fehler && <Hinweiskasten ton="fehler">{fehler}</Hinweiskasten>}

      <section aria-labelledby="positionen-titel" className="card-ap p-4">
        <h2 id="positionen-titel" className="mb-2 text-sm font-semibold text-label2">
          Positionen
        </h2>
        {angebot.positionen.length === 0 ? (
          <p className="text-sm text-label2">Keine Positionen.</p>
        ) : (
          <ul className="divide-y divide-sep">
            {angebot.positionen.map((p) => (
              <li key={p.id} className="flex items-center justify-between py-2 text-sm">
                <div>
                  <div className="text-label">{p.beschreibung}</div>
                  <div className="text-xs text-label2">
                    {p.menge} {p.einheit} × {p.einzelpreis} EUR
                  </div>
                </div>
                <div className="font-medium text-label">{p.gesamt} EUR</div>
              </li>
            ))}
          </ul>
        )}
        <div className="mt-3 border-t border-sep pt-2 text-right text-sm ">
          <div className="text-label2">Netto: {angebot.gesamt_netto} EUR</div>
          <div className="font-semibold text-label">Brutto: {angebot.gesamt_brutto} EUR</div>
        </div>
      </section>

      {angebot.status === "versendet" && angebot.ist_abgelaufen && (
        <Hinweiskasten ton="warnung" titel="Dieses Angebot ist abgelaufen">
          Eine Annahme ist nicht mehr möglich. Bitte wenden Sie sich an den Betrieb, wenn Sie das Angebot dennoch
          beauftragen möchten.
        </Hinweiskasten>
      )}

      {angebot.status === "versendet" && b2cAblauf && verbraucher && (
        <VerbindlichBeauftragen
          angebot={angebot}
          verbraucher={verbraucher}
          onBeauftragen={() => antwortMutation.mutate("angenommen")}
          onAblehnen={ablehnen}
          laeuft={antwortMutation.isPending}
        />
      )}
      {angebot.status === "versendet" && angebot.verbraucherschutz && !verbraucher?.belehrung && (
        <p className="text-center text-sm text-label2">Rechtliche Hinweise werden geladen…</p>
      )}
      {angebot.status === "versendet" && !angebot.verbraucherschutz && (
        <div className="flex gap-2">
          <button
            onClick={() => antwortMutation.mutate("angenommen")}
            disabled={antwortMutation.isPending || angebot.ist_abgelaufen}
            className="btn-touch btn-ap-primary flex-1 px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            Annehmen
          </button>
          <button
            onClick={ablehnen}
            disabled={antwortMutation.isPending}
            className="btn-touch btn-ap flex-1 px-4 py-2 text-sm font-medium text-st-fehlt disabled:opacity-50"
          >
            Ablehnen
          </button>
        </div>
      )}

      {angebot.status === "angenommen" && (
        <>
          <p className="text-center text-sm text-st-erledigt ">Sie haben dieses Angebot angenommen.</p>
          {angebot.widerruf_frist_bis && (
            <p className="text-center text-xs text-label2">
              Eine Bestätigung mit der Widerrufsbelehrung senden wir an {currentKunde?.email ?? "Ihre E-Mail-Adresse"}.
            </p>
          )}
          <WiderrufBereich angebot={angebot} verbraucher={verbraucher} />
        </>
      )}
      {angebot.status === "widerrufen" && angebot.widerrufen_am && (
        <p className="text-center text-sm text-st-arbeit">
          Sie haben diesen Vertrag am {datumZeit(angebot.widerrufen_am)} Uhr widerrufen.
        </p>
      )}
      {angebot.status === "abgelehnt" && (
        <p className="text-center text-sm text-st-fehlt ">Sie haben dieses Angebot abgelehnt.</p>
      )}
      {angebot.nachweis_referenz && (
        <p className="text-center text-xs text-label2">Referenz: {angebot.nachweis_referenz}</p>
      )}
    </div>
  );
}
