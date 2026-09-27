/** 进站许可模块的公共常量与动作请求：列表页和详情页共用，保证两边口径一致。 */
import { request } from '@/api/client'

export const ENDPOINT = '/api/visitor'
export const STATUSES = ['待受理', '已放行', '已进站', '已离站'] as const
export const ROW_ACTIONS = ['放行许可', '登记进站', '登记离站', '授予门禁', '撤销门禁'] as const

export interface PermitRow {
  id: number
  许可编号: string
  来访单位: string
  进站事由: string
  进站时段: string
  随行人员: string[]
  随行人数: number
  门禁授权: string
  许可状态: string
  登记人: string
  status: string
}

export interface ActionReply {
  ok: boolean
  message: string
}

/** 执行许可动作；把当前操作人与身份一并带给后端，越权与不合规动作由后端挡下并说明原因。 */
export async function runPermitAction(
  row: PermitRow,
  action: string,
  session: { operator: string; role: string },
  extra: Record<string, unknown> = {},
): Promise<ActionReply> {
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({
        values: { action, operator: session.operator, role: session.role, ...extra },
      }),
    })
    const payload = (await response.json()) as ActionReply
    return {
      ok: Boolean(payload.ok),
      message: payload.message ?? (payload.ok ? '操作已完成' : '操作被拦下'),
    }
  } catch (error) {
    return { ok: false, message: error instanceof Error ? error.message : '进站许可操作失败' }
  }
}

/** 门禁授权徽标样式：已授权亮绿，已撤销/已失效标红，未授权灰显。 */
export function gateBadgeClass(gate: string): string {
  if (gate === '已授权') return 'badge on'
  if (gate === '已撤销' || gate === '已失效') return 'badge revoked'
  return 'badge'
}
