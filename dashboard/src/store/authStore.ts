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
      login: (token, refreshToken, user) =>
        set({ token, refreshToken, user, isAuthenticated: true }),
      setTokens: (token, refreshToken) =>
        set({ token, refreshToken }),
      logout: () =>
        set({ token: null, refreshToken: null, user: null, isAuthenticated: false }),
    }),
    { name: "payshield-auth" },
  ),
);
