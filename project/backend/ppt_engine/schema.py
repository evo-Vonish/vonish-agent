"""VonishAgent PPT Artifact Engine — core data contract.

Every stage of the pipeline binds to these types:

    DeckDesignSpec  (agent picks theme + layout + content; never pixels)
      -> SlideIR    (deterministic per-slide intermediate representation:
                     elements, roles, bounding boxes — computed by the layout
                     engine, NOT by the model)
      -> PPTX       (python-pptx renderer reads SlideIR)
      -> ValidationReport (validator reads SlideIR)
      -> ArtifactPreview[] (Pillow renders the same SlideIR to PNG)

Geometry contract (single source of truth):
  * Canvas is pixels. Default 1280x720 (16:9).
  * BBox is [x, y, width, height] in canvas pixels.
  * Font sizes are in points (pt).
  * Renderers convert: 1 px = 9525 EMU; 1 pt = 96/72 px = 1.3333 px.

The model only ever emits a DeckDesignSpec (theme id + layout id + content).
It must never set x/y/w/h or raw colors/fonts — those come from the Theme and
the Layout engine. This separation is the whole point of the engine.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"

# Geometry constants ---------------------------------------------------------
DEFAULT_CANVAS_W = 1280
DEFAULT_CANVAS_H = 720
EMU_PER_PX = 9525          # 1280px -> 12192000 EMU (13.333in widescreen)
PX_PER_PT = 96.0 / 72.0    # 1pt -> 1.3333px at 96dpi


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class ElementType(str, Enum):
    TEXT = "text"
    SHAPE = "shape"
    IMAGE = "image"
    GROUP = "group"
    CHART = "chart"
    TABLE = "table"
    LINE = "line"


class ElementRole(str, Enum):
    TITLE = "title"
    SUBTITLE = "subtitle"
    BODY = "body"
    BULLET = "bullet"
    CARD = "card"
    CARD_TITLE = "card_title"
    CARD_BODY = "card_body"
    IMAGE = "image"
    CHART = "chart"
    QUOTE = "quote"
    CODE = "code"
    FOOTER = "footer"
    META = "meta"
    BADGE = "badge"
    DECORATION = "decoration"
    LEGEND = "legend"
    STEP = "step"
    MILESTONE = "milestone"
    DIAGRAM = "diagram"
    BACKGROUND = "background"
    ACCENTBAR = "accent_bar"


class ShapeType(str, Enum):
    RECT = "rect"
    ROUNDED_RECT = "rounded_rect"
    ELLIPSE = "ellipse"
    LINE = "line"
    ARROW = "arrow"
    CHEVRON = "chevron"
    PILL = "pill"


class Align(str, Enum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"
    JUSTIFY = "justify"


class VAlign(str, Enum):
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


class FixStrategy(str, Enum):
    AUTO = "auto"
    AGENT = "agent"
    USER = "user"
    NONE = "none"


class IssueType(str, Enum):
    TEXT_OVERFLOW = "TEXT_OVERFLOW"
    ELEMENT_OVERLAP = "ELEMENT_OVERLAP"
    OUT_OF_BOUNDS = "OUT_OF_BOUNDS"
    UNSAFE_MARGIN = "UNSAFE_MARGIN"
    TITLE_TOO_LONG = "TITLE_TOO_LONG"
    FONT_TOO_SMALL = "FONT_TOO_SMALL"
    COLOR_OUT_OF_THEME = "COLOR_OUT_OF_THEME"
    LOW_CONTRAST = "LOW_CONTRAST"
    FONT_CHAOS = "FONT_CHAOS"
    EMPTY_SLIDE = "EMPTY_SLIDE"
    OVERCROWDED_SLIDE = "OVERCROWDED_SLIDE"
    MISSING_PREVIEW = "MISSING_PREVIEW"
    INCONSISTENT_STYLE = "INCONSISTENT_STYLE"
    # L2 image-grounded checks (visual QA)
    RENDERED_BLANK = "RENDERED_BLANK"
    IMAGE_BLURRY = "IMAGE_BLURRY"
    COLOR_DRIFT = "COLOR_DRIFT"
    RENDER_TEXT_MISSING = "RENDER_TEXT_MISSING"


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
class BBox(BaseModel):
    """Bounding box in canvas pixels."""
    x: float
    y: float
    width: float
    height: float

    @property
    def x2(self) -> float:
        return self.x + self.width

    @property
    def y2(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return max(0.0, self.width) * max(0.0, self.height)

    def intersection_area(self, other: "BBox") -> float:
        ix = max(0.0, min(self.x2, other.x2) - max(self.x, other.x))
        iy = max(0.0, min(self.y2, other.y2) - max(self.y, other.y))
        return ix * iy

    def as_list(self) -> list[float]:
        return [round(self.x, 2), round(self.y, 2), round(self.width, 2), round(self.height, 2)]


class Canvas(BaseModel):
    width: int = DEFAULT_CANVAS_W
    height: int = DEFAULT_CANVAS_H
    unit: Literal["px"] = "px"


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------
class ThemeTokens(BaseModel):
    """Color tokens. Every color used in a deck must trace back to here."""
    background: str
    surface: str
    surfaceElevated: str
    primary: str
    accent: str
    accentSecondary: str
    text: str
    textMuted: str
    textInverse: str
    border: str
    borderSubtle: str
    warning: str = "#F59E0B"
    success: str = "#10B981"
    error: str = "#EF4444"
    chart: list[str] = Field(default_factory=list)

    def palette(self) -> list[str]:
        """All allowed colors (lowercased hex) for theme-conformance checks."""
        base = [
            self.background, self.surface, self.surfaceElevated, self.primary,
            self.accent, self.accentSecondary, self.text, self.textMuted,
            self.textInverse, self.border, self.borderSubtle, self.warning,
            self.success, self.error,
        ]
        return [c.lower() for c in (base + list(self.chart)) if c]


class FontStack(BaseModel):
    headingChinese: str = '"Noto Sans SC", "PingFang SC", "Microsoft YaHei"'
    headingEnglish: str = '"Inter", "SF Pro Display", "Helvetica Neue"'
    bodyChinese: str = '"Noto Sans SC", "PingFang SC", "Microsoft YaHei"'
    bodyEnglish: str = '"Inter", "SF Pro Text", "Helvetica Neue"'
    code: str = '"JetBrains Mono", "Fira Code", "Consolas"'
    fallback: list[str] = Field(default_factory=lambda: ["sans-serif"])

    def heading_primary(self) -> str:
        return _first_family(self.headingChinese) or _first_family(self.headingEnglish) or "Arial"

    def body_primary(self) -> str:
        return _first_family(self.bodyChinese) or _first_family(self.bodyEnglish) or "Arial"

    def code_primary(self) -> str:
        return _first_family(self.code) or "Consolas"


class Spacing(BaseModel):
    xs: int = 4
    sm: int = 8
    md: int = 16
    lg: int = 24
    xl: int = 32


class SafeMargin(BaseModel):
    """Fractions of the canvas dimension."""
    top: float = 0.08
    right: float = 0.06
    bottom: float = 0.08
    left: float = 0.06


class Grid(BaseModel):
    columns: int = 12
    gutter: int = 16


class LayoutRules(BaseModel):
    safeMargin: SafeMargin = Field(default_factory=SafeMargin)
    whitespaceRatio: float = 0.35
    grid: Grid = Field(default_factory=Grid)
    spacing: Spacing = Field(default_factory=Spacing)
    cardRadius: int = 8
    shadowIntensity: Literal["none", "subtle", "medium", "strong"] = "subtle"


class TypographyRules(BaseModel):
    titleSize: int = 32
    subtitleSize: int = 20
    bodySize: int = 18
    captionSize: int = 14
    minBodySize: int = 14
    minTitleSize: int = 24
    maxTitleSize: int = 44
    lineHeight: float = 1.35
    headingBold: bool = True


class ContentConstraints(BaseModel):
    maxCharsPerSlide: int = 320
    maxTitleLength: int = 60
    bodyFontMin: int = 14
    bodyFontMax: int = 24
    maxBodyLines: int = 8
    maxCards: int = 4
    maxListItems: int = 7
    maxChartSeries: int = 6


HARD_CONSTRAINTS = [
    "NO_RANDOM_COLOR", "NO_LOW_CONTRAST", "NO_TEXT_OVERFLOW", "NO_FONT_CHAOS",
    "NO_OVERLAP", "NO_EDGE_TOUCH", "NO_SMALL_FONT", "NO_OVERCROWD",
    "NO_LONG_TITLE", "NO_EMPTY_SLIDE",
]


class Theme(BaseModel):
    theme_id: str
    name: str
    family: Literal["base", "industry", "brand"] = "base"
    description: str = ""
    mode: Literal["light", "dark"] = "dark"
    tokens: ThemeTokens
    fonts: FontStack = Field(default_factory=FontStack)
    layout_rules: LayoutRules = Field(default_factory=LayoutRules)
    typography: TypographyRules = Field(default_factory=TypographyRules)
    constraints: ContentConstraints = Field(default_factory=ContentConstraints)


# ---------------------------------------------------------------------------
# Layout recipes
# ---------------------------------------------------------------------------
class RelativePosition(BaseModel):
    """Position hint as fractions of the content area (after safe margins)."""
    x: float = 0.0
    y: float = 0.0
    w: float = 1.0
    h: float = 1.0


class SlotDefinition(BaseModel):
    id: str
    role: ElementRole
    type: ElementType
    required: bool = False
    repeatable: bool = False
    max_count: int = 1
    position: Optional[RelativePosition] = None


class LayoutRecipe(BaseModel):
    id: str
    name: str
    description: str = ""
    category: Literal["cover", "toc", "chapter", "content", "data", "closing"] = "content"
    slots: list[SlotDefinition] = Field(default_factory=list)
    constraints: ContentConstraints = Field(default_factory=ContentConstraints)


# ---------------------------------------------------------------------------
# Agent-facing content (the only thing the model authors per slide)
# ---------------------------------------------------------------------------
class CardContent(BaseModel):
    title: str = ""
    body: str = ""
    icon: str = ""


class ColumnContent(BaseModel):
    title: str = ""
    body: str = ""
    bullets: list[str] = Field(default_factory=list)


class StepContent(BaseModel):
    title: str = ""
    body: str = ""
    label: str = ""


class ChartSeries(BaseModel):
    name: str = ""
    values: list[float] = Field(default_factory=list)


class ChartContent(BaseModel):
    type: Literal["bar", "column", "line", "pie", "area"] = "column"
    categories: list[str] = Field(default_factory=list)
    series: list[ChartSeries] = Field(default_factory=list)
    insight: str = ""


class CodeContent(BaseModel):
    language: str = "text"
    code: str = ""
    annotation: str = ""


class QuoteContent(BaseModel):
    text: str = ""
    author: str = ""
    context: str = ""


class DiagramNode(BaseModel):
    id: str = ""
    label: str = ""
    group: str = ""


class DiagramEdge(BaseModel):
    source: str = ""
    target: str = ""
    label: str = ""


class DiagramContent(BaseModel):
    nodes: list[DiagramNode] = Field(default_factory=list)
    edges: list[DiagramEdge] = Field(default_factory=list)
    legend: list[str] = Field(default_factory=list)


class SlideContent(BaseModel):
    """Loose content bag — each layout reads the fields it needs."""
    title: str = ""
    subtitle: str = ""
    meta: str = ""
    chapter_number: str = ""
    body: str = ""
    bullets: list[str] = Field(default_factory=list)
    cards: list[CardContent] = Field(default_factory=list)
    left: Optional[ColumnContent] = None
    right: Optional[ColumnContent] = None
    items: list[StepContent] = Field(default_factory=list)
    chart: Optional[ChartContent] = None
    code: Optional[CodeContent] = None
    quote: Optional[QuoteContent] = None
    diagram: Optional[DiagramContent] = None
    footer: str = ""
    emphasis: list[str] = Field(default_factory=list)


class SlideSpec(BaseModel):
    """One slide in the agent-authored DeckDesignSpec."""
    layout_id: str
    content: SlideContent = Field(default_factory=SlideContent)
    notes: str = ""
    theme_overrides: dict[str, Any] = Field(default_factory=dict)


class DeckDesignSpec(BaseModel):
    spec_version: str = SCHEMA_VERSION
    deck_id: str = ""
    title: str = ""
    theme_id: str = "tech-dark"
    canvas: Canvas = Field(default_factory=Canvas)
    slides: list[SlideSpec] = Field(default_factory=list)
    created_at: str = ""
    agent_version: str = "vonish-ppt-engine-1.0"


# ---------------------------------------------------------------------------
# SlideIR (deterministic, computed by the layout engine)
# ---------------------------------------------------------------------------
class TextStyle(BaseModel):
    fontSize: float = 18.0            # points
    fontFamily: str = "Arial"
    color: str = "#000000"
    bold: bool = False
    italic: bool = False
    align: Align = Align.LEFT
    valign: VAlign = VAlign.TOP
    lineHeight: float = 1.35
    role: Literal["heading", "body", "code"] = "body"


class ShapeStyle(BaseModel):
    fill: Optional[str] = None
    stroke: Optional[str] = None
    strokeWidth: float = 0.0
    radius: float = 0.0
    shadow: Literal["none", "subtle", "medium", "strong"] = "none"
    opacity: float = 1.0


class SlideElement(BaseModel):
    element_id: str
    role: ElementRole = ElementRole.BODY
    type: ElementType = ElementType.TEXT
    bbox: BBox
    z_index: int = 10
    editable: bool = True
    text: str = ""
    text_style: Optional[TextStyle] = None
    shape_type: Optional[ShapeType] = None
    shape_style: Optional[ShapeStyle] = None
    chart: Optional[ChartContent] = None
    children: list["SlideElement"] = Field(default_factory=list)
    source_references: list[str] = Field(default_factory=list)

    def flatten(self) -> list["SlideElement"]:
        out = [self]
        for child in self.children:
            out.extend(child.flatten())
        return out


class SlideBackground(BaseModel):
    type: Literal["solid", "gradient"] = "solid"
    color: str = "#0A0E1A"
    color2: Optional[str] = None


class SlideIR(BaseModel):
    slide_ir_version: str = SCHEMA_VERSION
    deck_id: str = ""
    slide_id: str = ""
    slide_index: int = 0
    layout_id: str = ""
    theme_id: str = ""
    canvas: Canvas = Field(default_factory=Canvas)
    background: SlideBackground = Field(default_factory=SlideBackground)
    elements: list[SlideElement] = Field(default_factory=list)
    notes: str = ""

    def all_elements(self) -> list[SlideElement]:
        out: list[SlideElement] = []
        for el in self.elements:
            out.extend(el.flatten())
        return out


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------
class SuggestedFix(BaseModel):
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)


class ValidatorIssue(BaseModel):
    id: str = ""
    type: IssueType
    severity: Severity = Severity.WARNING
    slide_id: str = ""
    slide_index: int = 0
    element_id: str = ""
    element_ids: list[str] = Field(default_factory=list)
    element_role: str = ""
    message: str = ""
    current_value: dict[str, Any] = Field(default_factory=dict)
    fixable: bool = False
    fix_strategy: FixStrategy = FixStrategy.NONE
    suggested_fix: Optional[SuggestedFix] = None
    auto_fixed: bool = False


class ValidationSummary(BaseModel):
    total_issues: int = 0
    error_count: int = 0
    warning_count: int = 0
    info_count: int = 0
    fixable_auto: int = 0
    fixable_agent: int = 0
    requires_user: int = 0
    auto_fixed: int = 0


class ValidationReport(BaseModel):
    validation_id: str = ""
    deck_id: str = ""
    timestamp: str = ""
    repair_rounds: int = 0
    delivery_grade: Literal[
        "perfect", "good", "acceptable", "degraded", "blocked"
    ] = "good"
    deliverable: bool = True
    summary: ValidationSummary = Field(default_factory=ValidationSummary)
    issues: list[ValidatorIssue] = Field(default_factory=list)
    blocking_issue_types: list[str] = Field(default_factory=list)

    def errors(self) -> list[ValidatorIssue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]


# ---------------------------------------------------------------------------
# Element Patch protocol (Phase 2)
# ---------------------------------------------------------------------------
class PatchOperation(BaseModel):
    op: Literal[
        "replace_text", "update_style", "update_shape_style",
        "move", "resize", "add_decoration", "delete",
    ]
    target: str
    value: Optional[str] = None
    changes: dict[str, Any] = Field(default_factory=dict)
    decoration: dict[str, Any] = Field(default_factory=dict)


class ElementPatch(BaseModel):
    protocol_version: str = SCHEMA_VERSION
    patch_id: str = ""
    deck_id: str = ""
    slide_id: str = ""
    slide_index: int = 0
    operations: list[PatchOperation] = Field(default_factory=list)
    patch_scope: Literal["element_only", "slide"] = "element_only"
    reasoning: str = ""


# ---------------------------------------------------------------------------
# Artifact output
# ---------------------------------------------------------------------------
class ArtifactPreview(BaseModel):
    slide_id: str = ""
    slide_index: int = 0
    path: str = ""               # workspace-relative PNG path
    width: int = DEFAULT_CANVAS_W
    height: int = DEFAULT_CANVAS_H
    title: str = ""


class ElementBox(BaseModel):
    """Lightweight element metadata for the workbench overlay (Phase 2)."""
    element_id: str
    role: str
    type: str
    bbox: list[float]
    text: str = ""


class SlideMeta(BaseModel):
    slide_id: str
    slide_index: int
    layout_id: str
    title: str = ""
    preview: str = ""
    elements: list[ElementBox] = Field(default_factory=list)


class DeckVersion(BaseModel):
    """One saved snapshot of a deck's SlideIR, for version history / rollback."""
    version_id: str = ""
    index: int = 0
    label: str = ""
    kind: Literal["generate", "patch", "restore"] = "generate"
    created_at: str = ""
    slide_count: int = 0
    grade: str = ""
    slideir_path: str = ""        # workspace-relative snapshot path


class VisualFinding(BaseModel):
    """One L2 image-grounded observation about a rendered slide."""
    slide_index: int = 0
    metric: str = ""              # blankness | sharpness | color_drift | text_presence
    score: float = 0.0
    ok: bool = True
    detail: str = ""


class DesignReview(BaseModel):
    """One L3 design-judge review of a slide (does NOT block delivery)."""
    slide_id: str = ""
    slide_index: int = 0
    score: float = 0.0            # 1-5
    severity: Literal["info", "low", "medium", "high"] = "info"
    visual_issues: list[str] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)
    dimension: str = "overall"


class DesignJudgeReport(BaseModel):
    """L3 judge output for a deck. ``mode`` records how it was produced."""
    enabled: bool = False
    mode: Literal["disabled", "mock", "local", "manual"] = "disabled"
    provider: str = ""
    average_score: float = 0.0
    reviews: list[DesignReview] = Field(default_factory=list)
    summary: str = ""


class ReferenceDeckProfile(BaseModel):
    """Style profile extracted from a user-supplied reference .pptx."""
    source_path: str = ""
    slide_count: int = 0
    aspect_ratio: str = ""
    palette: list[str] = Field(default_factory=list)         # hex colours, by frequency
    fonts: list[str] = Field(default_factory=list)
    title_positions: list[str] = Field(default_factory=list)  # top|center|left ...
    element_type_counts: dict[str, int] = Field(default_factory=dict)
    layout_hints: list[str] = Field(default_factory=list)
    suggested_theme_id: str = ""
    suggested_layouts: list[str] = Field(default_factory=list)
    notes: str = ""


class DeckResult(BaseModel):
    """Full output of an engine run, persisted as a sidecar manifest."""
    artifact_id: str = ""
    deck_id: str = ""
    title: str = ""
    theme_id: str = ""
    pptx_path: str = ""           # workspace-relative
    deck_spec_path: str = ""
    slide_ir_path: str = ""
    manifest_path: str = ""
    slide_count: int = 0
    previews: list[ArtifactPreview] = Field(default_factory=list)
    slides_meta: list[SlideMeta] = Field(default_factory=list)
    validation: ValidationReport = Field(default_factory=ValidationReport)
    versions: list[DeckVersion] = Field(default_factory=list)
    visual_findings: list[VisualFinding] = Field(default_factory=list)
    design_review: Optional[DesignJudgeReport] = None
    generation_log: list[str] = Field(default_factory=list)
    created_at: str = ""


SlideElement.model_rebuild()
ElementBox.model_rebuild()


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------
def _first_family(stack: str) -> str:
    """First concrete font family name from a CSS-style font stack."""
    if not stack:
        return ""
    first = stack.split(",")[0].strip()
    return first.strip('"').strip("'").strip()
