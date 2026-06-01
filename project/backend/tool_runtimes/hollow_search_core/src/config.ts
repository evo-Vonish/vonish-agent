// 引擎配置加载器 — 简化版，使用内联默认值替代 YAML 文件

import type { EngineConfig } from "./types.js";

const DEFAULT_CONFIGS: Record<string, EngineConfig> = {
  brave: {
    name: "brave",
    shortcut: "br",
    disabled: false,
    weight: 1,
    timeout: 10000,
    categories: ["general", "web"],
  },
  bing: {
    name: "bing",
    shortcut: "bi",
    disabled: false,
    weight: 1,
    timeout: 10000,
    categories: ["general", "web", "news"],
  },
  duckduckgo: {
    name: "duckduckgo",
    shortcut: "ddg",
    disabled: false,
    weight: 1,
    timeout: 10000,
    categories: ["general"],
  },
  wikipedia: {
    name: "wikipedia",
    shortcut: "wp",
    disabled: false,
    weight: 1,
    timeout: 8000,
    categories: ["general", "scholar"],
  },
  google: {
    name: "google",
    shortcut: "go",
    disabled: false,
    weight: 1,
    timeout: 10000,
    categories: ["general", "web", "news"],
  },
};

export function loadEngineConfigMap(): Map<string, EngineConfig> {
  const map = new Map<string, EngineConfig>();
  for (const [key, config] of Object.entries(DEFAULT_CONFIGS)) {
    map.set(key, { ...config });
  }
  return map;
}
