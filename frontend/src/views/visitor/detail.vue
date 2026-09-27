<template>
  <section class="page" data-module="visitor-detail">
    <header class="page-head">
      <div>
        <h2>进站许可详情</h2>
        <p class="page-desc">随行人员名单与门禁授权以服务端记录为准，返回列表刷新后仍保持一致；已离站的历史许可同样可读。</p>
      </div>
      <div class="page-actions">
        <button class="btn" type="button" @click="backToList">返回列表</button>
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

    <p v-if="notice.message" class="notice" :class="notice.ok ? 'ok' : 'err'">{{ notice.message }}</p>
    <p v-if="errorMessage" class="error-text">{{ errorMessage }}</p>

    <template v-if="entry">
      <div class="detail-grid">
        <div class="detail-item"><span>许可编号</span><strong>{{ entry.许可编号 }}</strong></div>
        <div class="detail-item"><span>来访单位</span><strong>{{ entry.来访单位 }}</strong></div>
        <div class="detail-item"><span>进站事由</span><strong>{{ entry.进站事由 }}</strong></div>
        <div class="detail-item"><span>进站时段</span><strong>{{ entry.进站时段 }}</strong></div>
        <div class="detail-item"><span>登记人</span><strong>{{ entry.登记人 }}</strong></div>
        <div class="detail-item"><span>许可状态</span><strong>{{ entry.许可状态 }}</strong></div>
        <div class="detail-item">
          <span>门禁授权</span>
          <strong><span :class="gateBadgeClass(entry.门禁授权)">{{ entry.门禁授权 }}</span></strong>
        </div>
      </div>

      <h3 class="section-title">随行人员名单（{{ entry.随行人员.length }} 人）</h3>
      <ol class="attendee-list">
        <li v-for="(name, index) in entry.随行人员" :key="index">{{ name }}</li>
      </ol>

      <div class="row-actions detail-actions">
        <button
          v-for="action in ROW_ACTIONS"
          :key="action"
          class="btn"
          type="button"
          @click="runAction(action)"
        >
          {{ action }}
        </button>
      </div>
    </template>

    <div v-if="checkinVisible" class="modal-mask" @click.self="checkinVisible = false">
      <div class="modal-card">
        <h3>登记进站 · {{ entry?.许可编号 }}</h3>
        <p class="form-hint">登记名单 {{ entry?.随行人员.length ?? 0 }} 人：{{ entry?.随行人员.join('、') }}</p>
        <label class="form-item">
          <span>实际到场随行人员</span>
          <textarea v-model="checkinNames" rows="3" placeholder="逐位填写，与登记名单逐一核对"></textarea>
        </label>
        <p class="form-hint">人数或名单不一致会被拦下，并指出差在哪一位</p>
        <div class="modal-actions">
          <button class="btn primary" type="button" @click="submitCheckin">核对并登记进站</button>
          <button class="btn ghost" type="button" @click="checkinVisible = false">取消</button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { request } from '@/api/client'
import { useSessionStore } from '@/stores/session'
import { ENDPOINT, ROW_ACTIONS, gateBadgeClass, runPermitAction } from './permit'
import type { PermitRow } from './permit'

const store = useSessionStore()
const route = useRoute()
const router = useRouter()

const entry = ref<PermitRow | null>(null)
const errorMessage = ref('')
const notice = reactive({ ok: true, message: '' })
const checkinVisible = ref(false)
const checkinNames = ref('')

function backToList() {
  void router.push('/visitor')
}

async function runAction(action: string) {
  if (!entry.value) return
  notice.message = ''
  if (action === '登记进站') {
    checkinNames.value = entry.value.随行人员.join('、')
    checkinVisible.value = true
    return
  }
  const reply = await runPermitAction(entry.value, action, store)
  notice.ok = reply.ok
  notice.message = reply.message
  await reload()
}

async function submitCheckin() {
  if (!entry.value) return
  const reply = await runPermitAction(entry.value, '登记进站', store, { 实际随行人员: checkinNames.value })
  notice.ok = reply.ok
  notice.message = reply.message
  if (reply.ok) {
    checkinVisible.value = false
  }
  await reload()
}

async function reload() {
  errorMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${String(route.params.id)}`)
    if (!response.ok) {
      const payload = await response.json().catch(() => null)
      throw new Error(payload?.detail ?? '进站许可读取失败')
    }
    entry.value = (await response.json()) as PermitRow
  } catch (error) {
    entry.value = null
    errorMessage.value = error instanceof Error ? error.message : '进站许可读取失败'
  }
}

onMounted(reload)
</script>
