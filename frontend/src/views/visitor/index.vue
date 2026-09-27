<template>
  <section class="page" data-module="visitor">
    <header class="page-head">
      <div>
        <h2>外来人员进站许可</h2>
        <p class="page-desc">
          外单位来观测场检修设备须先登记进站申请；许可按
          待受理 → 已放行 → 已进站 → 已离站 推进，门禁授权只在放行后生效。
        </p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="showCreate = true">登记进站申请</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label class="filter-item">
        <span>来访单位 / 编号 / 人员</span>
        <input v-model="keyword" placeholder="按来访单位、许可编号或人员检索" />
      </label>
      <label class="filter-item">
        <span>许可状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="s in statuses" :key="s" :value="s">{{ s }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)" class="clickable-row" @click="openDetail(row.id)">
          <td>{{ row.许可编号 }}</td>
          <td>{{ row.来访单位 }}</td>
          <td>{{ row.进站事由 || '—' }}</td>
          <td>{{ row.进站开始 }} ~ {{ row.进站结束 }}</td>
          <td>{{ row.随行人数 }} 人<div class="roster-preview">{{ row.随行人员 || '（历史数据无名单）' }}</div></td>
          <td>
            <span :class="['status-tag', statusClass(row.status)]">{{ row.status }}</span>
          </td>
          <td>
            <span :class="['auth-tag', authClass(row.门禁授权)]">{{ row.门禁授权 }}</span>
          </td>
          <td>{{ row.登记人 || '（无登记人）' }}</td>
          <td class="row-actions" @click.stop>
            <button class="link" type="button" @click="openDetail(row.id)">查看许可</button>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 1" class="empty-state">暂无进站许可，可先登记进站申请</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条进站许可</span>
      <span class="identity-hint">当前身份：{{ store.role }}（{{ store.operator }}）<template v-if="!store.isAdmin">，只能改动自己登记的许可</template></span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>

    <!-- 登记进站申请 -->
    <div v-if="showCreate" class="modal-mask" @click.self="closeCreate">
      <form class="modal-card" @submit.prevent="submitCreate">
        <h3>登记进站申请</h3>
        <label class="form-item">
          <span>来访单位 *</span>
          <input v-model="form.来访单位" placeholder="如：省大气探测技术保障中心" />
        </label>
        <label class="form-item">
          <span>进站事由 *</span>
          <input v-model="form.进站事由" placeholder="如：风速传感器故障检修" />
        </label>
        <div class="form-row">
          <label class="form-item">
            <span>进站开始 *</span>
            <input v-model="form.进站开始" placeholder="2026-09-28 09:30" />
          </label>
          <label class="form-item">
            <span>进站结束 *</span>
            <input v-model="form.进站结束" placeholder="2026-09-28 12:00" />
          </label>
        </div>
        <label class="form-item">
          <span>随行人员名单 *（顿号、逗号或换行分隔）</span>
          <textarea v-model="form.随行人员" rows="3" placeholder="王建军、李志强、赵敏"></textarea>
        </label>
        <label class="form-item">
          <span>登记站点</span>
          <input v-model="form.登记站点" placeholder="本观测场" />
        </label>
        <p v-if="formError" class="error-text form-error">{{ formError }}</p>
        <div class="modal-actions">
          <button class="btn" type="button" @click="closeCreate">取消</button>
          <button class="btn primary" type="submit">提交申请</button>
        </div>
      </form>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'

import { useSessionStore } from '@/stores/session'
import { createPermit, fetchPermits, PERMIT_STATUSES, type VisitorPermit } from './api'

const router = useRouter()
const store = useSessionStore()

const columns = ['许可编号', '来访单位', '进站事由', '进站时段', '随行人员', '许可状态', '门禁授权', '登记人']
const statuses = PERMIT_STATUSES

const rows = ref<VisitorPermit[]>([])
const total = ref(0)
const errorMessage = ref('')
const keyword = ref('')
const statusFilter = ref('')

const allRows = ref<VisitorPermit[]>([])
const stats = computed(() =>
  statuses.map((status) => ({
    label: status,
    value: allRows.value.filter((row) => row.status === status).length,
  })),
)

function statusClass(status: string) {
  return {
    待受理: 'st-pending',
    已放行: 'st-released',
    已进站: 'st-entered',
    已离站: 'st-left',
  }[status] ?? ''
}

function authClass(auth: string) {
  return {
    未授权: 'auth-off',
    已停用: 'auth-off',
    已授权: 'auth-on',
    已失效: 'auth-expired',
  }[auth] ?? ''
}

function resetFilters() {
  keyword.value = ''
  statusFilter.value = ''
  void reload()
}

function openDetail(id: number) {
  void router.push({ name: 'visitor-detail', params: { id } })
}

// 列表是门禁授权与随行人员的唯一展示口径：每次进入页面都重新拉取，
// 从详情返回时拿到的一定是最新派生结果。
async function reload() {
  errorMessage.value = ''
  try {
    const payload = await fetchPermits({ keyword: keyword.value, status: statusFilter.value })
    rows.value = payload.items
    total.value = payload.total
    const full = await fetchPermits({ keyword: keyword.value, size: 200 })
    allRows.value = full.items
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '进站许可列表读取失败'
  }
}

// ---- 登记表单 ----
const showCreate = ref(false)
const formError = ref('')
const form = reactive({
  来访单位: '',
  进站事由: '',
  进站开始: '',
  进站结束: '',
  随行人员: '',
  登记站点: '本观测场',
})

function closeCreate() {
  showCreate.value = false
  formError.value = ''
}

async function submitCreate() {
  formError.value = ''
  const payload = await createPermit({ ...form })
  if (!payload.ok) {
    formError.value = payload.message
    return
  }
  closeCreate()
  Object.assign(form, {
    来访单位: '',
    进站事由: '',
    进站开始: '',
    进站结束: '',
    随行人员: '',
    登记站点: '本观测场',
  })
  await reload()
}

onMounted(reload)
</script>
