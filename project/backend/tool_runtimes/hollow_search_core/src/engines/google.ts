import * as cheerio from 'cheerio';
import { EngineAdapter, EngineResponse } from './engine.js';
import { SearchRequest, RawResult, RequestParams, EngineConfig } from '../types.js';

const GOOGLE_CONFIG: EngineConfig = {
  name: 'google',
  shortcut: 'go',
  disabled: false,
  weight: 1,
  timeout: 10000,
  categories: ['general'],
};

export class GoogleEngine extends EngineAdapter {
  readonly name = 'google';
  readonly config: EngineConfig;

  constructor(config: EngineConfig = GOOGLE_CONFIG) {
    super();
    this.config = config;
  }

  buildRequest(query: string, req: SearchRequest): RequestParams {
    const params = new URLSearchParams({
      q: query,
      hl: req.language?.split('-')[0] ?? 'en',
      num: '10',
    });

    const pageno = req.pageno ?? 1;
    if (pageno > 1) {
      params.set('start', String((pageno - 1) * 10));
    }

    return {
      query,
      pageno,
      safesearch: (req.safesearch ?? 0) as 0 | 1 | 2,
      time_range: req.timeRange,
      language: req.language ?? 'en-US',
      headers: {
        'User-Agent':
          'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0',
        Accept: 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        Referer: 'https://www.google.com/',
      },
      cookies: {
        CONSENT: 'YES+1',
      },
      method: 'GET',
      url: `https://www.google.com/search?${params.toString()}`,
    };
  }

  async parseResponse(resp: EngineResponse): Promise<RawResult[]> {
    if (resp.status >= 400) {
      return [];
    }

    const $ = cheerio.load(await resp.text());
    const results: RawResult[] = [];

    $('a').each((_index: number, element: any) => {
      if (results.length >= 10) {
        return;
      }

      const href = $(element).attr('href') ?? '';
      const title = $(element).find('h3').first().text().trim();
      if (!title || !href.startsWith('http')) {
        return;
      }

      const container = $(element).closest('div');
      const content = container.text().replace(/\s+/g, ' ').trim();
      results.push({
        title,
        url: href,
        content: content === title ? undefined : content,
        position: results.length + 1,
      });
    });

    return results;
  }
}
