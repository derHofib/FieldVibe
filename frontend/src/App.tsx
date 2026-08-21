import { Suspense, lazy } from "react";
import { Navigate, Route, Routes } from "react-router-dom";

import { AccountTypenPage } from "./pages/AccountTypenPage";
import { FeldLayout } from "./components/FeldLayout";
import { Layout } from "./components/Layout";
import { useAuth } from "./context/AuthContext";
import { AuditLogPage } from "./pages/AuditLogPage";
import { DsgvoPage } from "./pages/DsgvoPage";
import { EinstellungenPage } from "./pages/EinstellungenPage";
import { LoginPage } from "./pages/LoginPage";
import { MandantDetailPage } from "./pages/MandantDetailPage";
import { MandantenPage } from "./pages/MandantenPage";
import { RegistrierenPage } from "./pages/RegistrierenPage";
import { UebersichtPage } from "./pages/UebersichtPage";
import { UsersPage } from "./pages/UsersPage";
import { AnfragenPage } from "./pages/feld/AnfragenPage";
import { AngebotDetailPage } from "./pages/feld/AngebotDetailPage";
import { AnlagenFelderPage } from "./pages/feld/AnlagenFelderPage";
import { AnlageProfilePage } from "./pages/feld/AnlageProfilePage";
import { AuswertungPage } from "./pages/feld/AuswertungPage";
import { BestellungDetailPage } from "./pages/feld/BestellungDetailPage";
import { BoardMobilePage } from "./pages/feld/boards/BoardMobilePage";
import { BoardsUebersichtPage } from "./pages/feld/boards/BoardsUebersichtPage";
import { BottomNavSettingsPage } from "./pages/feld/BottomNavSettingsPage";
import { DauerauftragDetailPage } from "./pages/feld/DauerauftragDetailPage";
import { DauerauftragNeuPage } from "./pages/feld/DauerauftragNeuPage";
import { DauerauftraegePage } from "./pages/feld/DauerauftraegePage";
import { DispoBoardPage } from "./pages/feld/DispoBoardPage";
import { EingangsrechnungDetailPage } from "./pages/feld/EingangsrechnungDetailPage";
import { FeedPage } from "./pages/feld/FeedPage";
import { FormularAusfuellenPage } from "./pages/feld/FormularAusfuellenPage";
import { FormularDetailPage } from "./pages/feld/FormularDetailPage";
import { FormularePage } from "./pages/feld/FormularePage";
import { HighlightsPage } from "./pages/feld/HighlightsPage";
import { InsightsPage } from "./pages/feld/InsightsPage";
import { IntegrationenPage } from "./pages/feld/IntegrationenPage";
import { KundenPage } from "./pages/feld/KundenPage";
import { KundeProfilePage } from "./pages/feld/KundeProfilePage";
import { MaterialDetailPage } from "./pages/feld/MaterialDetailPage";
import { MaterialPage } from "./pages/feld/MaterialPage";
import { NewVorgangPage } from "./pages/feld/NewVorgangPage";
import { NotificationsPage } from "./pages/feld/NotificationsPage";
import { PapierkorbPage } from "./pages/feld/PapierkorbPage";
import { PostfachNachrichtPage } from "./pages/feld/PostfachNachrichtPage";
import { PostfachPage } from "./pages/feld/PostfachPage";
import { PruefmittelPage } from "./pages/feld/PruefmittelPage";
import { ProfilePage } from "./pages/feld/ProfilePage";
import { RechnungDetailPage } from "./pages/feld/RechnungDetailPage";
import { RechnungenPage } from "./pages/feld/RechnungenPage";
import { RechnungseingangPage } from "./pages/feld/RechnungseingangPage";
import { SearchPage } from "./pages/feld/SearchPage";
import { SettingsPage } from "./pages/feld/SettingsPage";
import { StandortDetailPage } from "./pages/feld/StandortDetailPage";
import { StatistikPage } from "./pages/feld/StatistikPage";
import { TeamZeitenPage } from "./pages/feld/TeamZeitenPage";
import { TechnikerZuweisungenPage } from "./pages/feld/TechnikerZuweisungenPage";
import { VorgangDetailPage } from "./pages/feld/VorgangDetailPage";
import { UpdatePage } from "./pages/UpdatePage";
import { KundenPortalApp } from "./portal/KundenPortalApp";

// Nachgeladen statt fest importiert: Handy-Nutzer sollen den Desktop-Code nie
// herunterladen. Gleiches Muster wie das lazy MapboxFeedMap im Feed.
const OfficeAppLazy = lazy(() =>
  import("./office/OfficeApp").then((m) => ({ default: m.OfficeApp })),
);

function OfficeApp() {
  return (
    <Suspense fallback={<div className="p-6 text-slate-500 dark:text-stone-400">Lädt…</div>}>
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
    <Routes>
      <Route path="/portal/*" element={<KundenPortalApp />} />

      <Route
        path="/login"
        element={isAuthenticated ? <Navigate to="/" replace /> : <LoginPage />}
      />
      <Route path="/registrieren" element={<RegistrierenPage />} />

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
        <Route element={<Layout />}>
          <Route path="/uebersicht" element={<UebersichtPage />} />
          <Route path="/mandanten" element={<MandantenPage />} />
          <Route path="/mandanten/:id" element={<MandantDetailPage />} />
          <Route path="/accounts" element={<UsersPage />} />
          <Route path="/audit-log" element={<AuditLogPage />} />
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
          <Route path="/kunden/:id" element={<KundeProfilePage />} />
          <Route path="/anlagen/:id" element={<AnlageProfilePage />} />
          <Route path="/standorte/:id" element={<StandortDetailPage />} />
          <Route path="/anlagen-felder" element={<AnlagenFelderPage />} />
          <Route path="/formulare" element={<FormularePage />} />
          <Route path="/formulare/:id" element={<FormularDetailPage />} />
          <Route path="/vorgang-formulare/:id" element={<FormularAusfuellenPage />} />
          <Route path="/dauerauftraege" element={<DauerauftraegePage />} />
          <Route path="/dauerauftraege/neu" element={<DauerauftragNeuPage />} />
          <Route path="/dauerauftraege/:id" element={<DauerauftragDetailPage />} />
          <Route path="/dispo" element={<DispoBoardPage />} />
          <Route path="/boards" element={<BoardsUebersichtPage />} />
          <Route path="/boards/:id" element={<BoardMobilePage />} />
          <Route path="/pruefmittel" element={<PruefmittelPage />} />
          <Route path="/kunden" element={<KundenPage />} />
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
          <Route path="/accounts" element={<UsersPage />} />
          <Route path="/account-typen" element={<AccountTypenPage />} />
          <Route path="/einstellungen" element={<SettingsPage />} />
          <Route path="/einstellungen/menueleiste" element={<BottomNavSettingsPage />} />
          <Route path="/techniker-zuweisungen" element={<TechnikerZuweisungenPage />} />
          <Route path="/statistik" element={<StatistikPage />} />
          <Route path="/team-zeiten" element={<TeamZeitenPage />} />
          <Route path="/papierkorb" element={<PapierkorbPage />} />
          <Route path="*" element={<Navigate to={standardStartseite} replace />} />
        </Route>
      )}
    </Routes>
  );
}
