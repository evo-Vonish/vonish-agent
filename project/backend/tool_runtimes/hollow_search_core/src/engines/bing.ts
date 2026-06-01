// Bing search engine adapter
// Translated from SearXNG searx/engines/bing.py

import * as cheerio from 'cheerio';
import { EngineAdapter, EngineResponse } from './engine.js';
import { SearchRequest, RawResult, RequestParams, EngineConfig } from '../types.js';

/**
 * Bing engine configuration.
 */
const BING_CONFIG: EngineConfig = {
  name: 'bing',
  shortcut: 'bi',
  disabled: false,
  weight: 1,
  timeout: 10000,
  categories: ['general'],
};

/**
 * SafeSearch mapping for Bing query parameter.
 * 0 = off, 1 = moderate, 2 = strict
 * Bing uses adlt parameter: off=off, moderate=moderate, strict=strict
 */
function getSafesearchParam(level: 0 | 1 | 2): string {
  switch (level) {
    case 0: return 'off';
    case 2: return 'strict';
    case 1:
    default: return 'moderate';
  }
}

/**
 * Bing uses redirect URLs of the form:
 *   https://www.bing.com/ck/a?...&u=a1{base64}...
 * We need to extract and decode the `u` parameter.
 *
 * From SearXNG Python code:
 *   u_val = u_values[0]
 *   if u_val.startswith("a1"):
 *       encoded = u_val[2:]
 *       encoded += "=" * (-len(encoded) % 4)
 *       href = base64.urlsafe_b64decode(encoded).decode("utf-8")
 */
function decodeBingRedirect(url: string): string {
  try {
    const parsed = new URL(url);
    const uParam = parsed.searchParams.get('u');
    if (!uParam) return url;

    if (uParam.startsWith('a1')) {
      let encoded = uParam.slice(2);
      // Add padding for base64
      encoded += '='.repeat((-encoded.length) % 4);
      // Use Buffer for url-safe base64 decode
      const decoded = Buffer.from(encoded, 'base64').toString('utf-8');
      return decoded || url;
    }

    return url;
  } catch {
    return url;
  }
}

/**
 * Bing search engine adapter.
 *
 * Request: GET https://www.bing.com/search?q={query}&adlt={safesearch}
 * Response: HTML parsed with cheerio
 *
 * Special handling: Bing encodes result URLs via its own redirect endpoint.
 * The real URL is base64-encoded in the `u` parameter of /ck/a links.
 */
export class BingEngine extends EngineAdapter {
  readonly name = 'bing';
  readonly config: EngineConfig;

  constructor(config: EngineConfig = BING_CONFIG) {
    super();
    this.config = config;
  }

  buildRequest(query: string, req: SearchRequest): RequestParams {
    const safesearch = req.safesearch ?? 0;
    const params = new URLSearchParams({
      q: query,
    });

    // SafeSearch parameter
    params.set('adlt', getSafesearchParam(safesearch as 0 | 1 | 2));

    // Pagination: Bing uses `first` parameter (1, 11, 21, ...)
    const pageno = req.pageno ?? 1;
    if (pageno > 1) {
      params.set('first', String((pageno - 1) * 10 + 1));
    }

    // Language interface
    if (req.language) {
      params.set('setlang', req.language);
      params.set('mkt', req.language);
    }

    return {
      query,
      pageno,
      safesearch: safesearch as 0 | 1 | 2,
      time_range: req.timeRange,
      language: req.language ?? 'en',
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0',
        Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        Referer: 'https://www.bing.com/',
        DNT: '1',
        Connection: 'keep-alive',
      },
      cookies: {
        // Bing region cookie
        MKT: req.language ?? 'en-US',
      },
      method: 'GET',
      url: `https://www.bing.com/search?${params.toString()}`,
    };
  }

  async parseResponse(resp: EngineResponse, _params: RequestParams): Promise<RawResult[]> {
    const html = await resp.text();
    const $ = cheerio.load(html);
    const results: RawResult[] = [];

    $('li.b_algo').each((index: number, element: any) => {
      const el = $(element);

      // Title and link: h2 > a
      const linkEl = el.find('h2 > a');
      const title = linkEl.text().trim();
      let url = linkEl.attr('href') ?? '';

      // Decode Bing redirect URLs
      if (url.startsWith('https://www.bing.com/ck/a?')) {
        url = decodeBingRedirect(url);
      }

      // Content: p element within the result
      const contentEl = el.find('p');
      const content = contentEl.text().trim();

      if (title && url) {
        results.push({
          title,
          url,
          content: content || undefined,
          position: index + 1,
        });
      }
    });

    return results;
  }
}
