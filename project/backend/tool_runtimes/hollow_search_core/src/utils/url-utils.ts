const TRACKING_PARAMS = [
  'utm_source',
  'utm_medium',
  'utm_campaign',
  'utm_term',
  'utm_content',
  'utm_id',
  'utm_source_platform',
  'utm_creative_format',
  'utm_marketing_tactic',
  'fbclid',
  'gclid',
  'gbraid',
  'wbraid',
  'msclkid',
  'dclid',
  'twclid',
  'li_fat_id',
  'mc_cid',
  'mc_eid',
  '_ga',
  '_gid',
  '_gac',
  '_gl',
  'oly_anon_id',
  'oly_enc_id',
  'rb_clickid',
  's_kwcid',
  'ef_id',
  'epik',
  'pk_campaign',
  'pk_kwd',
  'pk_keyword',
  'pk_source',
  'pk_medium',
  'pk_content',
  'pk_cid',
  'piwik_campaign',
  'piwik_kwd',
  'piwik_keyword',
  'mtm_campaign',
  'mtm_source',
  'mtm_medium',
  'mtm_content',
  'mtm_cid',
  'mtm_group',
  'mtm_placement',
  'matomo_campaign',
  'matomo_source',
  'matomo_medium',
  'matomo_content',
  'matomo_cid',
  'matomo_group',
  'matomo_placement',
  'itm_source',
  'itm_medium',
  'itm_campaign',
  'itm_term',
  'itm_content',
];

export interface NormalizeUrlOptions {
  forceHttp?: boolean;
  stripAmp?: boolean;
}

export function normalizeUrl(
  url: string,
  options: NormalizeUrlOptions = {},
): string {
  if (!url || typeof url !== 'string') {
    return '';
  }

  let parsed: URL;
  try {
    parsed = new URL(url.trim());
  } catch {
    return url.trim();
  }

  parsed.hash = '';

  for (const param of TRACKING_PARAMS) {
    parsed.searchParams.delete(param);
  }

  if (parsed.search === '' || parsed.search === '?') {
    parsed.search = '';
  }

  if (parsed.pathname.length > 1 && parsed.pathname.endsWith('/')) {
    parsed.pathname = parsed.pathname.slice(0, -1);
  }

  if (options.forceHttp ?? true) {
    parsed.protocol = 'http:';
  }

  if (options.stripAmp ?? true) {
    parsed.pathname = parsed.pathname
      .replace(/\/amp\//g, '/')
      .replace(/\/amp\./g, '/')
      .replace(/\/+/g, '/');
  }

  return parsed.toString();
}

export function domainFromUrl(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, '');
  } catch {
    return '';
  }
}
