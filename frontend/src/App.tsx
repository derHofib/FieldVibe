import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { FehlerberichtAnbindung } from "./components/FehlerberichtAnbindung";
import { MfaErzwingenSeite } from "./components/MfaErzwingenSeite";
import { FeldLayout } from "./components/FeldLayout";
import { useAuth } from "./context/AuthContext";
import { ForgotPasswordPage } from "./pages/ForgotPasswordPage";
import { LoginPage } from "./pages/LoginPage";
import { BarrierefreiheitPage, DatenschutzPage, ImpressumPage } from "./pages/RechtlichesPage";
import { RegistrierenPage } from "./pages/RegistrierenPage";
import { ResetPasswordPage } from "./pages/ResetPasswordPage";
import { AnfragenPage } from "./pages/feld/AnfragenPage";
import { AnlagenFelderPage } from "./pages/feld/AnlagenFelderPage";
import { AnlageProfilePage } from "./pages/feld/AnlageProfilePage";
import { DauerauftragDetailPage } from "./pages/feld/DauerauftragDetailPage";
import { DauerauftragNeuPage } from "./pages/feld/DauerauftragNeuPage";
import { DauerauftraegePage } from "./pages/feld/DauerauftraegePage";
import { FeedPage } from "./pages/feld/FeedPage";
import { FormSubmissionAusfuellenPage } from "./pages/feld/FormSubmissionAusfuellenPage";
import { KundenPage } from "./pages/feld/KundenPage";
import { KundeProfilePage } from "./pages/feld/KundeProfilePage";
import { MaterialDetailPage } from "./pages/feld/MaterialDetailPage";
import { MaterialPage } from "./pages/feld/MaterialPage";
import { MeineAufgabenPage } from "./pages/feld/MeineAufgabenPage";
import { MehrPage } from "./pages/feld/MehrPage";
import { NewVorgangPage } from "./pages/feld/NewVorgangPage";
import { NotificationsPage } from "./pages/feld/NotificationsPage";
import { PartnerPage } from "./pages/feld/PartnerPage";
import { PartnerProfilePage } from "./pages/feld/PartnerProfilePage";
import { PruefmittelPage } from "./pages/feld/PruefmittelPage";
import { ProfilePage } from "./pages/feld/ProfilePage";
import { ProjektePageMobil } from "./pages/feld/ProjektePageMobil";
import { SearchPage } from "./pages/feld/SearchPage";
import { StandortDetailPage } from "./pages/feld/StandortDetailPage";
import { VorgangDetailPage } from "./pages/feld/VorgangDetailPage";
import { SeitenRahmen, lazyMitRetry } from "./components/Nachladen";

// Nachgeladen: wird erst beim Aufruf der Route geholt (siehe components/Nachladen.tsx).
const AccountTypenPage = lazyMitRetry(() => import("./pages/AccountTypenPage").then((m) => ({ default: m.AccountTypenPage })));
const Layout = lazyMitRetry(() => import("./components/Layout").then((m) => ({ default: m.Layout })));
const AuditLogPage = lazyMitRetry(() => import("./pages/AuditLogPage").then((m) => ({ default: m.AuditLogPage })));
const BugfixDetailPage = lazyMitRetry(() => import("./pages/BugfixesPage").then((m) => ({ default: m.BugfixDetailPage })));
const BugfixesPage = lazyMitRetry(() => import("./pages/BugfixesPage").then((m) => ({ default: m.BugfixesPage })));
const DsgvoPage = lazyMitRetry(() => import("./pages/DsgvoPage").then((m) => ({ default: m.DsgvoPage })));
const EinstellungenPage = lazyMitRetry(() => import("./pages/EinstellungenPage").then((m) => ({ default: m.EinstellungenPage })));
const MandantDetailPage = lazyMitRetry(() => import("./pages/MandantDetailPage").then((m) => ({ default: m.MandantDetailPage })));
const MandantenPage = lazyMitRetry(() => import("./pages/MandantenPage").then((m) => ({ default: m.MandantenPage })));
const UebersichtPage = lazyMitRetry(() => import("./pages/UebersichtPage").then((m) => ({ default: m.UebersichtPage })));
const UsersPage = lazyMitRetry(() => import("./pages/UsersPage").then((m) => ({ default: m.UsersPage })));
const AngebotDetailPage = lazyMitRetry(() => import("./pages/feld/AngebotDetailPage").then((m) => ({ default: m.AngebotDetailPage })));
const AuswertungPage = lazyMitRetry(() => import("./pages/feld/AuswertungPage").then((m) => ({ default: m.AuswertungPage })));
const BestellungDetailPage = lazyMitRetry(() => import("./pages/feld/BestellungDetailPage").then((m) => ({ default: m.BestellungDetailPage })));
const BoardMobilePage = lazyMitRetry(() => import("./pages/feld/boards/BoardMobilePage").then((m) => ({ default: m.BoardMobilePage })));
const BoardsUebersichtPage = lazyMitRetry(() => import("./pages/feld/boards/BoardsUebersichtPage").then((m) => ({ default: m.BoardsUebersichtPage })));
const DispoBoardPage = lazyMitRetry(() => import("./pages/feld/DispoBoardPage").then((m) => ({ default: m.DispoBoardPage })));
const EingangsrechnungDetailPage = lazyMitRetry(() => import("./pages/feld/EingangsrechnungDetailPage").then((m) => ({ default: m.EingangsrechnungDetailPage })));
const FormSchemaEditorPage = lazyMitRetry(() => import("./pages/feld/FormSchemaEditorPage").then((m) => ({ default: m.FormSchemaEditorPage })));
const FormSchemasPage = lazyMitRetry(() => import("./pages/feld/FormSchemasPage").then((m) => ({ default: m.FormSchemasPage })));
const PlanSymbolePage = lazyMitRetry(() => import("./pages/feld/PlanSymbolePage").then((m) => ({ default: m.PlanSymbolePage })));
const HighlightsPage = lazyMitRetry(() => import("./pages/feld/HighlightsPage").then((m) => ({ default: m.HighlightsPage })));
const InsightsPage = lazyMitRetry(() => import("./pages/feld/InsightsPage").then((m) => ({ default: m.InsightsPage })));
const IntegrationenPage = lazyMitRetry(() => import("./pages/feld/IntegrationenPage").then((m) => ({ default: m.IntegrationenPage })));
const LeistungsverzeichnisDetailPage = lazyMitRetry(() => import("./pages/feld/LeistungsverzeichnisDetailPage").then((m) => ({ default: m.LeistungsverzeichnisDetailPage })));
const LeistungsverzeichnisPage = lazyMitRetry(() => import("./pages/feld/LeistungsverzeichnisPage").then((m) => ({ default: m.LeistungsverzeichnisPage })));
const PapierkorbPage = lazyMitRetry(() => import("./pages/feld/PapierkorbPage").then((m) => ({ default: m.PapierkorbPage })));
const PostfachNachrichtPage = lazyMitRetry(() => import("./pages/feld/PostfachNachrichtPage").then((m) => ({ default: m.PostfachNachrichtPage })));
const PostfachPage = lazyMitRetry(() => import("./pages/feld/PostfachPage").then((m) => ({ default: m.PostfachPage })));
const ProjektZeitplanMobilPage = lazyMitRetry(() => import("./pages/feld/ProjektZeitplanMobilPage").then((m) => ({ default: m.ProjektZeitplanMobilPage })));
const RechnungDetailPage = lazyMitRetry(() => import("./pages/feld/RechnungDetailPage").then((m) => ({ default: m.RechnungDetailPage })));
const RechnungenPage = lazyMitRetry(() => import("./pages/feld/RechnungenPage").then((m) => ({ default: m.RechnungenPage })));
const RechnungseingangPage = lazyMitRetry(() => import("./pages/feld/RechnungseingangPage").then((m) => ({ default: m.RechnungseingangPage })));
const OfficeArbeitszeitEinstellungenPage = lazyMitRetry(() => import("./office/zeit/OfficeArbeitszeitEinstellungenPage").then((m) => ({ default: m.OfficeArbeitszeitEinstellungenPage })));
const OfficeAbwesenheitenPage = lazyMitRetry(() => import("./office/zeit/OfficeAbwesenheitenPage").then((m) => ({ default: m.OfficeAbwesenheitenPage })));
const SettingsPage = lazyMitRetry(() => import("./pages/feld/SettingsPage").then((m) => ({ default: m.SettingsPage })));
const StatistikPage = lazyMitRetry(() => import("./pages/feld/StatistikPage").then((m) => ({ default: m.StatistikPage })));
const TeamZeitenPage = lazyMitRetry(() => import("./pages/feld/TeamZeitenPage").then((m) => ({ default: m.TeamZeitenPage })));
const TechnikerZuweisungenPage = lazyMitRetry(() => import("./pages/feld/TechnikerZuweisungenPage").then((m) => ({ default: m.TechnikerZuweisungenPage })));
const ZeitenBuchenPage = lazyMitRetry(() => import("./pages/feld/ZeitenBuchenPage").then((m) => ({ default: m.ZeitenBuchenPage })));
const UpdatePage = lazyMitRetry(() => import("./pages/UpdatePage").then((m) => ({ default: m.UpdatePage })));
const KundenPortalApp = lazyMitRetry(() => import("./portal/KundenPortalApp").then((m) => ({ default: m.KundenPortalApp })));
const PartnerPortalApp = lazyMitRetry(() => import("./partner/PartnerPortalApp").then((m) => ({ default: m.PartnerPortalApp })));

// Nachgeladen statt fest importiert: Handy-Nutzer sollen den Desktop-Code nie
// herunterladen. Gleiches Muster wie das lazy MapboxFeedMap im Feed.
const OfficeAppLazy = lazy(() =>
  import("./office/OfficeApp").then((m) => ({ default: m.OfficeApp })),
);

function OfficeApp() {
  return (
    <Suspense fallback={<div className="p-6 text-label2">Lädt…</div>}>
      <OfficeAppLazy />
    </Suspense>
  );
}

export function App({ istOffice = false }: { istOffice?: boolean }) {
  const { currentUser, isAuthenticated, isImpersonating, isLoading } = useAuth();

  // Das Kundenportal ist unabhaengig vom Staff-Login erreichbar -- diese Route
  // muss vor der isAuthenticated-Verzweigung ausgewertet werden, sonst wuerde
  // ein nicht eingeloggter Mitarbeiter-Browser jeden /portal/*-Aufruf auf
  // /login statt /portal/login umleiten.
  if (isLoading) return <div className="p-6">Lädt…</div>;

  // Pflicht-MFA des Betriebs: bis zur Einrichtung nichts anderes anzeigen.
  if (currentUser?.mfa_einrichtung_erforderlich) return <MfaErzwingenSeite />;

  // Platform administration (Mandanten/Accounts/Audit-Log, no Social-UX) is
  // only for a genuine, non-impersonating super_admin. The moment that
  // person starts "Login als Mandant", they should see exactly what a real
  // mandant_admin or custom-Account-Typ in that tenant would see -- the
  // whole point of impersonation as a support tool -- so they get routed
  // into the Feld-App below instead, same as any real tenant user.
  const isPlatformAdmin = currentUser?.role === "super_admin" && !isImpersonating;

  // loesch_ansicht sieht ausschliesslich den Papierkorb (siehe
  // app/api/routes/papierkorb.py) -- /feed wuerde fuer diese Rolle mit 403
  // scheitern, also landet sie beim Login/bei jedem unbekannten Pfad direkt
  // dort statt im sonst ueblichen Feed.
  const standardStartseite = currentUser?.role === "loesch_ansicht" ? "/papierkorb" : "/feed";

  return (
    <FehlerberichtAnbindung>
    <Routes>
      <Route path="/portal/*" element={<SeitenRahmen><KundenPortalApp /></SeitenRahmen>} />
      <Route path="/partnerportal/*" element={<SeitenRahmen><PartnerPortalApp /></SeitenRahmen>} />

      {/* Oeffentlich fuer alle (angemeldet oder nicht, auch auf dem Office-
          Host): die Pflichtlinks muessen ueberall erreichbar sein. Spezifischer
          als der Office-Catch-all /* und der Login-Redirect *. */}
      <Route path="/impressum" element={<ImpressumPage />} />
      <Route path="/datenschutz" element={<DatenschutzPage />} />
      <Route path="/barrierefreiheit" element={<BarrierefreiheitPage />} />

      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
      />
      <Route path="/registrieren" element={<RegistrierenPage />} />
      <Route path="/passwort-vergessen" element={<ForgotPasswordPage />} />
      <Route path="/passwort-zuruecksetzen" element={<ResetPasswordPage />} />

      {!isAuthenticated && <Route path="*" element={<Navigate to="/login" replace />} />}

      {/* Desktop-Oberflaeche (office.-Subdomain). Bewusst NACH der
          Plattform-Admin-Weiche gedacht, aber vor der Feld-App: ein echter
          super_admin behaelt auch hier sein Plattform-Dashboard (Layout.tsx
          ist ohnehin schon eine Desktop-Sidebar), waehrend ein
          impersonierender super_admin wie jeder Mandanten-Nutzer in die
          Office-Shell faellt. */}
      {isAuthenticated && !isPlatformAdmin && istOffice && (
        <Route path="/*" element={<OfficeApp />} />
      )}

      {isAuthenticated && isPlatformAdmin && (
        <Route element={<SeitenRahmen><Layout /></SeitenRahmen>}>
          <Route path="/uebersicht" element={<UebersichtPage />} />
          <Route path="/mandanten" element={<MandantenPage />} />
          <Route path="/mandanten/:id" element={<MandantDetailPage />} />
          <Route path="/accounts" element={<UsersPage />} />
          <Route path="/audit-log" element={<AuditLogPage />} />
          <Route path="/bugfixes" element={<BugfixesPage />} />
          <Route path="/bugfixes/:id" element={<BugfixDetailPage />} />
          <Route path="/dsgvo" element={<DsgvoPage />} />
          <Route path="/update" element={<UpdatePage />} />
          <Route path="/einstellungen" element={<EinstellungenPage />} />
          <Route path="*" element={<Navigate to="/uebersicht" replace />} />
        </Route>
      )}

      {isAuthenticated && !isPlatformAdmin && !istOffice && (
        <Route element={<FeldLayout />}>
          <Route path="/feed" element={<FeedPage />} />
          <Route path="/suche" element={<SearchPage />} />
          <Route path="/neu" element={<NewVorgangPage />} />
          <Route path="/benachrichtigungen" element={<NotificationsPage />} />
          <Route path="/profil" element={<ProfilePage />} />
          <Route path="/vorgaenge/:id" element={<VorgangDetailPage />} />
          <Route path="/vorgaenge/:id/zeit" element={<VorgangDetailPage ansicht="zeit" />} />
          <Route path="/vorgaenge/:id/verlauf" element={<VorgangDetailPage ansicht="verlauf" />} />
          <Route path="/vorgaenge/:id/positionen" element={<VorgangDetailPage ansicht="positionen" />} />
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
          <Route path="/dispo" element={<DispoBoardPage />} />
          <Route path="/meine-aufgaben" element={<MeineAufgabenPage />} />
          <Route path="/mehr" element={<MehrPage />} />
          <Route path="/projekte" element={<ProjektePageMobil />} />
          <Route path="/projekte/:id/zeitplan" element={<ProjektZeitplanMobilPage />} />
          <Route path="/boards" element={<BoardsUebersichtPage />} />
          <Route path="/boards/:id" element={<BoardMobilePage />} />
          <Route path="/pruefmittel" element={<PruefmittelPage />} />
          <Route path="/kunden" element={<KundenPage />} />
          <Route path="/partner" element={<PartnerPage />} />
          <Route path="/material" element={<MaterialPage />} />
          <Route path="/anfragen" element={<AnfragenPage />} />
          <Route path="/angebote/:id" element={<AngebotDetailPage />} />
          <Route path="/rechnungen" element={<RechnungenPage />} />
          <Route path="/rechnungen/:id" element={<RechnungDetailPage />} />
          <Route path="/rechnungseingang" element={<RechnungseingangPage />} />
          <Route path="/rechnungseingang/:id" element={<EingangsrechnungDetailPage />} />
          <Route path="/auswertung" element={<AuswertungPage />} />
          <Route path="/bestellungen/:id" element={<BestellungDetailPage />} />
          <Route path="/material/:id" element={<MaterialDetailPage />} />
          <Route path="/highlights" element={<HighlightsPage />} />
          <Route path="/postfach" element={<PostfachPage />} />
          <Route path="/postfach/:id" element={<PostfachNachrichtPage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/integrationen" element={<IntegrationenPage />} />
          <Route path="/leistungsverzeichnis" element={<LeistungsverzeichnisPage />} />
          <Route path="/leistungsverzeichnis/:id" element={<LeistungsverzeichnisDetailPage />} />
          <Route path="/accounts" element={<UsersPage />} />
          <Route path="/account-typen" element={<AccountTypenPage />} />
          <Route path="/einstellungen" element={<SettingsPage />} />
          <Route path="/einstellungen/arbeitszeit" element={<OfficeArbeitszeitEinstellungenPage />} />
          <Route path="/abwesenheiten" element={<OfficeAbwesenheitenPage />} />
          <Route path="/techniker-zuweisungen" element={<TechnikerZuweisungenPage />} />
          <Route path="/statistik" element={<StatistikPage />} />
          <Route path="/team-zeiten" element={<TeamZeitenPage />} />
          <Route path="/zeiten-buchen" element={<ZeitenBuchenPage />} />
          <Route path="/papierkorb" element={<PapierkorbPage />} />
          <Route path="*" element={<Navigate to={standardStartseite} replace />} />
        </Route>
      )}
    </Routes>
    </FehlerberichtAnbindung>
  );
}
