import type { Conversation, Model, ContextProfile, FileNode, FileChange, WorkspaceDiff } from '@/types';

export const mockModels: Model[] = [
  {
    id: 'deepseek-v4-pro',
    name: 'DeepSeek V4-Pro',
    provider: 'deepseek',
    description: 'DeepSeek 最新旗舰模型，擅长编程和复杂推理',
    maxTokens: 8192,
    contextWindow: 256000,
    tags: ['推荐', '编程'],
  },
  {
    id: 'kimi-k2.6',
    name: 'Kimi K2.6',
    provider: 'moonshot',
    description: 'Moonshot 长上下文模型，支持 200K 上下文',
    maxTokens: 4096,
    contextWindow: 256000,
    tags: ['长文本'],
  },
];

export const mockContextProfile: ContextProfile = {
  id: 'balanced',
  name: 'Balanced',
  tokenBudget: 256000,
  tokenUsed: 28400,
  messageRounds: 12,
  memoryCount: 8,
  fileCount: 5,
  toolCount: 6,
  compressionLevel: 'none',
};

export const contextProfiles: ContextProfile[] = [
  {
    id: 'cheap',
    name: 'Cheap',
    tokenBudget: 256000,
    tokenUsed: 8200,
    messageRounds: 6,
    memoryCount: 4,
    fileCount: 2,
    toolCount: 3,
    compressionLevel: 'none',
  },
  mockContextProfile,
  {
    id: 'max',
    name: 'Max',
    tokenBudget: 256000,
    tokenUsed: 45200,
    messageRounds: 24,
    memoryCount: 16,
    fileCount: 12,
    toolCount: 10,
    compressionLevel: 'none',
  },
];

export const mockFileTree: FileNode[] = [
  {
    id: 'dir-uploads',
    name: 'uploads',
    type: 'folder',
    path: '/uploads',
    children: [
      {
        id: 'f-req',
        name: 'requirements.txt',
        type: 'file',
        path: '/uploads/requirements.txt',
        size: 2048,
        modifiedAt: Date.now() - 86400000,
      },
      {
        id: 'f-spec',
        name: 'design-spec.pdf',
        type: 'file',
        path: '/uploads/design-spec.pdf',
        size: 1548576,
        modifiedAt: Date.now() - 172800000,
      },
      {
        id: 'f-data',
        name: 'data.csv',
        type: 'file',
        path: '/uploads/data.csv',
        size: 102400,
        modifiedAt: Date.now() - 259200000,
      },
    ],
  },
  {
    id: 'dir-outputs',
    name: 'outputs',
    type: 'folder',
    path: '/outputs',
    children: [
      {
        id: 'f-report',
        name: 'analysis-report.md',
        type: 'file',
        path: '/outputs/analysis-report.md',
        size: 5120,
        modifiedAt: Date.now() - 3600000,
      },
      {
        id: 'f-codegen',
        name: 'generated-code.tsx',
        type: 'file',
        path: '/outputs/generated-code.tsx',
        size: 8192,
        modifiedAt: Date.now() - 7200000,
      },
    ],
  },
  {
    id: 'dir-cache',
    name: 'cache',
    type: 'folder',
    path: '/cache',
    children: [
      {
        id: 'f-embed',
        name: 'embeddings.json',
        type: 'file',
        path: '/cache/embeddings.json',
        size: 5242880,
        modifiedAt: Date.now() - 1800000,
      },
    ],
  },
  {
    id: 'dir-docs',
    name: 'docs',
    type: 'folder',
    path: '/docs',
    children: [
      {
        id: 'f-readme',
        name: 'README.md',
        type: 'file',
        path: '/docs/README.md',
        size: 3072,
        modifiedAt: Date.now() - 432000000,
      },
      {
        id: 'f-api',
        name: 'api-reference.md',
        type: 'file',
        path: '/docs/api-reference.md',
        size: 12288,
        modifiedAt: Date.now() - 400000000,
      },
    ],
  },
];

export const mockWorkspaceDiffs: WorkspaceDiff[] = [
  {
    id: 'diff-1',
    title: '本轮文件变更',
    timestamp: Date.now() - 120000,
    changes: [
      {
        id: 'chg-1',
        path: '/outputs/generated-code.tsx',
        type: 'added',
        preview: 'export const Header = () => { ... }',
        diff: '+ export const Header = () => {\n+   return <header>...</header>;\n+ };',
      },
      {
        id: 'chg-2',
        path: '/outputs/utils.ts',
        type: 'modified',
        preview: 'export const formatDate = ...',
        diff: '~ export const formatDate = (d: string) => {\n~   return new Date(d).toISOString();\n~ };',
      },
      {
        id: 'chg-3',
        path: '/cache/temp.log',
        type: 'deleted',
        preview: '[DEBUG] 临时日志文件',
        diff: '- [DEBUG] 临时日志文件\n- [INFO] Processing...',
      },
    ],
  },
];

export const suggestionQuestions = [
  '如何设计一个可复用的 Modal 组件？',
  '优化 React 应用性能的最佳实践有哪些？',
  '帮我写一个 Python 爬虫脚本',
  '解释 useEffect 的工作原理',
  '如何实现前端文件上传功能？',
];

const conv1Messages = [
  {
    id: 'msg-1',
    role: 'user' as const,
    content: '帮我设计一个 Agent 工作台的界面，需要包含侧边栏、消息流、工具调用展示等功能。用什么技术栈比较好？',
    type: 'text' as const,
    timestamp: Date.now() - 7200000,
    status: 'complete' as const,
  },
  {
    id: 'msg-2',
    role: 'assistant' as const,
    content: '我来帮你设计这个 Agent 工作台界面。基于你的需求，我推荐使用以下技术栈：\n\n## 技术栈推荐\n\n| 技术 | 版本 | 用途 |\n|------|------|------|\n| React | 19 | UI 框架 |\n| TypeScript | 5.7 | 类型安全 |\n| Tailwind CSS | 3.4 | 样式方案 |\n| Zustand | 5.0 | 状态管理 |\n| Vite | 6.0 | 构建工具 |\n\n### 核心功能模块\n\n1. **侧边栏 (Sidebar)**\n   - 可拖拽调整宽度\n   - 会话列表 + 文件树\n   - 搜索功能\n\n2. **消息流 (MessageStream)**\n   - 自动滚动跟随\n   - 空状态提示\n   - 建议问题卡片\n\n3. **工具卡片 (ToolCard)**\n   - [x] 展示工具调用状态\n   - [ ] 参数和结果展开\n   - [x] 执行耗时显示\n\n> 💡 **建议**：深色主题更适合开发者工具，使用 `#0d0d0d` 作为背景色可以营造沉浸式体验。',
    thinkingContent: '用户需要一个 Agent 工作台界面的设计方案。\n\n首先分析需求：\n1. 侧边栏 - 需要拖拽、会话列表、文件树\n2. 消息流 - 类似 ChatGPT 的对话界面\n3. 工具调用展示 - 需要状态管理\n\n技术栈选择考虑：\n- React 19 是最新的版本，性能好\n- Tailwind CSS 适合快速开发\n- Zustand 比 Redux 轻量\n\n我应该给出一个完整的方案，包括组件划分和数据结构设计。',
    type: 'text' as const,
    timestamp: Date.now() - 7100000,
    status: 'complete' as const,
  },
  {
    id: 'msg-2b',
    role: 'assistant' as const,
    content: '',
    type: 'tool_call' as const,
    timestamp: Date.now() - 7095000,
    status: 'complete' as const,
    toolCalls: [
      {
        id: 'tool-1',
        name: 'web_search',
        arguments: { query: 'React 19 Agent Workbench UI design pattern' },
        result: { hits: 5, results: ['React 19 patterns for dev tools', 'Building AI workbench UI'] },
        status: 'success' as const,
        duration: 3420,
        startTime: Date.now() - 7095000,
      },
      {
        id: 'tool-2',
        name: 'read_file',
        arguments: { path: '/workspace/package.json' },
        result: { content: '{ "dependencies": { "react": "^19.0.0" } }' },
        status: 'success' as const,
        duration: 180,
        startTime: Date.now() - 7090000,
      },
      {
        id: 'tool-3',
        name: 'edit_file',
        arguments: { path: '/workspace/src/App.tsx', content: 'import { MainLayout }...' },
        status: 'running' as const,
        duration: undefined,
        startTime: Date.now() - 3000,
      },
    ],
  },
];

const conv2Messages = [
  {
    id: 'msg-3',
    role: 'user' as const,
    content: '我们的 API 响应时间太慢了，P95 达到了 2.5s，有什么优化方案？',
    type: 'text' as const,
    timestamp: Date.now() - 170000000,
    status: 'complete' as const,
  },
  {
    id: 'msg-4',
    role: 'assistant' as const,
    content: 'P95 达到 2.5s 确实需要优化。让我先分析可能的原因，然后给出方案。',
    thinkingContent: 'API 延迟问题分析：\n\n1. 可能的原因：\n   - 数据库查询慢（缺少索引、N+1查询）\n   - 缺少缓存层\n   - 同步调用外部服务\n   - 序列化开销大\n\n2. 优化方向：\n   - 数据库优化（索引、连接池）\n   - 引入 Redis 缓存\n   - 异步处理\n   - 分页和限流',
    type: 'text' as const,
    timestamp: Date.now() - 169900000,
    status: 'complete' as const,
  },
  {
    id: 'msg-5',
    role: 'assistant' as const,
    content: 'API 性能优化可以从多个层面入手：\n\n### 1. 数据库层面\n- 添加合适的索引\n- 使用连接池\n- 查询优化，避免 N+1\n\n### 2. 缓存策略\n```python\nimport redis\n\ncache = redis.Redis(host="localhost", port=6379)\n\ndef get_data(key):\n    cached = cache.get(key)\n    if cached:\n        return json.loads(cached)\n    data = db.query(key)\n    cache.setex(key, 300, json.dumps(data))\n    return data\n```\n\n### 3. 架构优化\n- 异步处理非关键路径\n- 数据库读写分离\n- 水平扩展服务实例\n\n### 4. 代码层面\n- ~~减少不必要的序列化~~\n- 使用更高效的数据结构',
    type: 'text' as const,
    timestamp: Date.now() - 169800000,
    status: 'complete' as const,
  },
  {
    id: 'msg-6',
    role: 'user' as const,
    content: '缓存方案看起来很棒！但是担心缓存一致性问题，有什么好的实践吗？',
    type: 'text' as const,
    timestamp: Date.now() - 169700000,
    status: 'complete' as const,
  },
  {
    id: 'msg-7',
    role: 'assistant' as const,
    content: '缓存一致性确实是关键问题！推荐采用 **Cache-Aside + 过期时间** 的组合策略：\n\n1. **读取时**：先查缓存，未命中再查数据库\n2. **写入时**：先更新数据库，再删除缓存\n3. **设置合理的 TTL** 避免脏数据长期存在\n\n对于要求强一致的场景，可以使用 ***Write-Through*** 模式，即写入时同步更新缓存和数据库。\n\n---\n\n> ⚠️ 注意：避免使用 ***Cache-First*** 策略处理金融数据等敏感场景。',
    type: 'text' as const,
    timestamp: Date.now() - 169600000,
    status: 'complete' as const,
  },
];

export const mockConversations: Conversation[] = [
  {
    id: 'conv-1',
    title: 'Agent 工作台界面设计',
    model: 'deepseek-v4-pro',
    createdAt: Date.now() - 86400000,
    updatedAt: Date.now() - 7100000,
    messageCount: conv1Messages.length,
    messages: conv1Messages,
  },
  {
    id: 'conv-2',
    title: 'API 性能优化方案',
    model: 'kimi-k2.6',
    createdAt: Date.now() - 172800000,
    updatedAt: Date.now() - 169600000,
    messageCount: conv2Messages.length,
    messages: conv2Messages,
  },
  {
    id: 'conv-3',
    title: 'React 组件库重构',
    model: 'deepseek-v4-pro',
    createdAt: Date.now() - 259200000,
    updatedAt: Date.now() - 230000000,
    messageCount: 6,
    messages: [],
  },
  {
    id: 'conv-4',
    title: '数据库迁移计划',
    model: 'kimi-k2.6',
    createdAt: Date.now() - 345600000,
    updatedAt: Date.now() - 300000000,
    messageCount: 4,
    messages: [],
  },
  {
    id: 'conv-5',
    title: '前端状态管理方案对比',
    model: 'deepseek-v4-pro',
    createdAt: Date.now() - 432000000,
    updatedAt: Date.now() - 400000000,
    messageCount: 15,
    messages: [],
  },
  {
    id: 'conv-6',
    title: 'Python 异步编程指南',
    model: 'kimi-k2.6',
    createdAt: Date.now() - 518400000,
    updatedAt: Date.now() - 500000000,
    messageCount: 9,
    messages: [],
  },
];
