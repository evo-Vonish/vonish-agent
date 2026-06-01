import type { ModeConfig, PurifyMode } from './types.js';

const MODE_CONFIGS: Record<PurifyMode, ModeConfig> = {
  conservative: {
    mode: 'conservative',
    minConfidenceScore: 0.85,
    requireMultipleSignals: true,
    charThreshold: 300,
    useGenericSelectors: false,
    linkDensityThreshold: 0.6,
  },
  balanced: {
    mode: 'balanced',
    minConfidenceScore: 0.65,
    requireMultipleSignals: true,
    charThreshold: 500,
    useGenericSelectors: true,
    linkDensityThreshold: 0.5,
  },
  aggressive: {
    mode: 'aggressive',
    minConfidenceScore: 0.45,
    requireMultipleSignals: false,
    charThreshold: 200,
    useGenericSelectors: true,
    linkDensityThreshold: 0.35,
  },
};

export function getModeConfig(mode: PurifyMode): ModeConfig {
  return { ...MODE_CONFIGS[mode] };
}

export { MODE_CONFIGS };
