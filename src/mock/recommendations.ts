import type { RiskProfile } from "../app/state/app-state";
import type { RiskDimension } from "../features/risk-assessment/risk-scoring";

export interface RecommendationItem {
  code: string;
  focusDimensions: [RiskDimension, RiskDimension];
  nameEn: string;
  nameZh: string;
  reasonEn: string;
  reasonZh: string;
}

export const recommendationGroups: Record<RiskProfile, RecommendationItem[]> = {
  aggressive: [
    {
      code: "688111",
      focusDimensions: ["returnObjective", "riskTolerance"],
      nameEn: "Kingsoft Office",
      nameZh: "金山办公",
      reasonEn: "Higher volatility with stronger growth optionality.",
      reasonZh: "估值波动更大，但成长弹性更强。",
    },
  ],
  balanced: [
    {
      code: "600276",
      focusDimensions: ["investmentExperience", "investmentHorizon"],
      nameEn: "Hengrui Medicine",
      nameZh: "恒瑞医药",
      reasonEn: "Pipeline depth and product upgrades suit investors who can hold through cycles.",
      reasonZh: "研发管线和产品升级节奏，更适合能跨周期跟踪与持有的投资者。",
    },
    {
      code: "600519",
      focusDimensions: ["returnObjective", "riskTolerance"],
      nameEn: "Kweichow Moutai",
      nameZh: "贵州茅台",
      reasonEn: "Category leadership offers resilient quality with room for steady compounding.",
      reasonZh: "龙头地位稳固，在品质壁垒下仍保留稳健复利空间。",
    },
    {
      code: "000333",
      focusDimensions: ["capitalStability", "riskTolerance"],
      nameEn: "Midea Group",
      nameZh: "美的集团",
      reasonEn: "Cash-flow resilience can help anchor a balanced portfolio when conditions get uneven.",
      reasonZh: "现金流韧性较强，在组合需要稳定锚点时更容易发挥作用。",
    },
  ],
  conservative: [
    {
      code: "600036",
      focusDimensions: ["capitalStability", "riskTolerance"],
      nameEn: "China Merchants Bank",
      nameZh: "招商银行",
      reasonEn: "Stable earnings with strong dividend history.",
      reasonZh: "盈利稳定，分红记录较强。",
    },
  ],
  growth: [
    {
      code: "300750",
      focusDimensions: ["investmentHorizon", "returnObjective"],
      nameEn: "CATL",
      nameZh: "宁德时代",
      reasonEn: "High-growth business in a strong sector.",
      reasonZh: "成长属性明显，行业景气度高。",
    },
  ],
  stable: [
    {
      code: "600900",
      focusDimensions: ["capitalStability", "investmentHorizon"],
      nameEn: "Yangtze Power",
      nameZh: "长江电力",
      reasonEn: "Defensive profile with durable cash flows.",
      reasonZh: "防御属性较强，现金流稳健。",
    },
  ],
};
