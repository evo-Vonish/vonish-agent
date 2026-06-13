"""Reusable demo decks for tests and the end-to-end acceptance sample.

``acceptance_deck`` is a 12-slide deck covering every built-in layout. It is
the canonical sample used by the implementation report and the test suite.
"""
from __future__ import annotations

from .schema import (
    CardContent,
    ChartContent,
    ChartSeries,
    CodeContent,
    ColumnContent,
    DeckDesignSpec,
    DiagramContent,
    DiagramNode,
    QuoteContent,
    SlideContent,
    SlideSpec,
    StepContent,
)


def acceptance_slides() -> list[SlideSpec]:
    return [
        SlideSpec(layout_id="cover-center", content=SlideContent(
            title="VonishAgent PPT Artifact Engine",
            subtitle="确定性渲染管线 · Deterministic Deck Pipeline",
            meta="Vonish · 2026-06-14")),
        SlideSpec(layout_id="toc-simple", content=SlideContent(
            title="目录",
            items=[StepContent(title=t) for t in [
                "问题定义", "设计系统", "布局引擎", "渲染器",
                "质量验收", "自动修复", "预览闭环", "下一步"]])),
        SlideSpec(layout_id="chapter-break", content=SlideContent(
            chapter_number="01", title="问题定义",
            body="为什么 AI 生成的 PPT 总是配色随机、文字溢出、版面失序")),
        SlideSpec(layout_id="three-cards", content=SlideContent(
            title="三大核心能力",
            cards=[
                CardContent(title="确定性渲染", body="SlideIR 驱动，主题 token 严格约束配色与字体，杜绝随机美学"),
                CardContent(title="质量验收", body="交付前自动检测文字溢出、元素越界、对比度与主题一致性"),
                CardContent(title="预览闭环", body="每页导出 PNG 预览，进入 Artifact Workbench 可被检视与引用"),
            ])),
        SlideSpec(layout_id="left-right", content=SlideContent(
            title="旧管线 vs 新管线",
            left=ColumnContent(title="旧：iPython 随机摆放", bullets=[
                "随机配色与字体", "文字经常溢出图形框", "Agent 不知道结果长什么样", "无任何质量闸门"]),
            right=ColumnContent(title="新：Artifact Engine", bullets=[
                "主题 token 统一视觉", "布局引擎计算坐标", "渲染前预计算溢出", "交付前自动验收修复"]))),
        SlideSpec(layout_id="process", content=SlideContent(
            title="生成流程",
            items=[
                StepContent(title="DeckDesignSpec", body="主题 + 布局 + 内容"),
                StepContent(title="SlideIR", body="布局引擎计算坐标"),
                StepContent(title="Render", body="python-pptx 原生元素"),
                StepContent(title="Validate", body="规则检测 + 自动修复"),
                StepContent(title="Deliver", body="PPTX + 预览图"),
            ])),
        SlideSpec(layout_id="timeline", content=SlideContent(
            title="演进路线",
            items=[
                StepContent(label="Phase 1", title="止血版管线"),
                StepContent(label="Phase 2", title="元素级解剖"),
                StepContent(label="Phase 3", title="视觉反思闭环"),
            ])),
        SlideSpec(layout_id="architecture", content=SlideContent(
            title="系统架构",
            diagram=DiagramContent(
                nodes=[
                    DiagramNode(id="a", label="Theme Registry", group="design"),
                    DiagramNode(id="b", label="Layout Registry", group="design"),
                    DiagramNode(id="c", label="PPTX Renderer", group="render"),
                    DiagramNode(id="d", label="PPT Validator", group="qa"),
                    DiagramNode(id="e", label="Preview Export", group="render"),
                    DiagramNode(id="f", label="Artifact Workbench", group="ui"),
                ],
                legend=["design 设计系统", "render 渲染", "qa 质量闸门", "ui 工作台"])) ),
        SlideSpec(layout_id="data-chart", content=SlideContent(
            title="交付质量提升",
            chart=ChartContent(type="column", categories=["溢出", "越界", "配色", "一致性"],
                               series=[ChartSeries(name="旧", values=[42, 30, 55, 20]),
                                       ChartSeries(name="新", values=[3, 1, 2, 4])],
                               insight="文字溢出从 42% 降至 3%，配色越界基本消除"))),
        SlideSpec(layout_id="code-block", content=SlideContent(
            title="统一入口",
            code=CodeContent(language="python", code=(
                "result = generate_deck(\n"
                "    title=\"季度复盘\",\n"
                "    theme_id=\"business-bluegray\",\n"
                "    slides=[...],\n"
                "    workspace_dir=ws,\n"
                ")\n"
                "print(result.validation.delivery_grade)"),
                annotation="Agent 只描述内容，引擎负责坐标、配色、字体与验收")) ),
        SlideSpec(layout_id="quote-center", content=SlideContent(
            quote=QuoteContent(text="把空间推理交给确定性引擎，把审美交给设计系统",
                               author="VonishAgent 设计原则"))),
        SlideSpec(layout_id="summary-bullets", content=SlideContent(
            title="总结",
            bullets=["更稳定：布局引擎计算坐标", "更统一：主题 token 约束视觉",
                     "可验收：交付前自动 QA", "可回滚：SlideIR 快照"],
            footer="下一次 PPT 交付必须经过此管线")),
    ]


def acceptance_deck(theme_id: str = "tech-dark") -> DeckDesignSpec:
    return DeckDesignSpec(
        deck_id=f"acceptance-{theme_id}",
        title="VonishAgent PPT Artifact Engine",
        theme_id=theme_id,
        slides=acceptance_slides(),
    )
