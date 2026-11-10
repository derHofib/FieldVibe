import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye } from "lucide-react";
import { useEffect, useState } from "react";

import { organigrammApi } from "../../api/endpoints";
import { SeitenPanel } from "../../components/apple/SeitenPanel";
import { StatusPille } from "../../components/apple/StatusPille";
import type { AccountTyp } from "../../types";
import type { OrgEinheit, RechteRegistry } from "../../types/organigramm";
import { BesetzungTab } from "./BesetzungTab";
import { POSITION_STATUS_LABEL, POSITION_STATUS_TOKEN, verstaendlicherFehler } from "./darstellung";
import { RechteTab } from "./RechteTab";
import { StammdatenTab } from "./StammdatenTab";

export type PanelTab = "stammdaten" | "besetzung" | "rechte";

const TABS: { key: PanelTab; label: string }[] = [
  { key: "stammdaten", label: "Stammdaten" },
  { key: "besetzung", label: "Besetzung" },
  { key: "rechte", label: "Rechte" },
];

/** Detailpanel einer Position (rechts): Stammdaten, Besetzung, Rechte. */
export function PositionPanel({
  positionId,
  startTab,
  registry,
  orgEinheiten,
  accountTypen,
  darf,
  onClose,
  onAnzeigenAls,
}: {
  positionId: string;
  startTab: PanelTab;
  registry: RechteRegistry | undefined;
  orgEinheiten: OrgEinheit[];
  accountTypen: AccountTyp[];
  darf: (aktion: string) => boolean;
  onClose: () => void;
  onAnzeigenAls: (positionId: string) => void;
}) {
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<PanelTab>(startTab);
  useEffect(() => setTab(startTab), [startTab, positionId]);

  const { data: detail, error } = useQuery({
    queryKey: ["org-position", positionId],
    queryFn: () => organigrammApi.position(positionId),
  });
  const neuLaden = () => queryClient.invalidateQueries({ queryKey: ["org-position", positionId] });

  return (
    <SeitenPanel
      offen
      titel={detail?.titel ?? "Position"}
      onClose={onClose}
      minBreite={tab === "rechte" ? 1000 : undefined}
      aktionen={
        <button type="button" onClick={() => onAnzeigenAls(positionId)} className="btn-ap">
          <Eye size={14} strokeWidth={2} aria-hidden="true" />
          Anzeigen als …
        </button>
      }
    >
      {error ? (
        <p role="alert" className="p-4 text-sm text-st-fehlt">
          {verstaendlicherFehler(error, "Position konnte nicht geladen werden")}
        </p>
      ) : !detail ? (
        <p className="p-4 text-sm text-label2">Lädt…</p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 px-4 pt-3">
            {detail.status && <StatusPille status={POSITION_STATUS_TOKEN[detail.status]} label={POSITION_STATUS_LABEL[detail.status]} />}
            {detail.typ === "stabsstelle" && <span className="rounded-full bg-tintbg px-2 py-0.5 text-xs font-semibold text-tint-text">Stabsstelle</span>}
            {detail.archiviert_am && <span className="rounded-full bg-fill px-2 py-0.5 text-xs font-semibold text-label2">Archiviert</span>}
            <span className="text-xs text-label2">
              {detail.unterpositionen} Unterposition{detail.unterpositionen === 1 ? "" : "en"}
            </span>
          </div>
          <div role="tablist" aria-label="Abschnitte der Position" className="mb-1 flex gap-1 border-b border-sep px-4 pt-3 pb-2 text-sm">
            {TABS.map((t) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                id={`org-tab-${t.key}`}
                aria-selected={tab === t.key}
                aria-controls={`org-tabpanel-${t.key}`}
                onClick={() => setTab(t.key)}
                className={`rounded-[7px] px-2.5 py-1 font-medium whitespace-nowrap ${
                  tab === t.key ? "bg-fill text-label" : "text-label2 hover:text-label"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>

          {tab === "stammdaten" && (
            <StammdatenTab
              detail={detail}
              orgEinheiten={orgEinheiten}
              accountTypen={accountTypen}
              darfBearbeiten={darf("bearbeiten")}
              darfRechteVerwalten={darf("rechte_verwalten")}
              onGespeichert={neuLaden}
            />
          )}
          {tab === "besetzung" && (
            <BesetzungTab detail={detail} darfBearbeiten={darf("bearbeiten") || darf("rechte_verwalten")} onGeaendert={neuLaden} />
          )}
          {tab === "rechte" &&
            (registry ? (
              <RechteTab
                detail={detail}
                registry={registry}
                accountTypen={accountTypen}
                darfRechteVerwalten={darf("rechte_verwalten")}
                onGespeichert={neuLaden}
              />
            ) : (
              <p className="p-4 text-sm text-label2">Rechte-Registry lädt…</p>
            ))}
        </>
      )}
    </SeitenPanel>
  );
}
