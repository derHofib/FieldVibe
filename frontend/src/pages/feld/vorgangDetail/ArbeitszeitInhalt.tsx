import { AlertTriangle } from "lucide-react";
import { StatusPille } from "../../../components/apple/StatusPille";
import type { UserAuswahl, Vorgang } from "../../../types";
import { formatSekundenAlsHHMM } from "../../../utils/duration";
import { BUCHUNGSSTATUS_LABEL, buchungsstatusZuToken } from "../../../utils/zeiterfassung";
import { VORGANG_STATUS_ZEIT_GESPERRT } from "./konstanten";
import type { ZeitDaten } from "./useVorgangZeit";

interface ArbeitszeitInhaltProps {
  id: string | undefined;
  layout: "kompakt" | "dicht";
  users: UserAuswahl[] | undefined;
  vorgang: Vorgang;
  zeitDaten: ZeitDaten;
}

/** Arbeitszeit-Ansicht: im dichten Layout ein Tab, im kompakten Layout die Unterseite /vorgaenge/:id/zeit. */
export function ArbeitszeitInhalt({ id, layout, users, vorgang, zeitDaten }: ArbeitszeitInhaltProps) {
  const {
    ausgewaehlteZeitIds, ausgewaehlterStatus, buchenMutation, darfZeitenBuchen, gesamtKm,
    gesamtStunden, handleBuchen, kannZeitAuswaehlen, laufenderTimer, setAusgewaehlteZeitIds,
    setStornierenGrund, setStornierenModus, setTaetigkeit, setZeitSheetModus, startTimerMutation,
    stopTimerMutation, stornierenGrund, stornierenModus, stornierenMutation, taetigkeit,
    vormerkenMutation, zeitCheckboxToggeln, zeiterfassungListe, zurueckziehenMutation,
  } = zeitDaten;
  const timerLaeuftHier = laufenderTimer && laufenderTimer.vorgang_id === id;
  const timerLaeuftAnderswo = laufenderTimer && laufenderTimer.vorgang_id !== id;
  return (
    <>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-x-3 gap-y-1">
        <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Arbeitszeit</h2>
        {!VORGANG_STATUS_ZEIT_GESPERRT.includes(vorgang.status) && (
          <button onClick={() => setZeitSheetModus("neu")} className="btn-touch text-xs font-medium text-tint">
            + Zeit nachtragen
          </button>
        )}
        <span className="w-full text-sm font-medium text-label">
          Bisher {gesamtStunden} Std.{gesamtKm > 0 && ` · ${gesamtKm.toFixed(1)} km`}
        </span>
      </div>
      {timerLaeuftHier ? (
        <div className="flex items-center justify-between">
          <span className="flex items-center gap-2 text-sm font-medium text-label">
            <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-st-fehlt-dot" />
            Zeit läuft seit{" "}
            {new Date(laufenderTimer.start_at).toLocaleTimeString("de-DE", {
              timeZone: "Europe/Berlin",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
          <button
            onClick={() => stopTimerMutation.mutate(laufenderTimer.id)}
            disabled={stopTimerMutation.isPending}
            className="btn-touch rounded-md bg-st-fehlt-dot px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            Stoppen
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-2">
          <input
            value={taetigkeit}
            onChange={(e) => setTaetigkeit(e.target.value)}
            placeholder="Tätigkeit (optional)"
            className="btn-touch flex-1 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
          />
          <button
            onClick={() => startTimerMutation.mutate()}
            disabled={startTimerMutation.isPending || !!timerLaeuftAnderswo}
            title={timerLaeuftAnderswo ? "Es läuft bereits ein Timer für einen anderen Vorgang" : ""}
            className="btn-touch btn-ap-primary shrink-0 px-3 py-1.5 text-sm"
          >
            Zeit starten
          </button>
        </div>
      )}

      {(zeiterfassungListe ?? []).filter((e) => e.ende_at).length > 0 &&
        (layout === "dicht" ? (
          <div className="mt-2 overflow-x-auto border-t border-sep pt-2">
            <table className="w-full border-collapse text-xs">
              <thead>
                <tr className="text-left text-label2">
                  <th className="w-6 px-2 py-1" />
                  <th className="px-2 py-1 font-medium">Techniker</th>
                  <th className="px-2 py-1 font-medium">Tätigkeit</th>
                  <th className="px-2 py-1 font-medium">Datum</th>
                  <th className="px-2 py-1 font-medium">Von–Bis</th>
                  <th className="px-2 py-1 text-right font-medium">Dauer</th>
                  <th className="px-2 py-1 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {[...(zeiterfassungListe ?? [])]
                  .filter((e) => e.ende_at)
                  .sort((a, b) => new Date(b.start_at).getTime() - new Date(a.start_at).getTime())
                  .map((e) => {
                    const dauerSekunden =
                      (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000;
                    const techniker = users?.find((u) => u.id === e.techniker_id);
                    return (
                      <tr key={e.id} className="border-t border-sep hover:bg-fill">
                        <td className="px-2 py-1.5">
                          {kannZeitAuswaehlen(e) && (
                            <input
                              type="checkbox"
                              checked={ausgewaehlteZeitIds.has(e.id)}
                              onChange={() => zeitCheckboxToggeln(e)}
                              onClick={(ev) => ev.stopPropagation()}
                              className="h-4 w-4"
                            />
                          )}
                        </td>
                        <td className="cursor-pointer px-2 py-1.5 text-label" onClick={() => setZeitSheetModus(e)}>
                          {techniker?.name ?? "—"}
                        </td>
                        <td className="cursor-pointer px-2 py-1.5 text-label2" onClick={() => setZeitSheetModus(e)}>
                          {e.taetigkeit || (
                            <span className="flex items-center gap-1 text-st-arbeit">
                              <AlertTriangle size={12} strokeWidth={2} /> Tätigkeit fehlt
                            </span>
                          )}
                        </td>
                        <td className="cursor-pointer px-2 py-1.5 tabular-nums text-label2" onClick={() => setZeitSheetModus(e)}>
                          {new Date(e.start_at).toLocaleDateString("de-DE", { timeZone: "Europe/Berlin" })}
                        </td>
                        <td className="cursor-pointer px-2 py-1.5 tabular-nums text-label2" onClick={() => setZeitSheetModus(e)}>
                          {new Date(e.start_at).toLocaleTimeString("de-DE", {
                            timeZone: "Europe/Berlin",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                          –
                          {new Date(e.ende_at!).toLocaleTimeString("de-DE", {
                            timeZone: "Europe/Berlin",
                            hour: "2-digit",
                            minute: "2-digit",
                          })}
                        </td>
                        <td
                          className="cursor-pointer px-2 py-1.5 text-right font-medium tabular-nums text-label"
                          onClick={() => setZeitSheetModus(e)}
                        >
                          {formatSekundenAlsHHMM(dauerSekunden)} Std.
                          {e.km && <span className="ml-1 font-normal text-label2">· {e.km} km</span>}
                        </td>
                        <td className="cursor-pointer px-2 py-1.5" onClick={() => setZeitSheetModus(e)}>
                          <StatusPille
                            status={buchungsstatusZuToken(e.buchungsstatus)}
                            label={BUCHUNGSSTATUS_LABEL[e.buchungsstatus]}
                          />
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="mt-3 space-y-3 border-t border-sep pt-3">
            {(() => {
              let letztesDatum = "";
              return [...(zeiterfassungListe ?? [])]
                .filter((e) => e.ende_at)
                .sort((a, b) => new Date(b.start_at).getTime() - new Date(a.start_at).getTime())
                .map((e) => {
                  const dauerSekunden =
                    (new Date(e.ende_at!).getTime() - new Date(e.start_at).getTime()) / 1000;
                  const techniker = users?.find((u) => u.id === e.techniker_id);
                  const datum = new Date(e.start_at).toLocaleDateString("de-DE", {
                    timeZone: "Europe/Berlin",
                    weekday: "short",
                    day: "2-digit",
                    month: "2-digit",
                  });
                  const neuesDatum = datum !== letztesDatum;
                  letztesDatum = datum;
                  return (
                    <div key={e.id}>
                      {neuesDatum && (
                        <div className="mb-1.5 text-[11px] font-bold tracking-wide text-label3 uppercase">
                          {datum}
                        </div>
                      )}
                      <div className="flex items-start gap-2">
                        {kannZeitAuswaehlen(e) && (
                          <input
                            type="checkbox"
                            checked={ausgewaehlteZeitIds.has(e.id)}
                            onChange={() => zeitCheckboxToggeln(e)}
                            className="btn-touch mt-3.5 h-4 w-4 shrink-0"
                          />
                        )}
                        <button
                          onClick={() => setZeitSheetModus(e)}
                          className="btn-touch flex min-w-0 flex-1 items-start justify-between gap-3 border border-sep px-3 py-2.5 text-left hover:bg-fill"
                        >
                          <div className="min-w-0">
                            <div className="text-sm font-medium text-label">
                              {new Date(e.start_at).toLocaleTimeString("de-DE", {
                                timeZone: "Europe/Berlin",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                              –
                              {new Date(e.ende_at!).toLocaleTimeString("de-DE", {
                                timeZone: "Europe/Berlin",
                                hour: "2-digit",
                                minute: "2-digit",
                              })}
                              <span className="font-normal text-label2"> · {techniker?.name ?? "—"}</span>
                            </div>
                            <div className="mt-0.5 truncate text-xs text-label2">
                              {e.taetigkeit || (
                                <span className="inline-flex items-center gap-1 text-st-arbeit">
                                  <AlertTriangle size={12} strokeWidth={2} /> Tätigkeit fehlt
                                </span>
                              )}
                            </div>
                          </div>
                          <div className="flex shrink-0 flex-col items-end gap-1">
                            <span className="text-sm font-semibold tabular-nums text-label">
                              {formatSekundenAlsHHMM(dauerSekunden)} Std.
                            </span>
                            {e.km && <span className="text-[11px] tabular-nums text-label2">{e.km} km</span>}
                            <StatusPille
                              status={buchungsstatusZuToken(e.buchungsstatus)}
                              label={BUCHUNGSSTATUS_LABEL[e.buchungsstatus]}
                            />
                          </div>
                        </button>
                      </div>
                    </div>
                  );
                });
            })()}
          </div>
        ))}

      {ausgewaehlteZeitIds.size > 0 && (
        <div className="mt-2 border-t border-sep pt-2">
          {stornierenModus ? (
            <div className="flex items-center gap-2">
              <input
                autoFocus
                value={stornierenGrund}
                onChange={(e) => setStornierenGrund(e.target.value)}
                placeholder="Grund für die Stornierung"
                className="field-ap flex-1 text-sm"
              />
              <button
                onClick={() => stornierenMutation.mutate()}
                disabled={!stornierenGrund.trim() || stornierenMutation.isPending}
                className="btn-touch btn-ap-primary shrink-0 px-3 py-1.5 text-xs disabled:opacity-40"
              >
                Bestätigen
              </button>
              <button
                onClick={() => setStornierenModus(false)}
                className="btn-touch shrink-0 px-2 py-1.5 text-xs text-label2"
              >
                Abbrechen
              </button>
            </div>
          ) : (
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-xs text-label2">{ausgewaehlteZeitIds.size} ausgewählt</span>
              {ausgewaehlterStatus === "vermerkt" && (
                <button
                  onClick={() => vormerkenMutation.mutate([...ausgewaehlteZeitIds])}
                  disabled={vormerkenMutation.isPending}
                  className="btn-touch border border-sepstrong px-3 py-1.5 text-xs font-medium text-label hover:bg-fill"
                >
                  Zur Buchung vormerken
                </button>
              )}
              {(ausgewaehlterStatus === "vermerkt" || ausgewaehlterStatus === "vorgemerkt") &&
                darfZeitenBuchen && (
                  <button
                    onClick={handleBuchen}
                    disabled={buchenMutation.isPending}
                    className="btn-touch btn-ap-primary px-3 py-1.5 text-xs"
                  >
                    Buchen
                  </button>
                )}
              {ausgewaehlterStatus === "vorgemerkt" && (
                <button
                  onClick={() => zurueckziehenMutation.mutate([...ausgewaehlteZeitIds])}
                  disabled={zurueckziehenMutation.isPending}
                  className="btn-touch border border-sepstrong px-3 py-1.5 text-xs font-medium text-label hover:bg-fill"
                >
                  Zurückziehen
                </button>
              )}
              {ausgewaehlterStatus === "gebucht" && darfZeitenBuchen && (
                <button
                  onClick={() => setStornierenModus(true)}
                  className="btn-touch border border-sepstrong px-3 py-1.5 text-xs font-medium text-label hover:bg-fill"
                >
                  Buchung stornieren
                </button>
              )}
              <button
                onClick={() => setAusgewaehlteZeitIds(new Set())}
                className="btn-touch px-2 py-1.5 text-xs text-label2"
              >
                Auswahl aufheben
              </button>
            </div>
          )}
        </div>
      )}
    </>
  );
}
