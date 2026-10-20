import { useMutation } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { ApiError } from "../api/client";
import { mfaApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";

/** Einrichtung von TOTP-MFA: Start, QR-Code (lokal erzeugt, kein externer
 * Dienst), Bestätigung mit Code. Nach Erfolg zeigt der AuthProvider die
 * Wiederherstellungscodes (zeigeMfaCodes) -- die Tokens sind dann schon
 * erneuert, weil der Server alle bisherigen widerruft. */
export function MfaEinrichtenFormular({ onFertig }: { onFertig?: () => void }) {
  const { loginMitToken, zeigeMfaCodes } = useAuth();
  const [code, setCode] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const start = useMutation({ mutationFn: mfaApi.einrichten });

  async function bestaetigen(e: FormEvent) {
    e.preventDefault();
    setFehler(null);
    try {
      const antwort = await mfaApi.bestaetigen(code);
      zeigeMfaCodes(antwort.wiederherstellungscodes);
      await loginMitToken(antwort);
      onFertig?.();
    } catch (err) {
      setFehler(err instanceof ApiError ? err.message : "Bestätigung fehlgeschlagen");
    }
  }

  if (!start.data) {
    return (
      <div className="space-y-3">
        <p className="text-sm text-label2">
          Du brauchst eine Authenticator-App (z. B. Google Authenticator, Microsoft Authenticator, 2FAS oder
          Aegis).
        </p>
        {start.isError && (
          <p role="alert" className="text-sm text-st-fehlt">
            {start.error instanceof ApiError ? start.error.message : "Einrichtung konnte nicht gestartet werden"}
          </p>
        )}
        <button
          type="button"
          onClick={() => start.mutate()}
          disabled={start.isPending}
          className="btn-touch btn-ap-primary w-full py-2 disabled:opacity-50"
        >
          {start.isPending ? "Wird vorbereitet…" : "Einrichtung starten"}
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={bestaetigen} className="space-y-3">
      <p className="text-sm text-label2">
        1. QR-Code mit der Authenticator-App scannen (oder den Schlüssel von Hand eintragen).
      </p>
      <div className="flex justify-center">
        <img
          src={start.data.qr_svg_data_uri}
          alt="QR-Code zum Einrichten der Authenticator-App"
          width={200}
          height={200}
          className="rounded-[var(--radius-ap-input)]"
        />
      </div>
      <p className="text-center text-xs text-label2">
        Schlüssel:{" "}
        <span className="font-mono text-label select-all" data-testid="mfa-secret">
          {start.data.secret}
        </span>
      </p>
      <p className="text-sm text-label2">2. Den 6-stelligen Code aus der App eingeben.</p>
      {fehler && (
        <div role="alert" className="border border-st-fehlt px-3 py-2 text-sm text-st-fehlt">
          {fehler}
        </div>
      )}
      <label htmlFor="mfa-bestaetigen-code" className="block text-sm font-medium text-label">
        Code
      </label>
      <input
        id="mfa-bestaetigen-code"
        required
        inputMode="numeric"
        autoComplete="one-time-code"
        maxLength={7}
        value={code}
        onChange={(e) => setCode(e.target.value)}
        className="field-ap btn-touch tracking-widest"
      />
      <button type="submit" className="btn-touch btn-ap-primary w-full py-2">
        MFA aktivieren
      </button>
    </form>
  );
}
