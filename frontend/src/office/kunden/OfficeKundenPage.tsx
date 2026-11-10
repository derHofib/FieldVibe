import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Users } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { kundenApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import { useAuth } from "../../context/AuthContext";
import { KundeProfilePage } from "../../pages/feld/KundeProfilePage";
import type { Kunde, KundeTyp } from "../../types";
import { filtereKunden } from "../../utils/geschaeft";
import { ListeMitPanel } from "../ListeMitPanel";
import { FehlerHinweis, FilterChip, SeitenKopf } from "../OfficeUi";
import { SortierbareTabelle, type Spalte } from "../SortierbareTabelle";

const TYP_LABEL: Record<KundeTyp, string> = {
  privat: "Privat",
  gewerbe: "Gewerbe",
  oeffentlich: "Öffentlich",
  hausverwaltung: "Hausverwaltung",
};

const ORT = (k: Kunde) => [k.adresse?.plz, k.adresse?.ort].filter(Boolean).join(" ");

const SPALTEN: Spalte<Kunde>[] = [
  { key: "nr", label: "Kundennr.", render: (k) => k.kundennummer, sortWert: (k) => k.kundennummer },
  { key: "name", label: "Name", haupt: true, render: (k) => k.name, sortWert: (k) => k.name },
  {
    key: "typ",
    label: "Typ",
    render: (k) => (k.typ ? <StatusBadge label={TYP_LABEL[k.typ]} tone="slate" /> : "–"),
    sortWert: (k) => (k.typ ? TYP_LABEL[k.typ] : ""),
  },
  { key: "ort", label: "Ort", render: (k) => ORT(k) || "–", sortWert: ORT },
  {
    key: "kontakt",
    label: "Ansprechpartner",
    render: (k) => k.ansprechpartner[0]?.name ?? "–",
    sortWert: (k) => k.ansprechpartner[0]?.name ?? "",
  },
];

/** Desktop-Fassung des Tabs "Kunden" aus GeschaeftPage: Tabelle links, das
 * bestehende Kundenprofil als Detailpanel rechts. Die Auswahl steckt in der
 * URL (/kunden/:id), damit Reload und Deep-Links sie behalten. */
export function OfficeKundenPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { hatRecht } = useAuth();
  const [suche, setSuche] = useState("");
  const [typFilter, setTypFilter] = useState<KundeTyp | "alle">("alle");
  const [neu, setNeu] = useState(false);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["kunden"],
    queryFn: () => kundenApi.list(),
  });

  const kunden = (data ?? []).filter((k) => typFilter === "alle" || k.typ === typFilter);
  const gefiltert = filtereKunden(kunden, suche);
  const vorhandeneTypen = Array.from(new Set((data ?? []).map((k) => k.typ).filter((t): t is KundeTyp => !!t)));

  const waehlen = (kunde: Kunde) => {
    setNeu(false);
    navigate(`/kunden/${kunde.id}`);
  };
  const schliessen = () => {
    setNeu(false);
    if (id) navigate("/kunden");
  };

  const panel = neu ? (
    <NeuerKundeFormular
      onAbbrechen={() => setNeu(false)}
      onAngelegt={(kunde) => {
        setNeu(false);
        navigate(`/kunden/${kunde.id}`);
      }}
    />
  ) : id ? (
    <KundeProfilePage key={id} id={id} eingebettet onGeloescht={() => navigate("/kunden")} />
  ) : null;

  return (
    <div>
      <SeitenKopf titel="Kunden" anzahl={isLoading || isError ? undefined : gefiltert.length}>
        <label className="relative block">
          <span className="sr-only">Kunden suchen</span>
          <Search
            size={13}
            strokeWidth={2}
            className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-slate-400 dark:text-stone-500"
          />
          <input
            value={suche}
            onChange={(e) => setSuche(e.target.value)}
            placeholder="Name oder Kundennummer…"
            className="w-56 rounded-lg border border-slate-200 bg-slate-100 py-1.5 pr-2 pl-7 text-xs text-slate-700 placeholder:text-slate-400 dark:border-stone-700 dark:bg-stone-800 dark:text-stone-200 dark:placeholder:text-stone-500"
          />
        </label>
        {hatRecht("kunden", "erstellen") && (
          <button
            onClick={() => setNeu(true)}
            className="btn-clay flex items-center gap-1.5 rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-3 py-2 text-xs font-semibold text-white"
          >
            <Plus size={14} strokeWidth={2.5} />
            Neuer Kunde
          </button>
        )}
      </SeitenKopf>

      {vorhandeneTypen.length > 1 && (
        <div className="mb-4 flex flex-wrap gap-2">
          <FilterChip label="Alle" aktiv={typFilter === "alle"} onClick={() => setTypFilter("alle")} />
          {vorhandeneTypen.map((typ) => (
            <FilterChip
              key={typ}
              label={TYP_LABEL[typ]}
              aktiv={typFilter === typ}
              onClick={() => setTypFilter(typ)}
            />
          ))}
        </div>
      )}

      <ListeMitPanel
        panelTitel={neu ? "Neuer Kunde" : "Kundenprofil"}
        panel={panel}
        onSchliessen={schliessen}
        liste={
          isLoading ? (
            <SkeletonList count={6} />
          ) : isError ? (
            <FehlerHinweis
              text={error instanceof ApiError ? error.message : "Die Kunden konnten nicht geladen werden."}
              onNochmal={() => refetch()}
            />
          ) : (data ?? []).length === 0 ? (
            <EmptyState
              icon={Users}
              text="Noch keine Kunden angelegt. Mit „Neuer Kunde“ legst du den ersten an."
            />
          ) : gefiltert.length === 0 ? (
            <EmptyState icon={Search} text="Kein Kunde entspricht der Suche oder dem Filter." />
          ) : (
            <SortierbareTabelle
              zeilen={gefiltert}
              spalten={SPALTEN}
              zeilenKey={(k) => k.id}
              gewaehlt={id}
              onWaehlen={waehlen}
              startSortierung={{ key: "name" }}
            />
          )
        }
      />
    </div>
  );
}

const FELD =
  "w-full rounded-md border border-slate-300 px-2 py-1.5 text-sm dark:border-stone-700 dark:bg-stone-800 dark:text-stone-100";
const LABEL = "mb-1 block text-xs font-medium text-slate-500 dark:text-stone-400";

function NeuerKundeFormular({
  onAbbrechen,
  onAngelegt,
}: {
  onAbbrechen: () => void;
  onAngelegt: (kunde: Kunde) => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    name: "",
    kundennummer: "",
    typ: "",
    ustIdnr: "",
    strasse: "",
    plz: "",
    ort: "",
    notiz: "",
  });
  const setze = (teil: Partial<typeof form>) => setForm({ ...form, ...teil });

  const anlegen = useMutation({
    mutationFn: () => {
      const adresse =
        form.strasse || form.plz || form.ort
          ? { strasse: form.strasse || undefined, plz: form.plz || undefined, ort: form.ort || undefined }
          : undefined;
      return kundenApi.create({
        name: form.name.trim(),
        kundennummer: form.kundennummer || undefined,
        typ: form.typ || undefined,
        adresse,
        notiz: form.notiz || undefined,
        ust_idnr: form.ustIdnr || undefined,
      });
    },
    onSuccess: (kunde) => {
      queryClient.invalidateQueries({ queryKey: ["kunden"] });
      onAngelegt(kunde);
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        anlegen.mutate();
      }}
      className="space-y-3"
    >
      <h2 className="text-base font-bold text-slate-800 dark:text-stone-100">Neuer Kunde</h2>
      <div>
        <label htmlFor="kunde-name" className={LABEL}>
          Name *
        </label>
        <input
          id="kunde-name"
          autoFocus
          required
          value={form.name}
          onChange={(e) => setze({ name: e.target.value })}
          className={FELD}
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label htmlFor="kunde-nr" className={LABEL}>
            Kundennummer
          </label>
          <input
            id="kunde-nr"
            value={form.kundennummer}
            onChange={(e) => setze({ kundennummer: e.target.value })}
            placeholder="wird sonst vergeben"
            className={FELD}
          />
        </div>
        <div>
          <label htmlFor="kunde-typ" className={LABEL}>
            Typ
          </label>
          <select id="kunde-typ" value={form.typ} onChange={(e) => setze({ typ: e.target.value })} className={FELD}>
            <option value="">Bitte wählen…</option>
            {(Object.keys(TYP_LABEL) as KundeTyp[]).map((typ) => (
              <option key={typ} value={typ}>
                {TYP_LABEL[typ]}
              </option>
            ))}
          </select>
        </div>
      </div>
      {(form.typ === "gewerbe" || form.typ === "oeffentlich") && (
        <div>
          <label htmlFor="kunde-ust" className={LABEL}>
            USt-IdNr.
          </label>
          <input
            id="kunde-ust"
            value={form.ustIdnr}
            onChange={(e) => setze({ ustIdnr: e.target.value })}
            placeholder="DE123456789"
            className={FELD}
          />
        </div>
      )}
      <div>
        <label htmlFor="kunde-strasse" className={LABEL}>
          Straße + Hausnr.
        </label>
        <input id="kunde-strasse" value={form.strasse} onChange={(e) => setze({ strasse: e.target.value })} className={FELD} />
      </div>
      <div className="grid grid-cols-[1fr_2fr] gap-2">
        <div>
          <label htmlFor="kunde-plz" className={LABEL}>
            PLZ
          </label>
          <input id="kunde-plz" value={form.plz} onChange={(e) => setze({ plz: e.target.value })} className={FELD} />
        </div>
        <div>
          <label htmlFor="kunde-ort" className={LABEL}>
            Ort
          </label>
          <input id="kunde-ort" value={form.ort} onChange={(e) => setze({ ort: e.target.value })} className={FELD} />
        </div>
      </div>
      <div>
        <label htmlFor="kunde-notiz" className={LABEL}>
          Notiz
        </label>
        <textarea id="kunde-notiz" rows={2} value={form.notiz} onChange={(e) => setze({ notiz: e.target.value })} className={FELD} />
      </div>
      <p className="text-xs text-slate-400 dark:text-stone-500">
        Ansprechpartner können anschließend im Kundenprofil angelegt werden.
      </p>
      {anlegen.isError && (
        <p role="alert" className="text-xs text-rose-700 dark:text-rose-300">
          {anlegen.error instanceof ApiError ? anlegen.error.message : "Anlegen fehlgeschlagen."}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onAbbrechen}
          className="rounded-lg px-3 py-2 text-xs font-semibold text-slate-500 hover:bg-slate-100 dark:text-stone-400 dark:hover:bg-stone-800"
        >
          Abbrechen
        </button>
        <button
          type="submit"
          disabled={anlegen.isPending}
          className="btn-clay rounded-lg bg-linear-to-r from-cyan-500 to-blue-600 px-4 py-2 text-xs font-semibold text-white disabled:opacity-50"
        >
          {anlegen.isPending ? "Legt an…" : "Kunde anlegen"}
        </button>
      </div>
    </form>
  );
}
