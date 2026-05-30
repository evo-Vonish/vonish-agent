# web-search

**高性能 Web 搜索工具** — 为 AI Agent 设计的一站式搜索管道。

## 管线

```
Query → 多引擎并行搜索 → URL 合并去重 → 竞速批量爬取 → 文本提取清洗 → 内容去重评分 → 精选段落返回
```

## 特性

- **多引擎并行搜索** — DuckDuckGo + Wikipedia，无需 API Key
- **竞速批量爬取** — Promise.race 调度，最高 50 并发，TCP 快速失败探测
- **纯本地算法处理** — Jaccard 内容去重、TF-IDF 相关性评分、多样化段落精选
- **单端点 JSON API** — `POST /api/search`，所有参数可配置

## 快速开始

```bash
# 安装依赖
npm install

# 开发模式运行
npm run dev

# 构建 + 生产运行
npm run build
npm start
```

服务默认运行在 `http://0.0.0.0:3003`

## API

### `POST /api/search`

```json
{
  "query": "climate change effects 2025",
  "maxTime": 15000,
  "maxContentLength": 8000,
  "perUrlTimeout": 3000,
  "maxPerUrl": 5000
}
```

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `query` | string | *必填* | 搜索查询词 |
| `maxTime` | number | 15000 | 总时间上限 (ms)，范围 3000-60000 |
| `maxContentLength` | number | 8000 | 返回内容总长度上限 (chars)，范围 500-50000 |
| `perUrlTimeout` | number | 3000 | 单页超时 (ms)，范围 500-15000 |
| `maxPerUrl` | number | 5000 | 单页最大字符数，范围 500-30000 |

### 响应示例

```json
{
  "query": "climate change effects 2025",
  "results": [
    {
      "title": "Effects of climate change - Wikipedia",
      "url": "https://en.wikipedia.org/wiki/Effects_of_climate_change",
      "text": "The effects of climate change are well documented...",
      "score": 0.85,
      "fromEngines": ["wikipedia", "duckduckgo"],
      "domain": "en.wikipedia.org",
      "wordCount": 342
    }
  ],
  "stats": {
    "totalTimeMs": 2847,
    "urlsFound": 17,
    "crawled": 12,
    "crawlFailed": 3,
    "extractFailed": 1,
    "duplicatesRemoved": 2,
    "finalResults": 6,
    "stages": {
      "searchMs": 1203,
      "crawlMs": 1542,
      "processMs": 102
    }
  }
}
```

## 健康检查

```bash
GET /healthz
# → { "status": "ok", "timestamp": "2026-05-30T00:00:00.000Z" }
```

## 技术栈

- **Fastify** — 高性能 HTTP 服务
- **undici** — HTTP/2 连接池
- **cheerio** — 快速 HTML 解析（无 JSDOM 开销）
- **TypeScript** — 全项目强类型
