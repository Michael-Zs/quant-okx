"""对 AI 友好的 REST API 使用规范（可直接复制粘贴给 Agent / 外部脚本）。

与 core/strategy/spec.py 的策略开发规范平行：那份教 AI「写策略」，这份教 AI「调 API」。
通过 GET /api/api_spec 暴露，前端「设置」页可一键复制/下载。
"""

API_SPEC = """# OKX 量化交易控制台 · REST API 规范（供 Agent / 外部脚本使用）

你将通过 REST API 操控「OKX 量化交易控制台」：查询策略模板、回测、保存策略实例与
策略组、部署实盘、监控持仓。本规范是权威契约，照此调用即可，无需猜测。

## 1. 基础信息
- **Base URL**：`http://127.0.0.1:8787`（仅监听本机，不对外暴露）
- **Swagger 文档**：`http://127.0.0.1:8787/docs`（交互式，可在线试调）
- **数据格式**：JSON；请求体 `Content-Type: application/json`
- **实时回测 WebSocket**：`ws://127.0.0.1:8787/ws/backtest`

## 2. 鉴权
- **监控类 GET**：公开，无需 token。
- **控制类 POST / PUT / DELETE**：必须带请求头 `X-API-Token: <token>`。
- token 来自服务端 `.env` 的 `API_TOKEN`（占位值 `change_me`；本机常用 `quant_okx_local_token_change_me`）。
- 通过 `GET /api/config` 的 `api_token_set` 字段可知是否仍是默认值。
- 缺失/错误 token → `401 Unauthorized`。

```bash
TOKEN=quant_okx_local_token_change_me
curl -H "X-API-Token: $TOKEN" http://127.0.0.1:8787/api/balance?is_demo=true
```

## 3. 全局约定
- **symbol**：OKX 永续合约格式，如 `BTC-USDT-SWAP`、`ETH-USDT-SWAP`、`SOL-USDT-SWAP`。用 `GET /api/instruments` 拉全量可搜索列表。
- **bar（周期）**：大写，`1H` / `4H` / `1D`。
- **strategy_kind**：`single`（单币，一次一个品种）或 `multi`（多币，接收品种池做截面择优）。
- **template_name**：策略在注册表里的 key（如 `ma_cross`、`rsi`、`momentum_rotation`），用 `GET /api/templates` 拿全量 + 参数 schema。
- **指标字段**（`BacktestMetrics`）：`total_return / annual_return / max_drawdown / sharpe / sortino / calmar / volatility / win_rate / profit_factor / n_trades / final_capital`。收益率/回撤/胜率是小数（0.12 = 12%）。

> ⚠️ **余额 vs 权益**：API 返回两个字段——
> - `balance`：**可用余额**（free USDT，不含已占用保证金）
> - `equity`：**总权益**（free + 保证金 + 浮盈 + 其他币种折 USDT，对应 OKX App 显示的账户权益）
>
> 判断盈亏请用 `equity` 对比 `initial_capital`。

## 4. 端点速查

### 监控类（GET，公开）
| 方法 路径 | 用途 |
|---|---|
| `GET /api/health` | 健康检查 → `{status:"ok"}` |
| `GET /api/templates` | **策略模板列表**（含单/多币 + 参数 schema），回测/保存前先查这个 |
| `GET /api/instruments` | 可用合约列表（供品种搜索） |
| `GET /api/market/{symbol}?bar=1H&days=7` | 某品种行情摘要（首尾 K 线） |
| `GET /api/config` | 服务端配置（OKX 是否配置、默认参数、缓存大小、token 是否默认） |
| `GET /api/user_strategies` | `strategies/` 目录下用户保存的 `.py` 代码文件列表 |
| `GET /api/strategy_spec?kind=single\|multi` | AI 策略开发规范文本（给 Agent 写策略用） |
| `GET /api/deployments` | 部署列表（含 `alive` 运行状态） |
| `GET /api/deployments/{did}/state` | 部署实时状态（含 `balance` 可用余额 + `equity` 总权益） |
| `GET /api/deployments/{did}/logs?n=50` | 部署事件日志 |
| `GET /api/backtests?ref_id=&node_kind=&limit=50` | 回测历史列表 |
| `GET /api/backtests/{bid}?with_equity=true` | 单次回测详情（含权益曲线） |
| `GET /api/balance?is_demo=true` ⚑ | 账户余额（返回 `balance` 可用 + `equity` 总权益） |
| `GET /api/positions?is_demo=true&symbol=BTC-USDT-SWAP` ⚑ | 当前持仓（需 token） |

### 策略实例 CRUD（GET 公开 / 写需 token）
「策略实例」= 模板 + 一组参数（+ 可选 bar/days/symbols/invert），可命名复用。

| 方法 路径 | 用途 |
|---|---|
| `GET /api/strategies` | 列出全部实例 |
| `POST /api/strategies` ⚑ | 新建（需 token） |
| `GET /api/strategies/{sid}` | 详情 |
| `PUT /api/strategies/{sid}` ⚑ | 更新（需 token） |
| `DELETE /api/strategies/{sid}` ⚑ | 删除（需 token） |

### 策略组 CRUD（GET 公开 / 写需 token）
「策略组」= 一棵 node 树（多个实例按资金/信号合成），存 `spec`（node 树 JSON）。

| 方法 路径 | 用途 |
|---|---|
| `GET /api/groups` | 列出全部组 |
| `POST /api/groups` ⚑ | 新建（需 token） |
| `GET /api/groups/{gid}` | 详情 |
| `PUT /api/groups/{gid}` ⚑ | 更新（需 token） |
| `DELETE /api/groups/{gid}` ⚑ | 删除（需 token） |
| `POST /api/groups/validate` ⚑ | 校验 node 树能否重建（预检，需 token） |

### 控制类（全部需 token）
| 方法 路径 | 用途 |
|---|---|
| `POST /api/backtest` | **统一回测**（吃 node_spec 或 ref_id，落 backtests 表） |
| `POST /api/multi_backtest` | 多币回测（返回 per_symbol 明细 + holdings 矩阵） |
| `POST /api/grid_search` | 参数网格搜索（穷举组合 → 按 metric 排序） |
| `POST /api/user_strategies` | 保存用户策略 `.py` 到 strategies/ 并重载注册表 |
| `DELETE /api/user_strategies/{name}` | 删除用户策略文件 |
| `POST /api/deployments` ⚑ | 新建部署（需先有 group） |
| `PUT /api/deployments/{did}` ⚑ | 更新部署配置 |
| `POST /api/deployments/{did}/start` | 启动部署（拉起后台 daemon） |
| `POST /api/deployments/{did}/stop` | 停止部署 |
| `DELETE /api/deployments/{did}` | 删除部署 |
| `POST /api/config/env` | 写 OKX 凭证到 `.env` |
| `POST /api/cache/clear` | 清空 K 线缓存 |

⚑ = 需 `X-API-Token`。

## 5. 核心数据结构

### ParamSchema（参数声明，UI/校验用）
```json
{"name":"ma_fast","default":20,"label":"快线周期","kind":"slider",
 "min":2,"max":200,"step":1,"options":null}
```
`kind`：`slider`（有 min/max/step）/ `select`（有 options）/ `number`（仅 default）。

### NodeSpec（策略组的核心，递归 node 树）
三种 node_type，可嵌套：
```json
// 叶子：单个策略实例
{"node_type":"leaf","name":"我的MA","template_name":"ma_cross",
 "strategy_kind":"single","params":{"ma_fast":20,"ma_slow":60},"invert":false}

// 信号组合器：多子信号按 mode 合成（vote/majority/and/or/weighted）
{"node_type":"signal_combiner","name":"combo","mode":"vote",
 "children":[{"node":<NodeSpec>,"weight":1,"invert":false}, ...],"invert":false}

// 资金分配组：各子按 weight 切分资金独立持仓（资金层组合）
{"node_type":"allocation_group","name":"group",
 "children":[{"node":<NodeSpec>,"weight":0.6,"invert":false}, ...],"invert":false}
```
`invert` 是链路级（多层叠加 = XOR）。

### StrategyInstance（策略实例）
```json
{"id":"str_xxx","name":"我的MA","template_name":"ma_cross","strategy_kind":"single",
 "params":{"ma_fast":20,"ma_slow":60},"side_mode":"long_short","description":"",
 "bar":"1H","days":180,"symbols":["BTC-USDT-SWAP"],"invert":false,
 "created_at":"...","updated_at":"..."}
```

### GroupRefSpec（部署里引用策略组）
```json
{"group_id":"grp_xxx","weight":1.0,"invert":false}
```

### 账户余额响应
```jsonc
// GET /api/balance
{
  "balance": 97785.63,      // 可用余额（free USDT）
  "equity":  106897.74,     // 总权益 = free + margin + upnl + 其他币种折USDT
  "is_demo": true
}

// GET /api/deployments/{did}/state 也包含 balance + equity
{
  "deployment_id": "dep_xxx",
  "balance": 97766.13,      // 可用余额
  "equity":  106906.32,     // 总权益
  "positions": {...},
  "actions": ["BTC-USDT-SWAP hold"],
  ...
}
```

## 6. 端到端工作流（复制即用）

### 工作流 A：发现模板 → 回测一个单币策略
```bash
TOKEN=quant_okx_local_token_change_me
# 1) 看有哪些策略 + 参数
curl http://127.0.0.1:8787/api/templates
# 2) 内联 node_spec 直接回测
curl -X POST http://127.0.0.1:8787/api/backtest \\
  -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" \\
  -d '{"node_spec":{"node_type":"leaf","name":"bt","template_name":"ma_cross",
                     "strategy_kind":"single","params":{"ma_fast":20,"ma_slow":60}},
       "symbol":"BTC-USDT-SWAP","bar":"1H","days":180}'
# → {backtest_id, metrics, n_trades, equity_start, equity_end}
# 3) 拿完整权益曲线
curl "http://127.0.0.1:8787/api/backtests/<backtest_id>?with_equity=true"
```

### 工作流 B：保存策略实例 → 按引用回测
```bash
# 1) 存
SID=$(curl -sX POST http://127.0.0.1:8787/api/strategies \\
  -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" \\
  -d '{"name":"我的MA_v1","template_name":"ma_cross","strategy_kind":"single",
       "params":{"ma_fast":20,"ma_slow":60},"bar":"1H","days":180,
       "symbols":["BTC-USDT-SWAP"],"invert":false}' | jq -r .id)
# 2) 按 ref 回测（ref_kind=strategy）
curl -X POST http://127.0.0.1:8787/api/backtest \\
  -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" \\
  -d "{\"ref_kind\":\"strategy\",\"ref_id\":\"$SID\",\"bar\":\"1H\",\"days\":180}"
```

### 工作流 C：建策略组（资金分配）→ 回测 → 部署实盘
```bash
# 假设已有两个策略实例 str_aaa、str_bbb
# 1) 存策略组（allocation_group：60% A + 40% B）
GID=$(curl -sX POST http://127.0.0.1:8787/api/groups \\
  -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" \\
  -d '{"name":"我的组合","description":"MA+RSI 资金层组合",
       "spec":{"node_type":"allocation_group","name":"我的组合","invert":false,
               "children":[
                 {"node":{"node_type":"leaf","name":"a","template_name":"ma_cross",
                          "strategy_kind":"single","params":{},"invert":false},
                  "weight":0.6,"invert":false},
                 {"node":{"node_type":"leaf","name":"b","template_name":"rsi",
                          "strategy_kind":"single","params":{},"invert":false},
                  "weight":0.4,"invert":false}]}}' | jq -r .id)
# 2) 按组回测
curl -X POST http://127.0.0.1:8787/api/backtest \\
  -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" \\
  -d "{\"ref_kind\":\"group\",\"ref_id\":\"$GID\",\"symbol\":\"BTC-USDT-SWAP\",\"bar\":\"1H\",\"days\":180}"
# 3) 建部署（模拟盘）→ 启动 → 看状态 → 停止
DID=$(curl -sX POST http://127.0.0.1:8787/api/deployments \\
  -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" \\
  -d "{\"name\":\"我的部署\",\"is_demo\":true,\"bar\":\"1H\",
       \"symbols\":[\"BTC-USDT-SWAP\"],\"groups\":[{\"group_id\":\"$GID\",\"weight\":1,\"invert\":false}],
       \"leverage\":5,\"position_ratio\":0.1,\"initial_capital\":10000}" | jq -r .id)
curl -X POST http://127.0.0.1:8787/api/deployments/$DID/start -H "X-API-Token: $TOKEN"
curl http://127.0.0.1:8787/api/deployments/$DID/state
# → 返回 balance（可用余额）+ equity（总权益），盈亏看 equity 对比 initial_capital
curl http://127.0.0.1:8787/api/deployments/$DID/logs?n=20
curl -X POST http://127.0.0.1:8787/api/deployments/$DID/stop -H "X-API-Token: $TOKEN"
```

### 工作流 D：多币回测（看各币贡献 + 持仓热力图数据）
```bash
curl -X POST http://127.0.0.1:8787/api/multi_backtest \\
  -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" \\
  -d '{"node_spec":{"node_type":"leaf","name":"mr","template_name":"momentum_rotation",
                     "strategy_kind":"multi","params":{"period":24,"top_k":1,"rebalance":24}},
       "symbols":["BTC-USDT-SWAP","ETH-USDT-SWAP","SOL-USDT-SWAP"],
       "bar":"1H","days":180,
       "allocation":{"BTC-USDT-SWAP":1.0,"ETH-USDT-SWAP":1.0,"SOL-USDT-SWAP":1.0}}'
# → {metrics, equity:{ts,equity}, per_symbol:[{symbol,weight,metrics,equity}],
#     holdings:{ts,symbols,matrix}, initial_capital}
```

### 工作流 E：参数网格搜索
```bash
curl -X POST http://127.0.0.1:8787/api/grid_search \\
  -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" \\
  -d '{"template_name":"ma_cross",
       "param_ranges":{"ma_fast":[10,40,5],"ma_slow":[40,120,10]},
       "symbol":"BTC-USDT-SWAP","bar":"1H","days":180,"metric":"sharpe","n_jobs":4}'
# → {results:[{ma_fast,ma_slow,total_return,sharpe,...}, ...]（按 metric 降序）,
#     keys:["ma_fast","ma_slow"], metric:"sharpe", count:N}
```

### 工作流 F：让控制台「学会」一个新策略（写 .py 保存即注册）
先 `GET /api/strategy_spec?kind=single`（或 `multi`）拿到策略开发规范，让 Agent 按规范产出代码，然后：
```bash
curl -X POST http://127.0.0.1:8787/api/user_strategies \\
  -H "X-API-Token: $TOKEN" -H "Content-Type: application/json" \\
  -d '{"name":"my_breakout","code":"<完整 .py 内容，含转义>"}'
# → {ok:true, name, registered:true, names:[...]}  registered=false 表示代码有错
```
之后该策略即出现在 `GET /api/templates` 列表里，可像内置策略一样回测/部署。

## 7. 监控部署盈亏

部署运行后，通过 state 端点获取盈亏信息：

```bash
# 获取状态（balance=可用余额, equity=总权益）
curl http://127.0.0.1:8787/api/deployments/$DID/state

# 响应示例：
# {
#   "balance": 97766.13,       ← 可用 USDT（可用于开仓）
#   "equity":  106906.32,      ← 总权益（对应 OKX App 显示的账户权益，含保证金+BTC等）
#   "positions": {
#     "BTC-USDT-SWAP": {
#       "entry_price": 64390.0,
#       "price": 64269.7,
#       "unrealized_pnl": -32.54,
#       "position_contracts": 37.97,
#       "position_dir": 1
#     }
#   },
#   "actions": ["BTC-USDT-SWAP hold"],
#   "status": "running"
# }
#
# 盈亏 = equity - initial_capital（部署时设定的值）
```

## 8. WebSocket：实时回测预览
前端调参时用，低延迟。Agent 一般用 `POST /api/backtest` 即可，但若要流式预览：
```js
const ws = new WebSocket('ws://127.0.0.1:8787/ws/backtest')
ws.onopen = () => ws.send(JSON.stringify({
  node_spec: {node_type:'leaf',name:'bt',template_name:'ma_cross',
              strategy_kind:'single',params:{ma_fast:20,ma_slow:60}},
  symbols: ['BTC-USDT-SWAP'], bar: '1H', days: 180, initial_capital: 10000
}))
ws.onmessage = (e) => {
  const d = JSON.parse(e.data)
  // 成功：{metrics, equity:{ts,equity}, report_kind, n_trades}
  // 失败：{error: "..."}
}
```

## 9. 错误处理
- `400`：参数错误 / 数据加载失败 / 策略代码语法错（message 有详情）
- `401`：token 缺失/错误
- `404`：未知 id / 未知策略 / 文件不存在
- `409`：名称冲突（策略实例/组/部署名唯一）
- 回测/策略执行中的异常会被捕获并转成 `400`，不会让服务崩溃。

## 10. Python 调用示例（requests）
```python
import requests
BASE = "http://127.0.0.1:8787"
H = {"X-API-Token": "quant_okx_local_token_change_me", "Content-Type": "application/json"}

# 列模板
templates = requests.get(f"{BASE}/api/templates").json()["templates"]

# 回测
r = requests.post(f"{BASE}/api/backtest", headers=H, json={
    "node_spec": {"node_type":"leaf","name":"bt","template_name":"ma_cross",
                  "strategy_kind":"single","params":{"ma_fast":20,"ma_slow":60}},
    "symbol": "BTC-USDT-SWAP", "bar": "1H", "days": 180,
}).json()
print(r["metrics"]["total_return"], r["metrics"]["sharpe"])

# 查余额（equity 才是总权益）
r = requests.get(f"{BASE}/api/balance?is_demo=true", headers=H).json()
print(f"可用: {r['balance']:.2f}, 总权益: {r['equity']:.2f}")

# 部署实盘 + 轮询状态
d = requests.post(f"{BASE}/api/deployments", headers=H, json={
    "name":"api部署","is_demo":True,"bar":"1H","symbols":["BTC-USDT-SWAP"],
    "groups":[{"group_id":"<gid>","weight":1,"invert":False}],
    "leverage":5,"position_ratio":0.1,"initial_capital":10000,
}).json()
requests.post(f"{BASE}/api/deployments/{d['id']}/start", headers=H)
state = requests.get(f"{BASE}/api/deployments/{d['id']}/state").json()
pnl = state["equity"] - d["initial_capital"]  # 用 equity 算盈亏
print(f"盈亏: {pnl:.2f}")
```

## 11. 重要约束
- **余额 vs 权益**：`balance` = 可用余额（free USDT），`equity` = 总权益（含保证金 + 其他币种折 USDT）。判断盈亏请用 `equity` 对比 `initial_capital`。
- **回测引擎**为复利模型，默认**不建模爆仓**，高杠杆回测偏乐观。
- **实盘有风险**：真实盘（`is_demo:false`）会真实下单，请从模拟盘 + 最小仓位开始。
- **策略代码**拥有完整 Python 权限，仅运行可信代码。
- **symbol/bar 格式**严格按 OKX 格式（大写 bar、`XXX-USDT-SWAP` 合约）。
- 部署的 daemon 是独立进程（`start_new_session`），关 API/浏览器不死，需显式 `stop`。
"""
