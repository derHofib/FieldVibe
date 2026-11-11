import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useId, useState, type ChangeEvent } from "react";

import { plattformIntegrationenApi } from "../api/endpoints";
import type { PlattformIntegration } from "../types";
import { AnlegenPanel } from "../components/AnlegenPanel";
import { FehlerZustand } from "../components/FehlerZustand";
import { useBestaetigung } from "../components/ConfirmDialog";
import { DetailSkeleton } from "../components/Skeleton";

interface SmtpWerte {
  host: string;
  port: string;
  user: string;
  fromAddress: string;
  secret: string;
}

/** Felder der globalen SMTP-Konfiguration; für Anlegen (Panel) und Bearbeiten gleich. */
function SmtpFelder({
  werte,
  onChange,
  hatSecret = false,
  hostFehler,
  absenderFehler,
}: {
  werte: SmtpWerte;
  onChange: (neu: SmtpWerte) => void;
  hatSecret?: boolean;
  hostFehler?: string;
  absenderFehler?: string;
}) {
  const uid = useId();
  const set = (k: keyof SmtpWerte) => (e: ChangeEvent<HTMLInputElement>) => onChange({ ...werte, [k]: e.target.value });
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label htmlFor={`${uid}-host`} className="mb-1 block text-sm font-medium text-label">
            Host <span aria-hidden="true" className="text-st-fehlt">*</span>
          </label>
          <input
            id={`${uid}-host`}
            value={werte.host}
            onChange={set("host")}
            aria-invalid={!!hostFehler}
            aria-describedby={hostFehler ? `${uid}-host-fehler` : undefined}
            className="field-ap"
          />
          {hostFehler && (
            <p id={`${uid}-host-fehler`} role="alert" className="mt-1 text-xs text-st-fehlt">
              {hostFehler}
            </p>
          )}
        </div>
        <div>
          <label htmlFor={`${uid}-port`} className="mb-1 block text-sm font-medium text-label">
            Port
          </label>
          <input id={`${uid}-port`} inputMode="numeric" value={werte.port} onChange={set("port")} className="field-ap" />
        </div>
        <div>
          <label htmlFor={`${uid}-user`} className="mb-1 block text-sm font-medium text-label">
            Benutzername
          </label>
          <input id={`${uid}-user`} value={werte.user} onChange={set("user")} className="field-ap" />
        </div>
        <div>
          <label htmlFor={`${uid}-absender`} className="mb-1 block text-sm font-medium text-label">
            Absenderadresse <span aria-hidden="true" className="text-st-fehlt">*</span>
          </label>
          <input
            id={`${uid}-absender`}
            type="email"
            value={werte.fromAddress}
            onChange={set("fromAddress")}
            placeholder="account@fieldvibe.de"
            aria-invalid={!!absenderFehler}
            aria-describedby={absenderFehler ? `${uid}-absender-fehler` : undefined}
            className="field-ap"
          />
          {absenderFehler && (
            <p id={`${uid}-absender-fehler`} role="alert" className="mt-1 text-xs text-st-fehlt">
              {absenderFehler}
            </p>
          )}
        </div>
      </div>
      <div>
        <label htmlFor={`${uid}-secret`} className="mb-1 block text-sm font-medium text-label">
          Passwort
        </label>
        <input
          id={`${uid}-secret`}
          type="password"
          autoComplete="new-password"
          value={werte.secret}
          onChange={set("secret")}
          placeholder={hatSecret ? "Gesetzt, zum Ändern neu eingeben" : undefined}
          className="field-ap"
        />
      </div>
    </div>
  );
}

const LEERE_WERTE: SmtpWerte = { host: "", port: "587", user: "", fromAddress: "account@fieldvibe.de", secret: "" };

function SmtpZeile({ integration }: { integration: PlattformIntegration }) {
  const bestaetigen = useBestaetigung();
  const queryClient = useQueryClient();
  const [werte, setWerte] = useState<SmtpWerte>({
    host: String(integration.config.host ?? ""),
    port: String(integration.config.port ?? "587"),
    user: String(integration.config.user ?? ""),
    fromAddress: String(integration.config.from_address ?? ""),
    secret: "",
  });

  const updateMutation = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: (body: { config?: Record<string, unknown>; secret?: string | null; aktiv?: boolean }) =>
      plattformIntegrationenApi.update(integration.id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["plattform-integrationen"] }),
  });

  const deleteMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: () => plattformIntegrationenApi.delete(integration.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["plattform-integrationen"] }),
  });

  return (
    <div className="space-y-2 card-ap p-4">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-label">SMTP (globaler Mailversand)</span>
        <span
          className={`border px-2 py-0.5 text-xs font-semibold ${
            integration.aktiv
              ? "border-st-erledigt text-st-erledigt "
              : "border-sep text-label2"
          }`}
        >
          {integration.aktiv ? "Aktiv" : "Inaktiv"}
        </span>
      </div>

      <SmtpFelder werte={werte} onChange={setWerte} hatSecret={integration.hat_secret} />

      <div className="flex gap-2">
        <button
          onClick={() =>
            updateMutation.mutate({
              config: { host: werte.host, port: Number(werte.port) || werte.port, user: werte.user, from_address: werte.fromAddress },
              ...(werte.secret ? { secret: werte.secret } : {}),
            })
          }
          disabled={updateMutation.isPending}
          className="btn-touch btn-ap-primary flex-1 py-1.5 text-sm disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => updateMutation.mutate({ aktiv: !integration.aktiv })}
          disabled={updateMutation.isPending}
          className="btn-touch btn-ap py-1.5 text-sm disabled:opacity-50"
        >
          {integration.aktiv ? "Deaktivieren" : "Aktivieren"}
        </button>
        <button
          onClick={async () => {
            if (await bestaetigen({ titel: "Globale SMTP-Konfiguration löschen?", bestaetigenLabel: "Löschen" })) deleteMutation.mutate();
          }}
          disabled={deleteMutation.isPending}
          className="btn-touch border border-st-fehlt px-3 py-1.5 text-sm font-medium text-st-fehlt hover:bg-st-fehlt-bg disabled:opacity-50 dark:hover:bg-st-fehlt-dot"
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
  const [neu, setNeu] = useState<SmtpWerte>(LEERE_WERTE);
  const [fehler, setFehler] = useState<{ host?: string; absender?: string }>({});

  const { data: integrationen, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["plattform-integrationen"],
    queryFn: plattformIntegrationenApi.list,
  });

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () =>
      plattformIntegrationenApi.create({
        typ: "smtp",
        config: { host: neu.host, port: Number(neu.port) || neu.port, user: neu.user, from_address: neu.fromAddress },
        secret: neu.secret || undefined,
      }),
    onSuccess: () => {
      setShowForm(false);
      setNeu(LEERE_WERTE);
      queryClient.invalidateQueries({ queryKey: ["plattform-integrationen"] });
    },
  });

  if (ladeFehler && !integrationen) return <FehlerZustand fehler={ladeFehler} was="Die Einstellungen" zurueck onErneut={() => void neuLaden()} className="py-6" />;
  if (isLoading) return <DetailSkeleton />;

  const smtp = integrationen?.find((i) => i.typ === "smtp");

  return (
    <div className="space-y-4">
      <h1 className="font-heading text-2xl font-semibold text-label">Plattform-Einstellungen</h1>

      <div className="space-y-2">
        <p className="text-sm text-label2">
          Greift, sobald ein Mandant selbst keine eigene SMTP-Integration eingerichtet hat (Seite
          „Integrationen" im jeweiligen Mandanten-Bereich) — für Einladungen und Passwort-Reset-Mails.
          Ein Mandant mit eigener SMTP-Konfiguration überschreibt das automatisch, hier muss nichts
          umgeschaltet werden.
        </p>
        <p className="text-xs text-label2">
          Absenderadresse braucht eine Domain, für die SPF/DKIM tatsächlich eingerichtet ist — sonst
          landen die Mails eher im Spam-Ordner der Empfänger.
        </p>
      </div>

      {smtp ? (
        <SmtpZeile integration={smtp} />
      ) : (
        <button onClick={() => setShowForm(true)} className="btn-touch btn-ap px-4 py-2 text-sm font-medium">
          + Globales SMTP einrichten
        </button>
      )}

      <AnlegenPanel offen={showForm} titel="Globales SMTP einrichten" onClose={() => setShowForm(false)}>
        <div className="space-y-4 p-4">
          <SmtpFelder werte={neu} onChange={setNeu} hostFehler={fehler.host} absenderFehler={fehler.absender} />
          <button
            disabled={createMutation.isPending}
            onClick={() => {
              const f = {
                host: neu.host.trim() ? undefined : "Bitte einen Host eingeben.",
                absender: neu.fromAddress.trim() ? undefined : "Bitte eine Absenderadresse eingeben.",
              };
              setFehler(f);
              if (!f.host && !f.absender) createMutation.mutate();
            }}
            className="btn-touch btn-ap-primary w-full py-1.5 text-sm"
          >
            SMTP einrichten
          </button>
        </div>
      </AnlegenPanel>
    </div>
  );
}
