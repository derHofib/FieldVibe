import { useQuery } from "@tanstack/react-query";
import { CalendarRange, ChevronLeft, Diamond, Handshake, Package } from "lucide-react";
import type { ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { zeitplanApi } from "../../api/endpoints";
import { AbschnittskopfA, AbschnittskopfB } from "../../components/apple/AbschnittsKopf";
import { GroupedList, GroupedListRow } from "../../components/apple/GroupedList";
import { StatusPille } from "../../components/apple/StatusPille";
import { VORGANG_STATUS_LABEL, vorgangStatusZuToken } from "../../components/apple/status";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import {
  anzeigeZeitraeume,
  baueZeilen,
  formatKurz,
  heuteTag,
  montagVon,
  type Zeitraum,
} from "../../office/projekte/zeitplan/zeitplanLogik";
import type { ZeitplanElement } from "../../types";

function zeitraumText(e: ZeitplanElement, z: Zeitraum | undefined): string {
  if (!z) return e.typ === "meilenstein" && e.bestellung ? "Liefertermin offen" : "Ohne Datum";
  if (z.start === z.ende) return formatKurz(z.start);
  return `${formatKurz(z.start)} – ${formatKurz(z.ende)}`;
}

/** Feld-App: Zeitplan eines Projekts als reine Leseliste (keine Zeitleiste,
 * keine Bearbeitung). Heute/diese Woche sind hervorgehoben. */
export function ProjektZeitplanMobilPage() {
  const { id } = useParams<{ id: string }>();
  const { data: zeitplan, isLoading, error } = useQuery({
    queryKey: ["projekt-zeitplan", id],
    queryFn: () => zeitplanApi.get(id!),
    enabled: !!id,
    retry: (n, e) => !(e instanceof ApiError && e.status === 403) && n < 2,
  });
  const heute = heuteTag();
  const montag = montagVon(heute);

  // Ohne Recht "projekte.sehen" gibt es den Zeitplan-Abschnitt gar nicht -- zurueck zur Liste.
  if (error instanceof ApiError && error.status === 403) return <Navigate to="/projekte" replace />;

  const elemente = zeitplan?.elemente ?? [];
  const pos = anzeigeZeitraeume(elemente);
  const zeilen = baueZeilen(elemente, new Set(), null);

  // Gruppen: Phase (oder "Ohne Phase") mit ihren Schritten/Meilensteinen.
  const gruppen: { phase: ZeitplanElement | null; kinder: ZeitplanElement[] }[] = [];
  for (const z of zeilen) {
    if (z.art !== "element") continue;
    if (z.element.typ === "phase") gruppen.push({ phase: z.element, kinder: [] });
    else if (z.ebene === 1) gruppen[gruppen.length - 1].kinder.push(z.element);
    else {
      let lose = gruppen.find((g) => g.phase === null);
      if (!lose) {
        lose = { phase: null, kinder: [] };
        gruppen.push(lose);
      }
      lose.kinder.push(z.element);
    }
  }

  function symbol(e: ZeitplanElement): ReactNode {
    if (e.typ === "meilenstein" && e.bestellung) return <Package size={18} strokeWidth={2} className="text-tone-amber" aria-label="Lieferung" role="img" />;
    if (e.typ === "meilenstein") return <Diamond size={16} strokeWidth={2} className="text-tone-amber" aria-label="Meilenstein" role="img" />;
    if (e.partner) return <Handshake size={18} strokeWidth={2} className="text-tone-violet" aria-label="Fremdgewerk" role="img" />;
    return <span className="h-2.5 w-4 rounded-[3px] bg-tint-solid" aria-hidden="true" />;
  }

  function zusatz(e: ZeitplanElement): string | null {
    if (e.partner) return e.partner.name;
    if (e.bestellung) return [e.bestellung.lieferant_name, e.bestellung.bestellnummer].filter(Boolean).join(" · ");
    return null;
  }

  return (
    <div className="-mx-3 -mt-4 pb-8">
      <Link to="/projekte" className="flex items-center gap-0.5 px-3 pt-3 text-[17px] text-tint-text">
        <ChevronLeft size={20} strokeWidth={2} aria-hidden="true" /> Projekte
      </Link>
      <AbschnittskopfA titel="Zeitplan" />

      <div className="px-4">
        {isLoading ? (
          <SkeletonList count={4} />
        ) : error ? (
          <p role="alert" className="text-sm text-st-fehlt">
            Zeitplan konnte nicht geladen werden.
          </p>
        ) : gruppen.length === 0 ? (
          <EmptyState icon={CalendarRange} text="Für dieses Projekt gibt es noch keinen Zeitplan." />
        ) : (
          gruppen.map((g) => {
            const phaseZ = g.phase ? pos.get(g.phase.id) : undefined;
            return (
              <section key={g.phase?.id ?? "lose"} aria-label={g.phase?.titel ?? "Ohne Phase"}>
                <div className="flex items-baseline justify-between">
                  <AbschnittskopfB titel={g.phase?.titel ?? "Ohne Phase"} />
                  {g.phase && (
                    <span className="pt-[22px] pr-4 text-[13px] text-label2 tabular-nums">
                      {phaseZ ? `${formatKurz(phaseZ.start)} – ${formatKurz(phaseZ.ende)}` : ""} · {g.phase.fortschritt} %
                    </span>
                  )}
                </div>
                {g.kinder.length === 0 ? (
                  <p className="px-4 text-sm text-label2">Noch keine Schritte.</p>
                ) : (
                  <GroupedList>
                    {g.kinder.map((e, i) => {
                      const z = pos.get(e.id);
                      const aktiv = !e.erledigt && !!z && z.start <= heute && heute <= z.ende;
                      const dieseWoche = !e.erledigt && !aktiv && !!z && z.start <= montag + 6 && z.ende >= montag;
                      return (
                        <div key={e.id} className={aktiv || dieseWoche ? "bg-tintbg" : ""}>
                          <GroupedListRow last={i === g.kinder.length - 1} minHoehe={56}>
                            <span className="flex w-5 shrink-0 justify-center">{symbol(e)}</span>
                            <div className="min-w-0 flex-1">
                              <p className={`truncate text-[17px] ${e.erledigt ? "text-label2 line-through" : "text-label"}`}>{e.titel}</p>
                              <p className="truncate text-[13px] text-label2">
                                {zeitraumText(e, z)}
                                {zusatz(e) ? ` · ${zusatz(e)}` : ""}
                              </p>
                              {e.vorgang && (
                                <div className="mt-1">
                                  <StatusPille status={vorgangStatusZuToken(e.vorgang.status)} label={`${e.vorgang.vorgangsnummer} · ${VORGANG_STATUS_LABEL[e.vorgang.status]}`} />
                                </div>
                              )}
                            </div>
                            <div className="flex shrink-0 flex-col items-end gap-1 text-[13px] text-label2 tabular-nums">
                              {aktiv && <span className="rounded-full bg-tint-solid px-2 py-0.5 text-[11px] font-semibold text-white">Heute</span>}
                              {dieseWoche && <span className="rounded-full bg-tint-solid px-2 py-0.5 text-[11px] font-semibold text-white">Diese Woche</span>}
                              {e.typ === "schritt" && <span>{e.erledigt ? "Erledigt" : `${e.fortschritt} %`}</span>}
                              {e.typ === "meilenstein" && e.erledigt && <span>Erledigt</span>}
                            </div>
                          </GroupedListRow>
                        </div>
                      );
                    })}
                  </GroupedList>
                )}
              </section>
            );
          })
        )}
      </div>
    </div>
  );
}
