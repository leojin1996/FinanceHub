from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
import hashlib
import re
from collections.abc import Sequence

_NON_WORD_RE = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")
_STOCK_CODE_RE = re.compile(r"\b(?:\d{6}(?:\.(?:SH|SZ))?|[A-Z]{2}\d{6})\b")

_PREFERENCE_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "liquidity_high",
        (
            "流动性",
            "随时能用钱",
            "随时可用",
            "容易赎回",
            "灵活",
            "随取随用",
            "备用金",
            "应急",
            "应急金",
            "取用方便",
        ),
    ),
    (
        "liquidity_low",
        ("长期锁定", "封闭期长", "流动性低", "闲钱", "长期不用", "不着急用"),
    ),
    (
        "horizon_short",
        (
            "一年内",
            "1年内",
            "短期",
            "一年到两年",
            "1到2年",
            "1-2年",
            "半年内",
            "几个月",
        ),
    ),
    (
        "horizon_medium",
        ("三到五年", "3到5年", "3-5年", "中期", "两三年", "两到三年", "2到3年", "2-3年"),
    ),
    (
        "horizon_long",
        ("五年以上", "长期持有", "长期", "养老", "教育金", "十年以上"),
    ),
    (
        "drawdown_low",
        ("小幅回撤", "不能接受大回撤", "回撤小", "保本", "不希望净值波动太大", "本金不能亏太多", "不能亏太多"),
    ),
    (
        "drawdown_medium",
        ("适度波动", "中等回撤", "承受一些波动", "可以承受一定波动"),
    ),
    (
        "drawdown_high",
        ("高波动", "大回撤", "承受较大波动", "回撤大一点也可以"),
    ),
    (
        "risk_low",
        ("稳健", "低风险", "保守", "别冒太大风险", "不想冒太大风险"),
    ),
    (
        "risk_medium",
        ("平衡", "兼顾稳健和成长", "中风险", "稳中求进"),
    ),
    (
        "risk_high",
        ("激进", "高风险", "成长性更强", "博取更高收益"),
    ),
    (
        "preservation",
        ("保本", "本金安全", "资本保值"),
    ),
    (
        "income",
        ("现金流", "分红", "稳健收益", "固定收益", "收息", "票息"),
    ),
    (
        "balanced_growth",
        ("兼顾稳健和成长", "平衡增长", "稳中求进"),
    ),
    (
        "growth",
        ("成长", "高收益", "进攻性", "多赚一点", "向上弹性", "弹性"),
    ),
)

_TOPIC_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("market_view", ("市场", "波动", "行情", "大盘")),
    ("stock_analysis", ("股票", "个股", "估值", "基本面")),
    ("fund_selection", ("基金", "债基", "权益基金", "etf", "ETF", "指数基金")),
    ("wealth_management", ("理财", "流动性", "稳健配置", "备用金", "闲钱")),
    ("asset_allocation", ("配置", "仓位", "资产配置")),
    ("risk_management", ("回撤", "风控", "风险")),
)

_PREFERENCE_MEMORY_HINTS: tuple[str, ...] = (
    "我更看重",
    "希望",
    "我计划",
    "我倾向于",
    "我比较在意",
    "我想要",
    "最多接受",
    "可以接受",
    "持有期",
    "备用金",
    "闲钱",
    "随取随用",
)


@dataclass(frozen=True)
class ChatMessageMetadata:
    content_normalized: str
    content_fingerprint: str
    preference_tags: tuple[str, ...]
    topic_tags: tuple[str, ...]
    symbol_mentions: tuple[str, ...]
    is_preference_memory: bool
    information_density: float
    recency_bucket: str


@dataclass(frozen=True)
class RecallQueryContext:
    embedding_text: str
    preference_tags: tuple[str, ...]
    topic_tags: tuple[str, ...]
    symbol_mentions: tuple[str, ...]


def normalize_chat_text(text: str) -> str:
    collapsed = _NON_WORD_RE.sub(" ", text).strip()
    return re.sub(r"\s+", " ", collapsed)


def fingerprint_chat_text(normalized_text: str) -> str:
    return hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()[:16]


def extract_preference_tags(text: str) -> tuple[str, ...]:
    return _extract_tags(text, _PREFERENCE_PATTERNS)


def extract_topic_tags(text: str) -> tuple[str, ...]:
    return _extract_tags(text, _TOPIC_PATTERNS)


def extract_symbol_mentions(text: str) -> tuple[str, ...]:
    seen: set[str] = set()
    matches: list[str] = []
    for match in _STOCK_CODE_RE.findall(text.upper()):
        if match not in seen:
            seen.add(match)
            matches.append(match)
    return tuple(matches)


def is_preference_memory(text: str) -> bool:
    if extract_preference_tags(text):
        return True
    return any(hint in text for hint in _PREFERENCE_MEMORY_HINTS)


def estimate_information_density(text: str) -> float:
    if not text:
        return 0.0
    tokens = [token for token in text.split(" ") if token]
    if not tokens:
        return 0.0
    distinct_ratio = len(set(tokens)) / len(tokens)
    length_bonus = min(len(text) / 30.0, 1.0)
    return round((distinct_ratio * 0.6) + (length_bonus * 0.4), 4)


def bucketize_recency(created_at: str) -> str:
    created = datetime.fromisoformat(created_at.replace("Z", "+00:00")).astimezone(UTC)
    now = datetime.now(UTC)
    age_days = max((now - created).days, 0)
    if age_days <= 30:
        return "last_30d"
    if age_days <= 90:
        return "last_90d"
    if age_days <= 365:
        return "last_365d"
    return "older"


def build_chat_message_metadata(*, content: str, created_at: str) -> ChatMessageMetadata:
    normalized = normalize_chat_text(content)
    return ChatMessageMetadata(
        content_normalized=normalized,
        content_fingerprint=fingerprint_chat_text(normalized),
        preference_tags=extract_preference_tags(content),
        topic_tags=extract_topic_tags(content),
        symbol_mentions=extract_symbol_mentions(content),
        is_preference_memory=is_preference_memory(content),
        information_density=estimate_information_density(normalized),
        recency_bucket=bucketize_recency(created_at),
    )


def build_recall_query_context(
    *,
    current_user_message: str,
    recent_user_messages: Sequence[str],
) -> RecallQueryContext:
    recent_context = " | ".join(message.strip() for message in recent_user_messages if message.strip())
    aggregate_text = " ".join([*recent_user_messages, current_user_message])
    return RecallQueryContext(
        embedding_text="\n".join(
            [
                f"current_user_message={current_user_message.strip() or 'none'}",
                f"recent_user_context={recent_context or 'none'}",
            ]
        ),
        preference_tags=extract_preference_tags(aggregate_text),
        topic_tags=extract_topic_tags(aggregate_text),
        symbol_mentions=extract_symbol_mentions(aggregate_text),
    )


def _extract_tags(
    text: str,
    patterns: Sequence[tuple[str, Sequence[str]]],
) -> tuple[str, ...]:
    seen: set[str] = set()
    tags: list[str] = []
    for tag, keywords in patterns:
        if any(keyword in text for keyword in keywords) and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tuple(tags)
