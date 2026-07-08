# PLAN.md — Coding Agent Harness 实现计划

> 本文档由 `writing-plans` 技能生成，将 SPEC 分解为可由单个 subagent 在一次会话内完成的 task 列表。

---

## 技术选型

| 维度 | 选择 | 理由 |
|------|------|------|
| 语言 | Python 3.11+ | 开发快、pytest 成熟、asyncio 异步支持好 |
| LLM 供应商 | DeepSeek（默认） + Anthropic（可选） | OpenAI 兼容协议，性价比高 |
| 测试框架 | pytest + pytest-asyncio | 支持异步测试 |
| 配置格式 | YAML（声明式策略）+ Pydantic（类型校验） | 人类可读、类型安全 |
| CLI | Click | 简洁的命令分组 |
| WebUI | FastAPI + SSE | 流式传输 |
| 凭据存储 | keyring（+ 环境变量 fallback） | 系统钥匙串，Docker 自动降级 |
| 分发 | Docker | 一条命令运行 |

---

## 项目目录结构

```
coding-agent-harness/
├── harness/                          # 核心源码
│   ├── core/                         # Agent 主循环
│   │   ├── agent.py                  # 主循环
│   │   ├── context_builder.py        # 上下文组装
│   │   ├── action_parser.py          # LLM 输出解析
│   │   └── stop_decision.py          # 停机判断
│   ├── llm/                          # LLM 抽象层
│   │   ├── base.py                   # 抽象基类
│   │   ├── mock_client.py            # 确定性 Mock
│   │   ├── deepseek_client.py        # DeepSeek 接入
│   │   └── anthropic_client.py       # Anthropic 接入
│   ├── tools/                        # 工具系统
│   │   ├── base.py                   # Action/ActionResult/Tool
│   │   ├── registry.py               # 注册与分发
│   │   ├── file_tool.py              # 文件读写
│   │   └── shell_tool.py             # Shell 执行
│   ├── governance/                   # 治理 ★ MAIN CONTRIBUTION ★
│   │   ├── danger_classifier.py      # 危险等级分类
│   │   ├── policy_engine.py          # 声明式策略引擎
│   │   ├── hitl.py                   # HITL 状态机
│   │   ├── scope_fence.py            # 范围围栏
│   │   ├── sandbox.py                # 沙箱隔离
│   │   ├── action_interceptor.py     # 总调度器
│   │   └── policies/                 # 策略文件
│   │       ├── default.yaml
│   │       └── strict.yaml
│   ├── feedback/                     # 反馈闭环
│   │   ├── test_runner.py            # 测试运行
│   │   ├── failure_classifier.py     # 失败分类
│   │   └── feedback_injector.py      # 反馈注入
│   ├── memory/                       # 记忆系统
│   │   ├── session_store.py          # 会话历史
│   │   └── project_store.py          # 项目约定
│   └── config/                       # 配置系统
│       ├── schema.py                 # Pydantic 模式
│       ├── loader.py                 # YAML 加载
│       ├── secrets.py                # 凭据存储
│       └── defaults.yaml             # 默认配置
├── cli/
│   └── main.py                       # CLI 入口
├── tests/
│   ├── unit/
│   │   ├── test_config.py
│   │   ├── test_mock_llm.py
│   │   ├── test_action_parser.py
│   │   ├── test_stop_decision.py
│   │   ├── test_tool_registry.py
│   │   └── governance/
│   │       ├── test_danger_classifier.py
│   │       ├── test_hitl.py
│   │       ├── test_scope_fence.py
│   │       ├── test_policy_engine.py
│   │       └── test_action_interceptor.py
│   └── integration/
│       └── test_full_loop.py
├── demos/
│   ├── demo_guardrail_intercept.py
│   ├── demo_feedback_self_correction.py
│   └── demo_deep_governance.py
├── webui.py                          # WebUI 服务
├── Dockerfile
├── Makefile
├── pyproject.toml
├── requirements.txt
├── .github/workflows/ci.yml
├── SPEC.md
├── PLAN.md
├── SPEC_PROCESS.md
├── REFLECTION.md
└── README.md
```

---

## 实现顺序与 Task 列表

### Tier 0: 项目骨架（基础设施）

#### Task 0.1: 项目脚手架
- **目标**: 创建项目目录结构、pyproject.toml、Makefile、.gitignore、.env.example
- **涉及文件**: `pyproject.toml`, `requirements.txt`, `Makefile`, `.gitignore`, `.env.example`
- **验证**: `pip install -e ".[dev]"` 成功
- **依赖**: 无
- **状态**: ✅ 完成

#### Task 0.2: 配置系统
- **目标**: Pydantic 配置 schema + YAML loader + 环境变量覆盖
- **涉及文件**: `harness/config/schema.py`, `harness/config/loader.py`, `harness/config/defaults.yaml`
- **验证**: 10 个单元测试通过（`test_config.py`）
- **依赖**: Task 0.1
- **状态**: ✅ 完成

#### Task 0.3: 凭据安全存储
- **目标**: 基于 keyring 的 SecretsManager
- **涉及文件**: `harness/config/secrets.py`
- **验证**: 可存储/检索/删除 API key，查看状态不显示明文
- **依赖**: Task 0.1
- **状态**: ✅ 完成

#### Task 0.4: LLM 抽象基类
- **目标**: `LLMClient` 抽象基类 + `LLMResponse` 数据类
- **涉及文件**: `harness/llm/base.py`
- **验证**: 抽象类定义正确，可被 Mock 和真实客户端继承
- **依赖**: Task 0.1
- **状态**: ✅ 完成

### Tier 1: 核心机制

#### Task 1.1: Mock LLM 客户端
- **目标**: 确定性 Mock LLM，支持脚本模式和正则匹配模式
- **涉及文件**: `harness/llm/mock_client.py`, `tests/unit/test_mock_llm.py`
- **验证**: 10 个测试通过，脚本模式按序返回，模式匹配正确，记录调用历史
- **依赖**: Task 0.4
- **状态**: ✅ 完成

#### Task 1.2: 工具基类 + 注册表
- **目标**: `Tool` 抽象基类、`Action`/`ActionResult`/`ToolDefinition` 数据类、`ToolRegistry`
- **涉及文件**: `harness/tools/base.py`, `harness/tools/registry.py`
- **验证**: 注册/注销/分发/查重测试通过
- **依赖**: Task 0.1
- **状态**: ✅ 完成

#### Task 1.3: 文件工具 + Shell 工具
- **目标**: ReadFileTool、WriteFileTool、ListDirectoryTool、ShellTool
- **涉及文件**: `harness/tools/file_tool.py`, `harness/tools/shell_tool.py`, `tests/unit/test_tool_registry.py`
- **验证**: 读写文件、列出目录、执行命令、失败处理全部测试通过
- **依赖**: Task 1.2
- **状态**: ✅ 完成

#### Task 1.4: 动作解析器
- **目标**: 解析 LLM 输出为 Action 列表，支持 JSON/JSON block/自然语言 fallback
- **涉及文件**: `harness/core/action_parser.py`, `tests/unit/test_action_parser.py`
- **验证**: 10 个测试通过，覆盖 JSON/JSON block/多 action/无效 JSON/stop 检测
- **依赖**: Task 1.2
- **状态**: ✅ 完成

#### Task 1.5: 停机决策
- **目标**: StopDecisionEngine，判断任务完成/最大迭代/连续失败/LLM 错误/手动停止
- **涉及文件**: `harness/core/stop_decision.py`, `tests/unit/test_stop_decision.py`
- **验证**: 9 个测试通过，覆盖所有停机条件和优先级
- **依赖**: Task 0.1
- **状态**: ✅ 完成

### Tier 2: 治理核心 ★ MAIN CONTRIBUTION ★

#### Task 2.1: 危险等级分类器
- **目标**: DangerClassifier，30+ 正则模式 + 工具类型规则，四级分类
- **涉及文件**: `harness/governance/danger_classifier.py`, `tests/unit/governance/test_danger_classifier.py`
- **验证**: 26 个测试通过，覆盖所有危险等级和命令模式
- **依赖**: Task 1.2
- **状态**: ✅ 完成

#### Task 2.2: 策略引擎
- **目标**: PolicyEngine，优先级排序的声明式规则引擎，支持 regex/equals/in/not_in
- **涉及文件**: `harness/governance/policy_engine.py`, `tests/unit/governance/test_policy_engine.py`
- **验证**: 15 个测试通过，覆盖 default/strict/permissive 三种预设策略
- **依赖**: Task 2.1
- **状态**: ✅ 完成

#### Task 2.3: HITL 状态机
- **目标**: HITLStateMachine，纯函数式 (State, Event) → State，可注入 approval_callback
- **涉及文件**: `harness/governance/hitl.py`, `tests/unit/governance/test_hitl.py`
- **验证**: 15 个测试通过，覆盖所有状态转移和审批/拒绝/超时
- **依赖**: Task 1.2
- **状态**: ✅ 完成

#### Task 2.4: 范围围栏
- **目标**: ScopeFence，路径/命令/扩展名验证，防御路径穿越
- **涉及文件**: `harness/governance/scope_fence.py`, `tests/unit/governance/test_scope_fence.py`
- **验证**: 16 个测试通过，覆盖路径/命令/扩展名/敏感文件
- **依赖**: Task 0.1
- **状态**: ✅ 完成

### Tier 3: 治理集成

#### Task 3.1: 沙箱
- **目标**: Sandbox，三种策略（none/subprocess/docker）
- **涉及文件**: `harness/governance/sandbox.py`
- **验证**: 超时控制正常，策略切换正常
- **依赖**: Task 1.2
- **状态**: ✅ 完成

#### Task 3.2: 护栏总调度器 + 策略文件
- **目标**: ActionInterceptor 串联全部治理子系统，default.yaml + strict.yaml 策略文件
- **涉及文件**: `harness/governance/action_interceptor.py`, `harness/governance/policies/default.yaml`, `harness/governance/policies/strict.yaml`, `tests/unit/governance/test_action_interceptor.py`
- **验证**: 14 个测试通过，覆盖完整 pipeline 和各种 verdict 组合
- **依赖**: Task 2.1-2.4, Task 3.1
- **状态**: ✅ 完成

### Tier 4: 反馈闭环

#### Task 4.1: 测试运行器 + 结果解析器
- **目标**: SuiteRunner 异步执行 pytest 并解析输出
- **涉及文件**: `harness/feedback/test_runner.py`
- **验证**: 可解析 pytest 输出的 passed/failed/errors 和单个失败详情
- **依赖**: Task 0.1
- **状态**: ✅ 完成

#### Task 4.2: 失败分类器 + 反馈注入器
- **目标**: FailureClassifier（7 种分类）+ FeedbackInjector（格式化注入）
- **涉及文件**: `harness/feedback/failure_classifier.py`, `harness/feedback/feedback_injector.py`
- **验证**: 分类正确，反馈消息格式正确，`needs_correction()` 判断正确
- **依赖**: Task 4.1
- **状态**: ✅ 完成

### Tier 5: 记忆系统

#### Task 5.1: 会话存储 + 项目存储
- **目标**: SessionStore（内存历史）+ ProjectStore（JSON 持久化）
- **涉及文件**: `harness/memory/session_store.py`, `harness/memory/project_store.py`
- **验证**: 会话历史增删/截断，项目约定读写/持久化
- **依赖**: Task 0.1
- **状态**: ✅ 完成

### Tier 6: Agent 循环集成

#### Task 6.1: 上下文构建器
- **目标**: ContextBuilder 组装系统提示词 + 工具定义 + 会话历史 + 项目记忆
- **涉及文件**: `harness/core/context_builder.py`
- **验证**: 构建的 messages 列表包含 system prompt 和历史
- **依赖**: Task 1.3, Task 5.1
- **状态**: ✅ 完成

#### Task 6.2: Agent 主循环
- **目标**: Agent.run() 实现完整主循环
- **涉及文件**: `harness/core/agent.py`
- **验证**: 集成测试通过（Mock LLM 下完整运行）
- **依赖**: Task 1.1-1.5, Task 3.2, Task 4.2, Task 5.1, Task 6.1
- **状态**: ✅ 完成

#### Task 6.3: 真实 LLM 客户端
- **目标**: DeepSeekClient + AnthropicClient
- **涉及文件**: `harness/llm/deepseek_client.py`, `harness/llm/anthropic_client.py`
- **验证**: 真实 API 调用成功（需 API Key）
- **依赖**: Task 0.3, Task 0.4
- **状态**: ✅ 完成

### Tier 7: 演示、CI/CD、分发

#### Task 7.1: 三个机制演示脚本
- **目标**: demo_guardrail_intercept.py, demo_feedback_self_correction.py, demo_deep_governance.py
- **涉及文件**: `demos/`
- **验证**: 三个脚本均可独立运行，输出清晰
- **依赖**: Task 3.2, Task 4.2
- **状态**: ✅ 完成

#### Task 7.2: 集成测试
- **目标**: 端到端集成测试 + 三个机制演示的确定性测试
- **涉及文件**: `tests/integration/test_full_loop.py`
- **验证**: 7 个集成测试通过（Mock LLM）
- **依赖**: Task 6.2, Task 7.1
- **状态**: ✅ 完成

#### Task 7.3: CI 配置
- **目标**: GitHub Actions，每次 push 自动运行测试 + 构建 Docker 镜像
- **涉及文件**: `.github/workflows/ci.yml`
- **验证**: CI 通过（unit-test job + docker-build job）
- **依赖**: Task 7.2
- **状态**: ✅ 完成

#### Task 7.4: Docker 分发
- **目标**: Dockerfile + docker build + docker run
- **涉及文件**: `Dockerfile`
- **验证**: `docker build` 成功，`docker run` 可启动 WebUI
- **依赖**: Task 6.3
- **状态**: ✅ 完成

#### Task 7.5: CLI 入口 + WebUI
- **目标**: Click CLI（run/interactive/web/demo/test/setup-key/key-status/delete-key）+ FastAPI WebUI
- **涉及文件**: `cli/main.py`, `webui.py`
- **验证**: 所有 CLI 命令可用，WebUI 可访问
- **依赖**: Task 6.2, Task 6.3
- **状态**: ✅ 完成

#### Task 7.6: 文档
- **目标**: SPEC.md, PLAN.md, SPEC_PROCESS.md, REFLECTION.md, README.md
- **涉及文件**: 上述五个 .md 文件
- **验证**: 文档完整，符合课程要求
- **依赖**: 所有 task
- **状态**: ✅ 完成

---

## 依赖关系图

```
Tier 0 (基础设施)
  0.1 项目骨架 ──┬── 0.2 配置系统
                 ├── 0.3 凭据存储
                 └── 0.4 LLM 抽象
                      │
Tier 1 (核心机制)      │
  0.4 ──→ 1.1 Mock LLM
  0.1 ──→ 1.2 工具基类 ──→ 1.3 文件+Shell工具
  1.2 ──→ 1.4 动作解析器
  0.1 ──→ 1.5 停机决策
                      │
Tier 2 (治理核心 ★)    │
  1.2 ──→ 2.1 危险分类器 ──→ 2.2 策略引擎
  1.2 ──→ 2.3 HITL 状态机
  0.1 ──→ 2.4 范围围栏
                      │
Tier 3 (治理集成)      │
  1.2 ──→ 3.1 沙箱
  2.1-2.4,3.1 ──→ 3.2 总调度器
                      │
Tier 4 (反馈闭环)      │
  0.1 ──→ 4.1 测试运行器 ──→ 4.2 失败分类+注入
                      │
Tier 5 (记忆)         │
  0.1 ──→ 5.1 会话+项目存储
                      │
Tier 6 (Agent 集成)    │
  1.3,5.1 ──→ 6.1 上下文构建器
  全部 ──→ 6.2 Agent 主循环
  0.3,0.4 ──→ 6.3 真实 LLM
                      │
Tier 7 (交付)         │
  3.2,4.2 ──→ 7.1 演示脚本
  6.2,7.1 ──→ 7.2 集成测试
  7.2 ──→ 7.3 CI 配置
  6.3 ──→ 7.4 Docker
  6.2,6.3 ──→ 7.5 CLI+WebUI
  全部 ──→ 7.6 文档
```

---

## 可并行部分

| 并行组 | Tasks |
|--------|-------|
| Tier 0 内部 | 0.2, 0.3, 0.4 可并行 |
| Tier 1 内部 | 1.1, 1.2, 1.5 可并行 |
| Tier 2 内部 | 2.1, 2.3, 2.4 可并行（2.2 依赖 2.1） |
| Tier 4 内部 | 4.1 和 4.2 可合并 |
| 跨 Tier | Tier 4 (反馈) 和 Tier 5 (记忆) 与 Tier 2-3 (治理) 无依赖，可并行开发 |

---

## 最终测试结果

- **单元测试**: 143 个（治理 86 + 工具 22 + 解析器 10 + 配置 10 + Mock LLM 10 + 停机 9 + 其他）
- **集成测试**: 7 个（完整 Agent 循环 + 3 个机制演示）
- **总计**: 150 个测试全部通过
- **测试环境**: Mock LLM，无需网络，无需 API Key
- **CI 状态**: GitHub Actions 每次 push 自动运行全部测试