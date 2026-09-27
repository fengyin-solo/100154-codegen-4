/** 统一请求封装：拼后端地址、抛网络错误、给页脚留一句可读的说明。 */
const API_BASE = import.meta.env.VITE_API_BASE ?? ''

/** 当前操作人上下文：由会话 store 在初始化/切换身份时注册进来。 */
export interface OperatorContext {
  name: string
  role: string
}

let operatorContext: OperatorContext | null = null

export function setOperatorContext(context: OperatorContext | null) {
  operatorContext = context
}

/** HTTP 头只接受 ASCII，中文姓名/角色做 base64(UTF-8) 编码。 */
function encodeHeader(text: string): string {
  return btoa(unescape(encodeURIComponent(text)))
}

function operatorHeaders(): Record<string, string> {
  if (!operatorContext) return {}
  return {
    'X-Operator-Name': encodeHeader(operatorContext.name),
    'X-Operator-Role': encodeHeader(operatorContext.role),
  }
}

export function request(path: string, init?: RequestInit): Promise<Response> {
  const url = path.startsWith('http') ? path : `${API_BASE}${path}`
  return fetch(url, {
    headers: { 'Content-Type': 'application/json', ...operatorHeaders(), ...(init?.headers ?? {}) },
    ...init,
  }).catch((error: unknown) => {
    const detail = error instanceof Error ? error.message : '请求未送达'
    throw new Error(`接口请求失败：${detail}`)
  })
}

export async function fetchJson<T>(path: string): Promise<T> {
  const response = await request(path)
  if (!response.ok) {
    throw new Error(`接口返回 ${response.status}，数据未更新`)
  }
  return (await response.json()) as T
}
