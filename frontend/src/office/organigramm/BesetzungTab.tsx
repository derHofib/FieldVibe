import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { useState, type FormEvent } from "react";

import { organigrammApi, usersApi } from "../../api/endpoints";
import { SegmentedControl } from "../../components/apple/SegmentedControl";
import { SearchableSelect } from "../../components/SearchableSelect";
import type { Besetzung, BesetzungArt, PositionDetail } from "../../types/organigramm";
import { besetzungZeitraum, istUnterbesetzt, verstaendlicherFehler } from "./darstellung";

const ART_LABEL: Record<BesetzungArt, string> = { regulaer: "Regulär", vertretung: "Vertretung" };

function BesetzungZeile({
  b,
  darfBeenden,
  beendenLaeuft,
  onBeenden,
}: {
  b: Besetzung;
  darfBeenden: boolean;
  beendenLaeuft: boolean;
  onBeenden?: () => void;
}) {
  return (
    <li className="flex items-center gap-2 px-3 py-2.5">
      <div className="min-w-0 flex-1">
        <p className="truncate text-[15px] font-medium text-label">{b.name ?? "Person (Name ausgeblendet)"}</p>
        <p className="text-xs text-label2">
          <span className="mr-1.5 rounded-full bg-fill px-1.5 py-0.5 font-medium text-label">{ART_LABEL[b.art]}</span>
          {besetzungZeitraum(b)}
        </p>
      </div>
      {onBeenden && darfBeenden && (
        <button type="button" onClick={onBeenden} disabled={beendenLaeuft} className="btn-ap shrink-0 text-xs">
          Freistellen
        </button>
      )}
    </li>
  );
}

export function BesetzungTab({
  detail,
  darfBearbeiten,
  onGeaendert,
}: {
  detail: PositionDetail;
  // bearbeiten ODER rechte_verwalten (wie im Backend fuer das Beenden von Besetzungen)
  darfBearbeiten: boolean;
  onGeaendert: () => void;
}) {
  const queryClient = useQueryClient();
  const { data: users } = useQuery({ queryKey: ["users", "auswahl"], queryFn: usersApi.auswahl, enabled: darfBearbeiten });
  const [userId, setUserId] = useState("");
  const [art, setArt] = useState<BesetzungArt>("regulaer");
  const [von, setVon] = useState("");
  const [bis, setBis] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [warnung, setWarnung] = useState<string | null>(null);

  const geaendert = () => {
    queryClient.invalidateQueries({ queryKey: ["org-positionen"] });
    onGeaendert();
  };

  const besetzen = useMutation({
    mutationFn: () =>
      organigrammApi.besetzen(detail.id, {
        user_id: userId,
        art,
        gueltig_von: von ? new Date(von).toISOString() : null,
        gueltig_bis: bis ? new Date(bis).toISOString() : null,
      }),
    onSuccess: (r) => {
      setFehler(null);
      setWarnung(r.warnung ?? null);
      setUserId("");
      setVon("");
      setBis("");
      geaendert();
    },
    onError: (err) => setFehler(verstaendlicherFehler(err, "Besetzen fehlgeschlagen")),
  });

  const beenden = useMutation({
    mutationFn: (id: string) => organigrammApi.besetzungBeenden(id),
    onSuccess: () => {
      setFehler(null);
      setWarnung(null);
      geaendert();
    },
    onError: (err) => setFehler(verstaendlicherFehler(err, "Freistellen fehlgeschlagen")),
  });

  const aktiveIds = new Set(detail.besetzungen?.map((b) => b.id) ?? []);
  const aktive = detail.besetzungen ?? [];
  const historie = detail.alle_besetzungen.filter((b) => !aktiveIds.has(b.id));
  const archiviert = !!detail.archiviert_am;
  const vertretungOhneEnde = art === "vertretung" && !bis;

  const optionen = (users ?? [])
    .filter((u) => u.aktiv && u.role !== "super_admin")
    .map((u) => ({ value: u.id, label: u.name, sublabel: u.account_typ_name ?? undefined }));

  function absenden(e: FormEvent) {
    e.preventDefault();
    if (!userId || vertretungOhneEnde) return;
    besetzen.mutate();
  }

  return (
    <div role="tabpanel" id="org-tabpanel-besetzung" aria-labelledby="org-tab-besetzung" className="space-y-5 p-4">
      <div
        className={`flex items-center gap-2 rounded-[10px] px-3 py-2 text-sm ${
          istUnterbesetzt(detail) ? "bg-st-arbeit-bg text-st-arbeit" : "bg-fill text-label"
        }`}
        role={istUnterbesetzt(detail) ? "status" : undefined}
      >
        {istUnterbesetzt(detail) && <AlertTriangle size={15} strokeWidth={2} aria-hidden="true" />}
        <span className="tabular-nums">
          Besetzt {detail.ist_besetzung ?? 0} von {detail.soll_besetzung ?? 0}
        </span>
        {istUnterbesetzt(detail) && <span>– Soll-Besetzung nicht erreicht</span>}
      </div>

      {warnung && (
        <p role="status" className="flex items-start gap-2 rounded-[10px] bg-st-arbeit-bg px-3 py-2 text-sm text-st-arbeit">
          <AlertTriangle size={15} strokeWidth={2} className="mt-0.5 shrink-0" aria-hidden="true" />
          {warnung}
        </p>
      )}
      {fehler && (
        <p role="alert" className="text-sm text-st-fehlt">
          {fehler}
        </p>
      )}

      <section>
        <h3 className="mb-1.5 text-xs font-semibold tracking-wide text-label2 uppercase">Aktuell besetzt</h3>
        {aktive.length > 0 ? (
          <ul className="divide-y divide-sep overflow-hidden rounded-[12px] bg-cell">
            {aktive.map((b) => (
              <BesetzungZeile
                key={b.id}
                b={b}
                darfBeenden={darfBearbeiten && !archiviert}
                beendenLaeuft={beenden.isPending}
                onBeenden={() => {
                  if (window.confirm(`${b.name ?? "Die Person"} von dieser Position freistellen? Die Besetzung endet sofort und bleibt in der Historie.`)) {
                    beenden.mutate(b.id);
                  }
                }}
              />
            ))}
          </ul>
        ) : (
          <p className="rounded-[12px] bg-cell px-3 py-3 text-sm text-label2">
            {detail.status === "geplant" ? "Platzhalter – keine Besetzung vorgesehen." : "Vakant – niemand zugewiesen."}
          </p>
        )}
      </section>

      {darfBearbeiten && !archiviert && (
        <section>
          <h3 className="mb-1.5 text-xs font-semibold tracking-wide text-label2 uppercase">Person zuweisen</h3>
          <form onSubmit={absenden} className="card-ap space-y-3 p-3">
            <div>
              <label className="mb-1 block text-sm font-medium text-label">Mitarbeiter</label>
              <SearchableSelect options={optionen} value={userId} onChange={setUserId} placeholder="Mitarbeiter suchen…" />
            </div>
            <SegmentedControl
              ariaLabel="Art der Besetzung"
              optionen={[
                { wert: "regulaer", label: "Regulär" },
                { wert: "vertretung", label: "Vertretung" },
              ]}
              wert={art}
              onChange={setArt}
            />
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label htmlFor="bes-von" className="mb-1 block text-sm font-medium text-label">
                  Von (optional)
                </label>
                <input id="bes-von" type="datetime-local" value={von} onChange={(e) => setVon(e.target.value)} className="field-ap" />
              </div>
              <div>
                <label htmlFor="bes-bis" className="mb-1 block text-sm font-medium text-label">
                  Bis {art === "vertretung" ? "(Pflicht)" : "(optional)"}
                </label>
                <input id="bes-bis" type="datetime-local" value={bis} onChange={(e) => setBis(e.target.value)} className="field-ap" required={art === "vertretung"} />
              </div>
            </div>
            <button type="submit" disabled={!userId || vertretungOhneEnde || besetzen.isPending} className="btn-ap-primary">
              Zuweisen
            </button>
          </form>
        </section>
      )}

      {historie.length > 0 && (
        <section>
          <h3 className="mb-1.5 text-xs font-semibold tracking-wide text-label2 uppercase">Historie</h3>
          <ul className="divide-y divide-sep overflow-hidden rounded-[12px] bg-cell">
            {historie.map((b) => (
              <BesetzungZeile key={b.id} b={b} darfBeenden={false} beendenLaeuft={false} />
            ))}
          </ul>
        </section>
      )}
    </div>
  );
}
