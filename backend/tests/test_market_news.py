from __future__ import annotations

import pytest

from financehub_market_api.market_news import (
    MarketNewsService,
    TavilyMarketNewsProvider,
    build_market_news_service_from_env,
    classify_market_news_sentiment,
    optimize_market_news_query,
)


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, object]:
        return self._payload


class _FakeHttpClient:
    def __init__(self, payload: dict[str, object]) -> None:
        self._payload = payload
        self.calls: list[dict[str, object]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, object],
        timeout: float,
    ) -> _FakeResponse:
        self.calls.append(
            {
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return _FakeResponse(self._payload)


def test_tavily_market_news_provider_normalizes_deduplicates_and_summarizes_results() -> None:
    http_client = _FakeHttpClient(
        {
            "results": [
                {
                    "title": "半导体板块重大突破",
                    "url": "https://news.example.com/a",
                    "content": "国产芯片获批并大幅增长。",
                    "published_date": "2026-04-14T09:00:00Z",
                    "source": "Example News",
                },
                {
                    "title": "半导体板块重大突破",
                    "url": "https://news.example.com/a/",
                    "content": "重复报道应被去重。",
                    "published_date": "2026-04-14T09:05:00Z",
                },
                {
                    "title": "龙头公司被处罚",
                    "url": "https://risk.example.com/b",
                    "content": "监管处罚引发不确定。",
                    "published_date": "2026-04-14T10:00:00Z",
                },
                {
                    "title": "",
                    "content": "没有标题的结果应被忽略。",
                },
            ]
        }
    )
    service = MarketNewsService(
        provider=TavilyMarketNewsProvider(api_key="tavily-test", http_client=http_client)
    )

    digest = service.fetch_digest(query="半导体", time_range="week", max_results=5)

    assert http_client.calls == [
        {
            "url": "https://api.tavily.com/search",
            "headers": {
                "Authorization": "Bearer tavily-test",
                "Content-Type": "application/json",
            },
            "json": {
                "query": "半导体 中国 A股 证券市场 财经新闻 东方财富 证券时报 中国证券报",
                "topic": "news",
                "time_range": "week",
                "max_results": 5,
                "include_answer": False,
                "include_domains": [
                    "eastmoney.com",
                    "finance.sina.com.cn",
                    "stcn.com",
                    "cnstock.com",
                    "cs.com.cn",
                    "yicai.com",
                ],
            },
            "timeout": 15.0,
        }
    ]
    assert digest.query == "半导体"
    assert digest.positiveCount == 1
    assert digest.negativeCount == 1
    assert digest.neutralCount == 0
    assert digest.temperature == "中性"
    assert [item.title for item in digest.items] == [
        "半导体板块重大突破",
        "龙头公司被处罚",
    ]
    assert all(item.topic == "半导体" for item in digest.items)
    assert digest.items[0].source == "Example News"
    assert digest.items[1].source == "risk.example.com"
    assert digest.items[0].sentiment == "positive"
    assert digest.items[1].sentiment == "negative"
    assert "共 2 条" in digest.summaryZh
    assert "仅供参考" in digest.summaryZh


def test_market_news_service_optimizes_broad_a_share_query_without_changing_digest_query() -> None:
    http_client = _FakeHttpClient(
        {
            "results": [
                {
                    "title": "A股三大指数午后回升",
                    "url": "https://finance.eastmoney.com/a",
                    "content": "东方财富报道，证券市场风险偏好回暖。",
                }
            ]
        }
    )
    service = MarketNewsService(
        provider=TavilyMarketNewsProvider(api_key="tavily-test", http_client=http_client)
    )

    digest = service.fetch_digest(query="A股 市场 今日 要闻", time_range="day", max_results=3)

    tavily_query = http_client.calls[0]["json"]["query"]
    assert digest.query == "A股 市场 今日 要闻"
    assert digest.items[0].topic == "A股 市场 今日 要闻"
    assert "中国" in tavily_query
    assert "A股" in tavily_query
    assert "东方财富" in tavily_query
    assert "证券时报" in tavily_query
    assert http_client.calls[0]["json"]["include_domains"] == [
        "eastmoney.com",
        "finance.sina.com.cn",
        "stcn.com",
        "cnstock.com",
        "cs.com.cn",
        "yicai.com",
    ]


def test_market_news_service_skips_a_share_domain_filter_for_global_query() -> None:
    http_client = _FakeHttpClient({"results": []})
    service = MarketNewsService(
        provider=TavilyMarketNewsProvider(api_key="tavily-test", http_client=http_client)
    )

    service.fetch_digest(query="美股 纳斯达克 今日消息", time_range="day", max_results=3)

    assert http_client.calls[0]["json"]["query"] == "美股 纳斯达克 今日消息"
    assert "include_domains" not in http_client.calls[0]["json"]


def test_optimize_market_news_query_adds_a_share_context_for_short_sector_query() -> None:
    optimized = optimize_market_news_query("半导体")

    assert optimized.startswith("半导体")
    assert "中国" in optimized
    assert "A股" in optimized
    assert "财经新闻" in optimized


def test_optimize_market_news_query_respects_explicit_global_market_query() -> None:
    optimized = optimize_market_news_query("美股 纳斯达克 今日消息")

    assert optimized == "美股 纳斯达克 今日消息"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("公司取得重大突破，业绩超预期增长", "positive"),
        ("监管处罚叠加大幅亏损，存在退市风险", "negative"),
        ("公司召开调研会议并发布公告", "neutral"),
    ],
)
def test_classify_market_news_sentiment_uses_financial_keyword_signals(
    text: str,
    expected: str,
) -> None:
    assert classify_market_news_sentiment(text) == expected


def test_build_market_news_service_from_env_without_tavily_key_returns_empty_digest() -> None:
    service = build_market_news_service_from_env(
        environ={"FINANCEHUB_MARKET_NEWS_TAVILY_API_KEY": ""}
    )

    digest = service.fetch_digest(query="A股 市场 今日 要闻")

    assert digest.query == "A股 市场 今日 要闻"
    assert digest.items == []
    assert digest.positiveCount == 0
    assert digest.negativeCount == 0
    assert digest.neutralCount == 0
    assert digest.temperature == "中性"
    assert "暂未配置市场新闻数据源" in digest.summaryZh


def test_build_market_news_service_from_env_uses_configured_search_defaults(
    monkeypatch,
) -> None:
    http_client = _FakeHttpClient({"results": []})
    monkeypatch.setattr(
        "financehub_market_api.market_news.httpx.Client",
        lambda: http_client,
    )

    service = build_market_news_service_from_env(
        environ={
            "FINANCEHUB_MARKET_NEWS_PROVIDER": "tavily",
            "FINANCEHUB_MARKET_NEWS_TAVILY_API_KEY": "tavily-test",
            "FINANCEHUB_MARKET_NEWS_TIME_RANGE": "day",
            "FINANCEHUB_MARKET_NEWS_MAX_RESULTS": "4",
            "FINANCEHUB_MARKET_NEWS_TAVILY_INCLUDE_DOMAINS": "eastmoney.com,stcn.com",
        }
    )

    service.fetch_digest(query="半导体")

    assert http_client.calls[0]["json"]["time_range"] == "day"
    assert http_client.calls[0]["json"]["max_results"] == 4
    assert http_client.calls[0]["json"]["include_domains"] == [
        "eastmoney.com",
        "stcn.com",
    ]


def test_build_market_news_service_from_env_invalid_max_results_uses_default(
    monkeypatch,
) -> None:
    http_client = _FakeHttpClient({"results": []})
    monkeypatch.setattr(
        "financehub_market_api.market_news.httpx.Client",
        lambda: http_client,
    )

    service = build_market_news_service_from_env(
        environ={
            "FINANCEHUB_MARKET_NEWS_PROVIDER": "tavily",
            "FINANCEHUB_MARKET_NEWS_TAVILY_API_KEY": "tavily-test",
            "FINANCEHUB_MARKET_NEWS_MAX_RESULTS": "many",
        }
    )

    service.fetch_digest(query="半导体")

    assert http_client.calls[0]["json"]["max_results"] == 10
