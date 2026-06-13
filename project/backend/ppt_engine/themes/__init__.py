"""Built-in theme library for the PPT engine.

Each theme is a complete, self-consistent design system: colour tokens,
font stack, spacing, typography and content constraints. The agent only
references a theme by id; it never picks raw colours or fonts.
"""
from __future__ import annotations

from ..schema import (
    ContentConstraints,
    FontStack,
    Theme,
    ThemeTokens,
    TypographyRules,
)

_CN = '"Noto Sans SC", "PingFang SC", "Microsoft YaHei"'
_INTER = '"Inter", "SF Pro Display", "Helvetica Neue"'
_SERIF = '"Source Han Serif SC", "Songti SC", "Georgia"'
_CODE = '"JetBrains Mono", "Fira Code", "Consolas"'


def _theme(**kw) -> Theme:
    return Theme(**kw)


TECH_DARK = _theme(
    theme_id="tech-dark",
    name="科技黑 Tech Dark",
    family="base",
    mode="dark",
    description="Deep navy background with electric accents — technical architecture & product demos.",
    tokens=ThemeTokens(
        background="#0A0E1A", surface="#141B2D", surfaceElevated="#1E2640",
        primary="#3B82F6", accent="#22D3EE", accentSecondary="#A78BFA",
        text="#F1F5F9", textMuted="#94A3B8", textInverse="#0F172A",
        border="#334155", borderSubtle="#1E293B",
        warning="#F59E0B", success="#10B981", error="#EF4444",
        chart=["#3B82F6", "#22D3EE", "#A78BFA", "#F472B6", "#34D399", "#FBBF24"],
    ),
    fonts=FontStack(headingChinese=_CN, headingEnglish=_INTER, bodyChinese=_CN,
                    bodyEnglish=_INTER, code=_CODE),
)

ACADEMIC_WHITE = _theme(
    theme_id="academic-white",
    name="学术白 Academic White",
    family="base",
    mode="light",
    description="Clean white with deep blue headings — academic defenses & formal reports.",
    tokens=ThemeTokens(
        background="#FFFFFF", surface="#F4F6FA", surfaceElevated="#EAEEF6",
        primary="#1A365D", accent="#9B2C2C", accentSecondary="#2C5282",
        text="#1A202C", textMuted="#5A667A", textInverse="#FFFFFF",
        border="#CBD5E0", borderSubtle="#E2E8F0",
        warning="#B7791F", success="#276749", error="#9B2C2C",
        chart=["#1A365D", "#2C5282", "#9B2C2C", "#2F855A", "#6B46C1", "#B7791F"],
    ),
    fonts=FontStack(headingChinese=_SERIF, headingEnglish='"Georgia", "Times New Roman"',
                    bodyChinese=_CN, bodyEnglish=_INTER, code=_CODE),
    typography=TypographyRules(titleSize=32, subtitleSize=20, bodySize=18, captionSize=14,
                               minBodySize=14, minTitleSize=24, maxTitleSize=40, headingBold=True),
)

BUSINESS_BLUEGRAY = _theme(
    theme_id="business-bluegray",
    name="商业蓝灰 Business Blue-Gray",
    family="base",
    mode="light",
    description="Professional blue-gray — pitch decks, business reviews, strategy.",
    tokens=ThemeTokens(
        background="#F7F9FC", surface="#FFFFFF", surfaceElevated="#EEF2F8",
        primary="#1E3A5F", accent="#C9A227", accentSecondary="#4A6FA5",
        text="#1A2433", textMuted="#5B6B82", textInverse="#FFFFFF",
        border="#D2DAE6", borderSubtle="#E6EBF2",
        warning="#C05621", success="#2F855A", error="#C53030",
        chart=["#1E3A5F", "#4A6FA5", "#C9A227", "#2F855A", "#805AD5", "#DD6B20"],
    ),
    fonts=FontStack(headingChinese=_CN, headingEnglish=_INTER, bodyChinese=_CN,
                    bodyEnglish=_INTER, code=_CODE),
)

VONISH_AGENT = _theme(
    theme_id="vonish-agent",
    name="VonishAgent 品牌",
    family="brand",
    mode="dark",
    description="VonishAgent brand — indigo + cyan on deep space navy.",
    tokens=ThemeTokens(
        background="#0A0E1A", surface="#141B2D", surfaceElevated="#1E2640",
        primary="#6366F1", accent="#22D3EE", accentSecondary="#A78BFA",
        text="#F1F5F9", textMuted="#94A3B8", textInverse="#0F172A",
        border="#334155", borderSubtle="#1E293B",
        warning="#F59E0B", success="#10B981", error="#EF4444",
        chart=["#6366F1", "#22D3EE", "#A78BFA", "#F472B6", "#34D399", "#FBBF24"],
    ),
    fonts=FontStack(headingChinese=_CN, headingEnglish=_INTER, bodyChinese=_CN,
                    bodyEnglish=_INTER, code=_CODE),
)

VONISH_OCR = _theme(
    theme_id="vonish-ocr",
    name="VonishOCR 品牌",
    family="brand",
    mode="dark",
    description="VonishOCR brand — teal + amber on charcoal.",
    tokens=ThemeTokens(
        background="#0B1014", surface="#12191F", surfaceElevated="#1B252D",
        primary="#14B8A6", accent="#F59E0B", accentSecondary="#38BDF8",
        text="#ECFEFF", textMuted="#8CA3AD", textInverse="#06121A",
        border="#27343D", borderSubtle="#1A242B",
        warning="#FBBF24", success="#34D399", error="#F87171",
        chart=["#14B8A6", "#F59E0B", "#38BDF8", "#A3E635", "#FB7185", "#C084FC"],
    ),
    fonts=FontStack(headingChinese=_CN, headingEnglish=_INTER, bodyChinese=_CN,
                    bodyEnglish=_INTER, code=_CODE),
)


BUILTIN_THEMES: dict[str, Theme] = {
    t.theme_id: t
    for t in (TECH_DARK, ACADEMIC_WHITE, BUSINESS_BLUEGRAY, VONISH_AGENT, VONISH_OCR)
}

DEFAULT_THEME_ID = "tech-dark"
