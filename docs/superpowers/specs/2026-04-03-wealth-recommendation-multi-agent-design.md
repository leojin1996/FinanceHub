# FinanceHub 理财推荐页多智能体设计方案

Date: 2026-04-03
Topic: FinanceHub 个性化理财产品推荐页的多智能体系统设计
Design status: Drafted for review
Decision status: Chosen approach = 规则内核 + 智能体外壳

## 1. 背景与目标

FinanceHub 已具备市场数据、股票/指数展示、风险评估、个性化推荐等产品方向。本设计聚焦其中的“理财产品推荐页”，目标是在单一页面内完成：

- 用户风险与偏好理解
- 跨品类资产配置建议
- 基金、银行理财、股票三类资产的选品推荐
- 风险控制与合规提示
- 推荐理由的可解释输出

该页面不是简单的榜单页，而是“资产配置 + 选品一体”的投顾式结论页。

## 2. 设计边界

### 2.1 已确定边界

- 推荐服务对象：推荐页单页能力
- 推荐范围：基金 + 银行理财 + 股票
- 页面定位：先做资产配置，再做具体选品
- 约束强度：中约束
  - 主推荐方案严格遵守风险边界
  - 允许少量进取型备选方案
- 用户输入：风险测评 + 基础问卷 + 历史持仓/交易记录

### 2.2 非目标

本设计暂不包括：

- 全量生产级合规系统
- 高频实时行情驱动的秒级推荐
- 多轮聊天式追问推荐
- 自学习闭环与在线 A/B 测试
- 完整的投资组合回测体系

## 3. 核心设计原则

### 3.1 风险边界必须规则化

以下内容必须由规则或代码控制，而不是由 LLM 自由判断：

- 用户风险等级与产品风险等级匹配
- 股票上限、权益敞口上限
- 银行理财最低配置比例
- 高回撤、高波动产品剔除逻辑
- 合规提示与禁推条件

### 3.2 智能体负责理解与解释，规则负责裁决

适合由智能体处理：

- 用户画像归纳
- 市场环境总结
- 候选解释与排序辅助
- 推荐理由生成

适合由规则处理：

- 风险映射
- 资产配置边界
- 产品准入与过滤
- 合规审查
- 流程回退条件

### 3.3 推荐顺序必须是“先配大类，再选产品”

对基金、银行理财、股票三类资产，推荐流程必须遵循：

1. 用户画像分析
2. 市场环境分析
3. 资产配置生成
4. 分品类选品
5. 风控审核
6. 推荐说明生成

### 3.4 页面展示应结论优先

推荐页应采用如下顺序组织内容：

1. 推荐结论
2. 配置比例
3. 分品类推荐
4. 为什么这么配
5. 进取型备选
6. 风险提示

## 4. 总体架构

推荐系统采用“三层架构 + 编排协调器”。

### 4.1 输入理解层

作用：将用户输入与历史行为转成结构化用户画像。

输入：

- 风险测评结果
- 基础问卷
- 历史持仓
- 历史交易记录

输出：

- `UserProfile`

### 4.2 推荐决策层

作用：根据用户画像和市场环境，确定资产配置并生成候选池。

输入：

- `UserProfile`
- `MarketContext`
- 产品库与市场数据

输出：

- `AllocationPlan`
- `CandidatePool`

### 4.3 合规输出层

作用：统一审查推荐结果，并生成页面可消费的最终结果。

输入：

- `AllocationPlan`
- `CandidatePool`
- 风控规则

输出：

- `RiskReviewResult`
- `FinalRecommendation`

### 4.4 协调器

作用：负责编排整个流程、维护状态、执行回退策略与收口最终响应。

建议使用：

- 第一版：普通后端 orchestration service
- 后续升级：LangGraph-friendly state workflow

## 5. 智能体与模块拆分

## 5.1 协调器 Coordinator

职责：

- 统一编排推荐流程
- 维护全局状态
- 调用智能体与规则模块
- 处理失败回退与降级

实现方式：

- 不建议使用 LLM
- 应使用状态机或服务编排

## 5.2 用户画像智能体

职责：

- 解析风险测评、问卷、历史行为
- 提取风险偏好、流动性偏好、期限偏好、行为标签
- 输出结构化画像摘要

输入：

- 风险等级/分数
- 问卷结果
- 历史持仓
- 历史交易

输出示例：

```json
{
  "risk_level": "R3",
  "liquidity_preference": "medium",
  "investment_horizon": "1y_3y",
  "return_preference": "balanced",
  "loss_tolerance": "medium",
  "behavior_tags": ["prefers_fixed_income", "low_turnover"],
  "profile_confidence": "medium",
  "persona_summary": "用户偏稳健增值，能接受有限波动。"
}
```

实现原则：

- 用 LLM 做归纳与标签提取
- 不允许 LLM 越权修改风险边界
- 历史数据不足时回退为保守画像

## 5.3 市场情报智能体

职责：

- 将市场数据压缩成推荐可用的市场标签
- 形成对权益、固收、风格偏好的摘要

输入：

- 指数表现
- 利率/流动性环境
- 板块或风格特征
- 外部市场数据源

输出示例：

```json
{
  "market_regime": "defensive",
  "equity_sentiment": "neutral",
  "fixed_income_sentiment": "positive",
  "preferred_fund_styles": ["bond_fund", "balanced_fund"],
  "preferred_stock_styles": ["large_cap", "dividend"],
  "market_summary": "当前市场更适合稳健配置，权益资产适合小比例参与。"
}
```

实现原则：

- 市场原始数据必须来自工具或 repository
- LLM 只负责总结，不负责编造事实
- 数据缺失时允许回退到 neutral 标签

## 5.4 资产配置规则引擎

职责：

- 结合用户画像和市场上下文，确定基金/银行理财/股票的大类比例
- 生成主推荐方案和进取型备选方案
- 施加股票上限、权益敞口、流动性等约束

输入：

- `UserProfile`
- `MarketContext`
- 业务策略参数

输出示例：

```json
{
  "base_plan": {
    "fund": 0.45,
    "wealth_management": 0.40,
    "stock": 0.15
  },
  "aggressive_option": {
    "fund": 0.40,
    "wealth_management": 0.30,
    "stock": 0.30
  },
  "constraints": {
    "stock_max": 0.20,
    "equity_exposure_max": 0.35,
    "wealth_management_min": 0.25
  },
  "allocation_reasoning": [
    "用户风险等级为R3",
    "历史行为偏稳健",
    "当前市场偏防守",
    "因此主方案以基金和银行理财为主"
  ]
}
```

实现原则：

- 不建议使用 LLM
- 应实现为规则表 + 策略函数
- 必须可测试、可回放、可解释

## 5.5 品类选品智能体组

建议拆分三个独立子模块。

### 5.5.1 基金选品智能体

职责：

- 在基金池中筛选与排序
- 输出基金候选和理由

实现方式：

- 先规则筛选 / 检索生成候选池
- 再用 LLM 生成解释与排序辅助

### 5.5.2 银行理财选品智能体

职责：

- 在理财产品池中按风险等级、期限、流动性筛选
- 输出稳健类候选与解释

实现方式：

- 以结构化规则筛选为主
- LLM 主要负责解释文案

### 5.5.3 股票选股智能体

职责：

- 在受限预算下筛选低于风险边界的股票候选
- 输出增强型股票建议

实现方式：

- 必须受到资产配置上限和风控双重约束
- 页面上始终定位为“增强配置”，而非主推荐

## 5.6 合规风控模块

职责：

- 对候选结果做统一审查
- 驳回超出风险边界的候选
- 决定是否需要重选或降级输出
- 生成面向用户的风险提示

输出示例：

```json
{
  "approved": true,
  "review_status": "partial_pass",
  "removed_candidates": [
    {
      "product_id": "stock_009",
      "reason_code": "volatility_too_high",
      "reason_text": "波动超出当前用户适配范围"
    }
  ],
  "warnings": [
    "股票部分仅适合作为增强配置",
    "理财非存款，净值可能波动"
  ],
  "review_summary": "主推荐结果符合当前用户风险承受能力。"
}
```

实现原则：

- 规则决定 pass / reject / retry
- LLM 仅用于把审查结果翻译成用户可理解语言

## 5.7 推荐说明智能体

职责：

- 将最终结构化结果转成推荐页可展示文案
- 统一“为什么这么配”“为什么推这些产品”“风险提示”等说明

实现原则：

- 必须基于前序结构化状态生成
- 不允许新增事实或虚构收益信息

## 6. 状态流设计

推荐系统应维护统一全局状态。

### 6.1 全局状态结构

```json
{
  "request_context": {},
  "user_profile": {},
  "market_context": {},
  "allocation_plan": {},
  "candidate_pool": {
    "funds": [],
    "wealth_management": [],
    "stocks": []
  },
  "risk_review": {},
  "final_recommendation": {},
  "execution_trace": []
}
```

### 6.2 主流程

1. 输入标准化
2. 用户画像生成
3. 市场上下文生成
4. 资产配置生成
5. 分品类选品
6. 风控审核
7. 推荐说明生成
8. 返回页面结果

### 6.3 回退策略

仅建议保留有限回退：

- 用户历史不足：回退到保守画像，不中断流程
- 单一品类不合规：只回退对应选品器重试 1~2 次
- 整体无法形成合规方案：降级为基金 + 理财主方案，或仅返回配置建议

## 7. 数据模型建议

建议建立统一领域模型：

- `UserProfile`
- `MarketContext`
- `AllocationPlan`
- `CandidateProduct`
- `RiskReviewResult`
- `FinalRecommendation`

### 7.1 CandidateProduct 统一骨架

不论基金、理财、股票，建议统一外层字段：

- `product_id`
- `name`
- `category`
- `risk_level`
- `liquidity`
- `match_score`
- `reason_tags`
- `metrics`
- `category_specific`

这样前端和风控层都能以统一方式消费数据。

## 8. 推荐页交互设计

推荐页应定位为“投顾结论页”，而非聊天页或排行榜页。

### 8.1 建议页面区块

1. 页面头部：个性化推荐说明
2. 核心配置结论：一句话总结 + 风险等级匹配说明
3. 资产配置图：基金/理财/股票比例与角色说明
4. 推荐清单：按品类分组展示候选
5. Why This Plan：解释推荐依据
6. 进取型备选：默认折叠展示
7. 风险提示：固定区块

### 8.2 页面展示原则

- 先结论，后解释
- 先资产配置，后标的推荐
- 股票区权重低于基金和银行理财
- 不展示 agent 群聊过程，只展示多维分析结论

## 9. 后端模块边界

建议新增独立推荐能力域，例如：

- `backend/financehub_recommendation/`

内部建议拆分：

- `domain/`：领域模型
- `agents/`：LLM 参与模块
- `rules/`：风险与配置规则
- `services/`：业务编排服务
- `repositories/`：数据访问层
- `schemas/`：API request/response DTO
- `orchestration/`：流程编排与 trace

### 9.1 哪些是 agent

- 用户画像理解
- 市场上下文理解
- 推荐解释生成
- 候选排序辅助

### 9.2 哪些不是 agent

- 数据拉取
- 风险边界
- 资产配置硬约束
- 合规裁决
- 主流程编排

## 10. 外部数据接入策略

已知可参考的数据能力：

- `https://github.com/chenditc/investment_data`

建议其在系统中作为“数据供给层/适配层”，而不是推荐逻辑本身。

### 10.1 建议接入方式

通过 adapter 或 repository 包装外部数据：

- `investment_data_market_adapter`
- `investment_data_fund_adapter`
- `investment_data_stock_adapter`

作用：

- 获取外部数据
- 清洗并映射为系统内部统一模型
- 隔离外部字段变化对推荐系统的影响

### 10.2 原则

- 不允许在智能体内直接调用原始数据接口
- 外部数据必须先结构化，再进入 agent / rule / service 层

## 11. API 设计建议

推荐页建议只依赖一个核心接口：

- `POST /api/recommendations/generate`

### 11.1 请求示例

```json
{
  "user_id": "u_123",
  "risk_assessment_id": "ra_001",
  "include_aggressive_option": true
}
```

### 11.2 响应示例

```json
{
  "summary": {
    "title": "适合您的稳健增值配置建议",
    "subtitle": "以基金和银行理财为主，配少量股票增强收益弹性"
  },
  "profile_summary": "您整体属于中低风险偏好，重视稳健增值与资金安全。",
  "market_summary": "当前市场更适合以稳健资产打底，权益类资产小比例参与。",
  "allocation_display": {
    "fund": 45,
    "wealth_management": 40,
    "stock": 15
  },
  "sections": {
    "funds": [],
    "wealth_management": [],
    "stocks": []
  },
  "aggressive_option": {},
  "risk_notice": [],
  "why_this_plan": []
}
```

原则：

- 前端只负责展示，不负责二次决策
- 后端直接返回页面可渲染对象

## 12. 关键风险点

### 12.1 不要把推荐做成“会说话的筛选器”

系统必须保留：

- 用户画像
- 市场上下文
- 资产配置

否则多智能体价值会退化为文案包装。

### 12.2 不要把风控交给 LLM

LLM 只负责解释，规则负责拍板。

### 12.3 不要让股票模块带偏整个页面

股票应始终定位为：

- 小比例增强
- 风险更高
- 视觉权重更低

### 12.4 不要在第一版接入过多实时数据源

第一版目标应是跑通闭环，而不是追求最全和最快。

### 12.5 不要为了多智能体而强行上复杂图编排

设计上保持 LangGraph-friendly 即可，第一版实现可先使用普通 orchestration service。

## 13. 分阶段落地建议

### 阶段 1：闭环 MVP

目标：跑通“可解释的推荐闭环”。

包含：

- 风险测评 + 问卷 + 历史行为输入
- 用户画像智能体
- 市场情报智能体
- 资产配置规则引擎
- 三个品类选品器
- 风控审核器
- 推荐说明生成器
- 推荐页完整渲染结果

### 阶段 2：推荐质量增强

增强方向：

- 更多行为特征
- 更细市场风格识别
- 更复杂的产品打分与排序
- 更丰富的解释模板
- 用户反馈反哺画像

### 阶段 3：推荐中台化

增强方向：

- 抽成统一 recommendation domain
- 扩展资产类别
- 引入离线评估与效果分析
- 逐步升级为图编排或更复杂多智能体系统

## 14. 最终结论

FinanceHub 推荐页应构建为一个：

**规则主导、智能体协作、结果可解释的跨品类资产配置推荐系统。**

其核心实现方式为：

- 用智能体做理解、总结、解释、排序辅助
- 用规则做风险边界、资产配置、准入与合规
- 用协调器做状态流编排与有限回退
- 用推荐页做结论优先的投顾式展示

这将使系统既具备多智能体带来的分析深度，又保持金融推荐场景所需的稳定性、可测性与可信度。
