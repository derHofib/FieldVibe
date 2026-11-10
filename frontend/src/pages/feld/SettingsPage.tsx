import {
  Archive,
  CalendarClock,
  ClipboardList,
  Clock,
  type LucideIcon,
  Plug,
  Tags,
  TrendingUp,
  UserCog,
  Users,
  Wrench,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { IconBadge, type IconTone } from "../../components/IconBadge";
import { useAuth } from "../../context/AuthContext";
import { istOfficeHost } from "../../office/hostname";
import { istModulAktiv } from "../../utils/module";
import { darfRechteVerwalten, istAdminRolle } from "../../utils/rollen";

function SettingsLink({
  icon,
  tone,
  label,
  beschreibung,
  onClick,
}: {
  icon: LucideIcon;
  tone: IconTone;
  label: string;
  beschreibung: string;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="card-interactive btn-touch flex w-full items-center gap-3 card-ap p-4 text-left"
    >
      <IconBadge icon={icon} tone={tone} />
      <span className="min-w-0 flex-1">
        <span className="block font-medium text-label">{label}</span>
        <span className="block text-xs text-label2">{beschreibung}</span>
      </span>
      <span className="text-label2">›</span>
    </button>
  );
}

export function SettingsPage() {
  const navigate = useNavigate();
  const { currentUser, hatRecht } = useAuth();
  const zeigeKennzahlen = istAdminRolle(currentUser) && istModulAktiv(currentUser, "statistik");
  const zeigeBetrieb = hatRecht("kunden", "sehen") || hatRecht("formulare", "sehen") || zeigeKennzahlen;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold text-label">Einstellungen</h1>
        <p className="mt-1 text-sm text-label2">
          Verwaltung für {currentUser?.mandant_name ?? "diesen Mandanten"}.
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-label2">
          Team
        </h2>
        {/* Custom-Rollen duerfen die Seite oeffnen, das Backend sperrt aber /api/users und
            die Integrationen fuer sie -- diese Links nur fuer Admin-Rollen. */}
        {istAdminRolle(currentUser) && (
          <SettingsLink
            icon={Users}
            tone="amber"
            label="Nutzer verwalten"
            beschreibung="Accounts anlegen, Account-Typ zuweisen, deaktivieren"
            onClick={() => navigate("/accounts")}
          />
        )}
        {darfRechteVerwalten(currentUser, hatRecht) && (
          <SettingsLink
            icon={UserCog}
            tone="violet"
            label="Account-Typen & Rechte"
            beschreibung="Eigene Account-Typen definieren und ihre Rechte-Matrix einstellen"
            onClick={() => navigate("/account-typen")}
          />
        )}
        {hatRecht("dispo", "bearbeiten") && hatRecht("kunden", "bearbeiten") && (
          <SettingsLink
            icon={Wrench}
            tone="emerald"
            label="Techniker-Zuweisungen"
            beschreibung="Welcher Account sieht welche Kunden"
            onClick={() => navigate("/techniker-zuweisungen")}
          />
        )}
        {hatRecht("mitarbeiterverwaltung", "bearbeiten") && istModulAktiv(currentUser, "zeiterfassung") && (
          <SettingsLink
            icon={Clock}
            tone="cyan"
            label="Team-Zeiten"
            beschreibung="Arbeitszeiten je Mitarbeiter einsehen und als PDF exportieren"
            onClick={() => navigate("/team-zeiten")}
          />
        )}
        {currentUser?.darf_abwesenheiten_verwalten && istModulAktiv(currentUser, "zeiterfassung") && (
          <SettingsLink
            icon={CalendarClock}
            tone="cyan"
            label="Arbeitszeit"
            beschreibung="Soll-Zeit je Mitarbeiter, Feiertage und Bundesland"
            onClick={() => navigate("/einstellungen/arbeitszeit")}
          />
        )}
      </section>

      {zeigeBetrieb && (
        <section className="space-y-2">
          <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-label2">
            Betrieb
          </h2>
          {hatRecht("kunden", "sehen") && (
            <SettingsLink
              icon={Tags}
              tone="rose"
              label="Anlagen-Zusatzfelder"
              beschreibung="Eigene Felder je Anlagentyp definieren"
              onClick={() => navigate("/anlagen-felder")}
            />
          )}
          {hatRecht("formulare", "sehen") && (
            <SettingsLink
              icon={ClipboardList}
              tone="violet"
              label="Formulare"
              beschreibung="Checklisten & Protokolle für Leistungstypen erstellen"
              onClick={() => navigate("/form-schemas")}
            />
          )}
          {zeigeKennzahlen && (
            <SettingsLink
              icon={TrendingUp}
              tone="sky"
              label="Kennzahlen"
              beschreibung="Auslastung, Kennzahlen, Auswertungen"
              onClick={() => navigate("/insights")}
            />
          )}
        </section>
      )}

      {istAdminRolle(currentUser) && (
        <section className="space-y-2">
          <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-label2">
            Unternehmen
          </h2>
          {istAdminRolle(currentUser) && (
            <SettingsLink
              icon={Plug}
              tone="indigo"
              label="Firmendaten & Integrationen"
              beschreibung="Firmenlogo/-daten für Angebote, E-Mail-Versand, angebundene Dienste"
              onClick={() => navigate("/integrationen")}
            />
          )}
          {/* Breite Tabelle, nur am Desktop (office.) und nur fuer mandant_admin (Backend: dasselbe). */}
          {istOfficeHost() && currentUser?.role === "mandant_admin" && (
            <SettingsLink
              icon={Archive}
              tone="teal"
              label="Daten exportieren"
              beschreibung="Vollexport als ZIP und Z3-Export für die Finanzverwaltung"
              onClick={() => navigate("/einstellungen/export")}
            />
          )}
        </section>
      )}
    </div>
  );
}
