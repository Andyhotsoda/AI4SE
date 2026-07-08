# SPEC.md — Coding Agent Harness

> 本文件与 `AI4SE_Final_Project_A_Coding_Agent_Harness.md`（项目专属要求）及 `request.md`（通用要求）拼接阅读。

---

## 1. 问题陈述

### 1.1 要解决什么问题

当前 LLM（大语言模型）已经能完成大部分"思考"——决定下一步做什么。但 LLM 本身只是一个文本生成器，它不能读写文件、不能执行命令、不能自我纠错、不能感知危险操作。将 LLM 变成一个能稳定、可靠地完成编码任务的 **Coding Agent**，需要一层工程化的 **Harness**（缰绳）。

核心等式：**Agent = LLM + Harness**。LLM 是"CPU"，Harness 是剩下的所有工程。

### 1.2 目标用户

- 希望用 AI 辅助编码、但需要安全护栏的软件开发者
- 需要一套可审计、可测试的 agent 框架的研究者和工程师
- AI4SE 课程的学生和教师（作为教学案例）

### 1.3 为什么值得做

现有 Agent 框架（LangChain、AutoGen、CrewAI 等）提供了高层编排，但开发者往往只是做配置而非真正理解 agent 内部的工程机制。本项目从头构建一个 Harness，强制实现每个核心机制（主循环、工具分发、治理护栏、反馈闭环、记忆管理），让构建者对"一个可靠的 agent 系统到底需要哪些工程"获得第一手回答。

---

## 2. 用户故事

| # | 用户故事 | 验收标准 |
|---|---------|---------|
| US1 | 作为开发者，我想通过 CLI 给 Agent 一个编码任务，让它自动读写文件并执行命令来完成任务 | Agent 能解析自然语言任务，自主选择工具并执行，最终返回结果 |
| US2 | 作为开发者，我要求 Agent 执行 `rm -rf /` 时，系统必须拦截并拒绝，而不是依赖 LLM 的"自觉" | 护栏系统用确定性代码（正则匹配）拦截危险动作，不依赖 LLM 提示词 |
| US3 | 作为开发者，当 Agent 生成的代码测试失败时，系统应自动解析失败原因并反馈给 Agent 进行自我修正 | 反馈闭环：测试失败 → 分类 → 注入 LLM 上下文 → Agent 修正 |
| US4 | 作为安全管理员，我希望 Agent 只能操作指定目录内的文件，不能越界访问系统文件 | ScopeFence 用绝对路径解析阻止路径穿越攻击 |
| US5 | 作为用户，我可以通过 Web 浏览器与 Agent 交互，实时看到 Agent 的思考和执行过程 | WebUI 提供 SSE 流式传输，左侧对话、右侧文件预览 |
| US6 | 作为开发者，我可以在不连网、不调用真实 LLM 的情况下运行所有测试 | Mock LLM 驱动 150+ 个确定性单元测试，一键运行 |
| US7 | 作为用户，我的 API Key 绝不硬编码进源码、不提交 Git、不在日志中暴露 | 使用系统 keyring 安全存储，Docker 中支持环境变量 fallback |

---

## 3. 功能规约

### 3.1 Agent 主循环（决策封装）

- **输入**: 用户任务（自然语言字符串）
- **行为**:
  1. 构建上下文（系统提示词 + 工具定义 + 会话历史 + 项目记忆）
  2. 调用 LLM 获取响应
  3. 解析响应中的工具调用（JSON 格式）
  4. 对每个工具调用运行治理 pipeline（危险分类 → 策略 → HITL → 围栏 → 沙箱）
  5. 执行工具，收集结果
  6. 将结果回灌到会话上下文
  7. 检查停机条件（任务完成 / 最大迭代 / 连续失败）
  8. 若未停机，回到步骤 1
- **输出**: `AgentResult`（success, stop_reason, turns, total_iterations, total_actions）
- **边界条件**: 最大迭代次数（默认 30）、最大连续失败次数（默认 5）
- **错误处理**: LLM 调用失败 → 记录错误并停机；工具执行失败 → 注入反馈并继续

### 3.2 工具系统

| 工具 | 功能 | 输入参数 | 输出 |
|------|------|---------|------|
| `read_file` | 读取文件内容 | `path: str` | 文件内容或错误信息 |
| `write_file` | 写入文件（自动创建父目录） | `path: str, content: str` | 成功/失败 |
| `list_directory` | 列出目录内容 | `path: str` | 文件列表 |
| `shell` | 执行 Shell 命令 | `command: str` | stdout/stderr + 退出码 |
| `stop` | 信号任务完成 | `reason: str` | — |

所有工具实现 `Tool` 抽象基类，通过 `ToolRegistry` 注册和分发。

### 3.3 治理/护栏系统 ★ MAIN CONTRIBUTION ★

五子系统 pipeline：

```
Action → DangerClassifier → PolicyEngine → HITL StateMachine → ScopeFence → Sandbox → Execute
```

#### 3.3.1 DangerClassifier（危险等级分类）

- **纯代码、确定性**，30+ 正则模式 + 工具类型规则
- 四级分类：`SAFE` → `WARNING` → `DANGEROUS` → `CRITICAL`
- 示例：`rm -rf /` → CRITICAL；`git push --force` → DANGEROUS；`ls` → SAFE
- 支持自定义规则（Callable 注入）

#### 3.3.2 PolicyEngine（声明式策略引擎）

- 优先级排序的规则引擎，高优先级先匹配
- 每条规则：`{条件: {字段: {操作符: 值}}} → 判决: ALLOW/DENY/ASK/SANDBOX`
- 支持操作符：`regex`、`equals`、`in`、`not_in`
- 三级预设策略：`default`（推荐）、`strict`（严格）、`permissive`（宽松）
- 默认判决：`ALLOW`（default policy）

#### 3.3.3 HITL StateMachine（人工审批状态机）

- 纯函数式 `(State, Event) → State`
- 五个状态：`IDLE → AWAITING_APPROVAL → APPROVED/DENIED/TIMED_OUT → IDLE`
- `approval_callback` 可注入（测试用 mock，生产用控制台输入）
- 超时可配置（默认 120s）
- 所有状态转换记录到 history

#### 3.3.4 ScopeFence（范围围栏）

- 允许目录白名单：只能操作指定目录内的路径
- 命令白名单：只能执行白名单内的命令
- 扩展名白名单：只能创建/修改允许的文件类型
- 拒绝模式：`.env`、`.pem`、`.key`、`credentials`、`.git/` 等敏感文件
- 路径穿越防御：使用 `Path.resolve()` 解析绝对路径

#### 3.3.5 Sandbox（沙箱隔离）

- 三种策略：`none`（无隔离）、`subprocess`（asyncio 超时限制）、`docker`（完全隔离）
- `subprocess` 策略：可配置超时（默认 60s）

#### 3.3.6 ActionInterceptor（总调度器）

- 串联所有治理子系统的单一入口点
- 返回 `InterceptResult`（allowed, verdict, reason, danger_level, use_sandbox, matched_rule）

### 3.4 反馈闭环

```
Agent 写代码 → 运行测试 → 解析结果 → 分类失败 → 注入 LLM 上下文 → Agent 修正
```

- **TestRunner（SuiteRunner）**: 异步执行 pytest，解析输出为结构化 `TestResult`
- **FailureClassifier**: 7 种失败分类（SYNTAX_ERROR / IMPORT_ERROR / TYPE_ERROR / ASSERTION_FAILURE / RUNTIME_ERROR / TEST_ERROR / UNKNOWN），每类有针对性指导语
- **FeedbackInjector**: 格式化反馈消息，注入 LLM 对话上下文

### 3.5 记忆系统

- **SessionStore**: 会话内对话历史（内存），支持 max_history_turns 截断
- **ProjectStore**: 跨会话持久化（JSON 文件），存储项目约定和知识

### 3.6 配置系统

- **Pydantic Schema**: 类型安全的配置模型（AgentConfig, GovernanceConfig, LLMConfig 等）
- **YAML Loader**: 从文件加载配置，支持环境变量覆盖（`HARNESS_*` 前缀）
- **SecretsManager**: 基于系统 keyring 的凭据安全存储，Docker 环境自动 fallback 到环境变量

### 3.7 LLM 抽象层

- **LLMClient 抽象基类**: 定义 `complete()` 和 `count_tokens()` 接口
- **MockLLMClient**: 脚本模式（按顺序返回）+ 正则匹配模式，用于确定性测试
- **DeepSeekClient**: 通过 OpenAI 兼容协议接入 DeepSeek API
- **AnthropicClient**: 原生 Anthropic API 接入

### 3.8 CLI 和 WebUI

- **CLI**: `harness run`（单次任务）、`harness interactive`（交互式会话）、`harness setup-key`（凭据管理）、`harness demo`（演示）、`harness test`（测试）
- **WebUI**: FastAPI + SSE 流式传输，深色主题，左侧对话右侧文件预览

---

## 4. 非功能性需求

### 4.1 性能

- Mock LLM 测试套件（150 个测试）在 2 秒内完成
- Agent 单次迭代响应时间 < 5 秒（取决于 LLM API 延迟）
- 会话历史截断到最近 50 轮，防止上下文溢出

### 4.2 安全（含凭据威胁模型）

**威胁模型**:
- 威胁 1: API Key 硬编码在源码中 → 被 Git 提交泄露
- 威胁 2: API Key 通过命令行 `export` 设置 → 进入 shell history
- 威胁 3: API Key 写入日志/终端输出 → 被截屏或日志泄露
- 威胁 4: Agent 执行危险命令 → 系统级破坏
- 威胁 5: Agent 访问项目外文件 → 数据泄露
- 威胁 6: Agent 读写敏感文件（.env, .pem, .key）→ 凭据泄露

**对策**:
- Key 存储: 系统 keyring（Windows Credential Manager / macOS Keychain / Linux Secret Service），Docker 中 fallback 到环境变量
- Key 显示: `harness key-status` 只显示前 8 位和后 4 位，不显示完整 key
- 危险命令: DangerClassifier + PolicyEngine 拦截，HITL 要求人工审批
- 范围围栏: ScopeFence 限制操作目录，拒绝敏感文件模式
- 沙箱: subprocess 超时限制，可选 Docker 完全隔离

### 4.3 可用性

- 一键安装: `pip install -e ".[dev]"`
- 一键测试: `make test`（无需网络、无需 API Key）
- 一键演示: `make demo`
- CLI 帮助: `harness --help` 每个子命令都有详细帮助

### 4.4 可观测性

- Agent 每轮迭代记录完整的 `AgentTurn`（自然语言文本 + 工具执行记录）
- 工具执行结果记录到 `ToolExecution`（action, result, allowed, blocked_reason）
- HITL 审批历史记录到 `ApprovalRecord` 列表
- Mock LLM 记录完整调用历史（`call_history`）

---

## 5. 系统架构

### 5.1 组件图

```
┌──────────────────────────────────────────────────────────────┐
│                         CLI / WebUI                           │
├──────────────────────────────────────────────────────────────┤
│                        Agent (主循环)                          │
│  ContextBuilder → LLMClient → ActionParser → ActionInterceptor│
│  → ToolRegistry → Feedback → StopDecision → (loop)            │
├──────────────────────────────────────────────────────────────┤
│  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────────────┐ │
│  │   LLM    │ │  Tools   │ │Governance│ │    Feedback      │ │
│  │ Abstract │ │ Registry │ │ Pipeline │ │ TestRunner       │ │
│  │ Mock     │ │ File I/O │ │ Classifier│ │ FailureClassifier│ │
│  │ DeepSeek │ │ Shell    │ │ Policy   │ │ FeedbackInjector │ │
│  │ Anthropic│ │          │ │ HITL     │ │                  │ │
│  └──────────┘ └──────────┘ │ Fence    │ └──────────────────┘ │
│                             │ Sandbox  │                      │
│  ┌──────────┐ ┌──────────┐  └──────────────────┘             │
│  │  Memory  │ │  Config  │                                    │
│  │ Session  │ │ Schema   │                                    │
│  │ Project  │ │ Secrets  │                                    │
│  └──────────┘ └──────────┘                                    │
└──────────────────────────────────────────────────────────────┘
```

### 5.2 数据流

```
User Task
    │
    ▼
┌─────────────────┐
│  ContextBuilder  │ ← SessionStore (历史) + ProjectStore (约定)
└─────────────────┘
    │
    ▼
┌─────────────────┐
│   LLMClient      │ ← DeepSeek / Anthropic / Mock
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  ActionParser    │ → List[Action]
└─────────────────┘
    │
    ▼ (每个 Action)
┌──────────────────────┐
│  ActionInterceptor    │
│  DangerClassifier     │ → DangerLevel
│  PolicyEngine         │ → ALLOW/DENY/ASK/SANDBOX
│  HITLStateMachine     │ → APPROVED/DENIED/TIMED_OUT
│  ScopeFence           │ → 路径/命令校验
│  Sandbox              │ → 隔离执行
└──────────────────────┘
    │
    ▼
┌─────────────────┐
│  ToolRegistry    │ → ActionResult
└─────────────────┘
    │
    ▼
┌─────────────────┐
│  FeedbackLoop    │ → 测试 → 分类 → 注入上下文
└─────────────────┘
    │
    ▼
┌─────────────────┐
│ StopDecision     │ → 继续 / 停机
└─────────────────┘
```

### 5.3 外部依赖

- **LLM 供应商**: DeepSeek API（`https://api.deepseek.com`）、Anthropic API
- **Python 库**: `openai`（DeepSeek 兼容）、`anthropic`（Anthropic）、`pydantic`（配置校验）、`pyyaml`（配置解析）、`keyring`（凭据存储）、`click`（CLI）、`fastapi` + `uvicorn`（WebUI）
- **测试**: `pytest` + `pytest-asyncio`
- **分发**: Docker

---

## 6. 数据模型

| 实体 | 字段 | 约束 |
|------|------|------|
| `Action` | tool_name: str, parameters: dict, raw: str | tool_name ∈ VALID_TOOLS |
| `ActionResult` | success: bool, output: str, error: Optional[str] | — |
| `DangerLevel` | Enum: SAFE=0, WARNING=1, DANGEROUS=2, CRITICAL=3 | 有序枚举 |
| `InterceptResult` | allowed: bool, verdict: InterceptVerdict, reason: str, danger_level: DangerLevel, use_sandbox: bool, matched_rule: Optional[str] | — |
| `AgentTurn` | iteration: int, full_response: str, natural_text: str, tool_executions: list[ToolExecution], timestamp: datetime | — |
| `AgentResult` | success: bool, stop_reason: StopReason, message: str, turns: list[AgentTurn], total_iterations: int, total_actions: int | — |
| `StopReason` | Enum: TASK_COMPLETE, MAX_ITERATIONS, MAX_FAILURES, LLM_ERROR, MANUAL_STOP | — |
| `HITLState` | Enum: IDLE, AWAITING_APPROVAL, APPROVED, DENIED, TIMED_OUT | 状态转移表约束 |
| `TestResult` | total: int, passed: int, failed: int, errors: int, failures: list[TestFailure], raw_output: str, exit_code: int | total = passed + failed + errors |
| `TestFailure` | test_name: str, error_type: str, message: str, traceback: str, file_path: Optional[str], line_number: Optional[int] | — |
| `FailureCategory` | Enum: SYNTAX_ERROR, IMPORT_ERROR, TYPE_ERROR, ASSERTION_FAILURE, RUNTIME_ERROR, TEST_ERROR, UNKNOWN | — |
| `PolicyRule` | name: str, description: str, priority: int, condition: dict, verdict: str, reason: str | priority 越高越先匹配 |
| `ConversationTurn` | role: str, content: str, timestamp: datetime, metadata: dict | role ∈ {user, assistant, feedback} |

---

## 7. 凭据与分发设计

### 7.1 凭据存储方案

**三层优先级**:
1. 代码参数（显式传入 `api_key`）
2. 系统 keyring（Windows Credential Manager / macOS Keychain / Linux Secret Service）
3. 环境变量（`DEEPSEEK_API_KEY` 或 `ANTHROPIC_API_KEY`）

**录入流程**: `harness setup-key` → 调用 `getpass` 隐藏输入 → 存储到系统 keyring

**查看状态**: `harness key-status` → 显示 `stored (sk-xxx...xyz)` 或 `not stored`

**删除**: `harness delete-key` → 确认后从 keyring 删除

**Docker 环境**: keyring 不可用时自动 fallback 到环境变量，用户通过 `docker run -e DEEPSEEK_API_KEY=sk-xxx` 传入

### 7.2 分发形态

**Docker（主要）**:
```bash
docker build -t coding-agent-harness .
docker run --rm -p 8000:8000 -e DEEPSEEK_API_KEY=sk-xxx -v $(pwd):/workspace coding-agent-harness
```

**pip 安装（开发）**:
```bash
pip install -e ".[dev]"
harness web
```

**平台**: Linux (Docker)、Windows/macOS（直接运行）

---

## 8. 技术选型与理由

| 维度 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.11+ | 开发快、pytest 测试成熟、asyncio 异步支持好、AI 生态丰富 |
| LLM 供应商 | DeepSeek（默认） | 性价比高、OpenAI 兼容协议、支持中文 |
| 测试框架 | pytest + pytest-asyncio | 异步测试支持、fixture 机制灵活 |
| 配置格式 | YAML + Pydantic | 人类可读、类型安全、支持环境变量覆盖 |
| CLI | Click | 简洁的 CLI 框架、命令分组 |
| WebUI | FastAPI + SSE | 异步支持、流式传输、轻量 |
| 凭据存储 | keyring (+ 环境变量 fallback) | 跨平台操作系统钥匙串，Docker 中自动降级 |
| 分发 | Docker | 一条命令运行，环境隔离 |

---

## 9. 领域与机制设计（Coding Agent Harness 专属）

### 9.1 领域的反馈信号

Coding 领域的反馈信号是**客观、确定、可自动化**的：
- 测试结果（pytest pass/fail）
- Lint 检查（语法/风格）
- 类型检查（mypy/pyright）
- 退出码（0 = 成功，非 0 = 失败）

本项目实现：`SuiteRunner` 异步执行 pytest → 解析输出 → `FailureClassifier` 分类 → `FeedbackInjector` 注入 LLM 上下文。

### 9.2 危险动作

Coding 场景的危险动作：
- 系统级破坏：`rm -rf /`、`mkfs`、`dd if=... of=/dev/...`
- 远程代码执行：`curl ... | bash`、`eval`
- 强制推送：`git push --force`、`git push --delete`
- 权限提升：`sudo`、`chmod 777 /`
- 包安装：`pip install`、`npm install -g`

### 9.3 所需工具

- 文件读写（read_file, write_file, list_directory）
- Shell 命令执行（shell）
- 测试运行（通过 shell 调用 pytest）

### 9.4 记忆需求

- 会话内：对话历史、工具调用结果（用于上下文组装）
- 跨会话：项目约定、历史决策（JSON 持久化）

### 9.5 重点维度：治理/护栏

选择治理作为 Main Contribution 的理由：
- 天然由代码构成（正则匹配、状态机、路径解析），最契合"机制必须是代码"的要求
- 五个子系统独立可测试，组合后形成完整防御链
- 每个子系统都有明确的确定性行为，可用 mock LLM 验证
- 工程深度体现在 pipeline 的组合设计、HITL 状态机的形式化、PolicyEngine 的声明式规则系统

### 9.6 机制编码实现

所有机制均满足"移除 LLM 后仍可用单测验证"的硬标准：
- **护栏**: `DangerClassifier.classify(Action(command="rm -rf /"))` → 断言返回 `CRITICAL`
- **HITL**: `hitl.transition(REQUEST_APPROVAL)` → 断言 `state == AWAITING_APPROVAL`
- **反馈**: `FailureClassifier.classify(TestFailure(error_type="AssertionError"))` → 断言返回 `ASSERTION_FAILURE`
- **围栏**: `ScopeFence.validate_path("/etc/passwd")` → 断言 `allowed == False`

---

## 10. 验收标准

| 功能 | 验收标准 |
|------|---------|
| Agent 主循环 | Mock LLM 下完整运行一个任务，正确停机 |
| 工具系统 | 4 个工具全部注册、分发、执行正常 |
| 护栏拦截 | `rm -rf /` 被拦截，`ls` 放行 |
| HITL 审批 | 状态机全部转移正确，审批/拒绝/超时均可测试 |
| 范围围栏 | 项目外路径被拒绝，敏感文件被拒绝 |
| 反馈闭环 | 测试失败 → 分类 → 生成反馈消息 → `needs_correction()` 为 True |
| 凭据安全 | key 不硬编码、不提交 Git、`key-status` 不显示明文 |
| Mock 测试 | 所有 150 个测试在无网络环境下通过 |
| 机制演示 | 3 个 demo 脚本确定性地展示护栏、反馈、深度治理 |
| Docker 分发 | `docker build` + `docker run` 可启动 WebUI |

---

## 11. 风险与未决问题

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| LLM 输出格式不稳定 | ActionParser 无法解析 | 支持 JSON block、standalone JSON、自然语言 fallback 多种解析方式 |
| keyring 在 Docker 中不可用 | 凭据存储失败 | 自动 fallback 到环境变量，安装 keyrings.alt |
| LLM 响应超时 | Agent 卡住 | 设置 max_iterations 和 max_consecutive_failures |
| LLM 生成危险代码 | 系统安全风险 | 治理 pipeline 在工具执行前拦截，而非依赖 LLM 自觉 |
| 跨平台路径差异 | ScopeFence 校验失败 | 全部使用 `Path.resolve()` 绝对路径，正则用 `[\\\/]` 兼容 |
| 真实 LLM 集成测试成本高 | 难以频繁运行 | 核心机制全部用 Mock LLM 测试，真实 LLM 测试仅作为可选 |