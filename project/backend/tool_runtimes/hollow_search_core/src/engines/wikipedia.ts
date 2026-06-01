// Wikipedia search engine adapter
// Translated from SearXNG searx/engines/wikipedia.py

import * as cheerio from 'cheerio';
import { EngineAdapter, EngineResponse } from './engine.js';
import { SearchRequest, RawResult, RequestParams, EngineConfig } from '../types.js';

/**
 * Wikipedia engine configuration.
 */
const WIKIPEDIA_CONFIG: EngineConfig = {
  name: 'wikipedia',
  shortcut: 'wp',
  disabled: false,
  weight: 1,
  timeout: 10000,
  categories: ['general'],
};

/**
 * Build the Wikipedia REST API URL for a given title and language.
 *
 * The title needs to be URL-encoded. If the query is all lowercase,
 * capitalize the first letter (Wikipedia convention).
 */
function buildWikiUrl(title: string, language: string): string {
  const lang = language || 'en';
  const wikiNetloc = `${lang}.wikipedia.org`;

  // If query is all lowercase, apply title case (Python str.title() equivalent)
  let pageTitle = title;
  if (pageTitle === pageTitle.toLowerCase()) {
    pageTitle = pageTitle.replace(/\b\w/g, (c) => c.toUpperCase());
  }

  // URL-encode the title (spaces -> underscores, then encode)
  pageTitle = pageTitle.replace(/\s+/g, '_');
  const encodedTitle = encodeURIComponent(pageTitle);

  return `https://${wikiNetloc}/api/rest_v1/page/summary/${encodedTitle}`;
}

/**
 * Wikipedia Summary API response shape (partial).
 */
interface WikiSummaryResponse {
  title?: string;
  titles?: {
    canonical?: string;
    normalized?: string;
    display?: string;
  };
  description?: string;
  extract?: string;
  thumbnail?: {
    source?: string;
    width?: number;
    height?: number;
  };
  content_urls?: {
    desktop?: {
      page?: string;
      revisions?: string;
      edit?: string;
      talk?: string;
    };
    mobile?: {
      page?: string;
      revisions?: string;
      edit?: string;
      talk?: string;
    };
  };
  type?: string;
  detail?: string;
}

/**
 * Wikipedia search engine adapter.
 *
 * Uses the Wikipedia REST API (Summary endpoint) rather than HTML scraping.
 *
 * Request: GET https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}
 * Response: JSON
 *
 * Field mapping:
 *   - title: titles.display or title
 *   - content: description or extract
 *   - url: content_urls.desktop.page
 *   - thumbnail: thumbnail.source
 *
 * Error handling:
 *   - 404 -> return empty results (page not found)
 *   - 400 -> return empty results (bad request)
 */
export class WikipediaEngine extends EngineAdapter {
  readonly name = 'wikipedia';
  readonly config: EngineConfig;

  constructor(config: EngineConfig = WIKIPEDIA_CONFIG) {
    super();
    this.config = config;
  }

  buildRequest(query: string, req: SearchRequest): RequestParams {
    const language = req.language ?? 'en';
    const url = buildWikiUrl(query, language);

    return {
      query,
      pageno: req.pageno ?? 1,
      safesearch: (req.safesearch ?? 0) as 0 | 1 | 2,
      time_range: req.timeRange,
      language,
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.0',
        Accept: 'application/json; charset=utf-8;q=0.9, */*;q=0.1',
        'Accept-Language': 'en-US,en;q=0.5',
        'Api-User-Agent': 'Mini-SearXNG/1.0',
        Connection: 'keep-alive',
      },
      cookies: {},
      method: 'GET',
      url,
    };
  }

  async parseResponse(resp: EngineResponse, _params: RequestParams): Promise<RawResult[]> {
    // Handle 404 and 400 gracefully -> return empty results
    if (resp.status === 404 || resp.status === 400) {
      return [];
    }

    // Handle non-OK status codes
    if (resp.status < 200 || resp.status >= 300) {
      throw new Error(`Wikipedia API returned status ${resp.status}`);
    }

    const body = await resp.json() as WikiSummaryResponse;

    // If the API returned a detail error message
    if (body.detail) {
      return [];
    }

    // Determine title: prefer titles.display, fallback to title
    const title = cheerio.load(body.titles?.display ?? body.title ?? '').text();

    // Determine content: prefer description, fallback to extract
    const content = body.description ?? body.extract ?? '';

    // Determine URL
    const url = body.content_urls?.desktop?.page ?? '';

    // Thumbnail
    const thumbnail = body.thumbnail?.source;

    if (!title || !url) {
      return [];
    }

    return [
      {
        title,
        url,
        content: content || undefined,
        thumbnail: thumbnail || undefined,
        position: 1,
      },
    ];
  }
}
