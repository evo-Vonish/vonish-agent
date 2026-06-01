// ─── 搜索意图路由器 ───
// 来自 HOLLOW SearchAdapter 的 6 模式搜索策略
// 决定：用什么引擎、搜多少、超时多久、是否启用补充搜索

import type { SearchMode } from "../types/index.js";

export interface IntentConfig {
  mode: SearchMode;
  engines: string[];
  categories?: string[];
  limit: number;
  timeoutMs: number;
  supplement: boolean;
  freshOnly: boolean;
  preferAcademic: boolean;
  preferOfficial: boolean;
  preferRepos: boolean;
  preferMedia: boolean;
  description: string;
}

/**
 * 6 种搜索意图模式
 *
 * overview    通用搜索，平衡覆盖率和速度
 * scholar     学术搜索，偏好论文、edu、官方文档
 * dev         开发搜索，偏好 GitHub、StackOverflow、官方文档
 * live        实时搜索，偏好新闻、时间敏感性内容
 * media       媒体搜索，偏好图片/视频/媒体站点
 * deep_dive   深度研究，多引擎 + 大结果集 + 补充搜索
 */
export const INTENT_CONFIGS: Record<SearchMode, IntentConfig> = {
  overview: {
    mode: "overview",
    engines: ["brave", "duckduckgo", "wikipedia"],
    limit: 10,
    timeoutMs: 8000,
    supplement: false,
    freshOnly: false,
    preferAcademic: false,
    preferOfficial: false,
    preferRepos: false,
    preferMedia: false,
    description: "通用搜索，平衡覆盖率和速度",
  },

  scholar: {
    mode: "scholar",
    engines: ["brave", "duckduckgo", "wikipedia"],
    limit: 15,
    timeoutMs: 12000,
    supplement: true,
    freshOnly: false,
    preferAcademic: true,
    preferOfficial: true,
    preferRepos: false,
    preferMedia: false,
    description: "学术搜索，偏好论文、edu、官方文档",
  },

  dev: {
    mode: "dev",
    engines: ["brave", "bing", "google"],
    limit: 15,
    timeoutMs: 12000,
    supplement: true,
    freshOnly: false,
    preferAcademic: false,
    preferOfficial: true,
    preferRepos: true,
    preferMedia: false,
    description: "开发搜索，偏好 GitHub、StackOverflow、官方文档",
  },

  live: {
    mode: "live",
    engines: ["bing", "google"],
    limit: 20,
    timeoutMs: 10000,
    supplement: false,
    freshOnly: true,
    preferAcademic: false,
    preferOfficial: false,
    preferRepos: false,
    preferMedia: false,
    description: "实时搜索，偏好新闻和时间敏感内容",
  },

  media: {
    mode: "media",
    engines: ["brave", "bing", "google"],
    limit: 20,
    timeoutMs: 10000,
    supplement: false,
    freshOnly: false,
    preferAcademic: false,
    preferOfficial: false,
    preferRepos: false,
    preferMedia: true,
    description: "媒体搜索，偏好图片/视频/媒体站点",
  },

  deep_dive: {
    mode: "deep_dive",
    engines: ["brave", "bing", "duckduckgo", "wikipedia", "google"],
    limit: 30,
    timeoutMs: 20000,
    supplement: true,
    freshOnly: false,
    preferAcademic: true,
    preferOfficial: true,
    preferRepos: true,
    preferMedia: false,
    description: "深度研究，全引擎+大结果集+补充搜索",
  },
};

const KEYWORDS: Record<SearchMode, string[]> = {
  overview: [],
  scholar: [
    "论文", "paper", "arxiv", "doi", "研究", "research", "survey",
    "期刊", "journal", "学术", "scholar", "文献", "reference",
    "引用", "citation", "peer review", "综述", "元分析",
  ],
  dev: [
    "api", "sdk", "framework", "library", "package", "npm",
    "github", "gitlab", "stackoverflow", "issue", "bug",
    "documentation", "docs", "reference", "source code",
    "example", "tutorial", "how to", "安装", "配置",
  ],
  live: [
    "最新", "今天", "最近", "新闻", "刚刚", "突发",
    "latest", "news", "breaking", "today", "recent",
    "live", "实时", "更新", "宣布", "发布",
    "价格", "股价", "市值",
  ],
  media: [
    "图片", "视频", "壁纸", "海报", "封面",
    "image", "video", "wallpaper", "poster", "cover",
    "screenshot", "截图", "gif", "meme",
  ],
  deep_dive: [
    "深度", "对比", "调研", "分析", "报告", "总结",
    "全面", "综合", "review", "comparison", "analysis",
    "comprehensive", "overview", "guide", "终极",
    "全景", "透视", "解读",
  ],
};

/**
 * 根据查询文本自动推断搜索意图
 */
export function inferSearchMode(query: string, explicit?: SearchMode): IntentConfig {
  if (explicit) {
    return INTENT_CONFIGS[explicit] || INTENT_CONFIGS.overview;
  }

  const lower = query.toLowerCase();

  // 计算每种模式的匹配数
  const scores: { mode: SearchMode; count: number }[] = [];
  for (const [mode, words] of Object.entries(KEYWORDS)) {
    if (mode === "overview") continue;
    const count = words.filter((w) => lower.includes(w)).length;
    scores.push({ mode: mode as SearchMode, count });
  }

  // 取最高分，阈值 1
  scores.sort((a, b) => b.count - a.count);
  if (scores[0] && scores[0].count >= 1) {
    return INTENT_CONFIGS[scores[0].mode];
  }

  return INTENT_CONFIGS.overview;
}

/**
 * 获取指定意图的配置
 */
export function getIntentConfig(mode: SearchMode): IntentConfig {
  return INTENT_CONFIGS[mode] || INTENT_CONFIGS.overview;
}

export { INTENT_CONFIGS as default };
