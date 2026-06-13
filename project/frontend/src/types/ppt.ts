/**
 * TypeScript mirror of the backend PPT engine output contract.
 *
 * Single source of truth: F:/Projects/VonishAgent/project/backend/ppt_engine/schema.py
 * SCHEMA_VERSION = "1.0".
 *
 * Field names intentionally match the JSON produced by pydantic `model_dump_json`
 * (snake_case, e.g. `delivery_grade`, `slides_meta`, `pptx_path`, `slide_index`,
 * `element_id`). The sidecar `deck.manifest.json` is a serialized `DeckResult`,
 * which `DeckManifest` aliases.
 *
 * Geometry note: every `bbox` is `[x, y, width, height]` in canvas pixels
 * (default canvas 1280x720). PNG previews live at the `path` fields and are
 * workspace-relative.
 */

/** One rendered-PNG preview for a slide (mirrors `ArtifactPreview`). */
export interface ArtifactPreview {
  slide_id: string;
  slide_index: number;
  /** workspace-relative PNG path */
  path: string;
  width: number;
  height: number;
  title: string;
}

/** Lightweight element metadata for the workbench overlay (mirrors `ElementBox`). */
export interface ElementBox {
  element_id: string;
  role: string;
  type: string;
  /** [x, y, width, height] in canvas pixels */
  bbox: [number, number, number, number] | number[];
  text: string;
}

/** Per-slide structural metadata (mirrors `SlideMeta`). */
export interface SlideMeta {
  slide_id: string;
  slide_index: number;
  layout_id: string;
  title: string;
  /** workspace-relative PNG path for this slide */
  preview: string;
  elements: ElementBox[];
}

/** Severity of a validator issue (mirrors `Severity`). */
export type Severity = 'error' | 'warning' | 'info';

/** How a validator issue may be repaired (mirrors `FixStrategy`). */
export type FixStrategy = 'auto' | 'agent' | 'user' | 'none';

/** Validator issue type identifiers (mirrors `IssueType`). */
export type IssueType =
  | 'TEXT_OVERFLOW'
  | 'ELEMENT_OVERLAP'
  | 'OUT_OF_BOUNDS'
  | 'UNSAFE_MARGIN'
  | 'TITLE_TOO_LONG'
  | 'FONT_TOO_SMALL'
  | 'COLOR_OUT_OF_THEME'
  | 'LOW_CONTRAST'
  | 'FONT_CHAOS'
  | 'EMPTY_SLIDE'
  | 'OVERCROWDED_SLIDE'
  | 'MISSING_PREVIEW'
  | 'INCONSISTENT_STYLE';

/** Suggested fix payload for a validator issue (mirrors `SuggestedFix`). */
export interface SuggestedFix {
  action: string;
  parameters: Record<string, unknown>;
}

/** A single validation finding (mirrors `ValidatorIssue`). */
export interface ValidatorIssue {
  id: string;
  type: IssueType | string;
  severity: Severity;
  slide_id: string;
  slide_index: number;
  element_id: string;
  element_ids: string[];
  element_role: string;
  message: string;
  current_value: Record<string, unknown>;
  fixable: boolean;
  fix_strategy: FixStrategy;
  suggested_fix: SuggestedFix | null;
  auto_fixed: boolean;
}

/** Aggregate counts across all validator issues (mirrors `ValidationSummary`). */
export interface ValidationSummary {
  total_issues: number;
  error_count: number;
  warning_count: number;
  info_count: number;
  fixable_auto: number;
  fixable_agent: number;
  requires_user: number;
  auto_fixed: number;
}

/** Delivery grade of a deck (mirrors the `delivery_grade` literal). */
export type DeliveryGrade = 'perfect' | 'good' | 'acceptable' | 'degraded' | 'blocked';

/** Full validation report for a deck (mirrors `ValidationReport`). */
export interface ValidationReport {
  validation_id: string;
  deck_id: string;
  timestamp: string;
  repair_rounds: number;
  delivery_grade: DeliveryGrade;
  deliverable: boolean;
  summary: ValidationSummary;
  issues: ValidatorIssue[];
  blocking_issue_types: string[];
}

/** One saved SlideIR snapshot for version history / rollback (mirrors `DeckVersion`). */
export interface DeckVersion {
  version_id: string;
  index: number;
  label: string;
  kind: 'generate' | 'patch' | 'restore';
  created_at: string;
  slide_count: number;
  grade: string;
  slideir_path: string;
}

/** One L2 image-grounded observation about a rendered slide (mirrors `VisualFinding`). */
export interface VisualFinding {
  slide_index: number;
  metric: string;
  score: number;
  ok: boolean;
  detail: string;
}

/** One L3 design-judge review of a slide (advisory — never blocks delivery). */
export interface DesignReview {
  slide_id: string;
  slide_index: number;
  score: number;
  severity: 'info' | 'low' | 'medium' | 'high';
  visual_issues: string[];
  suggestions: string[];
  dimension: string;
}

/** L3 design-judge report (mirrors `DesignJudgeReport`). */
export interface DesignJudgeReport {
  enabled: boolean;
  mode: 'disabled' | 'mock' | 'local' | 'manual';
  provider: string;
  average_score: number;
  reviews: DesignReview[];
  summary: string;
}

/**
 * The sidecar `deck.manifest.json` — a serialized `DeckResult`.
 * Sits next to the generated `deck.pptx`.
 */
export interface DeckManifest {
  artifact_id: string;
  deck_id: string;
  title: string;
  theme_id: string;
  /** workspace-relative path to the .pptx */
  pptx_path: string;
  deck_spec_path: string;
  slide_ir_path: string;
  manifest_path: string;
  slide_count: number;
  previews: ArtifactPreview[];
  slides_meta: SlideMeta[];
  validation: ValidationReport;
  versions: DeckVersion[];
  visual_findings: VisualFinding[];
  design_review: DesignJudgeReport | null;
  generation_log: string[];
  created_at: string;
}
