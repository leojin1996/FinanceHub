from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Literal
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, Field

from financehub_market_api.env import build_env_values, read_env

MarketNewsSentiment = Literal["positive", "negative", "neutral"]

_DEFAULT_QUERY = "A股 市场 今日 要闻"
_DEFAULT_PROVIDER = "tavily"
_DEFAULT_TIME_RANGE = "week"
_DEFAULT_MAX_RESULTS = 10
_TAVILY_SEARCH_URL = "https://api.tavily.com/search"
_TAVILY_TIMEOUT_SECONDS = 15.0

_POSITIVE_KEYWORDS = (
    "超预期",
    "大幅增长",
    "重大突破",
    "获批",
    "中标",
    "增长",
    "改善",
    "优化",
    "合作",
    "布局",
    "反弹",
    "走强",
    "回暖",
)
_NEGATIVE_KEYWORDS = (
    "暴雷",
    "造假",
    "退市",
    "处罚",
    "大幅亏损",
    "下滑",
    "减少",
    "推迟",
    "不确定",
    "下跌",
    "走弱",
    "承压",
)
_A_SHARE_CONTEXT_TERMS = (
    "中国",
    "A股",
    "证券市场",
    "财经新闻",
    "东方财富",
    "证券时报",
    "中国证券报",
)
_DEFAULT_A_SHARE_INCLUDE_DOMAINS = (
    "eastmoney.com",
    "finance.sina.com.cn",
    "stcn.com",
    "cnstock.com",
    "cs.com.cn",
    "yicai.com",
)
_EXPLICIT_NON_A_SHARE_TERMS = (
    "美股",
    "港股",
    "纳斯达克",
    "道琼斯",
    "标普",
    "日经",
    "黄金",
    "原油",
    "美元",
    "比特币",
)


class MarketNewsItem(BaseModel):
    title: str
    url: str | None = None
    source: str | None = None
    publishedAt: str | None = None
    contentSnippet: str = ""
    sentiment: MarketNewsSentiment
    topic: str


class MarketNewsDigest(BaseModel):
    query: str
    asOf: str
    positiveCount: int = 0
    negativeCount: int = 0
    neutralCount: int = 0
    temperature: str = "中性"
    items: list[MarketNewsItem] = Field(default_factory=list)
    summaryZh: str


class TavilyMarketNewsProvider:
    def __init__(
        self,
        *,
        api_key: str,
        http_client: httpx.Client | None = None,
        search_url: str = _TAVILY_SEARCH_URL,
        timeout_seconds: float = _TAVILY_TIMEOUT_SECONDS,
    ) -> None:
        self._api_key = api_key
        self._http_client = http_client or httpx.Client()
        self._search_url = search_url
        self._timeout_seconds = timeout_seconds

    def fetch_items(
        self,
        *,
        query: str,
        time_range: str,
        max_results: int,
        topic: str | None = None,
        include_domains: list[str] | None = None,
    ) -> list[MarketNewsItem]:
        request_body: dict[str, object] = {
            "query": query,
            "topic": "news",
            "time_range": time_range,
            "max_results": max_results,
            "include_answer": False,
        }
        if include_domains:
            request_body["include_domains"] = include_domains

        response = self._http_client.post(
            self._search_url,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
            },
            json=request_body,
            timeout=self._timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results") if isinstance(payload, dict) else None
        if not isinstance(results, list):
            return []
        return _normalize_tavily_results(results, topic=topic or query)


class MarketNewsService:
    def __init__(
        self,
        provider: TavilyMarketNewsProvider | None = None,
        *,
        default_time_range: str = _DEFAULT_TIME_RANGE,
        default_max_results: int = _DEFAULT_MAX_RESULTS,
        default_include_domains: tuple[str, ...] = _DEFAULT_A_SHARE_INCLUDE_DOMAINS,
    ) -> None:
        self._provider = provider
        self._default_time_range = default_time_range
        self._default_max_results = default_max_results
        self._default_include_domains = default_include_domains

    def fetch_digest(
        self,
        *,
        query: str = _DEFAULT_QUERY,
        time_range: str | None = None,
        max_results: int | None = None,
    ) -> MarketNewsDigest:
        normalized_query = query.strip() or _DEFAULT_QUERY
        if self._provider is None:
            return _build_digest(
                query=normalized_query,
                items=[],
                empty_reason="暂未配置市场新闻数据源。",
            )

        items = self._provider.fetch_items(
            query=optimize_market_news_query(normalized_query),
            time_range=_normalize_time_range(time_range or self._default_time_range),
            max_results=_normalize_max_results(
                max_results
                if max_results is not None
                else self._default_max_results
            ),
            topic=normalized_query,
            include_domains=_include_domains_for_query(
                normalized_query,
                default_include_domains=self._default_include_domains,
            ),
        )
        return _build_digest(query=normalized_query, items=items)


def build_market_news_service_from_env(
    *,
    environ: Mapping[str, str] | None = None,
) -> MarketNewsService:
    env = build_env_values(environ=environ)
    provider = (
        read_env(env, "FINANCEHUB_MARKET_NEWS_PROVIDER") or _DEFAULT_PROVIDER
    ).lower()
    default_time_range = (
        read_env(env, "FINANCEHUB_MARKET_NEWS_TIME_RANGE") or _DEFAULT_TIME_RANGE
    )
    default_max_results = _normalize_max_results(
        read_env(env, "FINANCEHUB_MARKET_NEWS_MAX_RESULTS") or _DEFAULT_MAX_RESULTS
    )
    include_domains = _parse_include_domains(
        read_env(env, "FINANCEHUB_MARKET_NEWS_TAVILY_INCLUDE_DOMAINS")
    )
    if provider != "tavily":
        return MarketNewsService(
            default_time_range=default_time_range,
            default_max_results=default_max_results,
            default_include_domains=include_domains,
        )
    api_key = read_env(env, "FINANCEHUB_MARKET_NEWS_TAVILY_API_KEY")
    if not api_key:
        return MarketNewsService(
            default_time_range=default_time_range,
            default_max_results=default_max_results,
            default_include_domains=include_domains,
        )
    return MarketNewsService(
        provider=TavilyMarketNewsProvider(api_key=api_key),
        default_time_range=default_time_range,
        default_max_results=default_max_results,
        default_include_domains=include_domains,
    )


def classify_market_news_sentiment(text: str) -> MarketNewsSentiment:
    normalized = text.strip()
    negative = any(keyword in normalized for keyword in _NEGATIVE_KEYWORDS)
    positive = any(keyword in normalized for keyword in _POSITIVE_KEYWORDS)
    if negative:
        return "negative"
    if positive:
        return "positive"
    return "neutral"


def optimize_market_news_query(query: str) -> str:
    normalized_query = " ".join(query.strip().split()) or _DEFAULT_QUERY
    if _is_explicit_non_a_share_query(normalized_query):
        return normalized_query

    missing_terms = [
        term for term in _A_SHARE_CONTEXT_TERMS if term not in normalized_query
    ]
    if not missing_terms:
        return normalized_query
    return f"{normalized_query} {' '.join(missing_terms)}"


def _include_domains_for_query(
    query: str,
    *,
    default_include_domains: tuple[str, ...],
) -> list[str]:
    if _is_explicit_non_a_share_query(query):
        return []
    return list(default_include_domains)


def _is_explicit_non_a_share_query(query: str) -> bool:
    return any(term in query for term in _EXPLICIT_NON_A_SHARE_TERMS)


def _parse_include_domains(raw_value: str | None) -> tuple[str, ...]:
    if not raw_value:
        return _DEFAULT_A_SHARE_INCLUDE_DOMAINS
    domains = tuple(
        domain.strip()
        for domain in raw_value.split(",")
        if domain.strip()
    )
    return domains or _DEFAULT_A_SHARE_INCLUDE_DOMAINS


def _normalize_tavily_results(
    results: list[object],
    *,
    topic: str,
) -> list[MarketNewsItem]:
    items: list[MarketNewsItem] = []
    seen: set[str] = set()
    for raw_result in results:
        if not isinstance(raw_result, dict):
            continue
        title = _read_result_string(raw_result, "title")
        if not title:
            continue
        url = _read_result_string(raw_result, "url")
        dedupe_keys = [_dedupe_title_key(title)]
        if url:
            dedupe_keys.append(_dedupe_url_key(url))
        if any(key in seen for key in dedupe_keys):
            continue
        seen.update(dedupe_keys)

        content = (
            _read_result_string(raw_result, "content")
            or _read_result_string(raw_result, "raw_content")
            or _read_result_string(raw_result, "snippet")
        )
        source = _read_result_string(raw_result, "source") or _source_from_url(url)
        published_at = (
            _read_result_string(raw_result, "published_date")
            or _read_result_string(raw_result, "publishedAt")
            or _read_result_string(raw_result, "published_at")
        )
        items.append(
            MarketNewsItem(
                title=title,
                url=url or None,
                source=source,
                publishedAt=published_at or None,
                contentSnippet=content,
                sentiment=classify_market_news_sentiment(f"{title} {content}"),
                topic=topic,
            )
        )
    return items


def _build_digest(
    *,
    query: str,
    items: list[MarketNewsItem],
    empty_reason: str | None = None,
) -> MarketNewsDigest:
    positive_count = sum(1 for item in items if item.sentiment == "positive")
    negative_count = sum(1 for item in items if item.sentiment == "negative")
    neutral_count = sum(1 for item in items if item.sentiment == "neutral")
    temperature = _temperature(
        positive_count=positive_count,
        negative_count=negative_count,
    )
    return MarketNewsDigest(
        query=query,
        asOf=datetime.now(UTC).isoformat(),
        positiveCount=positive_count,
        negativeCount=negative_count,
        neutralCount=neutral_count,
        temperature=temperature,
        items=items,
        summaryZh=_summary_zh(
            items=items,
            positive_count=positive_count,
            negative_count=negative_count,
            neutral_count=neutral_count,
            temperature=temperature,
            empty_reason=empty_reason,
        ),
    )


def _summary_zh(
    *,
    items: list[MarketNewsItem],
    positive_count: int,
    negative_count: int,
    neutral_count: int,
    temperature: str,
    empty_reason: str | None,
) -> str:
    if not items:
        return f"{empty_reason or '暂无可用市场新闻。'} 新闻情绪仅供参考。"
    titles = "；".join(item.title for item in items[:3])
    return (
        f"新闻聚合：共 {len(items)} 条，利好 {positive_count} 条，"
        f"利空 {negative_count} 条，中性 {neutral_count} 条，"
        f"情绪温度 {temperature}。核心事件：{titles}。新闻情绪仅供参考。"
    )


def _temperature(*, positive_count: int, negative_count: int) -> str:
    if positive_count > negative_count:
        return "偏多"
    if negative_count > positive_count:
        return "偏空"
    return "中性"


def _read_result_string(result: dict[str, object], key: str) -> str:
    value = result.get(key)
    return value.strip() if isinstance(value, str) else ""


def _source_from_url(url: str) -> str | None:
    if not url:
        return None
    hostname = urlparse(url).hostname
    return hostname.removeprefix("www.") if hostname else None


def _dedupe_title_key(title: str) -> str:
    return f"title:{' '.join(title.strip().lower().split())}"


def _dedupe_url_key(url: str) -> str:
    return f"url:{url.strip().rstrip('/').lower()}"


def _normalize_time_range(time_range: str) -> str:
    return time_range.strip() or _DEFAULT_TIME_RANGE


def _normalize_max_results(max_results: object) -> int:
    try:
        value = int(max_results)
    except (TypeError, ValueError):
        value = _DEFAULT_MAX_RESULTS
    return max(0, min(value, 20))
