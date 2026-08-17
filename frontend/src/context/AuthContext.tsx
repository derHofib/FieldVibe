import {
  createContext,
  useCallback,
  useContext,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { authApi, mandantenApi } from "../api/endpoints";
import { authStore } from "../api/authStore";
import { clearAllOfflineData } from "../offline/db";
import type { CurrentUser, RechteAktion, RechteBereich } from "../types";

interface AuthContextValue {
  currentUser: CurrentUser | undefined;
  isLoading: boolean;
  isAuthenticated: boolean;
  isImpersonating: boolean;
  // Spiegelt app/api/deps.py:require_recht -- prueft currentUser.rechte
  // statt einer festen Rollenliste. Ohne eingeloggten Nutzer (noch ladend)
  // liefert das bewusst false, nicht true, damit UI-Elemente nicht kurz
  // aufblitzen, bevor /api/auth/me zurueck ist.
  hatRecht: (bereich: RechteBereich, aktion: RechteAktion) => boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  startImpersonation: (mandantId: string) => Promise<void>;
  endImpersonation: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const authState = useSyncExternalStore(authStore.subscribe, authStore.getState);
  const queryClient = useQueryClient();
  const hasToken = authStore.getActiveAccessToken() !== null;

  const meQuery = useQuery({
    queryKey: ["me", authState.primary?.accessToken, authState.impersonation?.accessToken],
    queryFn: authApi.me,
    enabled: hasToken,
    retry: false,
  });

  const login = useCallback(
    async (email: string, password: string) => {
      const tokens = await authApi.login(email, password);
      authStore.setPrimary({ accessToken: tokens.access_token, refreshToken: tokens.refresh_token });
      await queryClient.invalidateQueries({ queryKey: ["me"] });
    },
    [queryClient],
  );

  const logout = useCallback(() => {
    authStore.clear();
    queryClient.clear();
    // Geraet kann von mehreren Technikern geteilt sein (Firmenhandy) -- ohne
    // das wuerden Kunden-/Vorgangsdaten des vorherigen Nutzers sichtbar
    // bleiben und dessen noch nicht synchronisierte Outbox-Eintraege spaeter
    // unter der Identitaet des naechsten Nutzers hochgeladen.
    void clearAllOfflineData();
  }, [queryClient]);

  const startImpersonation = useCallback(
    async (mandantId: string) => {
      const resp = await mandantenApi.impersonate(mandantId);

      // Cancel in-flight requests from the still-mounted Mandanten/Accounts/
      // Audit-Log pages *before* switching the token. Those requests were
      // already dispatched with the old super_admin token -- reordering
      // code here can't change headers already baked into a request that's
      // in flight, but cancelling the query client-side means an eventual
      // 403 response for it is dropped instead of rendered, which was the
      // brief loading-state flash observed during manual testing right
      // after starting an impersonation.
      await queryClient.cancelQueries({ queryKey: ["me"] });
      await queryClient.cancelQueries({ queryKey: ["users"] });
      await queryClient.cancelQueries({ queryKey: ["mandanten"] });
      await queryClient.cancelQueries({ queryKey: ["audit-log"] });

      authStore.setImpersonation({
        accessToken: resp.access_token,
        mandantId: resp.mandant_id,
        expiresInMinutes: resp.expires_in_minutes,
        startedAt: Date.now(),
      });
      // Deliberately not a blanket invalidateQueries(): "mandanten" and
      // "audit-log" are still mounted at this exact point (React hasn't
      // re-rendered the route swap yet), and an unscoped invalidate would
      // force-refetch them immediately with the new, more restricted
      // impersonation token before they even get the chance to unmount --
      // producing a 403 that has nothing to do with what the user did.
      await queryClient.invalidateQueries({ queryKey: ["me"] });
      await queryClient.invalidateQueries({ queryKey: ["users"] });
    },
    [queryClient],
  );

  const endImpersonation = useCallback(() => {
    authStore.setImpersonation(null);
    // Safe to invalidate everything here: the active token reverts to the
    // super_admin's own, which can reach every endpoint these pages call.
    queryClient.invalidateQueries();
  }, [queryClient]);

  const hatRecht = useCallback(
    (bereich: RechteBereich, aktion: RechteAktion) =>
      meQuery.data?.rechte[bereich]?.includes(aktion) ?? false,
    [meQuery.data],
  );

  const value: AuthContextValue = {
    currentUser: meQuery.data,
    isLoading: hasToken && meQuery.isLoading,
    isAuthenticated: !!meQuery.data,
    isImpersonating: authState.impersonation !== null,
    hatRecht,
    login,
    logout,
    startImpersonation,
    endImpersonation,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth muss innerhalb von AuthProvider verwendet werden");
  return ctx;
}
