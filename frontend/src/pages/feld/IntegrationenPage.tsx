import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { integrationenApi, mandantEinstellungenApi } from "../../api/endpoints";
import { useAuth } from "../../context/AuthContext";
import type { MandantEinstellungen, MandantIntegration } from "../../types";

function FirmenprofilSection({ einstellungen }: { einstellungen: MandantEinstellungen }) {
  const queryClient = useQueryClient();
  const fd = einstellungen.firmendaten;
  const [strasse, setStrasse] = useState(fd.adresse?.strasse ?? "");
  const [plz, setPlz] = useState(fd.adresse?.plz ?? "");
  const [ort, setOrt] = useState(fd.adresse?.ort ?? "");
  const [telefon, setTelefon] = useState(fd.telefon ?? "");
  const [email, setEmail] = useState(fd.email ?? "");
  const [website, setWebsite] = useState(fd.website ?? "");
  const [bankName, setBankName] = useState(fd.bank_name ?? "");
  const [iban, setIban] = useState(fd.iban ?? "");
  const [bic, setBic] = useState(fd.bic ?? "");
  const [geschaeftsfuehrung, setGeschaeftsfuehrung] = useState(fd.geschaeftsfuehrung ?? "");
  const [handelsregister, setHandelsregister] = useState(fd.handelsregister ?? "");
  const [ustIdnr, setUstIdnr] = useState(fd.ust_idnr ?? "");

  const { data: logoUrl } = useQuery({
    queryKey: ["mandant-logo-url"],
    queryFn: mandantEinstellungenApi.logoUrl,
  });

  const speichernMutation = useMutation({
    mutationFn: () =>
      mandantEinstellungenApi.firmendatenSpeichern({
        adresse: { strasse, plz, ort },
        telefon,
        email,
        website,
        bank_name: bankName,
        iban,
        bic,
        geschaeftsfuehrung,
        handelsregister,
        ust_idnr: ustIdnr,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mandant-einstellungen"] }),
  });

  const logoUploadMutation = useMutation({
    mutationFn: (file: File) => mandantEinstellungenApi.logoUpload(file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mandant-einstellungen"] });
      queryClient.invalidateQueries({ queryKey: ["mandant-logo-url"] });
    },
  });

  const logoRemoveMutation = useMutation({
    mutationFn: () => mandantEinstellungenApi.logoRemove(),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mandant-einstellungen"] });
      queryClient.invalidateQueries({ queryKey: ["mandant-logo-url"] });
    },
  });

  const inputClass =
    "rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100";

  return (
    <div className="space-y-3 rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
      <div>
        <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300">🏢 Firmenprofil</h2>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Diese Angaben erscheinen im Briefkopf und in der Fußzeile eurer Angebots-PDFs.
        </p>
      </div>

      <div className="flex items-center gap-3">
        {logoUrl?.url ? (
          <img src={logoUrl.url} alt="Firmenlogo" className="h-12 max-w-[160px] object-contain" />
        ) : (
          <span className="text-xs text-slate-400 dark:text-slate-500">Kein Logo hinterlegt</span>
        )}
        <label className="btn-touch cursor-pointer rounded-md bg-slate-100 px-3 py-1.5 text-xs font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
          Logo hochladen
          <input
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => {
              const file = e.target.files?.[0];
              if (file) logoUploadMutation.mutate(file);
              e.target.value = "";
            }}
          />
        </label>
        {einstellungen.logo_object_key && (
          <button
            onClick={() => logoRemoveMutation.mutate()}
            disabled={logoRemoveMutation.isPending}
            className="btn-touch text-xs font-medium text-red-700 disabled:opacity-50 dark:text-red-400"
          >
            Entfernen
          </button>
        )}
      </div>

      <input
        value={strasse}
        onChange={(e) => setStrasse(e.target.value)}
        placeholder="Straße, Nr."
        className={`w-full ${inputClass}`}
      />
      <div className="grid grid-cols-3 gap-2">
        <input value={plz} onChange={(e) => setPlz(e.target.value)} placeholder="PLZ" className={inputClass} />
        <input
          value={ort}
          onChange={(e) => setOrt(e.target.value)}
          placeholder="Ort"
          className={`col-span-2 ${inputClass}`}
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <input value={telefon} onChange={(e) => setTelefon(e.target.value)} placeholder="Telefon" className={inputClass} />
        <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="E-Mail" className={inputClass} />
        <input
          value={website}
          onChange={(e) => setWebsite(e.target.value)}
          placeholder="Website"
          className={`col-span-2 ${inputClass}`}
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <input value={bankName} onChange={(e) => setBankName(e.target.value)} placeholder="Bank" className={inputClass} />
        <input value={iban} onChange={(e) => setIban(e.target.value)} placeholder="IBAN" className={inputClass} />
        <input value={bic} onChange={(e) => setBic(e.target.value)} placeholder="BIC" className={inputClass} />
        <input
          value={ustIdnr}
          onChange={(e) => setUstIdnr(e.target.value)}
          placeholder="USt-IdNr."
          className={inputClass}
        />
        <input
          value={geschaeftsfuehrung}
          onChange={(e) => setGeschaeftsfuehrung(e.target.value)}
          placeholder="Geschäftsführung"
          className={inputClass}
        />
        <input
          value={handelsregister}
          onChange={(e) => setHandelsregister(e.target.value)}
          placeholder="Handelsregister"
          className={inputClass}
        />
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => speichernMutation.mutate()}
          disabled={speichernMutation.isPending}
          className="btn-touch rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Speichern
        </button>
        {speichernMutation.isSuccess && (
          <span className="text-xs text-green-700 dark:text-green-400">Gespeichert.</span>
        )}
      </div>
    </div>
  );
}

function SmtpZeile({ integration }: { integration: MandantIntegration }) {
  const queryClient = useQueryClient();
  const [host, setHost] = useState(String(integration.config.host ?? ""));
  const [port, setPort] = useState(String(integration.config.port ?? "587"));
  const [user, setUser] = useState(String(integration.config.user ?? ""));
  const [fromAddress, setFromAddress] = useState(String(integration.config.from_address ?? ""));
  const [secret, setSecret] = useState("");

  const updateMutation = useMutation({
    mutationFn: (body: { config?: Record<string, unknown>; secret?: string | null; aktiv?: boolean }) =>
      integrationenApi.update(integration.id, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["integrationen"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: () => integrationenApi.delete(integration.id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["integrationen"] }),
  });

  return (
    <div className="space-y-2 rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
      <div className="flex items-center justify-between">
        <span className="text-sm font-semibold text-slate-700 dark:text-slate-300">SMTP (E-Mail-Versand)</span>
        <span
          className={`rounded-full px-2 py-0.5 text-xs font-semibold ${
            integration.aktiv
              ? "bg-green-50 text-green-700 dark:bg-green-500/10 dark:text-green-400"
              : "bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400"
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
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        <input
          value={port}
          onChange={(e) => setPort(e.target.value)}
          placeholder="Port"
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        <input
          value={user}
          onChange={(e) => setUser(e.target.value)}
          placeholder="Benutzername"
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
        <input
          value={fromAddress}
          onChange={(e) => setFromAddress(e.target.value)}
          placeholder="Absender-Adresse"
          className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
        />
      </div>
      <input
        type="password"
        value={secret}
        onChange={(e) => setSecret(e.target.value)}
        placeholder={integration.hat_secret ? "Passwort (gesetzt, zum Ändern eingeben)" : "Passwort"}
        className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
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
          className="btn-touch flex-1 rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
        >
          Speichern
        </button>
        <button
          onClick={() => updateMutation.mutate({ aktiv: !integration.aktiv })}
          disabled={updateMutation.isPending}
          className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-slate-800 dark:text-slate-300"
        >
          {integration.aktiv ? "Deaktivieren" : "Aktivieren"}
        </button>
        <button
          onClick={() => {
            if (window.confirm("SMTP-Integration wirklich löschen?")) deleteMutation.mutate();
          }}
          disabled={deleteMutation.isPending}
          className="btn-touch rounded-md bg-red-50 px-3 py-1.5 text-sm font-medium text-red-700 disabled:opacity-50 dark:bg-red-500/10 dark:text-red-400"
        >
          Löschen
        </button>
      </div>
    </div>
  );
}

export function IntegrationenPage() {
  const { currentUser } = useAuth();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);
  const [host, setHost] = useState("");
  const [port, setPort] = useState("587");
  const [user, setUser] = useState("");
  const [fromAddress, setFromAddress] = useState("");
  const [secret, setSecret] = useState("");

  const { data: integrationen, isLoading } = useQuery({
    queryKey: ["integrationen"],
    queryFn: integrationenApi.list,
  });

  const { data: einstellungen } = useQuery({
    queryKey: ["mandant-einstellungen"],
    queryFn: mandantEinstellungenApi.get,
  });

  const schedulerMutation = useMutation({
    mutationFn: (stunde: number | null) => mandantEinstellungenApi.update(stunde),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["mandant-einstellungen"] }),
  });

  const createMutation = useMutation({
    mutationFn: () =>
      integrationenApi.create({
        typ: "smtp",
        config: { host, port: Number(port) || port, user, from_address: fromAddress },
        secret: secret || undefined,
      }),
    onSuccess: () => {
      setShowForm(false);
      setHost("");
      setPort("587");
      setUser("");
      setFromAddress("");
      setSecret("");
      queryClient.invalidateQueries({ queryKey: ["integrationen"] });
    },
  });

  if (currentUser && currentUser.role !== "mandant_admin" && currentUser.role !== "loesch_operativ")
    return <Navigate to="/feed" replace />;
  if (isLoading) return <p className="text-center text-slate-500 dark:text-slate-400">Lädt…</p>;

  const smtp = integrationen?.find((i) => i.typ === "smtp");

  return (
    <div className="space-y-4">
      <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-slate-400">
        ← Zurück
      </button>
      <h1 className="text-lg font-bold text-slate-800 dark:text-slate-100">🔌 Integrationen</h1>

      {einstellungen && <FirmenprofilSection einstellungen={einstellungen} />}

      {einstellungen && (
        <div className="rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
          <h2 className="mb-1 text-sm font-semibold text-slate-700 dark:text-slate-300">
            Prüfzyklen-/Mahnwesen-Uhrzeit
          </h2>
          <p className="mb-2 text-xs text-slate-500 dark:text-slate-400">
            Uhrzeit (UTC), zu der der tägliche Hintergrund-Lauf für diesen Betrieb
            geprüfte/überfällige Vorgänge und Rechnungen bearbeitet.
          </p>
          <div className="flex items-center gap-2">
            <select
              value={einstellungen.scheduler_stunde_utc ?? ""}
              onChange={(e) =>
                schedulerMutation.mutate(e.target.value === "" ? null : Number(e.target.value))
              }
              className="btn-touch rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            >
              <option value="">Standard ({einstellungen.effektive_scheduler_stunde_utc.toString().padStart(2, "0")}:00 UTC)</option>
              {Array.from({ length: 24 }, (_, h) => (
                <option key={h} value={h}>
                  {h.toString().padStart(2, "0")}:00 UTC
                </option>
              ))}
            </select>
            {schedulerMutation.isPending && (
              <span className="text-xs text-slate-400 dark:text-slate-500">Speichert…</span>
            )}
          </div>
        </div>
      )}

      <p className="text-sm text-slate-500 dark:text-slate-400">
        SMTP wird für den "Passwort vergessen"-Link im Kundenportal genutzt. Ohne
        konfiguriertes SMTP kann ein Mitarbeiter das Passwort eines Kunden weiterhin
        direkt über den Kunden setzen.
      </p>

      {smtp ? (
        <SmtpZeile integration={smtp} />
      ) : showForm ? (
        <div className="space-y-2 rounded-lg bg-white p-4 shadow-sm dark:bg-slate-900 dark:shadow-none dark:ring-1 dark:ring-slate-800">
          <div className="grid grid-cols-2 gap-2">
            <input
              value={host}
              onChange={(e) => setHost(e.target.value)}
              placeholder="Host"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <input
              value={port}
              onChange={(e) => setPort(e.target.value)}
              placeholder="Port"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <input
              value={user}
              onChange={(e) => setUser(e.target.value)}
              placeholder="Benutzername"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
            <input
              value={fromAddress}
              onChange={(e) => setFromAddress(e.target.value)}
              placeholder="Absender-Adresse"
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
            />
          </div>
          <input
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            placeholder="Passwort"
            className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-slate-700 dark:bg-slate-800 dark:text-slate-100"
          />
          <button
            disabled={!host || !fromAddress || createMutation.isPending}
            onClick={() => createMutation.mutate()}
            className="btn-touch w-full rounded-md bg-gradient-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
          >
            SMTP einrichten
          </button>
        </div>
      ) : (
        <button
          onClick={() => setShowForm(true)}
          className="btn-touch w-full rounded-md bg-white py-2.5 text-sm font-medium text-slate-700 shadow-sm dark:bg-slate-900 dark:text-slate-300 dark:shadow-none dark:ring-1 dark:ring-slate-800"
        >
          + SMTP einrichten
        </button>
      )}
    </div>
  );
}
