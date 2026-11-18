import { useQuery } from "@tanstack/react-query";
import { CalendarDays, ChevronRight, ListChecks, Timer } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";

import { abwesenheitenApi, arbeitszeitApi, zeiterfassungApi } from "../../api/endpoints";
import { LaeuftPille } from "../../components/apple/LaeuftPille";
import { StatusPille } from "../../components/apple/StatusPille";
import { VORGANG_STATUS_LABEL, vorgangStatusZuToken } from "../../components/apple/status";
import { IconBadge, type IconTone } from "../../components/IconBadge";
import { VorgangStatusPille } from "../../components/VorgangStatusPille";
import { useAuth } from "../../context/AuthContext";
import { useVorgangsListe } from "../../hooks/useVorgangsListe";
import { ABWESENHEIT_ART_LABEL, formatTage, formatTageMitEinheit, formatZeitraum, resturlaubHinweis } from "../../utils/abwesenheit";
import { SALDO_TON_KLASSE, formatSaldo, parseStunden, saldoBis, saldoTon } from "../../utils/arbeitszeit";
import { formatStundenAlsHHMM } from "../../utils/duration";
import { heuteIso } from "../../utils/format";
import { istModulAktiv } from "../../utils/module";
import { formatUhrzeit, monatsGrenzen } from "../../utils/zeiterfassung";

function KartenKopf({ icon, tone, titel, rechts }: { icon: typeof Timer; tone: IconTone; titel: string; rechts?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-3">
      <IconBadge icon={icon} tone={tone} size="sm" />
      <h2 className="min-w-0 flex-1 truncate text-zeile font-semibold text-label">{titel}</h2>
      {rechts}
    </div>
  );
}

function Kennzahl({ label, wert, klasse = "text-label" }: { label: string; wert: string; klasse?: string }) {
  return (
    <div className="rounded-[var(--radius-ap-md)] bg-fill px-3 py-2.5">
      <p className="text-meta text-label2">{label}</p>
      <p className={`mt-0.5 text-titel-mobil font-semibold tabular-nums ${klasse}`}>{wert}</p>
    </div>
  );
}

const STUNDEN = (wert: string | undefined) => formatStundenAlsHHMM(parseStunden(wert));

/** Eigene Arbeitszeit: laufender Timer, Woche/Monat/Jahr und Monatssaldo.
 * Gleiche Query-Keys wie die Arbeitszeit-Seite, damit der Cache geteilt wird.
 * Fehler (z. B. fehlendes Statistik-Recht) blenden nur den jeweiligen Teil aus. */
export function ProfilArbeitszeitKarte() {
  const { currentUser } = useAuth();
  const kannErfassen = istModulAktiv(currentUser, "zeiterfassung");
  const kannAuswerten = istModulAktiv(currentUser, "statistik");

  const heute = heuteIso();
  const jetzt = new Date();
  const { von, bis } = monatsGrenzen(jetzt.getFullYear(), jetzt.getMonth());
  const saldoBisTag = saldoBis(von, bis, heute);

  const { data: laufend } = useQuery({
    queryKey: ["zeiterfassung-laufend"],
    queryFn: zeiterfassungApi.laufend,
    enabled: kannErfassen,
  });
  const { data: statistik } = useQuery({
    queryKey: ["zeiterfassung-statistik", currentUser?.id],
    queryFn: () => zeiterfassungApi.statistik(),
    enabled: kannErfassen || kannAuswerten,
    retry: false,
  });
  const { data: saldo } = useQuery({
    queryKey: ["arbeitszeit-saldo", currentUser?.id, von, saldoBisTag],
    queryFn: () => arbeitszeitApi.saldo({ von, bis: saldoBisTag!, user_id: currentUser!.id }),
    enabled: kannErfassen && !!currentUser && saldoBisTag !== null,
    retry: false,
  });

  if (!kannErfassen && !kannAuswerten) return null;
  const hatSoll = !!saldo && parseStunden(saldo.soll_stunden) > 0;

  return (
    <section className="card-ap flex h-full flex-col p-4" aria-label="Meine Arbeitszeit">
      <KartenKopf
        icon={Timer}
        tone="cyan"
        titel="Meine Arbeitszeit"
        rechts={laufend ? <LaeuftPille /> : undefined}
      />
      {laufend && (
        <Link
          to={laufend.vorgang_id ? `/vorgaenge/${laufend.vorgang_id}` : "/statistik"}
          className="mb-3 flex items-center gap-2 rounded-[var(--radius-ap-md)] bg-live-bg px-3 py-2.5 text-fliess text-label"
        >
          <span className="min-w-0 flex-1 truncate">
            {laufend.vorgangsnummer ?? "Ohne Vorgang"}
            {laufend.taetigkeit ? ` · ${laufend.taetigkeit}` : ""}
          </span>
          <span className="shrink-0 text-sekundaer tabular-nums text-label2">seit {formatUhrzeit(laufend.start_at)}</span>
        </Link>
      )}
      {statistik ? (
        <div className="grid grid-cols-3 gap-2">
          <Kennzahl label="Woche" wert={STUNDEN(statistik.wochenstunden)} />
          <Kennzahl label="Monat" wert={STUNDEN(statistik.monatsstunden)} />
          <Kennzahl label="Jahr" wert={STUNDEN(statistik.jahresstunden)} />
        </div>
      ) : (
        <p className="text-sekundaer text-label2">Keine Auswertung verfügbar.</p>
      )}
      {saldo && hatSoll && (
        <p className="mt-3 flex items-center justify-between text-fliess text-label2">
          <span>Monatssaldo (Ist {STUNDEN(saldo.ist_stunden)} von Soll {STUNDEN(saldo.soll_stunden)})</span>
          <span className={`font-semibold tabular-nums ${SALDO_TON_KLASSE[saldoTon(saldo.saldo_stunden)]}`}>
            {formatSaldo(saldo.saldo_stunden)}
          </span>
        </p>
      )}
      <Link to="/statistik" className="mt-auto flex items-center gap-1 pt-3 text-fliess font-medium text-tint-text">
        Zeiten ansehen <ChevronRight size={14} aria-hidden="true" />
      </Link>
    </section>
  );
}

/** Urlaubskonto des laufenden Jahres plus die nächsten eigenen Abwesenheiten.
 * Nur im Zeiterfassungs-Modul sichtbar, dort hängen die Abwesenheiten dran. */
export function ProfilUrlaubKarte({ mitLink }: { mitLink: boolean }) {
  const { currentUser } = useAuth();
  const kannErfassen = istModulAktiv(currentUser, "zeiterfassung");
  const heute = heuteIso();
  const jahr = new Date().getFullYear();

  const { data: konto } = useQuery({
    queryKey: ["abwesenheiten", "konto", currentUser?.id, jahr],
    queryFn: () => abwesenheitenApi.konto({ jahr }),
    enabled: kannErfassen && !!currentUser,
    retry: false,
  });
  const { data: liste } = useQuery({
    queryKey: ["abwesenheiten", "profil", currentUser?.id, heute],
    queryFn: () => abwesenheitenApi.liste({ von: heute, bis: `${jahr + 1}-12-31` }),
    enabled: kannErfassen && !!currentUser,
    retry: false,
  });

  if (!kannErfassen || (!konto && !liste)) return null;

  const kommende = (liste ?? [])
    .filter((a) => a.status === "offen" || a.status === "genehmigt")
    .sort((a, b) => a.von.localeCompare(b.von))
    .slice(0, 3);
  const verfall = konto ? resturlaubHinweis(konto) : null;

  return (
    <section className="card-ap flex h-full flex-col p-4" aria-label="Urlaub und Abwesenheit">
      <KartenKopf icon={CalendarDays} tone="amber" titel={`Urlaub ${jahr}`} />
      {konto && (
        <div className="grid grid-cols-3 gap-2">
          <Kennzahl label="Anspruch" wert={formatTage(konto.anspruch)} />
          <Kennzahl label="Genommen" wert={formatTage(konto.genommen)} />
          <Kennzahl
            label="Verbleibend"
            wert={formatTage(konto.verbleibend)}
            klasse={parseStunden(konto.verbleibend) < 0 ? "text-st-fehlt" : "text-label"}
          />
        </div>
      )}
      {konto && (parseStunden(konto.beantragt) > 0 || verfall) && (
        <p className="mt-3 text-sekundaer text-label2">
          {[parseStunden(konto.beantragt) > 0 ? `${formatTageMitEinheit(konto.beantragt)} beantragt` : null, verfall]
            .filter(Boolean)
            .join(" · ")}
        </p>
      )}
      <div className="mt-3">
        <p className="mb-1 text-meta font-semibold tracking-wide text-label2 uppercase">Nächste Abwesenheiten</p>
        {kommende.length === 0 ? (
          <p className="text-fliess text-label2">Keine geplant.</p>
        ) : (
          <ul className="space-y-1.5">
            {kommende.map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2 text-fliess">
                <span className="min-w-0 truncate text-label">
                  {ABWESENHEIT_ART_LABEL[a.art]} · <span className="tabular-nums text-label2">{formatZeitraum(a)}</span>
                </span>
                {a.status === "offen" && <StatusPille status="wartet" label="Offen" />}
              </li>
            ))}
          </ul>
        )}
      </div>
      {mitLink && (
        <Link to="/statistik" className="mt-auto flex items-center gap-1 pt-3 text-fliess font-medium text-tint-text">
          Beantragen und verwalten <ChevronRight size={14} aria-hidden="true" />
        </Link>
      )}
    </section>
  );
}

const OFFENE_STATUS = "neu,geplant,in_arbeit,wartet_kunde";
const ANZAHL_ZEILEN = 5;

const ANZAHL_KURZLISTE = 3;

/** Dem Nutzer zugewiesene, noch nicht abgeschlossene Vorgänge. Nutzt dieselbe
 * Feed-Query wie der Tab "Meine Vorgänge" und bleibt so per SSE aktuell.
 * `kurzliste` (Office): nur Nummer, Titel und Status der ersten drei, damit die
 * Karte neben Arbeitszeit/Urlaub nicht höher wird. */
export function ProfilVorgaengeKarte({ listeLink, kurzliste = false }: { listeLink: string; kurzliste?: boolean }) {
  const heute = heuteIso();
  const { data } = useVorgangsListe({ nur_meine: "true", status: OFFENE_STATUS });
  const items = data?.pages.flatMap((p) => p.items) ?? [];
  const mehr = (data?.pages.at(-1)?.next_cursor ?? null) !== null;
  if (!data) return null;

  return (
    <section className="card-ap flex h-full flex-col p-4" aria-label="Meine offenen Vorgänge">
      <KartenKopf
        icon={ListChecks}
        tone="indigo"
        titel="Meine offenen Vorgänge"
        rechts={<span className="text-fliess text-label2">{mehr ? `${items.length}+` : items.length}</span>}
      />
      {items.length === 0 ? (
        <p className="text-fliess text-label2">Dir ist aktuell nichts zugewiesen.</p>
      ) : kurzliste ? (
        <ul>
          {items.slice(0, ANZAHL_KURZLISTE).map((v) => (
            <li key={v.id} className="border-t border-sep first:border-t-0">
              <Link to={`/vorgaenge/${v.id}`} className="flex items-center gap-2 py-2 text-fliess hover:bg-fill">
                <span className="w-16 shrink-0 text-sekundaer tabular-nums text-label2">{v.vorgangsnummer}</span>
                <span className="min-w-0 flex-1 truncate text-label">{v.titel}</span>
                <VorgangStatusPille status={v.status} />
              </Link>
            </li>
          ))}
        </ul>
      ) : (
        <ul className="-mx-1 space-y-0.5">
          {items.slice(0, ANZAHL_ZEILEN).map((v) => (
            <li key={v.id}>
              <Link to={`/vorgaenge/${v.id}`} className="flex items-center gap-2 rounded-[var(--radius-ap-md)] px-1 py-2 hover:bg-fill">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-fliess text-label">{v.titel}</p>
                  <p className="truncate text-sekundaer text-label2">
                    {v.kunde_name}
                    {v.faelligkeit_am && (
                      <span className={v.faelligkeit_am < heute ? "font-semibold text-st-fehlt" : undefined}>
                        {" · fällig "}
                        {v.faelligkeit_am.split("-").reverse().join(".")}
                      </span>
                    )}
                  </p>
                </div>
                <StatusPille status={vorgangStatusZuToken(v.status)} label={VORGANG_STATUS_LABEL[v.status]} />
              </Link>
            </li>
          ))}
        </ul>
      )}
      <Link to={listeLink} className="mt-auto flex items-center gap-1 pt-3 text-fliess font-medium text-tint-text">
        Alle ansehen <ChevronRight size={14} aria-hidden="true" />
      </Link>
    </section>
  );
}
