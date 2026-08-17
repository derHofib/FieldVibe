import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { kundenApi, rechnungenApi } from "../../api/endpoints";
import { EmailSection } from "../../components/EmailSection";
import { useAuth } from "../../context/AuthContext";
import { RECHNUNG_STATUS_LABEL } from "../../utils/buchhaltung";
import { downloadBlob } from "../../utils/download";
import { heuteIso } from "../../utils/format";
import { openPdfBlob } from "../../utils/pdf";
import type { RechnungZahlungsart } from "../../types";

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

  if (!rechnung) return <p className="text-center text-slate-500 dark:text-stone-400">Lädt…</p>;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate(-1)} className="text-sm text-slate-500 dark:text-stone-400">
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

      <div className="rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="flex items-start justify-between">
          <div>
            <div className="text-xs text-slate-400 dark:text-stone-500">{rechnung.rechnungsnummer}</div>
            <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">{kunde?.name ?? "…"}</h1>
          </div>
          <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-stone-800 dark:text-stone-300">
            {RECHNUNG_STATUS_LABEL[rechnung.status]}
          </span>
        </div>
        {rechnung.leistungsdatum && (
          <p className="mt-1 text-xs text-slate-500 dark:text-stone-400">
            Leistungsdatum {new Date(rechnung.leistungsdatum).toLocaleDateString("de-DE")}
          </p>
        )}
        {rechnung.faellig_am && (
          <p className="mt-1 text-xs text-slate-500 dark:text-stone-400">
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
          <div className="text-slate-500 dark:text-stone-400">Netto: {rechnung.betrag_netto} EUR</div>
          <div className="font-semibold text-slate-800 dark:text-stone-100">
            Brutto: {rechnung.betrag_brutto} EUR
          </div>
          {rechnung.status !== "entwurf" && rechnung.status !== "storniert" && (
            <div className="mt-1 text-xs text-slate-500 dark:text-stone-400">
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

      <div className="rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Positionen</h2>
          {rechnung.status === "entwurf" && (
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

        {rechnung.positionen.length === 0 ? (
          <p className="text-sm text-slate-400 dark:text-stone-500">
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
                  <div className="text-slate-700 dark:text-stone-300">{p.beschreibung}</div>
                  <div className="text-xs text-slate-400 dark:text-stone-500">
                    {p.menge} {p.einheit} × {p.einzelpreis} EUR
                  </div>
                </div>
                <div className="font-medium text-slate-700 dark:text-stone-300">{p.gesamt} EUR</div>
              </div>
            ))}
          </div>
        )}
      </div>

      {(rechnung.status === "versendet" ||
        rechnung.status === "teilweise_bezahlt" ||
        rechnung.status === "bezahlt") && (
        <div className="rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <div className="mb-2 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-slate-500 dark:text-stone-400">Zahlungen</h2>
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
            <div className="mb-3 space-y-2 rounded-md bg-slate-50 p-3 dark:bg-stone-800/60">
              <div className="grid grid-cols-2 gap-2">
                <input
                  type="number"
                  step="0.01"
                  value={zahlungBetrag}
                  onChange={(e) => setZahlungBetrag(e.target.value)}
                  placeholder="Betrag"
                  className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                />
                <input
                  type="date"
                  value={zahlungDatum}
                  onChange={(e) => setZahlungDatum(e.target.value)}
                  max={heuteIso()}
                  className="rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
                />
              </div>
              <select
                value={zahlungsart}
                onChange={(e) => setZahlungsart(e.target.value as RechnungZahlungsart | "")}
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
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
                className="btn-touch w-full rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
              >
                Zahlung erfassen
              </button>
            </div>
          )}

          {rechnung.zahlungen.length === 0 ? (
            <p className="text-sm text-slate-400 dark:text-stone-500">Noch keine Zahlung erfasst.</p>
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
                    <span className="text-slate-500 dark:text-stone-400">
                      {new Date(z.datum).toLocaleDateString("de-DE")}
                      {z.zahlungsart && ` · ${z.zahlungsart}`}
                    </span>
                    <div className="flex items-center gap-2">
                      <span
                        className={`font-medium ${
                          Number(z.betrag) < 0
                            ? "text-red-600 dark:text-red-400"
                            : "text-slate-700 dark:text-stone-300"
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
            className="btn-touch flex-1 rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
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
