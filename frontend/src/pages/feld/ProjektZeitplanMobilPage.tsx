import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CalendarRange, ChevronLeft, Diamond, Handshake, Package } from "lucide-react";
import { useState, type ReactNode } from "react";
import { Link, Navigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { zeitplanApi } from "../../api/endpoints";
import { AbschnittskopfA, AbschnittskopfB } from "../../components/apple/AbschnittsKopf";
import { GroupedList, GroupedListRow } from "../../components/apple/GroupedList";
import { StatusPille } from "../../components/apple/StatusPille";
import { VORGANG_STATUS_LABEL, vorgangStatusZuToken } from "../../components/apple/status";
import { useAuth } from "../../context/AuthContext";
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
import {
  ANTRAG_STATUS_LABEL,
  ANTRAG_STATUS_TOKEN,
  antragZeitText,
  beantragbareArten,
} from "../../office/projekte/zeitplan/antragLogik";
import type { ZeitplanAntrag, ZeitplanElement } from "../../types";
import { ZeitplanAntragSheet } from "./ZeitplanAntragSheet";

function zeitraumText(e: ZeitplanElement, z: Zeitraum | undefined): string {
  if (!z) return e.typ === "meilenstein" && e.bestellung ? "Liefertermin offen" : "Ohne Datum";
  if (z.start === z.ende) return formatKurz(z.start);
  return `${formatKurz(z.start)} – ${formatKurz(z.ende)}`;
}

/** Feld-App: Zeitplan eines Projekts als reine Leseliste (keine Zeitleiste,
 * keine Bearbeitung). Heute/diese Woche sind hervorgehoben. Änderungen am Plan
 * gibt es nur als Antrag (ZeitplanAntragSheet), das Büro entscheidet. */
export function ProjektZeitplanMobilPage() {
  const { id } = useParams<{ id: string }>();
  const { currentUser, hatRecht } = useAuth();
  const queryClient = useQueryClient();
  const darfBeantragen = hatRecht("projekte", "zeitplan_beantragen");
  const [antragFuer, setAntragFuer] = useState<ZeitplanElement | null>(null);
  const { data: zeitplan, isLoading, error } = useQuery({
    queryKey: ["projekt-zeitplan", id],
    queryFn: () => zeitplanApi.get(id!),
    enabled: !!id,
    retry: (n, e) => !(e instanceof ApiError && e.status === 403) && n < 2,
  });
  // Eigene Antraege (Server liefert ohne Schreibrecht ohnehin nur die eigenen; Admins sehen alle, hier nur ihre).
  const { data: antraege } = useQuery({
    queryKey: ["zeitplan-antraege", id],
    queryFn: () => zeitplanApi.antraege(id!),
    enabled: !!id && !!zeitplan,
  });
  const eigene = (antraege ?? []).filter((a) => a.erstellt_von === currentUser?.id);
  const zurueckziehen = useMutation({
    mutationFn: (antragId: string) => zeitplanApi.antragZurueckziehen(id!, antragId),
    onSuccess: (antwort) => {
      queryClient.setQueryData(["projekt-zeitplan", id], antwort.zeitplan);
      queryClient.invalidateQueries({ queryKey: ["zeitplan-antraege", id] });
    },
  });
  const heute = heuteTag();
  const montag = montagVon(heute);

  // Ohne Zeitplan-Recht (projekte.sehen bzw. zeitplan_sehen) gibt es den Abschnitt gar nicht -- zurueck zur Liste.
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

  function antragBereich(e: ZeitplanElement): ReactNode {
    const meine = eigene.filter((a) => a.element_id === e.id);
    const offen = meine.find((a) => a.status === "offen");
    const letzter: ZeitplanAntrag | undefined = meine.find((a) => a.status !== "offen" && a.status !== "zurueckgezogen");
    const kannBeantragen = darfBeantragen && !e.erledigt && !offen && beantragbareArten(e).length > 0;
    if (!offen && !letzter && !kannBeantragen) return null;
    return (
      <div className="mt-1.5 space-y-1.5">
        {offen && (
          <div className="space-y-1">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPille status={ANTRAG_STATUS_TOKEN.offen} label={`Antrag ${ANTRAG_STATUS_LABEL.offen.toLowerCase()}`} />
              <span className="text-[13px] text-label2">{antragZeitText(offen)}</span>
            </div>
            <button
              type="button"
              onClick={() => zurueckziehen.mutate(offen.id)}
              disabled={zurueckziehen.isPending}
              className="btn-touch -ml-1 px-1 text-[15px] text-tint-text disabled:opacity-50"
            >
              Antrag zurückziehen
            </button>
          </div>
        )}
        {letzter && (
          <div className="space-y-0.5">
            <div className="flex flex-wrap items-center gap-2">
              <StatusPille status={ANTRAG_STATUS_TOKEN[letzter.status]} label={`Antrag ${ANTRAG_STATUS_LABEL[letzter.status].toLowerCase()}`} />
              <span className="text-[13px] text-label2">{antragZeitText(letzter)}</span>
            </div>
            {letzter.antwort && <p className="text-[13px] text-label2">„{letzter.antwort}“</p>}
          </div>
        )}
        {kannBeantragen && (
          <button type="button" onClick={() => setAntragFuer(e)} className="btn-touch -ml-1 px-1 text-[15px] font-medium text-tint-text">
            Änderung beantragen
          </button>
        )}
      </div>
    );
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
                              {antragBereich(e)}
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
      {antragFuer && id && <ZeitplanAntragSheet projektId={id} element={antragFuer} onClose={() => setAntragFuer(null)} />}
    </div>
  );
}
