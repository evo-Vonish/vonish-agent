# 🐋 hollow-search-core

**VonishAgent 的高性能研究型 Web 工具核心**

> mini-searxng 负责跑得快，HOLLOW 负责洗得净、排得准、吐得像证据。

## 架构

```
用户向 Agent 提问
  → Intent Router (6种搜索模式)
  → 5引擎并行搜索 (Brave/Bing/DDG/Wiki/Google)
  → 广告/SEO过滤 + 域名权威评分 + 追踪参数清理
  → 补充搜索 (Wikipedia API / GitHub API / ArXiv XML)
  → Ultra Crawler 并发爬取 (500并发/Race调度/Piscina Worker)
  → content-purifier 双阶段净化 (6信号保护/CJK适配)
  → Evidence Pack (分块/评分/去重/MMR精选/声明提取)
  → Agent 拿到能直接引用的研究材料
```

## 目录结构

```
src/
├── engines/          # 5引擎原生 TypeScript 搜索
├── search/           # 并行调度 + HOLLOW 搜索增强
│   ├── orchestrator.ts   # 多引擎并行搜索
│   ├── merger.ts         # 结果去重合并
│   ├── intent-router.ts  # 6种搜索意图模式
│   ├── result-ranker.ts  # 权威评分/广告/SEO过滤
│   ├── supplement.ts     # Wikipedia/GitHub/ArXiv补充
│   └── url-normalizer.ts # 追踪参数清理
├── crawler/          # Ultra 高并发爬虫
│   └── ultra/        # 连接池/流式截断/Worker池
├── purifier/         # HOLLOW 双阶段内容净化
│   ├── phase1/       # 噪声检测+移除
│   ├── phase2/       # Readability+残留清理+CJK适配
│   └── rules/        # 域名规则引擎
├── evidence/         # 证据包 (分块/评分/去重/精选)
├── api/              # Fastify HTTP 服务器
├── agent-tools/      # Agent 工具接口
│   ├── web_search.ts     # 多引擎搜索
│   ├── web_fetch.ts      # 抓取+净化
│   └── deep_research.ts  # 完整研究管道
├── types/            # API 类型定义
└── utils/            # HTTP客户端/日志/URL工具
```

## 启动

```bash
npm install
npm run build
npm start
# → http://127.0.0.1:3000
```

## API 端点

| 端点 | 方法 | 说明 |
|------|------|------|
| `/health` | GET | 健康检查 |
| `/api/search` | POST | 多引擎搜索 + 质量增强 |
| `/api/fetch` | POST | 爬取 + 净化指定URL |
| `/api/research` | POST | 完整管道: search→crawl→purify→evidence |
| `/api/evidence` | POST | 构建 Evidence Pack |

## Agent 工具

```ts
import { web_search } from './src/agent-tools/web_search.js';
import { web_fetch } from './src/agent-tools/web_fetch.js';
import { deep_research } from './src/agent-tools/deep_research.js';

// 普通搜索
const results = await web_search({ query: "Next.js 14 features" });

// 抓取网页
const pages = await web_fetch({ urls: ["https://nextjs.org/docs"], purify: true });

// 深度研究
const report = await deep_research({
  query: "RAG architecture comparison 2024",
  mode: "deep_dive",
});
```

## 搜索模式

| 模式 | 场景 | 引擎数 | 特征 |
|------|------|--------|------|
| `overview` | 通用搜索 | 3 | 快速平衡 |
| `scholar` | 学术搜索 | 3 | 偏好论文/edu/ArXiv |
| `dev` | 开发搜索 | 3 | 偏好GitHub/官方文档 |
| `live` | 实时新闻 | 2 | 偏好新鲜度 |
| `media` | 媒体搜索 | 3 | 保留媒体元数据 |
| `deep_dive` | 深度研究 | 5 | 全引擎+补充搜索+Evidence |

## 爬虫预设

| 预设 | 并发数 | 适用场景 |
|------|--------|----------|
| `fast` | 20 | 快速预览 |
| `balanced` | 50 | 默认推荐 |
| `deep` | 100 | 深度爬取 |
| `ultra` | 200 | 大规模研究 |
| `maximum` | 500 | 带宽拉满 |
| `unlimited` | 不限 | 用户显式开启 |

## 净化模式

| 模式 | 置信度阈值 | 适用 |
|------|-----------|------|
| `conservative` | 0.85 | 学术/技术文档 |
| `balanced` | 0.65 | 通用内容 |
| `aggressive` | 0.45 | 高噪声页面 |

## 零外部依赖

- ❌ 不需要 Docker
- ❌ 不需要 SearXNG 实例
- ❌ 不需要 API Key
- ✅ 纯 Node.js + TypeScript

## 许可证

AGPL-3.0
