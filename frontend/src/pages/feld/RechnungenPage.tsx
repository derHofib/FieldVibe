import { useMutation, useQuery } from "@tanstack/react-query";
import { FileCheck2, Receipt } from "lucide-react";
import { useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";

import { angeboteApi, kundenApi, rechnungenApi } from "../../api/endpoints";
import { NeueRechnungForm } from "../../components/NeueRechnungForm";
import { EmptyState } from "../../components/EmptyState";
import { SearchableSelect } from "../../components/SearchableSelect";
import { SkeletonList } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { useAuth } from "../../context/AuthContext";
import { RECHNUNG_STATUS_LABEL, RECHNUNG_STATUS_TONE } from "../../utils/buchhaltung";
import { downloadBlob } from "../../utils/download";
import { formatDatum, formatEuro, heuteIso } from "../../utils/format";
import { istModulAktiv } from "../../utils/module";
import type { AngebotStatus, RechnungStatus, RechnungenFilter } from "../../types";

type Bereich = "rechnungen" | "angebote";

const STATUS_OPTIONEN: RechnungStatus[] = ["entwurf", "versendet", "teilweise_bezahlt", "bezahlt", "storniert"];
const SEITENGROESSE = 50;

const ANGEBOT_STATUS_LABEL: Record<AngebotStatus, string> = {
  entwurf: "Entwurf",
  versendet: "Versendet",
  angenommen: "Angenommen",
  abgelehnt: "Abgelehnt",
};

function AngeboteListe() {
  const navigate = useNavigate();
  const [showForm, setShowForm] = useState(false);
  const [kundeId, setKundeId] = useState("");

  const { data: kunden } = useQuery({ queryKey: ["kunden"], queryFn: () => kundenApi.list() });
  const { data: angebote, isLoading } = useQuery({ queryKey: ["angebote"], queryFn: () => angeboteApi.list() });

  const erstellen = useMutation({
    mutationFn: () => angeboteApi.create({ kunde_id: kundeId }),
    onSuccess: (angebot) => navigate(`/angebote/${angebot.id}`),
  });

  const nameFuer = (id: string) => kunden?.find((k) => k.id === id)?.name ?? "—";

  return (
    <div className="space-y-4">
      <button
        onClick={() => setShowForm((v) => !v)}
        className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 dark:bg-stone-800 dark:text-stone-300"
      >
        {showForm ? "Abbrechen" : "+ Neues Angebot"}
      </button>

      {showForm && (
        <div className="space-y-3 rounded-lg bg-white p-4 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
          <div>
            <label className="mb-1 block text-xs font-medium text-slate-500 dark:text-stone-400">Kunde</label>
            <SearchableSelect
              value={kundeId}
              onChange={setKundeId}
              placeholder="Kunde wählen…"
              options={(kunden ?? []).map((k) => ({ value: k.id, label: `${k.name} (${k.kundennummer})` }))}
            />
          </div>
          <button
            disabled={!kundeId || erstellen.isPending}
            onClick={() => erstellen.mutate()}
            className="btn-touch w-full rounded-md btn-clay bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          >
            Angebot anlegen
          </button>
        </div>
      )}

      <div className="space-y-2">
        {isLoading ? (
          <SkeletonList count={3} />
        ) : (angebote ?? []).length === 0 ? (
          <EmptyState icon={FileCheck2} text="Keine Angebote vorhanden." />
        ) : (
          angebote!.map((a) => (
            <button
              key={a.id}
              onClick={() => navigate(`/angebote/${a.id}`)}
              className="card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800"
            >
              <div>
                <div className="text-xs text-slate-400 dark:text-stone-500">{a.angebotsnummer}</div>
                <div className="text-sm font-medium text-slate-800 dark:text-stone-100">{nameFuer(a.kunde_id)}</div>
                <div className="text-xs text-slate-500 dark:text-stone-400">{formatEuro(a.gesamt_brutto)}</div>
              </div>
              <span className="rounded-full bg-slate-100 px-2 py-1 text-xs font-semibold text-slate-600 dark:bg-stone-800 dark:text-stone-300">
                {ANGEBOT_STATUS_LABEL[a.status]}
              </span>
            </button>
          ))
        )}
      </div>
    </div>
  );
}

export function RechnungenPage() {
  const { currentUser, hatRecht } = useAuth();
  const navigate = useNavigate();

  const abrechnungAktiv = istModulAktiv(currentUser, "abrechnung");
  const kannSehen = hatRecht("abrechnung", "sehen");

  const [bereich, setBereich] = useState<Bereich>("rechnungen");
  const [zeigeNeu, setZeigeNeu] = useState(false);
  const [q, setQ] = useState("");
  const [statusAktiv, setStatusAktiv] = useState<Set<RechnungStatus>>(new Set());
  const [nurUeberfaellig, setNurUeberfaellig] = useState(false);
  const [faelligBis7Tage, setFaelligBis7Tage] = useState(false);
  const [seiten, setSeiten] = useState(1);

  const filter: RechnungenFilter = {
    q: q.trim() || undefined,
    status: statusAktiv.size > 0 ? Array.from(statusAktiv) : undefined,
    nur_ueberfaellig: nurUeberfaellig || undefined,
    faellig_bis: faelligBis7Tage ? heuteIso(7) : undefined,
    sort: "-faellig",
    limit: SEITENGROESSE * seiten,
  };

  const { data, isLoading } = useQuery({
    queryKey: ["rechnungen-uebersicht", filter],
    queryFn: () => rechnungenApi.list(filter),
    enabled: abrechnungAktiv && kannSehen && bereich === "rechnungen",
  });

  if (!abrechnungAktiv || !kannSehen) return <Navigate to="/feed" replace />;

  const toggleStatus = (s: RechnungStatus) => {
    setSeiten(1);
    setStatusAktiv((prev) => {
      const next = new Set(prev);
      if (next.has(s)) next.delete(s);
      else next.add(s);
      return next;
    });
  };

  const exportieren = async () => {
    const blob = await rechnungenApi.exportCsv(filter);
    downloadBlob(blob, "Rechnungen.csv");
  };

  const eintraege = data?.eintraege ?? [];
  const gibtMehr = data ? data.gesamt_anzahl > eintraege.length : false;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-slate-800 dark:text-stone-100">
          {bereich === "rechnungen" ? "Rechnungen" : "Angebote"}
        </h1>
        {bereich === "rechnungen" && (
          <button
            onClick={exportieren}
            className="btn-touch rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 dark:bg-stone-800 dark:text-stone-300"
          >
            CSV-Export
          </button>
        )}
      </div>

      <div className="flex gap-2 overflow-x-auto rounded-lg bg-white p-1 shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
        {([
          { wert: "rechnungen" as const, label: "Rechnungen" },
          { wert: "angebote" as const, label: "Angebote" },
        ]).map((o) => (
          <button
            key={o.wert}
            onClick={() => {
              setBereich(o.wert);
              setZeigeNeu(false);
            }}
            className={`btn-touch shrink-0 whitespace-nowrap rounded-md px-4 py-2 text-sm font-medium ${
              bereich === o.wert
                ? "btn-clay bg-linear-to-r from-cyan-500 to-blue-600 text-white"
                : "text-slate-600 dark:text-stone-400"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>

      {bereich === "angebote" ? (
        <AngeboteListe />
      ) : (
        <>
          <button
            onClick={() => setZeigeNeu((v) => !v)}
            className="btn-touch rounded-md bg-slate-100 px-4 py-2 text-sm font-medium text-slate-700 dark:bg-stone-800 dark:text-stone-300"
          >
            {zeigeNeu ? "Abbrechen" : "+ Neue Rechnung"}
          </button>

          {zeigeNeu && (
            <NeueRechnungForm
              onAbbrechen={() => setZeigeNeu(false)}
              onErfolg={(id) => navigate(`/rechnungen/${id}`)}
            />
          )}

          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setSeiten(1);
            }}
            placeholder="Rechnungsnummer oder Kunde suchen…"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100"
          />

          <div className="flex flex-wrap gap-2 text-xs">
            {STATUS_OPTIONEN.map((s) => (
              <button
                key={s}
                onClick={() => toggleStatus(s)}
                className={`btn-touch rounded-full px-3 py-1 font-medium ${
                  statusAktiv.has(s)
                    ? "bg-cyan-600 text-white"
                    : "bg-slate-100 text-slate-600 dark:bg-stone-800 dark:text-stone-300"
                }`}
              >
                {RECHNUNG_STATUS_LABEL[s]}
              </button>
            ))}
            <button
              onClick={() => {
                setSeiten(1);
                setNurUeberfaellig((v) => !v);
              }}
              className={`btn-touch rounded-full px-3 py-1 font-medium ${
                nurUeberfaellig
                  ? "bg-rose-600 text-white"
                  : "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300"
              }`}
            >
              Überfällig
            </button>
            <button
              onClick={() => {
                setSeiten(1);
                setFaelligBis7Tage((v) => !v);
              }}
              className={`btn-touch rounded-full px-3 py-1 font-medium ${
                faelligBis7Tage
                  ? "bg-amber-600 text-white"
                  : "bg-amber-50 text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
              }`}
            >
              Diese Woche fällig
            </button>
          </div>

          {data && (
            <div className="grid grid-cols-3 gap-2 rounded-lg bg-white p-3 text-center shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 dark:ring-stone-800">
              <div>
                <div className="text-xs text-slate-400 dark:text-stone-500">Treffer</div>
                <div className="text-sm font-semibold tabular-nums text-slate-800 dark:text-stone-100">
                  {data.gesamt_anzahl}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-400 dark:text-stone-500">Brutto gesamt</div>
                <div className="text-sm font-semibold tabular-nums text-slate-800 dark:text-stone-100">
                  {formatEuro(data.summe_brutto)}
                </div>
              </div>
              <div>
                <div className="text-xs text-slate-400 dark:text-stone-500">Offen</div>
                <div className="text-sm font-semibold tabular-nums text-amber-600 dark:text-amber-400">
                  {formatEuro(data.summe_offen)}
                </div>
              </div>
            </div>
          )}

          <div className="space-y-2">
            {isLoading ? (
              <SkeletonList count={5} />
            ) : eintraege.length === 0 ? (
              <EmptyState icon={Receipt} text="Keine Rechnungen für diesen Filter." />
            ) : (
              eintraege.map((r) => (
                <button
                  key={r.id}
                  onClick={() => navigate(`/rechnungen/${r.id}`)}
                  className={`card-interactive btn-touch flex w-full items-center justify-between rounded-lg bg-white p-3 text-left shadow-xs dark:bg-stone-900 dark:shadow-none dark:ring-1 ${
                    r.ist_ueberfaellig
                      ? "ring-rose-300 dark:ring-rose-500/40"
                      : "dark:ring-stone-800"
                  }`}
                >
                  <div className="min-w-0">
                    <div className="text-xs text-slate-400 dark:text-stone-500">{r.rechnungsnummer}</div>
                    <div className="truncate text-sm font-medium text-slate-800 dark:text-stone-100">
                      Fällig: {formatDatum(r.faellig_am)}
                      {r.ist_ueberfaellig && (
                        <span className="ml-1 text-rose-600 dark:text-rose-400">
                          ({r.tage_ueberfaellig} Tage überfällig)
                        </span>
                      )}
                    </div>
                    {r.mahnstufe > 0 && (
                      <div className="text-xs text-amber-600 dark:text-amber-400">
                        Mahnstufe {r.mahnstufe}
                      </div>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-col items-end gap-1">
                    <span className="tabular-nums text-sm font-medium text-slate-700 dark:text-stone-300">
                      {formatEuro(r.betrag_brutto)}
                    </span>
                    <StatusBadge label={RECHNUNG_STATUS_LABEL[r.status]} tone={RECHNUNG_STATUS_TONE[r.status]} />
                  </div>
                </button>
              ))
            )}
          </div>

          {gibtMehr && (
            <button
              onClick={() => setSeiten((v) => v + 1)}
              className="btn-touch w-full rounded-md bg-slate-100 px-3 py-2 text-sm font-medium text-slate-700 dark:bg-stone-800 dark:text-stone-300"
            >
              Mehr laden
            </button>
          )}
        </>
      )}
    </div>
  );
}
