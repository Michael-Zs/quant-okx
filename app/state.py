"""session_state 集中读写封装，避免 key 散落与拼写不一致。"""
import streamlit as st


def get(key, default=None):
    return st.session_state.get(key, default)


def set(key, value):
    st.session_state[key] = value
    return value


def ensure_registry():
    """确保策略注册表已发现（内置 + 用户）。幂等。"""
    if not st.session_state.get("_registry_loaded"):
        from core.strategy.registry import StrategyRegistry
        StrategyRegistry.discover_all()
        st.session_state["_registry_loaded"] = True


def coin_options() -> list[str]:
    """可交易合约品种列表（OKX USDT 永续，常用置顶，带会话缓存）。

    新增币种零改动：自动从 OKX 拉取全部上市品种，UI 可搜索选择。
    """
    from core.data.fetcher import list_swap_instruments
    from core.data.symbols import COMMON_SYMBOLS
    if "_swap_symbols" not in st.session_state:
        try:
            st.session_state["_swap_symbols"] = list_swap_instruments()
        except Exception:
            st.session_state["_swap_symbols"] = list(COMMON_SYMBOLS)
    all_syms = st.session_state["_swap_symbols"]
    top = [s for s in COMMON_SYMBOLS if s in all_syms]
    return top + [s for s in all_syms if s not in top]
