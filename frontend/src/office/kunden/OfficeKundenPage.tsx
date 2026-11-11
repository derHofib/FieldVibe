import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Search, Users } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { kundenApi } from "../../api/endpoints";
import { EmptyState } from "../../components/EmptyState";
import { SkeletonList } from "../../components/Skeleton";
import { FilterChip } from "../../components/apple/FilterChip";
import { SearchField } from "../../components/apple/SearchField";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { FehlerZustand } from "../../components/FehlerZustand";
import { useAuth } from "../../context/AuthContext";
import { KundeProfilePage } from "../../pages/feld/KundeProfilePage";
import type { Kunde, KundeTyp } from "../../types";
import { filtereKunden } from "../../utils/geschaeft";
import { ListeMitPanel } from "../ListeMitPanel";
import { SeitenKopf } from "../OfficeUi";
import { Select } from "../../components/apple/Select";
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
    render: (k) =>
      k.typ ? <span className="border border-sep px-2 py-0.5 text-xs font-semibold text-label">{TYP_LABEL[k.typ]}</span> : "–",
    sortWert: (k) => (k.typ ? TYP_LABEL[k.typ] : ""),
  },
  { key: "ort", label: "Ort", render: (k) => <span className="whitespace-nowrap">{ORT(k) || "–"}</span>, sortWert: ORT },
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
    navigate(`/kunden/${kunde.id}`);
  };
  const schliessen = () => {
    if (id) navigate("/kunden");
  };

  const panel = id ? <KundeProfilePage key={id} id={id} eingebettet /> : null;

  return (
    <div>
      <SeitenKopf titel="Kunden" anzahl={isLoading || isError ? undefined : gefiltert.length}>
        <SearchField
          value={suche}
          onChange={setSuche}
          placeholder="Name oder Kundennummer…"
          ariaLabel="Kunden suchen"
          className="w-64"
        />
        {hatRecht("kunden", "erstellen") && (
          <button
            onClick={() => setNeu(true)}
            className="btn-ap-primary flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold"
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
            <FilterChip key={typ} label={TYP_LABEL[typ]} aktiv={typFilter === typ} onClick={() => setTypFilter(typ)} />
          ))}
        </div>
      )}

      <ListeMitPanel
        panelTitel="Kundenprofil"
        panel={panel}
        onSchliessen={schliessen}
        liste={
          isLoading ? (
            <SkeletonList count={6} />
          ) : isError ? (
            <FehlerZustand fehler={error} was="Die Kunden" onErneut={() => void refetch()} />
          ) : (data ?? []).length === 0 ? (
            <EmptyState
              icon={Users}
              text="Noch keine Kunden angelegt."
              action={
                hatRecht("kunden", "erstellen") ? (
                  <button type="button" onClick={() => setNeu(true)} className="btn-ap btn-ap-primary px-4 py-2 text-sm">
                    Neuer Kunde
                  </button>
                ) : undefined
              }
            />
          ) : gefiltert.length === 0 ? (
            <EmptyState icon={Search} text="Kein Kunde entspricht der Suche oder dem Filter." />
          ) : (
            <SortierbareTabelle
              zeilen={gefiltert}
              // Bei offenem Panel ist die Tabelle schmal -- Nebenspalte weglassen statt abschneiden
              spalten={id ? SPALTEN.filter((sp) => sp.key !== "kontakt") : SPALTEN}
              zeilenKey={(k) => k.id}
              gewaehlt={id}
              onWaehlen={waehlen}
              startSortierung={{ key: "name" }}
            />
          )
        }
      />

      <AnlegenPanel offen={neu} onClose={() => setNeu(false)} titel="Neuer Kunde">
        <NeuerKundeFormular
          onAbbrechen={() => setNeu(false)}
          onAngelegt={(kunde) => {
            setNeu(false);
            navigate(`/kunden/${kunde.id}`);
          }}
        />
      </AnlegenPanel>
    </div>
  );
}

const FELD = "field-ap";
const LABEL = "mb-1 block text-xs font-medium text-label2";

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
      className="space-y-3 p-4"
    >
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
          <Select id="kunde-typ" value={form.typ} onChange={(e) => setze({ typ: e.target.value })}>
            <option value="">Bitte wählen…</option>
            {(Object.keys(TYP_LABEL) as KundeTyp[]).map((typ) => (
              <option key={typ} value={typ}>
                {TYP_LABEL[typ]}
              </option>
            ))}
          </Select>
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
      <p className="text-xs text-label2">
        Ansprechpartner können anschließend im Kundenprofil angelegt werden.
      </p>
      {anlegen.isError && (
        <p role="alert" className="text-xs text-st-fehlt">
          {anlegen.error instanceof ApiError ? anlegen.error.message : "Anlegen fehlgeschlagen."}
        </p>
      )}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onAbbrechen}
          className="btn-ap px-3 py-2 text-xs font-semibold"
        >
          Abbrechen
        </button>
        <button
          type="submit"
          disabled={anlegen.isPending}
          className="btn-ap-primary px-4 py-2 text-xs font-semibold disabled:opacity-50"
        >
          {anlegen.isPending ? "Legt an…" : "Kunde anlegen"}
        </button>
      </div>
    </form>
  );
}
