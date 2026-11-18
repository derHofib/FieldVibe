import { useState } from "react";
import { Bot } from "lucide-react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useSearchParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { kiApi } from "../api/endpoints";
import { GesperrtZustand } from "../components/EmptyState";
import { SkeletonList } from "../components/Skeleton";
import { SymbolKachel } from "../components/apple/SymbolKachel";
import type { KiScope } from "../types/ki";

type Modus = "lesen" | "schreiben";

/** Einwilligung fuer einen KI-Client (OAuth-Weg der MCP-Anbindung). Der Nutzer
 * waehlt den Umfang; die Antwort des Servers ist ein Redirect zurueck zum Client. */
export function KiVerbindenPage({ layout = "feld" }: { layout?: "feld" | "office" }) {
  const [params] = useSearchParams();
  const anfrage = params.get("anfrage") ?? "";
  const [modus, setModus] = useState<Modus>("lesen");

  const { data, isLoading, error } = useQuery({
    queryKey: ["ki", "anfrage", anfrage],
    queryFn: () => kiApi.anfrage(anfrage),
    enabled: !!anfrage,
    retry: false,
    // Die Anfrage ist einmalig und kurzlebig: kein Hintergrund-Abruf.
    staleTime: Infinity,
  });

  const antwort = useMutation({
    mutationFn: (erlauben: boolean) =>
      erlauben
        ? kiApi.autorisieren(anfrage, modus === "schreiben" ? ["fieldvibe.lesen", "fieldvibe.schreiben"] : (["fieldvibe.lesen"] as KiScope[]))
        : kiApi.ablehnen(anfrage),
    onSuccess: (r) => window.location.assign(r.redirect_url),
  });

  const Titel = layout === "office" ? "h1" : "h2";
  const zurueck = (
    <Link to="/" className="btn-touch btn-ap inline-flex items-center px-4">
      Zur Startseite
    </Link>
  );

  if (!anfrage) {
    return (
      <GesperrtZustand
        alsH1={layout === "office"}
        titel="Anfrage ungültig"
        text="Diese Verbindungsanfrage ist unvollständig. Starte die Verbindung noch einmal in Claude."
        action={zurueck}
      />
    );
  }
  if (isLoading) return <SkeletonList className="py-4" />;
  if (error || !data) {
    const status = error instanceof ApiError ? error.status : 0;
    return (
      <GesperrtZustand
        alsH1={layout === "office"}
        titel={status === 403 ? "Verbinden nicht möglich" : "Anfrage ungültig"}
        text={
          status === 403
            ? error instanceof ApiError && error.message
              ? error.message
              : "Du darfst FieldVibe nicht mit einem KI-Assistenten verbinden."
            : status === 400
              ? "Die Anfrage ist ungültig oder abgelaufen. Starte die Verbindung noch einmal in Claude."
              : "Die Anfrage konnte nicht geladen werden. Bitte versuche es erneut."
        }
        action={zurueck}
      />
    );
  }

  // Claude fragt nur den Pflicht-Scope an; ob geschrieben werden darf, entscheidet der Nutzer.
  const schreibenWaehlbar = data.schreiben_erlaubt;
  const fehler = antwort.error instanceof ApiError ? antwort.error.message : antwort.error ? "Die Antwort konnte nicht gesendet werden." : null;

  return (
    <div className="mx-auto max-w-lg space-y-4">
      <div className="card-ap space-y-4 p-4">
        <div className="flex items-center gap-3">
          <SymbolKachel icon={Bot} farbe="indigo" groesse={40} />
          <Titel className="min-w-0 text-zeile font-semibold text-label">
            {data.client_name} möchte auf FieldVibe zugreifen
          </Titel>
        </div>
        <p className="text-fliess text-label2">
          {data.client_name} arbeitet mit deinen Rechten: Es sieht nur, was du in FieldVibe auch sehen darfst. Die
          Daten, die dabei abgefragt werden, werden an den KI-Anbieter übermittelt. Du kannst die Verbindung jederzeit
          in deinem Profil trennen.
        </p>
        <p className="text-meta text-label2">Nach deiner Entscheidung geht es weiter zu {data.redirect_host}.</p>

        <fieldset className="space-y-2">
          <legend className="mb-1 text-fliess font-medium text-label">Zugriff</legend>
          <label className="flex cursor-pointer items-start gap-3 rounded-[var(--radius-ap-md)] bg-cell p-3">
            <input type="radio" name="ki-modus" className="mt-1" checked={modus === "lesen"} onChange={() => setModus("lesen")} />
            <span>
              <span className="block text-fliess text-label">Nur lesen</span>
              <span className="block text-sekundaer text-label2">Auswerten und nachschlagen, nichts wird verändert.</span>
            </span>
          </label>
          {schreibenWaehlbar && (
            <label className="flex cursor-pointer items-start gap-3 rounded-[var(--radius-ap-md)] bg-cell p-3">
              <input type="radio" name="ki-modus" className="mt-1" checked={modus === "schreiben"} onChange={() => setModus("schreiben")} />
              <span>
                <span className="block text-fliess text-label">Lesen und schreiben</span>
                <span className="block text-sekundaer text-label2">
                  Zusätzlich Entwürfe anlegen, z. B. Protokoll-Vorlagen und Kommentare. Löschen, Abschließen und
                  Abrechnen ist nie möglich.
                </span>
              </span>
            </label>
          )}
        </fieldset>

        {fehler && (
          <p role="alert" className="text-fliess text-st-fehlt">
            {fehler}
          </p>
        )}

        <div className="flex flex-col gap-2 sm:flex-row-reverse">
          <button
            type="button"
            disabled={antwort.isPending}
            onClick={() => antwort.mutate(true)}
            className="btn-touch btn-ap btn-ap-primary px-4 disabled:opacity-50"
          >
            Erlauben
          </button>
          <button
            type="button"
            disabled={antwort.isPending}
            onClick={() => antwort.mutate(false)}
            className="btn-touch btn-ap px-4 disabled:opacity-50"
          >
            Ablehnen
          </button>
        </div>
      </div>
    </div>
  );
}
