import {
  createContext,
  useCallback,
  useContext,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { partnerAuthStore } from "../api/partnerAuthStore";
import { partnerPortalAuthApi } from "../api/endpoints";
import type { CurrentPartner, TokenPair } from "../types";

interface PartnerAuthContextValue {
  currentPartner: CurrentPartner | undefined;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  // Direktes Einloggen nach abgeschlossener Einladung (PartnerRegistrierenPage).
  loginMitToken: (tokens: TokenPair) => Promise<void>;
  logout: () => void;
}

const PartnerAuthContext = createContext<PartnerAuthContextValue | null>(null);

export function PartnerAuthProvider({ children }: { children: ReactNode }) {
  const tokens = useSyncExternalStore(partnerAuthStore.subscribe, partnerAuthStore.getState);
  const queryClient = useQueryClient();
  const hasToken = tokens !== null;

  const meQuery = useQuery({
    queryKey: ["partnerportal-me"],
    queryFn: partnerPortalAuthApi.me,
    enabled: hasToken,
    retry: false,
  });

  // /me gleich mit abfragen: scheitert es (z. B. 403, weil das Modul
  // "nachunternehmer" beim Mandanten aus ist), darf kein halb eingeloggter
  // Zustand mit gespeichertem Token zurueckbleiben -- die Login-Seite soll
  // den Fehler anzeigen koennen.
  const sitzungAufbauen = useCallback(
    async (neu: TokenPair) => {
      partnerAuthStore.setTokens({ accessToken: neu.access_token, refreshToken: neu.refresh_token });
      try {
        const me = await partnerPortalAuthApi.me();
        queryClient.setQueryData(["partnerportal-me"], me);
      } catch (err) {
        partnerAuthStore.clear();
        throw err;
      }
    },
    [queryClient],
  );

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await partnerPortalAuthApi.login(email, password);
      await sitzungAufbauen(result);
    },
    [sitzungAufbauen],
  );

  const loginMitToken = useCallback(
    async (neu: TokenPair) => {
      await sitzungAufbauen(neu);
    },
    [sitzungAufbauen],
  );

  const logout = useCallback(() => {
    partnerAuthStore.clear();
    queryClient.clear();
  }, [queryClient]);

  const value: PartnerAuthContextValue = {
    currentPartner: hasToken ? meQuery.data : undefined,
    isLoading: hasToken && meQuery.isLoading,
    isAuthenticated: hasToken && !!meQuery.data,
    login,
    loginMitToken,
    logout,
  };

  return <PartnerAuthContext.Provider value={value}>{children}</PartnerAuthContext.Provider>;
}

export function usePartnerAuth(): PartnerAuthContextValue {
  const ctx = useContext(PartnerAuthContext);
  if (!ctx) throw new Error("usePartnerAuth muss innerhalb von PartnerAuthProvider verwendet werden");
  return ctx;
}
