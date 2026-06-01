// ─── URL 清洗器 ───
// 移除追踪参数、广告参数、跳转包装

const TRACKING_PARAMS = new Set([
  // Google Analytics
  "utm_source",
  "utm_medium",
  "utm_campaign",
  "utm_term",
  "utm_content",
  "utm_id",
  // Facebook
  "fbclid",
  "fb_action_ids",
  "fb_action_types",
  "fb_source",
  // Google Ads
  "gclid",
  "gclsrc",
  "dclid",
  // 阿里系
  "spm",
  "scm",
  "ali_trackid",
  // 其他
  "ref",
  "ref_",
  "referrer",
  "from",
  "source",
  "mc_cid",
  "mc_eid",
  "pk_campaign",
  "pk_kwd",
  "pk_source",
  "pk_medium",
  "pk_content",
  // 社交
  "s_cid",
  "trk",
  "trkCampaign",
  // 追踪
  "_ga",
  "_gl",
  "_hsenc",
  "_hsmi",
  "__hstc",
  "__hssc",
  "__hsfp",
  "hsCtaTracking",
  // 微信
  "isappinstalled",
  "wxwork_userid",
]);

/**
 * 清理单个 URL 的追踪参数
 */
export function cleanUrl(raw: string): string {
  try {
    const url = new URL(raw);

    // 移除追踪参数
    for (const param of TRACKING_PARAMS) {
      url.searchParams.delete(param);
    }

    // 移除空的 hash
    if (url.hash === "#" || url.hash === "") {
      url.hash = "";
    }

    // 移除尾部 ?
    let cleaned = url.toString();
    if (cleaned.endsWith("?")) {
      cleaned = cleaned.slice(0, -1);
    }

    return cleaned;
  } catch {
    return raw;
  }
}

/**
 * 检查是否包含追踪参数
 */
export function hasTrackingParams(url: string): boolean {
  try {
    const parsed = new URL(url);
    for (const param of TRACKING_PARAMS) {
      if (parsed.searchParams.has(param)) return true;
    }
    return false;
  } catch {
    return false;
  }
}

/**
 * 批量清理
 */
export function cleanUrls(urls: string[]): string[] {
  return urls.map(cleanUrl);
}

/**
 * 检查是否为有效的 HTTP(S) URL
 */
export function isValidUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === "http:" || parsed.protocol === "https:";
  } catch {
    return false;
  }
}
