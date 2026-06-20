"""多币策略上下文 + 特征注册表。

特征（feature）是可复用的指标计算函数，通过 @feature 注册；策略通过
ctx.feature(name, symbol, **kw) 取单币种特征，或 ctx.cross_section(name, **kw)
取 time×symbol 截面 DataFrame（轮动/排名用）。

新增特征 = 写一个 @feature 函数，不改任何框架代码（开闭原则）。
"""
from __future__ import annotations
from dataclasses import dataclass, field
import pandas as pd

_FEATURES: dict[str, callable] = {}


def feature(name: str):
    """特征注册装饰器。函数签名 (ctx, symbol, **kwargs) -> pd.Series（与 ctx.data[symbol] 等长）。"""
    def deco(fn):
        _FEATURES[name] = fn
        return fn
    return deco


def get_feature(name: str, ctx: "Context", symbol: str, **kwargs) -> pd.Series:
    if name not in _FEATURES:
        raise KeyError(f"未知特征: {name}（可用: {sorted(_FEATURES)}）")
    return _FEATURES[name](ctx, symbol, **kwargs)


def list_features() -> list[str]:
    return sorted(_FEATURES)


@dataclass
class Context:
    """多币策略上下文。data 已对齐（各 symbol 同长度同 ts）。"""
    data: dict[str, pd.DataFrame]
    bar: str = "1H"
    _cache: dict = field(default_factory=dict)

    @property
    def symbols(self) -> list[str]:
        return list(self.data.keys())

    def ts(self) -> pd.Series:
        """公共时间轴。"""
        first = next(iter(self.data.values()))
        return first["ts"]

    def feature(self, name: str, symbol: str, **kw) -> pd.Series:
        """单币种特征 Series（按位置对齐 data[symbol] 的行）。"""
        key = (name, symbol, tuple(sorted(kw.items())))
        if key not in self._cache:
            self._cache[key] = get_feature(name, self, symbol, **kw)
        return self._cache[key]

    def cross_section(self, name: str, **kw) -> pd.DataFrame:
        """time×symbol 截面 DataFrame（各 symbol 同长度，按位置对齐）。"""
        cols = {sym: self.feature(name, sym, **kw) for sym in self.data}
        return pd.DataFrame(cols)


# ---------------- 内置特征 ----------------

@feature("momentum")
def _momentum(ctx: Context, symbol: str, period: int = 20) -> pd.Series:
    """过去 period 根的收益率（动量）。"""
    close = ctx.data[symbol]["close"]
    return close.pct_change(int(period))


@feature("returns")
def _returns(ctx: Context, symbol: str, period: int = 1) -> pd.Series:
    return ctx.data[symbol]["close"].pct_change(int(period))


@feature("volatility")
def _volatility(ctx: Context, symbol: str, period: int = 20) -> pd.Series:
    ret = ctx.data[symbol]["close"].pct_change()
    return ret.rolling(int(period)).std()


@feature("rsi")
def _rsi(ctx: Context, symbol: str, period: int = 14) -> pd.Series:
    delta = ctx.data[symbol]["close"].diff()
    gain = delta.clip(lower=0).rolling(int(period)).mean()
    loss = (-delta.clip(upper=0)).rolling(int(period)).mean()
    rs = gain / loss.replace(0, pd.NA)
    return 100 - 100 / (1 + rs)
