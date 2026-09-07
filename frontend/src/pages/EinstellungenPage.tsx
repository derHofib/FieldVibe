import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { plattformIntegrationenApi } from "../api/endpoints";
import type { PlattformIntegration } from "../types";

function SmtpZeile({ integration }: { integration: PlattformIntegration }) {
  const queryClient = useQueryClient();
  const [host, setHost] = useState(String(integration.config.host ?? ""));
  const [port, setPort] = useState(String(integration.config.port ?? "587"));
  const [user, setUser] = useState(String(integration.config.user ?? ""));
  const [fromAddress, setFromAddress] = useState(String(integration.config.from_address ?? ""));
  const [secret, setSecret] = useState("");

  const updateMutation = useMutation({
    mutationFn: (body: { config?: Record<string, unknown>; secret?: string | null; aktiv?: boolean }) =>
      plattformIntegrationenApi.update(integration.id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["plattform-integrationen"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => plattformIntegrationenApi.delete(integration.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["plattform-integrationen"] }),
  });

  return (
    <div className="space-y-2 border border-ind-line bg-ind-bg p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-ind-ink-2">SMTP (globaler Mailversand)</span>
        <span
          className={`border px-2 py-0.5 text-xs font-semibold ${
            integration.aktiv
              ? "border-green-400 text-green-700 dark:border-green-600 dark:text-green-300"
              : "border-ind-line text-ind-ink-3"
          }`}
        >
          {integration.aktiv ? "Aktiv" : "Inaktiv"}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <input
          value={host}
          onChange={(e) => setHost(e.target.value)}
          placeholder="Host"
          className="input-industry"
        />
        <input
          value={port}
          onChange={(e) => setPort(e.target.value)}
          placeholder="Port"
          className="input-industry"
        />
        <input
          value={user}
          onChange={(e) => setUser(e.target.value)}
          placeholder="Benutzername"
          className="input-industry"
        />
        <input
          value={fromAddress}
          onChange={(e) => setFromAddress(e.target.value)}
          placeholder="Absender-Adresse (z.B. account@fieldvibe.de)"
          className="input-industry"
        />
      </div>
      <input
        type="password"
        value={secret}
        onChange={(e) => setSecret(e.target.value)}
        placeholder={integration.hat_secret ? "Passwort (gesetzt, zum Ändern eingeben)" : "Passwort"}
        className="input-industry"
      />

      <div className="flex gap-2">
        <button
          onClick={() =>
            updateMutation.mutate({
              config: { host, port: Number(port) || port, user, from_address: fromAddress },
              ...(secret ? { secret } : {}),
            })
          }
          disabled={updateMutation.isPending}
          className="btn-touch btn-industry btn-industry-primary flex-1 py-1.5 text-sm disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => updateMutation.mutate({ aktiv: !integration.aktiv })}
          disabled={updateMutation.isPending}
          className="btn-touch btn-industry btn-industry-secondary py-1.5 text-sm disabled:opacity-50"
        >
          {integration.aktiv ? "Deaktivieren" : "Aktivieren"}
        </button>
        <button
          onClick={() => {
            if (window.confirm("Globale SMTP-Konfiguration wirklich löschen?")) deleteMutation.mutate();
          }}
          disabled={deleteMutation.isPending}
          className="btn-touch border border-red-400 px-3 py-1.5 text-sm font-medium text-red-700 hover:bg-red-50 disabled:opacity-50 dark:border-red-600 dark:text-red-400 dark:hover:bg-red-950/30"
        >
          Löschen
        </button>
      </div>
    </div>
  );
}

export function EinstellungenPage() {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [host, setHost] = useState("");
  const [port, setPort] = useState("587");
  const [user, setUser] = useState("");
  const [fromAddress, setFromAddress] = useState("account@fieldvibe.de");
  const [secret, setSecret] = useState("");

  const { data: integrationen, isLoading } = useQuery({
    queryKey: ["plattform-integrationen"],
    queryFn: plattformIntegrationenApi.list,
  });

  const createMutation = useMutation({
    mutationFn: () =>
      plattformIntegrationenApi.create({
        typ: "smtp",
        config: { host, port: Number(port) || port, user, from_address: fromAddress },
        secret: secret || undefined,
      }),
    onSuccess: () => {
      setShowForm(false);
      setHost("");
      setPort("587");
      setUser("");
      setFromAddress("account@fieldvibe.de");
      setSecret("");
      queryClient.invalidateQueries({ queryKey: ["plattform-integrationen"] });
    },
  });

  if (isLoading) return <p className="text-center text-ind-ink-3">Lädt…</p>;

  const smtp = integrationen?.find((i) => i.typ === "smtp");

  return (
    <div className="space-y-4">
      <h1 className="font-heading text-2xl font-semibold text-ind-ink">Plattform-Einstellungen</h1>

      <div className="space-y-2">
        <p className="text-sm text-ind-ink-3">
          Greift, sobald ein Mandant selbst keine eigene SMTP-Integration eingerichtet hat (Seite
          „Integrationen" im jeweiligen Mandanten-Bereich) — für Einladungen und Passwort-Reset-Mails.
          Ein Mandant mit eigener SMTP-Konfiguration überschreibt das automatisch, hier muss nichts
          umgeschaltet werden.
        </p>
        <p className="text-xs text-ind-ink-3">
          Absenderadresse braucht eine Domain, für die SPF/DKIM tatsächlich eingerichtet ist — sonst
          landen die Mails eher im Spam-Ordner der Empfänger.
        </p>
      </div>

      {smtp ? (
        <SmtpZeile integration={smtp} />
      ) : showForm ? (
        <div className="space-y-2 border border-ind-line bg-ind-bg p-4">
          <div className="grid grid-cols-2 gap-2">
            <input
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="Host"
              className="input-industry"
            />
            <input
              value={port}
              onChange={(e) => setPort(e.target.value)}
              placeholder="Port"
              className="input-industry"
            />
            <input
              value={user}
              onChange={(e) => setUser(e.target.value)}
              placeholder="Benutzername"
              className="input-industry"
            />
            <input
              value={fromAddress}
              onChange={(e) => setFromAddress(e.target.value)}
              placeholder="Absender-Adresse"
              className="input-industry"
            />
          </div>
          <input
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="Passwort"
            className="input-industry"
          />
          <button
            disabled={!host || !fromAddress || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            className="btn-touch btn-industry btn-industry-primary w-full py-1.5 text-sm disabled:opacity-50"
          >
            SMTP einrichten
          </button>
        </div>
      ) : (
        <button
          onClick={() => setShowForm(true)}
          className="btn-touch btn-industry btn-industry-secondary w-full py-2.5 text-sm"
        >
          + Globales SMTP einrichten
        </button>
      )}
    </div>
  );
}
