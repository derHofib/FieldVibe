import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";

import { ApiError } from "../../api/client";
import { mfaApi } from "../../api/endpoints";
import { IconBadge } from "../../components/IconBadge";
import { MfaEinrichtenFormular } from "../../components/MfaEinrichtenFormular";
import { useAuth } from "../../context/AuthContext";

type Aktion = "deaktivieren" | "codes" | null;

/** Zwei-Faktor-Anmeldung im Profil (Feld-App und Office teilen sich die Seite). */
export function MfaKarte() {
  const { loginMitToken, zeigeMfaCodes } = useAuth();
  const queryClient = useQueryClient();
  const [offen, setOffen] = useState(false);
  const [aktion, setAktion] = useState<Aktion>(null);
  const [passwort, setPasswort] = useState("");
  const [code, setCode] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const status = useQuery({ queryKey: ["mfa-status"], queryFn: mfaApi.status });

  const ausfuehren = useMutation({
    mutationFn: async () => {
      if (aktion === "deaktivieren") {
        // Widerruft alle Tokens; die aufrufende Sitzung bekommt ein frisches Paar.
        await loginMitToken(await mfaApi.deaktivieren(passwort, code));
      } else {
        zeigeMfaCodes((await mfaApi.neueCodes(passwort, code)).wiederherstellungscodes);
      }
    },
    onSuccess: () => {
      setAktion(null);
      setPasswort("");
      setCode("");
      setFehler(null);
      void queryClient.invalidateQueries({ queryKey: ["mfa-status"] });
    },
    onError: (err) => setFehler(err instanceof ApiError ? err.message : "Aktion fehlgeschlagen"),
  });

  function absenden(e: FormEvent) {
    e.preventDefault();
    setFehler(null);
    ausfuehren.mutate();
  }

  const s = status.data;
  return (
    <div className="card-ap">
      <button
        type="button"
        onClick={() => setOffen((o) => !o)}
        aria-expanded={offen}
        className="btn-touch flex w-full items-center gap-3 p-4 text-left"
      >
        <IconBadge icon={ShieldCheck} tone="emerald" size="sm" />
        <span className="flex-1 font-medium text-label">Zwei-Faktor-Anmeldung</span>
        {s && <span className="text-sm text-label2">{s.aktiv ? "Aktiv" : "Aus"}</span>}
      </button>

      {offen && s && (
        <div className="space-y-3 px-4 pb-4">
          {!s.aktiv && (
            <MfaEinrichtenFormular
              onFertig={() => {
                void queryClient.invalidateQueries({ queryKey: ["mfa-status"] });
                setOffen(false);
              }}
            />
          )}

          {s.aktiv && (
            <>
              <p className="text-sm text-label2">
                Beim Anmelden wird zusätzlich ein Code aus deiner Authenticator-App verlangt. Noch{" "}
                {s.wiederherstellungscodes_uebrig} von 10 Wiederherstellungscodes übrig.
              </p>
              {!aktion && (
                <div className="flex flex-col gap-2">
                  <button type="button" onClick={() => setAktion("codes")} className="btn-touch btn-ap w-full">
                    Neue Wiederherstellungscodes erzeugen
                  </button>
                  {s.pflicht ? (
                    <p className="text-xs text-label2">Dein Betrieb schreibt MFA vor – sie kann nicht deaktiviert werden.</p>
                  ) : (
                    <button type="button" onClick={() => setAktion("deaktivieren")} className="btn-touch btn-ap w-full">
                      MFA deaktivieren
                    </button>
                  )}
                </div>
              )}
              {aktion && (
                <form onSubmit={absenden} className="space-y-3">
                  {fehler && (
                    <div role="alert" className="border border-st-fehlt px-3 py-2 text-sm text-st-fehlt">
                      {fehler}
                    </div>
                  )}
                  <label htmlFor="mfa-pw" className="block text-sm font-medium text-label">
                    Passwort
                  </label>
                  <input
                    id="mfa-pw"
                    type="password"
                    required
                    autoComplete="current-password"
                    value={passwort}
                    onChange={(e) => setPasswort(e.target.value)}
                    className="field-ap btn-touch"
                  />
                  <label htmlFor="mfa-aktion-code" className="block text-sm font-medium text-label">
                    Code oder Wiederherstellungscode
                  </label>
                  <input
                    id="mfa-aktion-code"
                    required
                    autoComplete="one-time-code"
                    value={code}
                    onChange={(e) => setCode(e.target.value)}
                    className="field-ap btn-touch"
                  />
                  <div className="flex gap-2">
                    <button
                      type="button"
                      onClick={() => {
                        setAktion(null);
                        setFehler(null);
                      }}
                      className="btn-touch btn-ap flex-1"
                    >
                      Abbrechen
                    </button>
                    <button type="submit" disabled={ausfuehren.isPending} className="btn-touch btn-ap-primary flex-1 disabled:opacity-50">
                      {aktion === "deaktivieren" ? "Deaktivieren" : "Neue Codes erzeugen"}
                    </button>
                  </div>
                </form>
              )}
            </>
          )}
        </div>
      )}
    </div>
  );
}
