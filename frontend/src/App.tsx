import { Navigate, Route, Routes } from "react-router-dom";

import { FeldLayout } from "./components/FeldLayout";
import { Layout } from "./components/Layout";
import { useAuth } from "./context/AuthContext";
import { AuditLogPage } from "./pages/AuditLogPage";
import { LoginPage } from "./pages/LoginPage";
import { MandantenPage } from "./pages/MandantenPage";
import { RechteMatrixPage } from "./pages/RechteMatrixPage";
import { UsersPage } from "./pages/UsersPage";
import { AnfragenPage } from "./pages/feld/AnfragenPage";
import { AngebotDetailPage } from "./pages/feld/AngebotDetailPage";
import { AnlagenFelderPage } from "./pages/feld/AnlagenFelderPage";
import { AnlageProfilePage } from "./pages/feld/AnlageProfilePage";
import { BestellungDetailPage } from "./pages/feld/BestellungDetailPage";
import { DauerauftragDetailPage } from "./pages/feld/DauerauftragDetailPage";
import { DauerauftragNeuPage } from "./pages/feld/DauerauftragNeuPage";
import { DauerauftraegePage } from "./pages/feld/DauerauftraegePage";
import { DispoBoardPage } from "./pages/feld/DispoBoardPage";
import { FeedPage } from "./pages/feld/FeedPage";
import { GeschaeftPage } from "./pages/feld/GeschaeftPage";
import { HighlightsPage } from "./pages/feld/HighlightsPage";
import { InsightsPage } from "./pages/feld/InsightsPage";
import { IntegrationenPage } from "./pages/feld/IntegrationenPage";
import { KundeProfilePage } from "./pages/feld/KundeProfilePage";
import { MaterialDetailPage } from "./pages/feld/MaterialDetailPage";
import { NewVorgangPage } from "./pages/feld/NewVorgangPage";
import { NotificationsPage } from "./pages/feld/NotificationsPage";
import { PapierkorbPage } from "./pages/feld/PapierkorbPage";
import { PruefmittelPage } from "./pages/feld/PruefmittelPage";
import { ProfilePage } from "./pages/feld/ProfilePage";
import { RechnungDetailPage } from "./pages/feld/RechnungDetailPage";
import { SearchPage } from "./pages/feld/SearchPage";
import { StandortDetailPage } from "./pages/feld/StandortDetailPage";
import { StatistikPage } from "./pages/feld/StatistikPage";
import { TechnikerZuweisungenPage } from "./pages/feld/TechnikerZuweisungenPage";
import { VorgangDetailPage } from "./pages/feld/VorgangDetailPage";
import { KundenPortalApp } from "./portal/KundenPortalApp";

export function App() {
  const { currentUser, isAuthenticated, isImpersonating, isLoading } = useAuth();

  // Das Kundenportal ist unabhaengig vom Staff-Login erreichbar -- diese Route
  // muss vor der isAuthenticated-Verzweigung ausgewertet werden, sonst wuerde
  // ein nicht eingeloggter Mitarbeiter-Browser jeden /portal/*-Aufruf auf
  // /login statt /portal/login umleiten.
  if (isLoading) return <div className="p-6">Lädt…</div>;

  // Platform administration (Mandanten/Accounts/Audit-Log, no Social-UX) is
  // only for a genuine, non-impersonating super_admin. The moment that
  // person starts "Login als Mandant", they should see exactly what a real
  // mandant_admin/disponent/techniker in that tenant would see -- the whole
  // point of impersonation as a support tool -- so they get routed into the
  // Feld-App below instead, same as any real tenant user.
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

      {!isAuthenticated && <Route path="*" element={<Navigate to="/login" replace />} />}

      {isAuthenticated && isPlatformAdmin && (
        <Route element={<Layout />}>
          <Route path="/mandanten" element={<MandantenPage />} />
          <Route path="/accounts" element={<UsersPage />} />
          <Route path="/audit-log" element={<AuditLogPage />} />
          <Route path="*" element={<Navigate to="/mandanten" replace />} />
        </Route>
      )}

      {isAuthenticated && !isPlatformAdmin && (
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
          <Route path="/dauerauftraege" element={<DauerauftraegePage />} />
          <Route path="/dauerauftraege/neu" element={<DauerauftragNeuPage />} />
          <Route path="/dauerauftraege/:id" element={<DauerauftragDetailPage />} />
          <Route path="/dispo" element={<DispoBoardPage />} />
          <Route path="/pruefmittel" element={<PruefmittelPage />} />
          <Route path="/geschaeft" element={<GeschaeftPage />} />
          <Route path="/anfragen" element={<AnfragenPage />} />
          <Route path="/angebote/:id" element={<AngebotDetailPage />} />
          <Route path="/rechnungen/:id" element={<RechnungDetailPage />} />
          <Route path="/bestellungen/:id" element={<BestellungDetailPage />} />
          <Route path="/material/:id" element={<MaterialDetailPage />} />
          <Route path="/highlights" element={<HighlightsPage />} />
          <Route path="/insights" element={<InsightsPage />} />
          <Route path="/integrationen" element={<IntegrationenPage />} />
          <Route path="/accounts" element={<UsersPage />} />
          <Route path="/rechte-matrix" element={<RechteMatrixPage />} />
          <Route path="/techniker-zuweisungen" element={<TechnikerZuweisungenPage />} />
          <Route path="/statistik" element={<StatistikPage />} />
          <Route path="/papierkorb" element={<PapierkorbPage />} />
          <Route path="*" element={<Navigate to={standardStartseite} replace />} />
        </Route>
      )}
    </Routes>
  );
}
