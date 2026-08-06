import { BarChart3, type LucideIcon, Plug, Tags, UserCog, Users, Wrench } from "lucide-react";
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
      className="card-interactive btn-touch flex w-full items-center gap-3 rounded-lg bg-white p-4 text-left shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800"
    >
      <IconBadge icon={icon} tone={tone} />
      <span className="min-w-0 flex-1">
        <span className="block font-medium text-slate-800 dark:text-slate-100">{label}</span>
        <span className="block text-xs text-slate-500 dark:text-slate-400">{beschreibung}</span>
      </span>
      <span className="text-slate-300 dark:text-slate-600">›</span>
    </button>
  );
}

export function SettingsPage() {
  const navigate = useNavigate();
  const { currentUser } = useAuth();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">Einstellungen</h1>
        <p className="mt-1 text-sm text-slate-500 dark:text-slate-400">
          Verwaltung für {currentUser?.mandant_name ?? "diesen Mandanten"}.
        </p>
      </div>

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
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
      </section>

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
          Betrieb
        </h2>
        <SettingsLink
          icon={Tags}
          tone="rose"
          label="Anlagen-Zusatzfelder"
          beschreibung="Eigene Felder je Anlagentyp definieren"
          onClick={() => navigate("/anlagen-felder")}
        />
        {istModulAktiv(currentUser, "statistik") && (
          <SettingsLink
            icon={BarChart3}
            tone="sky"
            label="Insights"
            beschreibung="Auslastung, Kennzahlen, Auswertungen"
            onClick={() => navigate("/insights")}
          />
        )}
      </section>

      <section className="space-y-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
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
