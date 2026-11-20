import { useEffect } from "react";
import { Navigate, Outlet, Route, Routes, useSearchParams } from "react-router-dom";

import { useGlobaleSucheFenster } from "../components/suche/GlobaleSucheProvider";
import { useAuth } from "../context/AuthContext";
import { AccountTypenPage } from "../pages/AccountTypenPage";
import { UsersPage } from "../pages/UsersPage";
import { AngebotDetailPage } from "../pages/feld/AngebotDetailPage";
import { AnlagenFelderPage } from "../pages/feld/AnlagenFelderPage";
import { AnlageProfilePage } from "../pages/feld/AnlageProfilePage";
import { BestellungDetailPage } from "../pages/feld/BestellungDetailPage";
import { DauerauftragDetailPage } from "../pages/feld/DauerauftragDetailPage";
import { DauerauftragNeuPage } from "../pages/feld/DauerauftragNeuPage";
import { DauerauftraegePage } from "../pages/feld/DauerauftraegePage";
import { EingangsrechnungDetailPage } from "../pages/feld/EingangsrechnungDetailPage";
import { FormSchemaEditorPage } from "../pages/feld/FormSchemaEditorPage";
import { OfficeFormularePage } from "./formulare/OfficeFormularePage";
import { FormSubmissionAusfuellenPage } from "../pages/feld/FormSubmissionAusfuellenPage";
import { HighlightsPage } from "../pages/feld/HighlightsPage";
import { IntegrationenPage } from "../pages/feld/IntegrationenPage";
import { OfficeArbeitszeitEinstellungenPage } from "./zeit/OfficeArbeitszeitEinstellungenPage";
import { OfficeAbwesenheitenPage } from "./zeit/OfficeAbwesenheitenPage";
import { OfficeArbeitszeitPage } from "./zeit/OfficeArbeitszeitPage";
import { LeistungsverzeichnisDetailPage } from "../pages/feld/LeistungsverzeichnisDetailPage";
import { LeistungsverzeichnisPage } from "../pages/feld/LeistungsverzeichnisPage";
import { MeineAufgabeSeite } from "./aufgaben/MeineAufgabeSeite";
import { MeineAufgabenOffice } from "./aufgaben/MeineAufgabenOffice";
import { NewVorgangPage } from "../pages/feld/NewVorgangPage";
import { PapierkorbPage } from "../pages/feld/PapierkorbPage";
import { KiVerbindenPage } from "../pages/KiVerbindenPage";
import { ProfilePage } from "../pages/feld/ProfilePage";
import { OfficePruefmittelPage } from "./pruefmittel/OfficePruefmittelPage";
import { RechnungDetailPage } from "../pages/feld/RechnungDetailPage";
import { SettingsPage } from "../pages/feld/SettingsPage";
import { StandortDetailPage } from "../pages/feld/StandortDetailPage";
import { TeamZeitenPage } from "../pages/feld/TeamZeitenPage";
import { TechnikerZuweisungenPage } from "../pages/feld/TechnikerZuweisungenPage";
import { Karte } from "./OfficeUi";
import { VorgangDetailPage } from "../pages/feld/VorgangDetailPage";
import { ZeitenBuchenPage } from "../pages/feld/ZeitenBuchenPage";
import { RouteGuard } from "../components/RouteGuard";
import { OfficeKundenPage } from "./kunden/OfficeKundenPage";
import { OfficePartnerPage } from "./partner/OfficePartnerPage";
import { KennzahlenPage } from "./kennzahlen/KennzahlenPage";
import { OfficeLayout } from "./OfficeLayout";
import { OfficeMaterialPage } from "./material/OfficeMaterialPage";
import { OfficeNavKategorienPage } from "./OfficeNavKategorienPage";
import { OfficeNavSettingsPage } from "./OfficeNavSettingsPage";
import { OfficeBoardPage } from "./boards/OfficeBoardPage";
import { OfficeAuftraegePage } from "./auftraege/OfficeAuftraegePage";
import { OfficeBoardsPage } from "./boards/OfficeBoardsPage";
import { OfficeBuchhaltungPage } from "./buchhaltung/OfficeBuchhaltungPage";
import { OfficeDatenimportPage } from "./datenimport/OfficeDatenimportPage";
import { OfficeDispoPage } from "./dispo/OfficeDispoPage";
import { OrganigrammPage } from "./organigramm/OrganigrammPage";
import { OfficeFehlerberichtDetailPage, OfficeFehlerberichtePage } from "./fehlerberichte/OfficeFehlerberichtePage";
import { OfficePostfachPage } from "./postfach/OfficePostfachPage";
import { PostfachEinstellungenPage } from "./postfach/PostfachEinstellungenPage";
import { OfficeExportPage } from "./export/OfficeExportPage";
import { OfficeProtokollPage } from "./protokoll/OfficeProtokollPage";
import { OfficeProjektePage } from "./projekte/OfficeProjektePage";
import { OfficeProjektVorlagenPage } from "./projekte/OfficeProjektVorlagenPage";
import { OfficeRechnungenPage } from "./rechnungen/OfficeRechnungenPage";
import { OfficeAnfragenPage } from "./anfragen/OfficeAnfragenPage";
import { OfficeRechnungseingangPage } from "./rechnungseingang/OfficeRechnungseingangPage";
import { OfficeTelefonatePage } from "./telefonate/OfficeTelefonatePage";
import { OfficeVorgaengePage } from "./vorgaenge/OfficeVorgaengePage";
import { NichtGefunden } from "../components/NichtGefunden";

/** `/suche?q=…` bleibt als Deep-Link: das Fenster öffnet sich über der Startseite, die Adresse wird ersetzt. */
function SucheDeepLink({ startseite }: { startseite: string }) {
  const [params] = useSearchParams();
  const { oeffnen } = useGlobaleSucheFenster();
  const q = params.get("q") ?? "";
  useEffect(() => {
    oeffnen(q);
  }, [oeffnen, q]);
  return <Navigate to={startseite} replace />;
}

/** Router der Desktop-Oberflaeche. Die drei ausgebauten Bereiche (Vorgaenge,
 * Rechnungen/Angebote, Dispo/Buchhaltung) haben eigene, auf die Breite
 * ausgelegte Seiten; alles Uebrige nutzt bewusst dieselbe Komponente wie die
 * Feld-App -- diese Seiten sind ohnehin schmale Formular-/Detailansichten,
 * fuer die eine zweite Fassung nur Pflegeaufwand waere. Das Formular-Modul
 * (Schema-Editor + Ausfuellen) gehoert bewusst hierher statt zu den
 * ausgebauten Bereichen: kein Drag&Drop-Canvas mehr (siehe Nicht-Ziel im
 * Migrationsplan), also keine Breite noetig, die eine eigene Desktop-Seite
 * rechtfertigen wuerde. */
export function OfficeApp() {
  const { currentUser } = useAuth();
  const startseite = currentUser?.role === "loesch_ansicht" ? "/papierkorb" : "/vorgaenge";

  return (
    <Routes>
      <Route element={<OfficeLayout />}>
        <Route element={<RouteGuard oberflaeche="office" />}>
          {/* Eigenstaendige Desktop-Ansichten */}
          <Route path="/vorgaenge" element={<OfficeVorgaengePage />} />
          <Route path="/meine-aufgaben" element={<MeineAufgabenOffice />} />
          <Route path="/meine-aufgaben/:id" element={<MeineAufgabeSeite />} />
          <Route path="/dispo" element={<OfficeDispoPage />} />
          <Route path="/rechnungen" element={<OfficeRechnungenPage />} />
          <Route path="/angebote" element={<OfficeRechnungenPage />} />
          <Route path="/auswertung" element={<OfficeBuchhaltungPage />} />
          <Route path="/postfach" element={<OfficePostfachPage />} />
          <Route path="/postfach/einstellungen" element={<PostfachEinstellungenPage />} />
          {/* Tabelle mit Detailpanel braucht die volle Breite, nicht die Lesespalte */}
          <Route path="/anfragen" element={<OfficeAnfragenPage />} />
          <Route path="/anfragen/:id" element={<OfficeAnfragenPage />} />
          <Route path="/telefonate" element={<OfficeTelefonatePage />} />
          {/* Volle Breite: das Kennzahlen-Raster fuellt die Inhaltsflaeche, kein max-w-Wrapper wie bei den Lesespalten. */}
          <Route path="/kennzahlen" element={<KennzahlenPage />} />
          {/* Lesezeichen und Fehlerberichte mit route=/insights landen auf der neuen Seite. */}
          <Route path="/insights" element={<Navigate to="/kennzahlen" replace />} />
          <Route path="/kunden" element={<OfficeKundenPage />} />
          <Route path="/kunden/:id" element={<OfficeKundenPage />} />
          <Route path="/partner" element={<OfficePartnerPage />} />
          <Route path="/partner/:id" element={<OfficePartnerPage />} />
          <Route path="/pruefmittel" element={<OfficePruefmittelPage />} />
          <Route path="/pruefmittel/:id" element={<OfficePruefmittelPage />} />
          <Route path="/material" element={<OfficeMaterialPage />} />
          <Route path="/material/:id" element={<OfficeMaterialPage />} />
          <Route path="/boards" element={<OfficeBoardsPage />} />
          <Route path="/boards/:id" element={<OfficeBoardPage />} />
          <Route path="/projekte" element={<OfficeProjektePage />} />
          <Route path="/projekte/vorlagen" element={<OfficeProjektVorlagenPage />} />
          <Route path="/auftraege" element={<OfficeAuftraegePage />} />
          <Route path="/datenimport" element={<OfficeDatenimportPage />} />
          <Route path="/protokoll" element={<OfficeProtokollPage />} />
          <Route path="/einstellungen/export" element={<OfficeExportPage />} />
          <Route path="/organigramm" element={<OrganigrammPage />} />
          {/* Tabelle mit Detailpanel in voller Breite; "Ganze Seite" haengt den Beleg
              neben die Daten (1400px wie Vorgang-Vollbild), deshalb ausserhalb von
              <SchmaleSpalte>. */}
          <Route path="/rechnungseingang" element={<OfficeRechnungseingangPage />} />
          <Route path="/rechnungseingang/:id" element={<OfficeRechnungseingangPage />} />
          <Route
            path="/rechnungseingang/:id/vollbild"
            element={
              <div className="max-w-[1400px]">
                <EingangsrechnungDetailPage layout="vollbild" />
              </div>
            }
          />
          <Route path="/fehlerberichte" element={<OfficeFehlerberichtePage />} />
          <Route path="/fehlerberichte/:id" element={<OfficeFehlerberichtDetailPage />} />
          {/* "Ganze Seite" aus der Split-Ansicht (VorgaengeListe.tsx) -- volle
              Desktop-Breite statt der schmalen Inspektor-Spalte, deshalb
              bewusst NICHT in <SchmaleSpalte> unten. layout="dicht" fuer
              echte Tabs, breit fuer die staendig sichtbare Verlauf-Spalte
              (siehe VorgangDetailPage.tsx, verlaufSpalteBreit). */}
          <Route
            path="/vorgaenge/:id/vollbild"
            element={
              <div className="max-w-[1400px]">
                <Karte className="office-panel p-4">
                  <VorgangDetailPage layout="dicht" breit />
                </Karte>
              </div>
            }
          />

          {/* Leistungsverzeichnis nutzt die Desktop-Breite (Tabelle, Seitenspalte)
              statt der schmalen Lesespalte; layout="dicht" schaltet die
              Feld-App-Seiten darauf um, ohne die Feld-App zu veraendern. */}
          <Route
            path="/leistungsverzeichnis"
            element={
              <div className="max-w-[1400px]">
                <LeistungsverzeichnisPage layout="dicht" />
              </div>
            }
          />
          <Route
            path="/leistungsverzeichnis/:id"
            element={
              <div className="max-w-[1400px]">
                <LeistungsverzeichnisDetailPage layout="dicht" />
              </div>
            }
          />

          {/* Monatsliste mit allen Kalendertagen braucht die Desktop-Breite;
              die Feld-App behaelt ihre Wochenansicht (StatistikPage). */}
          <Route
            path="/statistik"
            element={
              <div className="max-w-[1760px]">
                <OfficeArbeitszeitPage />
              </div>
            }
          />

          {/* Zeiten buchen vergleicht viele Eintraege spaltenweise (Dauer, Status, Vorgang) und braucht
              dafuer die Desktop-Breite; die Feld-App behaelt die Kartenliste. */}
          <Route path="/zeiten-buchen" element={<div className="max-w-[1400px]"><ZeitenBuchenPage layout="dicht" /></div>} />

          {/* Formulare: Vorlagen-/Protokolltabelle mit Vorschau-Panel und der Drei-Spalten-Baukasten
              brauchen die Desktop-Breite; die Feld-App behaelt FormSchemasPage (schmal, mobil). */}
          <Route
            path="/form-schemas"
            element={
              <div className="max-w-[1760px]">
                <OfficeFormularePage />
              </div>
            }
          />
          <Route
            path="/form-schemas/:id"
            element={
              <div className="max-w-[1760px]">
                <FormSchemaEditorPage layout="office" />
              </div>
            }
          />

          {/* Rechte-Matrix je Account-Typ braucht die Desktop-Breite (Bereich x 9 Aktionen). */}
          <Route
            path="/account-typen"
            element={
              <div className="max-w-[1400px]">
                <AccountTypenPage />
              </div>
            }
          />

          {/* Profil braucht zwei Spalten, deshalb ausserhalb der schmalen Lesespalte */}
          <Route path="/profil" element={<ProfilePage layout="office" />} />

          {/* Aus der Feld-App uebernommen, in begrenzter Lesespalte */}
          <Route element={<SchmaleSpalte />}>
          <Route path="/feed" element={<Navigate to="/vorgaenge" replace />} />
          <Route path="/vorgaenge/:id" element={<VorgangDetailPage />} />
          <Route path="/vorgaenge/:id/zeit" element={<VorgangDetailPage ansicht="zeit" />} />
          <Route path="/vorgaenge/:id/verlauf" element={<VorgangDetailPage ansicht="verlauf" />} />
          <Route path="/vorgaenge/:id/positionen" element={<VorgangDetailPage ansicht="positionen" />} />
          <Route path="/ki-verbinden" element={<KiVerbindenPage layout="office" />} />
          <Route path="/neu" element={<NewVorgangPage />} />
          <Route path="/suche" element={<SucheDeepLink startseite={startseite} />} />
          <Route path="/anlagen/:id" element={<AnlageProfilePage />} />
          <Route path="/standorte/:id" element={<StandortDetailPage />} />
          <Route path="/anlagen-felder" element={<AnlagenFelderPage />} />
          <Route path="/form-submissions/:id" element={<FormSubmissionAusfuellenPage />} />
          <Route path="/dauerauftraege" element={<DauerauftraegePage />} />
          <Route path="/dauerauftraege/neu" element={<DauerauftragNeuPage />} />
          <Route path="/dauerauftraege/:id" element={<DauerauftragDetailPage />} />
          <Route path="/angebote/:id" element={<AngebotDetailPage />} />
          <Route path="/rechnungen/:id" element={<RechnungDetailPage />} />
          <Route path="/bestellungen/:id" element={<BestellungDetailPage />} />
          <Route path="/highlights" element={<HighlightsPage />} />
          <Route path="/integrationen" element={<IntegrationenPage />} />
          <Route path="/accounts" element={<UsersPage />} />
          <Route path="/einstellungen" element={<SettingsPage />} />
          <Route path="/einstellungen/seitenleiste" element={<OfficeNavSettingsPage />} />
          <Route path="/einstellungen/arbeitszeit" element={<OfficeArbeitszeitEinstellungenPage />} />
          <Route path="/abwesenheiten" element={<OfficeAbwesenheitenPage />} />
          <Route path="/einstellungen/kategorien" element={<OfficeNavKategorienPage />} />
          <Route path="/techniker-zuweisungen" element={<TechnikerZuweisungenPage />} />
          <Route path="/team-zeiten" element={<TeamZeitenPage />} />
          <Route path="/papierkorb" element={<PapierkorbPage />} />
          </Route>

          <Route path="/" element={<Navigate to={startseite} replace />} />
          <Route path="*" element={<NichtGefunden startRoute={startseite} alsH1 />} />
        </Route>
      </Route>
    </Routes>
  );
}

// Die uebernommenen Seiten sind fuer eine schmale Spalte entworfen. Ueber die
// volle Monitorbreite gezerrt werden Formulare und Detailansichten unlesbar,
// deshalb bekommen sie hier eine begrenzte Lesespalte statt der vollen Breite.
function SchmaleSpalte() {
  return (
    <div className="office-schmal max-w-3xl">
      <Outlet />
    </div>
  );
}
