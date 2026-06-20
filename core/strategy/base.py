"""Strategy 基类 + 参数声明。

设计要点：
- 策略只产出 `signal` 列（1 做多 / -1 做空 / 0 空仓），下游组合/回测/实盘统一消费。
- 参数用类属性 Param 声明，元类自动收集到 _param_list，UI 据此自动渲染控件。
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any
import pandas as pd


@dataclass
class Param:
    name: str
    default: Any
    min: float = None
    max: float = None
    step: float = None
    options: list = None
    label: str = ""
    help: str = ""

    @property
    def kind(self) -> str:
        """控件类型，供 UI 渲染。"""
        if self.options is not None:
            return "select"
        if self.min is not None and self.max is not None:
            return "slider"
        return "number"


class _StrategyMeta(type):
    """元类：收集类属性中的 Param（含继承），挂到 cls._param_list。"""
    def __new__(mcs, name, bases, namespace):
        cls = super().__new__(mcs, name, bases, namespace)
        merged: dict[str, Param] = {}
        for b in bases:
            for p in getattr(b, "_param_list", []):
                merged[p.name] = p
        for k, v in namespace.items():
            if isinstance(v, Param):
                merged[k] = v
        cls._param_list = list(merged.values())
        return cls


class Strategy(metaclass=_StrategyMeta):
    # 元数据
    name: str = ""              # 唯一标识（registry key、文件名）
    display_name: str = ""      # UI 显示名
    description: str = ""
    side_mode: str = "long_short"   # long_only | long_short
    version: str = "1.0"

    def __init__(self, **kwargs):
        self.p: dict[str, Any] = {}
        for param in self._param_list:
            val = kwargs.get(param.name, param.default)
            setattr(self, param.name, val)
            self.p[param.name] = val

    @classmethod
    def param_schema(cls) -> list[Param]:
        return list(getattr(cls, "_param_list", []))

    @classmethod
    def default_params(cls) -> dict:
        return {p.name: p.default for p in cls.param_schema()}

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """输入 OHLCV df，返回含 'signal' 列(1/-1/0)的 df，行数不变。"""
        raise NotImplementedError(f"{self.__class__.__name__} 未实现 generate_signals")

    def __repr__(self):
        return f"<{self.__class__.__name__} name={self.name!r} params={self.p}>"
