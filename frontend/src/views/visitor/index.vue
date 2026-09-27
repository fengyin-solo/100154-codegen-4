<template>
  <section class="page" data-module="visitor">
    <header class="page-head">
      <div>
        <h2>外来人员进站许可</h2>
        <p class="page-desc">
          登记来访单位、进站事由、进站时段与随行人员名单，许可按 待受理→已放行→已进站→已离站 推进，门禁授权只在放行之后生效。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记进站申请</button>
        <button class="btn" type="button" @click="exportRows">导出进站许可清单</button>
      </div>
    </header>

    <div class="identity-bar">
      <span>当前身份</span>
      <select v-model="store.role">
        <option>站点管理员</option>
        <option>值班人员</option>
      </select>
      <span>操作人</span>
      <input v-model="store.operator" placeholder="操作人姓名" />
      <span class="identity-hint">门禁授权仅站点管理员可改动；值班人员只能查看或改动本人登记的许可</span>
    </div>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>来访单位 / 许可编号</span>
        <input v-model="filters.keyword" placeholder="按来访单位或许可编号检索" />
      </label>
      <label class="filter-item">
        <span>许可状态</span>
        <select v-model="filters.status">
          <option value="">全部状态</option>
          <option v-for="status in STATUSES" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <p v-if="notice.message" class="notice" :class="notice.ok ? 'ok' : 'err'">{{ notice.message }}</p>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">
            <span v-if="column === '门禁授权'" :class="gateBadgeClass(row.门禁授权)">{{ row.门禁授权 }}</span>
            <template v-else>{{ row[column] ?? '—' }}</template>
          </td>
          <td class="row-actions">
            <button class="link" type="button" @click="openDetail(row)">查看</button>
            <button
              v-for="action in ROW_ACTIONS"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无进站许可记录，可先登记进站申请</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条进站许可记录</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <div v-if="createVisible" class="modal-mask" @click.self="createVisible = false">
      <div class="modal-card">
        <h3>登记进站申请</h3>
        <label class="form-item">
          <span>来访单位</span>
          <input v-model="createForm.来访单位" placeholder="如：华云气象设备公司" />
        </label>
        <label class="form-item">
          <span>进站事由</span>
          <input v-model="createForm.进站事由" placeholder="如：检修观测场天气雷达伺服系统" />
        </label>
        <label class="form-item">
          <span>进站时段</span>
          <input v-model="createForm.进站时段" placeholder="如：2026-09-28 09:00-12:00" />
        </label>
        <label class="form-item">
          <span>随行人员</span>
          <textarea v-model="createForm.随行人员" rows="3" placeholder="逐位填写，顿号或换行分隔，如：王检修、李安全"></textarea>
        </label>
        <p class="form-hint">同一来访单位同时段只保留一条进站申请；登记人为当前操作人 {{ store.operator }}</p>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="submitCreate">提交登记</button>
          <button class="btn ghost" type="button" @click="createVisible = false">取消</button>
        </div>
      </div>
    </div>

    <div v-if="checkinRow" class="modal-mask" @click.self="checkinRow = null">
      <div class="modal-card">
        <h3>登记进站 · {{ checkinRow.许可编号 }}</h3>
        <p class="form-hint">登记名单 {{ checkinRow.随行人员.length }} 人：{{ checkinRow.随行人员.join('、') }}</p>
        <label class="form-item">
          <span>实际到场随行人员</span>
          <textarea v-model="checkinNames" rows="3" placeholder="逐位填写，与登记名单逐一核对"></textarea>
        </label>
        <p class="form-hint">人数或名单不一致会被拦下，并指出差在哪一位</p>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="submitCheckin">核对并登记进站</button>
          <button class="btn ghost" type="button" @click="checkinRow = null">取消</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { ENDPOINT, ROW_ACTIONS, STATUSES, gateBadgeClass, runPermitAction } from './permit'
import type { PermitRow } from './permit'

const store = useSessionStore()
const router = useRouter()

const columns = ['许可编号', '来访单位', '进站事由', '进站时段', '随行人数', '门禁授权', '许可状态', '登记人'] as const

const rows = ref<PermitRow[]>([])
const total = ref(0)
const errorMessage = ref('')
const notice = reactive({ ok: true, message: '' })
const filters = reactive({ keyword: '', status: '' })
const stats = ref([
  { label: '待受理', value: 0 },
  { label: '已放行待进站', value: 0 },
  { label: '当前在站', value: 0 },
  { label: '历史已离站', value: 0 },
])

const createVisible = ref(false)
const createForm = reactive({ 来访单位: '', 进站事由: '', 进站时段: '', 随行人员: '' })

const checkinRow = ref<PermitRow | null>(null)
const checkinNames = ref('')

function resetFilters() {
  filters.keyword = ''
  filters.status = ''
  void reload()
}

function exportRows() {
  window.open(`${ENDPOINT}/export`, '_blank')
}

function openCreate() {
  createForm.来访单位 = ''
  createForm.进站事由 = ''
  createForm.进站时段 = ''
  createForm.随行人员 = ''
  createVisible.value = true
}

function openDetail(row: PermitRow) {
  void router.push(`/visitor/${row.id}`)
}

async function runAction(action: string, row: PermitRow) {
  notice.message = ''
  if (action === '登记进站') {
    checkinRow.value = row
    checkinNames.value = row.随行人员.join('、')
    return
  }
  const reply = await runPermitAction(row, action, store)
  notice.ok = reply.ok
  notice.message = reply.message
  await reload()
}

async function submitCheckin() {
  if (!checkinRow.value) return
  const reply = await runPermitAction(checkinRow.value, '登记进站', store, { 实际随行人员: checkinNames.value })
  notice.ok = reply.ok
  notice.message = reply.message
  if (reply.ok) {
    checkinRow.value = null
  }
  await reload()
}

async function submitCreate() {
  notice.message = ''
  try {
    const response = await request(ENDPOINT, {
      method: 'POST',
      body: JSON.stringify({ values: { ...createForm, operator: store.operator } }),
    })
    const payload = await response.json()
    notice.ok = Boolean(payload.ok)
    notice.message = payload.message ?? (payload.ok ? '进站许可已登记' : '登记被拦下')
    if (payload.ok) {
      createVisible.value = false
    }
  } catch (error) {
    notice.ok = false
    notice.message = error instanceof Error ? error.message : '进站许可登记失败'
  }
  await reload()
}

async function refreshStats() {
  try {
    const response = await request(`${ENDPOINT}?size=200`)
    if (!response.ok) return
    const payload = await response.json()
    const items = (payload.items ?? []) as PermitRow[]
    const count = (status: string) => items.filter((row) => row.status === status).length
    stats.value = [
      { label: '待受理', value: count('待受理') },
      { label: '已放行待进站', value: count('已放行') },
      { label: '当前在站', value: count('已进站') },
      { label: '历史已离站', value: count('已离站') },
    ]
  } catch {
    // 统计读取失败不阻塞列表展示
  }
}

async function reload() {
  errorMessage.value = ''
  const query = new URLSearchParams()
  if (filters.keyword) query.set('keyword', filters.keyword)
  if (filters.status) query.set('status', filters.status)
  try {
    const response = await request(`${ENDPOINT}?${query.toString()}`)
    if (!response.ok) {
      throw new Error('进站许可列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '进站许可列表读取失败'
  }
  await refreshStats()
}

onMounted(reload)
</script>
