import { create } from 'zustand';

export type AppMode = 'chat' | 'work' | 'code';

interface UIState {
  activeMode: AppMode;
  setActiveMode: (mode: AppMode) => void;

  // Sidebar
  sidebarOpen: boolean;
  sidebarWidth: number;
  sidebarHoverOpen: boolean;
  setSidebarOpen: (open: boolean) => void;
  setSidebarWidth: (width: number | ((prev: number) => number)) => void;
  setSidebarHoverOpen: (open: boolean) => void;
  toggleSidebar: () => void;

  // Right panel (context manager)
  rightPanelOpen: boolean;
  toggleRightPanel: () => void;
  setRightPanelOpen: (open: boolean) => void;

  // Mobile
  isMobile: boolean;
  setIsMobile: (mobile: boolean) => void;
  mobileSidebarOpen: boolean;
  setMobileSidebarOpen: (open: boolean) => void;

  // Composer
  composerHeight: number;
  setComposerHeight: (h: number) => void;
}

const MIN_SIDEBAR_WIDTH = 200;
const MAX_SIDEBAR_WIDTH = 350;

export const useUIStore = create<UIState>((set) => ({
  activeMode: 'chat',
  setActiveMode: (mode) => set({ activeMode: mode }),

  sidebarOpen: true,
  sidebarWidth: 260,
  sidebarHoverOpen: false,

  setSidebarOpen: (open) => set({ sidebarOpen: open }),

  setSidebarWidth: (width) =>
    set((state) => {
      const newWidth = typeof width === 'function' ? width(state.sidebarWidth) : width;
      return { sidebarWidth: Math.max(MIN_SIDEBAR_WIDTH, Math.min(MAX_SIDEBAR_WIDTH, newWidth)) };
    }),

  setSidebarHoverOpen: (open) => set({ sidebarHoverOpen: open }),

  toggleSidebar: () =>
    set((state) => ({ sidebarOpen: !state.sidebarOpen })),

  rightPanelOpen: false,
  toggleRightPanel: () =>
    set((state) => ({ rightPanelOpen: !state.rightPanelOpen })),
  setRightPanelOpen: (open) => set({ rightPanelOpen: open }),

  isMobile: false,
  setIsMobile: (mobile) => set({ isMobile: mobile }),
  mobileSidebarOpen: false,
  setMobileSidebarOpen: (open) => set({ mobileSidebarOpen: open }),

  composerHeight: 160,
  setComposerHeight: (h) => set({ composerHeight: h }),
}));
