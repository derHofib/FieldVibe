import { AlertTriangle } from "lucide-react";
import { bestaetigen } from "../../../components/apple/BestaetigungsDialog";
import { useAuth } from "../../../context/AuthContext";
import type { UserAuswahl } from "../../../types";
import { WOCHENTAGE, addTage, startOfWoche, tagesSchluessel, toLocalInputValue } from "./helfer";
import { TERMIN_STATUS_LABEL } from "./konstanten";
import type { TermineDaten } from "./useVorgangTermine";

interface TermineAbschnittProps {
  istAktiverTab: (ziel: string) => boolean;
  layout: "kompakt" | "dicht";
  tabPanelProps: (ziel: string) => { role?: "tabpanel"; "aria-labelledby"?: string };
  users: UserAuswahl[] | undefined;
  termineDaten: TermineDaten;
}

/** Termine des Vorgangs inkl. Planungsformular und Wochenkalender (dichtes Layout). */
export function TermineAbschnitt({
  istAktiverTab, layout, tabPanelProps, users, termineDaten,
}: TermineAbschnittProps) {
  const {
    deleteTerminMutation, setShowTerminForm, setTerminEnde, setTerminStart, setTerminTechnikerId,
    setTerminTitel, setTerminWocheOffset, showTerminForm, terminEnde, terminMutation, terminStart,
    terminTechnikerId, terminTitel, terminWarnungen, terminWocheOffset, termine,
  } = termineDaten;
  const { currentUser, hatRecht } = useAuth();
  const kannDisponieren = hatRecht("vorgaenge", "bearbeiten");
  const kannPapierkorbLoeschen = currentUser?.role === "loesch_operativ";
  return (
    <div
      id="abschnitt-termine"
      className={`scroll-mt-4 card-ap p-3 ${istAktiverTab("abschnitt-termine") ? "" : "hidden"}`}
      {...tabPanelProps("abschnitt-termine")}
    >
      <div className="mb-2 flex items-center justify-between">
        {/* Leerer Abschnitt auf Mobile: Ueberschrift entfaellt, die
         * Leer-Meldung nennt den Abschnitt stattdessen selbst -- spart
         * eine ganze Zeile, ohne den Abschnitt komplett zu verstecken
         * (Aktion bleibt sofort erreichbar). */}
        {!(layout !== "dicht" && (termine ?? []).length === 0 && !showTerminForm) && (
          <h2 className="font-heading text-sm font-semibold uppercase tracking-wide text-label">Termine</h2>
        )}
        {kannDisponieren && (
          <button
            onClick={() => {
              setShowTerminForm((v) => !v);
              if (!terminStart) {
                const start = new Date();
                start.setMinutes(0, 0, 0);
                start.setHours(start.getHours() + 1);
                const ende = new Date(start.getTime() + 60 * 60 * 1000);
                setTerminStart(toLocalInputValue(start));
                setTerminEnde(toLocalInputValue(ende));
                setTerminTechnikerId(
                  users?.find((u) => u.role === "mandant_admin" || u.role === "custom")?.id ?? "",
                );
              }
            }}
            className="btn-touch text-xs font-medium text-tint"
          >
            {showTerminForm ? "Abbrechen" : "+ Termin planen"}
          </button>
        )}
      </div>

      {terminWarnungen.length > 0 && (
        <div className="mb-2 rounded-md border border-st-arbeit bg-st-arbeit-bg p-2 text-xs text-st-arbeit">
          {terminWarnungen.map((w, i) => (
            <p key={i} className="flex items-center gap-1">
              <AlertTriangle size={13} strokeWidth={2} /> {w.meldung}
            </p>
          ))}
        </div>
      )}

      {showTerminForm && (
        <div className="mb-2 space-y-2 border border-sepstrong p-2">
          <input
            value={terminTitel}
            onChange={(e) => setTerminTitel(e.target.value)}
            placeholder="Titel"
            className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
          />
          <select
            value={terminTechnikerId}
            onChange={(e) => setTerminTechnikerId(e.target.value)}
            className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
          >
            {(users ?? [])
              .filter((u) => u.role === "mandant_admin" || u.role === "custom")
              .map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
          </select>
          <div className="flex gap-2">
            <input
              type="datetime-local"
              value={terminStart}
              onChange={(e) => setTerminStart(e.target.value)}
              className="w-1/2 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            <input
              type="datetime-local"
              value={terminEnde}
              onChange={(e) => setTerminEnde(e.target.value)}
              className="w-1/2 border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
          </div>
          <button
            disabled={!terminTitel || !terminTechnikerId || terminMutation.isPending}
            onClick={() => terminMutation.mutate()}
            className="btn-touch btn-ap-primary w-full px-3 py-1.5 text-sm"
          >
            Anlegen
          </button>
        </div>
      )}

      {layout === "dicht"
        ? (() => {
            const heute = new Date();
            const sortiert = [...(termine ?? [])].sort(
              (a, b) => new Date(a.start_at).getTime() - new Date(b.start_at).getTime(),
            );
            const naechster =
              sortiert.find((t) => new Date(t.start_at).getTime() >= heute.getTime()) ??
              sortiert[sortiert.length - 1];
            const referenz = naechster ? new Date(naechster.start_at) : heute;
            const wocheStart = addTage(startOfWoche(referenz), terminWocheOffset * 7);
            const wocheTage = Array.from({ length: 7 }, (_, i) => addTage(wocheStart, i));
            const wocheEnde = addTage(wocheStart, 6);
            const perTag = new Map<string, typeof sortiert>();
            for (const t of sortiert) {
              const key = tagesSchluessel(new Date(t.start_at));
              perTag.set(key, [...(perTag.get(key) ?? []), t]);
            }
            return (
              <div>
                <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setTerminWocheOffset((o) => o - 1)}
                      className="btn-touch border border-sep px-2 py-1 text-xs text-label hover:bg-fill"
                    >
                      ← Vorherige Woche
                    </button>
                    <button
                      type="button"
                      onClick={() => setTerminWocheOffset(0)}
                      disabled={terminWocheOffset === 0}
                      className="btn-touch border border-sep px-2 py-1 text-xs text-label hover:bg-fill disabled:opacity-50"
                    >
                      Diese Woche
                    </button>
                    <button
                      type="button"
                      onClick={() => setTerminWocheOffset((o) => o + 1)}
                      className="btn-touch border border-sep px-2 py-1 text-xs text-label hover:bg-fill"
                    >
                      Nächste Woche →
                    </button>
                  </div>
                  <span className="text-xs text-label2">
                    {wocheStart.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}–
                    {wocheEnde.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit", year: "numeric" })}
                  </span>
                </div>
                <div className="grid grid-cols-7 gap-px overflow-hidden border border-sep bg-sep">
                  {wocheTage.map((tag, i) => {
                    const heuteFlag = tagesSchluessel(tag) === tagesSchluessel(heute);
                    const eintraege = perTag.get(tagesSchluessel(tag)) ?? [];
                    return (
                      <div key={i} className="min-h-[110px] bg-card p-1.5">
                        <div className={`mb-1 text-[11px] font-medium ${heuteFlag ? "text-tint" : "text-label2"}`}>
                          {WOCHENTAGE[i]} {tag.toLocaleDateString("de-DE", { day: "2-digit", month: "2-digit" })}
                        </div>
                        <div className="space-y-1">
                          {eintraege.map((t) => (
                            <div
                              key={t.id}
                              title={t.titel}
                              className={`rounded-[5px] border p-1 text-[11px] ${
                                t.status === "abgesagt"
                                  ? "border-sep text-label2 line-through"
                                  : "border-tint text-tint"
                              }`}
                            >
                              <div className="font-semibold">
                                {new Date(t.start_at).toLocaleTimeString("de-DE", {
                                  timeZone: "Europe/Berlin",
                                  hour: "2-digit",
                                  minute: "2-digit",
                                })}
                              </div>
                              <div className="truncate">{t.titel}</div>
                              {kannPapierkorbLoeschen && (
                                <button
                                  type="button"
                                  onClick={async () => {
                                    if (await bestaetigen(`Termin "${t.titel}" wirklich löschen?`)) {
                                      deleteTerminMutation.mutate(t.id);
                                    }
                                  }}
                                  disabled={deleteTerminMutation.isPending}
                                  className="mt-0.5 text-[10px] font-medium text-st-fehlt"
                                >
                                  Löschen
                                </button>
                              )}
                            </div>
                          ))}
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })()
        : (termine ?? []).length === 0 ? (
            <p className="text-sm text-label2">{showTerminForm ? "Keine Termine geplant." : "Termine: Keine geplant."}</p>
          ) : (
            <div className="space-y-1.5">
              {termine!.map((t) => (
                <div
                  key={t.id}
                  className="flex items-center justify-between border border-sepstrong p-2 text-sm"
                >
                  <div>
                    <div className="font-medium text-label">{t.titel}</div>
                    <div className="text-xs text-label2">
                      {new Date(t.start_at).toLocaleString("de-DE", {
                        timeZone: "Europe/Berlin",
                        dateStyle: "short",
                        timeStyle: "short",
                      })}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    <span
                      className={`border px-2 py-0.5 text-xs font-medium ${
                        t.status === "abgesagt"
                          ? "border-sep text-label2"
                          : "border-tint text-tint"
                      }`}
                    >
                      {TERMIN_STATUS_LABEL[t.status]}
                    </span>
                    {kannPapierkorbLoeschen && (
                      <button
                        onClick={async () => {
                          if (await bestaetigen(`Termin "${t.titel}" wirklich löschen?`)) {
                            deleteTerminMutation.mutate(t.id);
                          }
                        }}
                        disabled={deleteTerminMutation.isPending}
                        className="btn-touch text-xs font-medium text-st-fehlt"
                      >
                        Löschen
                      </button>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
    </div>
  );
}
