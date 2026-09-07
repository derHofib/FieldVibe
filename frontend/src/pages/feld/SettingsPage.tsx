import {
  ClipboardList,
  Clock,
  LayoutGrid,
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
import { istModulAktiv } from "../../utils/module";

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
      className="card-interactive btn-touch flex w-full items-center gap-3 border border-ind-line bg-ind-bg p-4 text-left"
    >
      <IconBadge icon={icon} tone={tone} />
      <span className="min-w-0 flex-1">
        <span className="block font-medium text-ind-ink">{label}</span>
        <span className="block text-xs text-ind-ink-3">{beschreibung}</span>
      </span>
      <span className="text-ind-ink-3">›</span>
    </button>
  );
}

export function SettingsPage() {
  const navigate = useNavigate();
  const { currentUser, hatRecht } = useAuth();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold text-ind-ink">Einstellungen</h1>
        <p className="mt-1 text-sm text-ind-ink-3">
          Verwaltung für {currentUser?.mandant_name ?? "diesen Mandanten"}.
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-ind-ink-3">
          Team
        </h2>
        <SettingsLink
          icon={Users}
          tone="amber"
          label="Nutzer verwalten"
          beschreibung="Accounts anlegen, Account-Typ zuweisen, deaktivieren"
          onClick={() => navigate("/accounts")}
        />
        <SettingsLink
          icon={UserCog}
          tone="violet"
          label="Account-Typen & Rechte"
          beschreibung="Eigene Account-Typen definieren und ihre Rechte-Matrix einstellen"
          onClick={() => navigate("/account-typen")}
        />
        <SettingsLink
          icon={Wrench}
          tone="emerald"
          label="Techniker-Zuweisungen"
          beschreibung="Welcher Account sieht welche Kunden"
          onClick={() => navigate("/techniker-zuweisungen")}
        />
        {hatRecht("mitarbeiterverwaltung", "bearbeiten") && (
          <SettingsLink
            icon={Clock}
            tone="cyan"
            label="Team-Zeiten"
            beschreibung="Arbeitszeiten je Mitarbeiter einsehen und als PDF exportieren"
            onClick={() => navigate("/team-zeiten")}
          />
        )}
      </section>

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-ind-ink-3">
          Betrieb
        </h2>
        <SettingsLink
          icon={Tags}
          tone="rose"
          label="Anlagen-Zusatzfelder"
          beschreibung="Eigene Felder je Anlagentyp definieren"
          onClick={() => navigate("/anlagen-felder")}
        />
        {hatRecht("formulare", "sehen") && (
          <SettingsLink
            icon={ClipboardList}
            tone="violet"
            label="Formulare"
            beschreibung="Checklisten & Protokolle für Auftragstypen erstellen"
            onClick={() => navigate("/formulare")}
          />
        )}
        {istModulAktiv(currentUser, "statistik") && (
          <SettingsLink
            icon={TrendingUp}
            tone="sky"
            label="Kennzahlen"
            beschreibung="Auslastung, Kennzahlen, Auswertungen"
            onClick={() => navigate("/insights")}
          />
        )}
      </section>

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-ind-ink-3">
          Darstellung
        </h2>
        <SettingsLink
          icon={LayoutGrid}
          tone="cyan"
          label="Menüleiste anpassen"
          beschreibung="Welche Seiten unten in der Navigation sichtbar sind"
          onClick={() => navigate("/einstellungen/menueleiste")}
        />
      </section>

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-ind-ink-3">
          Unternehmen
        </h2>
        <SettingsLink
          icon={Plug}
          tone="indigo"
          label="Firmendaten & Integrationen"
          beschreibung="Firmenlogo/-daten für Angebote, E-Mail-Versand, angebundene Dienste"
          onClick={() => navigate("/integrationen")}
        />
      </section>
    </div>
  );
}
