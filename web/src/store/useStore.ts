import { create } from 'zustand'
import { api } from '../api/client'
import type { StrategyInstance, StrategyGroup } from '../api/types'

interface AppState {
  strategies: StrategyInstance[]
  groups: StrategyGroup[]
  refreshStrategies: () => Promise<void>
  refreshGroups: () => Promise<void>
}

export const useStore = create<AppState>((set) => ({
  strategies: [],
  groups: [],
  refreshStrategies: async () => {
    const { strategies } = await api.listStrategies()
    set({ strategies })
  },
  refreshGroups: async () => {
    const { groups } = await api.listGroups()
    set({ groups })
  },
}))
