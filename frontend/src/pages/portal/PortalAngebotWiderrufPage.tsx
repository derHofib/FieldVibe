import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2 } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { kundenportalApi } from "../../api/endpoints";
import { Hinweiskasten } from "../../components/Hinweiskasten";
import { SkeletonCard } from "../../components/Skeleton";
import { useKundenAuth } from "../../context/KundenAuthContext";
import { datumZeit, widerrufFristLetzterTag } from "../../utils/portalAngebot";
import type { PortalAngebot } from "../../types";

/** Zweite Stufe des Widerrufsbuttons (§ 356a BGB): Bestaetigungsseite, danach
 * Eingangsbestaetigung. Die E-Mail auf dauerhaftem Datentraeger verschickt das
 * Backend. */
export function PortalAngebotWiderrufPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentKunde } = useKundenAuth();
  const [fehler, setFehler] = useState<string | null>(null);
  const [erledigt, setErledigt] = useState<PortalAngebot | null>(null);
  const ueberschrift = useRef<HTMLHeadingElement>(null);

  const { data: angebot } = useQuery({
    queryKey: ["portal-angebot", id],
    queryFn: () => kundenportalApi.angebot(id!),
    enabled: !!id,
  });

  const widerrufMutation = useMutation({
    mutationFn: () => kundenportalApi.widerrufAngebot(id!),
    onSuccess: (neu) => {
      setFehler(null);
      setErledigt(neu);
      queryClient.invalidateQueries({ queryKey: ["portal-angebot", id] });
      queryClient.invalidateQueries({ queryKey: ["portal-angebote"] });
    },
    onError: (err) => {
      setFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen.");
      queryClient.invalidateQueries({ queryKey: ["portal-angebot", id] });
    },
  });

  // Nach dem Seitenwechsel (Bestaetigt) liest der Screenreader die neue Ueberschrift.
  useEffect(() => {
    ueberschrift.current?.focus();
  }, [erledigt]);

  if (!angebot) return <SkeletonCard />;

  if (erledigt) {
    return (
      <div className="space-y-4">
        <div className="card-ap space-y-3 p-4">
          <CheckCircle2 size={28} strokeWidth={2} className="text-st-erledigt" aria-hidden="true" />
          <h1 ref={ueberschrift} tabIndex={-1} className="text-lg font-bold text-label outline-none">
            Ihr Widerruf ist eingegangen
          </h1>
          <p className="text-sm text-label">
            Wir haben Ihren Widerruf zum Angebot {erledigt.angebotsnummer}
            {erledigt.widerrufen_am ? ` am ${datumZeit(erledigt.widerrufen_am)} Uhr` : ""} erhalten. Die
            Eingangsbestätigung senden wir an {currentKunde?.email ?? "Ihre E-Mail-Adresse"}.
          </p>
          {erledigt.nachweis_referenz && (
            <p className="text-xs text-label2">Referenz: {erledigt.nachweis_referenz}</p>
          )}
        </div>
        <Link to={`/portal/angebote/${erledigt.id}`} className="btn-touch btn-ap block px-4 py-2 text-center text-sm font-medium">
          Zurück zum Angebot
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div className="card-ap space-y-3 p-4">
        <h1 ref={ueberschrift} className="text-lg font-bold text-label">
          Vertrag widerrufen
        </h1>
        <dl className="space-y-1 text-sm">
          <div>
            <dt className="text-label2">Angebot</dt>
            <dd className="text-label">Nr. {angebot.angebotsnummer}</dd>
          </div>
          <div>
            <dt className="text-label2">Gesamtpreis (brutto)</dt>
            <dd className="text-label">{angebot.gesamt_brutto} EUR</dd>
          </div>
          {angebot.angenommen_am && (
            <div>
              <dt className="text-label2">Beauftragt am</dt>
              <dd className="text-label">{datumZeit(angebot.angenommen_am)} Uhr</dd>
            </div>
          )}
          {angebot.widerruf_frist_bis && (
            <div>
              <dt className="text-label2">Widerruf möglich bis</dt>
              <dd className="text-label">{widerrufFristLetzterTag(angebot.widerruf_frist_bis)}</dd>
            </div>
          )}
        </dl>
      </div>

      {fehler && <Hinweiskasten ton="fehler">{fehler}</Hinweiskasten>}

      {angebot.widerruf_moeglich ? (
        <>
          <Hinweiskasten ton="warnung" titel="Bitte bestätigen Sie Ihren Widerruf">
            Mit „Widerruf bestätigen“ widerrufen Sie den Vertrag verbindlich. Sie erhalten eine
            Eingangsbestätigung per E-Mail.
          </Hinweiskasten>
          <div className="flex flex-col gap-2">
            <button
              type="button"
              onClick={() => widerrufMutation.mutate()}
              disabled={widerrufMutation.isPending}
              className="btn-touch btn-ap-primary w-full px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              {widerrufMutation.isPending ? "Wird gesendet…" : "Widerruf bestätigen"}
            </button>
            <button
              type="button"
              onClick={() => navigate(`/portal/angebote/${angebot.id}`)}
              className="btn-touch btn-ap w-full px-4 py-2 text-sm font-medium"
            >
              Abbrechen
            </button>
          </div>
        </>
      ) : (
        <>
          <Hinweiskasten ton="warnung" titel="Ein Widerruf ist hier nicht möglich">
            {angebot.widerruf_hinweis ??
              (angebot.status === "widerrufen"
                ? "Dieser Vertrag wurde bereits widerrufen."
                : "Für dieses Angebot besteht über das Portal kein Widerrufsrecht.")}
          </Hinweiskasten>
          <Link to={`/portal/angebote/${angebot.id}`} className="btn-touch btn-ap block px-4 py-2 text-center text-sm font-medium">
            Zurück zum Angebot
          </Link>
        </>
      )}
    </div>
  );
}
