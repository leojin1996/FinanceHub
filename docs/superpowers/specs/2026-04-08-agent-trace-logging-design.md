# Recommendation Agent Trace Logging 设计

Date: 2026-04-08
Topic: recommendation agents 请求与回答日志跟踪
Design status: Drafted for review
Decision status: Chosen approach = runtime 主日志 + provider 补充阶段日志

## 1. 背景与问题

当前 recommendation agent 链路已经支持：

- 按 agent 维度选择不同的 Claude 模型
- provider 结构化解析与 fallback
- 原始响应 capture 到本地忽略目录

但日常排障时，开发者仍然很难在常规后端日志里直接回答这些问题：

- 这一次 recommendation 请求里，哪些 agent 实际发起了调用
- 每个 agent 用了哪个模型
- 每个 agent 的请求耗时大概是多少
- 每个 agent 最终返回了什么结构化对象
- 某个阶段失败时，是 agent 自己失败、provider 失败，还是 structured/fallback 阶段切换导致

现在若要排查这些问题，通常需要：

- 读代码推断 agent 顺序
- 打开 raw capture 文件人工比对
- 结合 warning 或异常信息猜测阶段

这对本地开发排障来说偏重，也不适合直接在 [backend-8000.log](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/tmp/run-logs/backend-8000.log) 中快速查看。

## 2. 目标

本次设计目标是：

- 为 6 个 recommendation runtime agent 增加请求开始、请求结束、请求失败日志
- 在日志中明确记录 `request_name`、`model_name`、耗时与裁剪后的结构化回答摘要
- 在 provider 层补充 structured/fallback 阶段日志，帮助定位低层问题
- 让日志默认在本地开发与测试路径可用，在生产环境可明确关闭
- 保持改动范围小，不改 orchestration 语义、不改 agent prompt、不改 response schema

6 个跟踪目标如下：

1. `user_profile`
2. `market_intelligence`
3. `fund_selection`
4. `wealth_selection`
5. `stock_selection`
6. `explanation`

## 3. 非目标

本次设计不包括：

- 记录完整 prompt 文本
- 记录完整 provider 原始响应到常规后端日志
- 替代现有 raw capture 机制
- 引入新的日志基础设施或第三方 observability 依赖
- 更改 recommendation 的执行路径、降级策略或 agent 输出契约

## 4. 选择的方案

本次采用“runtime 主日志 + provider 补充阶段日志”的方案。

具体分层如下：

- [anthropic_runtime.py](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/financehub_market_api/recommendation/agents/anthropic_runtime.py)
  - 记录每个 agent 的开始、结束、错误日志
  - 这是开发者最关心的语义层
- [provider.py](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/financehub_market_api/recommendation/agents/provider.py)
  - 只补 structured/fallback 阶段、底层异常等必要日志
  - 不在 provider 层重复打印完整的业务成功日志

不选择“只在 provider 层打日志”的原因：

- provider 只知道请求，不天然代表 recommendation 语义中的 agent 阶段
- 对开发者来说，不够直观

不选择“只在 runtime 层打日志”的原因：

- structured/fallback 切换、provider 低层错误仍然不够透明

选中方案的原则是：

- 主要信息在 runtime 层看得懂
- 关键低层细节在 provider 层补得上
- 避免双层都打印完整 payload 造成噪音

## 5. 日志开关设计

### 5.1 显式环境变量

新增环境变量：

- `FINANCEHUB_LLM_AGENT_TRACE_LOGS`

解析规则：

- `true/1/yes/on` -> 开启
- `false/0/no/off` -> 关闭

### 5.2 默认策略

为避免运行时猜测环境，本次实现采用明确但稳定的策略：

- 代码默认值为关闭
- 本地开发通过 [backend/.env.local](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/.env.local) 显式开启
- 测试中按需显式开启
- 生产环境若未配置该变量，则保持关闭

这样虽然不是“运行时自动判断 dev/test/prod”，但在实际效果上达成：

- dev/test 开
- prod 关

同时避免：

- 依赖 `PYTEST_CURRENT_TEST`
- 依赖当前目录或文件是否存在
- 靠 `.env.local` 是否被扫描到来隐式改变行为

## 6. Runtime 层日志设计

### 6.1 记录位置

在 [anthropic_runtime.py](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/financehub_market_api/recommendation/agents/anthropic_runtime.py) 的 `_BaseStructuredOutputAgent._execute()` 中加日志。

原因：

- 这里天然拿得到 `request_name`
- 这里天然拿得到最终选定的 `model_name`
- 这里能覆盖所有 6 个 agent
- 这里已经是“结构化请求”边界，最适合记录成功/失败语义

### 6.2 开始日志

在发起 provider 请求前记录一条：

- event: `agent_request_start`
- `request_name`
- `model_name`

示例：

```text
agent_request_start request_name=market_intelligence model_name=claude-opus-4-6-thinking
```

### 6.3 结束日志

在收到并成功返回结构化对象后记录一条：

- event: `agent_request_finish`
- `request_name`
- `model_name`
- `duration_ms`
- `response_summary`

示例：

```text
agent_request_finish request_name=market_intelligence model_name=claude-opus-4-6-thinking duration_ms=842 response_summary={"summary_zh":"市场整体偏稳，关注估值与流动性。","summary_en":"Market remains broadly stable; watch valuation and liquidity."}
```

### 6.4 错误日志

在 provider 或解析阶段抛错时记录：

- event: `agent_request_error`
- `request_name`
- `model_name`
- `duration_ms`
- `error_type`
- `error_message`

示例：

```text
agent_request_error request_name=market_intelligence model_name=claude-opus-4-6-thinking duration_ms=842 error_type=LLMProviderError error_message="structured-output provider request failed: ..."
```

## 7. 回答摘要裁剪设计

### 7.1 目标

日志应帮助排障，但不能把日志文件刷爆。

因此 runtime 成功日志不打印完整原始响应，也不无上限打印完整解析后 JSON，而是打印裁剪版 `response_summary`。

### 7.2 裁剪规则

建议对解析后对象做浅到中度裁剪：

- 字符串超过固定长度时截断，例如保留前 160 字符
- 列表最多保留前 5 项
- 嵌套对象最多保留前若干键
- 超出部分用明确占位，例如：
  - `"...(truncated)"`
  - `["item1", "item2", "...(truncated)"]`

### 7.3 保留原则

保留：

- 顶层键名
- 短字符串字段
- 排序类结果中的前几个 ID
- explanation / summary 的前一段内容

不保留：

- 超长文本全文
- 大数组完整内容
- 无限制嵌套对象

## 8. Provider 层补充日志设计

在 [provider.py](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/financehub_market_api/recommendation/agents/provider.py) 中补充必要但克制的阶段日志。

### 8.1 结构化阶段失败

当 structured 请求返回不可解析结果并准备 fallback 时，记录：

- event: `provider_structured_invalid`
- `request_name`
- `model_name`
- `error_message`

### 8.2 fallback 成功

当 fallback 请求成功解析时，记录：

- event: `provider_fallback_success`
- `request_name`
- `model_name`

### 8.3 fallback 失败

当 structured 与 fallback 都失败时，记录：

- event: `provider_fallback_invalid`
- `request_name`
- `model_name`
- `error_message`

provider 层不重复打印完整 `response_summary`，避免和 runtime 层成功日志重复。

## 9. 日志实现方式

本次不引入新依赖，直接使用标准库 `logging`。

建议：

- 模块级 logger，例如 `logging.getLogger(__name__)`
- 使用 `logger.info(...)` 记录开始/结束
- 使用 `logger.warning(...)` 或 `logger.exception(...)` 记录错误与 fallback

日志保持单行、结构化文本风格，方便直接在后端运行日志中 grep。

## 10. 测试设计

测试以相关单元测试为主，集中放在：

- [test_recommendation_provider.py](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/tests/test_recommendation_provider.py)
- 需要时新增或补充 runtime 测试文件

至少覆盖：

1. 开关关闭时不打日志
2. 开关开启时 runtime 成功日志包含：
   - `request_name`
   - `model_name`
   - `duration_ms`
   - `response_summary`
3. 开关开启时 runtime 错误日志包含：
   - `error_type`
   - `error_message`
4. `response_summary` 被裁剪，不会原样输出超长内容
5. provider structured -> fallback 路径会输出阶段日志

测试中优先使用 `caplog` 断言日志内容，而不是依赖真实日志文件。

## 11. 验证方式

本次实现后的验证顺序：

1. 相关单元测试
2. [backend](/Users/zefengjin/Desktop/Practice/FinanceHub/backend) 下 `python3 -m pytest -q`
3. 重启后端服务
4. 实际调用 recommendation 接口
5. 检查 [backend-8000.log](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/tmp/run-logs/backend-8000.log) 中是否能看到 6 个 agent 的开始/结束或错误日志

## 12. 风险与约束

主要风险：

- 若摘要裁剪不当，日志仍可能过大
- 若错误日志直接透传原异常，可能出现过长错误文本
- 若 provider 与 runtime 双层日志都过多，可能造成重复噪音

缓解方式：

- 统一裁剪策略
- provider 层只记阶段信息，不打印完整响应摘要
- runtime 层作为主要成功日志出口

## 13. 实现范围收口

本次实现限定为：

1. 增加 LLM agent trace 日志开关
2. 在 runtime 层补开始/结束/错误日志
3. 在 provider 层补 structured/fallback 阶段日志
4. 增加裁剪摘要工具函数
5. 增加相关测试与实际日志验证

不顺手改动：

- recommendation 编排逻辑
- prompt 文本
- provider capture 文件格式
- API 响应 schema
