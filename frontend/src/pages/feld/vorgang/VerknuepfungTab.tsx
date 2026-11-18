import { ArrowUp, CheckCheck, ClipboardList, Clock, Euro, Flag, Folder, GitBranch, Lock, LockOpen, Repeat2, Rss, type LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { Fortschritt } from "../../../components/apple/Fortschritt";
import { Switch } from "../../../components/apple/Switch";
import { VorgangStatusPille } from "../../../components/VorgangStatusPille";
import { SkeletonList } from "../../../components/Skeleton";
import type { Vorgang, VorgangHerkunftArt, VorgangHerkunftEintrag, VorgangVerknuepfung } from "../../../types";
import { formatDatum, formatEuro } from "../../../utils/format";
import { auftragLink, istVorgangErledigt, projektLink } from "../../../utils/verknuepfung";
import { ABSCHNITT_AKTION, Abschnitt } from "./Abschnitt";
import { useZweispaltig } from "./useZweispaltig";

const ICON: Record<VorgangHerkunftArt, LucideIcon> = {
  projekt_angelegt: Folder,
  auftrag_angelegt: ClipboardList,
  vorgang_angelegt: Rss,
  folge_vorgang: GitBranch,
  zuordnung_geaendert: Repeat2,
  eigenstaendig_gesetzt: Lock,
  eigenstaendig_aufgehoben: LockOpen,
};

const KACHEL = "flex h-7 w-7 shrink-0 items-center justify-center rounded-[var(--radius-ap-md)] bg-fill text-label2";

const stunden = (sekunden: number) => `${(Math.round(sekunden / 360) / 10).toLocaleString("de-DE")} h`;

/** Der Server liefert den Satz fertig; der Verweis-Name darin wird zum Link, damit die Kette
 * als Fließtext lesbar bleibt. Fehlt der Name im Satz, hängt der Link hinten an. */
function eintragText(e: VorgangHerkunftEintrag, link: ((e: VorgangHerkunftEintrag) => (() => void) | null)): ReactNode {
  const klick = e.ref_id && e.ref_label ? link(e) : null;
  if (!klick || !e.ref_label) return e.text;
  const knopf = (
    <button type="button" onClick={klick} className="text-tint-text underline-offset-2 hover:underline">
      {e.ref_label}
    </button>
  );
  const i = e.text.indexOf(e.ref_label);
  if (i < 0) return <>{e.text} · {knopf}</>;
  return (
    <>
      {e.text.slice(0, i)}
      {knopf}
      {e.text.slice(i + e.ref_label.length)}
    </>
  );
}

/** Tab "Projekt" (Feld-App: Abschnitt) eines Vorgangs: Herkunft, Rückmeldung nach oben, Freigabe
 * ("Eigenständig führen", nur mit Recht) und die Geschwister im selben Auftrag. */
export function VerknuepfungTab({
  vorgang,
  daten,
  laedt,
  fehler,
  onErneut,
  linksAktiv,
  navigate,
  vorgangPfad,
  onEigenstaendig,
  eigenstaendigPending,
  zweispaltigMoeglich,
  wrapperProps,
}: {
  vorgang: Vorgang;
  daten: VorgangVerknuepfung | undefined;
  laedt: boolean;
  fehler: boolean;
  onErneut: () => void;
  /** Projekt-/Auftrag-Links aktiv (Office mit Recht projekte/sehen). */
  linksAktiv: boolean;
  navigate: (to: string) => void;
  vorgangPfad: (id: string) => string;
  onEigenstaendig: (an: boolean) => void;
  eigenstaendigPending: boolean;
  zweispaltigMoeglich: boolean;
  /** id/hidden/role des Tab-Panels, kommt von der Seite (siehe istAktiverTab). */
  wrapperProps: { hidden: boolean; role?: "tabpanel"; "aria-labelledby"?: string };
}) {
  const { wurzel, zweispaltig } = useZweispaltig(zweispaltigMoeglich);
  const { hidden, ...rolle } = wrapperProps;

  const linkFuer = (e: VorgangHerkunftEintrag) => {
    if (!e.ref_id) return null;
    if (e.ref_typ === "vorgang") return () => navigate(vorgangPfad(e.ref_id!));
    if (!linksAktiv) return null;
    if (e.ref_typ === "projekt") return () => navigate(projektLink(e.ref_id!));
    if (e.ref_typ === "auftrag") return () => navigate(auftragLink(e.ref_id!));
    return null;
  };

  let inhalt: ReactNode;
  if (laedt) {
    inhalt = <SkeletonList count={3} />;
  } else if (fehler || !daten) {
    inhalt = (
      <div className="card-ap p-4 text-fliess text-label2">
        Die Zuordnung konnte nicht geladen werden.{" "}
        <button type="button" onClick={onErneut} className="font-medium text-tint-text">
          Erneut versuchen
        </button>
      </div>
    );
  } else {
    const r = daten.rueckmeldung;
    const ziel = daten.auftrag ? "Auftrag" : "Projekt";
    const zielLink = daten.auftrag ? auftragLink(daten.auftrag.id) : daten.projekt ? projektLink(daten.projekt.id) : null;
    const nenner = r.arbeitszeit_sekunden_auftrag;
    const zeilen: { icon: LucideIcon; label: string; wert: ReactNode }[] = [
      {
        icon: Clock,
        label: "Arbeitszeit",
        wert: (
          <>
            <span className="font-medium text-label">{stunden(r.arbeitszeit_sekunden)}</span>
            {nenner != null && <span className="text-label2"> von {stunden(nenner)} im Auftrag</span>}
          </>
        ),
      },
      {
        icon: Euro,
        label: "Positionen",
        wert: (
          <>
            <span className="font-medium text-label">{r.positionen_anzahl}</span>
            {r.positionen_netto != null && <span className="text-label2"> · {formatEuro(r.positionen_netto)} netto</span>}
          </>
        ),
      },
      {
        icon: Flag,
        label: "Offene Mängel",
        wert: <span className={r.offene_maengel > 0 ? "font-medium text-st-fehlt" : "text-label"}>{r.offene_maengel}</span>,
      },
      { icon: CheckCheck, label: "Status", wert: <VorgangStatusPille status={r.status} /> },
    ];

    const herkunft = (
      <Abschnitt titel="Herkunft">
        <ol className="space-y-0">
          {daten.herkunft.map((e, i) => {
            const Icon = ICON[e.art] ?? GitBranch;
            const letzte = i === daten.herkunft.length - 1;
            const meta = [formatDatum(e.datum), e.person_name, e.zusatz].filter(Boolean).join(" · ");
            return (
              <li key={`${e.art}-${i}`} className="relative flex gap-3 pb-3 last:pb-0" aria-current={e.aktuell ? "step" : undefined}>
                {!letzte && <span aria-hidden="true" className="absolute top-8 bottom-0 left-[13px] w-px bg-sep" />}
                <span className={e.aktuell ? `${KACHEL} bg-tintbg text-tint-text` : KACHEL}>
                  <Icon size={15} strokeWidth={1.5} aria-hidden="true" />
                </span>
                <div className="min-w-0 text-fliess">
                  <p className={e.aktuell ? "font-semibold text-label" : "text-label"}>{eintragText(e, linkFuer)}</p>
                  <p className="text-meta text-label2">{meta}</p>
                </div>
              </li>
            );
          })}
        </ol>
      </Abschnitt>
    );

    const rueckmeldung = (
      <Abschnitt
        titel={`Rückmeldung an ${daten.auftrag ? "den Auftrag" : "das Projekt"}`}
        aktion={
          linksAktiv && zielLink ? (
            <button type="button" onClick={() => navigate(zielLink)} className={ABSCHNITT_AKTION}>
              {ziel} öffnen
            </button>
          ) : undefined
        }
      >
        <dl className="space-y-2 text-fliess">
          {zeilen.map((z) => (
            <div key={z.label} className="flex items-center gap-3">
              <span className={KACHEL}>
                <z.icon size={15} strokeWidth={1.5} aria-hidden="true" />
              </span>
              <dt className="flex-1 text-label">{z.label}</dt>
              <dd className="text-right">{z.wert}</dd>
            </div>
          ))}
        </dl>
        <p className="mt-3 flex items-center gap-1.5 text-meta text-label2">
          <ArrowUp size={13} strokeWidth={1.5} aria-hidden="true" />
          wird automatisch im Auftrag und im Projekt mitgezählt
        </p>
      </Abschnitt>
    );

    const eigenstaendig = !!vorgang.verknuepfung_eigenstaendig;
    const freigabe = vorgang.darf_eigenstaendig_setzen ? (
      <Abschnitt titel="Freigabe">
        <div className="flex items-start gap-3 rounded-[var(--radius-ap-card)] bg-fill p-3">
          <Lock size={16} strokeWidth={1.5} aria-hidden="true" className="mt-0.5 shrink-0 text-label2" />
          <div className="min-w-0 flex-1 text-sekundaer text-label2">
            <p className="text-fliess font-medium text-label">Eigenständig führen</p>
            {eigenstaendig ? (
              <p>
                Eigenständig geführt – seit {formatDatum(vorgang.verknuepfung_eigenstaendig_am)}
                {vorgang.verknuepfung_eigenstaendig_von_name ? ` von ${vorgang.verknuepfung_eigenstaendig_von_name}` : ""}. Projekt und
                Auftrag sind in diesem Vorgang ausgeblendet (auch für Techniker und Nachunternehmer), Änderungen am Auftrag wirken nicht
                auf ihn. Zeit, Positionen, Mängel und Status fließen weiter zurück.
              </p>
            ) : (
              <p>
                Blendet Projekt und Auftrag in diesem Vorgang aus (auch für Techniker und Nachunternehmer) und koppelt ihn von Änderungen
                am Auftrag ab. Zeit, Positionen, Mängel und Status fließen weiter zurück.
              </p>
            )}
          </div>
          <span className={eigenstaendigPending ? "pointer-events-none opacity-50" : ""}>
            <Switch checked={eigenstaendig} onChange={onEigenstaendig} ariaLabel="Eigenständig führen" />
          </span>
        </div>
      </Abschnitt>
    ) : null;

    const erledigt = daten.geschwister.filter((g) => istVorgangErledigt(g.status)).length;
    const geschwister =
      daten.auftrag && daten.geschwister.length > 0 ? (
        <Abschnitt titel="Im selben Auftrag" aktion={<Fortschritt erledigt={erledigt} gesamt={daten.geschwister.length} />}>
          <ul className="divide-y-[0.5px] divide-sep">
            {daten.geschwister.map((g) => (
              <li key={g.id}>
                <button
                  type="button"
                  onClick={() => !g.ist_aktuell && navigate(vorgangPfad(g.id))}
                  aria-current={g.ist_aktuell ? "true" : undefined}
                  className={`flex w-full items-center gap-3 rounded-[var(--radius-ap-md)] px-2 py-2 text-left text-fliess ${
                    g.ist_aktuell ? "bg-tintbg" : "hover:bg-fill"
                  }`}
                >
                  <span className="shrink-0 text-label2">{g.vorgangsnummer}</span>
                  <span className={`min-w-0 flex-1 truncate ${g.ist_aktuell ? "font-semibold text-label" : "text-label"}`}>{g.titel}</span>
                  <VorgangStatusPille status={g.status} />
                </button>
              </li>
            ))}
          </ul>
        </Abschnitt>
      ) : null;

    inhalt = zweispaltig ? (
      <div className="grid grid-cols-[minmax(0,1fr)_320px] items-start gap-x-4">
        <div className="min-w-0">
          {herkunft}
          {rueckmeldung}
        </div>
        <div className="min-w-0 border-l-[0.5px] border-sep pl-4">
          {freigabe}
          {geschwister}
        </div>
      </div>
    ) : (
      <div className="space-y-4 in-[.office-panel]:space-y-0">
        {herkunft}
        {rueckmeldung}
        {freigabe}
        {geschwister}
      </div>
    );
  }

  return (
    <div id="abschnitt-projekt" ref={wurzel} className={`scroll-mt-4 ${hidden ? "hidden" : ""}`} {...rolle}>
      {inhalt}
    </div>
  );
}
