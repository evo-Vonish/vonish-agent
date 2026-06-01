// DuckDuckGo search engine adapter
// Translated from SearXNG searx/engines/duckduckgo.py

import * as cheerio from 'cheerio';
import { EngineAdapter, EngineResponse } from './engine.js';
import { SearchRequest, RawResult, RequestParams, EngineConfig } from '../types.js';

/**
 * DuckDuckGo engine configuration.
 */
const DUCKDUCKGO_CONFIG: EngineConfig = {
  name: 'duckduckgo',
  shortcut: 'ddg',
  disabled: false,
  weight: 1,
  timeout: 10000,
  categories: ['general'],
};

/**
 * Time range mapping for DuckDuckGo.
 * day=d, week=w, month=m, year=y
 */
function getTimeRangeParam(range?: string): string | undefined {
  if (!range) return undefined;
  const mapping: Record<string, string> = {
    day: 'd',
    week: 'w',
    month: 'm',
    year: 'y',
  };
  return mapping[range];
}

/**
 * SafeSearch mapping for DuckDuckGo form data.
 * DDG uses: -1 = off, 1 = moderate, 2 = strict
 */
function getSafesearchParam(level: 0 | 1 | 2): string {
  switch (level) {
    case 0: return '-1';
    case 2: return '1';
    case 1:
    default: return '-1';
  }
}

/**
 * In-memory cache for the vqd token extracted from DuckDuckGo responses.
 * The vqd token is required for pagination.
 */
const vqdCache: Map<string, string> = new Map();

/**
 * DuckDuckGo search engine adapter.
 *
 * Request: POST https://html.duckduckgo.com/html/
 *   Form data: q={query}
 *   Headers: Referer, Sec-Fetch-*, Accept-Language
 *   Cookies: kl={region}, df={time_range}
 *
 * Response: HTML parsed with cheerio
 *   Each result: div.web-result (or div[class*="web-result"])
 *   Title+link: h2 > a
 *   Content: a.result__snippet
 *   vqd token: input[name="vqd"]@value (cached for pagination)
 *   Zero-click info: div#zero_click_abstract
 *   CAPTCHA detection: form#challenge-form
 */
export class DuckDuckGoEngine extends EngineAdapter {
  readonly name = 'duckduckgo';
  readonly config: EngineConfig;

  constructor(config: EngineConfig = DUCKDUCKGO_CONFIG) {
    super();
    this.config = config;
  }

  buildRequest(query: string, req: SearchRequest): RequestParams {
    const safesearch = req.safesearch ?? 0;
    const language = req.language ?? 'en-US';
    const pageno = req.pageno ?? 1;

    // Build cookies
    const cookies: Record<string, string> = {
      // Region/language cookie
      kl: language,
    };

    // Time range cookie
    const timeParam = getTimeRangeParam(req.timeRange);
    if (timeParam) {
      cookies.df = timeParam;
    }

    // Build form data
    const data: Record<string, string> = {
      q: query,
      // SafeSearch parameter for DDG
      kp: getSafesearchParam(safesearch as 0 | 1 | 2),
    };

    // Add vqd token for pagination (pageno > 1)
    const cacheKey = `${query}:${language}`;
    if (pageno > 1) {
      const vqd = vqdCache.get(cacheKey);
      if (vqd) {
        data.vqd = vqd;
        data.s = String((pageno - 1) * 30);
        data.dc = String((pageno - 1) * 30 + 1);
      }
    }

    // SafeSearch: DDG uses different form parameters
    // 'ex' parameter for safesearch
    if (safesearch === 2) {
      data.ex = '1';
    } else {
      data.ex = '-1';
    }

    return {
      query,
      pageno,
      safesearch: safesearch as 0 | 1 | 2,
      time_range: req.timeRange,
      language,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0',
        Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        Referer: 'https://html.duckduckgo.com/',
        Origin: 'https://html.duckduckgo.com',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Sec-Fetch-User': '?1',
        'Content-Type': 'application/x-www-form-urlencoded',
        DNT: '1',
        Connection: 'keep-alive',
      },
      cookies,
      method: 'POST',
      url: 'https://html.duckduckgo.com/html/',
      data,
    };
  }

  async parseResponse(resp: EngineResponse, params: RequestParams): Promise<RawResult[]> {
    const html = await resp.text();
    const $ = cheerio.load(html);
    const results: RawResult[] = [];

    // --- CAPTCHA detection ---
    const challengeForm = $('form#challenge-form');
    if (challengeForm.length > 0) {
      return [];
    }

    // --- Extract and cache vqd token for pagination ---
    const vqdInput = $('input[name="vqd"]');
    if (vqdInput.length > 0) {
      const vqdValue = vqdInput.attr('value');
      if (vqdValue) {
        const cacheKey = `${params.query}:${params.language}`;
        vqdCache.set(cacheKey, vqdValue);
      }
    }

    // --- Parse search results ---
    // DuckDuckGo uses various class names: "web-result", "result", etc.
    $('div[class*="web-result"], div.result, div.web-result').each((index: number, element: any) => {
      const el = $(element);

      // Title and link: h2 > a
      const linkEl = el.find('h2 a, h2 > a');
      const title = linkEl.text().trim();
      let url = linkEl.attr('href') ?? '';

      // Sometimes DDG returns relative redirect URLs
      if (url.startsWith('/l/')) {
        url = `https://html.duckduckgo.com${url}`;
      }

      // Content: a.result__snippet
      const snippetEl = el.find('a.result__snippet');
      const content = snippetEl.text().trim();

      if (title && url) {
        results.push({
          title,
          url,
          content: content || undefined,
          position: index + 1,
        });
      }
    });

    // --- Zero-click info (featured snippet) ---
    const zeroClick = $('div#zero_click_abstract');
    if (zeroClick.length > 0) {
      const zcText = zeroClick.text().trim();
      if (zcText && results.length > 0) {
        // Enhance the first result with zero-click abstract if it has no content
        if (!results[0].content) {
          results[0].content = zcText;
        }
      }
    }

    return results;
  }
}
