# Anthropic 响应采样与结构化解析设计

Date: 2026-04-07
Topic: Anthropic recommendation agents 的真实响应采样、结构化对象提取与测试覆盖
Design status: Drafted for review
Decision status: Chosen approach = 分层提取 + 真实采样 + 脱敏 fixture

## 1. 背景与问题

当前推荐智能体运行时通过 [provider.py](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/financehub_market_api/recommendation/agents/provider.py) 的 `AnthropicChatProvider.chat_json()` 调用 Anthropic Messages API。

现状问题在于：

- provider 先尝试 `output_config.format=json_schema`
- 若结构化响应不可用，再回退到不带 `output_config` 的普通请求
- 解析层目前只接受 `body["content"]` 中 `type == "text"` 的 block
- 之后仅从 `text` 字符串中提取 JSON 对象

因此，只要真实 provider 返回的最终对象没有落在这一条窄路径上，就会触发：

- `provider response has no content blocks`
- `provider response has no text content block`
- `provider returned invalid JSON content`

这类错误并不一定代表 provider 没有返回可用对象，更可能是本地解析假设过窄。

## 2. 目标

本设计的目标是：

- 扩大 Anthropic provider 响应的结构化对象提取覆盖面
- 保留当前 recommendation runtime 的降级与容错语义
- 通过真实调用 6 个 runtime agent 采样返回体，避免纯猜测式兼容
- 将真实返回体转成可提交的脱敏 fixture，用于稳定回归测试
- 让原始响应采集默认关闭，仅在显式开启时写入本地忽略目录

## 3. 非目标

本次设计不包括：

- 改写 recommendation orchestration 架构
- 调整 agent prompt 或 agent 顺序
- 引入新的 LLM provider
- 变更规则引擎、候选池逻辑或前端展示
- 将原始响应采集默认接入生产常规路径

## 4. 设计边界

本次实现范围限定为四部分：

1. provider 响应提取管线增强
2. 原始响应采集开关与本地落盘
3. 六个 runtime agent 的真实采样入口
4. 基于脱敏样本的测试补强

六个采样目标如下：

1. `user_profile`
2. `market_intelligence`
3. `fund_selection`
4. `wealth_selection`
5. `stock_selection`
6. `explanation`

## 5. 选择的方案

本次采用“分层提取 + 真实采样 + 脱敏 fixture”方案。

不采用“只补 text 正则”的原因：

- 改动虽小，但覆盖范围仍然依赖文本包装形式
- 无法系统应对真实 provider 的 block/type 差异

不采用“全量递归扫描后拿到任意 dict 就接受”的原因：

- Anthropic Messages 响应包含多种 block 结构
- 若直接接受任意对象，容易把中间对象或无关 payload 误判为 agent 输出

选中方案的原则是：

- 先走高置信提取路径
- 失败后再扩大搜索范围
- 即便扩大搜索，也必须由当前 agent 的目标 schema 收口
- 对真实返回形态以采样结果为准，而不是凭经验硬编码全部格式

## 6. Provider 解析设计

### 6.1 请求路径保持不变

`chat_json()` 保留现有双阶段请求策略：

1. 先发送带 `output_config.format=json_schema` 的请求
2. 若响应无法提取出可用对象，再发送普通 messages 请求

这能继续兼容支持 structured output 和不稳定 structured output 的网关实现。

### 6.2 从“单点解析”改为“候选提取管线”

provider 的响应解析改成按层次提取候选对象。

第一层是高置信路径：

- `content[]` 中 `type == "text"` 的 `text`
- markdown fenced JSON
- 文本中的嵌入式 JSON 对象

第二层是返回体候选扫描：

- 递归遍历整个 provider 响应体
- 收集所有 dict 形态的候选对象
- 不在扫描阶段直接认定任何候选为最终结果

第三层是 schema 匹配：

- 根据当前 `response_schema` 或由其提取出的必需字段集合筛选候选对象
- 仅接受满足当前 agent 输出形状的对象

例如：

- `UserProfileAgentOutput` 需要 `profile_focus_zh` 与 `profile_focus_en`
- `MarketIntelligenceAgentOutput` 需要 `summary_zh` 与 `summary_en`
- `ProductRankingAgentOutput` 需要 `ranked_ids`
- `ExplanationAgentOutput` 需要 `why_this_plan_zh` 与 `why_this_plan_en`

### 6.3 匹配与歧义规则

候选对象判定规则如下：

- 若没有候选匹配当前 schema，返回 `LLMInvalidResponseError`
- 若只有一个候选匹配当前 schema，接受该对象
- 若有多个候选同时匹配，视为歧义响应，返回更具体的 `LLMInvalidResponseError`

实现上应优先保留“高置信路径优先”的顺序，即便后续递归扫描也不应打乱优先级。

### 6.4 错误语义

推荐使用更具体的错误消息，但保留 `LLMInvalidResponseError` 这一异常类型，以免破坏 runtime 降级路径。

建议错误语义：

- `provider response has no extractable structured content`
- `provider response contains multiple schema-matching objects`
- `provider response is not valid JSON`

现有空响应语义仍需兼容，因为 runtime 已把这类错误映射为清晰的降级 warning。

## 7. 原始响应采集设计

### 7.1 开关

新增显式环境变量开关，例如：

- `FINANCEHUB_LLM_CAPTURE_RAW_RESPONSES=1`

默认关闭。不开启时，不写任何原始响应文件。

### 7.2 采集内容

每次 provider 请求在收到 `response.json()` 后，保存以下上下文：

- agent 名称
- 模型名
- 请求阶段：`structured` 或 `fallback`
- 时间戳
- 原始 response body

若请求在 HTTP 层失败，则不生成伪造 body 文件。

### 7.3 落盘位置

原始响应写入本地忽略目录，例如：

- [backend/tmp/llm-captures/](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/tmp/llm-captures/)

文件命名建议为：

- `YYYY-MM-DDTHHMMSS-user_profile-structured.json`
- `YYYY-MM-DDTHHMMSS-user_profile-fallback.json`

目录应加入 `.gitignore`，避免原始 provider 返回体进入仓库。

## 8. 真实采样入口设计

需要新增一个仅用于开发验证的入口，用来逐个调用 6 个 runtime agent。

该入口的职责是：

- 构造最小可运行的 agent 输入
- 依次执行六个 agent
- 在采集开关开启时落盘原始响应
- 输出每个 agent 的解析结果或错误摘要

该入口不进入生产主路径，也不改变 recommendation service 的默认行为。

优先选择：

- 仓库内单独脚本，或
- 一个明确标记为开发采样用途的 pytest/CLI 入口

无论采用哪种形式，都应保证开发者可以单独运行，不与常规单元测试混跑。

## 9. 脱敏 Fixture 设计

### 9.1 目标

将真实采样得到的响应体转成稳定、可提交、可回归的测试样本。

### 9.2 存放位置

建议放在：

- [backend/tests/fixtures/anthropic_responses/](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/tests/fixtures/anthropic_responses/)

### 9.3 保留与替换原则

保留：

- content block 结构
- block type
- 与结构化提取相关的字段层级
- 能复现解析行为的文本内容

替换或移除：

- request id
- 账号标识
- 可能出现的敏感元数据
- 不稳定时间戳
- 无关且噪声较大的追踪字段

脱敏后的样本应最大程度保留“形状”，而不是只保留最终 JSON 文本。

## 10. 测试设计

测试按三层补齐。

### 10.1 Provider 单元测试

在 [test_recommendation_provider.py](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/tests/test_recommendation_provider.py) 中补充：

- 高置信文本提取仍然可用
- 递归扫描能从真实返回体形状中找到目标对象
- 候选对象不匹配当前 schema 时不会误判成功
- 多个候选同时匹配时会报歧义错误
- 原始响应采集开关关闭时不落盘
- 原始响应采集开关开启时会写入本地文件

### 10.2 Fixture 回归测试

增加针对脱敏真实样本的测试，验证六个 agent 各自都能从采样响应中提取出目标对象。

这部分测试应覆盖：

- `user_profile`
- `market_intelligence`
- 三个 ranking agent
- `explanation`

### 10.3 Runtime 保底测试

保留并按需调整现有 runtime/orchestration 测试，确保：

- `LLMInvalidResponseError` 仍按既有方式降级
- 空响应 warning 仍然可识别
- ranking agent 的非阻断降级不被新解析逻辑破坏

## 11. 兼容性与风险控制

### 11.1 兼容性

本次不改变：

- `AnthropicMultiAgentRuntime` 的 agent 顺序
- 现有 provider 配置环境变量
- recommendation orchestration 的主流程
- 规则回退语义

### 11.2 风险

主要风险有两类：

1. 递归扫描过宽，误命中非最终对象
2. 原始响应采集污染仓库或泄露敏感字段

对应控制方式：

- 必须以 schema 匹配收口，不接受任意 dict
- 歧义时报错而不是猜测
- 原始响应仅写入 git 忽略目录
- 提交到仓库的仅是脱敏 fixture

## 12. 验证计划

实现完成后按以下顺序验证：

1. 运行 provider 相关测试
2. 运行 recommendation flow/runtime 相关测试
3. 开启采集开关，真实调用 6 个 agent
4. 基于真实返回体补齐或修正 fixture
5. 再次运行针对性测试，确认解析与降级行为一致

## 13. 本次实现收口

本次实现应严格收口到以下交付物：

- provider 分层提取逻辑
- 原始响应采集开关
- 6 个 agent 的真实采样入口
- 脱敏 fixture
- 解析与降级相关测试

本次不顺带重写 prompt、runtime 结构或规则引擎。
