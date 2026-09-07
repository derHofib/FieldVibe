import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, ListChecks } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { kundenApi, leistungsverzeichnisApi, rechnungenApi } from "../../api/endpoints";
import type { RechnungPositionVorschlag } from "../../types";
import { EmailSection } from "../../components/EmailSection";
import { SearchableSelect } from "../../components/SearchableSelect";
import { useAuth } from "../../context/AuthContext";
import { RECHNUNG_STATUS_LABEL } from "../../utils/buchhaltung";
import { downloadBlob } from "../../utils/download";
import { heuteIso } from "../../utils/format";
import { openPdfBlob } from "../../utils/pdf";
import type { RechnungZahlungsart } from "../../types";

/** Vorschlagsbox fuer Rechnungen mit Vorgangsbezug -- fasst bereits am
 * Vorgang erfasstes Material und abrechenbare Zeiterfassung zusammen, die
 * der Nutzer gezielt als Positionen uebernimmt statt alles freihand
 * einzutippen. Reiner Vorschlag ohne Nebenwirkung, bis "Übernehmen"
 * gedrueckt wird -- legt dann ganz normal ueber addPosition echte
 * RechnungPosition-Zeilen an. */
function PositionsVorschlaege({ rechnungId, vorgangId }: { rechnungId: string; vorgangId: string }) {
  const queryClient = useQueryClient();
  const [ausgewaehlt, setAusgewaehlt] = useState<Set<number>>(new Set());

  const { data: vorschlaege } = useQuery({
    queryKey: ["rechnung-vorschlaege", rechnungId],
    queryFn: () => rechnungenApi.positionsvorschlaege(rechnungId),
  });

  const uebernehmenMutation = useMutation({
    mutationFn: async () => {
      const gewaehlte = (vorschlaege ?? []).filter((_, i) => ausgewaehlt.has(i));
      for (const v of gewaehlte) {
        await rechnungenApi.addPosition(rechnungId, {
          beschreibung: v.beschreibung,
          menge: v.menge,
          einheit: v.einheit,
          einzelpreis: v.einzelpreis,
        });
      }
    },
    onSuccess: () => {
      setAusgewaehlt(new Set());
      queryClient.invalidateQueries({ queryKey: ["rechnung", rechnungId] });
    },
  });

  const toggle = (i: number) =>
    setAusgewaehlt((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });

  if (!vorgangId || (vorschlaege && vorschlaege.length === 0)) return null;

  return (
    <div className="mb-3 rounded-lg border border-dashed border-cyan-200 bg-cyan-50/60 p-3 dark:border-cyan-500/30 dark:bg-cyan-500/10">
      <div className="mb-2 flex items-center gap-1.5">
        <ListChecks size={13} strokeWidth={2} className="text-cyan-700 dark:text-cyan-300" />
        <p className="text-xs font-bold text-cyan-800 dark:text-cyan-200">Vorschläge aus dem Vorgang</p>
      </div>
      <div className="space-y-1.5">
        {(vorschlaege ?? []).map((v: RechnungPositionVorschlag, i) => (
          <label key={i} className="flex items-center gap-2 rounded-md bg-white px-2 py-1.5 text-sm dark:bg-stone-900">
            <input
              type="checkbox"
              checked={ausgewaehlt.has(i)}
              onChange={() => toggle(i)}
              className="h-3.5 w-3.5"
            />
            <span className="flex-1 text-ind-ink">
              {v.beschreibung}, {v.menge} {v.einheit} × {v.einzelpreis} EUR
            </span>
            <span className="border border-ind-line px-2 py-0.5 text-[10px] font-semibold text-ind-ink-3">
              {v.quelle === "material" ? "Material" : v.quelle === "leistung" ? "Leistungsverzeichnis" : "Zeiterfassung"}
            </span>
          </label>
        ))}
      </div>
      <button
        disabled={ausgewaehlt.size === 0 || uebernehmenMutation.isPending}
        onClick={() => uebernehmenMutation.mutate()}
        className="btn-touch mt-2 rounded-md btn-industry btn-industry-primary px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
      >
        Übernehmen
      </button>
    </div>
  );
}

const ZAHLUNGSART_OPTIONEN: { value: RechnungZahlungsart; label: string }[] = [
  { value: "ueberweisung", label: "Überweisung" },
  { value: "bar", label: "Bar" },
  { value: "karte", label: "Karte" },
  { value: "lastschrift", label: "Lastschrift" },
  { value: "sonstiges", label: "Sonstiges" },
];

// id optional als Prop, damit die Office-Oberflaeche diese Seite in ihrem
// Detail-Panel einbetten kann, ohne dass es einen zweiten, parallel zu
// pflegenden Nachbau braucht. Ohne Prop verhaelt sie sich wie bisher.
export function RechnungDetailPage({ id: idProp }: { id?: string } = {}) {
  const { id: idParam } = useParams<{ id: string }>();
  const id = idProp ?? idParam;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { currentUser } = useAuth();
  const kannLoeschen = currentUser?.role === "loesch_operativ";
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ beschreibung: "", menge: "1", einheit: "Stk", einzelpreis: "0" });
  const [lvAuswahl, setLvAuswahl] = useState("");
  const [showZahlungForm, setShowZahlungForm] = useState(false);
  const [zahlungBetrag, setZahlungBetrag] = useState("");
  const [zahlungDatum, setZahlungDatum] = useState(heuteIso());
  const [zahlungsart, setZahlungsart] = useState<RechnungZahlungsart | "">("");

  const deleteMutation = useMutation({
    mutationFn: () => rechnungenApi.remove(id!),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
      navigate("/feed");
    },
  });

  const { data: rechnung } = useQuery({
    queryKey: ["rechnung", id],
    queryFn: () => rechnungenApi.get(id!),
    enabled: !!id,
  });
  const { data: kunde } = useQuery({
    queryKey: ["kunde", rechnung?.kunde_id],
    queryFn: () => kundenApi.get(rechnung!.kunde_id),
    enabled: !!rechnung,
  });
  const { data: leistungsverzeichnis } = useQuery({
    queryKey: ["leistungsverzeichnis", rechnung?.kunde_id],
    queryFn: () => leistungsverzeichnisApi.list(rechnung!.kunde_id),
    enabled: showForm && !!rechnung,
  });
  const { data: storniertRechnung } = useQuery({
    queryKey: ["rechnung", rechnung?.storniert_rechnung_id],
    queryFn: () => rechnungenApi.get(rechnung!.storniert_rechnung_id!),
    enabled: !!rechnung?.storniert_rechnung_id,
  });

  const statusMutation = useMutation({
    mutationFn: (status: string) => rechnungenApi.updateStatus(id!, status),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["rechnung", id] }),
  });

  const stornoMutation = useMutation({
    mutationFn: () => rechnungenApi.storno(id!),
    onSuccess: (storno) => {
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
      navigate(`/rechnungen/${storno.id}`);
    },
  });

  const addPositionMutation = useMutation({
    mutationFn: () =>
      rechnungenApi.addPosition(id!, {
        beschreibung: form.beschreibung,
        menge: form.menge,
        einheit: form.einheit,
        einzelpreis: form.einzelpreis,
      }),
    onSuccess: () => {
      setShowForm(false);
      setForm({ beschreibung: "", menge: "1", einheit: "Stk", einzelpreis: "0" });
      setLvAuswahl("");
      queryClient.invalidateQueries({ queryKey: ["rechnung", id] });
    },
  });

  const pdfMutation = useMutation({
    mutationFn: () => rechnungenApi.pdf(id!),
    onSuccess: openPdfBlob,
  });

  const xmlMutation = useMutation({
    mutationFn: () => rechnungenApi.xml(id!),
    onSuccess: (blob) => downloadBlob(blob, "factur-x.xml"),
  });

  const addZahlungMutation = useMutation({
    mutationFn: () =>
      rechnungenApi.addZahlung(id!, {
        betrag: zahlungBetrag,
        datum: zahlungDatum,
        zahlungsart: zahlungsart || undefined,
      }),
    onSuccess: () => {
      setShowZahlungForm(false);
      setZahlungBetrag("");
      setZahlungsart("");
      queryClient.invalidateQueries({ queryKey: ["rechnung", id] });
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
    },
  });

  const stornoZahlungMutation = useMutation({
    mutationFn: (zahlungId: string) => rechnungenApi.stornoZahlung(id!, zahlungId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["rechnung", id] });
      queryClient.invalidateQueries({ queryKey: ["rechnungen"] });
    },
  });

  if (!rechnung) return <p className="text-center text-ind-ink-3">Lädt…</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-ind-ink-3">
          ← Zurück
        </button>
        {kannLoeschen && (
          <button
            onClick={() => {
              if (window.confirm("Rechnung wirklich löschen? Sie wandert in den Papierkorb.")) {
                deleteMutation.mutate();
              }
            }}
            disabled={deleteMutation.isPending}
            className="btn-touch text-sm font-medium text-red-700 disabled:opacity-50 dark:text-red-400"
          >
            Rechnung löschen
          </button>
        )}
      </div>

      {rechnung.ist_storno && (
        <div className="rounded-lg bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
          Diese Rechnung storniert{" "}
          {storniertRechnung ? (
            <button
              onClick={() => navigate(`/rechnungen/${storniertRechnung.id}`)}
              className="btn-touch underline-offset-2 hover:underline"
            >
              {storniertRechnung.rechnungsnummer}
            </button>
          ) : (
            "eine andere Rechnung"
          )}
          .
        </div>
      )}

      {rechnung.xml_object_key && (
        <div className="rounded-lg bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300">
          ZUGFeRD-Rechnung — diese PDF enthält eine eingebettete E-Rechnungs-XML.
        </div>
      )}

      <div className="border border-ind-line bg-ind-bg p-4">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-ind-ink-3">{rechnung.rechnungsnummer}</div>
            <h1 className="text-lg font-bold text-ind-ink">{kunde?.name ?? "…"}</h1>
          </div>
          <span className="border border-ind-line px-2 py-1 text-xs font-semibold text-ind-ink-2">
            {RECHNUNG_STATUS_LABEL[rechnung.status]}
          </span>
        </div>
        {rechnung.leistungsdatum && (
          <p className="mt-1 text-xs text-ind-ink-3">
            Leistungsdatum {new Date(rechnung.leistungsdatum).toLocaleDateString("de-DE")}
          </p>
        )}
        {rechnung.faellig_am && (
          <p className="mt-1 text-xs text-ind-ink-3">
            Fällig am {new Date(rechnung.faellig_am).toLocaleDateString("de-DE")}
          </p>
        )}
        {rechnung.mahnstufe > 0 && (
          <p className="mt-1 text-xs font-semibold text-red-600 dark:text-red-400">
            {rechnung.mahnstufe}. Mahnung
            {rechnung.letzte_mahnung_am &&
              ` am ${new Date(rechnung.letzte_mahnung_am).toLocaleDateString("de-DE")}`}
          </p>
        )}

        <div className="mt-3 text-right text-sm">
          <div className="text-ind-ink-3">Netto: {rechnung.betrag_netto} EUR</div>
          <div className="font-semibold text-ind-ink">
            Brutto: {rechnung.betrag_brutto} EUR
          </div>
          {rechnung.status !== "entwurf" && rechnung.status !== "storniert" && (
            <div className="mt-1 text-xs text-ind-ink-3">
              Bezahlt: {rechnung.bezahlter_betrag} EUR · Offen: {rechnung.offener_betrag} EUR
            </div>
          )}
        </div>

        <div className="mt-3 flex items-center gap-2">
          <button
            onClick={() => pdfMutation.mutate()}
            disabled={pdfMutation.isPending}
            className="btn-touch flex items-center justify-center gap-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
          >
            <FileText size={14} strokeWidth={2} /> PDF anzeigen
          </button>
          {rechnung.xml_object_key && (
            <button
              onClick={() => xmlMutation.mutate()}
              disabled={xmlMutation.isPending}
              className="btn-touch flex items-center justify-center gap-1 rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
            >
              <FileText size={14} strokeWidth={2} /> XML herunterladen
            </button>
          )}
        </div>
      </div>

      <div className="border border-ind-line bg-ind-bg p-4">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-ind-ink-3">Positionen</h2>
          {rechnung.status === "entwurf" && (
            <button
              onClick={() => setShowForm((v) => !v)}
              className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
            >
              {showForm ? "Abbrechen" : "+ Position"}
            </button>
          )}
        </div>

        {rechnung.status === "entwurf" && rechnung.vorgang_id && (
          <PositionsVorschlaege rechnungId={id!} vorgangId={rechnung.vorgang_id} />
        )}

        {showForm && (
          <div className="mb-3 space-y-2 border border-ind-line-2 p-3">
            {(leistungsverzeichnis ?? []).length > 0 && (
              <div>
                <label className="mb-1 block text-xs font-medium text-ind-ink-2">
                  Aus Leistungsverzeichnis wählen (optional)
                </label>
                <SearchableSelect
                  value={lvAuswahl}
                  onChange={(v) => {
                    setLvAuswahl(v);
                    const position = (leistungsverzeichnis ?? []).find((p) => p.id === v);
                    if (position) {
                      setForm({
                        beschreibung: position.bezeichnung,
                        menge: "1",
                        einheit: position.einheit,
                        einzelpreis: position.einzelpreis,
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
            <input
              value={form.beschreibung}
              onChange={(e) => setForm({ ...form, beschreibung: e.target.value })}
              placeholder="Beschreibung"
              className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
            />
            <div className="grid grid-cols-3 gap-2">
              <input
                type="number"
                step="0.01"
                value={form.menge}
                onChange={(e) => setForm({ ...form, menge: e.target.value })}
                placeholder="Menge"
                className="border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
              <input
                value={form.einheit}
                onChange={(e) => setForm({ ...form, einheit: e.target.value })}
                placeholder="Einheit"
                className="border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
              <input
                type="number"
                step="0.01"
                value={form.einzelpreis}
                onChange={(e) => setForm({ ...form, einzelpreis: e.target.value })}
                placeholder="Preis"
                className="border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              />
            </div>
            <button
              disabled={!form.beschreibung || addPositionMutation.isPending}
              onClick={() => addPositionMutation.mutate()}
              className="btn-touch w-full rounded-md btn-industry btn-industry-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
            >
              Hinzufügen
            </button>
          </div>
        )}

        {rechnung.positionen.length === 0 ? (
          <p className="text-sm text-ind-ink-3">
            Keine eigenen Positionen -- Betrag wurde als Gesamtsumme angelegt.
          </p>
        ) : (
          <div className="space-y-1.5">
            {rechnung.positionen.map((p) => (
              <div
                key={p.id}
                className="flex items-center justify-between rounded-md bg-slate-50 p-2 text-sm dark:bg-stone-800/60"
              >
                <div>
                  <div className="text-ind-ink-2">{p.beschreibung}</div>
                  <div className="text-xs text-ind-ink-3">
                    {p.menge} {p.einheit} × {p.einzelpreis} EUR
                  </div>
                </div>
                <div className="font-medium text-ind-ink-2">{p.gesamt} EUR</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {(rechnung.status === "versendet" ||
        rechnung.status === "teilweise_bezahlt" ||
        rechnung.status === "bezahlt") && (
        <div className="border border-ind-line bg-ind-bg p-4">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-ind-ink-3">Zahlungen</h2>
            {(rechnung.status === "versendet" || rechnung.status === "teilweise_bezahlt") && (
              <button
                onClick={() => {
                  setZahlungBetrag(rechnung.offener_betrag);
                  setShowZahlungForm((v) => !v);
                }}
                className="btn-touch text-xs font-medium text-blue-700 dark:text-blue-400"
              >
                {showZahlungForm ? "Abbrechen" : "+ Zahlung"}
              </button>
            )}
          </div>

          {showZahlungForm && (
            <div className="mb-3 space-y-2 border border-ind-line-2 p-3">
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="number"
                  step="0.01"
                  value={zahlungBetrag}
                  onChange={(e) => setZahlungBetrag(e.target.value)}
                  placeholder="Betrag"
                  className="border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
                />
                <input
                  type="date"
                  value={zahlungDatum}
                  onChange={(e) => setZahlungDatum(e.target.value)}
                  max={heuteIso()}
                  className="border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
                />
              </div>
              <select
                value={zahlungsart}
                onChange={(e) => setZahlungsart(e.target.value as RechnungZahlungsart | "")}
                className="w-full border border-ind-line bg-transparent px-2 py-1.5 text-sm text-ind-ink"
              >
                <option value="">Zahlungsart (optional)</option>
                {ZAHLUNGSART_OPTIONEN.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
              {addZahlungMutation.isError && (
                <p className="text-xs text-red-600 dark:text-red-400">
                  Zahlung übersteigt den offenen Betrag oder ist ungültig.
                </p>
              )}
              <button
                disabled={!zahlungBetrag || addZahlungMutation.isPending}
                onClick={() => addZahlungMutation.mutate()}
                className="btn-touch w-full rounded-md btn-industry btn-industry-primary px-3 py-1.5 text-sm font-medium disabled:opacity-50"
              >
                Zahlung erfassen
              </button>
            </div>
          )}

          {rechnung.zahlungen.length === 0 ? (
            <p className="text-sm text-ind-ink-3">Noch keine Zahlung erfasst.</p>
          ) : (
            <div className="space-y-1.5">
              {(() => {
                const bereitsStorniert = new Set(
                  rechnung.zahlungen.map((z) => z.storniert_zahlung_id).filter((v): v is string => v !== null),
                );
                return rechnung.zahlungen.map((z) => (
                  <div
                    key={z.id}
                    className="flex items-center justify-between rounded-md bg-slate-50 p-2 text-sm dark:bg-stone-800/60"
                  >
                    <span className="text-ind-ink-3">
                      {new Date(z.datum).toLocaleDateString("de-DE")}
                      {z.zahlungsart && ` · ${z.zahlungsart}`}
                    </span>
                    <div className="flex items-center gap-2">
                      <span
                        className={`font-medium ${
                          Number(z.betrag) < 0
                            ? "text-red-600 dark:text-red-400"
                            : "text-ind-ink-2"
                        }`}
                      >
                        {z.betrag} EUR
                      </span>
                      {Number(z.betrag) > 0 && rechnung.status !== "storniert" && !bereitsStorniert.has(z.id) && (
                        <button
                          onClick={() => {
                            if (window.confirm("Diese Zahlung stornieren?")) stornoZahlungMutation.mutate(z.id);
                          }}
                          disabled={stornoZahlungMutation.isPending}
                          className="btn-touch text-xs text-slate-400 underline-offset-2 hover:underline disabled:opacity-50 dark:text-stone-500"
                        >
                          Storno
                        </button>
                      )}
                    </div>
                  </div>
                ));
              })()}
            </div>
          )}
        </div>
      )}

      <EmailSection
        queryKey={["rechnung-emails", id]}
        listEmails={() => rechnungenApi.emails(id!)}
        sendEmail={(body) => rechnungenApi.sendEmail(id!, body)}
        defaultEmpfaenger={kunde?.ansprechpartner.find((a) => a.email)?.email ?? undefined}
        betreffPflicht={false}
        hinweis="Die Rechnung wird als PDF-Anhang mitgesendet."
      />

      {rechnung.status === "entwurf" && (
        <div className="flex gap-2">
          <button
            onClick={() => statusMutation.mutate("versendet")}
            disabled={statusMutation.isPending}
            className="btn-touch flex-1 rounded-md btn-industry btn-industry-primary px-4 py-2 text-sm font-medium disabled:opacity-50"
          >
            An Kunden senden
          </button>
          <button
            onClick={() => statusMutation.mutate("storniert")}
            disabled={statusMutation.isPending}
            className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
          >
            Stornieren
          </button>
        </div>
      )}
      {(rechnung.status === "versendet" || rechnung.status === "teilweise_bezahlt") && (
        <div className="flex gap-2">
          <button
            onClick={() => statusMutation.mutate("bezahlt")}
            disabled={statusMutation.isPending}
            className="btn-touch flex-1 rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Als bezahlt markieren
          </button>
          <button
            onClick={() => {
              if (window.confirm("Diese Rechnung stornieren? Es wird eine Stornorechnung mit eigener Nummer erzeugt."))
                stornoMutation.mutate();
            }}
            disabled={stornoMutation.isPending}
            className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
          >
            Stornieren
          </button>
        </div>
      )}
      {rechnung.status === "bezahlt" && !rechnung.ist_storno && (
        <button
          onClick={() => {
            if (window.confirm("Diese bereits bezahlte Rechnung stornieren? Es wird eine Stornorechnung mit eigener Nummer erzeugt."))
              stornoMutation.mutate();
          }}
          disabled={stornoMutation.isPending}
          className="btn-touch w-full rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-50 dark:bg-stone-800 dark:text-stone-300"
        >
          Stornieren
        </button>
      )}
    </div>
  );
}
