from financehub_market_api.models import MetricCard
from financehub_market_api.watchlist import WATCHLIST


def test_backend_package_smoke_imports() -> None:
    card = MetricCard(
        label="test",
        value="1",
        delta="+0%",
        tone="neutral",
        changeValue=0.0,
        changePercent=0.0,
    )

    assert card.label == "test"
    assert len(WATCHLIST) >= 20
    assert WATCHLIST[0].name == "宁德时代"
    assert any(entry.name == "中国移动" for entry in WATCHLIST)
