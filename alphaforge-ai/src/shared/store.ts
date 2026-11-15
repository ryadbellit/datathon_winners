import { create } from 'zustand';
import { createJSONStorage, persist } from 'zustand/middleware';
import { ASSETS, SCENARIOS } from '../data/assets';
import type { Profile, ViewMode } from '../data/types';

interface Toast {
  id: number;
  message: string;
}

interface AppState {
  profile: Profile | null;
  selectedIds: string[];
  weightOverrides: Record<string, number>;
  viewMode: ViewMode;
  scenarioId: string;
  horizonOverride: number | null;
  toast: Toast | null;

  saveProfile: (profile: Profile, initialSelection: string[]) => void;
  toggleAsset: (ticker: string) => void;
  clearSelection: () => void;
  setWeight: (ticker: string, value: number) => void;
  resetWeights: () => void;
  setViewMode: (mode: ViewMode) => void;
  setScenario: (id: string) => void;
  setHorizon: (years: number | null) => void;
  notify: (message: string) => void;
  dismissToast: () => void;
}

let toastSeq = 0;

/** localStorage access can throw in private windows or with blocked site data. */
const safeStorage = {
  getItem: (name: string) => {
    try {
      return window.localStorage.getItem(name);
    } catch {
      return null;
    }
  },
  setItem: (name: string, value: string) => {
    try {
      window.localStorage.setItem(name, value);
    } catch {
      /* ignore: the app still works without persistence */
    }
  },
  removeItem: (name: string) => {
    try {
      window.localStorage.removeItem(name);
    } catch {
      /* ignore */
    }
  },
};

export const useAppStore = create<AppState>()(
  persist(
    (set, get) => ({
      profile: null,
      selectedIds: [],
      weightOverrides: {},
      viewMode: 'guided',
      scenarioId: SCENARIOS[0].id,
      horizonOverride: null,
      toast: null,

      saveProfile: (profile, initialSelection) =>
        set({
          profile,
          selectedIds: initialSelection,
          weightOverrides: {},
          viewMode: profile.knowledge === 'advanced' ? 'advanced' : 'guided',
          horizonOverride: null,
        }),

      toggleAsset: (ticker) => {
        const { selectedIds } = get();
        const asset = ASSETS.find((a) => a.ticker === ticker);
        const isOn = selectedIds.includes(ticker);
        const next = isOn ? selectedIds.filter((t) => t !== ticker) : [...selectedIds, ticker];
        set({ selectedIds: next });
        get().notify(`${isOn ? 'Removed' : 'Added'} ${asset?.name ?? ticker} ${isOn ? 'from' : 'to'} your selection`);
      },

      clearSelection: () => set({ selectedIds: [], weightOverrides: {} }),

      setWeight: (ticker, value) =>
        set((s) => ({ weightOverrides: { ...s.weightOverrides, [ticker]: value } })),

      resetWeights: () => {
        set({ weightOverrides: {} });
        get().notify('Weights reset to the base mix');
      },

      setViewMode: (mode) => set({ viewMode: mode }),
      setScenario: (id) => set({ scenarioId: id }),
      setHorizon: (years) => set({ horizonOverride: years }),

      notify: (message) => {
        toastSeq += 1;
        set({ toast: { id: toastSeq, message } });
      },
      dismissToast: () => set({ toast: null }),
    }),
    {
      name: 'alphaforge-state',
      storage: createJSONStorage(() => safeStorage),
      partialize: (s) => ({
        profile: s.profile,
        selectedIds: s.selectedIds,
        weightOverrides: s.weightOverrides,
        viewMode: s.viewMode,
      }),
    },
  ),
);
