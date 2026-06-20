"""根据 Strategy.param_schema() 自动渲染参数控件，返回 {name: value}。"""
import streamlit as st
from core.strategy.base import Strategy


def render_params(strategy_cls: type[Strategy], container=None, key_prefix="") -> dict:
    """在指定容器（默认主区域）渲染策略参数，返回参数字典。"""
    st_ = container or st
    schema = strategy_cls.param_schema()
    if not schema:
        return strategy_cls.default_params()

    params: dict = {}
    # 两列排布控件
    cols = st_.columns(2)
    for i, p in enumerate(schema):
        c = cols[i % 2]
        label = p.label or p.name
        wkey = f"{key_prefix}param_{strategy_cls.name}_{p.name}"
        with c:
            if p.kind == "select":
                opts = list(p.options)
                idx = opts.index(p.default) if p.default in opts else 0
                params[p.name] = st.selectbox(label, opts, index=idx, key=wkey, help=p.help)
            elif p.kind == "slider":
                step = p.step if p.step else (p.max - p.min) / 100.0
                params[p.name] = st.slider(label, float(p.min), float(p.max),
                                           float(p.default), step=float(step),
                                           key=wkey, help=p.help)
            else:
                params[p.name] = st.number_input(label, value=p.default, key=wkey, help=p.help)
    return params


def params_summary(strategy_cls: type[Strategy], params: dict) -> str:
    """生成参数摘要字符串，用于标题展示。"""
    parts = [f"{p.name}={params[p.name]}" for p in strategy_cls.param_schema()]
    return ", ".join(parts)
