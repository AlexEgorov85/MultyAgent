"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import {
  DEFAULT_PREFERENCES,
  readUiPreferences,
  writeUiPreferences,
  type UiPreferences,
} from "./preferences";

type SettingsContextValue = {
  settings: UiPreferences;
  ready: boolean;
  setSetting: <K extends keyof UiPreferences,>(
    key: K,
    value: UiPreferences[K],
  ) => void;
  resetSettings: () => void;
};

const SettingsContext = createContext<SettingsContextValue | null>(null);

function resolveTheme(theme: UiPreferences["theme"]): "light" | "dark" {
  if (theme !== "system") return theme;
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches
    ? "dark"
    : "light";
}

export function applySettings(settings: UiPreferences): void {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const theme = resolveTheme(settings.theme);

  root.dataset.theme = theme;
  root.dataset.themeMode = settings.theme;
  root.dataset.accent = settings.accent;
  root.dataset.density = settings.density;
  root.dataset.radius = settings.radius;
  root.dataset.width = settings.width;
  root.dataset.font = settings.fontFamily;
  root.dataset.background = settings.background;
  root.dataset.animations = settings.animations ? "on" : "off";
  root.dataset.glass = settings.glass ? "on" : "off";
  root.style.setProperty("--ui-scale", String(settings.fontScale));
  root.style.setProperty("--chat-scale", String(settings.chatFontScale));
  root.style.colorScheme = theme;
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<UiPreferences>(DEFAULT_PREFERENCES);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    const stored = readUiPreferences();
    setSettings(stored);
    applySettings(stored);
    setReady(true);
  }, []);

  useEffect(() => {
    applySettings(settings);
  }, [settings]);

  useEffect(() => {
    if (settings.theme !== "system" || typeof window === "undefined") return;
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const onChange = () => applySettings(settings);
    media.addEventListener("change", onChange);
    return () => media.removeEventListener("change", onChange);
  }, [settings]);

  useEffect(() => {
    const onStorage = (event: StorageEvent) => {
      if (event.key !== "audit-ui-preferences") return;
      const next = readUiPreferences();
      setSettings(next);
      applySettings(next);
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  const setSetting = useCallback(
    <K extends keyof UiPreferences,>(key: K, value: UiPreferences[K]) => {
      setSettings((previous) => {
        const next = { ...previous, [key]: value };
        writeUiPreferences(next);
        applySettings(next);
        return next;
      });
    },
    [],
  );

  const resetSettings = useCallback(() => {
    const next = { ...DEFAULT_PREFERENCES };
    setSettings(next);
    writeUiPreferences(next);
    applySettings(next);
  }, []);

  const value = useMemo(
    () => ({ settings, ready, setSetting, resetSettings }),
    [settings, ready, setSetting, resetSettings],
  );

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings(): SettingsContextValue {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error("useSettings must be used inside SettingsProvider");
  }
  return context;
}
