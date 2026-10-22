import type { ReactNode } from "react";
import { FormularAbschnitt } from "../../../components/FormularAbschnitt";
import type { Adresse, Anlage, Kunde, Standort, UserAuswahl, Vorgang } from "../../../types";
import { ZuordnungKopf } from "./ZuordnungKopf";
import { StatusBereich } from "./StatusBereich";
import { TermineAbschnitt } from "./TermineAbschnitt";
import { MaengelAbschnitt } from "./MaengelAbschnitt";
import { VerknuepfteAufgaben } from "./VerknuepfteAufgaben";
import { PartnerAbschnitt } from "./PartnerAbschnitt";
import type { MaengelDaten } from "./useVorgangMaengel";
import type { PartnerDaten } from "./useVorgangPartner";
import type { TermineDaten } from "./useVorgangTermine";
import type { UebersichtDaten } from "./useVorgangUebersicht";

interface DichteLinkeSpalteProps {
  anlage: Anlage | undefined;
  anzeigeAdresse: Adresse | null;
  arbeitszeitInhalt: ReactNode;
  istAktiverTab: (ziel: string) => boolean;
  kartenKoordinaten: { lng: number; lat: number } | null;
  kunde: Kunde | undefined;
  layout: "kompakt" | "dicht";
  positionenInhalt: ReactNode;
  standort: Standort | undefined;
  tabPanelProps: (ziel: string) => { role?: "tabpanel"; "aria-labelledby"?: string };
  users: UserAuswahl[] | undefined;
  vorgang: Vorgang;
  maengelDaten: MaengelDaten;
  partnerDaten: PartnerDaten;
  termineDaten: TermineDaten;
  uebersichtDaten: UebersichtDaten;
}

/** Linke Spalte im dichten Layout: Übersicht, Zeit, Termine, Mängel, Aufgaben, Positionen und Partner als Tab-Panels. */
export function DichteLinkeSpalte({
  anlage, anzeigeAdresse, arbeitszeitInhalt, istAktiverTab, kartenKoordinaten, kunde, layout,
  positionenInhalt, standort, tabPanelProps, users, vorgang, maengelDaten, partnerDaten,
  termineDaten, uebersichtDaten,
}: DichteLinkeSpalteProps) {
  const { verknuepfteAufgaben } = maengelDaten;
  const { kannPartnerVerwalten } = partnerDaten;
  return (
    <>
      <div
        id="abschnitt-uebersicht"
        className={`scroll-mt-4 grid gap-4 ${istAktiverTab("abschnitt-uebersicht") ? "" : "hidden"}`}
        {...tabPanelProps("abschnitt-uebersicht")}
      >
        <div className="card-ap p-4">
          <ZuordnungKopf
            anlage={anlage}
            anzeigeAdresse={anzeigeAdresse}
            kartenKoordinaten={kartenKoordinaten}
            kunde={kunde}
            standort={standort}
            vorgang={vorgang}
            uebersichtDaten={uebersichtDaten}
          />
          <StatusBereich vorgang={vorgang} uebersichtDaten={uebersichtDaten} />
        </div>
      </div>

      {layout === "dicht" && (
        <div
          id="abschnitt-zeit"
          className={`scroll-mt-4 card-ap p-3 ${istAktiverTab("abschnitt-zeit") ? "" : "hidden"}`}
          {...tabPanelProps("abschnitt-zeit")}
        >
          {arbeitszeitInhalt}
        </div>
      )}

      <TermineAbschnitt
        istAktiverTab={istAktiverTab}
        layout={layout}
        tabPanelProps={tabPanelProps}
        users={users}
        termineDaten={termineDaten}
      />

      {vorgang && (
        <div className={istAktiverTab("abschnitt-uebersicht") ? "" : "hidden"} {...tabPanelProps("abschnitt-uebersicht")}>
          <FormularAbschnitt vorgangId={vorgang.id} vorgangStatus={vorgang.status} />
        </div>
      )}

      <MaengelAbschnitt
        istAktiverTab={istAktiverTab}
        layout={layout}
        tabPanelProps={tabPanelProps}
        maengelDaten={maengelDaten}
      />

      {(verknuepfteAufgaben ?? []).length > 0 && (
        <VerknuepfteAufgaben maengelDaten={maengelDaten} />
      )}

      {layout === "dicht" && (
        <div
          id="abschnitt-material"
          className={`scroll-mt-4 card-ap p-3 ${istAktiverTab("abschnitt-material") ? "" : "hidden"}`}
          {...tabPanelProps("abschnitt-material")}
        >
          {positionenInhalt}
        </div>
      )}

      {kannPartnerVerwalten && (
        <PartnerAbschnitt
          istAktiverTab={istAktiverTab}
          tabPanelProps={tabPanelProps}
          vorgang={vorgang}
          partnerDaten={partnerDaten}
        />
      )}
    </>
  );
}
