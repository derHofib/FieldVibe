import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";

import { kundenApi, kundenportalZugaengeApi } from "../../../api/endpoints";
import { ApiError } from "../../../api/client";
import { AnlegenPanel } from "../../../components/AnlegenPanel";
import { Feld, FELD_KLASSE, NEU_BUTTON_KLASSE } from "../../../components/FormularFeld";
import { useAuth } from "../../../context/AuthContext";
import type { Kunde, KundenportalZugang } from "../../../types";
import { MIN_PASSWORT_LAENGE } from "../../../utils/passwort";

function PortalZugangZeile({ zugang, kundeId }: { zugang: KundenportalZugang; kundeId: string }) {
  const queryClient = useQueryClient();

  const toggleMutation = useMutation({
    mutationFn: () => kundenportalZugaengeApi.update(kundeId, zugang.id, { aktiv: !zugang.aktiv }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["portal-zugaenge", kundeId] }),
  });

  return (
    <div
      className={`flex items-start justify-between card-ap p-3 ${
        zugang.aktiv ? "" : "opacity-60"
      }`}
    >
      <div>
        <div className="text-fliess font-medium text-label">{zugang.name}</div>
        <div className="text-sekundaer text-label2">{zugang.email}</div>
      </div>
      <button
        onClick={() => toggleMutation.mutate()}
        className="btn-touch shrink-0 btn-ap px-3 py-1.5 text-sekundaer font-semibold"
      >
        {zugang.aktiv ? "Deaktivieren" : "Aktivieren"}
      </button>
    </div>
  );
}

export function KundenPortalLinkUndLogo({ kunde }: { kunde: Kunde }) {
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const istMandantAdmin =
    currentUser?.role === "mandant_admin" || currentUser?.role === "loesch_operativ";
  const [kopiert, setKopiert] = useState(false);
  const link = `${window.location.origin}/portal/l/${kunde.portal_slug}`;

  const { data: logoUrl } = useQuery({
    queryKey: ["kunde-logo-url", kunde.id],
    queryFn: () => kundenApi.logoUrl(kunde.id),
    enabled: !!kunde.logo_object_key,
  });

  const uploadMutation = useMutation({
    meta: { erfolg: "Hochgeladen" },
    mutationFn: (file: File) => kundenApi.logoUpload(kunde.id, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kunde.id] });
      queryClient.invalidateQueries({ queryKey: ["kunde-logo-url", kunde.id] });
    },
  });

  const removeMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: () => kundenApi.logoRemove(kunde.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["kunde-profil", kunde.id] });
      queryClient.invalidateQueries({ queryKey: ["kunde-logo-url", kunde.id] });
    },
  });

  async function kopieren() {
    await navigator.clipboard.writeText(link);
    setKopiert(true);
    setTimeout(() => setKopiert(false), 2000);
  }

  return (
    <div className="card-ap p-4">
      <h2 className="mb-2 text-fliess font-semibold text-label2">
        Portal-Link für {kunde.name}
      </h2>
      <p className="mb-2 text-sekundaer text-label2">
        Ein Link für den ganzen Kunden – jeder Mitarbeiter mit eigenem Kundenportal-Zugang meldet
        sich darüber mit seiner eigenen E-Mail und seinem eigenen Passwort an.
      </p>
      <div className="flex items-center gap-2 rounded-md bg-fill px-2 py-1.5">
        <span className="flex-1 truncate text-sekundaer text-label2">{link}</span>
        <button
          onClick={kopieren}
          className="btn-touch shrink-0 text-sekundaer font-medium text-tint "
        >
          {kopiert ? "Kopiert ✓" : "Link kopieren"}
        </button>
      </div>

      {istMandantAdmin && (
        <div className="mt-3 border-t border-sep pt-3 ">
          <h3 className="mb-2 text-sekundaer font-semibold text-label2">
            Logo für die Portal-Login-Seite
          </h3>
          <div className="flex items-center gap-3">
            {kunde.logo_object_key && logoUrl?.url && (
              <img
                src={logoUrl.url}
                alt={`Logo ${kunde.name}`}
                className="h-12 w-12 rounded-md object-contain ring-1 ring-sep "
              />
            )}
            <label className="btn-touch cursor-pointer btn-ap px-3 py-1.5 text-sekundaer font-semibold">
              {kunde.logo_object_key ? "Logo ersetzen" : "Logo hochladen"}
              <input
                type="file"
                accept="image/*"
                className="hidden"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file) uploadMutation.mutate(file);
                  e.target.value = "";
                }}
              />
            </label>
            {kunde.logo_object_key && (
              <button
                onClick={() => removeMutation.mutate()}
                disabled={removeMutation.isPending}
                className="btn-touch text-sekundaer text-st-fehlt underline disabled:opacity-50 "
              >
                Entfernen
              </button>
            )}
          </div>
          {uploadMutation.isError && (
            <p className="mt-1 text-sekundaer text-st-fehlt ">
              {uploadMutation.error instanceof ApiError ? uploadMutation.error.message : "Fehler beim Hochladen"}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

function NeuerPortalZugang({ kundeId }: { kundeId: string }) {
  const queryClient = useQueryClient();
  const [zeigen, setZeigen] = useState(false);
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fehler, setFehler] = useState<{ name?: string; email?: string; passwort?: string }>({});

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: () => kundenportalZugaengeApi.create(kundeId, { name, email, password }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["portal-zugaenge", kundeId] });
      setZeigen(false);
      setName("");
      setEmail("");
      setPassword("");
      setError(null);
    },
    onError: (err) => setError(err instanceof ApiError ? err.message : "Zugang konnte nicht angelegt werden"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    const f = {
      name: name.trim() ? undefined : "Bitte einen Namen eingeben.",
      email: /\S+@\S+\.\S+/.test(email) ? undefined : "Bitte eine gültige E-Mail-Adresse eingeben.",
      passwort: password.length >= MIN_PASSWORT_LAENGE ? undefined : `Das Passwort braucht mindestens ${MIN_PASSWORT_LAENGE} Zeichen.`,
    };
    setFehler(f);
    if (f.name || f.email || f.passwort) return;
    createMutation.mutate();
  }

  return (
    <>
      <button onClick={() => setZeigen(true)} className={NEU_BUTTON_KLASSE}>
        + Neuer Zugang
      </button>
      <AnlegenPanel offen={zeigen} titel="Neuer Kundenportal-Zugang" onClose={() => setZeigen(false)}>
        <form onSubmit={handleSubmit} className="space-y-3 p-4" noValidate>
          <Feld label="Name des Ansprechpartners" pflicht fehler={fehler.name}>
            {(p) => <input {...p} autoFocus value={name} onChange={(e) => setName(e.target.value)} className={FELD_KLASSE} />}
          </Feld>
          <Feld label="E-Mail" pflicht fehler={fehler.email}>
            {(p) => <input {...p} type="email" value={email} onChange={(e) => setEmail(e.target.value)} className={FELD_KLASSE} />}
          </Feld>
          <Feld label={`Passwort (mind. ${MIN_PASSWORT_LAENGE} Zeichen)`} pflicht fehler={fehler.passwort}>
            {(p) => (
              <input {...p} type="password" autoComplete="new-password" value={password} onChange={(e) => setPassword(e.target.value)} className={FELD_KLASSE} />
            )}
          </Feld>
          {error && (
            <p role="alert" className="text-fliess text-st-fehlt">
              {error}
            </p>
          )}
          <button type="submit" disabled={createMutation.isPending} className="btn-touch btn-ap-primary w-full rounded-md py-2 text-sekundaer font-medium">
            Anlegen
          </button>
        </form>
      </AnlegenPanel>
    </>
  );
}

export function PortalZugaengeVerwaltung({ kundeId }: { kundeId: string }) {
  const { data: zugaenge } = useQuery({
    queryKey: ["portal-zugaenge", kundeId],
    queryFn: () => kundenportalZugaengeApi.list(kundeId),
  });

  return (
    <div>
      <h2 className="mb-2 text-fliess font-semibold text-label2">Kundenportal-Zugänge</h2>
      {!zugaenge || zugaenge.length === 0 ? (
        <p className="text-sekundaer text-label2">Noch kein Zugang angelegt.</p>
      ) : (
        <div className="space-y-2">
          {zugaenge.map((z) => (
            <PortalZugangZeile key={z.id} zugang={z} kundeId={kundeId} />
          ))}
        </div>
      )}
      <div className="mt-2">
        <NeuerPortalZugang kundeId={kundeId} />
      </div>
    </div>
  );
}
