from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class WatchlistEntry:
    code: str
    symbol: str
    name: str
    sector: str


WATCHLIST: tuple[WatchlistEntry, ...] = (
    WatchlistEntry(code="300750", symbol="SZ300750", name="宁德时代", sector="新能源"),
    WatchlistEntry(code="002594", symbol="SZ002594", name="比亚迪", sector="汽车"),
    WatchlistEntry(code="600519", symbol="SH600519", name="贵州茅台", sector="白酒"),
    WatchlistEntry(code="600036", symbol="SH600036", name="招商银行", sector="银行"),
    WatchlistEntry(code="601318", symbol="SH601318", name="中国平安", sector="保险"),
    WatchlistEntry(code="600900", symbol="SH600900", name="长江电力", sector="公用事业"),
    WatchlistEntry(code="000333", symbol="SZ000333", name="美的集团", sector="家电"),
    WatchlistEntry(code="300059", symbol="SZ300059", name="东方财富", sector="金融科技"),
    WatchlistEntry(code="000858", symbol="SZ000858", name="五粮液", sector="白酒"),
    WatchlistEntry(code="600887", symbol="SH600887", name="伊利股份", sector="食品饮料"),
    WatchlistEntry(code="603288", symbol="SH603288", name="海天味业", sector="食品饮料"),
    WatchlistEntry(code="600030", symbol="SH600030", name="中信证券", sector="券商"),
    WatchlistEntry(code="000651", symbol="SZ000651", name="格力电器", sector="家电"),
    WatchlistEntry(code="688981", symbol="SH688981", name="中芯国际", sector="半导体"),
    WatchlistEntry(code="688041", symbol="SH688041", name="海光信息", sector="半导体"),
    WatchlistEntry(code="002475", symbol="SZ002475", name="立讯精密", sector="电子"),
    WatchlistEntry(code="600276", symbol="SH600276", name="恒瑞医药", sector="医药"),
    WatchlistEntry(code="300760", symbol="SZ300760", name="迈瑞医疗", sector="医疗器械"),
    WatchlistEntry(code="603259", symbol="SH603259", name="药明康德", sector="医药服务"),
    WatchlistEntry(code="601138", symbol="SH601138", name="工业富联", sector="先进制造"),
    WatchlistEntry(code="600941", symbol="SH600941", name="中国移动", sector="通信运营"),
    WatchlistEntry(code="601857", symbol="SH601857", name="中国石油", sector="能源"),
    WatchlistEntry(code="601088", symbol="SH601088", name="中国神华", sector="煤炭"),
    WatchlistEntry(code="601899", symbol="SH601899", name="紫金矿业", sector="有色金属"),
)
