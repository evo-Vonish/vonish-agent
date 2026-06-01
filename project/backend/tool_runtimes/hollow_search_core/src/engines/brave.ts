// Brave search engine adapter
// Translated from SearXNG searx/engines/brave.py

import * as cheerio from 'cheerio';
import { EngineAdapter, EngineResponse } from './engine.js';
import { SearchRequest, RawResult, RequestParams, EngineConfig } from '../types.js';

/**
 * Brave engine configuration.
 */
const BRAVE_CONFIG: EngineConfig = {
  name: 'brave',
  shortcut: 'br',
  disabled: false,
  weight: 1,
  timeout: 10000,
  categories: ['general'],
};

/**
 * SafeSearch mapping for Brave cookies.
 * 0 = off, 1 = moderate, 2 = strict
 */
function getSafesearchCookie(level: 0 | 1 | 2): string {
  switch (level) {
    case 0: return 'off';
    case 2: return 'strict';
    case 1:
    default: return 'moderate';
  }
}

/**
 * Brave search engine adapter.
 *
 * Request: GET https://search.brave.com/search?q={query}&source=web
 * Cookies: safesearch={off|moderate|strict}, useLocation=0, summarizer=0
 * Response: HTML parsed with cheerio
 */
export class BraveEngine extends EngineAdapter {
  readonly name = 'brave';
  readonly config: EngineConfig;

  constructor(config: EngineConfig = BRAVE_CONFIG) {
    super();
    this.config = config;
  }

  buildRequest(query: string, req: SearchRequest): RequestParams {
    const safesearch = req.safesearch ?? 0;
    const params = new URLSearchParams({
      q: query,
      source: 'web',
    });

    // pagination offset if supported
    if (req.pageno && req.pageno > 1) {
      params.set('offset', String((req.pageno - 1) * 20));
    }

    return {
      query,
      pageno: req.pageno ?? 1,
      safesearch: safesearch as 0 | 1 | 2,
      time_range: req.timeRange,
      language: req.language ?? 'en',
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0',
        Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        DNT: '1',
        Connection: 'keep-alive',
      },
      cookies: {
        safesearch: getSafesearchCookie(safesearch as 0 | 1 | 2),
        useLocation: '0',
        summarizer: '0',
      },
      method: 'GET',
      url: `https://search.brave.com/search?${params.toString()}`,
    };
  }

  async parseResponse(resp: EngineResponse, _params: RequestParams): Promise<RawResult[]> {
    const html = await resp.text();
    const $ = cheerio.load(html);
    const results: RawResult[] = [];

    $('div.snippet').each((index: number, element: any) => {
      const el = $(element);

      // Title
      const titleEl = el.find('.title');
      const title = titleEl.text().trim();

      // Link
      const linkEl = el.find('a');
      const url = linkEl.attr('href') ?? '';

      // Content
      const contentEl = el.find('div.content');
      const content = contentEl.text().trim();

      // Thumbnail
      const thumbEl = el.find('.thumbnail img');
      const thumbnail = thumbEl.attr('src');

      // Published date (if available)
      // Brave sometimes includes date info near the result
      let publishedDate: string | undefined;
      const dateEl = el.find('.result-header .url');
      const dateText = dateEl.text().trim();
      const dateMatch = dateText.match(/(\d{1,2})\s+(\w+)\s+(\d{4})/);
      if (dateMatch) {
        publishedDate = dateMatch[0];
      }

      if (title && url) {
        results.push({
          title,
          url,
          content: content || undefined,
          publishedDate,
          thumbnail: thumbnail || undefined,
          position: index + 1,
        });
      }
    });

    return results;
  }
}
