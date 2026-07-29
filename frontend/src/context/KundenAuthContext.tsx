import {
  createContext,
  useCallback,
  useContext,
  useSyncExternalStore,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";

import { kundenportalAuthApi } from "../api/endpoints";
import { kundenAuthStore } from "../api/kundenAuthStore";
import type { CurrentKunde } from "../types";

interface KundenAuthContextValue {
  currentKunde: CurrentKunde | undefined;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
}

const KundenAuthContext = createContext<KundenAuthContextValue | null>(null);

export function KundenAuthProvider({ children }: { children: ReactNode }) {
  const tokens = useSyncExternalStore(kundenAuthStore.subscribe, kundenAuthStore.getState);
  const queryClient = useQueryClient();
  const hasToken = kundenAuthStore.getAccessToken() !== null;

  const meQuery = useQuery({
    queryKey: ["kundenportal-me", tokens?.accessToken],
    queryFn: kundenportalAuthApi.me,
    enabled: hasToken,
    retry: false,
  });

  const login = useCallback(
    async (email: string, password: string) => {
      const result = await kundenportalAuthApi.login(email, password);
      kundenAuthStore.setTokens({ accessToken: result.access_token, refreshToken: result.refresh_token });
      await queryClient.invalidateQueries({ queryKey: ["kundenportal-me"] });
    },
    [queryClient],
  );

  const logout = useCallback(() => {
    kundenAuthStore.clear();
    queryClient.clear();
  }, [queryClient]);

  const value: KundenAuthContextValue = {
    currentKunde: meQuery.data,
    isLoading: hasToken && meQuery.isLoading,
    isAuthenticated: !!meQuery.data,
    login,
    logout,
  };

  return <KundenAuthContext.Provider value={value}>{children}</KundenAuthContext.Provider>;
}

export function useKundenAuth(): KundenAuthContextValue {
  const ctx = useContext(KundenAuthContext);
  if (!ctx) throw new Error("useKundenAuth muss innerhalb von KundenAuthProvider verwendet werden");
  return ctx;
}
