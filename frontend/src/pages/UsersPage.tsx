import { type FormEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, Building2, CircleDot, LogOut, Truck, Mail, Send, Shield, ShieldOff, Trash2, User as UserIcon, UserCheck, UserX, Users } from "lucide-react";
import { Link } from "react-router-dom";

import { AktionsMenue, type AktionsMenueEintrag } from "../components/AktionsMenue";
import { accountTypenApi, fahrzeugZuweisungenApi, mandantenApi, usersApi } from "../api/endpoints";
import { FahrzeugZuordnungSheet } from "../components/FahrzeugZuordnungSheet";
import { istModulAktiv } from "../utils/module";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";
import { Sheet } from "../components/apple/Sheet";
import { filterAnwenden, sucheAnwenden } from "../components/filter/auswerten";
import { FilterLeiste } from "../components/filter/FilterLeiste";
import type { FilterFeld } from "../components/filter/typen";
import { useFilterZustand } from "../components/filter/useFilterZustand";
import { AnlegenPanel } from "../components/AnlegenPanel";
import { EmptyState } from "../components/EmptyState";
import { FELD_KLASSE, NEU_BUTTON_KLASSE } from "../components/FormularFeld";
import { SeitenKopf } from "../office/OfficeUi";
import { istOfficeHost } from "../office/hostname";
import type { Einladung, EinladungRolle, Role, User } from "../types";
import { istVersteckteTastenkombi, klickFolge } from "../utils/verstecktFreischalten";
import { MIN_PASSWORT_LAENGE } from "../utils/passwort";
import { FehlerZustand } from "../components/FehlerZustand";
import { useBestaetigung } from "../components/ConfirmDialog";
import { SkeletonList } from "../components/Skeleton";
import { Select } from "../components/apple/Select";

export const ROLE_LABEL: Record<Role, string> = {
  super_admin: "Super-Admin",
  mandant_admin: "Mandanten-Admin",
  custom: "Account-Typ",
  loesch_ansicht: "Papierkorb (nur Ansicht)",
  loesch_operativ: "Papierkorb (operativ)",
};

// Nur super_admin darf diese Rollen vergeben (siehe app/api/routes/users.py).
// "custom" fehlt hier bewusst: ein Account-Typ ist an genau einen Mandanten
// gebunden (siehe app/api/routes/account_typen.py, mandant_admin-only), ein
// nicht-impersonierender super_admin hat also gar keinen Account-Typ-Katalog,
// aus dem er waehlen koennte.
const SUPER_ADMIN_ROLLEN: Role[] = ["super_admin", "mandant_admin", "loesch_ansicht", "loesch_operativ"];
// mandant_admin darf ausser sich selbst (weiteren Admins) nur eigene
// Account-Typen vergeben -- die Papierkorb-Rollen bleiben super_admin
// vorbehalten (siehe _PAPIERKORB_ROLLEN in app/api/routes/users.py).
const MANDANT_ADMIN_ROLLEN: Role[] = ["mandant_admin", "custom"];

// Deckungsgleich mit EinladungRolle in app/schemas/einladung.py -- fuer
// super_admin/loesch_*-Rollen gibt es keinen Einladungsweg im Backend, die
// bleiben bei direkter Anlage mit Passwort.
function istEinladungsfaehig(role: Role): role is EinladungRolle {
  return role === "mandant_admin" || role === "custom";
}

function LinkKopierenButton({ link }: { link: string }) {
  const [kopiert, setKopiert] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        await navigator.clipboard.writeText(link);
        setKopiert(true);
        setTimeout(() => setKopiert(false), 1500);
      }}
      className="btn-touch btn-ap"
    >
      {kopiert ? "Kopiert ✓" : "Link kopieren"}
    </button>
  );
}

// Unter dem Plattform-Layout liefert dessen Header das h1; Office und Feld-App brauchen ein eigenes.
function UsersTitel() {
  if (istOfficeHost()) return <SeitenKopf titel="Accounts" />;
  return <h1 className="text-titel-mobil font-bold text-label">Accounts</h1>;
}

function rolleText(u: User): string {
  return u.role === "custom" ? u.account_typ_name ?? "Account-Typ" : ROLE_LABEL[u.role];
}

export function UsersPage() {
  const uid = useId();
  const bestaetigen = useBestaetigung();
  const { currentUser, isImpersonating, hatRecht } = useAuth();
  const queryClient = useQueryClient();
  const isSuperAdmin = currentUser?.role === "super_admin";
  const istPlattform = isSuperAdmin && !isImpersonating;
  const [zeigeNeu, setZeigeNeu] = useState(false);

  const [formError, setFormError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("mandant_admin");
  const [accountTypId, setAccountTypId] = useState<string>("");
  const [mandantId, setMandantId] = useState<string>("");
  const [letzteEinladung, setLetzteEinladung] = useState<Einladung | null>(null);

  const [versteckteAnzeigen, setVersteckteAnzeigen] = useState(false);
  const klickZeiten = useRef<number[]>([]);
  const [loeschZiel, setLoeschZiel] = useState<User | null>(null);
  const [loeschBestaetigung, setLoeschBestaetigung] = useState("");

  useEffect(() => {
    function aufTaste(e: KeyboardEvent) {
      if (istVersteckteTastenkombi(e)) {
        e.preventDefault();
        setVersteckteAnzeigen(true);
      }
    }
    document.addEventListener("keydown", aufTaste);
    return () => document.removeEventListener("keydown", aufTaste);
  }, []);

  function aufUeberschriftKlick() {
    const { zeiten, erreicht } = klickFolge(klickZeiten.current, Date.now());
    klickZeiten.current = zeiten;
    if (erreicht) setVersteckteAnzeigen(true);
  }

  function versteckteAusblenden() {
    setVersteckteAnzeigen(false);
    if (role === "loesch_ansicht" || role === "loesch_operativ") setRole("mandant_admin");
  }

  const { data: users, isLoading, error: ladeFehler, refetch: neuLaden } = useQuery({
    queryKey: ["users", { versteckte: versteckteAnzeigen }],
    queryFn: versteckteAnzeigen ? usersApi.listMitVersteckten : usersApi.list,
  });
  // Backend (fahrzeug_zuweisungen.py): mandant_admin|custom, dispo.bearbeiten, Modul "fahrzeuge".
  // Die Übersicht kennt genau die Accounts, denen ein Fahrzeug zugeordnet werden kann.
  const kannFahrzeugZuordnen =
    !istPlattform &&
    (currentUser?.role === "mandant_admin" || currentUser?.role === "custom") &&
    hatRecht("dispo", "sehen") &&
    hatRecht("dispo", "bearbeiten") &&
    istModulAktiv(currentUser, "fahrzeuge");
  const { data: fahrzeugUebersicht } = useQuery({
    queryKey: ["fahrzeug-zuweisungen"],
    queryFn: fahrzeugZuweisungenApi.uebersicht,
    enabled: kannFahrzeugZuordnen,
  });
  const fahrzeugJeUser = new Map((fahrzeugUebersicht ?? []).map((z) => [z.techniker.id, z.fahrzeug]));
  const [fahrzeugZiel, setFahrzeugZiel] = useState<User | null>(null);
  const { data: mandanten } = useQuery({
    queryKey: ["mandanten"],
    queryFn: mandantenApi.list,
    enabled: isSuperAdmin,
  });
  const { data: accountTypen } = useQuery({
    queryKey: ["account-typen"],
    queryFn: accountTypenApi.list,
    enabled: !isSuperAdmin,
  });
  const { data: einladungen } = useQuery({
    queryKey: ["users", "einladungen"],
    queryFn: usersApi.listEinladungen,
  });

  const felder = useMemo<FilterFeld<User>[]>(
    () => [
      { key: "name", label: "Name", typ: "text", icon: UserIcon, wert: (u) => u.name },
      { key: "email", label: "E-Mail", typ: "text", icon: Mail, wert: (u) => u.email },
      {
        key: "rolle",
        label: "Rolle",
        typ: "auswahl",
        icon: Shield,
        wert: rolleText,
        optionen: [...new Set((users ?? []).map(rolleText))].sort().map((r) => ({ wert: r, label: r })),
      },
      ...(isSuperAdmin
        ? [
            {
              key: "mandant",
              label: "Mandant",
              typ: "verknuepfung" as const,
              icon: Building2,
              wert: (u: User) => u.mandant_id,
              optionen: (mandanten ?? []).map((m) => ({ wert: m.id, label: m.name })),
            },
          ]
        : []),
      {
        key: "status",
        label: "Status",
        typ: "auswahl",
        icon: CircleDot,
        wert: (u) => (u.aktiv ? "aktiv" : "deaktiviert"),
        optionen: [
          { wert: "aktiv", label: "Aktiv", status: "erledigt" },
          { wert: "deaktiviert", label: "Deaktiviert" },
        ],
      },
    ],
    [users, mandanten, isSuperAdmin],
  );
  const zustand = useFilterZustand({ felder });

  const createMutation = useMutation({
    meta: { erfolg: "Angelegt" },
    mutationFn: usersApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setEmail("");
      setName("");
      setPassword("");
      setZeigeNeu(false);
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Fehler"),
  });

  const einladenMutation = useMutation({
    meta: { erfolg: "Einladung gesendet" },
    mutationFn: usersApi.einladen,
    onSuccess: (einladung) => {
      queryClient.invalidateQueries({ queryKey: ["users", "einladungen"] });
      setLetzteEinladung(einladung);
      setEmail("");
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Fehler"),
  });

  const resendMutation = useMutation({
    meta: { erfolg: "Einladung erneut gesendet" },
    mutationFn: usersApi.einladungErneutSenden,
    onSuccess: (einladung) => {
      queryClient.invalidateQueries({ queryKey: ["users", "einladungen"] });
      setLetzteEinladung(einladung);
    },
  });

  const revokeMutation = useMutation({
    meta: { erfolg: "Einladung widerrufen" },
    mutationFn: usersApi.einladungWiderrufen,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users", "einladungen"] }),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, aktiv }: { id: string; aktiv: boolean }) =>
      usersApi.update(id, { aktiv }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const abmeldenMutation = useMutation({
    mutationFn: usersApi.abmeldenErzwingen,
  });

  const mfaResetMutation = useMutation({
    mutationFn: usersApi.mfaZuruecksetzen,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteMutation = useMutation({
    meta: { erfolg: "Gelöscht" },
    mutationFn: usersApi.remove,
    onSuccess: () => {
      setDeleteError(null);
      setLoeschZiel(null);
      setLoeschBestaetigung("");
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (err) => setDeleteError(err instanceof ApiError ? err.message : "Löschen fehlgeschlagen"),
  });

  const kannEingeladenWerden = istEinladungsfaehig(role);
  const verfuegbareRollen = (isSuperAdmin ? SUPER_ADMIN_ROLLEN : MANDANT_ADMIN_ROLLEN).filter(
    (r) => versteckteAnzeigen || (r !== "loesch_ansicht" && r !== "loesch_operativ"),
  );
  const loeschErwartet = loeschZiel ? loeschZiel.name.trim() || loeschZiel.email : "";
  const loeschBestaetigt = loeschZiel !== null && loeschBestaetigung.trim() === loeschErwartet;

  function loeschDialogSchliessen() {
    setLoeschZiel(null);
    setLoeschBestaetigung("");
  }

  function anlegenOeffnen() {
    setFormError(null);
    setLetzteEinladung(null);
    setZeigeNeu(true);
  }

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    setLetzteEinladung(null);
    const effectiveMandantId = isSuperAdmin ? mandantId || null : currentUser?.mandant_id ?? null;
    if (role !== "super_admin" && !effectiveMandantId) {
      setFormError("Bitte einen Mandanten auswählen");
      return;
    }
    if (role === "custom" && !accountTypId) {
      setFormError("Bitte einen Account-Typ auswählen");
      return;
    }
    if (kannEingeladenWerden) {
      einladenMutation.mutate({
        email,
        role,
        account_typ_id: role === "custom" ? accountTypId : null,
        mandant_id: isSuperAdmin ? effectiveMandantId : null,
      });
      return;
    }
    createMutation.mutate({
      mandant_id: role === "super_admin" ? null : effectiveMandantId,
      email,
      password,
      role,
      account_typ_id: null,
      name,
    });
  }

  // Eigener Account: Abmelden erzwingen/Löschen/MFA-Reset gar nicht anbieten
  // (das Backend lehnt sie ab) statt als ausgegrauten Eintrag.
  const kontoAktionen = (u: User): (AktionsMenueEintrag | "trenner")[] => [
    ...(u.aktiv && fahrzeugJeUser.has(u.id)
      ? [{ label: "Fahrzeug zuordnen", icon: Truck, onClick: () => setFahrzeugZiel(u) }]
      : []),
    {
      label: u.aktiv ? "Deaktivieren" : "Aktivieren",
      icon: u.aktiv ? UserX : UserCheck,
      onClick: () => toggleActiveMutation.mutate({ id: u.id, aktiv: !u.aktiv }),
    },
    ...(u.id === currentUser?.id
      ? []
      : [
          {
            label: "Abmelden erzwingen",
            icon: LogOut,
            disabled: abmeldenMutation.isPending,
            onClick: async () => {
              if (await bestaetigen({ titel: `${u.name} auf allen Geräten abmelden?`, bestaetigenLabel: "Abmelden" })) {
                abmeldenMutation.mutate(u.id);
              }
            },
          },
          ...(u.mfa_aktiv
            ? [
                {
                  label: "MFA zurücksetzen",
                  icon: ShieldOff,
                  disabled: mfaResetMutation.isPending,
                  onClick: async () => {
                    if (await bestaetigen({ titel: `Zwei-Faktor-Anmeldung von ${u.name} zurücksetzen?`, text: "Der Nutzer wird überall abgemeldet.", bestaetigenLabel: "Zurücksetzen" })) {
                      mfaResetMutation.mutate(u.id);
                    }
                  },
                },
              ]
            : []),
          "trenner" as const,
          {
            label: "Löschen",
            icon: Trash2,
            destruktiv: true,
            onClick: () => {
              setDeleteError(null);
              setLoeschBestaetigung("");
              setLoeschZiel(u);
            },
          },
        ]),
  ];

  const mandantNameById = new Map((mandanten ?? []).map((m) => [m.id, m.name]));
  const wirkt = (key: string) => zustand.bedingungen.some((b) => b.feld === key);
  const sichtbareUsers = sucheAnwenden(
    filterAnwenden(users ?? [], zustand.bedingungen, felder),
    zustand.sucheVerzoegert,
    (u) => `${u.name} ${u.email} ${rolleText(u)}`,
  );
  const filterAktiv = zustand.bedingungen.length > 0 || zustand.sucheVerzoegert !== "";
  const accountTypNameById = new Map((accountTypen ?? []).map((t) => [t.id, t.name]));
  const einladungRolleLabel = (e: Einladung) =>
    e.rolle === "custom" ? accountTypNameById.get(e.account_typ_id ?? "") ?? "Account-Typ" : ROLE_LABEL[e.rolle ?? "mandant_admin"];

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {istPlattform ? <span /> : <UsersTitel />}
        <div className="flex flex-wrap items-center gap-2">
          <button type="button" onClick={anlegenOeffnen} className={NEU_BUTTON_KLASSE}>
            {kannEingeladenWerden ? "+ Kollegen einladen" : "+ Neuer Account"}
          </button>
        </div>
      </div>

      <AnlegenPanel
        offen={zeigeNeu}
        titel={kannEingeladenWerden ? "Kollegen einladen" : "Neuen Account anlegen"}
        onClose={() => setZeigeNeu(false)}
      >
        <form onSubmit={handleCreate} className="space-y-3 p-4">
          {!kannEingeladenWerden && (
            <div>
              <label htmlFor={`${uid}-0`} className="mb-1 block text-fliess font-medium text-label">Name</label>
              <input id={`${uid}-0`}
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className={FELD_KLASSE}
              />
            </div>
          )}
          <div>
            <label htmlFor={`${uid}-1`} className="mb-1 block text-fliess font-medium text-label">E-Mail</label>
            <input id={`${uid}-1`}
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className={FELD_KLASSE}
            />
          </div>
          {!kannEingeladenWerden && (
            <div>
              <label htmlFor={`${uid}-2`} className="mb-1 block text-fliess font-medium text-label">Passwort</label>
              <input id={`${uid}-2`}
                type="password"
                required
                minLength={MIN_PASSWORT_LAENGE}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={FELD_KLASSE}
              />
              <p className="mt-1 text-sekundaer text-label2">Mindestens {MIN_PASSWORT_LAENGE} Zeichen.</p>
            </div>
          )}
          <div>
            <label htmlFor={`${uid}-3`} className="mb-1 block text-fliess font-medium text-label">Rolle</label>
            <Select id={`${uid}-3`}
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
            >
              {verfuegbareRollen.map((value) => (
                <option key={value} value={value}>
                  {value === "custom" ? "Account-Typ…" : ROLE_LABEL[value]}
                </option>
              ))}
            </Select>
          </div>
          {role === "custom" && (
            <div>
              <label htmlFor={`${uid}-6`} className="mb-1 block text-fliess font-medium text-label">
                Account-Typ
              </label>
              {accountTypen && accountTypen.length > 0 ? (
                <Select
                  id={`${uid}-6`}
                  required
                  value={accountTypId}
                  onChange={(e) => setAccountTypId(e.target.value)}
                >
                  <option value="" disabled>
                    Bitte wählen…
                  </option>
                  {accountTypen.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.icon ? `${t.icon} ` : ""}
                      {t.name}
                    </option>
                  ))}
                </Select>
              ) : (
                <Link
                  to="/account-typen"
                  className="text-fliess font-medium text-tint-text hover:underline"
                >
                  Noch keine Account-Typen — jetzt anlegen →
                </Link>
              )}
            </div>
          )}
          {isSuperAdmin && role !== "super_admin" && (
            <div>
              <label htmlFor={`${uid}-4`} className="mb-1 block text-fliess font-medium text-label">Mandant</label>
              <Select id={`${uid}-4`}
                required
                value={mandantId}
                onChange={(e) => setMandantId(e.target.value)}
              >
                <option value="" disabled>
                  Bitte wählen…
                </option>
                {mandanten?.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </Select>
            </div>
          )}
          {formError && <p role="alert" className="text-fliess text-st-fehlt">{formError}</p>}
          {letzteEinladung && (
            <div className="flex flex-wrap items-center gap-3 border rounded-[var(--radius-ap-md)] border-st-erledigt px-4 py-3 text-fliess text-st-erledigt">
              <span>
                Einladung an <strong>{letzteEinladung.email}</strong> verschickt.
              </span>
              {letzteEinladung.registrierungslink && (
                <LinkKopierenButton link={letzteEinladung.registrierungslink} />
              )}
            </div>
          )}
          <button
            type="submit"
            disabled={createMutation.isPending || einladenMutation.isPending}
            className="btn-touch btn-ap-primary w-full"
          >
            {kannEingeladenWerden ? "Einladen" : "Anlegen"}
          </button>
        </form>
      </AnlegenPanel>

      {einladungen && einladungen.length > 0 && (
        <section>
          <h2 className="mb-4 text-zeile font-bold text-label">Offene Einladungen</h2>
          <div className="card-ap overflow-x-auto">
          <table className="w-full text-left">
            <thead className="text-sekundaer text-label2">
              <tr>
                <th className="px-4 py-3">E-Mail</th>
                <th className="px-4 py-3">Rolle</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sep text-fliess">
              {einladungen
                .filter((e) => e.status === "offen")
                .map((e) => (
                  <tr key={e.id}>
                    <td className="px-4 py-3 text-label">{e.email}</td>
                    <td className="px-4 py-3 text-label">{einladungRolleLabel(e)}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`border rounded-[var(--radius-ap-pill)] px-2 py-0.5 text-meta font-semibold ${
                          e.abgelaufen
                            ? "border-st-arbeit text-st-arbeit "
                            : "border-sep text-label2"
                        }`}
                      >
                        {e.abgelaufen ? "Abgelaufen" : "Offen"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {e.registrierungslink && <LinkKopierenButton link={e.registrierungslink} />}
                        <AktionsMenue
                          label={`Aktionen für Einladung an ${e.email}`}
                          eintraege={[
                            { label: "Erneut senden", icon: Send, onClick: () => resendMutation.mutate(e.id) },
                            "trenner",
                            {
                              label: "Widerrufen",
                              icon: Ban,
                              destruktiv: true,
                              onClick: async () => {
                                if (await bestaetigen({ titel: `Einladung an ${e.email} widerrufen?`, bestaetigenLabel: "Widerrufen" })) {
                                  revokeMutation.mutate(e.id);
                                }
                              },
                            },
                          ]}
                        />
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-4 text-zeile font-bold text-label" onClick={aufUeberschriftKlick}>
          Accounts
        </h2>
        <FilterLeiste
          felder={felder}
          zustand={zustand}
          suchPlatzhalter="Accounts suchen"
          variante={istPlattform ? "office" : undefined}
          className="mb-3"
        />
        {versteckteAnzeigen && (
          <p className="mb-2 flex items-center gap-2 text-sekundaer text-label2">
            Versteckte Accounts werden angezeigt
            <button type="button" onClick={versteckteAusblenden} className="font-medium text-tint-text hover:underline">
              Ausblenden
            </button>
          </p>
        )}
        {deleteError && <p className="mb-2 text-fliess text-st-fehlt ">{deleteError}</p>}
        {isLoading ? (
          <SkeletonList count={4} />
        ) : ladeFehler && !users ? (
          <FehlerZustand fehler={ladeFehler} was="Die Nutzer" onErneut={() => void neuLaden()} />
        ) : sichtbareUsers.length === 0 ? (
          <EmptyState
            icon={Users}
            text={
              filterAktiv
                ? zustand.bedingungen.length > 0 || !zustand.sucheVerzoegert
                  ? "Keine Treffer für diese Filter"
                  : `Nichts gefunden für „${zustand.sucheVerzoegert}"`
                : "Noch keine Accounts angelegt. Lege den ersten Account an, damit sich jemand anmelden kann."
            }
            action={
              filterAktiv ? (
                <button type="button" onClick={zustand.zuruecksetzen} className={NEU_BUTTON_KLASSE}>
                  Filter zurücksetzen
                </button>
              ) : (
                <button type="button" onClick={anlegenOeffnen} className={NEU_BUTTON_KLASSE}>
                  {kannEingeladenWerden ? "+ Kollegen einladen" : "+ Neuer Account"}
                </button>
              )
            }
          />
        ) : (
          <>
          <ul className="space-y-2 md:hidden">
            {sichtbareUsers.map((u) => (
              <li key={u.id} className="card-ap flex items-start justify-between gap-2 p-3">
                <div className="min-w-0">
                  <p className="truncate text-fliess font-medium text-label">{u.name}</p>
                  <p className="truncate text-sekundaer text-label2">{u.email}</p>
                  <p className="mt-1 text-sekundaer text-label2">
                    {u.role === "custom" ? u.account_typ_name ?? "Account-Typ" : ROLE_LABEL[u.role]}
                    {isSuperAdmin && u.mandant_id ? ` · ${mandantNameById.get(u.mandant_id) ?? "–"}` : ""}
                  </p>
                  <span
                    className={`mt-1.5 inline-block border rounded-[var(--radius-ap-pill)] px-2 py-0.5 text-meta font-semibold ${
                      u.aktiv ? "border-st-erledigt text-st-erledigt" : "border-sep text-label2"
                    }`}
                  >
                    {u.aktiv ? "Aktiv" : "Deaktiviert"}
                  </span>
                </div>
                <AktionsMenue label={`Aktionen für ${u.name}`} eintraege={kontoAktionen(u)} />
              </li>
            ))}
          </ul>
          <div className="hidden md:block">
          <div className="card-ap overflow-hidden">
          <table className="w-full text-left">
            <thead className="text-sekundaer text-label2">
              <tr>
                <th className={`px-4 py-3 ${wirkt("name") ? "text-tint-text" : ""}`}>Name</th>
                <th className={`px-4 py-3 ${wirkt("email") ? "text-tint-text" : ""}`}>E-Mail</th>
                <th className={`px-4 py-3 ${wirkt("rolle") ? "text-tint-text" : ""}`}>Rolle</th>
                {isSuperAdmin && <th className={`px-4 py-3 ${wirkt("mandant") ? "text-tint-text" : ""}`}>Mandant</th>}
                <th className={`px-4 py-3 ${wirkt("status") ? "text-tint-text" : ""}`}>Status</th>
                <th className="px-4 py-3 text-right">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sep text-fliess">
              {sichtbareUsers.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-3 font-medium text-label">{u.name}</td>
                  <td className="px-4 py-3 text-label2">{u.email}</td>
                  <td className="px-4 py-3 text-label">
                    {u.role === "custom" ? u.account_typ_name ?? "Account-Typ" : ROLE_LABEL[u.role]}
                    {fahrzeugJeUser.get(u.id) && (
                      <span className="block text-sekundaer text-label2">Fahrzeug: {fahrzeugJeUser.get(u.id)?.bezeichnung}</span>
                    )}
                  </td>
                  {isSuperAdmin && (
                    <td className="px-4 py-3 text-label2">
                      {u.mandant_id ? mandantNameById.get(u.mandant_id) ?? "–" : "–"}
                    </td>
                  )}
                  <td className="px-4 py-3">
                    <span
                      className={`border rounded-[var(--radius-ap-pill)] px-2 py-0.5 text-meta font-semibold ${
                        u.aktiv
                          ? "border-st-erledigt text-st-erledigt "
                          : "border-sep text-label2"
                      }`}
                    >
                      {u.aktiv ? "Aktiv" : "Deaktiviert"}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right">
                    <AktionsMenue label={`Aktionen für ${u.name}`} eintraege={kontoAktionen(u)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          </div>
          </>
        )}
      </section>

      {fahrzeugZiel && (
        <FahrzeugZuordnungSheet
          userId={fahrzeugZiel.id}
          name={fahrzeugZiel.name}
          aktuellesFahrzeugId={fahrzeugJeUser.get(fahrzeugZiel.id)?.id ?? null}
          onClose={() => setFahrzeugZiel(null)}
        />
      )}

      <Sheet
        offen={loeschZiel !== null}
        onClose={loeschDialogSchliessen}
        titel="Account löschen"
        links={
          <button type="button" onClick={loeschDialogSchliessen} className="text-zeile text-tint-text">
            Abbrechen
          </button>
        }
        rechts={
          <button
            type="button"
            disabled={!loeschBestaetigt || deleteMutation.isPending}
            onClick={() => loeschZiel && deleteMutation.mutate(loeschZiel.id)}
            className="text-zeile font-semibold text-st-fehlt disabled:opacity-40"
          >
            Löschen
          </button>
        }
      >
        {loeschZiel && (
          <div className="space-y-4 p-4">
            <p className="text-fliess text-label">
              Account von {loeschZiel.name || loeschZiel.email} endgültig löschen? Persönliche Daten werden
              unwiderruflich entfernt. Zeiterfassungen, Rechnungen und Verlauf bleiben erhalten und werden als
              „Gelöschter Nutzer“ angezeigt.
            </p>
            <div>
              <label htmlFor={`${uid}-5`} className="mb-1 block text-fliess font-medium text-label">
                Zur Bestätigung „{loeschErwartet}“ eintippen
              </label>
              <input id={`${uid}-5`}
                value={loeschBestaetigung}
                onChange={(e) => setLoeschBestaetigung(e.target.value)}
                autoComplete="off"
                className="btn-touch w-full border rounded-[var(--radius-ap-input)] border-sep bg-transparent px-3 py-2 text-label"
              />
            </div>
            {deleteError && <p className="text-fliess text-st-fehlt">{deleteError}</p>}
          </div>
        )}
      </Sheet>
    </div>
  );
}
