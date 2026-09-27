import { defineStore } from 'pinia'

/** 顶栏可切换的演示身份；真实环境应由登录态决定。 */
export interface RoleOption {
  name: string
  role: string
}

export const ROLE_PRESETS: RoleOption[] = [
  { name: '周凯', role: '值班人员' },
  { name: '林晓', role: '值班人员' },
  { name: '站点管理员', role: '站点管理员' },
]

export const useSessionStore = defineStore('session', {
  state: () => ({
    operator: '周凯',
    role: '值班人员',
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
    switchIdentity(option: RoleOption) {
      this.operator = option.name
      this.role = option.role
    },
  },
})
