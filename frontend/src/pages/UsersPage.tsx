import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { mandantenApi, usersApi } from "../api/endpoints";
import { useAuth } from "../context/AuthContext";
import { ApiError } from "../api/client";
import type { Role } from "../types";

export const ROLE_LABEL: Record<Role, string> = {
  super_admin: "Super-Admin",
  mandant_admin: "Mandanten-Admin",
  disponent: "Disponent",
  techniker: "Techniker",
  controller: "Controller",
  mitarbeiter: "Mitarbeiter",
  loesch_ansicht: "Papierkorb (nur Ansicht)",
  loesch_operativ: "Papierkorb (operativ)",
};

// Nur super_admin darf diese Rollen vergeben (siehe app/api/routes/users.py) --
// ein mandant_admin sieht sie im Anlage-Dropdown gar nicht erst.
const SUPER_ADMIN_ONLY_ROLES: Role[] = ["super_admin", "loesch_ansicht", "loesch_operativ"];

export function UsersPage() {
  const { currentUser } = useAuth();
  const queryClient = useQueryClient();
  const isSuperAdmin = currentUser?.role === "super_admin";

  const [formError, setFormError] = useState<string | null>(null);
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<Role>("techniker");
  const [mandantId, setMandantId] = useState<string>("");

  const { data: users, isLoading } = useQuery({ queryKey: ["users"], queryFn: usersApi.list });
  const { data: mandanten } = useQuery({
    queryKey: ["mandanten"],
    queryFn: mandantenApi.list,
    enabled: isSuperAdmin,
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

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    setFormError(null);
    const effectiveMandantId = isSuperAdmin ? mandantId || null : currentUser?.mandant_id ?? null;
    if (role !== "super_admin" && !effectiveMandantId) {
      setFormError("Bitte einen Mandanten auswählen");
      return;
    }
    createMutation.mutate({
      mandant_id: role === "super_admin" ? null : effectiveMandantId,
      email,
      password,
      role,
      name,
    });
  }

  const mandantNameById = new Map((mandanten ?? []).map((m) => [m.id, m.name]));

  return (
    <div className="space-y-8">
      {currentUser?.role === "mandant_admin" && (
        <div className="flex justify-end">
          <Link
            to="/rechte-matrix"
            className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-200"
          >
            Rechte für Controller/Mitarbeiter einstellen →
          </Link>
        </div>
      )}
      <section>
        <h2 className="mb-4 text-lg font-bold text-slate-800">Neuen Account anlegen</h2>
        <form onSubmit={handleCreate} className="flex flex-wrap items-end gap-3">
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="btn-touch rounded-md border border-slate-300 px-3 py-2"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">E-Mail</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="btn-touch rounded-md border border-slate-300 px-3 py-2"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Passwort</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="btn-touch rounded-md border border-slate-300 px-3 py-2"
            />
          </div>
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Rolle</label>
            <select
              value={role}
              onChange={(e) => setRole(e.target.value as Role)}
              className="btn-touch rounded-md border border-slate-300 px-3 py-2"
            >
              {Object.entries(ROLE_LABEL)
                .filter(
                  ([value]) => isSuperAdmin || !SUPER_ADMIN_ONLY_ROLES.includes(value as Role),
                )
                .map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
            </select>
          </div>
          {isSuperAdmin && role !== "super_admin" && (
            <div>
              <label className="mb-1 block text-sm font-medium text-slate-700">Mandant</label>
              <select
                required
                value={mandantId}
                onChange={(e) => setMandantId(e.target.value)}
                className="btn-touch rounded-md border border-slate-300 px-3 py-2"
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
            disabled={createMutation.isPending}
            className="btn-touch rounded-md bg-slate-900 px-4 py-2 font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            Anlegen
          </button>
        </form>
        {formError && <p className="mt-2 text-sm text-red-700">{formError}</p>}
      </section>

      <section>
        <h2 className="mb-4 text-lg font-bold text-slate-800">Accounts</h2>
        {deleteError && <p className="mb-2 text-sm text-red-700">{deleteError}</p>}
        {isLoading ? (
          <p>Lädt…</p>
        ) : (
          <table className="w-full overflow-hidden rounded-lg bg-white text-left shadow-sm">
            <thead className="bg-slate-50 text-sm text-slate-600">
              <tr>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3">E-Mail</th>
                <th className="px-4 py-3">Rolle</th>
                {isSuperAdmin && <th className="px-4 py-3">Mandant</th>}
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Aktion</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm">
              {users?.map((u) => (
                <tr key={u.id}>
                  <td className="px-4 py-3 font-medium">{u.name}</td>
                  <td className="px-4 py-3 text-slate-500">{u.email}</td>
                  <td className="px-4 py-3">{ROLE_LABEL[u.role]}</td>
                  {isSuperAdmin && (
                    <td className="px-4 py-3 text-slate-500">
                      {u.mandant_id ? mandantNameById.get(u.mandant_id) ?? "–" : "–"}
                    </td>
                  )}
                  <td className="px-4 py-3">
                    <span
                      className={`rounded-full px-3 py-1 text-xs font-semibold ${
                        u.aktiv ? "bg-green-100 text-green-800" : "bg-slate-200 text-slate-600"
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
                        className="btn-touch rounded-md bg-slate-100 px-3 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-200"
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
                        className="btn-touch rounded-md bg-red-50 px-3 py-2 text-xs font-semibold text-red-700 hover:bg-red-100 disabled:cursor-not-allowed disabled:opacity-40"
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
