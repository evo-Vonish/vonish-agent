import { create } from 'zustand';

export type AutoSaveMode = 'off' | 'delay' | 'blur';

interface SettingsState {
  autoSave: AutoSaveMode;
  setAutoSave: (mode: AutoSaveMode) => void;
}

const LS_KEY = 'vonish-agent.settings';

function load(): Partial<SettingsState> {
  try {
    return JSON.parse(localStorage.getItem(LS_KEY) || '{}');
  } catch {
    return {};
  }
}

function persist(autoSave: AutoSaveMode) {
  try {
    localStorage.setItem(LS_KEY, JSON.stringify({ autoSave }));
  } catch {
    /* ignore */
  }
}

export const useSettingsStore = create<SettingsState>((set) => ({
  autoSave: (load().autoSave as AutoSaveMode) || 'off',
  setAutoSave: (mode) => {
    persist(mode);
    set({ autoSave: mode });
  },
}));
