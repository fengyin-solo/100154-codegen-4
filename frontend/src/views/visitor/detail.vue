<template>
  <section class="page" data-module="visitor-detail">
    <header class="page-head">
      <div>
        <h2>进站许可 {{ permit?.许可编号 ?? '' }}</h2>
        <p class="page-desc">
          许可状态与门禁授权以后端返回为准；在此执行的每次动作都会重新拉取明细，
          返回列表后看到的随行人员与门禁授权保持一致。
        </p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn" to="/visitor">返回列表</RouterLink>
      </div>
    </header>

    <p v-if="loadError" class="error-text">{{ loadError }}</p>

    <template v-if="permit">
      <div class="detail-grid">
        <article class="detail-card span-2">
          <h3>申请信息</h3>
          <dl class="detail-list">
            <div><dt>来访单位</dt><dd>{{ permit.来访单位 }}</dd></div>
            <div><dt>进站事由</dt><dd>{{ permit.进站事由 || '—' }}</dd></div>
            <div><dt>进站开始</dt><dd>{{ permit.进站开始 }}</dd></div>
            <div><dt>进站结束</dt><dd>{{ permit.进站结束 }}</dd></div>
            <div><dt>登记站点</dt><dd>{{ permit.登记站点 }}</dd></div>
            <div><dt>登记人</dt><dd>{{ permit.登记人 || '（历史数据无登记人）' }}</dd></div>
          </dl>
        </article>

        <article class="detail-card">
          <h3>当前状态</h3>
          <div class="status-flow">
            <span
              v-for="(step, index) in statusFlow"
              :key="step"
              :class="['flow-step', flowClass(index)]"
            >{{ step }}</span>
          </div>
          <p class="auth-line">
            门禁授权：
            <span :class="['auth-tag', authClass(permit.门禁授权)]">{{ permit.门禁授权 }}</span>
            <span class="muted-note">（仅放行后可生效，离站自动失效）</span>
          </p>
        </article>

        <article class="detail-card span-2">
          <h3>随行人员登记名单（{{ permit.随行人数 }} 人）</h3>
          <ul v-if="permit.随行人员名单.length" class="roster-list">
            <li v-for="(name, index) in permit.随行人员名单" :key="name">
              <span class="roster-no">{{ index + 1 }}</span>{{ name }}
            </li>
          </ul>
          <p v-else class="muted-note">该条为历史数据，未保留随行人员名单。</p>
        </article>

        <article class="detail-card span-2">
          <h3>门禁授权记录</h3>
          <pre v-if="permit.门禁授权记录 !== '（无）'" class="auth-log">{{ permit.门禁授权记录 }}</pre>
          <p v-else class="muted-note">暂无授权操作记录。</p>
        </article>
      </div>

      <!-- 操作区 -->
      <article class="detail-card action-card">
        <h3>许可处置</h3>

        <div v-if="!canOperatePermit" class="readonly-tip">
          该许可由「{{ permit.登记人 || '历史数据（无登记人）' }}」登记，
          当前身份为{{ store.role }}（{{ store.operator }}），只能查看，不能改动别人的进站许可。
        </div>

        <div class="action-row">
          <button
            v-if="permit.status === '待受理'"
            class="btn primary"
            type="button"
            :disabled="!canOperatePermit || acting"
            :title="canOperatePermit ? '' : '只有登记人或站点管理员可受理'"
            @click="runSimpleAction('受理放行')"
          >受理放行（放行后门禁授权自动生效）</button>

          <template v-if="permit.status === '已放行'">
            <label class="actual-roster">
              <span>进站核对：实际到岗随行人员 *</span>
              <textarea v-model="actualRoster" rows="2" :disabled="!canOperatePermit || acting"></textarea>
              <small class="muted-note">默认取登记名单；名单不一致会被拦下并指出差在哪一位。</small>
            </label>
            <button
              class="btn primary"
              type="button"
              :disabled="!canOperatePermit || acting"
              @click="runEnter"
            >核对名单并登记进站</button>
          </template>

          <button
            v-if="permit.status === '已进站'"
            class="btn primary"
            type="button"
            :disabled="!canOperatePermit || acting"
            @click="runSimpleAction('登记离站')"
          >登记离站（离站后门禁授权自动失效）</button>

          <span v-if="permit.status === '已离站'" class="readonly-tip">该许可已办结（已离站），无后续动作。</span>
        </div>

        <div class="action-row auth-actions">
          <span class="auth-actions-label">门禁授权（仅站点管理员可改）：</span>
          <button
            class="btn"
            type="button"
            :disabled="acting || !store.isAdmin || !authManualEditable"
            :title="store.isAdmin ? '' : '门禁授权只能由站点管理员改动'"
            @click="runAuthAction('开启门禁授权')"
          >开启授权</button>
          <button
            class="btn"
            type="button"
            :disabled="acting || !store.isAdmin || !authManualEditable"
            :title="store.isAdmin ? '' : '门禁授权只能由站点管理员改动'"
            @click="runAuthAction('关闭门禁授权')"
          >关闭授权</button>
          <small v-if="!store.isAdmin" class="muted-note">值班人员无权改动门禁授权。</small>
        </div>

        <p v-if="actionMessage" :class="actionOk ? 'ok-text' : 'error-text'" class="action-message">
          {{ actionMessage }}
        </p>
      </article>
    </template>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { useSessionStore } from '@/stores/session'
import { fetchPermit, PERMIT_STATUSES, submitPermitAction, type VisitorPermit } from './api'

const route = useRoute()
const store = useSessionStore()

const statusFlow = PERMIT_STATUSES
const permit = ref<VisitorPermit | null>(null)
const loadError = ref('')
const acting = ref(false)
const actionMessage = ref('')
const actionOk = ref(false)
const actualRoster = ref('')

const permitId = computed(() => String(route.params.id))

// 值班人员只能处置自己登记的许可；管理员不受归属限制；历史数据无登记人时仅管理员可动。
const canOperatePermit = computed(() => {
  if (!permit.value) return false
  if (store.isAdmin) return true
  return Boolean(permit.value.登记人) && permit.value.登记人 === store.operator
})

// 授权手动开关仅在放行后、离站前允许操作（是否有权限另由后端按角色判定）。
const authManualEditable = computed(() =>
  permit.value?.status === '已放行' || permit.value?.status === '已进站',
)

function flowClass(index: number) {
  if (!permit.value) return ''
  const current = statusFlow.indexOf(permit.value.status)
  if (index < current) return 'flow-done'
  if (index === current) return 'flow-current'
  return 'flow-todo'
}

function authClass(auth: string) {
  return {
    未授权: 'auth-off',
    已停用: 'auth-off',
    已授权: 'auth-on',
    已失效: 'auth-expired',
  }[auth] ?? ''
}

async function load() {
  loadError.value = ''
  try {
    permit.value = await fetchPermit(permitId.value)
    actualRoster.value = permit.value.随行人员
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '进站许可明细读取失败'
    permit.value = null
  }
}

async function send(values: Record<string, unknown>) {
  if (!permit.value) return
  acting.value = true
  actionMessage.value = ''
  try {
    const result = await submitPermitAction(permit.value.id, values)
    actionOk.value = result.ok
    actionMessage.value = result.message
    // 无论成功失败都重新拉取：成功要刷新状态/授权，失败要确认服务端数据未被改动。
    await load()
  } catch (error) {
    actionOk.value = false
    actionMessage.value = error instanceof Error ? error.message : '操作失败'
  } finally {
    acting.value = false
  }
}

function runSimpleAction(action: string) {
  void send({ action })
}

function runEnter() {
  if (!actualRoster.value.trim()) {
    actionOk.value = false
    actionMessage.value = '请填写实际到岗随行人员，再做进站核对'
    return
  }
  void send({ action: '登记进站', 随行人员: actualRoster.value })
}

function runAuthAction(action: string) {
  if (!store.isAdmin) {
    actionOk.value = false
    actionMessage.value = `门禁授权只能由站点管理员改动，当前身份为${store.role}，无权改动`
    return
  }
  void send({ action })
}

watch(permitId, () => void load())

onMounted(load)
</script>
