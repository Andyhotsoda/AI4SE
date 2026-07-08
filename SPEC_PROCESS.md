# SPEC_PROCESS.md — 规约与计划生成过程

> 本文档记录与 Superpowers（Claude Code）协作生成 SPEC 和 PLAN 的完整过程。

---

## 一、过程概述

本项目使用 Claude Code 作为编码智能体，遵循 Superpowers 的七步工作流。整个过程从两份需求文档出发，经过 brainstorming → 架构设计 → 计划分解 → 分层实现 → 调试修复 → 功能扩展，最终交付一个完整的 Coding Agent Harness。

---

## 二、Brainstorming 关键节点

### 2.1 需求理解阶段

智能体首先读取了两个需求文件（`AI4SE_Final_Project_A_Coding_Agent_Harness.md` 和 `request.md`），然后进入 plan mode 进行架构设计。在进入 plan mode 之前，智能体提出了四个关键决策问题：

1. **编程语言选择**（TypeScript / Python / Go / Rust）
2. **重点深入维度**（Governance / Feedback / Memory / Multi-Agent）
3. **分发方式**（Docker / npm / 单文件二进制）
4. **LLM 供应商**（Anthropic / OpenAI / 多供应商）

### 2.2 关键决策节点

**节点 1: 语言选择（Java → Python）**

一开始用户询问是否可以用 Java。智能体详细分析了 Java 的可行性（强类型、JUnit 5、Picocli、Maven/Gradle、ProcessBuilder、Fat JAR），并给予肯定。但随后用户决定"还是用 Python 吧"。

- **AI 提出的建议**: 四种语言各有优劣，但推荐 TypeScript 或 Python
- **用户决策**: 先问 Java，后改为 Python
- **我的处理**: 接受 AI 的建议，Python 的 pytest 异步测试生态和 AI 库支持确实是更高效的选择

**节点 2: 重点维度选择（治理/护栏）**

智能体提供了四个建议方向，推荐治理/护栏作为 Main Contribution，理由是：
- 天然由代码构成（正则匹配、状态机、路径解析）
- 最契合"机制必须是代码"的要求
- 五个子系统独立可测试

- **AI 提出的建议**: 四个方向各有深度，推荐治理
- **用户决策**: 接受默认推荐
- **我的处理**: 同意。治理系统的 pipeline 设计确实最能体现工程深度

**节点 3: 分发方式（Docker）**

- **AI 提出的建议**: Docker 最通用
- **用户决策**: 接受默认
- **我的处理**: 同意。Docker 提供了最一致的环境

**节点 4: LLM 供应商变更（Anthropic → DeepSeek）**

初始架构设计基于 Anthropic Claude。但在项目后期，用户提出"我预想用 deepseek"。智能体立即添加了 `DeepSeekClient`，使用 OpenAI 兼容协议接入。

- **AI 提出的建议**: 初始推荐 Anthropic
- **用户决策**: 改为 DeepSeek
- **我的处理**: 在 AI 协助下添加了 DeepSeek 支持，同时保留了 Anthropic 作为可选方案

---

## 三、至少 3 轮关键迭代

### 迭代 1: 交互模式重构

**对话节选**:
```
智能体分析当前 Agent 交互模式存在的问题：
- 只能输出 JSON → 改为自然语言 + 内嵌 JSON 工具调用
- 每轮一个 JSON 动作 → 改为"边说边做，自动规划多步"
- task → done → 新 task → 改为"持续对话，始终记住上下文"
- 固定格式错误就死 → 改为"自然语言兜底，格式错误也能继续"
- 纯 CLI → 改为"CLI + WebUI（FastAPI + SSE 流式）"
```

**我的决策**: 同意这个重构方向。原来的 JSON-only 模式太脆弱，LLM 输出格式稍有偏差就导致整个 Agent 卡死。改为自然语言 + 内嵌 JSON 后，Agent 的鲁棒性显著提升。

**对 SPEC 的影响**: 修改了 ActionParser 的设计，从单一 JSON 解析变为多层 fallback（JSON block → standalone JSON → 自然语言代码块提取）。

### 迭代 2: DeepSeek 集成中的问题修复

**对话节选**:
```
Agent 跑起来了但连续失败 5 次。问题在于 DeepSeek 返回的内容格式 
ActionParser 解析不了。需要看看它实际返回了什么，然后修复。
```

**我的决策**: 让 AI 分析 DeepSeek 的实际输出格式，调整 ActionParser 的解析逻辑。

**对 SPEC 的影响**: 在 ActionParser 中增加了更宽松的 JSON 匹配模式，支持 JSON 代码块中的 tool 调用，以及自然语言中的代码块提取。

### 迭代 3: Docker 部署中的 keyring 问题

**对话节选**:
```
docker部署的网站显示:
Error: No recommended backend was available. 
Install a recommended 3rd party backend package; or, install the keyrings.alt package
```

**我的决策**: 让 AI 修复 SecretsManager，使其在 Docker 环境中优雅降级到环境变量。

**对 SPEC 的影响**: 更新了凭据存储方案，增加了 Docker 环境的 fallback 机制。在 `SecretsManager` 中增加了 keyring 不可用时的降级处理。

---

## 四、AI 提出而我采纳的建议

1. **治理系统的 pipeline 架构**: AI 提出的 DangerClassifier → PolicyEngine → HITL → ScopeFence → Sandbox 五层 pipeline 设计，每个子系统独立可测试，组合后形成完整防御链。这个设计非常清晰，我完全采纳。

2. **Mock LLM 的脚本模式 + 正则模式**: AI 设计了两种 Mock 模式，脚本模式用于端到端测试（按顺序返回预设响应），正则模式用于单个机制测试。这个设计使得测试既有灵活性又有确定性。

3. **TDD 分层实现策略**: AI 将实现分为 7 个 Tier，从基础设施到交付物，每个 Tier 先写测试再写实现。这个策略保证了代码质量。

4. **自然语言 + 内嵌 JSON 的交互模型**: AI 提出将 Agent 从纯 JSON 输出改为自然语言对话中嵌入 JSON 工具调用，大幅提升了可用性。

5. **WebUI 的 SSE 流式传输**: AI 建议用 FastAPI + SSE 实现实时流式输出，让用户可以看到 Agent 的每一步思考和执行。

6. **keyring 懒加载 + 环境变量 fallback**: 针对 Docker 部署问题，AI 将 keyring 改为懒加载，并在不可用时自动降级。

## 五、AI 提出而我推翻或修正的建议

1. **初始推荐 Anthropic 而非 DeepSeek**: AI 初始推荐 Anthropic Claude，但考虑到 DeepSeek 的性价比和中文支持，我要求改为 DeepSeek 作为默认供应商。

2. **测试中的本地路径断言**: AI 在 `test_custom_working_directory` 中写了 `"Liuyihe" in config.working_directory`，这在 GitHub Actions 的 Linux 环境会失败。我让 AI 改为跨平台的 `os.path.isabs()` 断言。

3. **初始的纯 JSON 交互模式**: AI 最初的设计是 Agent 只输出 JSON，但实际使用中发现 LLM 的 JSON 格式经常出现小偏差导致解析失败。我同意 AI 后续提出的自然语言 + 内嵌 JSON 方案。

---

## 六、冷启动验证

### 验证过程

使用 GitHub Actions 的 CI 环境作为"第二个智能体"的模拟——在一个全新的 Ubuntu 环境中，仅凭 SPEC.md + PLAN.md（即代码和测试），不提供任何额外上下文，运行全部测试。

### 暴露的问题

1. **`test_custom_working_directory` 使用了本地路径断言**: 测试中硬编码了 `"Liuyihe"` 用户名，在 CI 的 `/home/runner/...` 路径下失败。**修复**: 改为 `os.path.isabs()` 断言。

2. **keyring 在 Docker 中不可用**: 在无桌面环境的容器中，keyring 找不到后端。**修复**: 懒加载 keyring + 环境变量 fallback。

### 对 SPEC 的修订

- 在 SPEC §7.1 中增加了 Docker 环境 keyring 降级机制的说明
- 在 SPEC §11 中增加了"keyring 在 Docker 中不可用"的风险项
- 在测试中移除了所有平台特定的断言

---

## 七、反思：Brainstorming 技能的评价

### 做得好的地方

1. **主动追问设计决策**: 在进入实现之前，brainstorming 技能主动追问了语言、重点维度、分发方式、LLM 供应商四个关键决策，避免了后期返工。

2. **结构化呈现选项**: 对每个决策都给出了清晰的对比表格（优势/劣势），帮助快速理解 trade-off。

3. **Plan 分解颗粒度合理**: 每个 task 的粒度控制在 2-5 分钟，涉及文件明确，验证步骤具体。

### 不满的地方

1. **默认推荐偏保守**: 初始推荐 Anthropic 而非更经济的选择，没有主动询问用户的预算约束。

2. **对跨平台兼容性的关注不足**: 初始的测试代码写了平台特定的断言（如 Windows 用户名），在 CI 中暴露了问题。

3. **对 Docker 环境的考虑不充分**: keyring 在容器环境中的问题直到实际部署时才暴露，应该在设计阶段就考虑到。但这也反映了 AI 的一个普遍局限：它倾向于假设"完整桌面环境"，而实际部署往往是 headless 的。