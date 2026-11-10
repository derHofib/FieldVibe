import { LogOut } from "lucide-react";

import { useAuth } from "../context/AuthContext";
import { Logo } from "./brand/Logo";
import { Hinweiskasten } from "./Hinweiskasten";
import { MfaEinrichtenFormular } from "./MfaEinrichtenFormular";

/** Ersetzt die gesamte App, solange der Betrieb MFA vorschreibt und der
 * Account sie noch nicht eingerichtet hat (das Token erlaubt serverseitig
 * ohnehin nur diesen Weg). */
export function MfaErzwingenSeite() {
  const { logout } = useAuth();
  return (
    <div className="flex min-h-screen items-center justify-center bg-gbg p-4">
      <div className="w-full max-w-sm space-y-4">
        <div className="flex justify-center">
          <Logo variante="wortmarke" hoehe={32} />
        </div>
        <div className="card-ap space-y-4 p-5">
          <h1 className="text-[17px] font-semibold text-label">Zwei-Faktor-Anmeldung einrichten</h1>
          <Hinweiskasten ton="info">
            Dein Betrieb schreibt die Zwei-Faktor-Anmeldung vor. Richte sie jetzt ein, um fortzufahren.
          </Hinweiskasten>
          <MfaEinrichtenFormular />
        </div>
        <button type="button" onClick={logout} className="btn-touch btn-ap flex w-full items-center justify-center gap-2">
          <LogOut size={16} aria-hidden="true" /> Abmelden
        </button>
      </div>
    </div>
  );
}
