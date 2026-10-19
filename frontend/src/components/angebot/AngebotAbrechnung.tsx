import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";

import { ApiError } from "../../api/client";
import { rechnungenApi } from "../../api/endpoints";
import type { Angebot, Rechnung } from "../../types";
import { RECHNUNG_STATUS_LABEL, RECHNUNG_STATUS_TONE } from "../../utils/buchhaltung";
import { formatEuro } from "../../utils/format";
import { StatusBadge } from "../StatusBadge";
import { FehlerMeldung, Hinweiskasten } from "../Hinweiskasten";
import { AbschlagSheet } from "./AbschlagSheet";
import type { RechnungStatus } from "../../types";

/** Abrechnungsstand eines angenommenen Angebots: Fortschritt, Abschläge und die
 * Wege zu Abschlag, Schlussrechnung bzw. Rechnung. Alles entsteht als Entwurf,
 * deshalb ohne Rückfrage. */
export function AngebotAbrechnung({
  angebot,
  kannErstellen,
  onRechnung,
}: {
  angebot: Angebot;
  kannErstellen: boolean;
  onRechnung: (rechnung: Rechnung) => void;
}) {
  const queryClient = useQueryClient();
  const [abschlagOffen, setAbschlagOffen] = useState(false);
  const [fehler, setFehler] = useState<string | null>(null);

  const abschlaege = angebot.abschlaege ?? [];
  const gesamt = Number(angebot.gesamt_netto);
  const abgerechnet = Number(angebot.abgerechnet_netto ?? "0");
  const rest = angebot.rest_netto ?? angebot.gesamt_netto;
  const prozent = gesamt > 0 ? Math.min(100, Math.max(0, (abgerechnet / gesamt) * 100)) : 0;

  const hatSchluss = !!angebot.schlussrechnung_id;
  const hatRechnung = !!angebot.rechnung_id;
  const abgeschlossen = hatSchluss || hatRechnung;
  const entwurfsAbschlaege = abschlaege.filter((a) => a.status === "entwurf");

  const erstellen = useMutation({
    mutationFn: (art: "rechnung" | "schluss") =>
      rechnungenApi.ausAngebot({ angebot_id: angebot.id, rechnungsart: art }),
    onSuccess: (rechnung) => {
      queryClient.invalidateQueries({ queryKey: ["angebot", angebot.id] });
      queryClient.invalidateQueries({ queryKey: ["angebote"] });
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
      queryClient.invalidateQueries({ queryKey: ["rechnungen-uebersicht"] });
      onRechnung(rechnung);
    },
    onError: (err) =>
      setFehler(err instanceof ApiError ? err.message : "Verbindung fehlgeschlagen — bitte erneut versuchen."),
  });

  const starten = (art: "rechnung" | "schluss") => {
    setFehler(null);
    erstellen.mutate(art);
  };

  const keinRest = Number(rest) <= 0;

  return (
    <div className="card-ap space-y-3 p-4" data-testid="angebot-abrechnung">
      <h2 className="text-sm font-semibold text-label2">Abrechnung</h2>

      <div>
        <div className="mb-1 flex justify-between text-xs text-label2">
          <span>Abgerechnet {formatEuro(abgerechnet)}</span>
          <span>Rest {formatEuro(rest)}</span>
        </div>
        <div
          role="progressbar"
          aria-label="Abgerechneter Anteil des Angebots"
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={Math.round(prozent)}
          className="h-2 overflow-hidden rounded-full bg-fill2"
        >
          <div className="h-full rounded-full bg-tint-solid" style={{ width: `${prozent}%` }} />
        </div>
        <p className="mt-1 text-xs text-label2">
          {Math.round(prozent)} % von {formatEuro(angebot.gesamt_netto)} netto
        </p>
      </div>

      {abschlaege.length > 0 && (
        <ul className="space-y-1.5">
          {abschlaege.map((a) => (
            <li key={a.rechnung_id}>
              <Link
                to={`/rechnungen/${a.rechnung_id}`}
                className="btn-touch flex items-center justify-between gap-2 rounded-md bg-fill p-2 text-sm"
              >
                <span className="min-w-0">
                  <span className="block text-xs text-label2">Abschlag</span>
                  <span className="block truncate font-medium text-label">{a.rechnungsnummer}</span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  <span className="tabular-nums font-medium text-label">{formatEuro(a.netto)}</span>
                  <StatusBadge
                    label={RECHNUNG_STATUS_LABEL[a.status as RechnungStatus] ?? a.status}
                    tone={RECHNUNG_STATUS_TONE[a.status as RechnungStatus] ?? "slate"}
                  />
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}

      {hatSchluss && (
        <Link to={`/rechnungen/${angebot.schlussrechnung_id}`} className="btn-touch inline-block text-sm font-medium text-tint-text">
          Zur Schlussrechnung →
        </Link>
      )}
      {hatRechnung && (
        <Link to={`/rechnungen/${angebot.rechnung_id}`} className="btn-touch inline-block text-sm font-medium text-tint-text">
          Zur Rechnung →
        </Link>
      )}

      {fehler && <FehlerMeldung meldung={fehler} alsKasten />}

      {!abgeschlossen && abschlaege.length > 0 && entwurfsAbschlaege.length > 0 && (
        <Hinweiskasten ton="info">
          <p>
            {entwurfsAbschlaege.length === 1 ? "Ein Abschlag ist" : `${entwurfsAbschlaege.length} Abschläge sind`} noch
            ein Entwurf ({entwurfsAbschlaege.map((a) => a.rechnungsnummer).join(", ")}). Die Schlussrechnung ist erst
            möglich, wenn alle Abschläge versendet sind.
          </p>
        </Hinweiskasten>
      )}

      {kannErstellen && !abgeschlossen && (
        <div className="flex flex-col gap-2 sm:flex-row">
          {!keinRest && (
            <button
              type="button"
              onClick={() => setAbschlagOffen(true)}
              disabled={erstellen.isPending}
              className="btn-touch btn-ap flex-1 px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              Abschlag erstellen
            </button>
          )}
          {abschlaege.length > 0 ? (
            <button
              type="button"
              onClick={() => starten("schluss")}
              disabled={erstellen.isPending || entwurfsAbschlaege.length > 0}
              className="btn-touch btn-ap btn-ap-primary flex-1 px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              Schlussrechnung erstellen
            </button>
          ) : (
            <button
              type="button"
              onClick={() => starten("rechnung")}
              disabled={erstellen.isPending}
              className="btn-touch btn-ap btn-ap-primary flex-1 px-4 py-2 text-sm font-medium disabled:opacity-50"
            >
              Rechnung erstellen
            </button>
          )}
        </div>
      )}

      {abschlagOffen && (
        <AbschlagSheet
          angebotId={angebot.id}
          angebotNetto={angebot.gesamt_netto}
          restNetto={rest}
          onClose={() => setAbschlagOffen(false)}
          onErstellt={(rechnung) => {
            setAbschlagOffen(false);
            onRechnung(rechnung);
          }}
        />
      )}
    </div>
  );
}
