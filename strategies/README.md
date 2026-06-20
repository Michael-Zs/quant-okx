# 用户策略目录

把你的策略写成一个 `.py` 文件放在本目录，控制台启动时（或在「策略实验室」页保存后）会**自动发现并注册**，无需改任何配置。

## 规则

- 文件名须是合法 Python 标识符（字母/数字/下划线，不以数字开头），建议与策略 `name` 一致。
- 文件内定义一个继承 `core.strategy.base.Strategy` 的类，设置 `name`，实现 `generate_signals`。
- 以 `_` 开头或 `.example` 结尾的文件会被跳过。

## 模板

```python
from core.strategy.base import Strategy, Param
import pandas as pd


class MyStrategy(Strategy):
    name = "my_strategy"          # 唯一标识（registry key）
    display_name = "我的策略"
    description = "一句话描述"
    side_mode = "long_short"       # 或 long_only

    period = Param("period", 20, 5, 100, 1, label="周期")  # UI 自动生成控件

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = df.copy()
        # 你的逻辑：df 含 ts/open/high/low/close/vol
        df["signal"] = 0           # 1 做多 / -1 做空 / 0 空仓
        df["trade"] = df["signal"].diff().fillna(0).astype(int)
        return df
```

保存后到「数据与回测」页即可选用，或到「策略实验室」页在线编辑（编辑器保存即重载）。
