# FinanceHub 合规知识 RAG 设计方案

Date: 2026-04-13
Topic: FinanceHub 推荐链路中的合规规则 / 适当性 / 风控知识检索增强
Design status: Drafted for review
Decision status: Chosen approach = 混合判定型（公开监管规则优先 + 静态规则 fallback）

## 1. 背景与目标

FinanceHub 现有推荐 graph 已完成“产品资料 / 基金公告 / 理财说明书”知识检索接入，但合规审核部分仍主要依赖写死在代码中的静态规则。当前静态规则能完成基础风险等级与流动性判断，却缺少以下能力：

- 基于公开监管规则与官方指引的可追溯依据
- 更细粒度的适当性准入和期限约束
- 规则更新时无需频繁改代码的知识更新路径
- 对 `approve / revise_conservative / block` 的依据化输出

本设计的目标是在现有 recommendation graph 内新增第二条知识线：`合规知识 RAG`。该知识线面向 `compliance_risk_officer` 节点，优先检索公开监管规则 / 官方指引，再由 agent 结合命中的规则依据给出审核结论；当知识检索不可用时，自动回退到现有静态规则。

## 2. 已确认边界

### 2.1 第一阶段覆盖范围

第一阶段优先覆盖以下三类知识：

- 风险等级匹配 / 适当性准入
- 流动性 / 封闭期 / 期限约束
- 风险揭示 / 披露文案 / 人工复核提示

### 2.2 知识来源

- 公开监管规则 / 官方指引为主
- 内部规则作为补充，但第一阶段不做内部规则前端展示

### 2.3 运行方式

- 检索结果只供后台审核节点使用
- 第一阶段不向前端返回合规知识引用
- 当前静态规则保留，用作 fallback

### 2.4 非目标

本设计暂不包括：

- 前端展示监管规则引用
- 内部制度对终端用户可见
- 完整的规则引擎 DSL
- 合规知识问答页
- 全量产品禁售白黑名单平台化

## 3. 当前实现问题

现有静态规则主要位于 [backend/financehub_market_api/recommendation/compliance/service.py](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/financehub_market_api/recommendation/compliance/service.py)。核心问题包括：

- 条款覆盖面较窄，主要集中在风险等级和低风险用户流动性约束
- 风险等级映射、流动性标签、`90天` 阈值等均为硬编码
- `ComplianceFactsService` 虽支持 `rule_snapshot` 概念，但默认仍是占位结构
- `ComplianceReviewResult` 虽支持 `block`，但静态规则几乎只产出 `revise_conservative`
- `lockup_days`、`max_drawdown_percent` 已进入 facts，但未被静态规则充分消费

因此，当前静态规则适合作为兜底 guardrail，不适合作为主要的合规依据系统。

## 4. 方案比较

### 4.1 方案一：证据增强型

保留静态规则为主，只在 `compliance_risk_officer` 前补充合规知识检索，知识库只负责提供解释和披露文案建议。

优点：

- 改动最小
- 上线快
- 风险低

缺点：

- 最终判定仍主要依赖硬编码
- 合规知识更多是说明性证据，而不是决策输入

### 4.2 方案二：混合判定型（推荐）

新增 `ComplianceKnowledgeRetrievalService`，先检索公开监管规则 / 官方指引，再将检索结果与候选产品事实一同喂给 `compliance_risk_officer`。当检索失败、agent 失败或输出非法时，再回退静态规则。

优点：

- 能让监管依据真正参与 `approve / revise / block`
- 与现有 product knowledge RAG 架构高度一致
- 保留现有静态规则的稳定 fallback
- 易于逐步扩展到更多合规场景

缺点：

- 需要新增一套 metadata 与检索过滤逻辑
- 需要为官方 PDF / 网页原文建立合规知识 seed 流程

### 4.3 方案三：规则引擎型

先将公开监管规则抽成结构化条款表，再由确定性规则引擎执行审核，RAG 只负责找依据和解释。

优点：

- 最强的可审计性
- 最适合长期合规平台化

缺点：

- 第一阶段建设成本过高
- 当前知识源是 PDF / 网页原文，不适合直接落结构化引擎

### 4.4 决策

采用方案二：`公开监管规则优先 + 静态规则 fallback`。

## 5. 总体架构

### 5.1 架构定位

新增一条与产品知识 RAG 平行的第二知识线：

- 产品知识 RAG：回答“这个产品是什么、为何推荐”
- 合规知识 RAG：回答“这个推荐在规则上是否允许、需要提示什么、是否需要人工复核”

### 5.2 graph 内数据流

推荐 graph 流程保持不变：

1. `user_profile_analyst`
2. `market_intelligence`
3. `product_match_expert`
4. `compliance_risk_officer`
5. `manager_coordinator`

其中第 4 步改造为：

1. 读取用户画像与已选候选产品事实
2. 构造合规 query 与 metadata filter
3. 检索合规知识库
4. 将检索结果写入 graph state
5. 将检索结果 + 候选产品事实一起喂给 `compliance_risk_officer`
6. agent 输出 `verdict / applied_rule_ids / blocking_reason_codes / disclosures`
7. 若合规知识不可用，则回退静态规则服务

### 5.3 fallback 语义

新的优先级如下：

1. 合规知识检索成功 + agent 输出合法：以知识增强合规审核结果为主
2. 合规知识检索失败：记录 warning，回退静态规则
3. agent 调用失败或输出非法：记录 warning，回退静态规则
4. 静态规则也失败：进入现有 block / limited 降级链路

## 6. 数据模型设计

### 6.1 新增检索对象

新增合规证据对象：

```python
class RetrievedComplianceEvidence(BaseModel):
    evidence_id: str
    score: float
    snippet: str
    source_title: str
    source_uri: str | None = None
    doc_type: str
    source_type: str
    jurisdiction: str
    rule_id: str
    rule_type: str
    audience: str
    applies_to_categories: list[str] = Field(default_factory=list)
    applies_to_risk_tiers: list[str] = Field(default_factory=list)
    liquidity_requirement: str | None = None
    lockup_limit_days: int | None = None
    disclosure_type: str | None = None
    effective_date: str | None = None
    section_title: str | None = None
    page_number: int | None = None
```

### 6.2 graph state 扩展

在 [backend/financehub_market_api/recommendation/graph/state.py](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/financehub_market_api/recommendation/graph/state.py) 中新增：

```python
class ComplianceRetrievalContext(BaseModel):
    evidences: list[RetrievedComplianceEvidence] = Field(default_factory=list)
```

并在 `RecommendationGraphState` 中增加：

```python
compliance_retrieval: ComplianceRetrievalContext | None
```

### 6.3 Qdrant payload 字段

第一阶段每个合规知识 chunk 至少需要以下 payload：

```json
{
  "document_id": "csrc-suitability-2025-001",
  "chunk_id": "csrc-suitability-2025-001#03",
  "rule_id": "suitability-risk-tier-match",
  "rule_type": "suitability",
  "jurisdiction": "CN",
  "audience": "retail",
  "applies_to_categories": ["fund", "wealth_management"],
  "applies_to_risk_tiers": ["R1", "R2", "R3", "R4", "R5"],
  "liquidity_requirement": null,
  "lockup_limit_days": null,
  "disclosure_type": "suitability_warning",
  "source_type": "public_regulation",
  "source_title": "基金销售适当性管理办法",
  "source_uri": "https://...",
  "effective_date": "2025-01-01",
  "section_title": "投资者适当性匹配要求",
  "page_number": 6,
  "text": "销售机构应当将产品风险等级与投资者风险承受能力进行匹配..."
}
```

### 6.4 第一阶段 metadata 约定

关键字段取值建议：

- `jurisdiction`: `CN`
- `rule_type`:
  - `suitability`
  - `liquidity_guardrail`
  - `risk_disclosure`
  - `manual_review_trigger`
- `audience`:
  - `retail`
  - `fund_sales`
  - `wealth_management`
- `source_type`:
  - `public_regulation`
  - `public_guideline`
  - `internal_policy`

## 7. 检索设计

### 7.1 检索输入

检索输入不直接使用用户自然语言，而是由以下信息构成：

- 用户画像：
  - `risk_tier`
  - `liquidity_preference`
  - `investment_horizon`
- 候选产品事实：
  - `category`
  - `risk_level`
  - `liquidity`
  - `lockup_days`
- 当前审核意图：
  - `suitability`
  - `liquidity_guardrail`
  - `disclosure`

### 7.2 语义 query 模板

示例 query：

`公募基金 低风险投资者 适当性匹配 风险等级 流动性 封闭期 披露要求`

或：

`银行理财 高流动性 偏低风险客户 封闭期 期限约束 风险揭示`

### 7.3 metadata filter

检索时必须同时叠加 metadata 过滤：

- `rule_type in ["suitability", "liquidity_guardrail", "risk_disclosure", "manual_review_trigger"]`
- `applies_to_categories overlaps current_categories`
- `jurisdiction == "CN"`
- `effective_date <= today`
- 必要时按 `audience` 限制为当前销售场景

### 7.4 命中规则

第一阶段建议：

- 总命中数：`8-12`
- 同一 `rule_id` 最多保留 `1-2` 条
- 优先较新的规则
- 同一文档相邻 chunk 去重

## 8. Prompt 设计

### 8.1 `compliance_risk_officer` 新增输入

在现有 [_build_compliance_prompt_context(...)](/Users/zefengjin/Desktop/Practice/FinanceHub/backend/financehub_market_api/recommendation/graph/nodes.py#L902) 中新增一节：

- `Retrieved compliance evidence`

示例：

```json
[
  {
    "rule_id": "suitability-risk-tier-match",
    "rule_type": "suitability",
    "snippet": "销售机构应当将产品风险等级与投资者风险承受能力进行匹配",
    "source_title": "基金销售适当性管理办法",
    "effective_date": "2025-01-01"
  }
]
```

### 8.2 prompt 硬约束

新增三条硬约束：

1. 优先依据命中的监管条款给出 `verdict`
2. 未检索到明确依据时可回退静态规则，但不得编造条文或规则编号
3. `applied_rule_ids / blocking_reason_codes` 只能引用命中的规则或静态 fallback 编码

## 9. 文件与职责

### 9.1 新增模块

1. `backend/financehub_market_api/recommendation/compliance_knowledge/schemas.py`
   - 合规证据对象与检索 query 对象
2. `backend/financehub_market_api/recommendation/compliance_knowledge/service.py`
   - 合规知识检索统一入口
3. `backend/financehub_market_api/recommendation/compliance_knowledge/qdrant_store.py`
   - Qdrant 检索与 metadata filter
4. `backend/scripts/seed_compliance_knowledge_collection.py`
   - 官方 PDF / 网页解析结果入库 seed

### 9.2 修改文件

1. `backend/financehub_market_api/recommendation/graph/state.py`
   - 扩展 `RecommendationGraphState`
2. `backend/financehub_market_api/recommendation/graph/runtime.py`
   - `GraphServices` 增加 `compliance_knowledge`
   - 默认 wiring 从 env 构建合规知识服务
3. `backend/financehub_market_api/recommendation/graph/nodes.py`
   - `compliance_risk_officer_node` 新增检索、state 写入、fallback
   - `_build_compliance_prompt_context` 新增检索结果 section
4. `backend/financehub_market_api/recommendation/compliance/service.py`
   - 保留静态规则，但明确作为 fallback 使用

## 10. 测试与验证

### 10.1 单元测试

新增：

- `backend/tests/test_compliance_knowledge_service.py`
- `backend/tests/test_compliance_knowledge_qdrant_store.py`

验证内容：

- 检索过滤
- `effective_date` 过滤
- 同 `rule_id` 去重
- `rule_type / audience / category` 过滤

### 10.2 graph 集成测试

更新：

- `backend/tests/test_recommendation_graph_runtime.py`

验证：

- `compliance_risk_officer` 能读到合规证据
- 命中规则时会影响 `approve / revise / block`
- 检索失败时回退静态规则
- `applied_rule_ids / blocking_reason_codes` 写入 state

### 10.3 API 测试

更新：

- `backend/tests/test_api.py`

验证：

- 前端响应不暴露合规知识引用
- 合规结论仍能通过推荐接口体现
- fallback 路径行为可验证

### 10.4 smoke / live

新增：

- `backend/tests/test_compliance_rag_smoke.py`
- `backend/tests/test_compliance_rag_live_smoke.py`
- `backend/tests/test_compliance_rag_live_e2e.py`

验证：

- deterministic fixture 可跑通
- 真实 Qdrant + embedding 环境下能命中公开监管规则

## 11. 验收标准

以下条件全部满足时，本阶段才算完成：

- `compliance_risk_officer` 优先使用公开监管知识进行审核
- A / B / D 三类知识能影响 `approve / revise_conservative / block`
- 合规知识检索失败时自动回退现有静态规则
- 前端不暴露合规知识引用
- smoke 与 live-gated 测试可用

## 12. 风险与边界

### 12.1 主要风险

- 官方 PDF / 网页原文的条文粒度不统一，metadata 标注成本高
- 不同监管文件可能存在新旧版本并存，需要 `effective_date` 管理
- 模型若拿到多条相近条文，可能输出重复或模糊的 `rule_id`

### 12.2 第一阶段控制策略

- 先控制在少量高价值监管资料
- 明确 `rule_id` 与 `rule_type`
- 只允许后台使用
- 静态规则保底，不让检索异常直接破坏主链路

## 13. 后续扩展

后续可以在本设计基础上扩展：

- 前端展示公开监管依据
- 内部制度覆盖层
- 渠道 / 客群差异化规则
- 结构化规则引擎
- 合规知识问答与人工复核工作台
