import type { RiskDimension } from "../features/risk-assessment/risk-scoring";

interface QuestionnaireAnswer {
  labelZh: string;
  labelEn: string;
  score: 1 | 2 | 3 | 4 | 5;
}

interface QuestionnaireItem {
  answers: QuestionnaireAnswer[];
  dimension: RiskDimension;
  id: number;
  promptEn: string;
  promptZh: string;
}

function createFivePointAnswers(
  zhLabels: [string, string, string, string, string],
  enLabels: [string, string, string, string, string],
): QuestionnaireAnswer[] {
  return zhLabels.map((labelZh, index) => ({
    labelEn: enLabels[index],
    labelZh,
    score: (index + 1) as QuestionnaireAnswer["score"],
  }));
}

export const questionnaire: QuestionnaireItem[] = [
  {
    answers: createFivePointAnswers(
      ["无法接受波动", "较难接受波动", "可以接受一般波动", "能接受明显波动", "愿意承受大幅波动"],
      [
        "Cannot tolerate volatility",
        "Struggle with volatility",
        "Can accept normal volatility",
        "Can accept clear volatility",
        "Willing to accept sharp swings",
      ],
    ),
    dimension: "riskTolerance",
    id: 1,
    promptEn: "How do you feel about short-term market volatility?",
    promptZh: "面对短期市场波动，你通常是什么感受？",
  },
  {
    answers: createFivePointAnswers(
      ["会立刻减仓", "会明显降低仓位", "先观察再决定", "会维持原策略", "会考虑逢低布局"],
      [
        "I would sell immediately",
        "I would cut exposure significantly",
        "I would observe first",
        "I would keep my strategy",
        "I may add on weakness",
      ],
    ),
    dimension: "riskTolerance",
    id: 2,
    promptEn: "If your portfolio drops 10% quickly, what would you most likely do?",
    promptZh: "如果你的持仓短期回撤 10%，你最可能怎么做？",
  },
  {
    answers: createFivePointAnswers(
      ["单周亏损就难以接受", "连续两周下跌会焦虑", "连续数周下跌可以承受", "月度回撤仍可坚持", "较长时间回撤也能保持纪律"],
      [
        "A single losing week is hard to accept",
        "Two losing weeks would make me anxious",
        "Several losing weeks are manageable",
        "A monthly drawdown is still acceptable",
        "I can stay disciplined through longer drawdowns",
      ],
    ),
    dimension: "riskTolerance",
    id: 3,
    promptEn: "How long of a losing streak can you tolerate without changing course?",
    promptZh: "在不改变策略的前提下，你能承受多长时间的连续下跌？",
  },
  {
    answers: createFivePointAnswers(
      ["2% 以内", "5% 左右", "10% 左右", "15% 左右", "20% 以上"],
      ["Within 2%", "Around 5%", "Around 10%", "Around 15%", "Above 20%"],
    ),
    dimension: "riskTolerance",
    id: 4,
    promptEn: "What temporary drawdown range can you realistically bear?",
    promptZh: "你实际能够承受的阶段性回撤幅度大概是多少？",
  },
  {
    answers: createFivePointAnswers(
      ["3 个月以内", "3-6 个月", "6-12 个月", "1-3 年", "3 年以上"],
      ["Under 3 months", "3 to 6 months", "6 to 12 months", "1 to 3 years", "More than 3 years"],
    ),
    dimension: "investmentHorizon",
    id: 5,
    promptEn: "What is your typical planned holding period for this capital?",
    promptZh: "这笔资金的计划投资期限通常是多久？",
  },
  {
    answers: createFivePointAnswers(
      ["不能等待", "最多等待几周", "可以等待几个月", "可以等待 1 年左右", "愿意等待更长周期"],
      [
        "I cannot wait",
        "I can wait a few weeks at most",
        "I can wait several months",
        "I can wait around a year",
        "I am willing to wait much longer",
      ],
    ),
    dimension: "investmentHorizon",
    id: 6,
    promptEn: "If the market is weak, how long can you wait for the thesis to play out?",
    promptZh: "如果市场阶段性偏弱，你愿意等待多久让投资逻辑兑现？",
  },
  {
    answers: createFivePointAnswers(
      ["很快就要用到", "半年内可能要用", "一年内可能要用", "两三年内大概率不用", "长期都不会动用"],
      [
        "I need it soon",
        "I may need it within 6 months",
        "I may need it within a year",
        "I likely will not need it for 2 to 3 years",
        "I will not touch it for the long term",
      ],
    ),
    dimension: "investmentHorizon",
    id: 7,
    promptEn: "How soon might you need this invested money for other purposes?",
    promptZh: "这笔投资资金在多久内可能需要挪作他用？",
  },
  {
    answers: createFivePointAnswers(
      ["没有长期规划", "只有短期用途", "有一年左右安排", "有明确中期目标", "有清晰长期目标"],
      [
        "No long-term plan",
        "Only short-term uses",
        "A plan for around one year",
        "Clear medium-term goals",
        "Clear long-term goals",
      ],
    ),
    dimension: "investmentHorizon",
    id: 8,
    promptEn: "How clear is your long-term financial plan for this portfolio?",
    promptZh: "你对这部分资产的长期财务规划有多清晰？",
  },
  {
    answers: createFivePointAnswers(
      ["收入非常不稳定", "收入波动较大", "收入基本稳定", "收入较稳定且可预期", "收入非常稳定且增长明确"],
      [
        "My income is very unstable",
        "My income fluctuates a lot",
        "My income is mostly stable",
        "My income is stable and predictable",
        "My income is highly stable with clear growth",
      ],
    ),
    dimension: "capitalStability",
    id: 9,
    promptEn: "How stable is your current income source?",
    promptZh: "你当前的收入来源稳定性如何？",
  },
  {
    answers: createFivePointAnswers(
      ["几乎没有备用金", "备用金不足 3 个月", "备用金约 3-6 个月", "备用金约 6-12 个月", "备用金超过 12 个月"],
      [
        "I have almost no emergency fund",
        "Emergency fund is under 3 months",
        "Emergency fund is around 3 to 6 months",
        "Emergency fund is around 6 to 12 months",
        "Emergency fund is above 12 months",
      ],
    ),
    dimension: "capitalStability",
    id: 10,
    promptEn: "How much emergency cash reserve do you currently have?",
    promptZh: "你目前大概有多少应急备用金？",
  },
  {
    answers: createFivePointAnswers(
      ["几乎肯定会用到", "较大概率会用到", "存在一定可能", "大概率不会动用", "基本确定不会动用"],
      [
        "I will almost certainly need it",
        "I am quite likely to need it",
        "There is some chance I need it",
        "I probably will not need it",
        "I am almost certain I will not need it",
      ],
    ),
    dimension: "capitalStability",
    id: 11,
    promptEn: "How likely are you to need this capital within the next 12 months?",
    promptZh: "未来 12 个月内，你需要动用这笔资金的概率有多高？",
  },
  {
    answers: createFivePointAnswers(
      ["会影响日常生活", "会影响重要支出", "有一定压力但可调整", "基本独立于日常开支", "完全属于长期闲置可投资资金"],
      [
        "It affects daily living",
        "It affects important spending",
        "It creates some pressure but is manageable",
        "It is mostly separate from daily expenses",
        "It is fully discretionary long-term capital",
      ],
    ),
    dimension: "capitalStability",
    id: 12,
    promptEn: "How independent is this capital from your daily spending needs?",
    promptZh: "这笔资金与日常生活开支的独立程度如何？",
  },
  {
    answers: createFivePointAnswers(
      ["几乎没有经验", "接触很少", "有基础经验", "有较多实操经验", "经历过多轮市场周期"],
      [
        "Almost no experience",
        "Very limited exposure",
        "Basic experience",
        "Considerable hands-on experience",
        "I have lived through multiple market cycles",
      ],
    ),
    dimension: "investmentExperience",
    id: 13,
    promptEn: "How much practical investment experience do you have with equity products?",
    promptZh: "你在权益类产品上的实际投资经验大概有多少？",
  },
  {
    answers: createFivePointAnswers(
      ["完全不了解", "了解很有限", "理解基本概念", "较理解波动与回撤", "能系统理解波动、回撤与估值"],
      [
        "I do not understand them at all",
        "My understanding is very limited",
        "I understand the basic concepts",
        "I understand volatility and drawdowns fairly well",
        "I understand volatility, drawdowns, and valuation systematically",
      ],
    ),
    dimension: "investmentExperience",
    id: 14,
    promptEn: "How well do you understand volatility, drawdown, and valuation changes?",
    promptZh: "你对波动、回撤和估值变化的理解程度如何？",
  },
  {
    answers: createFivePointAnswers(
      ["没有经历过", "经历过但较难接受", "经历过并能基本应对", "经历过并能复盘调整", "多次经历且能保持纪律"],
      [
        "I have never experienced one",
        "I have, but it was hard to handle",
        "I have and could basically cope",
        "I have and could review and adjust",
        "I have many times and stayed disciplined",
      ],
    ),
    dimension: "investmentExperience",
    id: 15,
    promptEn: "How have you handled meaningful market declines in the past?",
    promptZh: "过去遇到明显市场下跌时，你通常应对得怎么样？",
  },
  {
    answers: createFivePointAnswers(
      ["几乎不会看", "只看盈亏", "会看基础信息", "会结合波动与仓位看", "会系统看收益、风险和配置"],
      [
        "I barely review it",
        "I only check profit and loss",
        "I review basic information",
        "I review volatility and position sizing together",
        "I review return, risk, and allocation systematically",
      ],
    ),
    dimension: "investmentExperience",
    id: 16,
    promptEn: "How do you usually review and understand your portfolio behavior?",
    promptZh: "你平时如何复盘和理解自己的组合表现？",
  },
  {
    answers: createFivePointAnswers(
      ["只想保本", "以保值为主", "希望稳健增值", "愿意追求较高增长", "更看重较高收益空间"],
      [
        "I only want to preserve capital",
        "Capital preservation comes first",
        "I want steady appreciation",
        "I am willing to pursue stronger growth",
        "I prioritize higher upside potential",
      ],
    ),
    dimension: "returnObjective",
    id: 17,
    promptEn: "What best describes your main return objective?",
    promptZh: "以下哪项最符合你的主要收益目标？",
  },
  {
    answers: createFivePointAnswers(
      ["极低收益也能接受", "低收益即可", "中等收益即可", "希望较高收益", "希望尽量争取更高收益"],
      [
        "Very low returns are acceptable",
        "Low returns are enough",
        "Moderate returns are enough",
        "I want stronger returns",
        "I want to pursue the highest returns possible",
      ],
    ),
    dimension: "returnObjective",
    id: 18,
    promptEn: "How ambitious are your return expectations for this portfolio?",
    promptZh: "你对这部分组合的收益预期有多积极？",
  },
  {
    answers: createFivePointAnswers(
      ["不愿意承担额外波动", "尽量少承担波动", "可接受适度波动换收益", "愿意承受较大波动", "愿意为高收益承担明显波动"],
      [
        "I do not want extra volatility",
        "I want to minimize volatility",
        "I can accept moderate volatility for returns",
        "I can take significant volatility",
        "I am willing to accept sharp volatility for upside",
      ],
    ),
    dimension: "returnObjective",
    id: 19,
    promptEn: "How much volatility are you willing to trade for higher returns?",
    promptZh: "为了更高收益，你愿意交换多少波动风险？",
  },
  {
    answers: createFivePointAnswers(
      ["不配置", "少量尝试", "适度配置", "可以提高比例", "可以作为重要配置方向"],
      [
        "None",
        "Only a small trial allocation",
        "A moderate allocation",
        "A higher allocation is acceptable",
        "It can be a major allocation theme",
      ],
    ),
    dimension: "returnObjective",
    id: 20,
    promptEn: "How much of your portfolio can be allocated to higher-volatility growth assets?",
    promptZh: "你愿意将多大比例的组合配置给高波动成长资产？",
  },
];
