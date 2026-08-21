import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { angeboteApi, kundenApi, leistungsverzeichnisApi } from "../../api/endpoints";
import { EmailSection } from "../../components/EmailSection";
import { SearchableSelect } from "../../components/SearchableSelect";
import { useAuth } from "../../context/AuthContext";
import { openPdfBlob } from "../../utils/pdf";
import type { AngebotPositionstyp, AngebotStatus } from "../../types";

const STATUS_LABEL: Record<AngebotStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

const POSITIONSTYP_LABEL: Record<AngebotPositionstyp, string> = {
  material: "Material",
  arbeitszeit: "Arbeitszeit",
};

interface NeuePosition {
  artikelnummer: string;
  beschreibung: string;
  menge: string;
  einheit: string;
  einzelpreis: string;
  positionstyp: AngebotPositionstyp;
}

// id optional als Prop, damit die Office-Oberflaeche diese Seite in ihrem
// Detail-Panel einbetten kann, ohne dass es einen zweiten, parallel zu
// pflegenden Nachbau braucht. Ohne Prop verhaelt sie sich wie bisher.
export function AngebotDetailPage({ id: idProp }: { id?: string } = {}) {
  const { id: idParam } = useParams<{ id: string }>();
  const id = idProp ?? idParam;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const kannLoeschen = currentUser?.role === "loesch_operativ";
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState<NeuePosition>({
    artikelnummer: "",
    beschreibung: "",
    menge: "1",
    einheit: "Stk",
    einzelpreis: "0",
    positionstyp: "material",
  });
  const [lvAuswahl, setLvAuswahl] = useState("");

  const deleteMutation = useMutation({
    mutationFn: () => angeboteApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["angebote"] });
      navigate("/feed");
    },
  });

  const { data: angebot } = useQuery({
    queryKey: ["angebot", id],
    queryFn: () => angeboteApi.get(id!),
    enabled: !!id,
  });
  const { data: kunde } = useQuery({
    queryKey: ["kunde", angebot?.kunde_id],
    queryFn: () => kundenApi.get(angebot!.kunde_id),
    enabled: !!angebot,
  });
  const { data: leistungsverzeichnis } = useQuery({
    queryKey: ["leistungsverzeichnis", angebot?.kunde_id],
    queryFn: () => leistungsverzeichnisApi.list(angebot!.kunde_id),
    enabled: showForm && !!angebot,
  });

  const addPositionMutation = useMutation({
    mutationFn: () =>
      angeboteApi.addPosition(id!, {
        artikelnummer: form.artikelnummer || undefined,
        beschreibung: form.beschreibung,
        menge: form.menge,
        einheit: form.einheit,
        einzelpreis: form.einzelpreis,
        positionstyp: form.positionstyp,
      }),
    onSuccess: () => {
      setShowForm(false);
      setForm({
        artikelnummer: "",
        beschreibung: "",
        menge: "1",
        einheit: "Stk",
        einzelpreis: "0",
        positionstyp: "material",
      });
      setLvAuswahl("");
      queryClient.invalidateQueries({ queryKey: ["angebot", id] });
    },
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) => angeboteApi.updateStatus(id!, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["angebot", id] }),
  });

  const pdfMutation = useMutation({
    mutationFn: () => angeboteApi.pdf(id!),
    onSuccess: openPdfBlob,
  });

  if (!angebot) return <p className="text-center text-slate-500 dark:text-stone-400">Lädt…</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-stone-400">
          ← Zurück
        </button>
        {kannLoeschen && (
          <button
            onClick={() => {
              if (window.confirm("Angebot wirklich löschen? Es wandert in den Papierkorb.")) {
                deleteMutation.mutate();
              }
            }}
            disabled={deleteMutation.isPending}
            className="btn-touch text-sm font-medium text-red-700 disabled:opacity-50 dark:text-red-400"
          >
            Angebot löschen
          </button>
        )}
      </div>

      <div className="rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-slate-400 dark:text-stone-500">{angebot.angebotsnummer}</div>
            <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">{kunde?.name ?? "…"}</h1>
          </div>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-stone-800 dark:text-stone-300">
            {STATUS_LABEL[angebot.status]}
          </span>
        </div>
        {angebot.gueltig_bis && (
          <p className="mt-1 text-xs text-slate-500 dark:text-stone-400">
            Gültig bis {new Date(angebot.gueltig_bis).toLocaleDateString("de-DE")}
          </p>
        )}
        <button
          onClick={() => pdfMutation.mutate()}
          disabled={pdfMutation.isPending}
          className="btn-touch mt-3 flex items-center justify-center gap-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
        >
          <FileText size={14} strokeWidth={2} /> PDF anzeigen
        </button>
      </div>

      <div className="rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Positionen</h2>
          {angebot.status === "entwurf" && (
            <button
              onClick={() => setShowForm((v) => !v)}
              className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
            >
              {showForm ? "Abbrechen" : "+ Position"}
            </button>
          )}
        </div>

        {showForm && (
          <div className="mb-3 space-y-2 rounded-md bg-slate-50 p-3 dark:bg-stone-800/60">
            {(leistungsverzeichnis ?? []).length > 0 && (
              <div>
                <label className="mb-1 block text-xs font-medium text-slate-600 dark:text-stone-400">
                  Aus Leistungsverzeichnis wählen (optional)
                </label>
                <SearchableSelect
                  value={lvAuswahl}
                  onChange={(v) => {
                    setLvAuswahl(v);
                    const position = (leistungsverzeichnis ?? []).find((p) => p.id === v);
                    if (position) {
                      setForm({
                        ...form,
                        beschreibung: position.bezeichnung,
                        menge: "1",
                        einheit: position.einheit,
                        einzelpreis: position.einzelpreis,
                        positionstyp: position.ist_stundensatz ? "arbeitszeit" : "material",
                      });
                    }
                  }}
                  placeholder="Position wählen…"
                  options={(leistungsverzeichnis ?? []).map((p) => ({
                    value: p.id,
                    label: p.bezeichnung,
                    sublabel: `${p.einzelpreis} €/${p.einheit}`,
                  }))}
                />
              </div>
            )}
            <div className="flex gap-1.5">
              {(["material", "arbeitszeit"] as AngebotPositionstyp[]).map((typ) => (
                <button
                  key={typ}
                  type="button"
                  onClick={() => setForm({ ...form, positionstyp: typ })}
                  className={`btn-touch rounded-md px-3 py-1.5 text-xs font-medium ${
                    form.positionstyp === typ
                      ? "bg-blue-600 text-white"
                      : "bg-white text-slate-600 ring-1 ring-slate-300 dark:bg-stone-800 dark:text-stone-300 dark:ring-stone-700"
                  }`}
                >
                  {POSITIONSTYP_LABEL[typ]}
                </button>
              ))}
            </div>
            <input
              value={form.artikelnummer}
              onChange={(e) => setForm({ ...form, artikelnummer: e.target.value })}
              placeholder="Art-Nr. (optional)"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <input
              value={form.beschreibung}
              onChange={(e) => setForm({ ...form, beschreibung: e.target.value })}
              placeholder="Beschreibung"
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
            />
            <div className="grid grid-cols-3 gap-2">
              <input
                type="number"
                step="0.01"
                value={form.menge}
                onChange={(e) => setForm({ ...form, menge: e.target.value })}
                placeholder="Menge"
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
              <input
                value={form.einheit}
                onChange={(e) => setForm({ ...form, einheit: e.target.value })}
                placeholder="Einheit"
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
              <input
                type="number"
                step="0.01"
                value={form.einzelpreis}
                onChange={(e) => setForm({ ...form, einzelpreis: e.target.value })}
                placeholder="Preis"
                className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
              />
            </div>
            <button
              disabled={!form.beschreibung || addPositionMutation.isPending}
              onClick={() => addPositionMutation.mutate()}
              className="btn-touch w-full rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
            >
              Hinzufügen
            </button>
          </div>
        )}

        {angebot.positionen.length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-stone-500">Noch keine Positionen.</p>
        ) : (
          <div className="space-y-1.5">
            {angebot.positionen.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-md bg-slate-50 p-2 text-sm dark:bg-stone-800/60"
              >
                <div>
                  <div className="text-slate-700 dark:text-stone-300">
                    {p.positionstyp === "arbeitszeit" && (
                      <span className="mr-1.5 rounded-full bg-amber-100 px-1.5 py-0.5 text-xs text-amber-700 dark:bg-amber-500/15 dark:text-amber-300">
                        {POSITIONSTYP_LABEL.arbeitszeit}
                      </span>
                    )}
                    {p.artikelnummer && (
                      <span className="mr-1.5 text-xs text-slate-400 dark:text-stone-500">{p.artikelnummer}</span>
                    )}
                    {p.beschreibung}
                  </div>
                  <div className="text-xs text-slate-400 dark:text-stone-500">
                    {p.menge} {p.einheit} × {p.einzelpreis} EUR
                  </div>
                </div>
                <div className="font-medium text-slate-700 dark:text-stone-300">{p.gesamt} EUR</div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-3 border-t border-slate-100 pt-2 text-right text-sm dark:border-stone-800">
          <div className="text-slate-500 dark:text-stone-400">Netto: {angebot.gesamt_netto} EUR</div>
          <div className="font-semibold text-slate-800 dark:text-stone-100">
            Brutto: {angebot.gesamt_brutto} EUR
          </div>
        </div>
      </div>

      <EmailSection
        queryKey={["angebot-emails", id]}
        listEmails={() => angeboteApi.emails(id!)}
        sendEmail={(body) => angeboteApi.sendEmail(id!, body)}
        defaultEmpfaenger={kunde?.ansprechpartner.find((a) => a.email)?.email ?? undefined}
        betreffPflicht={false}
        hinweis="Das Angebot wird als PDF-Anhang mitgesendet."
      />

      {angebot.status === "entwurf" && (
        <button
          onClick={() => statusMutation.mutate("versendet")}
          disabled={statusMutation.isPending}
          className="btn-touch w-full rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          An Kunden senden
        </button>
      )}
      {angebot.status === "versendet" && (
        <div className="flex gap-2">
          <button
            onClick={() => statusMutation.mutate("angenommen")}
            disabled={statusMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Angenommen
          </button>
          <button
            onClick={() => statusMutation.mutate("abgelehnt")}
            disabled={statusMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-red-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Abgelehnt
          </button>
        </div>
      )}
      {angebot.status === "angenommen" && (
        <p className="text-center text-sm text-green-700 dark:text-green-400">
          Angebot angenommen – ein Reparatur-Vorgang wurde automatisch angelegt (siehe verknüpfte Mängel).
        </p>
      )}
    </div>
  );
}
