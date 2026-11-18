import { useState, type FormEvent } from "react";
import { KeyRound } from "lucide-react";

import { ApiError } from "../../api/client";
import { authApi } from "../../api/endpoints";
import { GroupedListRow } from "../../components/apple/GroupedList";
import { SymbolKachel } from "../../components/apple/SymbolKachel";
import { IconBadge } from "../../components/IconBadge";
import { useAuth } from "../../context/AuthContext";
import { MIN_PASSWORT_LAENGE } from "../../utils/passwort";

/** Passwort ändern im Profil (Feld-App und Office teilen sich die Seite).
 * `variante="zeile"` (Office): Listenzeile für eine gemeinsame GroupedList
 * "Sicherheit", das Formular klappt darunter auf. */
export function PasswortAendernKarte({ variante = "karte", last = false }: { variante?: "karte" | "zeile"; last?: boolean }) {
  const zeile = variante === "zeile";
  const { loginMitToken } = useAuth();
  const [offen, setOffen] = useState(false);
  const [altesPasswort, setAltesPasswort] = useState("");
  const [neuesPasswort, setNeuesPasswort] = useState("");
  const [wiederholung, setWiederholung] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [erfolg, setErfolg] = useState(false);
  const [laeuft, setLaeuft] = useState(false);

  function zuruecksetzen() {
    setAltesPasswort("");
    setNeuesPasswort("");
    setWiederholung("");
    setFehler(null);
  }

  async function absenden(e: FormEvent) {
    e.preventDefault();
    setFehler(null);
    setErfolg(false);
    if (neuesPasswort !== wiederholung) {
      setFehler("Die neuen Passwörter stimmen nicht überein.");
      return;
    }
    setLaeuft(true);
    try {
      // Der Server widerruft alle bisherigen Tokens (andere Geräte sind damit
      // abgemeldet) und liefert für diese Sitzung ein frisches Paar.
      const tokens = await authApi.passwortAendern(altesPasswort, neuesPasswort);
      await loginMitToken(tokens);
      zuruecksetzen();
      setOffen(false);
      setErfolg(true);
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : "Passwort ändern fehlgeschlagen");
    } finally {
      setLaeuft(false);
    }
  }

  const umschalten = () => {
    setOffen((o) => !o);
    setErfolg(false);
    zuruecksetzen();
  };

  return (
    <div className={zeile ? undefined : "card-ap"}>
      {zeile ? (
        <GroupedListRow onClick={umschalten} navigierbar last={last && !offen && !erfolg}>
          <SymbolKachel icon={KeyRound} farbe="indigo" />
          <span className="text-zeile text-label">Passwort ändern</span>
        </GroupedListRow>
      ) : (
        <button
          type="button"
          onClick={umschalten}
          aria-expanded={offen}
          className="btn-touch flex w-full items-center gap-3 p-4 text-left"
        >
          <IconBadge icon={KeyRound} tone="violet" size="sm" />
          <span className="font-medium text-label">Passwort ändern</span>
        </button>
      )}

      {erfolg && !offen && (
        <p className="mx-4 mb-4 border rounded-[var(--radius-ap-md)] border-st-erledigt px-3 py-2 text-fliess text-st-erledigt">
          Passwort geändert. Auf allen anderen Geräten wurdest du abgemeldet.
        </p>
      )}

      {offen && (
        <form onSubmit={absenden} className="px-4 pb-4">
          {fehler && (
            <div role="alert" className="mb-4 border rounded-[var(--radius-ap-md)] border-st-fehlt px-3 py-2 text-fliess text-st-fehlt">
              {fehler}
            </div>
          )}

          <label htmlFor="pw-alt" className="mb-1 block text-fliess font-medium text-label">
            Aktuelles Passwort
          </label>
          <input
            id="pw-alt"
            type="password"
            required
            autoComplete="current-password"
            value={altesPasswort}
            onChange={(e) => setAltesPasswort(e.target.value)}
            className="field-ap btn-touch mb-4"
          />

          <label htmlFor="pw-neu" className="mb-1 block text-fliess font-medium text-label">
            Neues Passwort
          </label>
          <input
            id="pw-neu"
            type="password"
            required
            minLength={MIN_PASSWORT_LAENGE}
            autoComplete="new-password"
            value={neuesPasswort}
            onChange={(e) => setNeuesPasswort(e.target.value)}
            className="field-ap btn-touch mb-1"
          />
          <p className="mb-4 text-sekundaer text-label2">Mindestens {MIN_PASSWORT_LAENGE} Zeichen.</p>

          <label htmlFor="pw-wiederholung" className="mb-1 block text-fliess font-medium text-label">
            Neues Passwort wiederholen
          </label>
          <input
            id="pw-wiederholung"
            type="password"
            required
            minLength={MIN_PASSWORT_LAENGE}
            autoComplete="new-password"
            value={wiederholung}
            onChange={(e) => setWiederholung(e.target.value)}
            className="field-ap btn-touch mb-4"
          />

          <button
            type="submit"
            disabled={laeuft}
            className="btn-touch btn-ap-primary w-full py-2 disabled:opacity-50"
          >
            {laeuft ? "Speichern…" : "Passwort speichern"}
          </button>
        </form>
      )}
    </div>
  );
}
