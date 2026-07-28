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
import type { CurrentUser } from "../types";

interface AuthContextValue {
  currentUser: CurrentUser | undefined;
  isLoading: boolean;
  isAuthenticated: boolean;
  isImpersonating: boolean;
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
  }, [queryClient]);

  const startImpersonation = useCallback(
    async (mandantId: string) => {
      const resp = await mandantenApi.impersonate(mandantId);
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

  const value: AuthContextValue = {
    currentUser: meQuery.data,
    isLoading: hasToken && meQuery.isLoading,
    isAuthenticated: !!meQuery.data,
    isImpersonating: authState.impersonation !== null,
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
