import { create } from "zustand";
import { persist } from "zustand/middleware";

interface User {
  username: string;
  role: string;
}

interface AuthState {
  token: string | null;
  refreshToken: string | null;
  user: User | null;
  isAuthenticated: boolean;
  login: (token: string, refreshToken: string, user: User) => void;
  setTokens: (token: string, refreshToken: string) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      refreshToken: null,
      user: null,
      isAuthenticated: false,
      login: (token, refreshToken, user) => {
        // Mirror the tokens into the keys the axios interceptor reads
        // (api/client.ts) so every subsequent request carries the header.
        localStorage.setItem("auth_token", token);
        localStorage.setItem("refresh_token", refreshToken);
        set({ token, refreshToken, user, isAuthenticated: true });
      },
      setTokens: (token, refreshToken) => {
        localStorage.setItem("auth_token", token);
        localStorage.setItem("refresh_token", refreshToken);
        set({ token, refreshToken });
      },
      logout: () => {
        localStorage.removeItem("auth_token");
        localStorage.removeItem("refresh_token");
        localStorage.removeItem("api_key");
        localStorage.removeItem("payshield-auth");
        set({ token: null, refreshToken: null, user: null, isAuthenticated: false });
      },
    }),
    { name: "payshield-auth" },
  ),
);
