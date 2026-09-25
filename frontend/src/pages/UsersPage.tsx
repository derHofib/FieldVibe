import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { accountTypenApi, mandantenApi, usersApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";
import type { Einladung, EinladungRolle, Role } from "../types";

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

export function UsersPage() {
  const { currentUser } = useAuth();
  const queryClient = useQueryClient();
  const isSuperAdmin = currentUser?.role === "super_admin";

  const [formError, setFormError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("mandant_admin");
  const [accountTypId, setAccountTypId] = useState<string>("");
  const [mandantId, setMandantId] = useState<string>("");
  const [letzteEinladung, setLetzteEinladung] = useState<Einladung | null>(null);

  const { data: users, isLoading } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
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

  const createMutation = useMutation({
    mutationFn: usersApi.create,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["users"] });
      setEmail("");
      setName("");
      setPassword("");
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Fehler"),
  });

  const einladenMutation = useMutation({
    mutationFn: usersApi.einladen,
    onSuccess: (einladung) => {
      queryClient.invalidateQueries({ queryKey: ["users", "einladungen"] });
      setLetzteEinladung(einladung);
      setEmail("");
    },
    onError: (err) => setFormError(err instanceof ApiError ? err.message : "Fehler"),
  });

  const resendMutation = useMutation({
    mutationFn: usersApi.einladungErneutSenden,
    onSuccess: (einladung) => {
      queryClient.invalidateQueries({ queryKey: ["users", "einladungen"] });
      setLetzteEinladung(einladung);
    },
  });

  const revokeMutation = useMutation({
    mutationFn: usersApi.einladungWiderrufen,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users", "einladungen"] }),
  });

  const toggleActiveMutation = useMutation({
    mutationFn: ({ id, aktiv }: { id: string; aktiv: boolean }) =>
      usersApi.update(id, { aktiv }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["users"] }),
  });

  const [deleteError, setDeleteError] = useState<string | null>(null);
  const deleteMutation = useMutation({
    mutationFn: usersApi.remove,
    onSuccess: () => {
      setDeleteError(null);
      queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (err) => setDeleteError(err instanceof ApiError ? err.message : "Löschen fehlgeschlagen"),
  });

  const kannEingeladenWerden = istEinladungsfaehig(role);

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

  const mandantNameById = new Map((mandanten ?? []).map((m) => [m.id, m.name]));
  const accountTypNameById = new Map((accountTypen ?? []).map((t) => [t.id, t.name]));
  const einladungRolleLabel = (e: Einladung) =>
    e.rolle === "custom" ? accountTypNameById.get(e.account_typ_id ?? "") ?? "Account-Typ" : ROLE_LABEL[e.rolle ?? "mandant_admin"];

  return (
    <div className="space-y-8">
      <section>
        <h2 className="mb-4 text-lg font-bold text-label">
          {kannEingeladenWerden ? "Kollegen einladen" : "Neuen Account anlegen"}
        </h2>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          {!kannEingeladenWerden && (
            <div>
              <label className="mb-1 block text-sm font-medium text-label">Name</label>
              <input
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
              />
            </div>
          )}
          <div>
            <label className="mb-1 block text-sm font-medium text-label">E-Mail</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
            />
          </div>
          {!kannEingeladenWerden && (
            <div>
              <label className="mb-1 block text-sm font-medium text-label">Passwort</label>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
              />
            </div>
          )}
          <div>
            <label className="mb-1 block text-sm font-medium text-label">Rolle</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
            >
              {(isSuperAdmin ? SUPER_ADMIN_ROLLEN : MANDANT_ADMIN_ROLLEN).map((value) => (
                <option key={value} value={value}>
                  {value === "custom" ? "Account-Typ…" : ROLE_LABEL[value]}
                </option>
              ))}
            </select>
          </div>
          {role === "custom" && (
            <div>
              <label className="mb-1 block text-sm font-medium text-label">
                Account-Typ
              </label>
              {accountTypen && accountTypen.length > 0 ? (
                <select
                  required
                  value={accountTypId}
                  onChange={(e) => setAccountTypId(e.target.value)}
                  className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
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
                </select>
              ) : (
                <Link
                  to="/account-typen"
                  className="text-sm font-medium text-tint hover:underline"
                >
                  Noch keine Account-Typen — jetzt anlegen →
                </Link>
              )}
            </div>
          )}
          {isSuperAdmin && role !== "super_admin" && (
            <div>
              <label className="mb-1 block text-sm font-medium text-label">Mandant</label>
              <select
                required
                value={mandantId}
                onChange={(e) => setMandantId(e.target.value)}
                className="btn-touch border border-sep bg-transparent px-3 py-2 text-label"
              >
                <option value="" disabled>
                  Bitte wählen…
                </option>
                {mandanten?.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name}
                  </option>
                ))}
              </select>
            </div>
          )}
          <button
            type="submit"
            disabled={createMutation.isPending || einladenMutation.isPending}
            className="btn-touch btn-ap-primary"
          >
            {kannEingeladenWerden ? "Einladen" : "Anlegen"}
          </button>
        </form>
        {formError && <p className="mt-2 text-sm text-st-fehlt ">{formError}</p>}
        {letzteEinladung && (
          <div className="mt-3 flex flex-wrap items-center gap-3 border border-st-erledigt px-4 py-3 text-sm text-st-erledigt ">
            <span>
              Einladung an <strong>{letzteEinladung.email}</strong> verschickt.
            </span>
            {letzteEinladung.registrierungslink && (
              <LinkKopierenButton link={letzteEinladung.registrierungslink} />
            )}
          </div>
        )}
      </section>

      {einladungen && einladungen.length > 0 && (
        <section>
          <h2 className="mb-4 text-lg font-bold text-label">Offene Einladungen</h2>
          <table className="w-full border border-sep bg-card text-left">
            <thead className="text-sm text-label2">
              <tr>
                <th className="px-4 py-3">E-Mail</th>
                <th className="px-4 py-3">Rolle</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sep text-sm">
              {einladungen
                .filter((e) => e.status === "offen")
                .map((e) => (
                  <tr key={e.id}>
                    <td className="px-4 py-3 text-label">{e.email}</td>
                    <td className="px-4 py-3 text-label">{einladungRolleLabel(e)}</td>
                    <td className="px-4 py-3">
                      <span
                        className={`border px-2 py-0.5 text-xs font-semibold ${
                          e.abgelaufen
                            ? "border-st-arbeit text-st-arbeit "
                            : "border-sep text-label2"
                        }`}
                      >
                        {e.abgelaufen ? "Abgelaufen" : "Offen"}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-wrap gap-2">
                        {e.registrierungslink && <LinkKopierenButton link={e.registrierungslink} />}
                        <button
                          onClick={() => resendMutation.mutate(e.id)}
                          className="btn-touch btn-ap"
                        >
                          Erneut senden
                        </button>
                        <button
                          onClick={() => {
                            if (window.confirm(`Einladung an ${e.email} widerrufen?`)) {
                              revokeMutation.mutate(e.id);
                            }
                          }}
                          className="btn-touch border border-st-fehlt px-3 py-2 text-xs font-semibold text-st-fehlt hover:bg-st-fehlt-bg dark:hover:bg-st-fehlt-dot"
                        >
                          Widerrufen
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
            </tbody>
          </table>
        </section>
      )}

      <section>
        <h2 className="mb-4 text-lg font-bold text-label">Accounts</h2>
        {deleteError && <p className="mb-2 text-sm text-st-fehlt ">{deleteError}</p>}
        {isLoading ? (
          <p className="text-label2">Lädt…</p>
        ) : (
          <table className="w-full border border-sep bg-card text-left">
            <thead className="text-sm text-label2">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">E-Mail</th>
                <th className="px-4 py-3">Rolle</th>
                {isSuperAdmin && <th className="px-4 py-3">Mandant</th>}
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-sep text-sm">
              {users?.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-3 font-medium text-label">{u.name}</td>
                  <td className="px-4 py-3 text-label2">{u.email}</td>
                  <td className="px-4 py-3 text-label">
                    {u.role === "custom" ? u.account_typ_name ?? "Account-Typ" : ROLE_LABEL[u.role]}
                  </td>
                  {isSuperAdmin && (
                    <td className="px-4 py-3 text-label2">
                      {u.mandant_id ? mandantNameById.get(u.mandant_id) ?? "–" : "–"}
                    </td>
                  )}
                  <td className="px-4 py-3">
                    <span
                      className={`border px-2 py-0.5 text-xs font-semibold ${
                        u.aktiv
                          ? "border-st-erledigt text-st-erledigt "
                          : "border-sep text-label2"
                      }`}
                    >
                      {u.aktiv ? "Aktiv" : "Deaktiviert"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <div className="flex gap-2">
                      <button
                        onClick={() =>
                          toggleActiveMutation.mutate({ id: u.id, aktiv: !u.aktiv })
                        }
                        className="btn-touch btn-ap"
                      >
                        {u.aktiv ? "Deaktivieren" : "Aktivieren"}
                      </button>
                      <button
                        onClick={() => {
                          if (window.confirm(`${u.name} wirklich löschen? Das kann nicht rückgängig gemacht werden.`)) {
                            setDeleteError(null);
                            deleteMutation.mutate(u.id);
                          }
                        }}
                        disabled={u.id === currentUser?.id}
                        title={u.id === currentUser?.id ? "Eigener Account kann nicht gelöscht werden" : undefined}
                        className="btn-touch border border-st-fehlt px-3 py-2 text-xs font-semibold text-st-fehlt hover:bg-st-fehlt-bg disabled:cursor-not-allowed disabled:opacity-40 dark:hover:bg-st-fehlt-dot"
                      >
                        Löschen
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </div>
  );
}
