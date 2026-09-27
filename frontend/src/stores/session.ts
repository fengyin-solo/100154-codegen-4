import { defineStore } from 'pinia'

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '值班管理员',
    role: '站点管理员',
    shiftLabel: '白班 08:00-20:00',
    scope: '气象观测站网运维平台',
  }),
  getters: {
    canOperate: (state) => state.operator.length > 0,
    isAdmin: (state) => state.role === '站点管理员',
  },
  actions: {
    setShift(label: string) {
      this.shiftLabel = label
    },
    setRole(role: string) {
      this.role = role
    },
    setOperator(name: string) {
      this.operator = name
    },
  },
})
