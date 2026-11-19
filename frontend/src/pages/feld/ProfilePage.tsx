import { useState } from "react";
import { Building2, LogOut, Mail, MonitorSmartphone, Repeat, Timer } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { authApi } from "../../api/endpoints";
import { AbschnittskopfB } from "../../components/apple/AbschnittsKopf";
import { GroupedList, GroupedListRow } from "../../components/apple/GroupedList";
import { Monogramm } from "../../components/apple/Monogramm";
import { SymbolKachel } from "../../components/apple/SymbolKachel";
import { AppearancePicker } from "../../components/AppearancePicker";
import { useAuth } from "../../context/AuthContext";
import { SeitenKopf } from "../../office/OfficeUi";
import { istModulAktiv } from "../../utils/module";
import { ROLE_LABEL } from "../UsersPage";
import { KiVerbindungenKarte } from "./KiVerbindungenKarte";
import { MfaKarte } from "./MfaKarte";
import { PasswortAendernKarte } from "./PasswortAendernKarte";
import { ProfilArbeitszeitKarte, ProfilUrlaubKarte, ProfilVorgaengeKarte } from "./ProfilUebersichten";
import { useBestaetigung } from "../../components/ConfirmDialog";

/** Profil: Feld-App (einspaltig) und Office (volle Breite mit Kopfzeile, Überblick,
 * Einstellungen und Verbindungen, `layout="office"`) teilen sich diese Seite. */
export function ProfilePage({ layout = "feld" }: { layout?: "feld" | "office" }) {
  const bestaetigen = useBestaetigung();
  const { currentUser, hatRecht, isImpersonating, logout } = useAuth();
  const navigate = useNavigate();
  const [abmeldenLaeuft, setAbmeldenLaeuft] = useState(false);
  const [abmeldenFehler, setAbmeldenFehler] = useState<string | null>(null);
  const office = layout === "office";

  const ueberallAbmelden = async () => {
    if (!(await bestaetigen({ titel: "Auf allen Geräten abmelden?", text: "Du musst dich danach überall neu anmelden.", bestaetigenLabel: "Abmelden", destruktiv: false }))) {
      return;
    }
    setAbmeldenLaeuft(true);
    setAbmeldenFehler(null);
    try {
      await authApi.ueberallAbmelden();
      logout();
    } catch {
      setAbmeldenFehler("Abmelden auf allen Geräten ist fehlgeschlagen.");
      setAbmeldenLaeuft(false);
    }
  };

  // "Disponieren" (Techniker einteilen, Dauer-Auftraege verwalten) bleibt
  // hier auf dem Profil, weil es operative Alltagsarbeit ist, nicht
  // Verwaltung -- die Einstellungen-Seite (Zahnrad im Header) buendelt
  // stattdessen Account-Verwaltung/Firmendaten/Integrationen.
  const kannDisponieren = hatRecht("dispo", "bearbeiten");
  const dauerauftraege = kannDisponieren && istModulAktiv(currentUser, "dauerauftrag");
  const zeiterfassung = istModulAktiv(currentUser, "zeiterfassung");

  // Bei Impersonation gehoert das Profil dem Super-Admin; er hat keine KI-Verbindungen.
  const kiAktiv = !isImpersonating && istModulAktiv(currentUser, "ki_zugriff");
  const kiVerbindungen = kiAktiv && <KiVerbindungenKarte />;

  const rolle =
    currentUser &&
    (currentUser.role === "custom" ? (currentUser.account_typ_name ?? "Account") : ROLE_LABEL[currentUser.role]);

  const konto = (
    <div className="card-ap p-4">
      <div className="flex items-center gap-3">
        <Monogramm name={currentUser?.name ?? "?"} groesse={56} />
        <div className="min-w-0">
          <p className="truncate text-zeile font-semibold text-label">{currentUser?.name}</p>
          <p className="text-sekundaer text-label2">{rolle}</p>
        </div>
      </div>
      <GroupedList className="mt-4">
        <GroupedListRow>
          <SymbolKachel icon={Mail} farbe="blue" />
          <div className="min-w-0 flex-1">
            <p className="text-meta text-label2">E-Mail</p>
            <p className="truncate text-fliess text-label">{currentUser?.email}</p>
          </div>
        </GroupedListRow>
        <GroupedListRow last>
          <SymbolKachel icon={Building2} farbe="indigo" />
          <div className="min-w-0 flex-1">
            <p className="text-meta text-label2">Mandant</p>
            <p className="truncate text-fliess text-label">{currentUser?.mandant_name}</p>
          </div>
        </GroupedListRow>
      </GroupedList>
    </div>
  );

  const verknuepfungen = (dauerauftraege || zeiterfassung) && (
    <div>
      <AbschnittskopfB titel="Arbeit" />
      <div>
        <GroupedList>
          {dauerauftraege && (
            <GroupedListRow onClick={() => navigate("/dauerauftraege")} navigierbar last={!zeiterfassung}>
              <SymbolKachel icon={Repeat} farbe="orange" />
              <span className="text-zeile text-label">Dauer-Aufträge</span>
            </GroupedListRow>
          )}
          {zeiterfassung && (
            <GroupedListRow onClick={() => navigate("/statistik")} navigierbar last>
              <SymbolKachel icon={Timer} farbe="blue" />
              <span className="text-zeile text-label">
                {currentUser?.nur_zugewiesene_kunden ? "Meine Arbeitszeit" : "Arbeitszeit"}
              </span>
            </GroupedListRow>
          )}
        </GroupedList>
      </div>
    </div>
  );

  const darstellung = (
    <div>
      <AbschnittskopfB titel="Darstellung" />
      <AppearancePicker />
    </div>
  );

  // Bei Impersonation gehoert das Profil dem Super-Admin, nicht dem Mandanten-Nutzer.
  const sicherheit = !isImpersonating && (
    <>
      <PasswortAendernKarte />
      <MfaKarte />
    </>
  );

  const abmelden = (
    <div className="space-y-2">
      <button
        onClick={ueberallAbmelden}
        disabled={abmeldenLaeuft}
        className="btn-touch btn-ap flex w-full items-center justify-center gap-2 disabled:opacity-50"
      >
        <MonitorSmartphone size={16} strokeWidth={1.5} /> Auf allen Geräten abmelden
      </button>
      {abmeldenFehler && <p className="text-fliess text-st-fehlt">{abmeldenFehler}</p>}
      <button onClick={logout} className="btn-touch btn-ap flex w-full items-center justify-center gap-2">
        <LogOut size={16} strokeWidth={1.5} /> Abmelden
      </button>
    </div>
  );

  if (office) {
    // auto-fit statt fester Spaltenzahl: ausgeblendete Blöcke (ohne Modul/Recht)
    // lassen keine Lücke, die übrigen teilen sich die Breite.
    const raster = "grid items-start gap-4 grid-cols-[repeat(auto-fit,minmax(min(100%,320px),1fr))]";
    return (
      <div className="max-w-[1400px] space-y-4">
        <SeitenKopf titel="Profil" />
        <div className="card-ap flex flex-wrap items-center gap-x-6 gap-y-4 px-5 py-4">
          <div className="flex min-w-0 items-center gap-4">
            <Monogramm name={currentUser?.name ?? "?"} groesse={64} />
            <div className="min-w-0">
              <p className="truncate text-titel-mobil font-semibold text-label">{currentUser?.name}</p>
              <p className="text-sekundaer text-label2">{rolle}</p>
            </div>
          </div>
          <div className="flex min-w-0 flex-wrap gap-x-7 gap-y-3 lg:border-l lg:border-sep lg:pl-6">
            <div className="flex min-w-0 items-center gap-3">
              <SymbolKachel icon={Mail} farbe="blue" />
              <div className="min-w-0">
                <p className="text-meta text-label2">E-Mail</p>
                <p className="truncate text-fliess text-label">{currentUser?.email}</p>
              </div>
            </div>
            <div className="flex min-w-0 items-center gap-3">
              <SymbolKachel icon={Building2} farbe="indigo" />
              <div className="min-w-0">
                <p className="text-meta text-label2">Mandant</p>
                <p className="truncate text-fliess text-label">{currentUser?.mandant_name}</p>
              </div>
            </div>
          </div>
          <div className="ml-auto flex flex-wrap gap-2">
            <button onClick={ueberallAbmelden} disabled={abmeldenLaeuft} className="btn-ap flex items-center gap-2 px-4 py-2 disabled:opacity-50">
              <MonitorSmartphone size={16} strokeWidth={1.5} /> Auf allen Geräten abmelden
            </button>
            <button onClick={logout} className="btn-ap flex items-center gap-2 px-4 py-2">
              <LogOut size={16} strokeWidth={1.5} /> Abmelden
            </button>
          </div>
          {abmeldenFehler && <p className="w-full text-fliess text-st-fehlt">{abmeldenFehler}</p>}
        </div>

        <section aria-label="Überblick">
          <AbschnittskopfB titel="Überblick" />
          <div className={raster + " items-stretch"}>
            <ProfilArbeitszeitKarte />
            <ProfilUrlaubKarte mitLink={zeiterfassung} />
            <ProfilVorgaengeKarte listeLink="/vorgaenge" kurzliste />
          </div>
        </section>

        <div className={raster}>
          {verknuepfungen}
          {darstellung}
          {!isImpersonating && (
            <div>
              <AbschnittskopfB titel="Sicherheit" />
              <GroupedList>
                <PasswortAendernKarte variante="zeile" />
                <MfaKarte variante="zeile" last />
              </GroupedList>
            </div>
          )}
        </div>

        {kiAktiv && <KiVerbindungenKarte variante="zeilen" />}
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {konto}
      <ProfilArbeitszeitKarte />
      <ProfilVorgaengeKarte listeLink="/feed" />
      <ProfilUrlaubKarte mitLink={false} />
      {verknuepfungen}
      {darstellung}
      {sicherheit}
      {kiVerbindungen}
      {abmelden}
    </div>
  );
}
