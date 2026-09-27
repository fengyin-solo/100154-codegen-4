/** 外来人员进站许可：类型定义与接口封装。 */
import { request } from '@/api/client'

export interface VisitorPermit {
  id: number
  status: string
  许可编号: string
  来访单位: string
  进站事由: string
  进站开始: string
  进站结束: string
  随行人员: string
  随行人员名单: string[]
  随行人数: number
  登记人: string | null
  登记站点: string
  门禁授权: string
  门禁授权生效: boolean
  门禁授权记录: string
}

export interface PagePayload {
  items: VisitorPermit[]
  total: number
  page: number
  size: number
}

export interface ActionPayload {
  ok: boolean
  message: string
  entry: VisitorPermit | null
}

export const PERMIT_STATUSES = ['待受理', '已放行', '已进站', '已离站']

export async function fetchPermits(params: {
  keyword?: string
  status?: string
  page?: number
  size?: number
}): Promise<PagePayload> {
  const query = new URLSearchParams()
  if (params.keyword) query.set('keyword', params.keyword)
  if (params.status) query.set('status', params.status)
  query.set('page', String(params.page ?? 1))
  query.set('size', String(params.size ?? 50))
  const response = await request(`/api/visitor?${query.toString()}`)
  if (!response.ok) throw new Error('进站许可列表读取失败')
  return response.json()
}

export async function fetchPermit(id: string | number): Promise<VisitorPermit> {
  const response = await request(`/api/visitor/${id}`)
  if (!response.ok) throw new Error('进站许可明细读取失败')
  return response.json()
}

/** 把动作结果统一成 (entry, message)，业务被后端拦下时由调用方展示原因。 */
export async function submitPermitAction(
  id: number,
  values: Record<string, unknown>,
): Promise<ActionPayload> {
  const response = await request(`/api/visitor/${id}/actions`, {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  if (!response.ok) throw new Error('进站许可动作未送达，请稍后重试')
  return response.json()
}

export async function createPermit(values: Record<string, unknown>): Promise<ActionPayload> {
  const response = await request('/api/visitor', {
    method: 'POST',
    body: JSON.stringify({ values }),
  })
  if (!response.ok) throw new Error('进站申请未送达，请稍后重试')
  return response.json()
}
