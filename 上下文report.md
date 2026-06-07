# VonishAgent 上下文压缩与回忆机制研究报告

## 1. 执行摘要

VonishAgent 的定位是一个本地优先的 Agent IDE / Workbench，其核心差异化在于长期运行复杂任务的能力——编程开发、文件读写、深度研究、文档与多媒体生成、浏览器自动化、工具调用、多轮工作流、上下文召回、文件工作台、引用系统以及任务交接与恢复。这类 Agent Runtime 对上下文管理提出了远超普通聊天 UI 的要求。传统的"上下文太长就总结一下前面"的简单粗暴方案，在 Agent 场景下会导致灾难性后果：丢失用户硬约束、遗忘已否定的方案、混淆文件路径与行号、遗漏关键错误日志、破坏可执行的工作现场。

本报告基于对 **MemGPT、Claude Code、Codex CLI、OpenHands、Context-Folding、ACE、True Memory、HiGMem、GAM、HiMem、Parallel Context Compaction、LLMLingua、LongLLMLingua、Focus Agent、AFM、Headroom** 等前沿研究与生产系统的深度调研，提出了一套完整的上下文压缩与回忆工程方案。核心设计理念是：**压缩不是遗忘，而是将混乱的桌面整理成档案柜**。压缩后的上下文必须让 Agent 能够继续执行任务——它需要知道哪些内容是原始上下文、哪些是压缩摘要、哪些有隐藏原文可召回、如何召回、以及什么时候必须召回。

本报告的核心结论包括六个方面。**第一**，不能无脑压缩前部，必须按内容类型、任务相关性、引用频率、约束属性、阶段依赖等多重因素综合判断重要性。**第二**，不同内容类型必须采用差异化压缩策略——用户硬约束应 pin 住不进入压缩池，代码文件应保持"结构 + 关键片段索引"而非自然语言化，工具结果应按类型保留元数据和可召回 ID，Agent 思维链应转化为决策日志而非保留原始推理。**第三**，压缩结果必须保持结构化（YAML/XML 标记），禁止熬成一锅粥式的散文摘要。**第四**，必须配备与压缩联动的 recall 工具族——`CRAZY_for_MAX` 用于最大上下文扩展、`custom_context_recall` 用于精准召回、`context_map` 用于查看可召回索引。**第五**，采用"本地算法预压缩 + AI 语义精压缩 + 本地验证"的 Hybrid 三层架构，在速度、成本、质量之间取得平衡。**第六**，并行无感压缩机制应在主 Agent 继续工作时后台执行，在阶段切换点、上下文容量阈值、高风险动作前自动触发，对用户完全透明。

本报告最终输出包含完整的结构化压缩格式规范、Recall Tool API 设计、System Prompt 工程方案、数据结构设计、质量评估标准、禁止事项清单以及分三阶段的落地路线图。

---

## 2. 问题定义：为什么普通摘要远远不够

### 2.1 普通压缩的本质缺陷

传统上下文压缩的核心逻辑是：上下文太长 → 总结前面内容 → 丢掉原文 → 继续对话。这个流程在简单问答场景下可以勉强工作，但在 Agent Runtime 中会导致系统性失效。现有研究明确指出了这一问题的严重性：AMA-Bench 的评测发现，Agent 在许多 benchmark 上的性能下降"不是因为模型原则上无法解决任务，而是因为它失去了继续解决任务所需的信息"[^10^]。换句话说，**信息丢失是 Agent 失败的首要原因，而非模型能力不足**。

普通摘要存在四个根本性缺陷。**信息不可逆丢失**是最致命的问题——一旦原始内容被丢弃，就永远无法恢复。LLM-based summarization 是"inherently lossy"的，上下文被减少了 90-99% 的 token，但模型决定保留什么、丢弃什么时"with no guarantee of consistency across runs"[^1^]。在交互式编码 Agent 中，这种信息丢失尤其具有破坏性：最近的上下文（包含 Agent 刚刚积累的洞察）与旧内容一起被重度压缩，迫使 Agent 在后续轮次中重新发现和重建这些上下文，代价是额外的 token 和时间。

**结构破坏**是第二个核心问题。普通摘要将所有内容混合成一段散文，完全破坏了原始内容的类型边界。代码文件变成了自然语言描述，工具结果的元数据丢失了，错误日志的上下文消失了，用户约束的语气强度被削弱了。研究表明，代码 Agent 的轨迹包含"dense, causally structured state transitions"（密集的、具有因果结构的状态转换），这种结构化信息在自然语言摘要中几乎完全丢失[^10^]。

**无法按需召回**是第三个问题。普通压缩是一个单向过程：原始 → 摘要 → 丢弃。但 Agent Runtime 需要的是一个双向过程：原始 → 压缩索引 → 按需展开。没有 recall 机制的压缩等同于主动遗忘。

**时机错误**是第四个问题。大多数系统只在上下文超过阈值时才触发压缩，此时 Agent 已经处于"喝醉了"的混乱状态——它被迫在信息丢失的情况下继续工作，而不是在清醒状态下重新整理工作现场。

### 2.2 Agent Runtime 的特殊性

VonishAgent 作为一个 Agent IDE / Workbench，其上下文管理面临着多维度挑战。这些挑战源于 Agent 需要同时处理多种类型的内容，每种类型都有不同的保留要求。用户消息可能包含不可违背的硬约束；assistant 消息可能包含已承诺的计划和设计决策；tool_call 需要结构化保留以避免重复执行；tool_result 需要根据工具类型差异化处理——web_search 需要保留来源和证据、code_file_read 需要保留结构和关键片段、shell_output 需要保留错误和退出码、browser_snapshot 需要保留关键可见元素。Agent 的思维链（thinking）需要转化为决策日志，而非保留原始推理。系统计划和任务状态需要始终清晰可访问。

这些内容的共同特点是：**它们不是被动的历史记录，而是 Agent 继续执行任务的现场依据**。压缩必须保持这个现场的可执行性。

### 2.3 研究前沿的验证

我们的研究发现了大量支持这一设计方向的证据。Context-Folding 框架通过强化学习（FoldGRPO）训练 Agent 主动管理上下文，将子任务的完整轨迹折叠成简洁摘要，在 BrowseComp-Plus 和 SWE-Bench Verified 上实现了 **90% 以上的上下文压缩率**（107K token 压缩至 6.5K），同时性能匹配甚至超过使用 327K token 上下文的基线[^49^]。ACE（Agentic Context Engineering）提出将上下文视为"evolving playbook"（不断演化的剧本），通过生成-反思-整理循环积累策略，在 AppWorld 上取得了 **+10.6% 的性能提升**[^59^]。True Memory 提出了"Storage Is Not Memory"（存储不等于记忆）的架构理念，将 Agent 记忆重新定义为以检索为中心的六层管道，在 LoCoMo 上达到 **93.0% 的准确率**[^48^]。这些研究共同指向一个结论：**上下文的组织方式和召回机制比上下文的绝对长度更重要**。

---

## 3. 上下文内容分类体系

### 3.1 十二类内容的全景分类

基于对生产级 Agent 系统的深入分析，我们将 VonishAgent 的上下文内容划分为十二个核心类别。这种分类不是随意的，而是基于每类内容的**可压缩性**、**对任务连续性的关键程度**、**结构化程度**以及**丢失后的不可逆性**四个维度建立的。

| 内容类型 | 关键程度 | 可压缩性 | 结构化程度 | 丢失不可逆性 | 核心保留策略 |
|---------|---------|---------|-----------|------------|-------------|
| user_message | **极高** | 低-中 | 中 | **极高** | 硬约束 pin 住，长消息提取关键原句 |
| assistant_message | 中-高 | 中-高 | 中 | 中 | 计划/方案保留结构，普通解释可摘要 |
| agent_thinking | 中 | **极高** | 低 | 低 | 转化为 decision_log/task_state，丢弃原始推理 |
| tool_call | 高 | **极低** | **极高** | 高 | 结构化保留 id/tool/args/status |
| tool_result | **极高** | 因类型而异 | 因类型而异 | **极高** | 按子类型差异化压缩，保留 recall id |
| code_file | **极高** | 中 | **极高** | **极高** | 结构+关键片段索引，禁止自然语言化 |
| search_research | **极高** | 中-高 | 中-高 | 高 | 保留查询词、来源、核心证据段 |
| browser_snapshot | 高 | 中 | 中 | 高 | 保留 URL、关键元素、表单、操作结果 |
| diff_patch | **极高** | 低-中 | **极高** | **极高** | 保留 hunk header、add/remove 行、意图 |
| shell_log | 高 | 中 | 中 | 高 | 保留命令、exit_code、错误、summary |
| artifact_result | 中-高 | 中 | 中 | 中 | 保留路径、类型、验证状态、限制 |
| system_plan | **极高** | 低 | **极高** | **极高** | 尽量完整保留，高优先级预算 |

### 3.2 分类的工程意义

这种分类的直接工程意义在于：**不存在统一的压缩算法适用于所有内容类型**。LLMLingua 系列的 token-level 压缩可以达到 20x 的压缩比[^23^]，但它对所有内容一视同仁地删除"低信息 token"，这会破坏代码结构、丢失工具调用的元数据、混淆错误日志的上下文。研究表明，token-level 压缩方法"lack semantic awareness and disrupt coherence in multi-step reasoning chains"（缺乏语义感知，破坏多步推理链的连贯性）[^1^]。

Headroom 项目的实践证明了内容类型感知压缩的价值：代码搜索结果压缩 **92%**（17,765 → 1,408 tokens），SRE 事件调试日志压缩 **92%**（65,694 → 5,118 tokens），但代码库探索只压缩 **47%**（78,502 → 41,254 tokens）——因为代码行携带的独特信号更多[^38^]。这验证了我们的核心观点：**压缩率应该由内容类型决定，而不是由统一阈值决定**。

---

## 4. 不同内容类型的压缩策略

### 4.1 user_message：用户消息的至高优先级处理

用户消息在 Agent Runtime 中具有最高的优先级，因为用户是任务的最终权威来源。压缩用户消息时必须遵循三个核心原则。

**硬约束的 pin 机制**。用户的明确禁止、强烈偏好、纠错、命名约定、路径要求、技术栈锁定等属于"不可压缩"内容。这些内容必须以 `pinned_constraint` 的形式独立存在，不进入普通压缩池。研究表明，即使是非常小的约束标记丢失也会导致 Agent 行为偏离——AFM（Adaptive Fidelity Management）通过为消息分配保真度层级（Full/Compressed/Placeholder），在约束召回上达到了 **83.3% 的准确率**，证明了结构化保真度管理优于朴素截断[^67^]。用户的硬约束包括："一次性干完！DON'T ASK ME ANYTHING!"、"不要用假数据"、"必须用 TypeScript"、"端口必须是 3000"、"不要改这个文件"等。这些约束的丢失往往意味着 Agent 走上错误道路的开始。

**短消息原文保留**。短用户消息（<100 tokens）应尽量原文保留，因为重写可能改变语气和强度。用户说"不对，我要的是 X 不是 Y"如果被压缩成"用户澄清了需求"，Agent 就失去了对错误的具体理解。

**长消息结构化提取**。长用户消息（>200 tokens）应进行结构化提取，保留关键原句和明确的指令列表，而非重写为第三人称描述。原始消息中的引用、代码片段、路径列表、编号要求都必须保留原始形式。

### 4.2 assistant_message：助手回复的选择性压缩

Assistant 消息的压缩空间比用户消息大，但仍需保留关键内容。**已承诺的计划和任务书**必须保留结构化大纲——如果 Agent 之前向用户承诺了"三步计划：1.搜索 2.设计 3.实现"，这个计划必须可在压缩后恢复。**已做的设计决策**需要保留，尤其是用户已经确认或锁定的决策。**错误承认和修正**需要保留，因为 Agent 需要记住自己之前犯过什么错、如何修正的，以避免重复犯错。**普通解释性内容**可以大胆摘要，因为这类内容通常不包含可执行信息。

ACE 框架的研究提供了一个重要洞察：将 Agent 上下文视为"evolving playbook"（不断演化的剧本）而非被动历史记录，可以显著提升性能[^59^]。这意味着 assistant 消息不应被压缩成"之前做了什么"的散文，而应被整理成"当前已知什么、已决定什么、下一步该做什么"的结构化剧本条目。

### 4.3 agent_thinking：思维链的转化而非保留

Agent 思维链（thinking / reasoning trace）是一个特殊类别。研究明确表明，**不应将原始思维链长期塞回上下文**[^15^]。原始思维链通常包含大量中间推理、错误假设、已废弃的思路、重复尝试——这些信息对继续任务几乎没有价值，反而会混淆 Agent 的注意力。

正确的处理方式是将思维链**转化为可执行的工作记忆**。Focus Agent 提出了"从被动保留到主动压缩"的范式转变：Agent 主动内省，将近期轨迹总结为高层次的"学习"，然后物理删除原始日志[^8^]。这种转化产出应包括：当前任务状态（task_state）、决策日志（decision_log）、已知假设（assumptions）、下一步动作（next_actions）、风险备注（risk_notes）、未解决问题（unresolved_questions）。

LightThinker 的研究为此提供了技术支撑：通过将思维链的动态中间状态压缩为少量 gist token，可以减少 **70% 的峰值 token 使用量**和 **26% 的推理时间**[^71^]。这为 VonishAgent 的 thinking 压缩提供了量化目标。

### 4.4 tool_call：结构化元数据保留

Tool call 本身通常较短，但其结构化元数据对 Agent 自我认知至关重要。每个 tool_call 应保留为结构化记录，核心字段包括：唯一标识符（id）、工具名称（tool）、参数摘要（args_summary）、执行状态（status）、关联结果 ID（result_id）。这种结构化保留使 Agent 能够：知道自己已经执行过什么操作、避免重复执行相同的工具调用、通过 result_id 召回对应的 tool_result。

OpenHands 的 condenser 架构提供了一个关键设计原则：condensation 在"视图层"操作——插入 CondensationAction 标记而非删除事件——这意味着原始事件流永远不会被修改，支持 session replay[^14^]。这种"标记而非删除"的原则应被 VonishAgent 的 tool_call 压缩所采用。

### 4.5 tool_result：最重要的差异化压缩

Tool_result 是上下文压缩中最复杂也最重要的部分。不能采用统一的压缩策略，必须按子类型差异化处理。

**web_search / research_result**。必须保留：查询词（用户需要知道搜过什么）、来源标题和 URL（用于引用和验证）、时间戳（判断信息新鲜度）、核心证据段（支撑结论的事实）、互相冲突的信息（Agent 需要知道证据分歧）、可信度提示、被排除的来源列表。不能压缩成"搜索到一些资料"这种无用的描述。True Memory 的研究强调了 verbatim event preservation（逐字事件保留）的重要性：任何在摄取时丢弃的内容在查询时都无法恢复[^48^]。对于搜索结果，这意味着原始搜索结果页面必须通过 recall id 可恢复。

**code_file_read_result**。代码文件压缩应以"结构 + 原文片段索引"为核心策略。必须保留：文件路径、语言、导入/导出列表、类型定义、类/函数名称列表、与当前任务相关的函数签名、TODO/FIXME 标记、错误附近的行、重要代码片段的原文和行号范围。Sermble 项目（一个 AI-agent-native 代码搜索工具）的实践表明，token 效率可以通过分层输出来实现：`--outline` 模式（每块一个签名行）比完整输出减少 **47%** 的 token，`--compact` 模式保留所有匹配行，而 `--json --strip` 只在需要时才提供完整代码块[^76^]。这为 VonishAgent 的代码压缩提供了分层策略的参考。

**grep_result**。保留：查询词、匹配文件列表、匹配行及其上下文行、匹配计数。对于匹配密集的文件应特别标注。

**shell_output**。保留：执行的命令、工作目录、exit code、错误信息和 warning、test summary（通过了多少/失败了多少）、build summary、安装结果。长日志应采用"错误优先压缩"——保留头部（命令和初始输出）、保留尾部（最终结果和错误）、中间部分压缩为统计摘要。

**diff / patch**。Diff 是 Agent 代码修改的核心证据，不能被普通摘要吞掉。必须保留：文件路径、hunk header（@@ 行号范围 @@）、added/removed 行的实际内容、修改意图说明、应用状态（是否已应用）、后续验证状态。

**browser_snapshot**。保留：URL、页面标题、关键可见元素（表单、按钮、链接）、当前焦点、错误 banner、最近的操作结果。浏览器快照的结构化程度使其适合转化为"页面状态摘要"而非保留完整 HTML。

### 4.6 压缩策略的分层设计

综合以上分析，我们提出 VonishAgent 的压缩策略分层设计：

| 层级 | 内容 | 压缩方式 | 保留形式 |
|-----|------|---------|---------|
| L0-Pinned | 用户硬约束、当前任务目标、活跃文件 | **不压缩** | 原文，独立预算池 |
| L1-Structure | 代码结构、工具调用记录、决策日志 | 本地算法提取 | 结构化元数据 |
| L2-Segments | 关键代码片段、错误日志、证据段 | 头尾+关键段保留 | 原文片段+recall id |
| L3-Summary | 普通解释、历史聊天、已完成的子任务 | AI 语义摘要 | 结构化摘要+recall id |
| L4-Archive | 过期内容、无关闲聊、已验证的旧结果 | 本地压缩+AI精压缩 | 压缩摘要+recall id |

---

## 5. 结构化压缩格式设计

### 5.1 格式设计的核心原则

基于对 Claude Code 五层 graduated compaction 管道[^34^]、OpenCode 的两阶段外科式策略[^14^]、以及 ACE 的 evolving playbook 理念的深入分析，我们提出 VonishAgent 的压缩格式必须满足三个条件：**机器可读**（模型能准确理解哪些内容是压缩的、哪些可以召回）、**人类可审**（开发者和用户能检查压缩质量）、**可执行**（Agent 看到压缩上下文后能继续工作而非迷失方向）。

禁止将所有历史压缩成一大段散文。这种压缩方式会严重降低 Agent 性能，因为模型无法区分"用户原始需求"和"系统压缩摘要"，也无法知道哪些内容可以展开。研究表明，模型看到压缩上下文时"cannot judge whether a memory is truly worth reading as it lacks a mechanism for reasoning over different levels of abstraction"（无法判断一段记忆是否真正值得阅读，因为缺乏跨抽象层次推理的机制）[^2^]。结构化格式正是为了解决这个问题。

### 5.2 推荐压缩格式：VCCS（VonishAgent Compacted Context Structure）

我们设计了一套基于 XML 标记的压缩格式，命名为 VCCS。选择 XML 标记而非纯 YAML/JSON 的原因是：LLM 对明确的标记边界（`<tag>...</tag>`）有更强的识别能力，且 XML 标记在 prompt 中的语义边界更清晰。

```xml
<context_compaction_notice>
这是经过压缩的上下文快照。部分原始内容已折叠，但可通过 recall 工具展开。
折叠内容带有 [recall:xxx] 标记——当你需要精确原文时，请使用 recall 工具。
切勿假装已阅读过折叠内容，也不要根据摘要编造原文细节。
</context_compaction_notice>

<task_state>
  <goal>设计 VonishAgent 的上下文压缩与回忆引擎</goal>
  <current_phase>研究报告撰写</current_phase>
  <completed_steps>
    - 完成前沿研究调研（MemGPT/Claude Code/Context-Folding/ACE 等）
    - 完成内容分类体系设计
    - 完成差异化压缩策略设计
  </completed_steps>
  <pending_steps>
    - 并行无感压缩架构设计
    - System Prompt 工程方案
    - 数据结构与 Tool API 设计
  </pending_steps>
  <blockers>无</blockers>
</task_state>

<user_constraints pinned="true">
  <constraint intensity="hard" source="user_message_003">
    "一次性干完！DON'T ASK ME ANYTHING!"
  </constraint>
  <constraint intensity="hard" source="user_message_007">
    不要无脑 head/tail 压缩——必须按内容类型和重要性压缩
  </constraint>
  <constraint intensity="hard" source="user_message_012">
    压缩不是遗忘，而是重建工作现场
  </constraint>
  <constraint intensity="soft" source="user_message_015">
    优先输出工程方案，理论部分精简
  </constraint>
</user_constraints>

<decision_log>
  <decision id="d_001" timestamp="2026-06-07T10:23:00Z">
    <choice>采用 Hybrid 三层压缩架构（本地预压缩 + AI 精压缩 + 本地验证）</choice>
    <rationale>平衡速度、成本和质量</rationale>
    <status>locked</status>
  </decision>
  <decision id="d_002" timestamp="2026-06-07T11:45:00Z">
    <choice>结构化压缩格式采用 XML 标记而非纯散文</choice>
    <rationale>LLM 对标记边界识别更清晰，支持多级抽象</rationale>
    <status>locked</status>
  </decision>
</decision_log>

<file_index>
  <file path="src/stores/workbenchStore.ts" lang="typescript"
        recall_id="tr_file_read_023" recall_type="file_range">
    <summary>管理 workbench tabs、dirty state、save/open/close 行为</summary>
    <structure>
      - type WorkbenchTab = { id, path, dirty, content }
      - openFile(path: string): void
      - saveTab(tabId: string): Promise&lt;void&gt;
      - closeTab(tabId: string): void
    </structure>
    <important_segments>
      <segment lines="24-66" recall="ex_file_range(src/stores/workbenchStore.ts,24,66)">
        Tab state type definitions
      </segment>
      <segment lines="101-148" recall="ex_file_range(src/stores/workbenchStore.ts,101,148)">
        openFile logic — current task target
      </segment>
    </important_segments>
  </file>
</file_index>

<tool_result_index>
  <tool_result id="tr_search_001" type="web_search" recall="ex_tool_result(tr_search_001)">
    <query>LLM agent context compression parallel background</query>
    <summary>找到 3 篇核心论文：Parallel Context Compaction(2026)、
            Context-Folding(2025)、True Memory(2026)</summary>
    <sources count="3">
      <source title="Parallel Context Compaction for Long-Horizon LLM Agent Serving"
              url="https://arxiv.org/abs/2605.23296" key_evidence="yes"/>
      <source title="Scaling Long-Horizon LLM Agent via Context-Folding"
              url="https://arxiv.org/abs/2510.11967" key_evidence="yes"/>
      <source title="Storage Is Not Memory: A Retrieval-Centered Architecture"
              url="https://arxiv.org/abs/2605.04897" key_evidence="yes"/>
    </sources>
  </tool_result>
  
  <tool_result id="tr_shell_005" type="shell" recall="ex_tool_result(tr_shell_005)">
    <command>npm run test -- --run</command>
    <cwd>/mnt/agents/vonish</cwd>
    <exit_code>1</exit_code>
    <summary>3 tests failed, 47 passed</summary>
    <key_errors>
      - FAIL: src/compression/engine.test.ts - "should preserve line numbers"
      - FAIL: src/recall/tools.test.ts - "custom_context_recall returns full text"
    </key_errors>
    <full_log recall="ex_tool_result(tr_shell_005,full)"/>
  </tool_result>
</tool_result_index>

<conversation_summary>
  <turns_total>32</turns_total>
  <turns_visible>8</turns_visible>
  <turns_compacted>24</turns_compacted>
  
  <recent_turns>
    <!-- 最近 8 轮保留完整原文 -->
  </recent_turns>
  
  <compacted_turns>
    <topic period="turns_1-12" recall="ex_turns(1,12)">
      用户介绍 VonishAgent 项目背景，明确需求：设计上下文压缩+回忆引擎。
      核心要求：压缩不是遗忘、结构化保留、支持 recall tools、并行无感压缩。
    </topic>
    <topic period="turns_13-24" recall="ex_turns(13,24)">
      完成研究调研，确定核心架构方向：Hybrid 三层压缩 + 结构化格式 + Recall 工具族。
      用户确认方向并追问 recall tool 的具体设计。
    </topic>
  </compacted_turns>
</conversation_summary>

<recall_instructions>
当你需要以下类型的精确信息时，请使用对应的 recall 工具：
  1. 代码修改前的原始代码 → custom_context_recall(type="file_range", path=..., startLine=..., endLine=...)
  2. 证据引用或事实验证 → custom_context_recall(type="tool_result", id=...)
  3. 用户之前的具体表述 → custom_context_recall(type="chat_message", id=...)
  4. 大规模上下文扩展 → CRAZY_for_MAX(scope=..., priority=[...])
  5. 查看有哪些可召回内容 → context_map()

必须在以下场景前 recall：
  - 写最终报告或交付文件前
  - 修改代码前
  - 引用研究证据前
  - Debug 复杂错误前
  - 看到 [recall:xxx] 标记且内容可能重要时
</recall_instructions>
```

### 5.3 必须告知模型"这是 compacted"

研究明确支持这一设计选择。当模型不知道上下文已被压缩时，它会"误以为压缩摘要等于完整原文"，从而基于不完整的摘要做出错误决策。Codex CLI 的 `/responses/compact` 端点设计上就返回一个特殊的 `type=compaction` 项，其中包含"opaque encrypted_content that preserves the model's latent understanding of the original conversation"（保留模型对原始对话的潜在理解的加密内容）[^37^]——这种显式的 compact 标记确保模型知道自己在处理压缩内容。

告知模型的表达应该平衡清晰度和干扰度。推荐表达："以下是经过压缩的上下文快照。它保留了任务状态、用户约束、关键证据和可召回索引。部分原始内容已折叠；如需精确内容，请使用 recall 工具展开。"这种表达明确传达了三个关键信息：这是压缩的、保留了关键内容、可以召回。

---

## 6. Recall Memory 机制设计

### 6.1 设计理念：从"被动存储"到"主动召回"

传统记忆系统的问题是"storage-centric"（以存储为中心）——它们专注于如何存储信息，而非如何召回信息。True Memory 的研究提出了一个革命性的观点：**"Extraction at ingestion is the wrong primitive for agent memory: content discarded before the query is known cannot be recovered at retrieval time"（在摄取时提取是 Agent 记忆的错误原语：在查询已知之前丢弃的内容无法在检索时恢复）**[^48^]。VonishAgent 的 recall 机制正是为了解决这个问题而设计。

### 6.2 CRAZY_for_MAX：最大上下文扩展工具

**设计目的**。`CRAZY_for_MAX` 用于需要尽可能多上下文的场景——重大总结、复杂 Debug、大重构、最终验收、研究报告写作等。它的核心行为是"自动展开尽可能多的相关上下文，填满上下文预算"。

**参数设计**。

| 参数 | 类型 | 默认值 | 说明 |
|-----|------|--------|------|
| turns | number | 3 | 召回轮数，每轮结束后提醒剩余轮数 |
| scope | enum | "current_task" | 召回范围：当前任务/全部近期/研究/编码/调试/artifact |
| maxTokens | number | 动态计算 | 最大 token 预算，由上下文窗口决定 |
| priority | string[] | 全部 | 优先级顺序：user_constraints > tool_results > file_reads > diffs > errors > plans > research_evidence > chat_messages |
| includeRaw | boolean | false | 是否包含原始全文（极耗 token） |
| includeKeySegments | boolean | true | 是否包含关键片段 |
| query | string | 可选 | 语义过滤查询词 |
| reason | string | 必填 | 召回原因（Agent 必须说明为什么需要 MAX 模式） |

**行为设计**。CRAZY_for_MAX 的行为遵循以下流程：（1）Agent 调用时需提供 reason，系统验证合理性；（2）激活后进入"扩展上下文模式"，每轮结束提醒剩余轮数；（3）按 priority 顺序展开内容，直到填满 token 预算；（4）不重新执行工具，只展开已存档内容；（5）过期时明确提醒 Agent"MAX 模式已结束，如需继续依赖隐藏证据，请再次调用 recall 工具"；（6）支持显式提前终止。

**状态提示**。激活时："MAX 回忆模式已开启：剩余 3 轮。你正在使用扩展上下文。若最终任务尚未完成，请在过期前继续或重新召回。"过期时："MAX 回忆模式已结束。上下文将回到普通压缩模式。如需继续依赖隐藏证据，请再次调用 recall 工具。"

**改名建议**。虽然 `CRAZY_for_MAX` 这个名字具有强烈的 VonishAgent 品牌个性，但从工程角度考虑，`expand_context_max` 或 `recall_maximum` 可能更清晰地表达功能。我们建议在系统内部使用 `recall_maximum`，在用户可见层保留"MAX 回忆模式"的品牌表达。

### 6.3 custom_context_recall：精准召回工具

**设计目的**。用于精确召回指定内容，支持细粒度的目标选择和模式控制。

**参数设计**。

| 参数 | 类型 | 说明 |
|-----|------|------|
| targets | array | 召回目标列表，每个目标包含 type/id/path/query/startLine/endLine |
| turns | number | 召回持续轮数 |
| maxTokens | number | 单轮最大 token |
| mode | enum | raw / key_segments / summary_plus_segments / structure_only |
| reason | string | 召回原因（必填，培养 Agent 的 recall 意识） |

**支持的目标类型**。`tool_result`（通过 ID 召回工具结果）、`chat_message`（通过 ID 召回对话消息）、`file`（通过路径召回文件）、`file_range`（通过路径+行号范围召回代码段）、`grep`（通过查询词执行代码搜索并召回结果）、`search_result`（召回搜索结果的原始数据）、`browser_snapshot`（召回浏览器快照）、`error_log`（召回错误日志）、`shell_output`（召回命令行输出）、`diff`（召回 diff/patch）、`user_constraint`（召回用户约束原文）、`plan`（召回任务计划原文）、`artifact_validation`（召回验证结果）。

**模式选择**。`raw` 返回原始全文（最精确但最耗 token）；`key_segments` 返回关键片段（平衡选择）；`summary_plus_segments` 返回摘要+关键片段（默认推荐）；`structure_only` 返回结构索引（最低 token 消耗）。

**使用示例**。Agent 在修改 `workbenchStore.ts` 前的典型召回调用：以 reason "Need exact context before editing file workbench logic" 调用 custom_context_recall，targets 包含 `{type: "file_range", path: "src/stores/workbenchStore.ts", startLine: 90, endLine: 160}` 和 `{type: "tool_result", id: "tr_shell_005"}`，mode 为 "summary_plus_segments"。

### 6.4 context_map：记忆地图工具

**设计目的**。让 Agent 在展开前先看"有哪些可召回内容"，避免盲目调用 CRAZY_for_MAX。这类似于地图应用中的"查看周边"功能——先浏览，再决定去哪里。

**返回结构**。

```yaml
available_memory:
  user_constraints:
    total: 12
    pinned: 5
    recent: 7
  tool_results:
    web_search: 4
    read_file: 18
    shell: 9
    diff: 6
    browser_snapshot: 2
  chat_messages:
    total: 32
    visible: 8
    compacted: 24
  pinned_items:
    files: 3
    decisions: 5
    errors: 2
  recall_stats:
    total_recalls_this_session: 7
    most_recalled: ["tr_file_read_023", "tr_search_001"]
```

### 6.5 pin_memory：钉住机制

**设计目的**。允许 Agent（或系统）将特定内容"钉"在上下文中，使其不进入压缩池。这是保证关键信息不丢失的最后一道防线。

**可钉住的内容**。用户硬约束、当前活跃文件、未解决的错误、待验证的假设、用户明确说"记住这个"的内容。

**实现方式**。pinned 内容存储在独立的预算池中，不参与常规压缩流程。当上下文重建时，pinned 内容优先进入上下文，剩余预算才分配给压缩内容和可见轮次。

---

## 7. 并行无感压缩架构

### 7.1 基本架构设计

并行无感压缩的核心思想是：在主 Agent 继续执行的同时，后台启动压缩任务，压缩完成后写入 Memory Store，下一轮上下文构建时使用 compressed view。这一设计直接受到了 **Parallel Context Compaction** 研究的启发——该研究证明并行压缩可以"gives the operator fine-grained, predictable control over summary volume and enables more targeted prompt engineering per block"（给操作者提供细粒度、可预测的摘要量控制，并支持每个块更针对性的 prompt 工程）[^1^]。

VonishAgent 的并行压缩架构包含四个核心组件。

**Compactor Service**。独立的压缩服务，接收待压缩的内容块，执行本地预压缩或调用 AI 进行语义压缩。Compactor 在主 Agent 运行时不阻塞推理流程。

**Memory Store**。集中式存储，保存所有原始内容（raw）和压缩视图（compressed view）。每条内容都有 stable id，支持通过 recall id 精确检索。

**Context Builder**。负责在每轮 Agent 调用前组装上下文。组装优先级：pinned 内容 > 最近 N 轮完整对话 > 压缩后的历史内容 > 召回的内容。

**Background Scheduler**。调度后台压缩任务的触发和执行。

### 7.2 触发时机

并行压缩的触发条件分为四类。

**内容长度触发**。单个 tool_result 超过阈值（如 2000 tokens）时触发。天然长的内容类型包括：web_search 结果、read_file 大文件、shell log、browser snapshot、pdf/doc parse。

**上下文容量触发**。当前上下文超过窗口的 60%/70%/80% 时分级触发。多轮任务超过 N 轮（如 20 轮）时触发。

**阶段切换触发**。这是最重要的触发时机。当 Agent 从研究阶段进入写作阶段、从读文件进入改代码阶段、从编码进入验证阶段时，前一阶段的完整上下文应被压缩为结构化摘要。Context-Folding 的研究证明，子任务完成后的折叠（folding）是实现 90%+ 压缩率的关键时机[^49^]。

**高风险动作前触发**。最终回答前、交付文件前、大规模代码修改前、删除文件前、执行不可逆操作前——这些场景都应触发"任务再明确"压缩（见第 10 节）。

### 7.3 安全替换机制

**不在同一轮替换**。tool_result 产生后，raw 存入 Memory Store，background compaction 开始，当前 Agent turn 仍然可见原始或当前视图。Turn 结束后进入 context rebuild，下一轮才使用 compressed view。这避免了 Agent 当前正在引用某段内容时突然消失的问题。

**双阶段压缩**。如果内容极长，已经无法进入当前上下文，则立即使用"快速本地压缩"（保留头尾+关键词+结构）作为应急视图，同时后台 AI 进行精细压缩。这确保了即使在极端情况下 Agent 也不会看到空白或截断的内容。

**版本追踪**。每条内容维护版本历史：raw → local_compressed → ai_compressed。Recall 工具可以指定展开哪个版本。这支持 Agent 在不同精度需求间切换。

### 7.4 与工具执行的天然并行

Sema Code 的研究揭示了一个重要洞察：当 Agent 等待外部工具执行时（如 pytest、shell 命令、外部 API），GPU/推理资源是空闲的，此时进行压缩"at zero opportunity cost"（零机会成本）[^66^]。VonishAgent 应利用这个天然的并行窗口：当 Agent 调用工具后等待结果时，后台 Compactor 自动处理待压缩队列。

---

## 8. AI 压缩与本地算法压缩的分工

### 8.1 本地算法压缩：速度、稳定、零幻觉

本地算法压缩的优势在于速度快、稳定性高、成本低、不会幻觉。适合执行结构化的、规则明确的压缩任务。

**适合的压缩任务**。Head/tail 提取（保留内容的头部和尾部）、按行切块（将长文本按行分割并标记）、关键词和路径提取（用正则表达式提取 URL、文件路径、函数名等）、代码符号索引（提取 import/export、function/class/typedef 定义）、grep 匹配邻域（保留匹配行及其上下文）、diff hunk 提取（保留 @@ 头部和变更行）、shell exit code 和 error 段落提取、JSON key path 提取、Markdown heading outline 提取、长度统计和 hidden section map 生成。

Semble 项目展示了本地算法在代码搜索中的 token 效率：`--outline` 模式（每块一个签名行）比完整输出减少 **47%** token，`tree` 命令将 `ls -R` 压缩 **4x-747x**，`digest` 对 CI 日志压缩率达到 **98.9%**[^76^]。这证明了本地算法在特定场景下的高效性。

### 8.2 AI 压缩：语义理解、重要性判断、综合提炼

AI 压缩的优势在于语义理解能力强、能判断内容重要性、能进行综合提炼。适合需要"理解"内容的压缩任务。

**适合的压缩任务**。用户意图提炼（从长用户消息中提取核心需求和约束）、研究证据综合（从多个搜索结果中提炼结论和冲突）、任务状态建立（从混乱的历史中重建清晰的 task_state）、决策日志生成（从 agent_thinking 中提取决策依据和风险管理笔记）、内容重要性排序（判断哪些代码段、哪些搜索结果对当前任务最重要）、下一步建议生成。

### 8.3 Hybrid 三层架构

推荐采用"本地预压缩 → AI 语义精压缩 → 本地验证"的 Hybrid 三层架构。

**第一层：本地预压缩**。快速处理原始内容，生成保守的压缩视图。包括：提取头尾、提取关键词和路径、提取错误段落、生成结构索引、标记 hidden sections。这层压缩在毫秒级完成，确保即使 AI 压缩失败也有可用的压缩视图。

**第二层：AI 语义精压缩**。调用 LLM 对本地预压缩的结果进行语义层面的精炼。包括：生成摘要、判断重要性、建立关联、更新 task_state。这层压缩在秒级完成，是质量的主要贡献者。

**第三层：本地验证**。AI 压缩完成后，进行规则验证确保关键信息未丢失。包括：检查硬约束是否仍在、检查文件路径和行号是否保留、检查 recall id 是否正确关联、检查关键错误是否被标记。如果验证失败，回退到本地预压缩的结果。

### 8.4 降级策略

任何压缩 pipeline 都必须有降级策略。推荐的四级降级链是：（1）正常流程：本地预压缩 → AI 精压缩 → 验证通过；（2）AI 失败降级：本地预压缩 → 直接使用（AI 压缩失败时至少保留本地结果）；（3）本地也失败：保留原始内容 + 标记待压缩；（4）极端情况：head/tail 截断 + 标记需要人工干预。不允许因为压缩失败就丢弃 raw content——这是底线原则。

---

## 9. 压缩质量评估标准

### 9.1 十二项评估维度

如何评价一次压缩是否成功？我们提出十二项标准。

| # | 标准 | 检查方法 | 权重 |
|---|------|---------|------|
| 1 | 用户硬约束保留 | 验证所有 pinned constraints 仍在 | **极高** |
| 2 | 当前任务目标清晰 | Agent 能明确说出 goal 和 next step | **极高** |
| 3 | 关键决策保留 | 验证 decision_log 包含 locked decisions | **极高** |
| 4 | 文件路径和行号保留 | 验证 file_index 的 path/line 准确 | **极高** |
| 5 | 错误和失败原因保留 | 验证 errors 段落包含关键 error | 高 |
| 6 | 来源 URL 和引用保留 | 验证 tool_result_index 的 URL 完整 | 高 |
| 7 | 可召回 ID 完整 | 验证所有 recall 标记指向有效内容 | **极高** |
| 8 | 无幻觉/编造 | 对比原始内容验证摘要准确性 | **极高** |
| 9 | Token 减少率达标 | 实际 token < 原始 token × 目标比率 | 中 |
| 10 | 支持下一步行动 | Agent 看到压缩后能确定 next action | **极高** |
| 11 | Agent 状态更清醒 | 压缩后 Agent 对任务的理解更清晰 | 高 |
| 12 | 可逆性 | 所有压缩内容可通过 recall 恢复原文 | **极高** |

### 9.2 自动化评估

建议实现自动化评估 pipeline：在每次压缩后，使用一个轻量级 LLM（如 GPT-4o-mini）作为评估器，对照原始内容检查上述 12 项标准。评估结果用于：（1）如果评估失败，自动触发 re-compression 或降级；（2）累积评估数据用于优化压缩 prompt；（3）生成压缩质量报告供开发者审查。

### 9.3 压缩失败的典型对比

**失败示例**："之前用户让助手做了很多事情，包括开发项目、搜索资料、修复错误、生成报告……"——这种压缩完全丢失了可执行信息。

**成功示例**：保留清晰的 task_state（goal: 设计 VonishAgent 的 context compression + recall engine）、hard_constraints（不要无脑 head/tail 压缩、tool_result 必须可通过 recall tools 展开）、pending_questions（AI 压缩和本地算法如何分工）等结构化信息。

---

## 10. UI/UX 设计："正在回忆一切……"

### 10.1 状态层级

VonishAgent 的压缩和回忆状态分为三个层级，对用户呈现不同的信息强度。

**轻量后台压缩**。状态文案："正在整理记忆……"或完全不显示（仅在 debug 面板展示）。这是最常见的状态，用户几乎无感知。

**重大回忆模式**。状态文案序列："正在扫描记忆地图……" → "正在召回工具结果……" → "正在展开关键证据……" → "正在钉住用户约束……" → "正在重建工作现场……" → "回忆完成。"这一系列文案的设计目的是让用户理解 Agent 正在从混乱中恢复清醒，而非简单地在"加载"。

**MAX 回忆模式**。状态文案："MAX 回忆模式已开启：剩余 3 轮"。轮数结束时提醒："MAX 回忆模式已结束。若后续仍需隐藏证据，请再次召回。"

### 10.2 用户可见的控制

用户应能触发以下操作：显式触发"回忆一切"（如输入"/recall"或"回忆一下"）、强制 pin/unpin 特定内容、查看当前记忆地图（debug 模式）、调整压缩阈值（高级设置）。

### 10.3 设计哲学

压缩 UI 的核心哲学是**透明而不干扰**。用户应该知道 Agent 在整理记忆，但这个过程不应打断用户的工作流。只有在重大回忆（涉及多轮展开、长时间处理）时才需要显式状态指示。日常的后台压缩应对用户完全透明。

---

## 11. System Prompt 工程方案

### 11.1 模块一：Context Compression Awareness

```
[CONTEXT_COMPRESSION_AWARENESS]

你正在处理的可能是一个经过压缩的上下文快照。这意味着：

1. 部分历史内容已被压缩为摘要形式，不等同于完整原文。
2. 带有 [recall:xxx] 标记的内容表示原始数据仍可召回。
3. 当你需要精确信息（尤其是代码、错误日志、用户原话、证据）时，
   必须使用 recall 工具展开，不能假装已经看过原文。
4. 压缩摘要只应作为"地图"使用——它告诉你有什么，但不代替你看内容。
5. 如果你基于压缩摘要做出了决策，应在关键行动前验证原文。

禁止行为：
- 不要假装展开过内容
- 不要根据摘要编造原文细节
- 不要使用不存在的 tool_result id
- 不要把 compressed summary 当引用来源
- 不要在没有召回证据时写确定性结论
```

### 11.2 模块二：Recall Tool Usage Policy

```
[RECALL_TOOL_USAGE_POLICY]

你必须在以下场景调用 recall 工具：

必须 recall（强制）：
- 写最终报告或交付文件前 → 召回所有相关证据
- 修改代码前 → 召回目标文件的精确内容
- Debug 复杂错误前 → 召回错误日志和相关代码
- 引用事实或数据前 → 召回原始来源
- 对用户的前文做判断前 → 召回用户原话
- 看到 [recall:xxx] 标记且内容可能重要时

建议 recall（推荐）：
- 阶段切换时（研究→写作、读→改、改→验证）
- 长时间工作后重新明确任务时
- 需要对比多个来源时
- 不确定某个决策的依据时

CRAZY_for_MAX 使用规则：
- 仅在重大任务（大重构、复杂 Debug、最终报告）时调用
- 调用时必须提供 reason 说明为什么需要 MAX 模式
- 注意剩余轮数，在过期前完成关键工作
- MAX 模式过期后如需继续，再次调用
```

### 11.3 模块三：Content-Type Handling Policy

```
[CONTENT_TYPE_HANDLING_POLICY]

不同类型的压缩内容有不同的信任级别和使用方式：

user_constraints（用户约束）：
- 信任级别：最高
- 这些是直接来自用户的硬约束，不是摘要
- 即使其他内容都被压缩，约束也必须遵守
- 如果不确定约束的具体含义，recall 用户原话

tool_result_index（工具结果索引）：
- 信任级别：中-高
- 摘要告诉你结果是什么，但精确数据需要 recall
- 写代码前 recall file reads，引用证据前 recall search results
- shell outputs 的摘要通常足够判断状态，debug 时需要 recall 详细日志

code_file_index（代码文件索引）：
- 信任级别：中（结构）/ 必须 recall（修改前）
- 结构索引（函数列表、import）可信
- 但摘要不能替代原始代码——修改代码前必须 recall 原文
- 行号范围和 recall id 是你的地图，跟着它走

agent_thinking / decision_log：
- 信任级别：中
- 这是思维过程的转化，不是原始思考
- 它告诉你之前做了什么决定，但不包含完整推理
- 如果需要理解为什么做某个决定，recall 当时的上下文

conversation_summary（对话摘要）：
- 信任级别：低-中
- 了解话题脉络够用，引用用户原话不够
- 任何涉及用户意图判断的场景都应 recall 原文
```

### 11.4 模块四：Phase-Based Recall 策略

```
[PHASE_BASED_RECALL]

不同工作阶段应优先召回不同类型的内容：

研究阶段：
- 优先 recall: search_evidence, browser_snapshots, research_notes
- 目标：收集足够证据形成结论

编码阶段：
- 优先 recall: file_reads, diffs, errors, shell_outputs
- 目标：理解代码现状，做出正确修改

验证阶段：
- 优先 recall: shell_outputs, test_results, build_logs
- 目标：确认修改正确，没有破坏现有功能

写作/报告阶段：
- 优先 recall: all_evidence（全部证据）
- 考虑 CRAZY_for_MAX
- 目标：确保每个结论都有证据支撑

交付阶段：
- 优先 recall: user_constraints, validation_results
- 目标：确保交付物满足用户要求
```

---

## 12. Tool API 设计草案

### 12.1 recall_maximum（CRAZY_for_MAX 的工程名）

```typescript
interface RecallMaximumInput {
  turns?: number;        // 默认 3，范围 1-10
  scope?: "current_task" | "all_recent" | "research" | "coding" 
        | "debugging" | "artifact" | "custom";
  maxTokens?: number;    // 默认动态计算
  priority?: Array<
    "user_constraints" | "tool_results" | "research_evidence" 
    | "file_reads" | "diffs" | "errors" | "plans" | "chat_messages"
  >;
  includeRaw?: boolean;           // 默认 false
  includeKeySegments?: boolean;   // 默认 true
  query?: string;        // 语义过滤
  reason: string;        // 必填：为什么需要 MAX 模式
}

interface RecallMaximumOutput {
  status: "active" | "expired" | "cancelled";
  turnsRemaining: number;
  expandedItems: Array<{
    type: string;
    id: string;
    tokensUsed: number;
    content: string;  // 展开的内容
  }>;
  totalTokensUsed: number;
  warning?: string;  // 如 "部分请求因预算限制被截断"
}
```

### 12.2 custom_context_recall

```typescript
interface CustomContextRecallTarget {
  type: "tool_result" | "chat_message" | "file" | "file_range"
      | "grep" | "search_result" | "browser_snapshot" | "error_log"
      | "shell_output" | "diff" | "user_constraint" | "plan" 
      | "artifact_validation";
  id?: string;
  path?: string;
  query?: string;
  startLine?: number;
  endLine?: number;
}

interface CustomContextRecallInput {
  targets: CustomContextRecallTarget[];  // 至少一个
  turns?: number;           // 默认 1
  maxTokens?: number;       // 默认 4000
  mode?: "raw" | "key_segments" | "summary_plus_segments" | "structure_only";
  reason: string;           // 必填
}

interface CustomContextRecallOutput {
  recalledItems: Array<{
    target: CustomContextRecallTarget;
    found: boolean;
    content?: string;
    tokensUsed: number;
    hasMore?: boolean;  // 是否有更多内容可召回
  }>;
  totalTokensUsed: number;
}
```

### 12.3 context_map

```typescript
interface ContextMapInput {
  scope?: "all" | "current_task" | "recent" | "pinned";
}

interface ContextMapOutput {
  availableMemory: {
    userConstraints: { total: number; pinned: number };
    toolResults: Record<string, number>;
    chatMessages: { total: number; visible: number; compacted: number };
    pinnedItems: { files: number; decisions: number; errors: number };
  };
  recallStats: {
    totalRecallsThisSession: number;
    mostRecalled: string[];
  };
  compressionStatus: {
    totalRawTokens: number;
    currentCompressedTokens: number;
    compressionRatio: number;
    pendingCompaction: number;
  };
}
```

### 12.4 pin_memory / unpin_memory

```typescript
interface PinMemoryInput {
  target: {
    type: "user_constraint" | "file" | "decision" | "error" | "note";
    id?: string;
    content?: string;
  };
  reason?: string;
  expiresAfterTurns?: number;  // 可选：自动过期
}

interface UnpinMemoryInput {
  targetId: string;
}
```

---

## 13. 数据结构设计草案

### 13.1 核心数据模型

```typescript
// 统一的内容条目——所有上下文内容的基类
interface MemoryEntry {
  id: string;                    // Stable ID，全局唯一
  type: ContentType;             // 12 种内容类型之一
  timestamp: number;             // 创建时间戳
  turnId: string;                // 所属对话轮次
  
  // 原始内容（始终保留，不可删除）
  raw: {
    content: string;
    tokenCount: number;
    checksum: string;
  };
  
  // 压缩视图（多层）
  compressed: {
    local?: LocalCompressedView;     // 本地算法压缩
    ai?: AICompressedView;           // AI 语义压缩
    current: CompressedViewType;     // 当前使用的视图
  };
  
  // 元数据
  metadata: {
    source: string;                // 来源标识
    importance: number;            // 重要性分数 0-1
    recallCount: number;           // 被召回次数
    lastRecalledAt?: number;       // 上次召回时间
    pinned: boolean;               // 是否被钉住
    tags: string[];                // 标签
  };
}

// 本地压缩视图
interface LocalCompressedView {
  head: string;                  // 头部保留内容
  tail: string;                  // 尾部保留内容
  keywords: string[];            // 提取的关键词
  structure?: object;            // 结构化索引（代码用）
  hiddenMap: HiddenSection[];    // 隐藏段落地图
  tokenCount: number;
  createdAt: number;
}

// AI 压缩视图
interface AICompressedView {
  summary: string;               // 语义摘要
  keySegments: KeySegment[];     // 关键片段索引
  taskState?: TaskState;         // 任务状态提取
  decisions?: Decision[];        // 决策提取
  tokenCount: number;
  createdAt: number;
  model: string;                 // 使用的压缩模型
}

// 任务状态
interface TaskState {
  goal: string;
  currentPhase: string;
  completedSteps: string[];
  pendingSteps: string[];
  blockers: string[];
  lastUpdated: number;
}

// 决策记录
interface Decision {
  id: string;
  choice: string;
  rationale: string;
  status: "pending" | "locked" | "reversed";
  timestamp: number;
}

// 关键片段
interface KeySegment {
  description: string;
  rawStart?: number;             // 在 raw 中的起始位置
  rawEnd?: number;               // 在 raw 中的结束位置
  content?: string;              // 片段内容（可选）
}
```

### 13.2 上下文构建器状态

```typescript
interface ContextBuildState {
  budget: {
    total: number;                 // 总预算
    used: number;                  // 已使用
    remaining: number;             // 剩余
  };
  
  layers: {
    pinned: MemoryEntry[];         // L0: Pinned 内容
    taskState: TaskStateEntry;     // L1: 任务状态
    recentTurns: TurnEntry[];      // L2: 最近 N 轮完整对话
    compressedHistory: CompactedEntry[];  // L3: 压缩后的历史
    recalled: RecalledEntry[];     // L4: 当前召回的内容
  };
  
  stats: {
    compressionRatio: number;      // 当前压缩率
    recallCount: number;           // 本 session 召回次数
    lastCompactionAt: number;      // 上次压缩时间
  };
}
```

---

## 14. 禁止事项与安全边界

### 14.1 十五项绝对禁止

| # | 禁止事项 | 违反后果 |
|---|---------|---------|
| 1 | **禁止**把所有内容压缩成一大段散文 | Agent 无法定位可执行信息 |
| 2 | **禁止**无脑只压缩前部（head-only） | 可能丢失用户原始需求和约束 |
| 3 | **禁止**压缩掉用户硬约束 | Agent 偏离用户要求 |
| 4 | **禁止**把代码文件完全自然语言化 | Agent 无法准确修改代码 |
| 5 | **禁止**丢掉文件路径、行号、函数名 | Agent 无法定位和引用代码 |
| 6 | **禁止**丢掉 URL、来源、引用信息 | Agent 无法验证和引用证据 |
| 7 | **禁止**丢掉错误日志中的关键错误 | Agent 重复已知的失败 |
| 8 | **禁止**让模型误以为 compressed summary 是完整原文 | 模型基于不完整信息做决策 |
| 9 | **禁止**没有 recall id 的不可逆压缩 | 内容永久丢失，无法恢复 |
| 10 | **禁止**压缩失败后删除 raw content | 即使压缩失败也必须保留原始 |
| 11 | **禁止**在最终报告前不召回证据 | 报告可能基于摘要编造 |
| 12 | **禁止**在代码修改前只凭摘要改代码 | 修改基于不完整信息，容易出错 |
| 13 | **禁止**把 agent_thinking 原文长期压回上下文 | 污染上下文，降低推理质量 |
| 14 | **禁止**压缩过程中改变用户意图 | 输出偏离用户真实需求 |
| 15 | **禁止**为了省 token 丢掉任务状态 | Agent 迷失方向，不知道下一步做什么 |

### 14.2 安全边界机制

**降级保障**。任何压缩流程都必须有降级链，确保最坏情况下也有可用的上下文（见 8.4 节）。

**原始内容不可删除**。Raw content 是只增不删的——压缩只会增加 compressed view，不会删除 raw。存储管理通过 TTL（过期时间）和归档策略来处理历史内容，而非主动删除。

**验证闭环**。AI 压缩后必须进行本地验证，确保关键信息未丢失。验证失败时自动回退。

---

## 15. 落地路线图

### 15.1 MVP（4-6 周）

**目标**：建立基础的记忆存储、本地压缩和简单召回能力。

**核心组件**：
- **Memory Store**：SQLite 存储 raw message 和 tool_result，每条有 stable id
- **Local Compression**：实现 head/tail、关键词提取、代码 outline 提取、hidden section map
- **Compacted View**：按类型保存本地压缩视图
- **Context Builder**：根据预算组合 pinned + active + compressed
- **Recall Tools**：`custom_context_recall`（基础版）+ `context_map`
- **System Prompt**：基础的 compression awareness 模块
- **UI 状态**："正在整理记忆"的轻量提示

**技术选型**：SQLite（存储）、Tree-sitter（代码结构提取）、正则+规则引擎（本地压缩）。

### 15.2 v1（8-10 周）

**目标**：引入 AI 压缩、完整 recall 工具族、并行压缩。

**新增组件**：
- **AI Compression**：调用 LLM 对 user constraints、research result、long messages 做语义摘要
- **CRAZY_for_MAX**：完整实现最大上下文扩展工具
- **Parallel Compaction**：后台压缩任务队列，与主 Agent 并行执行
- **Pin Memory**：钉住机制实现
- **Phase Detection**：自动检测阶段切换并触发压缩
- **完整 System Prompt**：所有四个模块上线
- **UI 状态**：完整的回忆状态序列

### 15.3 v2（12-16 周）

**目标**：智能压缩、自适应预算、高级 recall。

**新增组件**：
- **Adaptive Budget**：根据任务类型动态调整各层级的 token 预算
- **Importance Scoring**：基于引用频率、任务相关性、用户反馈的重要性评分
- **Semantic Search**：向量检索支持基于语义的 recall
- **Compression Quality Monitoring**：自动化质量评估和反馈循环
- **Task Handoff**：完整的任务交接和恢复机制
- **User Feedback Loop**：用户可以对压缩质量反馈，用于持续优化

---

## 16. 结论

### 16.1 核心设计原则总结

VonishAgent 的上下文压缩与回忆机制设计遵循六项核心原则：**压缩不是遗忘**——而是建立记忆地图、类型化压缩、保留关键原文、允许通过 recall tools 重新展开；**保持结构**——禁止熬成一锅粥的散文摘要，采用 XML 标记的结构化压缩格式；**原文片段优先**——代码、日志、证据必须保留原文片段和行号，不能只变成自然语言描述；**差异化压缩**——12 种内容类型各有不同的压缩策略，不存在统一压缩算法；**并行无感**——后台压缩与主 Agent 并行执行，用户无感知；**AI + 本地 Hybrid**——本地算法负责速度和稳定性，AI 负责语义理解和质量。

### 16.2 关键创新点

本方案相对于现有系统的关键创新包括四个维度。**结构化压缩格式 VCCS**——首次为 Agent Runtime 设计了明确的压缩标记格式，让模型能够区分原始内容、压缩摘要和可召回内容。**Recall 工具族**——设计了 `recall_maximum`、`custom_context_recall`、`context_map`、`pin_memory` 的完整工具生态，使 Agent 能主动管理自己的记忆。**Hybrid 三层架构**——本地预压缩 + AI 精压缩 + 本地验证的分层设计，在速度、成本、质量之间取得了生产级的平衡。**任务再明确机制**——将压缩过程与任务状态重建结合，使 Agent 在压缩后"像洗了把脸重新清醒过来"，而非越压缩越迷糊。

### 16.3 研究支撑

本方案的设计得到了多项前沿研究的有力支撑。Context-Folding（90%+ 压缩率）[^49^] 证明了子任务折叠的有效性；True Memory（93.0% LoCoMo 准确率）[^48^] 验证了以检索为中心的架构优于以存储为中心的架构；Parallel Context Compaction[^1^] 证明了并行压缩的可行性和性能优势；ACE（+10.6% Agent 性能提升）[^59^] 验证了 evolving playbook 理念的有效性；Claude Code 的五层 graduated compaction[^34^] 提供了生产级压缩管道的设计参考；AFM（83.3% 约束召回准确率）[^67^] 证明了结构化保真度管理的必要性。

### 16.4 最终思考

VonishAgent 的上下文压缩机制真正高级的地方在于：**它不是把 Agent 的脑子削薄，而是把混乱的桌面整理成档案柜**。普通 compact 的结果是"前面内容总结如下……"——Agent 越压缩越笨。VonishAgent 的 compact 过程是"正在回忆一切……已恢复用户约束……已恢复工具证据……已恢复文件结构……已恢复错误现场……已恢复下一步目标"——Agent 不是越压缩越健忘，而是像熬夜写代码写懵之后，突然洗了把脸、重新看了一遍任务书、把桌上的纸分门别类放好，然后说："我清醒了，继续。"

这正是 VonishAgent 作为 Agent IDE / Workbench 所需要的：一个不会遗忘、只会整理、越压缩越清醒的记忆系统。

---

## 参考文献

[^1^]: Cim M, Topcu B, Das C, Kandemir M. *Parallel Context Compaction for Long-Horizon LLM Agent Serving*. arXiv:2605.23296, 2026.

[^2^]: Cao S, He J, Tan F. *HiGMem: A Hierarchical and LLM-Guided Memory System for Long-Term Conversational Agents*. arXiv:2604.18349, 2026.

[^8^]: *Active Context Compression: Autonomous Memory Management in LLM Agents (Focus Agent)*. arXiv:2601.07190, 2026.

[^10^]: *AMA-Bench: Evaluating Long-Horizon Memory for Agentic Applications*. arXiv:2602.22769, 2026.

[^14^]: *Inside the Scaffold: A Source-Code Taxonomy of Coding Agent Architectures*. arXiv:2604.03515, 2026.

[^15^]: *Memory Architectures for LLM Agents*. arXiv:2605.00356, 2026.

[^23^]: Jiang H, Wu Q, Lin C Y, et al. *LLMLingua: Compressing Prompts for Accelerated Inference of Large Language Models*. EMNLP 2023.

[^34^]: *Dive into Claude Code: The Design Space of Today's and Future AI Agent Systems*. arXiv:2604.14228, 2026.

[^37^]: *Unrolling the Codex agent loop*. OpenAI Blog, 2026.

[^38^]: *Headroom: Compress AI Agent Context, Logs, and RAG Chunks*. 2026.

[^48^]: *Storage Is Not Memory: A Retrieval-Centered Architecture for Agent Recall (True Memory)*. arXiv:2605.04897, 2026.

[^49^]: *Scaling Long-Horizon LLM Agent via Context-Folding*. arXiv:2510.11967, 2025.

[^59^]: *ACE: Agentic Context Engineering*. arXiv:2510.04618, 2025.

[^67^]: *Agent-Triggered Focus Sessions for Isolated Per-Agent Steering in Multi-Agent LLM Orchestration*. arXiv:2604.07911, 2026.

[^71^]: *LightThinker: Thinking Step-by-Step Compression*. arXiv:2502.15589, 2025.