import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Mail, Plus, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";

import { mailApi } from "../../api/endpoints";
import { Switch } from "../../components/apple/Switch";
import { AbschnittskopfB } from "../../components/apple/AbschnittsKopf";
import { GroupedList, GroupedListRow } from "../../components/apple/GroupedList";
import { useBestaetigung } from "../../components/ConfirmDialog";
import { FehlerZustand } from "../../components/FehlerZustand";
import { Hinweiskasten } from "../../components/Hinweiskasten";
import { SkeletonList } from "../../components/Skeleton";
import { StatusBadge } from "../../components/StatusBadge";
import type { MailAccount, MailAnbieter } from "../../types";
import { SeitenKopf } from "../OfficeUi";
import { PostfachEinrichten } from "./PostfachEinrichten";
import { ServerEinstellungen, werteAusAnbieter, type ServerWerte } from "./ServerEinstellungen";

function serverWerteVon(konto: MailAccount): ServerWerte {
  return {
    imap_host: konto.imap_host,
    imap_port: konto.imap_port,
    imap_verschluesselung: konto.imap_verschluesselung,
    imap_benutzername: konto.imap_benutzername,
    smtp_host: konto.smtp_host,
    smtp_port: konto.smtp_port,
    smtp_verschluesselung: konto.smtp_verschluesselung,
    smtp_benutzername: konto.smtp_benutzername,
  };
}

function KontoKachel({ anbieter }: { anbieter: MailAnbieter | undefined }) {
  return anbieter ? (
    <span
      className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[9px] text-sekundaer font-bold text-white"
      style={{ backgroundColor: anbieter.farbe }}
      aria-hidden="true"
    >
      {anbieter.kuerzel}
    </span>
  ) : (
    <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-[9px] bg-fill text-label2" aria-hidden="true">
      <Mail size={16} strokeWidth={2} />
    </span>
  );
}

function ZeilenFeld({ label, children, last }: { label: string; children: React.ReactNode; last?: boolean }) {
  return (
    <GroupedListRow last={last}>
      <span className="w-28 shrink-0 text-fliess text-label2">{label}</span>
      <div className="min-w-0 flex-1">{children}</div>
    </GroupedListRow>
  );
}

const ZEILEN_INPUT = "w-full bg-transparent py-1 text-fliess text-label outline-none focus-visible:underline";

function AllgemeinSignatur({ konto, anbieter }: { konto: MailAccount; anbieter: MailAnbieter | undefined }) {
  const queryClient = useQueryClient();
  const [name, setName] = useState(konto.name);
  const [email, setEmail] = useState(konto.email_adresse);
  const [signatur, setSignatur] = useState(konto.signatur ?? "");
  const [passwortAendern, setPasswortAendern] = useState(false);
  const [passwort, setPasswort] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);

  const speichern = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: () =>
      mailApi.accounts.update(konto.id, {
        name: name.trim(),
        email_adresse: email.trim(),
        signatur: signatur.trim() ? signatur : null,
        // Das Backend prüft die Verbindung nur mit vollständigen Zugangsdaten
        ...(passwort ? { passwort, ...serverWerteVon(konto) } : {}),
      }),
    onMutate: () => setFehler(null),
    onSuccess: () => {
      setPasswort("");
      setPasswortAendern(false);
      queryClient.invalidateQueries({ queryKey: ["mail-accounts"] });
    },
    onError: (err: Error) => setFehler(err.message),
  });

  const geaendert =
    name !== konto.name || email !== konto.email_adresse || signatur !== (konto.signatur ?? "") || !!passwort;

  return (
    <div>
      <AbschnittskopfB titel="Allgemein" />
      <GroupedList>
        <ZeilenFeld label="Name">
          <input aria-label="Name" className={ZEILEN_INPUT} value={name} onChange={(e) => setName(e.target.value)} />
        </ZeilenFeld>
        <ZeilenFeld label="E-Mail-Adresse">
          <input
            aria-label="E-Mail-Adresse"
            type="email"
            className={ZEILEN_INPUT}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </ZeilenFeld>
        <ZeilenFeld label="Anbieter">
          <span className="flex flex-wrap items-center gap-2 text-fliess text-label">
            {anbieter?.name ?? "Eigener Server"}
            {konto.server_angepasst && (
              <span className="rounded-full bg-fill px-2 py-0.5 text-meta font-medium text-label2">Server angepasst</span>
            )}
          </span>
        </ZeilenFeld>
        <ZeilenFeld label="Passwort" last>
          {passwortAendern ? (
            <div className="flex items-center gap-2">
              <input
                aria-label="Neues Passwort"
                type="password"
                autoComplete="new-password"
                autoFocus
                className={ZEILEN_INPUT}
                value={passwort}
                placeholder="Neues Passwort"
                onChange={(e) => setPasswort(e.target.value)}
              />
              <button
                type="button"
                className="shrink-0 text-fliess text-tint"
                onClick={() => {
                  setPasswort("");
                  setPasswortAendern(false);
                }}
              >
                Abbrechen
              </button>
            </div>
          ) : (
            <div className="flex items-center justify-between gap-2">
              <span className="text-fliess text-label">••••••••</span>
              <button type="button" className="text-fliess text-tint" onClick={() => setPasswortAendern(true)}>
                Ändern
              </button>
            </div>
          )}
        </ZeilenFeld>
      </GroupedList>

      <AbschnittskopfB titel="Signatur" />
      <div className="rounded-[var(--radius-ap-card)] bg-cell p-3">
        <textarea
          aria-label="Signatur"
          rows={4}
          className="w-full resize-none bg-transparent text-fliess text-label outline-none"
          placeholder="Wird an jede gesendete Mail angehängt"
          value={signatur}
          onChange={(e) => setSignatur(e.target.value)}
        />
      </div>

      {fehler && (
        <div className="mt-3">
          <Hinweiskasten ton="fehler">{fehler}</Hinweiskasten>
        </div>
      )}
      <div className="mt-3 flex justify-end">
        <button
          type="button"
          disabled={!geaendert || !name.trim() || !email.trim() || speichern.isPending}
          onClick={() => speichern.mutate()}
          className="btn-ap-primary flex items-center gap-1.5 px-4 disabled:opacity-40"
        >
          {speichern.isPending && <Loader2 size={13} className="animate-spin" aria-hidden="true" />}
          Speichern
        </button>
      </div>
    </div>
  );
}

function ServerBereich({ konto, anbieter }: { konto: MailAccount; anbieter: MailAnbieter | undefined }) {
  const queryClient = useQueryClient();
  const vorgabe = anbieter ? werteAusAnbieter(anbieter, konto.email_adresse) : null;
  const [selbst, setSelbst] = useState(konto.server_angepasst || !anbieter);
  const [werte, setWerte] = useState<ServerWerte>(serverWerteVon(konto));
  const [passwort, setPasswort] = useState("");
  const [fehler, setFehler] = useState<string | null>(null);
  const [testStatus, setTestStatus] = useState<"idle" | "ok" | "fehler">("idle");
  const [testFehler, setTestFehler] = useState<string | null>(null);

  const speichern = useMutation({
    meta: { erfolg: "Gespeichert" },
    mutationFn: () => {
      if (!selbst && anbieter) {
        // Zurück auf die Vorgabe: nur Host/Port/Verschlüsselung, Benutzernamen bleiben unberührt
        return mailApi.accounts.update(konto.id, {
          imap_host: anbieter.imap_host,
          imap_port: anbieter.imap_port,
          imap_verschluesselung: anbieter.imap_verschluesselung,
          smtp_host: anbieter.smtp_host,
          smtp_port: anbieter.smtp_port,
          smtp_verschluesselung: anbieter.smtp_verschluesselung,
        });
      }
      return mailApi.accounts.update(konto.id, { ...werte, ...(passwort ? { passwort } : {}) });
    },
    onMutate: () => setFehler(null),
    onSuccess: () => {
      setPasswort("");
      queryClient.invalidateQueries({ queryKey: ["mail-accounts"] });
    },
    onError: (err: Error) => setFehler(err.message),
  });

  const testen = useMutation({
    mutationFn: () => mailApi.testVerbindung({ ...werte, passwort }),
    onMutate: () => {
      setTestStatus("idle");
      setTestFehler(null);
    },
    onSuccess: () => setTestStatus("ok"),
    onError: (err: Error) => {
      setTestStatus("fehler");
      setTestFehler(err.message);
    },
  });

  const schalten = (an: boolean) => {
    if (!anbieter) return;
    setSelbst(an);
    if (!an && vorgabe) setWerte({ ...werte, ...vorgabe, imap_benutzername: werte.imap_benutzername, smtp_benutzername: werte.smtp_benutzername });
  };

  return (
    <div>
      <AbschnittskopfB titel="Servereinstellungen" />
      <div className="space-y-4 rounded-[var(--radius-ap-card)] bg-cell p-4">
        <div className="flex items-center justify-between gap-3">
          <div>
            <p className="text-zeile font-semibold text-label">Selbst festlegen</p>
            <p className="text-sekundaer text-label2">
              {anbieter
                ? `Aus: FieldVibe nutzt die hinterlegten Werte für ${anbieter.name}.`
                : "Für dieses Postfach ist kein Anbieter hinterlegt."}
            </p>
          </div>
          <Switch checked={selbst} onChange={schalten} ariaLabel="Servereinstellungen selbst festlegen" />
        </div>

        {selbst && (
          <>
            {anbieter && (
              <Hinweiskasten ton="info">
                Nur ändern, wenn dein Anbieter abweichende Werte vorgibt. Zurück auf die {anbieter.name}-Vorgabe:
                Schalter ausschalten.
              </Hinweiskasten>
            )}
            <ServerEinstellungen
              werte={werte}
              onChange={(w) => {
                setWerte(w);
                setTestStatus("idle");
              }}
              vorgabe={vorgabe}
            />
            <div>
              <label htmlFor="server-passwort" className="mb-1 block text-sekundaer font-medium text-label2">
                Passwort (für den Verbindungstest)
              </label>
              <input
                id="server-passwort"
                type="password"
                autoComplete="new-password"
                className="field-ap"
                value={passwort}
                onChange={(e) => setPasswort(e.target.value)}
              />
              <p className="mt-1 text-meta text-label2">
                Das gespeicherte Passwort wird nicht angezeigt. Zum Testen bitte erneut eingeben.
              </p>
            </div>
          </>
        )}

        {testStatus === "ok" && (
          <p className="flex items-center gap-1.5 text-sekundaer font-medium text-st-erledigt">
            <Check size={14} aria-hidden="true" /> Verbindung erfolgreich.
          </p>
        )}
        {testStatus === "fehler" && testFehler && <Hinweiskasten ton="fehler">{testFehler}</Hinweiskasten>}
        {fehler && <Hinweiskasten ton="fehler">{fehler}</Hinweiskasten>}

        <div className="flex flex-wrap items-center justify-between gap-2">
          {selbst ? (
            <button
              type="button"
              disabled={!passwort || !werte.imap_host || !werte.smtp_host || testen.isPending}
              onClick={() => testen.mutate()}
              className="btn-ap flex items-center gap-1.5 disabled:opacity-40"
            >
              {testen.isPending && <Loader2 size={13} className="animate-spin" aria-hidden="true" />}
              Verbindung testen
            </button>
          ) : (
            <span />
          )}
          <button
            type="button"
            disabled={speichern.isPending}
            onClick={() => speichern.mutate()}
            className="btn-ap-primary flex items-center gap-1.5 px-4 disabled:opacity-40"
          >
            {speichern.isPending && <Loader2 size={13} className="animate-spin" aria-hidden="true" />}
            Speichern
          </button>
        </div>
      </div>
    </div>
  );
}

function AbgleichUndTrennen({ konto }: { konto: MailAccount }) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const bestaetigen = useBestaetigung();

  const trennen = useMutation({
    meta: { erfolg: "Postfach getrennt" },
    mutationFn: () => mailApi.accounts.delete(konto.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["mail-accounts"] });
      navigate("/postfach");
    },
  });

  return (
    <div>
      <AbschnittskopfB titel="Abgleich" />
      <div className="rounded-[var(--radius-ap-card)] bg-cell p-4 text-fliess">
        {konto.letzter_sync_fehler ? (
          <p className="text-st-fehlt">Letzter Abgleich fehlgeschlagen: {konto.letzter_sync_fehler}</p>
        ) : konto.letzter_sync_am ? (
          <p className="flex items-center gap-2 text-label">
            <Check size={15} className="text-st-erledigt" aria-hidden="true" />
            Zuletzt abgeglichen{" "}
            {new Date(konto.letzter_sync_am).toLocaleString("de-DE", {
              day: "2-digit",
              month: "2-digit",
              hour: "2-digit",
              minute: "2-digit",
            })}
          </p>
        ) : (
          <p className="text-label2">Noch nicht abgeglichen.</p>
        )}
      </div>
      <button
        type="button"
        disabled={trennen.isPending}
        onClick={async () => {
          if (
            !(await bestaetigen({
              titel: `Postfach „${konto.name}“ trennen?`,
              text: "Die Zugangsdaten und die in FieldVibe gespeicherten Nachrichten dieses Postfachs werden gelöscht. Beim Anbieter bleibt alles unverändert.",
              bestaetigenLabel: "Trennen",
            }))
          )
            return;
          trennen.mutate();
        }}
        className="btn-ap mt-5 flex items-center gap-1.5 text-st-fehlt"
      >
        <Trash2 size={14} strokeWidth={2} aria-hidden="true" /> Postfach trennen
      </button>
    </div>
  );
}

/** Eigene Seite für Postfach-Einstellungen: links alle Postfächer, rechts das
 * ausgewählte (?konto=<id>). */
export function PostfachEinstellungenPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const [neu, setNeu] = useState(params.get("neu") === "1");

  const { data: konten, isLoading, error, refetch } = useQuery({
    queryKey: ["mail-accounts"],
    queryFn: () => mailApi.accounts.list(),
  });
  const { data: anbieterListe, isLoading: anbieterLaedt } = useQuery({
    queryKey: ["mail-anbieter"],
    queryFn: () => mailApi.anbieter(),
    staleTime: Infinity,
  });

  const kontoId = params.get("konto");
  const aktiv = konten?.find((k) => k.id === kontoId) ?? konten?.[0];

  // Ohne gültige Auswahl die URL auf das erste Konto ziehen, damit Reload/Teilen stimmt.
  useEffect(() => {
    if (aktiv && kontoId !== aktiv.id) setParams({ konto: aktiv.id }, { replace: true });
  }, [aktiv, kontoId, setParams]);

  const kopf = (
    <>
      <Link to="/postfach" className="mb-1 inline-block text-sekundaer font-medium text-tint">
        ‹ Postfach
      </Link>
      <SeitenKopf titel="Postfach-Einstellungen" />
    </>
  );

  if (isLoading || anbieterLaedt) {
    return (
      <div>
        {kopf}
        <SkeletonList count={3} />
      </div>
    );
  }
  if (error) {
    return (
      <div>
        {kopf}
        <FehlerZustand fehler={error} was="Die Postfächer" onErneut={() => void refetch()} />
      </div>
    );
  }

  const anbieterVon = (k: MailAccount) => anbieterListe?.find((a) => a.id === k.anbieter_id);

  return (
    <div>
      {kopf}
      <div className="grid max-w-[1400px] grid-cols-1 items-start gap-5 lg:grid-cols-[300px_minmax(0,1fr)]">
        <nav aria-label="Postfächer" className="rounded-[var(--radius-ap-card)] bg-card p-2">
          {(konten ?? []).map((k) => {
            const ausgewaehlt = !neu && k.id === aktiv?.id;
            return (
              <button
                key={k.id}
                type="button"
                aria-current={ausgewaehlt ? "true" : undefined}
                onClick={() => {
                  setNeu(false);
                  setParams({ konto: k.id });
                }}
                className={`flex w-full items-center gap-3 rounded-[var(--radius-ap-md)] p-2 text-left ${
                  ausgewaehlt ? "bg-tintbg" : "hover:bg-fill"
                }`}
              >
                <KontoKachel anbieter={anbieterVon(k)} />
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-fliess font-semibold text-label">{k.name}</span>
                  <span className="block truncate text-meta text-label2">{k.email_adresse}</span>
                </span>
                <StatusBadge label={k.letzter_sync_fehler ? "Fehler" : "OK"} tone={k.letzter_sync_fehler ? "rose" : "emerald"} />
              </button>
            );
          })}
          <button
            type="button"
            onClick={() => setNeu(true)}
            className="mt-1 flex w-full items-center gap-2 rounded-[var(--radius-ap-md)] p-2 text-fliess font-medium text-tint hover:bg-fill"
          >
            <Plus size={16} strokeWidth={2} aria-hidden="true" /> Weiteres Postfach verbinden
          </button>
        </nav>

        {neu || !aktiv ? (
          <PostfachEinrichten
            layout="office"
            onFertig={() => setNeu(false)}
            onAbbrechen={konten && konten.length > 0 ? () => setNeu(false) : () => navigate("/postfach")}
          />
        ) : (
          <div key={aktiv.id} className="grid grid-cols-1 items-start gap-x-5 xl:grid-cols-2">
            <div>
              <AllgemeinSignatur konto={aktiv} anbieter={anbieterVon(aktiv)} />
              <AbgleichUndTrennen konto={aktiv} />
            </div>
            <ServerBereich konto={aktiv} anbieter={anbieterVon(aktiv)} />
          </div>
        )}
      </div>
    </div>
  );
}
