from datetime import UTC, datetime, timedelta

from financehub_market_api.cache import RedisSnapshotCache, SnapshotCache, build_snapshot_cache


class MutableClock:
    def __init__(self, current: datetime) -> None:
        self._current = current

    def now(self) -> datetime:
        return self._current

    def advance(self, *, seconds: int) -> None:
        self._current = self._current + timedelta(seconds=seconds)


class FakeRedis:
    def __init__(self) -> None:
        self._items: dict[str, dict[bytes, bytes]] = {}

    def hset(self, key: str, mapping: dict[bytes, bytes]) -> int:
        self._items[key] = dict(mapping)
        return 1

    def hgetall(self, key: str) -> dict[bytes, bytes]:
        value = self._items.get(key)
        if value is None:
            return {}
        return dict(value)

    def delete(self, key: str) -> int:
        self._items.pop(key, None)
        return 1

    def set_hash(self, key: str, value: dict[bytes, bytes]) -> None:
        self._items[key] = value


class FailingRedis(FakeRedis):
    def hset(self, key: str, mapping: dict[bytes, bytes]) -> int:
        raise RuntimeError("write failure")

    def hgetall(self, key: str) -> dict[bytes, bytes]:
        raise RuntimeError("read failure")

    def delete(self, key: str) -> int:
        raise RuntimeError("delete failure")


def test_get_returns_cached_value_before_expiry() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 12, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=300, now=clock.now)

    cache.put("market:overview", {"status": "fresh"})

    clock.advance(seconds=299)
    assert cache.get("market:overview") == {"status": "fresh"}


def test_get_returns_none_after_expiry_but_peek_returns_last_value() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 12, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=300, now=clock.now)

    cache.put("market:overview", {"status": "stale"})

    clock.advance(seconds=300)
    assert cache.get("market:overview") is None
    assert cache.peek("market:overview") == {"status": "stale"}


def test_put_replaces_value_and_resets_expiry_window() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 12, 0, tzinfo=UTC))
    cache = SnapshotCache(ttl_seconds=300, now=clock.now)

    cache.put("market:overview", {"version": 1})
    clock.advance(seconds=250)
    cache.put("market:overview", {"version": 2})
    clock.advance(seconds=100)

    assert cache.get("market:overview") == {"version": 2}


def test_redis_snapshot_cache_returns_fresh_value_before_fresh_until() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 12, 0, tzinfo=UTC))
    cache = RedisSnapshotCache(redis_client=FakeRedis(), ttl_seconds=300, now=clock.now)

    cache.put("market:overview", {"status": "fresh"})

    clock.advance(seconds=299)
    assert cache.get("market:overview") == {"status": "fresh"}


def test_redis_snapshot_cache_returns_none_after_fresh_expiry_but_peek_keeps_value() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 12, 0, tzinfo=UTC))
    cache = RedisSnapshotCache(redis_client=FakeRedis(), ttl_seconds=300, now=clock.now)

    cache.put("market:overview", {"status": "stale"})

    clock.advance(seconds=301)
    assert cache.get("market:overview") is None
    assert cache.peek("market:overview") == {"status": "stale"}


def test_build_snapshot_cache_uses_redis_when_url_is_configured() -> None:
    redis_client = FakeRedis()
    cache = build_snapshot_cache(
        environ={"FINANCEHUB_MARKET_CACHE_REDIS_URL": "redis://localhost:6379/0"},
        redis_factory=lambda _: redis_client,
    )

    assert isinstance(cache, RedisSnapshotCache)


def test_build_snapshot_cache_falls_back_to_memory_when_factory_raises() -> None:
    cache = build_snapshot_cache(
        redis_factory=lambda _: (_ for _ in ()).throw(RuntimeError("redis unavailable"))
    )

    assert isinstance(cache, SnapshotCache)
    assert not isinstance(cache, RedisSnapshotCache)


def test_build_snapshot_cache_uses_default_url_for_explicit_empty_environ() -> None:
    seen_urls: list[str] = []
    cache = build_snapshot_cache(
        environ={},
        redis_factory=lambda url: seen_urls.append(url) or FakeRedis(),
    )

    assert isinstance(cache, RedisSnapshotCache)
    assert seen_urls == ["redis://127.0.0.1:6379/0"]


def test_build_snapshot_cache_passes_configured_url_to_redis_factory() -> None:
    seen_urls: list[str] = []
    cache = build_snapshot_cache(
        environ={"FINANCEHUB_MARKET_CACHE_REDIS_URL": "redis://cache.internal:6379/9"},
        redis_factory=lambda url: seen_urls.append(url) or FakeRedis(),
    )

    assert isinstance(cache, RedisSnapshotCache)
    assert seen_urls == ["redis://cache.internal:6379/9"]


def test_redis_snapshot_cache_treats_malformed_data_as_cache_miss_and_deletes() -> None:
    redis = FakeRedis()
    cache = RedisSnapshotCache(redis_client=redis)
    key = "financehub:market:snapshot:market:overview"
    redis.set_hash(
        key,
        {
            b"value": b"not-json",
            b"stored_at": b"2026-04-02T12:00:00+00:00",
            b"fresh_until": b"2026-04-02T12:05:00+00:00",
        },
    )

    assert cache.get("market:overview") is None
    assert cache.peek("market:overview") is None
    assert redis.hgetall(key) == {}


def test_redis_snapshot_cache_deletes_structurally_invalid_json_payload_without_poisoning_redis() -> None:
    redis = FakeRedis()
    cache = RedisSnapshotCache(redis_client=redis)
    key = "financehub:market:snapshot:stock-snapshot"
    redis.set_hash(
        key,
        {
            b"value": (
                b'{"kind":"stock_price_snapshot","data":{"as_of_date":"2026-04-02"}}'
            ),
            b"stored_at": b"2026-04-02T12:00:00+00:00",
            b"fresh_until": b"2026-04-02T12:05:00+00:00",
        },
    )

    assert cache.get("stock-snapshot") is None
    assert redis.hgetall(key) == {}

    cache.put("stock-snapshot", {"ok": True})
    assert cache.get("stock-snapshot") == {"ok": True}


def test_build_snapshot_cache_runtime_redis_errors_fall_back_to_memory_cache() -> None:
    clock = MutableClock(datetime(2026, 4, 2, 12, 0, tzinfo=UTC))
    cache = build_snapshot_cache(
        redis_factory=lambda _: FailingRedis(),
        now=clock.now,
    )

    cache.put("market:overview", {"status": "fresh"})
    assert cache.get("market:overview") == {"status": "fresh"}
