# Build-MCP-Step-by-Step

这个仓库现在包含两部分内容：

- 一套从 `LLM -> Agent -> MCP -> Runtime -> Evaluation -> Production` 展开的长文型 notebook
- 一套最小但真实可运行的本地实现，用来证明这不是只有文稿，没有系统

## 当前项目结构

- `01-12_*.ipynb`
  - 解释整套系统的原理、结构、案例和工程化路径
- `server/`
  - 一个最小本地 MCP 风格 server
  - 通过 stdio 提供 `tools / resources / prompts`
- `runtime/`
  - 本地 `Ollama` 调用层
  - MCP client
  - 最小 agent runtime
- `examples/`
  - JD 样例
  - 候选人资料样例
- `demo/run_demo.py`
  - 端到端 demo 脚本

## 现在已经真实实现了什么

### 1. 最小 MCP 风格能力层

`server/mcp_server.py` 和 `server/capabilities.py` 现在已经真实暴露了三类能力：

- `tools`
  - `extract_key_requirements`
  - `score_candidate_fit`
  - `summarize_section`
- `resources`
  - `project://prd/main`
  - `project://case/jd_sample`
  - `project://case/candidate_profile`
- `prompts`
  - `map_candidate_to_jd`
  - `analyze_project_brief`

它不是完整 MCP SDK 实现，但已经保留了最关键的边界：
- 能力发现
- resource 读取
- prompt 获取
- tool 调用

### 2. 最小 Agent Runtime

`runtime/agent_runtime.py` 现在已经实现了一个最小闭环：

1. 读取 JD resource
2. 读取 candidate resource
3. 调用要求抽取工具
4. 调用匹配评分工具
5. 生成最终结构化结果

如果本地 `Ollama` 可用，模型会参与：
- 下一步动作规划
- 最终结果综合

如果本地模型不可用或输出结构损坏，runtime 会走 fallback 路径，确保：
- resource 链路能验证
- tool 链路能验证
- 状态推进能验证

### 3. 本地模型接入

`runtime/ollama_client.py` 通过 HTTP 调用本地 `Ollama`。

默认模型名写的是：

- `gpt-oss:120b`

如果你本地模型名不同，需要自己改 `demo/run_demo.py` 或 `runtime/ollama_client.py` 里的默认值。

## 运行方式

### 前提

你本地需要有：

- 已启动的 `Ollama`
- 可用模型，例如 `gpt-oss:120b`

### 运行 demo

```bash
python -B demo/run_demo.py
```

这个脚本会做的事情不是单纯调一次模型，而是：

1. 拉起本地 `server/mcp_server.py`
2. Runtime 通过 stdio 连接这个 server
3. 读取样例 resource
4. 调用本地 tool
5. 让模型参与规划和最终综合
6. 输出 trace 和最终结果

## 当前实现的定位

这套实现现在的定位是：

- 它已经不是纯文稿
- 但它也还不是完整生产级 MCP 系统

更准确地说，它是一个“最小真实闭环”：

- 有真实 server
- 有真实 runtime
- 有真实 resource / tool / prompt
- 有真实 demo

但还没有做重的部分，例如：

- 完整 MCP SDK 接入
- 更复杂的多任务状态治理
- 更严格的权限控制
- 完整测试体系
- 更成熟的错误恢复和评估框架实现

## 这套项目真正要展示什么

这个仓库想证明的不是“会不会调用 API”，而是：

- 理解大模型为什么会表现出任务性
- 理解 Agent 不等于聊天机器人
- 理解 MCP 不是工具清单，而是能力层
- 知道 runtime 才是系统中枢
- 能把这些理解真正落成一个最小可运行原型

如果后面继续扩，这个仓库最自然的方向是：

- 把当前最小 MCP 风格 server 换成正式 MCP SDK 实现
- 增加更多资源、工具和 prompt
- 把 demo 提升成更完整的案例与评估链
- 补测试、trace 和版本治理
