from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Callable, Protocol

from .upstreams.dolthub import StockPriceSnapshot
from .upstreams.index_data import IndexSnapshot


def _default_now() -> datetime:
    return datetime.now(UTC)


@dataclass
class CacheEntry:
    value: object
    stored_at: datetime
    expires_at: datetime


class SnapshotCache:
    def __init__(
        self,
        ttl_seconds: int = 300,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._ttl_seconds = ttl_seconds
        self._now = now or _default_now
        self._items: dict[str, CacheEntry] = {}

    def get(self, key: str) -> object | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        if self._now() >= entry.expires_at:
            return None
        return entry.value

    def peek(self, key: str) -> object | None:
        entry = self._items.get(key)
        if entry is None:
            return None
        return entry.value

    def put(self, key: str, value: object) -> None:
        stored_at = self._now()
        self._items[key] = CacheEntry(
            value=value,
            stored_at=stored_at,
            expires_at=stored_at + timedelta(seconds=self._ttl_seconds),
        )

    def delete(self, key: str) -> None:
        self._items.pop(key, None)


class RedisLike(Protocol):
    def hset(self, key: str, mapping: dict[bytes, bytes]) -> int: ...

    def hgetall(self, key: str) -> dict[bytes, bytes]: ...

    def delete(self, key: str) -> int: ...


class RedisSnapshotCache(SnapshotCache):
    def __init__(
        self,
        redis_client: RedisLike,
        ttl_seconds: int = 300,
        now: Callable[[], datetime] | None = None,
        key_prefix: str = "financehub:market:snapshot:",
    ) -> None:
        super().__init__(ttl_seconds=ttl_seconds, now=now)
        self._redis = redis_client
        self._key_prefix = key_prefix
        self._fallback = SnapshotCache(ttl_seconds=ttl_seconds, now=now)
        self._redis_unavailable = False

    def get(self, key: str) -> object | None:
        if not self._redis_unavailable:
            try:
                entry = self._read_entry(key)
            except Exception:
                self._redis_unavailable = True
            else:
                if entry is not None:
                    if self._now() >= entry.expires_at:
                        return None
                    return entry.value
        return self._fallback.get(key)

    def peek(self, key: str) -> object | None:
        if not self._redis_unavailable:
            try:
                entry = self._read_entry(key)
            except Exception:
                self._redis_unavailable = True
            else:
                if entry is not None:
                    return entry.value
        return self._fallback.peek(key)

    def put(self, key: str, value: object) -> None:
        self._fallback.put(key, value)
        stored_at = self._now()
        expires_at = stored_at + timedelta(seconds=self._ttl_seconds)
        value_payload = self._serialize_value(value)
        if self._redis_unavailable:
            return
        try:
            self._redis.hset(
                self._full_key(key),
                mapping={
                    b"value": value_payload,
                    b"stored_at": stored_at.isoformat().encode("utf-8"),
                    b"fresh_until": expires_at.isoformat().encode("utf-8"),
                },
            )
        except Exception:
            self._redis_unavailable = True

    def delete(self, key: str) -> None:
        self._fallback.delete(key)
        if self._redis_unavailable:
            return
        try:
            self._redis.delete(self._full_key(key))
        except Exception:
            self._redis_unavailable = True

    def _full_key(self, key: str) -> str:
        return f"{self._key_prefix}{key}"

    def _read_entry(self, key: str) -> CacheEntry | None:
        raw = self._redis.hgetall(self._full_key(key))
        if not raw:
            return None

        value_payload = raw.get(b"value")
        stored_at_text = raw.get(b"stored_at")
        fresh_until_text = raw.get(b"fresh_until")
        if value_payload is None or stored_at_text is None or fresh_until_text is None:
            self.delete(key)
            return None

        try:
            value = self._deserialize_value(value_payload)
            stored_at = datetime.fromisoformat(stored_at_text.decode("utf-8"))
            fresh_until = datetime.fromisoformat(fresh_until_text.decode("utf-8"))
        except (
            KeyError,
            IndexError,
            ValueError,
            TypeError,
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            self.delete(key)
            return None
        return CacheEntry(value=value, stored_at=stored_at, expires_at=fresh_until)

    def _serialize_value(self, value: object) -> bytes:
        if isinstance(value, StockPriceSnapshot):
            payload = {
                "kind": "stock_price_snapshot",
                "data": {
                    "as_of_date": value.as_of_date,
                    "latest_prices": value.latest_prices,
                    "previous_prices": value.previous_prices,
                    "latest_volumes": value.latest_volumes,
                    "latest_amounts": value.latest_amounts,
                    "recent_closes": value.recent_closes,
                },
            }
        elif isinstance(value, dict) and all(
            isinstance(snapshot, IndexSnapshot) for snapshot in value.values()
        ):
            payload = {
                "kind": "index_snapshot_map",
                "data": {
                    name: {
                        "name": snapshot.name,
                        "as_of_date": snapshot.as_of_date,
                        "closes": snapshot.closes,
                    }
                    for name, snapshot in value.items()
                },
            }
        else:
            payload = {"kind": "json", "data": value}
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")

    def _deserialize_value(self, payload: bytes) -> object:
        body = json.loads(payload.decode("utf-8"))
        if not isinstance(body, dict):
            raise ValueError("cached payload must be an object")

        kind = body.get("kind")
        data = body.get("data")
        if kind == "stock_price_snapshot":
            if not isinstance(data, dict):
                raise ValueError("stock payload must be an object")
            return StockPriceSnapshot(
                as_of_date=str(data["as_of_date"]),
                latest_prices={k: float(v) for k, v in dict(data["latest_prices"]).items()},
                previous_prices={
                    k: float(v) for k, v in dict(data["previous_prices"]).items()
                },
                latest_volumes={k: float(v) for k, v in dict(data["latest_volumes"]).items()},
                latest_amounts={k: float(v) for k, v in dict(data["latest_amounts"]).items()},
                recent_closes={
                    symbol: [(str(item[0]), float(item[1])) for item in closes]
                    for symbol, closes in dict(data["recent_closes"]).items()
                },
            )
        if kind == "index_snapshot_map":
            if not isinstance(data, dict):
                raise ValueError("index payload must be an object")
            return {
                name: IndexSnapshot(
                    name=str(snapshot["name"]),
                    as_of_date=str(snapshot["as_of_date"]),
                    closes=[
                        (str(item[0]), float(item[1])) for item in list(snapshot["closes"])
                    ],
                )
                for name, snapshot in data.items()
            }
        if kind == "json":
            return data
        raise ValueError("unsupported cache payload kind")


def build_snapshot_cache(
    *,
    environ: dict[str, str] | None = None,
    redis_factory: Callable[[str], RedisLike] | None = None,
    ttl_seconds: int = 300,
    now: Callable[[], datetime] | None = None,
) -> SnapshotCache:
    env = os.environ if environ is None else environ
    redis_url = env.get(
        "FINANCEHUB_MARKET_CACHE_REDIS_URL",
        "redis://127.0.0.1:6379/0",
    )

    if redis_factory is None:
        try:
            import redis  # type: ignore[import-untyped]
        except ImportError:
            return SnapshotCache(ttl_seconds=ttl_seconds, now=now)
        try:
            redis_client = redis.from_url(redis_url)
        except Exception:
            return SnapshotCache(ttl_seconds=ttl_seconds, now=now)
    else:
        try:
            redis_client = redis_factory(redis_url)
        except Exception:
            return SnapshotCache(ttl_seconds=ttl_seconds, now=now)

    return RedisSnapshotCache(
        redis_client=redis_client,
        ttl_seconds=ttl_seconds,
        now=now,
    )
