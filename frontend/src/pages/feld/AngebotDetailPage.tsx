import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Ban, FileText } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { angeboteApi, kundenApi, leistungsverzeichnisApi } from "../../api/endpoints";
import { EmailSection } from "../../components/EmailSection";
import { EmptyState } from "../../components/EmptyState";
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
  const [lvSplitMenge, setLvSplitMenge] = useState("1");

  const deleteMutation = useMutation({
    mutationFn: () => angeboteApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["angebote"] });
      navigate("/feed");
    },
  });

  const {
    data: angebot,
    isError: angebotIstFehler,
    error: angebotFehler,
  } = useQuery({
    queryKey: ["angebot", id],
    queryFn: () => angeboteApi.get(id!),
    enabled: !!id,
    retry: false,
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

  const lvPosition = (leistungsverzeichnis ?? []).find((p) => p.id === lvAuswahl);
  // Eine LV-Position mit Kalkulation (Modus "berechnet" oder mit
  // Unterpunkten) hat lohn_gesamt/material_gesamt > 0 -- dann wird sie als
  // zwei Angebotspositionen (Lohn/Material) uebernommen statt als eine
  // manuell ausgefuellte, siehe Ausarbeitung "Leistungsverzeichnis als
  // Kalkulator".
  const lvHatSplit =
    !!lvPosition && (Number(lvPosition.lohn_gesamt) > 0 || Number(lvPosition.material_gesamt) > 0);

  const addSplitPositionenMutation = useMutation({
    mutationFn: async () => {
      if (Number(lvPosition!.lohn_gesamt) > 0) {
        await angeboteApi.addPosition(id!, {
          beschreibung: `${lvPosition!.bezeichnung} – Lohn`,
          menge: lvSplitMenge,
          einheit: lvPosition!.einheit,
          einzelpreis: lvPosition!.lohn_gesamt,
          positionstyp: "arbeitszeit",
        });
      }
      if (Number(lvPosition!.material_gesamt) > 0) {
        await angeboteApi.addPosition(id!, {
          beschreibung: `${lvPosition!.bezeichnung} – Material`,
          menge: lvSplitMenge,
          einheit: lvPosition!.einheit,
          einzelpreis: lvPosition!.material_gesamt,
          positionstyp: "material",
        });
      }
    },
    onSuccess: () => {
      setShowForm(false);
      setLvAuswahl("");
      setLvSplitMenge("1");
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

  if (angebotIstFehler) {
    return (
      <div className="space-y-4">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
          ← Zurück
        </button>
        <EmptyState
          icon={Ban}
          text={
            angebotFehler instanceof ApiError && angebotFehler.status === 404
              ? "Angebot nicht gefunden oder kein Zugriff."
              : "Angebot konnte nicht geladen werden."
          }
        />
      </div>
    );
  }
  if (!angebot) return <p className="text-center text-label2">Lädt…</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-label2">
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
            className="btn-touch text-sm font-medium text-st-fehlt disabled:opacity-50 "
          >
            Angebot löschen
          </button>
        )}
      </div>

      <div className="border border-sep bg-card p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-label2">{angebot.angebotsnummer}</div>
            <h1 className="text-lg font-bold text-label">{kunde?.name ?? "…"}</h1>
          </div>
          <span className="border border-sep px-2 py-1 text-xs font-semibold text-label">
            {STATUS_LABEL[angebot.status]}
          </span>
        </div>
        {angebot.gueltig_bis && (
          <p className="mt-1 text-xs text-label2">
            Gültig bis {new Date(angebot.gueltig_bis).toLocaleDateString("de-DE")}
          </p>
        )}
        <button
          onClick={() => pdfMutation.mutate()}
          disabled={pdfMutation.isPending}
          className="btn-touch mt-3 flex items-center justify-center gap-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-label disabled:opacity-50 dark:bg-stone-800 "
        >
          <FileText size={14} strokeWidth={2} /> PDF anzeigen
        </button>
      </div>

      <div className="border border-sep bg-card p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-label2">Positionen</h2>
          {angebot.status === "entwurf" && (
            <button
              onClick={() => setShowForm((v) => !v)}
              className="btn-touch text-xs font-medium text-tint "
            >
              {showForm ? "Abbrechen" : "+ Position"}
            </button>
          )}
        </div>

        {showForm && (
          <div className="mb-3 space-y-2 border border-sepstrong p-3">
            {(leistungsverzeichnis ?? []).length > 0 && (
              <div>
                <label className="mb-1 block text-xs font-medium text-label">
                  Aus Leistungsverzeichnis wählen (optional)
                </label>
                <SearchableSelect
                  value={lvAuswahl}
                  onChange={(v) => {
                    setLvAuswahl(v);
                    setLvSplitMenge("1");
                    const position = (leistungsverzeichnis ?? []).find((p) => p.id === v);
                    const hatSplit =
                      position && (Number(position.lohn_gesamt) > 0 || Number(position.material_gesamt) > 0);
                    if (position && !hatSplit) {
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

            {lvHatSplit ? (
              <div className="space-y-2">
                <p className="text-xs text-label2">
                  Wird als zwei Positionen übernommen:{" "}
                  {Number(lvPosition!.lohn_gesamt) > 0 && (
                    <>
                      Lohn <strong className="text-label">{lvPosition!.lohn_gesamt} €</strong>
                    </>
                  )}
                  {Number(lvPosition!.lohn_gesamt) > 0 && Number(lvPosition!.material_gesamt) > 0 && ", "}
                  {Number(lvPosition!.material_gesamt) > 0 && (
                    <>
                      Material{" "}
                      <strong className="text-label">{lvPosition!.material_gesamt} €</strong>
                    </>
                  )}{" "}
                  (je {lvPosition!.einheit}).
                </p>
                <div>
                  <label className="mb-1 block text-xs font-medium text-label">
                    Menge ({lvPosition!.einheit})
                  </label>
                  <input
                    type="number"
                    step="0.01"
                    value={lvSplitMenge}
                    onChange={(e) => setLvSplitMenge(e.target.value)}
                    className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
                  />
                </div>
                <button
                  disabled={!lvSplitMenge || addSplitPositionenMutation.isPending}
                  onClick={() => addSplitPositionenMutation.mutate()}
                  className="btn-touch w-full rounded-md btn-ap-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
                >
                  Hinzufügen
                </button>
              </div>
            ) : (
              <>
            <div className="flex gap-1.5">
              {(["material", "arbeitszeit"] as AngebotPositionstyp[]).map((typ) => (
                <button
                  key={typ}
                  type="button"
                  onClick={() => setForm({ ...form, positionstyp: typ })}
                  className={`btn-touch rounded-md px-3 py-1.5 text-xs font-medium ${
                    form.positionstyp === typ
                      ? "bg-tint text-white"
                      : "bg-white text-label ring-1 ring-sep dark:bg-stone-800 "
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
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            <input
              value={form.beschreibung}
              onChange={(e) => setForm({ ...form, beschreibung: e.target.value })}
              placeholder="Beschreibung"
              className="w-full border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
            />
            <div className="grid grid-cols-3 gap-2">
              <input
                type="number"
                step="0.01"
                value={form.menge}
                onChange={(e) => setForm({ ...form, menge: e.target.value })}
                placeholder="Menge"
                className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <input
                value={form.einheit}
                onChange={(e) => setForm({ ...form, einheit: e.target.value })}
                placeholder="Einheit"
                className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
              <input
                type="number"
                step="0.01"
                value={form.einzelpreis}
                onChange={(e) => setForm({ ...form, einzelpreis: e.target.value })}
                placeholder="Preis"
                className="border border-sep bg-transparent px-2 py-1.5 text-sm text-label"
              />
            </div>
            <button
              disabled={!form.beschreibung || addPositionMutation.isPending}
              onClick={() => addPositionMutation.mutate()}
              className="btn-touch w-full rounded-md btn-ap-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Hinzufügen
            </button>
              </>
            )}
          </div>
        )}

        {angebot.positionen.length === 0 ? (
          <p className="text-sm text-label2">Noch keine Positionen.</p>
        ) : (
          <div className="space-y-1.5">
            {angebot.positionen.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-md bg-slate-50 p-2 text-sm dark:bg-stone-800/60"
              >
                <div>
                  <div className="text-label">
                    {p.positionstyp === "arbeitszeit" && (
                      <span className="mr-1.5 border border-st-arbeit px-1.5 py-0.5 text-xs text-st-arbeit ">
                        {POSITIONSTYP_LABEL.arbeitszeit}
                      </span>
                    )}
                    {p.artikelnummer && (
                      <span className="mr-1.5 text-xs text-label2">{p.artikelnummer}</span>
                    )}
                    {p.beschreibung}
                  </div>
                  <div className="text-xs text-label2">
                    {p.menge} {p.einheit} × {p.einzelpreis} EUR
                  </div>
                </div>
                <div className="font-medium text-label">{p.gesamt} EUR</div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-3 border-t border-sep pt-2 text-right text-sm ">
          <div className="text-label2">Netto: {angebot.gesamt_netto} EUR</div>
          <div className="font-semibold text-label">
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
          className="btn-touch w-full rounded-md btn-ap-primary px-4 py-2 text-sm font-medium disabled:opacity-50"
        >
          An Kunden senden
        </button>
      )}
      {angebot.status === "versendet" && (
        <div className="flex gap-2">
          <button
            onClick={() => statusMutation.mutate("angenommen")}
            disabled={statusMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-st-erledigt-dot px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Angenommen
          </button>
          <button
            onClick={() => statusMutation.mutate("abgelehnt")}
            disabled={statusMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-st-fehlt-dot px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Abgelehnt
          </button>
        </div>
      )}
      {angebot.status === "angenommen" && (
        <p className="text-center text-sm text-st-erledigt ">
          Angebot angenommen – ein Reparatur-Vorgang wurde automatisch angelegt (siehe verknüpfte Mängel).
        </p>
      )}
    </div>
  );
}
