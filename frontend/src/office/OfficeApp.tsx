import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { OfficeLayout } from "./OfficeLayout";
import { lazyMitRetry } from "../components/Nachladen";

// Nachgeladen: wird erst beim Aufruf der Route geholt (siehe components/Nachladen.tsx).
const AccountTypenPage = lazyMitRetry(() => import("../pages/AccountTypenPage").then((m) => ({ default: m.AccountTypenPage })));
const UsersPage = lazyMitRetry(() => import("../pages/UsersPage").then((m) => ({ default: m.UsersPage })));
const AnfragenPage = lazyMitRetry(() => import("../pages/feld/AnfragenPage").then((m) => ({ default: m.AnfragenPage })));
const AngebotDetailPage = lazyMitRetry(() => import("../pages/feld/AngebotDetailPage").then((m) => ({ default: m.AngebotDetailPage })));
const AnlagenFelderPage = lazyMitRetry(() => import("../pages/feld/AnlagenFelderPage").then((m) => ({ default: m.AnlagenFelderPage })));
const AnlageProfilePage = lazyMitRetry(() => import("../pages/feld/AnlageProfilePage").then((m) => ({ default: m.AnlageProfilePage })));
const BestellungDetailPage = lazyMitRetry(() => import("../pages/feld/BestellungDetailPage").then((m) => ({ default: m.BestellungDetailPage })));
const DauerauftragDetailPage = lazyMitRetry(() => import("../pages/feld/DauerauftragDetailPage").then((m) => ({ default: m.DauerauftragDetailPage })));
const DauerauftragNeuPage = lazyMitRetry(() => import("../pages/feld/DauerauftragNeuPage").then((m) => ({ default: m.DauerauftragNeuPage })));
const DauerauftraegePage = lazyMitRetry(() => import("../pages/feld/DauerauftraegePage").then((m) => ({ default: m.DauerauftraegePage })));
const EingangsrechnungDetailPage = lazyMitRetry(() => import("../pages/feld/EingangsrechnungDetailPage").then((m) => ({ default: m.EingangsrechnungDetailPage })));
const FormSchemaEditorPage = lazyMitRetry(() => import("../pages/feld/FormSchemaEditorPage").then((m) => ({ default: m.FormSchemaEditorPage })));
const FormSchemasPage = lazyMitRetry(() => import("../pages/feld/FormSchemasPage").then((m) => ({ default: m.FormSchemasPage })));
const FormSubmissionAusfuellenPage = lazyMitRetry(() => import("../pages/feld/FormSubmissionAusfuellenPage").then((m) => ({ default: m.FormSubmissionAusfuellenPage })));
const HighlightsPage = lazyMitRetry(() => import("../pages/feld/HighlightsPage").then((m) => ({ default: m.HighlightsPage })));
const InsightsPage = lazyMitRetry(() => import("../pages/feld/InsightsPage").then((m) => ({ default: m.InsightsPage })));
const IntegrationenPage = lazyMitRetry(() => import("../pages/feld/IntegrationenPage").then((m) => ({ default: m.IntegrationenPage })));
const OfficeArbeitszeitEinstellungenPage = lazyMitRetry(() => import("./zeit/OfficeArbeitszeitEinstellungenPage").then((m) => ({ default: m.OfficeArbeitszeitEinstellungenPage })));
const OfficeAbwesenheitenPage = lazyMitRetry(() => import("./zeit/OfficeAbwesenheitenPage").then((m) => ({ default: m.OfficeAbwesenheitenPage })));
const OfficeArbeitszeitPage = lazyMitRetry(() => import("./zeit/OfficeArbeitszeitPage").then((m) => ({ default: m.OfficeArbeitszeitPage })));
const LeistungsverzeichnisDetailPage = lazyMitRetry(() => import("../pages/feld/LeistungsverzeichnisDetailPage").then((m) => ({ default: m.LeistungsverzeichnisDetailPage })));
const LeistungsverzeichnisPage = lazyMitRetry(() => import("../pages/feld/LeistungsverzeichnisPage").then((m) => ({ default: m.LeistungsverzeichnisPage })));
const KundenPage = lazyMitRetry(() => import("../pages/feld/KundenPage").then((m) => ({ default: m.KundenPage })));
const KundeProfilePage = lazyMitRetry(() => import("../pages/feld/KundeProfilePage").then((m) => ({ default: m.KundeProfilePage })));
const MaterialDetailPage = lazyMitRetry(() => import("../pages/feld/MaterialDetailPage").then((m) => ({ default: m.MaterialDetailPage })));
const MaterialPage = lazyMitRetry(() => import("../pages/feld/MaterialPage").then((m) => ({ default: m.MaterialPage })));
const MeineAufgabenPage = lazyMitRetry(() => import("../pages/feld/MeineAufgabenPage").then((m) => ({ default: m.MeineAufgabenPage })));
const NewVorgangPage = lazyMitRetry(() => import("../pages/feld/NewVorgangPage").then((m) => ({ default: m.NewVorgangPage })));
const NotificationsPage = lazyMitRetry(() => import("../pages/feld/NotificationsPage").then((m) => ({ default: m.NotificationsPage })));
const PapierkorbPage = lazyMitRetry(() => import("../pages/feld/PapierkorbPage").then((m) => ({ default: m.PapierkorbPage })));
const PlanSymbolePage = lazyMitRetry(() => import("../pages/feld/PlanSymbolePage").then((m) => ({ default: m.PlanSymbolePage })));
const PartnerPage = lazyMitRetry(() => import("../pages/feld/PartnerPage").then((m) => ({ default: m.PartnerPage })));
const PartnerProfilePage = lazyMitRetry(() => import("../pages/feld/PartnerProfilePage").then((m) => ({ default: m.PartnerProfilePage })));
const ProfilePage = lazyMitRetry(() => import("../pages/feld/ProfilePage").then((m) => ({ default: m.ProfilePage })));
const PruefmittelPage = lazyMitRetry(() => import("../pages/feld/PruefmittelPage").then((m) => ({ default: m.PruefmittelPage })));
const RechnungDetailPage = lazyMitRetry(() => import("../pages/feld/RechnungDetailPage").then((m) => ({ default: m.RechnungDetailPage })));
const RechnungseingangPage = lazyMitRetry(() => import("../pages/feld/RechnungseingangPage").then((m) => ({ default: m.RechnungseingangPage })));
const SearchPage = lazyMitRetry(() => import("../pages/feld/SearchPage").then((m) => ({ default: m.SearchPage })));
const SettingsPage = lazyMitRetry(() => import("../pages/feld/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const StandortDetailPage = lazyMitRetry(() => import("../pages/feld/StandortDetailPage").then((m) => ({ default: m.StandortDetailPage })));
const TeamZeitenPage = lazyMitRetry(() => import("../pages/feld/TeamZeitenPage").then((m) => ({ default: m.TeamZeitenPage })));
const TechnikerZuweisungenPage = lazyMitRetry(() => import("../pages/feld/TechnikerZuweisungenPage").then((m) => ({ default: m.TechnikerZuweisungenPage })));
const VorgangDetailPage = lazyMitRetry(() => import("../pages/feld/VorgangDetailPage").then((m) => ({ default: m.VorgangDetailPage })));
const ZeitenBuchenPage = lazyMitRetry(() => import("../pages/feld/ZeitenBuchenPage").then((m) => ({ default: m.ZeitenBuchenPage })));
const OfficeNavKategorienPage = lazyMitRetry(() => import("./OfficeNavKategorienPage").then((m) => ({ default: m.OfficeNavKategorienPage })));
const OfficeNavSettingsPage = lazyMitRetry(() => import("./OfficeNavSettingsPage").then((m) => ({ default: m.OfficeNavSettingsPage })));
const OfficeBoardPage = lazyMitRetry(() => import("./boards/OfficeBoardPage").then((m) => ({ default: m.OfficeBoardPage })));
const OfficeAuftraegePage = lazyMitRetry(() => import("./auftraege/OfficeAuftraegePage").then((m) => ({ default: m.OfficeAuftraegePage })));
const OfficeBoardsPage = lazyMitRetry(() => import("./boards/OfficeBoardsPage").then((m) => ({ default: m.OfficeBoardsPage })));
const OfficeBuchhaltungPage = lazyMitRetry(() => import("./buchhaltung/OfficeBuchhaltungPage").then((m) => ({ default: m.OfficeBuchhaltungPage })));
const OfficeDatenimportPage = lazyMitRetry(() => import("./datenimport/OfficeDatenimportPage").then((m) => ({ default: m.OfficeDatenimportPage })));
const OfficeDispoPage = lazyMitRetry(() => import("./dispo/OfficeDispoPage").then((m) => ({ default: m.OfficeDispoPage })));
const OrganigrammPage = lazyMitRetry(() => import("./organigramm/OrganigrammPage").then((m) => ({ default: m.OrganigrammPage })));
const OfficeFehlerberichtDetailPage = lazyMitRetry(() => import("./fehlerberichte/OfficeFehlerberichtePage").then((m) => ({ default: m.OfficeFehlerberichtDetailPage })));
const OfficeFehlerberichtePage = lazyMitRetry(() => import("./fehlerberichte/OfficeFehlerberichtePage").then((m) => ({ default: m.OfficeFehlerberichtePage })));
const OfficePostfachPage = lazyMitRetry(() => import("./postfach/OfficePostfachPage").then((m) => ({ default: m.OfficePostfachPage })));
const OfficeExportPage = lazyMitRetry(() => import("./export/OfficeExportPage").then((m) => ({ default: m.OfficeExportPage })));
const OfficeProtokollPage = lazyMitRetry(() => import("./protokoll/OfficeProtokollPage").then((m) => ({ default: m.OfficeProtokollPage })));
const OfficeProjektePage = lazyMitRetry(() => import("./projekte/OfficeProjektePage").then((m) => ({ default: m.OfficeProjektePage })));
const OfficeProjektVorlagenPage = lazyMitRetry(() => import("./projekte/OfficeProjektVorlagenPage").then((m) => ({ default: m.OfficeProjektVorlagenPage })));
const OfficeRechnungenPage = lazyMitRetry(() => import("./rechnungen/OfficeRechnungenPage").then((m) => ({ default: m.OfficeRechnungenPage })));
const OfficeVorgaengePage = lazyMitRetry(() => import("./vorgaenge/OfficeVorgaengePage").then((m) => ({ default: m.OfficeVorgaengePage })));

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
  const { currentUser, hatRecht } = useAuth();
  const hatFehlerberichtRecht = hatRecht("fehlerberichte", "sehen");
  const hatOrganigrammRecht = hatRecht("organigramm", "sehen");
  const startseite = currentUser?.role === "loesch_ansicht" ? "/papierkorb" : "/vorgaenge";

  return (
    <Routes>
      <Route element={<OfficeLayout />}>
        {/* Eigenstaendige Desktop-Ansichten */}
        <Route path="/vorgaenge" element={<OfficeVorgaengePage />} />
        <Route path="/dispo" element={<OfficeDispoPage />} />
        <Route path="/rechnungen" element={<OfficeRechnungenPage />} />
        <Route path="/angebote" element={<OfficeRechnungenPage />} />
        <Route path="/auswertung" element={<OfficeBuchhaltungPage />} />
        <Route path="/postfach" element={<OfficePostfachPage />} />
        <Route path="/boards" element={<OfficeBoardsPage />} />
        <Route path="/boards/:id" element={<OfficeBoardPage />} />
        <Route path="/projekte" element={<OfficeProjektePage />} />
        <Route path="/projekte/vorlagen" element={<OfficeProjektVorlagenPage />} />
        <Route path="/auftraege" element={<OfficeAuftraegePage />} />
        <Route path="/datenimport" element={<OfficeDatenimportPage />} />
        <Route path="/protokoll" element={<OfficeProtokollPage />} />
        <Route path="/einstellungen/export" element={<OfficeExportPage />} />
        {hatOrganigrammRecht && <Route path="/organigramm" element={<OrganigrammPage />} />}
        {hatFehlerberichtRecht && (
          <>
            <Route path="/fehlerberichte" element={<OfficeFehlerberichtePage />} />
            <Route path="/fehlerberichte/:id" element={<OfficeFehlerberichtDetailPage />} />
          </>
        )}
        {/* "Ganze Seite" aus der Split-Ansicht (VorgaengeListe.tsx) -- volle
            Desktop-Breite statt der schmalen Inspektor-Spalte, deshalb
            bewusst NICHT in <SchmaleSpalte> unten. layout="dicht" fuer
            echte Tabs, breit fuer die staendig sichtbare Verlauf-Spalte
            (siehe VorgangDetailPage.tsx, verlaufSpalteBreit). */}
        <Route
          path="/vorgaenge/:id/vollbild"
          element={
            <div className="mx-auto max-w-[1400px]">
              <VorgangDetailPage layout="dicht" breit />
            </div>
          }
        />

        {/* Leistungsverzeichnis nutzt die Desktop-Breite (Tabelle, Seitenspalte)
            statt der schmalen Lesespalte; layout="dicht" schaltet die
            Feld-App-Seiten darauf um, ohne die Feld-App zu veraendern. */}
        <Route
          path="/leistungsverzeichnis"
          element={
            <div className="mx-auto max-w-[1400px]">
              <LeistungsverzeichnisPage layout="dicht" />
            </div>
          }
        />
        <Route
          path="/leistungsverzeichnis/:id"
          element={
            <div className="mx-auto max-w-[1400px]">
              <LeistungsverzeichnisDetailPage layout="dicht" />
            </div>
          }
        />

        {/* Monatsliste mit allen Kalendertagen braucht die Desktop-Breite;
            die Feld-App behaelt ihre Wochenansicht (StatistikPage). */}
        <Route
          path="/statistik"
          element={
            <div className="mx-auto max-w-[1400px]">
              <OfficeArbeitszeitPage />
            </div>
          }
        />

        {/* Rechte-Matrix je Account-Typ braucht die Desktop-Breite (Bereich x 9 Aktionen). */}
        <Route
          path="/account-typen"
          element={
            <div className="mx-auto max-w-[1400px]">
              <AccountTypenPage />
            </div>
          }
        />

        {/* Aus der Feld-App uebernommen, in begrenzter Lesespalte */}
        <Route element={<SchmaleSpalte />}>
        <Route path="/feed" element={<Navigate to="/vorgaenge" replace />} />
        <Route path="/vorgaenge/:id" element={<VorgangDetailPage />} />
        <Route path="/vorgaenge/:id/zeit" element={<VorgangDetailPage ansicht="zeit" />} />
        <Route path="/vorgaenge/:id/verlauf" element={<VorgangDetailPage ansicht="verlauf" />} />
        <Route path="/vorgaenge/:id/positionen" element={<VorgangDetailPage ansicht="positionen" />} />
        <Route path="/neu" element={<NewVorgangPage />} />
        <Route path="/suche" element={<SearchPage />} />
        <Route path="/benachrichtigungen" element={<NotificationsPage />} />
        <Route path="/profil" element={<ProfilePage />} />
        <Route path="/kunden/:id" element={<KundeProfilePage />} />
        <Route path="/partner/:id" element={<PartnerProfilePage />} />
        <Route path="/anlagen/:id" element={<AnlageProfilePage />} />
        <Route path="/standorte/:id" element={<StandortDetailPage />} />
        <Route path="/anlagen-felder" element={<AnlagenFelderPage />} />
        <Route path="/form-submissions/:id" element={<FormSubmissionAusfuellenPage />} />
        <Route path="/form-schemas" element={<FormSchemasPage />} />
        <Route path="/form-schemas/:id" element={<FormSchemaEditorPage />} />
        <Route path="/plan-symbole" element={<PlanSymbolePage />} />
        <Route path="/dauerauftraege" element={<DauerauftraegePage />} />
        <Route path="/dauerauftraege/neu" element={<DauerauftragNeuPage />} />
        <Route path="/dauerauftraege/:id" element={<DauerauftragDetailPage />} />
        <Route path="/pruefmittel" element={<PruefmittelPage />} />
        <Route path="/kunden" element={<KundenPage />} />
        <Route path="/partner" element={<PartnerPage />} />
        <Route path="/material" element={<MaterialPage />} />
        <Route path="/meine-aufgaben" element={<MeineAufgabenPage />} />
        <Route path="/anfragen" element={<AnfragenPage />} />
        <Route path="/angebote/:id" element={<AngebotDetailPage />} />
        <Route path="/rechnungen/:id" element={<RechnungDetailPage />} />
        <Route path="/rechnungseingang" element={<RechnungseingangPage />} />
        <Route path="/rechnungseingang/:id" element={<EingangsrechnungDetailPage />} />
        <Route path="/bestellungen/:id" element={<BestellungDetailPage />} />
        <Route path="/material/:id" element={<MaterialDetailPage />} />
        <Route path="/highlights" element={<HighlightsPage />} />
        <Route path="/insights" element={<InsightsPage />} />
        <Route path="/integrationen" element={<IntegrationenPage />} />
        <Route path="/accounts" element={<UsersPage />} />
        <Route path="/einstellungen" element={<SettingsPage />} />
        <Route path="/einstellungen/seitenleiste" element={<OfficeNavSettingsPage />} />
        <Route path="/einstellungen/arbeitszeit" element={<OfficeArbeitszeitEinstellungenPage />} />
        <Route path="/abwesenheiten" element={<OfficeAbwesenheitenPage />} />
        <Route path="/einstellungen/kategorien" element={<OfficeNavKategorienPage />} />
        <Route path="/techniker-zuweisungen" element={<TechnikerZuweisungenPage />} />
        <Route path="/team-zeiten" element={<TeamZeitenPage />} />
        <Route path="/zeiten-buchen" element={<ZeitenBuchenPage />} />
        <Route path="/papierkorb" element={<PapierkorbPage />} />
        </Route>

        <Route path="*" element={<Navigate to={startseite} replace />} />
      </Route>
    </Routes>
  );
}

// Die uebernommenen Seiten sind fuer eine schmale Spalte entworfen. Ueber die
// volle Monitorbreite gezerrt werden Formulare und Detailansichten unlesbar,
// deshalb bekommen sie hier eine begrenzte Lesespalte statt der vollen Breite.
function SchmaleSpalte() {
  return (
    <div className="mx-auto max-w-3xl">
      <Outlet />
    </div>
  );
}
