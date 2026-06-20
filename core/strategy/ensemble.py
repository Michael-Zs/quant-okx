"""信号组合器（Ensemble）：多个策略的 signal 按规则合成一个最终 signal。

本身只需实现 generate_signals(df) -> df(含 signal 列)，即可像「一个策略」一样
被回测引擎 / 实盘 trader 消费，下游无需感知它是组合。
"""
from __future__ import annotations
import pandas as pd


class Ensemble:
    MODES = ["vote", "majority", "and", "or", "weighted"]

    def __init__(self, sub_strategies: list, mode: str = "vote", weights: dict | None = None):
        if not sub_strategies:
            raise ValueError("Ensemble 至少需要一个子策略")
        self.subs = list(sub_strategies)
        self.mode = mode
        self.weights = weights or {}

    @property
    def name(self) -> str:
        return "ensemble_" + "_".join(getattr(s, "name", "?") for s in self.subs)

    @property
    def display_name(self) -> str:
        return f"组合[{self.mode}](" + "+".join(getattr(s, "name", "?") for s in self.subs) + ")"

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        # 收集各子策略 signal，列对齐到 df.index
        sig = pd.DataFrame(index=df.index)
        for s in self.subs:
            out = s.generate_signals(df)
            sig[getattr(s, "name", id(s))] = out["signal"].fillna(0).astype(int).values

        n = sig.shape[1]
        if self.mode == "and":
            final = sig.eq(1).all(axis=1).astype(int) - sig.eq(-1).all(axis=1).astype(int)
        elif self.mode == "or":
            final = sig.eq(1).any(axis=1).astype(int) - sig.eq(-1).any(axis=1).astype(int)
        elif self.mode == "majority":
            pos = (sig == 1).sum(axis=1)
            neg = (sig == -1).sum(axis=1)
            final = pd.Series(0, index=df.index)
            final[pos > n / 2] = 1
            final[neg > n / 2] = -1
        elif self.mode == "weighted":
            w = {getattr(s, "name", "?"): float(self.weights.get(getattr(s, "name", "?"), 1.0))
                 for s in self.subs}
            ws = pd.Series(w)
            ws = ws / ws.sum()
            net = sig.mul(ws.values, axis=1).sum(axis=1)
            final = pd.Series(0, index=df.index)
            final[net > 0] = 1
            final[net < 0] = -1
        else:  # vote：净票数符号
            net = sig.sum(axis=1)
            final = pd.Series(0, index=df.index)
            final[net > 0] = 1
            final[net < 0] = -1

        out = df.copy()
        out["signal"] = final.astype(int).values
        out["trade"] = out["signal"].diff().fillna(0).astype(int)
        return out
