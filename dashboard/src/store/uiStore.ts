import { create } from "zustand";
import { persist } from "zustand/middleware";
import type { AlertPayload } from "../types";

interface UiState {
  sidebarOpen: boolean;
  theme: "light" | "dark";
  alertFilter: { fraud_types?: string[]; min_probability?: number };
  alertQueue: AlertPayload[];
  toggleSidebar: () => void;
  setTheme: (theme: "light" | "dark") => void;
  setAlertFilter: (filter: { fraud_types?: string[]; min_probability?: number }) => void;
  pushAlert: (alert: AlertPayload) => void;
  clearAlerts: () => void;
}

export const useUiStore = create<UiState>()(
  persist(
    (set) => ({
      sidebarOpen: true,
      theme: "dark",
      alertFilter: {},
      alertQueue: [],
      toggleSidebar: () => set((s) => ({ sidebarOpen: !s.sidebarOpen })),
      setTheme: (theme) => set({ theme }),
      setAlertFilter: (filter) => set({ alertFilter: filter }),
      pushAlert: (alert) =>
        set((s) => ({ alertQueue: [...s.alertQueue.slice(-99), alert] })),
      clearAlerts: () => set({ alertQueue: [] }),
    }),
    { name: "payshield-ui", partialize: (state) => ({ theme: state.theme, sidebarOpen: state.sidebarOpen }) },
  ),
);
