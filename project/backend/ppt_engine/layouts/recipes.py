"""Built-in layout recipes.

A recipe is a *contract*: it declares the slots a layout exposes and the
content constraints the validator/auto-fit honour. The geometry itself is
computed by ``ppt_engine.layouts.engine`` — recipes never carry pixel
coordinates, the layout algorithm does.
"""
from __future__ import annotations

from ..schema import (
    ContentConstraints,
    ElementRole,
    ElementType,
    LayoutRecipe,
    SlotDefinition,
)


def _slot(id_, role, type_=ElementType.TEXT, required=False, repeatable=False, max_count=1):
    return SlotDefinition(id=id_, role=role, type=type_, required=required,
                          repeatable=repeatable, max_count=max_count)


BUILTIN_LAYOUTS: dict[str, LayoutRecipe] = {
    "cover-center": LayoutRecipe(
        id="cover-center", name="封面居中 Cover", category="cover",
        description="Centered title + subtitle + meta line for the opening slide.",
        slots=[
            _slot("title", ElementRole.TITLE, required=True),
            _slot("subtitle", ElementRole.SUBTITLE),
            _slot("meta", ElementRole.META),
        ],
        constraints=ContentConstraints(maxTitleLength=48, maxCharsPerSlide=160),
    ),
    "toc-simple": LayoutRecipe(
        id="toc-simple", name="目录 Table of Contents", category="toc",
        description="Numbered agenda list, two columns when long.",
        slots=[
            _slot("title", ElementRole.TITLE, required=True),
            _slot("items", ElementRole.BULLET, repeatable=True, max_count=8),
        ],
        constraints=ContentConstraints(maxListItems=8),
    ),
    "chapter-break": LayoutRecipe(
        id="chapter-break", name="章节页 Chapter", category="chapter",
        description="Large chapter number + title + one-line description.",
        slots=[
            _slot("chapter_number", ElementRole.BADGE),
            _slot("title", ElementRole.TITLE, required=True),
            _slot("body", ElementRole.BODY),
        ],
        constraints=ContentConstraints(maxTitleLength=40, maxCharsPerSlide=120),
    ),
    "three-cards": LayoutRecipe(
        id="three-cards", name="三卡片 Three Cards", category="content",
        description="Title + up to 4 parallel cards (title + body each).",
        slots=[
            _slot("title", ElementRole.TITLE, required=True),
            _slot("cards", ElementRole.CARD, ElementType.GROUP, repeatable=True, max_count=4),
        ],
        constraints=ContentConstraints(maxCards=4, maxCharsPerSlide=300),
    ),
    "left-right": LayoutRecipe(
        id="left-right", name="左右对比 Left/Right", category="content",
        description="Title + two columns for comparison or before/after.",
        slots=[
            _slot("title", ElementRole.TITLE, required=True),
            _slot("left", ElementRole.BODY, ElementType.GROUP, required=True),
            _slot("right", ElementRole.BODY, ElementType.GROUP, required=True),
        ],
        constraints=ContentConstraints(maxCharsPerSlide=360),
    ),
    "timeline": LayoutRecipe(
        id="timeline", name="时间线 Timeline", category="content",
        description="Title + horizontal milestones along a baseline.",
        slots=[
            _slot("title", ElementRole.TITLE, required=True),
            _slot("items", ElementRole.MILESTONE, ElementType.GROUP, repeatable=True, max_count=5),
        ],
        constraints=ContentConstraints(maxListItems=5),
    ),
    "process": LayoutRecipe(
        id="process", name="流程 Process", category="content",
        description="Title + horizontal numbered steps with chevrons.",
        slots=[
            _slot("title", ElementRole.TITLE, required=True),
            _slot("items", ElementRole.STEP, ElementType.GROUP, repeatable=True, max_count=5),
        ],
        constraints=ContentConstraints(maxListItems=5),
    ),
    "architecture": LayoutRecipe(
        id="architecture", name="架构图 Architecture", category="content",
        description="Title + node/edge diagram area + legend.",
        slots=[
            _slot("title", ElementRole.TITLE, required=True),
            _slot("diagram", ElementRole.DIAGRAM, ElementType.GROUP, required=True),
            _slot("legend", ElementRole.LEGEND),
        ],
        constraints=ContentConstraints(maxCharsPerSlide=400),
    ),
    "data-chart": LayoutRecipe(
        id="data-chart", name="数据图表 Data Chart", category="data",
        description="Title + chart + insight callout.",
        slots=[
            _slot("title", ElementRole.TITLE, required=True),
            _slot("chart", ElementRole.CHART, ElementType.CHART, required=True),
            _slot("insight", ElementRole.BODY),
        ],
        constraints=ContentConstraints(maxChartSeries=6),
    ),
    "quote-center": LayoutRecipe(
        id="quote-center", name="引用 Quote", category="content",
        description="Large centered pull-quote + author.",
        slots=[
            _slot("quote", ElementRole.QUOTE, required=True),
            _slot("author", ElementRole.META),
        ],
        constraints=ContentConstraints(maxCharsPerSlide=200),
    ),
    "code-block": LayoutRecipe(
        id="code-block", name="代码 Code", category="content",
        description="Title + monospace code panel + annotation.",
        slots=[
            _slot("title", ElementRole.TITLE, required=True),
            _slot("code", ElementRole.CODE, required=True),
            _slot("annotation", ElementRole.BODY),
        ],
        constraints=ContentConstraints(maxCharsPerSlide=600),
    ),
    "summary-bullets": LayoutRecipe(
        id="summary-bullets", name="总结要点 Summary", category="closing",
        description="Title + key takeaways as bullets, optional footer banner.",
        slots=[
            _slot("title", ElementRole.TITLE, required=True),
            _slot("bullets", ElementRole.BULLET, repeatable=True, max_count=7),
            _slot("footer", ElementRole.FOOTER),
        ],
        constraints=ContentConstraints(maxListItems=7),
    ),
}

DEFAULT_LAYOUT_ID = "summary-bullets"
LAYOUT_IDS = list(BUILTIN_LAYOUTS.keys())
