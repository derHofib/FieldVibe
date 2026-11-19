import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { useAuth } from "../../context/AuthContext";
import type { Telefonat } from "../../types";
import { uhrLaden, uhrStarten, type AnrufUhr } from "./anrufUhr";
import { TelefonatSheet, type TelefonatSheetProps } from "./TelefonatSheet";

export interface TelefonatKontext {
  kundeId?: string | null;
  vorgangId?: string | null;
  kontextText?: string;
  partner?: { ansprechpartnerId?: string | null; name?: string; nummer?: string | null };
  vorgaenge?: TelefonatSheetProps["vorgaenge"];
  ansprechpartner?: TelefonatSheetProps["ansprechpartner"];
  kundeWaehlbar?: boolean;
}

interface TelefonatSteuerung {
  /** tel:-Klick: Uhr starten und Sheet mit Partner, Richtung "ausgehend" öffnen. */
  anrufen: (kontext: TelefonatKontext) => void;
  /** Sheet zum nachträglichen Erfassen (ohne Uhr). */
  erfassen: (kontext: TelefonatKontext) => void;
  bearbeiten: (telefonat: Telefonat) => void;
}

const LEER: TelefonatSteuerung = { anrufen: () => {}, erfassen: () => {}, bearbeiten: () => {} };
const TelefonatContext = createContext<TelefonatSteuerung>(LEER);

export function useTelefonat(): TelefonatSteuerung {
  return useContext(TelefonatContext);
}

interface Offen {
  schluessel: number;
  telefonat?: Telefonat;
  kontext?: TelefonatKontext;
  uhr?: AnrufUhr | null;
}

/** Hält das eine globale Telefonat-Sheet: tel:-Links (AnrufLink) liegen überall im Baum, die Uhr
 * muss aber auch nach einem Neuladen wieder auftauchen -- deshalb hier statt je Seite. */
export function TelefonatProvider({ children }: { children: ReactNode }) {
  const { isAuthenticated } = useAuth();
  const [offen, setOffen] = useState<Offen | null>(null);
  const zaehler = useRef(0);
  const wiederhergestellt = useRef(false);

  const anrufen = useCallback((kontext: TelefonatKontext) => {
    const uhr = uhrStarten({
      kundeId: kontext.kundeId,
      vorgangId: kontext.vorgangId,
      ansprechpartnerId: kontext.partner?.ansprechpartnerId,
      partnerName: kontext.partner?.name,
      partnerNummer: kontext.partner?.nummer,
    });
    setOffen({ schluessel: ++zaehler.current, kontext, uhr });
  }, []);
  const erfassen = useCallback((kontext: TelefonatKontext) => {
    setOffen({ schluessel: ++zaehler.current, kontext });
  }, []);
  const bearbeiten = useCallback((telefonat: Telefonat) => {
    setOffen({ schluessel: ++zaehler.current, telefonat });
  }, []);

  // Eine beim Neuladen noch laufende Uhr wieder anbieten (nur einmal je App-Start).
  useEffect(() => {
    if (!isAuthenticated || wiederhergestellt.current) return;
    wiederhergestellt.current = true;
    const uhr = uhrLaden();
    if (!uhr) return;
    setOffen({
      schluessel: ++zaehler.current,
      uhr,
      kontext: {
        kundeId: uhr.kundeId,
        vorgangId: uhr.vorgangId,
        partner: { ansprechpartnerId: uhr.ansprechpartnerId, name: uhr.partnerName ?? undefined, nummer: uhr.partnerNummer },
      },
    });
  }, [isAuthenticated]);

  const steuerung = useMemo(() => ({ anrufen, erfassen, bearbeiten }), [anrufen, erfassen, bearbeiten]);
  const k = offen?.kontext;

  return (
    <TelefonatContext.Provider value={steuerung}>
      {children}
      {offen && (
        <TelefonatSheet
          key={offen.schluessel}
          offen
          onClose={() => setOffen(null)}
          telefonat={offen.telefonat}
          kundeId={k?.kundeId ?? undefined}
          vorgangId={k?.vorgangId ?? undefined}
          kontextText={k?.kontextText}
          kundeWaehlbar={k?.kundeWaehlbar}
          vorgaenge={k?.vorgaenge}
          ansprechpartner={k?.ansprechpartner}
          vorbelegung={{ richtung: "ausgehend", partner: k?.partner }}
          uhr={offen.uhr}
        />
      )}
    </TelefonatContext.Provider>
  );
}
