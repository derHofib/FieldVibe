import { Navigate, Outlet, Route, Routes } from "react-router-dom";

import { useAuth } from "../context/AuthContext";
import { AccountTypenPage } from "../pages/AccountTypenPage";
import { UsersPage } from "../pages/UsersPage";
import { AnfragenPage } from "../pages/feld/AnfragenPage";
import { AngebotDetailPage } from "../pages/feld/AngebotDetailPage";
import { AnlagenFelderPage } from "../pages/feld/AnlagenFelderPage";
import { AnlageProfilePage } from "../pages/feld/AnlageProfilePage";
import { BestellungDetailPage } from "../pages/feld/BestellungDetailPage";
import { DauerauftragDetailPage } from "../pages/feld/DauerauftragDetailPage";
import { DauerauftragNeuPage } from "../pages/feld/DauerauftragNeuPage";
import { DauerauftraegePage } from "../pages/feld/DauerauftraegePage";
import { EingangsrechnungDetailPage } from "../pages/feld/EingangsrechnungDetailPage";
import { FormularAusfuellenPage } from "../pages/feld/FormularAusfuellenPage";
import { GeschaeftPage } from "../pages/feld/GeschaeftPage";
import { HighlightsPage } from "../pages/feld/HighlightsPage";
import { InsightsPage } from "../pages/feld/InsightsPage";
import { IntegrationenPage } from "../pages/feld/IntegrationenPage";
import { KundeProfilePage } from "../pages/feld/KundeProfilePage";
import { MaterialDetailPage } from "../pages/feld/MaterialDetailPage";
import { NewVorgangPage } from "../pages/feld/NewVorgangPage";
import { NotificationsPage } from "../pages/feld/NotificationsPage";
import { PapierkorbPage } from "../pages/feld/PapierkorbPage";
import { ProfilePage } from "../pages/feld/ProfilePage";
import { PruefmittelPage } from "../pages/feld/PruefmittelPage";
import { RechnungDetailPage } from "../pages/feld/RechnungDetailPage";
import { RechnungseingangPage } from "../pages/feld/RechnungseingangPage";
import { SearchPage } from "../pages/feld/SearchPage";
import { SettingsPage } from "../pages/feld/SettingsPage";
import { StandortDetailPage } from "../pages/feld/StandortDetailPage";
import { StatistikPage } from "../pages/feld/StatistikPage";
import { TeamZeitenPage } from "../pages/feld/TeamZeitenPage";
import { TechnikerZuweisungenPage } from "../pages/feld/TechnikerZuweisungenPage";
import { VorgangDetailPage } from "../pages/feld/VorgangDetailPage";
import { OfficeLayout } from "./OfficeLayout";
import { OfficeNavSettingsPage } from "./OfficeNavSettingsPage";
import { OfficeBuchhaltungPage } from "./buchhaltung/OfficeBuchhaltungPage";
import { OfficeDispoPage } from "./dispo/OfficeDispoPage";
import { OfficeFormularDetailPage } from "./formulare/OfficeFormularDetailPage";
import { OfficeFormularePage } from "./formulare/OfficeFormularePage";
import { OfficePostfachPage } from "./postfach/OfficePostfachPage";
import { OfficeRechnungenPage } from "./rechnungen/OfficeRechnungenPage";
import { OfficeVorgaengePage } from "./vorgaenge/OfficeVorgaengePage";

/** Router der Desktop-Oberflaeche. Die vier ausgebauten Bereiche (Vorgaenge,
 * Rechnungen/Angebote, Formulare, Dispo/Buchhaltung) haben eigene, auf die
 * Breite ausgelegte Seiten; alles Uebrige nutzt bewusst dieselbe Komponente
 * wie die Feld-App -- diese Seiten sind ohnehin schmale Formular-/
 * Detailansichten, fuer die eine zweite Fassung nur Pflegeaufwand waere. */
export function OfficeApp() {
  const { currentUser } = useAuth();
  const startseite = currentUser?.role === "loesch_ansicht" ? "/papierkorb" : "/vorgaenge";

  return (
    <Routes>
      <Route element={<OfficeLayout />}>
        {/* Eigenstaendige Desktop-Ansichten */}
        <Route path="/vorgaenge" element={<OfficeVorgaengePage />} />
        <Route path="/dispo" element={<OfficeDispoPage />} />
        <Route path="/rechnungen" element={<OfficeRechnungenPage />} />
        <Route path="/angebote" element={<OfficeRechnungenPage />} />
        <Route path="/formulare" element={<OfficeFormularePage />} />
        <Route path="/formulare/:id" element={<OfficeFormularDetailPage />} />
        <Route path="/auswertung" element={<OfficeBuchhaltungPage />} />
        <Route path="/postfach" element={<OfficePostfachPage />} />

        {/* Aus der Feld-App uebernommen, in begrenzter Lesespalte */}
        <Route element={<SchmaleSpalte />}>
        <Route path="/feed" element={<Navigate to="/vorgaenge" replace />} />
        <Route path="/vorgaenge/:id" element={<VorgangDetailPage />} />
        <Route path="/neu" element={<NewVorgangPage />} />
        <Route path="/suche" element={<SearchPage />} />
        <Route path="/benachrichtigungen" element={<NotificationsPage />} />
        <Route path="/profil" element={<ProfilePage />} />
        <Route path="/kunden/:id" element={<KundeProfilePage />} />
        <Route path="/anlagen/:id" element={<AnlageProfilePage />} />
        <Route path="/standorte/:id" element={<StandortDetailPage />} />
        <Route path="/anlagen-felder" element={<AnlagenFelderPage />} />
        <Route path="/vorgang-formulare/:id" element={<FormularAusfuellenPage />} />
        <Route path="/dauerauftraege" element={<DauerauftraegePage />} />
        <Route path="/dauerauftraege/neu" element={<DauerauftragNeuPage />} />
        <Route path="/dauerauftraege/:id" element={<DauerauftragDetailPage />} />
        <Route path="/pruefmittel" element={<PruefmittelPage />} />
        <Route path="/geschaeft" element={<GeschaeftPage />} />
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
        <Route path="/account-typen" element={<AccountTypenPage />} />
        <Route path="/einstellungen" element={<SettingsPage />} />
        <Route path="/einstellungen/seitenleiste" element={<OfficeNavSettingsPage />} />
        <Route path="/techniker-zuweisungen" element={<TechnikerZuweisungenPage />} />
        <Route path="/statistik" element={<StatistikPage />} />
        <Route path="/team-zeiten" element={<TeamZeitenPage />} />
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
