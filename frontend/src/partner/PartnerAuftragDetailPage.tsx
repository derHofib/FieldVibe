import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, Send } from "lucide-react";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";

import { ApiError } from "../api/client";
import { partnerPortalApi } from "../api/endpoints";
import { AbschnittskopfB } from "../components/apple/AbschnittsKopf";
import { GroupedList, GroupedListValueRow } from "../components/apple/GroupedList";
import { Sheet } from "../components/apple/Sheet";
import { StatusPille } from "../components/apple/StatusPille";
import { LEISTUNGSTYP_LABEL } from "../config/vorgangDarstellung";
import { SkeletonList } from "../components/Skeleton";
import type { Adresse, PartnerStatusSetzbar, PartnerVorgang, VorgangEvent } from "../types";
import { formatDatum, formatEuro } from "../utils/format";
import { auftragsPille, istBearbeitbar } from "./partnerStatus";

function adresseAlsZeile(adresse: Adresse | null | undefined): string {
  return [adresse?.strasse, [adresse?.plz, adresse?.ort].filter(Boolean).join(" ")].filter(Boolean).join(", ");
}

const STATUS_AKTIONEN: { status: PartnerStatusSetzbar; label: string }[] = [
  { status: "in_arbeit", label: "In Arbeit" },
  { status: "wartet_kunde", label: "Wartet auf Kunde" },
];

export function PartnerAuftragDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [fehler, setFehler] = useState<string | null>(null);
  const [ablehnenOffen, setAblehnenOffen] = useState(false);
  const [grund, setGrund] = useState("");
  const [abschliessenOffen, setAbschliessenOffen] = useState(false);
  const [kommentar, setKommentar] = useState("");
  // Das Partner-API hat keinen Lese-Endpunkt fuer den Verlauf -- hier stehen
  // nur die in dieser Sitzung gesendeten Kommentare.
  const [gesendet, setGesendet] = useState<VorgangEvent[]>([]);

  const { data: auftrag, isLoading, error } = useQuery({
    queryKey: ["partnerportal-auftrag", id],
    queryFn: () => partnerPortalApi.auftrag(id),
    enabled: !!id,
  });

  function uebernehmen(neu: PartnerVorgang) {
    queryClient.setQueryData(["partnerportal-auftrag", id], neu);
    void queryClient.invalidateQueries({ queryKey: ["partnerportal-auftraege"] });
    void queryClient.invalidateQueries({ queryKey: ["partnerportal-zeitplan"] });
  }
  function bei(err: unknown) {
    setFehler(err instanceof ApiError ? err.message : "Aktion fehlgeschlagen. Bitte erneut versuchen.");
  }

  const antwort = useMutation({
    mutationFn: (v: { status: "angenommen" | "abgelehnt"; grund?: string }) =>
      partnerPortalApi.antworten(id, v.status, v.grund),
    onSuccess: (neu) => {
      setFehler(null);
      setAblehnenOffen(false);
      uebernehmen(neu);
    },
    onError: bei,
  });
  const statusWechsel = useMutation({
    mutationFn: (status: PartnerStatusSetzbar) => partnerPortalApi.statusSetzen(id, status),
    onSuccess: (neu) => {
      setFehler(null);
      setAbschliessenOffen(false);
      uebernehmen(neu);
    },
    onError: (err) => {
      setAbschliessenOffen(false);
      bei(err);
    },
  });
  const senden = useMutation({
    mutationFn: (text: string) => partnerPortalApi.kommentieren(id, text),
    onSuccess: (event) => {
      setFehler(null);
      setKommentar("");
      setGesendet((alt) => [event, ...alt]);
    },
    onError: bei,
  });

  const zurueck = (
    <Link to="/partnerportal/auftraege" className="btn-touch flex items-center gap-0.5 px-3 text-[17px] text-tint-text">
      <ChevronLeft size={20} aria-hidden="true" /> Aufträge
    </Link>
  );

  if (isLoading) {
    return (
      <main className="mx-auto max-w-2xl px-3 py-4">
        {zurueck}
        <div className="px-4 pt-4">
          <SkeletonList count={3} />
        </div>
      </main>
    );
  }
  if (error || !auftrag) {
    return (
      <main className="mx-auto max-w-2xl px-3 py-4">
        {zurueck}
        <p role="alert" className="px-5 pt-4 text-sm text-st-fehlt">
          {error instanceof ApiError && error.status === 404
            ? "Dieser Auftrag existiert nicht (mehr) oder ist Ihnen nicht zugewiesen."
            : "Der Auftrag konnte nicht geladen werden."}
        </p>
      </main>
    );
  }

  const pille = auftragsPille(auftrag);
  const bearbeitbar = istBearbeitbar(auftrag);
  const adresse = adresseAlsZeile(auftrag.anlage_adresse);
  const aktiv = antwort.isPending || statusWechsel.isPending;

  return (
    <main className="mx-auto max-w-2xl px-3 py-4 pb-10">
      {zurueck}
      <div className="px-5 pt-2">
        <p className="text-[13px] text-label2">{auftrag.vorgangsnummer}</p>
        <h1 className="ap-heading text-[26px] leading-tight font-bold text-label">{auftrag.titel}</h1>
        <div className="mt-2">
          <StatusPille status={pille.status} label={pille.label} />
        </div>
      </div>

      {fehler && (
        <p role="alert" className="mx-4 mt-4 rounded-[var(--radius-ap-input)] bg-st-fehlt-bg px-3 py-2 text-sm text-st-fehlt">
          {fehler}
        </p>
      )}

      {auftrag.partner_freigabe_status === "vorgeschlagen" && (
        <div className="mx-4 mt-4 rounded-[var(--radius-ap-card)] bg-cell p-4">
          <p className="mb-3 text-[15px] text-label">Wollen Sie diesen Auftrag übernehmen?</p>
          <div className="flex gap-2">
            <button
              onClick={() => antwort.mutate({ status: "angenommen" })}
              disabled={aktiv}
              className="btn-ap-capsule btn-ap-capsule-primary flex-1"
            >
              Annehmen
            </button>
            <button
              onClick={() => setAblehnenOffen(true)}
              disabled={aktiv}
              className="btn-ap-capsule btn-ap-capsule-secondary flex-1"
            >
              Ablehnen
            </button>
          </div>
        </div>
      )}

      {auftrag.partner_freigabe_status === "abgelehnt" && (
        <p className="mx-4 mt-4 rounded-[var(--radius-ap-card)] bg-cell p-4 text-[15px] text-label2">
          Sie haben diesen Auftrag abgelehnt
          {auftrag.partner_ablehnung_grund ? `: ${auftrag.partner_ablehnung_grund}` : "."}
        </p>
      )}

      <AbschnittskopfB titel="Auftrag" />
      <div className="px-4">
        <GroupedList>
          <GroupedListValueRow label="Kunde" wert={auftrag.kunde_name} />
          {auftrag.anlage_bezeichnung && <GroupedListValueRow label="Anlage" wert={auftrag.anlage_bezeichnung} />}
          {adresse && <GroupedListValueRow label="Adresse" wert={<span className="text-right">{adresse}</span>} />}
          <GroupedListValueRow label="Leistung" wert={LEISTUNGSTYP_LABEL[auftrag.leistungstyp] ?? auftrag.leistungstyp} />
          {auftrag.partner_honorar_netto && (
            <GroupedListValueRow label="Honorar (netto)" wert={formatEuro(auftrag.partner_honorar_netto)} />
          )}
          <GroupedListValueRow label="Angelegt" wert={formatDatum(auftrag.created_at)} last />
        </GroupedList>
      </div>

      {auftrag.beschreibung && (
        <>
          <AbschnittskopfB titel="Beschreibung" />
          <p className="mx-4 rounded-[var(--radius-ap-card)] bg-cell p-4 text-[15px] whitespace-pre-wrap text-label">
            {auftrag.beschreibung}
          </p>
        </>
      )}

      {bearbeitbar && (
        <>
          <AbschnittskopfB titel="Status melden" />
          <div className="flex flex-wrap gap-2 px-4">
            {STATUS_AKTIONEN.map((a) => (
              <button
                key={a.status}
                onClick={() => statusWechsel.mutate(a.status)}
                disabled={aktiv || auftrag.status === a.status}
                aria-pressed={auftrag.status === a.status}
                className={`btn-ap-capsule ${auftrag.status === a.status ? "btn-ap-capsule-primary" : "btn-ap-capsule-secondary"}`}
              >
                {a.label}
              </button>
            ))}
            <button
              onClick={() => setAbschliessenOffen(true)}
              disabled={aktiv}
              className="btn-ap-capsule btn-ap-capsule-secondary"
            >
              Abschließen
            </button>
          </div>
        </>
      )}

      {bearbeitbar && (
        <>
          <AbschnittskopfB titel="Kommentar an den Betrieb" />
          <form
            className="mx-4"
            onSubmit={(e) => {
              e.preventDefault();
              if (kommentar.trim()) senden.mutate(kommentar.trim());
            }}
          >
            <label htmlFor="partner-kommentar" className="sr-only">
              Kommentar
            </label>
            <textarea
              id="partner-kommentar"
              rows={3}
              value={kommentar}
              onChange={(e) => setKommentar(e.target.value)}
              placeholder="Nachricht schreiben…"
              className="field-ap mb-2"
            />
            <button
              type="submit"
              disabled={senden.isPending || !kommentar.trim()}
              className="btn-ap-capsule btn-ap-capsule-primary w-full"
            >
              <Send size={16} aria-hidden="true" /> Senden
            </button>
          </form>
          {gesendet.length > 0 && (
            <div className="px-4 pt-3">
              <GroupedList>
                {gesendet.map((k, i) => (
                  <div key={k.id} className="relative px-4 py-2.5">
                    <p className="text-[15px] whitespace-pre-wrap text-label">{k.body}</p>
                    <p className="text-[12px] text-label3">Gesendet {new Date(k.created_at).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" })}</p>
                    {i < gesendet.length - 1 && <span className="absolute right-0 bottom-0 left-4 h-px bg-sep" aria-hidden="true" />}
                  </div>
                ))}
              </GroupedList>
            </div>
          )}
        </>
      )}

      <Sheet
        offen={ablehnenOffen}
        onClose={() => setAblehnenOffen(false)}
        titel="Auftrag ablehnen"
        links={
          <button onClick={() => setAblehnenOffen(false)} className="btn-touch text-[17px] text-tint-text">
            Abbrechen
          </button>
        }
      >
        <div className="p-4">
          <label htmlFor="partner-ablehnung-grund" className="mb-1 block text-sm font-medium text-label">
            Grund (optional)
          </label>
          <textarea
            id="partner-ablehnung-grund"
            rows={3}
            value={grund}
            onChange={(e) => setGrund(e.target.value)}
            className="field-ap mb-4"
          />
          <button
            onClick={() => antwort.mutate({ status: "abgelehnt", grund: grund.trim() })}
            disabled={antwort.isPending}
            className="btn-ap-capsule btn-ap-capsule-primary w-full"
          >
            Ablehnen
          </button>
        </div>
      </Sheet>

      <Sheet
        offen={abschliessenOffen}
        onClose={() => setAbschliessenOffen(false)}
        titel="Auftrag abschließen"
        links={
          <button onClick={() => setAbschliessenOffen(false)} className="btn-touch text-[17px] text-tint-text">
            Abbrechen
          </button>
        }
      >
        <div className="p-4">
          <p className="mb-4 text-[15px] text-label2">
            Nach dem Abschließen können Sie den Status nicht mehr ändern und keine Kommentare mehr senden.
          </p>
          <button
            onClick={() => statusWechsel.mutate("abgeschlossen")}
            disabled={statusWechsel.isPending}
            className="btn-ap-capsule btn-ap-capsule-primary w-full"
          >
            Abschließen
          </button>
        </div>
      </Sheet>
    </main>
  );
}
