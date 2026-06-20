import type { TemplateInfo, StrategyInstance, StrategyGroup, Deployment, NodeSpec, BacktestMetrics } from './types'

// API token：每次请求动态读 localStorage（用户在侧边栏设置入口填），回退默认
function getToken(): string {
  return localStorage.getItem('api_token') || 'change_me'
}

async function req<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`/api${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Token': getToken(),
      ...(options.headers || {}),
    },
  })
  if (!res.ok) {
    throw new Error(`${res.status}: ${await res.text()}`)
  }
  return res.json()
}

export const api = {
  // 模板
  templates: () => req<{ templates: TemplateInfo[]; count: number }>('/templates'),
  // 可用合约列表（搜索选择用）
  instruments: () => req<{ instruments: string[]; fallback?: boolean }>('/instruments'),

  // 策略实例
  listStrategies: () => req<{ strategies: StrategyInstance[] }>('/strategies'),
  createStrategy: (data: { name: string; template_name: string; strategy_kind: string; params: Record<string, number | string>; description?: string }) =>
    req<StrategyInstance>('/strategies', { method: 'POST', body: JSON.stringify(data) }),
  deleteStrategy: (id: string) => req<{ id: string; deleted: boolean }>(`/strategies/${id}`, { method: 'DELETE' }),

  // 策略组
  listGroups: () => req<{ groups: StrategyGroup[] }>('/groups'),
  createGroup: (data: { name: string; spec: NodeSpec; description?: string }) =>
    req<StrategyGroup>('/groups', { method: 'POST', body: JSON.stringify(data) }),
  updateGroup: (id: string, data: { spec?: NodeSpec; name?: string }) =>
    req<StrategyGroup>(`/groups/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
  deleteGroup: (id: string) => req<{ id: string; deleted: boolean }>(`/groups/${id}`, { method: 'DELETE' }),

  // 部署
  listDeployments: () => req<{ deployments: Deployment[] }>('/deployments'),
  createDeployment: (data: Record<string, unknown>) =>
    req<Deployment>('/deployments', { method: 'POST', body: JSON.stringify(data) }),
  startDeployment: (id: string) => req<{ deployment_id: string; status: string }>(`/deployments/${id}/start`, { method: 'POST' }),
  stopDeployment: (id: string) => req<{ deployment_id: string; stopped: boolean }>(`/deployments/${id}/stop`, { method: 'POST' }),
  deleteDeployment: (id: string) => req(`/deployments/${id}`, { method: 'DELETE' }),
  deploymentState: (id: string) => req<Record<string, unknown>>(`/deployments/${id}/state`),
  deploymentLogs: (id: string) => req<{ logs: Record<string, unknown>[] }>(`/deployments/${id}/logs`),

  // 回测
  backtest: (data: Record<string, unknown>) =>
    req<{ backtest_id: string; metrics: BacktestMetrics; report_kind: string; n_trades: number; equity_start: number; equity_end: number }>(
      '/backtest', { method: 'POST', body: JSON.stringify(data) }),
}

// WS 实时回测预览（组合页拖动时推送）
export function openBacktestWS(onMessage: (data: Record<string, unknown>) => void): WebSocket {
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const ws = new WebSocket(`${proto}://${location.host}/ws/backtest`)
  ws.onmessage = (e) => {
    try { onMessage(JSON.parse(e.data)) } catch { /* ignore */ }
  }
  return ws
}
