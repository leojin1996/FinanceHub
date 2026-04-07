import type { Messages } from "../messages";

export const zhCNMessages: Messages = {
  auth: {
    title: "欢迎来到 FinanceHub",
    subtitle: "登录后即可访问你的投资仪表盘。",
    emailLabel: "邮箱地址",
    highlightMarkets: "追踪市场",
    highlightData: "真实数据",
    highlightInsights: "风险洞察",
    passwordLabel: "密码",
    signInAction: "登录",
    demoAction: "体验 Demo 账户",
  },
  dataState: {
    cachedLabel: "正在显示上次缓存数据",
    loading: "正在加载市场数据",
    errorTitle: "市场数据暂不可用",
    errorBody: "请稍后重试，或等待上一次成功快照恢复。",
    staleLabel: "最近可用收盘数据",
  },
  languageLabel: "语言",
  marketOverview: {
    chartTitle: "近期收盘走势",
    insightTitle: "盘面洞察",
    gainersTitle: "涨幅榜",
    losersTitle: "跌幅榜",
    insightBody: "重点关注代表性股票与核心指数的最新交易日收盘表现。",
  },
  session: {
    logoutAction: "退出登录",
    userAriaLabel: "当前登录用户",
  },
  topStatus: {
    workspaceLabel: "中国市场工作区",
    dataBadgeLabel: "A股收盘数据",
  },
  nav: {
    overview: {
      navLabel: "市场",
      title: "市场概览",
      subtitle: "追踪市场关键指标与今日异动。",
      description: "追踪中国市场与核心指数动态。",
    },
    stocks: {
      navLabel: "股票",
      title: "中国股票",
      subtitle: "聚焦重点股票表现与成交情况。",
      description: "查看A股重点板块与代表个股行情。",
    },
    indices: {
      navLabel: "指数",
      title: "中国指数",
      subtitle: "对比核心指数走势与相对强弱。",
      description: "跟踪沪深主要指数的日内与阶段表现。",
    },
    riskAssessment: {
      navLabel: "风险测评",
      title: "风险评估",
      subtitle: "评估当前风险偏好与组合承受能力。",
      description: "梳理风险维度，为后续问卷评估预留入口。",
    },
    recommendations: {
      navLabel: "推荐",
      title: "个性化推荐",
      subtitle: "根据风险偏好展示候选策略方向。",
      description: "展示基于画像与市场状态的策略占位内容。",
    },
  },
};
