import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Boxes, Package, Plus, Search, Truck } from "lucide-react";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { ApiError } from "../../api/client";
import { anlagenApi, lieferantenApi, materialApi, tagsApi } from "../../api/endpoints";
import { FilterChip } from "../../components/apple/FilterChip";
import { SearchField } from "../../components/apple/SearchField";
import { AnlegenPanel } from "../../components/AnlegenPanel";
import { EmptyState } from "../../components/EmptyState";
import { FehlerZustand } from "../../components/FehlerZustand";
import { SkeletonList } from "../../components/Skeleton";
import { useAuth } from "../../context/AuthContext";
import { MaterialDetailPage } from "../../pages/feld/MaterialDetailPage";
import { LagerorteVerwaltung, MaterialPage, MaterialZeile } from "../../pages/feld/MaterialPage";
import type { Material } from "../../types";
import { filtereMaterial, istUnterbestand } from "../../utils/geschaeft";
import { ListeMitPanel } from "../ListeMitPanel";
import { AnsichtUmschalter, SeitenKopf } from "../OfficeUi";
import { Select } from "../../components/apple/Select";
import { SortierbareTabelle, type Spalte } from "../SortierbareTabelle";

const EURO = new Intl.NumberFormat("de-DE", { style: "currency", currency: "EUR" });

/** Desktop-Fassung des Tabs "Material" aus GeschaeftPage: Tabelle links, rechts
 * Stammdaten (bestehende Detailseite) plus Bestände je Lager. Auswahl in der
 * URL (/material/:id) wie bei den Kunden. */
export function OfficeMaterialPage() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { hatRecht } = useAuth();
  const [suche, setSuche] = useState("");
  const [lieferantId, setLieferantId] = useState("");
  const [tagId, setTagId] = useState("");
  const [nurUnterbestand, setNurUnterbestand] = useState(false);
  const [neu, setNeu] = useState(false);
  const [ansicht, setAnsicht] = useState<"material" | "bestellwesen">("material");
  const [lagerorteZeigen, setLagerorteZeigen] = useState(false);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: ["material"],
    queryFn: () => materialApi.list(),
  });
  const { data: lieferanten } = useQuery({ queryKey: ["lieferanten"], queryFn: () => lieferantenApi.list() });
  const { data: tags } = useQuery({ queryKey: ["tags"], queryFn: tagsApi.list });
  const { data: alleAnlagen } = useQuery({ queryKey: ["lagerorte"], queryFn: () => anlagenApi.list() });
  const lagerorte = (alleAnlagen ?? []).filter((a) => a.objekttyp !== "kundenanlage");

  const lieferantName = (m: Material) => lieferanten?.find((l) => l.id === m.lieferant_id)?.name;
  const gefiltert = filtereMaterial(data ?? [], { suche, lieferantId, tagId, nurUnterbestand });
  const gewaehltesMaterial = id ? (data ?? []).find((m) => m.id === id) : undefined;

  const spalten: Spalte<Material>[] = [
    { key: "bezeichnung", label: "Bezeichnung", haupt: true, render: (m) => m.bezeichnung, sortWert: (m) => m.bezeichnung },
    { key: "artikelnummer", label: "Art.-Nr.", render: (m) => m.artikelnummer ?? "–", sortWert: (m) => m.artikelnummer ?? "" },
    {
      key: "bestand",
      label: "Bestand",
      align: "rechts",
      render: (m) => (
        <span
          className={
            istUnterbestand(m) ? "font-semibold text-st-fehlt" : undefined
          }
        >
          {m.bestand_gesamt} {m.einheit}
          {istUnterbestand(m) && <span className="sr-only"> (Unterbestand)</span>}
        </span>
      ),
      sortWert: (m) => Number(m.bestand_gesamt),
    },
    {
      key: "mindestbestand",
      label: "Mindestbestand",
      align: "rechts",
      render: (m) => `${m.mindestbestand} ${m.einheit}`,
      sortWert: (m) => Number(m.mindestbestand),
    },
    {
      key: "preis",
      label: "Einzelpreis",
      align: "rechts",
      render: (m) => (m.einzelpreis ? EURO.format(Number(m.einzelpreis)) : "–"),
      sortWert: (m) => (m.einzelpreis ? Number(m.einzelpreis) : -1),
    },
    { key: "lieferant", label: "Lieferant", render: (m) => lieferantName(m) ?? "–", sortWert: (m) => lieferantName(m) ?? "" },
  ];

  const schliessen = () => {
    if (id) navigate("/material");
  };

  const panel = id ? (
    <div className="space-y-4">
      <MaterialDetailPage key={id} id={id} eingebettet />
      {gewaehltesMaterial && (
        <div>
          <h3 className="mb-2 text-xs font-bold tracking-wider text-label2 uppercase">
            Bestände je Lager
          </h3>
          <MaterialZeile
            material={gewaehltesMaterial}
            lagerorte={lagerorte}
            lieferantName={lieferantName(gewaehltesMaterial)}
            tags={(tags ?? []).filter((t) => gewaehltesMaterial.tag_ids.includes(t.id))}
          />
        </div>
      )}
    </div>
  ) : null;

  return (
    <div>
      <SeitenKopf titel="Material" anzahl={isLoading || isError ? undefined : gefiltert.length}>
        <AnsichtUmschalter
          wert={ansicht}
          optionen={[
            { wert: "material", label: "Material", icon: Boxes },
            { wert: "bestellwesen", label: "Bestellwesen", icon: Truck },
          ]}
          onWechsel={(neuerWert) => {
            setAnsicht(neuerWert);
            if (id) navigate("/material");
          }}
        />
        {ansicht === "material" && (
          <SearchField
            value={suche}
            onChange={setSuche}
            placeholder="Bezeichnung oder Art.-Nr.…"
            ariaLabel="Material suchen"
            className="w-64"
          />
        )}
        {hatRecht("material", "erstellen") && (
          <button
            onClick={() => {
              if (id) navigate("/material");
              setAnsicht("material");
              setNeu(true);
            }}
            className="btn-ap-primary flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold"
          >
            <Plus size={14} strokeWidth={2.5} />
            Neues Material
          </button>
        )}
      </SeitenKopf>

      {ansicht === "bestellwesen" ? (
        <MaterialPage nurBestellwesen />
      ) : (
        <>
          {(data ?? []).length > 0 && (
            <div className="mb-4 flex flex-wrap items-center gap-2">
              <FilterChip
                label="Nur Unterbestand"
                aktiv={nurUnterbestand}
                onClick={() => setNurUnterbestand((v) => !v)}
              />
              <label className="sr-only" htmlFor="material-lieferant">
                Lieferant filtern
              </label>
              <Select className="w-auto" groesse="kompakt"
                id="material-lieferant"
                value={lieferantId}
                onChange={(e) => setLieferantId(e.target.value)}
              >
                <option value="">Alle Lieferanten</option>
                {(lieferanten ?? []).map((l) => (
                  <option key={l.id} value={l.id}>
                    {l.name}
                  </option>
                ))}
              </Select>
              <label className="sr-only" htmlFor="material-tag">
                Tag filtern
              </label>
              <Select className="w-auto" groesse="kompakt"
                id="material-tag"
                value={tagId}
                onChange={(e) => setTagId(e.target.value)}
              >
                <option value="">Alle Tags</option>
                {(tags ?? []).map((t) => (
                  <option key={t.id} value={t.id}>
                    #{t.label}
                  </option>
                ))}
              </Select>
              <button
                type="button"
                onClick={() => setLagerorteZeigen((v) => !v)}
                aria-expanded={lagerorteZeigen}
                className="ml-auto text-xs font-medium text-tint-text hover:underline"
              >
                Lagerorte verwalten
              </button>
            </div>
          )}
          {lagerorteZeigen && (
            <div className="mb-4">
              <LagerorteVerwaltung
                lagerorte={lagerorte.filter((l) => l.objekttyp !== "lager" || l.bezeichnung !== "Zentrallager")}
              />
            </div>
          )}

      <ListeMitPanel
        panelTitel="Materialdetails"
        panel={panel}
        onSchliessen={schliessen}
        liste={
          isLoading ? (
            <SkeletonList count={6} />
          ) : isError ? (
            <FehlerZustand fehler={error} was="Das Material" onErneut={() => void refetch()} />
          ) : (data ?? []).length === 0 ? (
            <EmptyState
              icon={Package}
              text="Noch kein Material erfasst. Mit „Neues Material“ legst du den ersten Artikel an."
            />
          ) : gefiltert.length === 0 ? (
            <EmptyState icon={Search} text="Kein Material entspricht Suche oder Filter." />
          ) : (
            <SortierbareTabelle
              zeilen={gefiltert}
              spalten={spalten}
              zeilenKey={(m) => m.id}
              gewaehlt={id}
              onWaehlen={(m) => navigate(`/material/${m.id}`)}
              startSortierung={{ key: "bezeichnung" }}
            />
          )
        }
      />
        </>
      )}

      <AnlegenPanel offen={neu} onClose={() => setNeu(false)} titel="Neues Material">
        <NeuesMaterialFormular
          lagerorte={lagerorte.map((l) => ({ id: l.id, bezeichnung: l.bezeichnung }))}
          lieferanten={lieferanten ?? []}
          onAbbrechen={() => setNeu(false)}
          onAngelegt={() => setNeu(false)}
        />
      </AnlegenPanel>
    </div>
  );
}

const FELD = "field-ap";
const LABEL = "mb-1 block text-xs font-medium text-label2";

function NeuesMaterialFormular({
  lagerorte,
  lieferanten,
  onAbbrechen,
  onAngelegt,
}: {
  lagerorte: { id: string; bezeichnung: string }[];
  lieferanten: { id: string; name: string }[];
  onAbbrechen: () => void;
  onAngelegt: () => void;
}) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState({
    bezeichnung: "",
    einheit: "Stk",
    menge: "0",
    lagerId: "",
    mindestbestand: "0",
    einzelpreis: "",
    lieferantId: "",
  });
  const setze = (teil: Partial<typeof form>) => setForm({ ...form, ...teil });

  const anlegen = useMutation({
    mutationFn: () =>
      materialApi.create({
        bezeichnung: form.bezeichnung.trim(),
        einheit: form.einheit,
        menge: form.menge,
        lager_id: form.lagerId || undefined,
        mindestbestand: form.mindestbestand,
        einzelpreis: form.einzelpreis || undefined,
        lieferant_id: form.lieferantId || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["material"] });
      queryClient.invalidateQueries({ queryKey: ["stories"] });
      onAngelegt();
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
        <label htmlFor="material-bezeichnung" className={LABEL}>
          Bezeichnung *
        </label>
        <input
          id="material-bezeichnung"
          autoFocus
          required
          value={form.bezeichnung}
          onChange={(e) => setze({ bezeichnung: e.target.value })}
          className={FELD}
        />
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div>
          <label htmlFor="material-einheit" className={LABEL}>
            Einheit
          </label>
          <input id="material-einheit" value={form.einheit} onChange={(e) => setze({ einheit: e.target.value })} className={FELD} />
        </div>
        <div>
          <label htmlFor="material-preis" className={LABEL}>
            Einzelpreis (EUR)
          </label>
          <input id="material-preis" type="number" step="0.01" value={form.einzelpreis} onChange={(e) => setze({ einzelpreis: e.target.value })} className={FELD} />
        </div>
        <div>
          <label htmlFor="material-menge" className={LABEL}>
            Anfangsbestand
          </label>
          <input id="material-menge" type="number" step="0.01" value={form.menge} onChange={(e) => setze({ menge: e.target.value })} className={FELD} />
        </div>
        <div>
          <label htmlFor="material-min" className={LABEL}>
            Mindestbestand
          </label>
          <input id="material-min" type="number" step="0.01" value={form.mindestbestand} onChange={(e) => setze({ mindestbestand: e.target.value })} className={FELD} />
        </div>
      </div>
      <div>
        <label htmlFor="material-lieferant-neu" className={LABEL}>
          Standard-Lieferant
        </label>
        <Select id="material-lieferant-neu" value={form.lieferantId} onChange={(e) => setze({ lieferantId: e.target.value })}>
          <option value="">Kein Lieferant hinterlegt</option>
          {lieferanten.map((l) => (
            <option key={l.id} value={l.id}>
              {l.name}
            </option>
          ))}
        </Select>
      </div>
      <div>
        <label htmlFor="material-lager" className={LABEL}>
          Lagerort für Anfangsbestand
        </label>
        <Select id="material-lager" value={form.lagerId} onChange={(e) => setze({ lagerId: e.target.value })}>
          <option value="">Zentrallager (Standard)</option>
          {lagerorte.map((l) => (
            <option key={l.id} value={l.id}>
              {l.bezeichnung}
            </option>
          ))}
        </Select>
      </div>
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
          {anlegen.isPending ? "Legt an…" : "Material anlegen"}
        </button>
      </div>
    </form>
  );
}
