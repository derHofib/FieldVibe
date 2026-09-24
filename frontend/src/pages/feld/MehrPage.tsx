import { LogOut, Search, Settings, User } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { AbschnittskopfA, AbschnittskopfB } from "../../components/apple/AbschnittsKopf";
import { GroupedList, GroupedListRow } from "../../components/apple/GroupedList";
import { Monogramm } from "../../components/apple/Monogramm";
import { AppearancePicker } from "../../components/AppearancePicker";
import { NAV_KATEGORIE_REIHENFOLGE, sichtbareNavSeiten } from "../../config/navSeiten";
import { useAuth } from "../../context/AuthContext";

/** "Mehr"-Tab (Abschnitt 5.3, vierter Tab): ersetzt die vorherige
 * individualisierbare Bottom-Nav-Rotunde -- bei genau 4 festen Tabs gibt es
 * keinen wischbaren Zusatzbereich mehr, "Mehr" listet stattdessen
 * ausnahmslos alles, was vorher darueber erreichbar war (siehe
 * docs/ui-redesign/REVIEW.md "Bewusste Abweichungen"). Gruppiert nach
 * denselben Kategorien wie die Office-Seitenleiste. */
export function MehrPage() {
  const navigate = useNavigate();
  const { currentUser, hatRecht, logout } = useAuth();
  // Gleiches Rechte-Gate wie zuvor am Zahnrad-Symbol im (jetzt entfernten)
  // Header: die Verwaltungsseite (/einstellungen: Nutzer, Account-Typen,
  // Firmendaten ...) ist kein Darstellungs-Setting, sondern echte
  // Mandanten-Verwaltung -- nur fuer die Rollen sichtbar, die sie vorher
  // auch sahen.
  const kannVerwaltungSehen = currentUser?.role === "mandant_admin" || currentUser?.role === "loesch_operativ";

  const sichtbar = sichtbareNavSeiten(currentUser, hatRecht).filter(
    (seite) => !seite.nurOffice && seite.key !== "feed",
  );
  const gruppen = NAV_KATEGORIE_REIHENFOLGE.map((kategorie) => ({
    name: kategorie,
    seiten: sichtbar.filter((s) => s.kategorie === kategorie),
  })).filter((g) => g.seiten.length > 0);

  return (
    // -mx-3 -mt-4 hebt das Aussenpolster von FeldLayout.tsx auf (px-3 py-4
    // um <Outlet/>) -- diese Seite ist wie alle Apple-Bausteine (Abschnitt
    // 4.2) randstaendig gebaut, mit eigenem Innenpolster in AbschnittskopfA/
    // GroupedList. Wird obsolet, sobald FeldLayout selbst randstaendig wird.
    <div className="-mx-3 -mt-4 pb-8">
      <AbschnittskopfA titel="Mehr" />

      <div className="px-4">
        <GroupedList>
          <GroupedListRow onClick={() => navigate("/profil")} navigierbar last>
            <Monogramm name={currentUser?.name ?? "?"} groesse={36} />
            <div className="min-w-0">
              <p className="truncate text-[17px] font-semibold text-label">{currentUser?.name}</p>
              <p className="truncate text-[13px] text-label2">{currentUser?.email}</p>
            </div>
          </GroupedListRow>
        </GroupedList>
      </div>

      {gruppen.map((gruppe) => (
        <div key={gruppe.name}>
          <AbschnittskopfB titel={gruppe.name} />
          <div className="px-4">
            <GroupedList>
              {gruppe.seiten.map((seite, i) => (
                <GroupedListRow
                  key={seite.key}
                  onClick={() => navigate(seite.route)}
                  navigierbar
                  last={i === gruppe.seiten.length - 1}
                >
                  <seite.icon size={20} strokeWidth={2} className="shrink-0 text-tint" />
                  <span className="flex-1 text-[17px] text-label">{seite.label}</span>
                </GroupedListRow>
              ))}
            </GroupedList>
          </div>
        </div>
      ))}

      <AbschnittskopfB titel="Darstellung" />
      <div className="px-4">
        <AppearancePicker />
      </div>

      <AbschnittskopfB titel="App" />
      <div className="px-4">
        <GroupedList>
          <GroupedListRow onClick={() => navigate("/suche")} navigierbar>
            <Search size={20} strokeWidth={2} className="shrink-0 text-tint" />
            <span className="flex-1 text-[17px] text-label">Suche</span>
          </GroupedListRow>
          <GroupedListRow onClick={() => navigate("/profil")} navigierbar>
            <User size={20} strokeWidth={2} className="shrink-0 text-tint" />
            <span className="flex-1 text-[17px] text-label">Profil</span>
          </GroupedListRow>
          {kannVerwaltungSehen && (
            <GroupedListRow onClick={() => navigate("/einstellungen")} navigierbar>
              <Settings size={20} strokeWidth={2} className="shrink-0 text-tint" />
              <span className="flex-1 text-[17px] text-label">Verwaltung</span>
            </GroupedListRow>
          )}
          <GroupedListRow onClick={logout} last>
            <LogOut size={20} strokeWidth={2} className="shrink-0 text-st-fehlt" />
            <span className="flex-1 text-[17px] text-st-fehlt">Abmelden</span>
          </GroupedListRow>
        </GroupedList>
      </div>
    </div>
  );
}
