// ─── 搜索结果排序器 ───
// 来自 HOLLOW SearchAdapter 的权威评分、广告检测、SEO 过滤

import type { RawSearchResult, SearchResult } from "../types/index.js";

// 域名权威度评分表
const DOMAIN_AUTHORITY: Record<string, number> = {
  "wikipedia.org": 0.7,
  "en.wikipedia.org": 0.7,
  "zh.wikipedia.org": 0.7,
  "github.com": 0.6,
  "stackoverflow.com": 0.55,
  "arxiv.org": 0.65,
  "doi.org": 0.6,
  "semanticscholar.org": 0.6,
  "pubmed.ncbi.nlm.nih.gov": 0.65,
  "developer.mozilla.org": 0.6,
  "docs.python.org": 0.55,
  "nodejs.org": 0.55,
  "npmjs.com": 0.4,
  "pypi.org": 0.4,
  "medium.com": 0.2,
  "blog.csdn.net": 0.15,
  "juejin.cn": 0.2,
  "zhuanlan.zhihu.com": 0.15,
  "toutiao.com": -0.3,
  "baijiahao.baidu.com": -0.35,
  "codenong.com": -0.3,
};

// 被屏蔽的低质域名 (SEO 农场 / 内容农场 / 镜像站)
const BLOCKED_DOMAINS = new Set([
  "codenong.com",
  "programmer.group",
  "pythonmana.com",
  "copyfuture.com",
  "blogread.cn",
  "freesion.com",
  "programmerall.com",
  "developpaper.com",
  "www.coder.work",
  "www.cnblogs.com",
  "www.cxyzjd.com",
  "www.codetd.com",
  "www.codeprj.com",
  "www.programmersought.com",
  "www.debugcn.com",
  "www.softnami.com",
  "www.5axxw.com",
  "www.programminghunter.com",
  "www.appsloveworld.com",
  "www.yaolong.net",
]);

// 广告关键词模式
const AD_PATTERNS = [
  /sponsor/i, /promoted/i, /advertisement/i,
  /^ad$/i, /^ads$/i, /\bad\b/i,
];

// SEO 垃圾信号
const SEO_SPAM_SIGNALS: Array<{ pattern: RegExp; weight: number }> = [
  { pattern: /^(最全|史上最|全网最|独家|揭秘|震惊|重磅)/, weight: 0.4 },
  { pattern: /(点击查看|立即下载|免费领取|限时|优惠|促销)/, weight: 0.35 },
  { pattern: /(关注公众号|加微信|扫码|私信|转发)/, weight: 0.3 },
  { pattern: /\d{3,}个?(赞|评论|收藏|转发|阅读)/, weight: 0.25 },
  { pattern: /猛戳|速看|快转|千万别|一定要看|不看后悔/, weight: 0.35 },
];

/**
 * 提取域名
 */
function getDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

/**
 * 获取域名权威分
 */
export function domainAuthority(url: string): number {
  const hostname = getDomain(url).toLowerCase();

  // 精确匹配
  if (DOMAIN_AUTHORITY[hostname] !== undefined) {
    return DOMAIN_AUTHORITY[hostname];
  }

  // 模糊匹配
  if (hostname.endsWith(".edu") || hostname.endsWith(".ac.")) return 0.5;
  if (hostname.endsWith(".gov") || hostname.endsWith(".gov.cn")) return 0.5;
  if (hostname.endsWith(".org")) return 0.3;
  if (hostname.includes("docs.") || hostname.includes("documentation")) return 0.35;
  if (hostname.includes("github.io")) return 0.1;

  return 0;
}

/**
 * 检测是否广告
 */
export function isLikelyAd(result: RawSearchResult): boolean {
  const text = (result.title + " " + result.content).toLowerCase();
  return AD_PATTERNS.some((p) => p.test(text));
}

/**
 * 检测是否 SEO 垃圾
 */
export function isLikelySeoSpam(result: RawSearchResult): boolean {
  const text = result.title + " " + result.content;
  let score = 0;
  for (const signal of SEO_SPAM_SIGNALS) {
    if (signal.pattern.test(text)) {
      score += signal.weight;
    }
  }
  return score >= 0.3;
}

/**
 * 检查域名是否在黑名单
 */
export function isBlockedDomain(url: string): boolean {
  return BLOCKED_DOMAINS.has(getDomain(url).toLowerCase());
}

/**
 * 内容新鲜度评分
 */
export function freshnessScore(result: RawSearchResult, preferFresh: boolean): number {
  if (!preferFresh) return 0;
  if (result.publishedDate) {
    const ageDays = (Date.now() - new Date(result.publishedDate).getTime()) / 86400000;
    return Math.max(0, 1 - ageDays / 365);
  }
  return 0;
}

/**
 * 语言匹配度
 */
export function languageScore(result: RawSearchResult, queryLanguage: string): number {
  // 简单的中文/英文检测
  const text = result.title + result.content;
  const cjkCount = (text.match(/[\u4e00-\u9fff\u3400-\u4dbf]/g) || []).length;
  const isChinese = cjkCount > text.length * 0.1;

  if (queryLanguage === "zh" && isChinese) return 0.3;
  if (queryLanguage !== "zh" && !isChinese) return 0.2;
  if (!queryLanguage) return 0;
  return -0.1;
}

/**
 * 结果排序：综合评分
 *
 * finalScore = baseScore
 *   + domainAuthority
 *   + freshnessBoost
 *   + languageMatchBoost
 *   - adPenalty
 *   - seoSpamPenalty
 *   - duplicatePenalty
 */
export function rankResults(
  results: RawSearchResult[],
  options: {
    preferFresh?: boolean;
    queryLanguage?: string;
    preferAcademic?: boolean;
    preferOfficial?: boolean;
    preferRepos?: boolean;
  } = {},
): SearchResult[] {
  const ranked: SearchResult[] = results.map((r) => {
    const domain = getDomain(r.url);
    let score = r.score;
    const authority = domainAuthority(r.url);
    const ad = isLikelyAd(r);
    const spam = isLikelySeoSpam(r);
    const fresh = freshnessScore(r, !!options.preferFresh);
    const lang = languageScore(r, options.queryLanguage || "");

    score += authority;
    score += fresh;
    score += lang;

    if (options.preferAcademic) {
      const isAcademic =
        domain.endsWith(".edu") || domain.includes("arxiv") || domain.includes("scholar");
      if (isAcademic) score += 0.25;
    }

    if (options.preferOfficial) {
      const isOfficial =
        domain.includes("docs.") ||
        domain.endsWith(".org") ||
        domain.includes("documentation");
      if (isOfficial) score += 0.15;
    }

    if (options.preferRepos) {
      const isRepo =
        domain.includes("github.com") ||
        domain.includes("gitlab.com") ||
        domain.includes("npmjs.com") ||
        domain.includes("pypi.org");
      if (isRepo) score += 0.2;
    }

    if (ad) score -= 0.5;
    if (spam) score -= 0.4;

    return {
      ...r,
      cleanUrl: r.url,
      domain,
      score: Math.round(score * 100) / 100,
      isAd: ad,
      isSeoSpam: spam,
      domainAuthority: authority,
    };
  });

  // 移除黑名单域名
  const filtered = ranked.filter((r) => !isBlockedDomain(r.url));

  // 按综合评分降序
  filtered.sort((a, b) => b.score - a.score);

  return filtered;
}
