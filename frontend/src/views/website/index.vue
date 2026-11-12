<template>
  <section class="page" data-module="website">
    <header class="page-head">
      <div>
        <h2>网页抓取规则管理</h2>
        <p class="page-desc">维护网页抓取的选择器规则、请求策略与编码配置，支持列表页与详情页两级抓取。</p>
      </div>
      <div class="page-actions">
        <button class="btn primary" type="button" @click="openCreate">登记抓取规则</button>
        <button class="btn" type="button" @click="exportRows">导出网页抓取规则清单</button>
      </div>
    </header>

    <div class="stat-row">
      <article v-for="item in stats" :key="item.label" class="stat-card">
        <span class="stat-label">{{ item.label }}</span>
        <strong class="stat-value">{{ item.value }}</strong>
      </article>
    </div>

    <form class="filter-bar" @submit.prevent="reload">
      <label v-for="field in filterFields" :key="field" class="filter-item">
        <span>{{ field }}</span>
        <input v-model="filters[field]" :placeholder="`按${field}检索`" />
      </label>
      <label class="filter-item">
        <span>状态</span>
        <select v-model="statusFilter">
          <option value="">全部状态</option>
          <option v-for="status in statuses" :key="status" :value="status">{{ status }}</option>
        </select>
      </label>
      <button class="btn" type="submit">查询</button>
      <button class="btn ghost" type="button" @click="resetFilters">重置条件</button>
    </form>

    <table class="data-table">
      <thead>
        <tr>
          <th v-for="column in columns" :key="column">{{ column }}</th>
          <th>状态</th>
          <th>可执行动作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="String(row.id)">
          <td v-for="column in columns" :key="column">{{ row[column] ?? '—' }}</td>
          <td>{{ row.status ?? '—' }}</td>
          <td class="row-actions">
            <button
              v-for="action in availableActions(row)"
              :key="action"
              class="link"
              type="button"
              @click="runAction(action, row)"
            >
              {{ action }}
            </button>
            <span v-if="!availableActions(row).length" class="empty-state">无可用动作</span>
          </td>
        </tr>
        <tr v-if="!rows.length">
          <td :colspan="columns.length + 2" class="empty-state">暂无网页抓取规则数据，可先登记抓取规则</td>
        </tr>
      </tbody>
    </table>

    <footer class="page-foot">
      <span>共 {{ total }} 条网页抓取规则记录</span>
      <span v-if="noticeMessage" class="notice-text">{{ noticeMessage }}</span>
      <span v-if="errorMessage" class="error-text">{{ errorMessage }}</span>
    </footer>
  </section>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'

import { request } from '@/api/client'

type Row = Record<string, string | number | null>

const ENDPOINT = '/api/website'
const columns = ["规则编号", "目标站点", "列表选择器", "详情选择器", "翻页参数", "请求间隔", "字符编码", "重试上限"]
const statuses = ["草稿", "待校验", "已启用", "已停用"]
const stats = [{"label": "抓取规则总数", "value": 0}, {"label": "待校验抓取规则", "value": 0}, {"label": "已启用抓取规则", "value": 0}]

// 状态只能单向推进：草稿 → 待校验 → 已启用 → 已停用；已停用只允许重新校验。
const ACTIONS_BY_STATUS: Record<string, string[]> = {
  草稿: ["提交校验"],
  待校验: ["启用配置"],
  已启用: ["停用配置"],
  已停用: ["提交校验"],
}

// 过滤框字段与后端查询参数的对应关系，列表与导出共用，保证两边条数一致。
const FILTER_PARAM_MAP: Record<string, string> = {
  规则编号: 'keyword',
  目标站点: 'site',
  列表选择器: 'selector',
}

const rows = ref<Row[]>([])
const total = ref(0)
const errorMessage = ref('')
const noticeMessage = ref('')
const filters = ref<Record<string, string>>({})
const statusFilter = ref('')
const filterFields = columns.slice(0, 3)

function availableActions(row: Row): string[] {
  return ACTIONS_BY_STATUS[String(row.status ?? '')] ?? []
}

function buildQuery(): string {
  const params = new URLSearchParams()
  for (const field of filterFields) {
    const value = (filters.value[field] ?? '').trim()
    if (value) {
      params.set(FILTER_PARAM_MAP[field], value)
    }
  }
  if (statusFilter.value) {
    params.set('status', statusFilter.value)
  }
  return params.toString()
}

function resetFilters() {
  filters.value = {}
  statusFilter.value = ''
  void reload()
}

function exportRows() {
  const query = buildQuery()
  window.open(`${ENDPOINT}/export${query ? `?${query}` : ''}`, '_blank')
}

function openCreate() {
  errorMessage.value = '抓取规则登记入口尚未接入审批流'
}

async function runAction(action: string, row: Row) {
  errorMessage.value = ''
  noticeMessage.value = ''
  try {
    const response = await request(`${ENDPOINT}/${row.id}/actions`, {
      method: 'POST',
      body: JSON.stringify({ action }),
    })
    const payload = (await response.json()) as { ok: boolean; message?: string }
    if (!response.ok || !payload.ok) {
      throw new Error(payload.message || '网页抓取规则动作未生效，请稍后重试')
    }
    noticeMessage.value = payload.message || `抓取规则已${action}`
    await reload()
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '网页抓取规则操作失败'
  }
}

async function reload() {
  errorMessage.value = ''
  const query = buildQuery()
  try {
    const response = await request(`${ENDPOINT}${query ? `?${query}` : ''}`)
    if (!response.ok) {
      throw new Error('抓取规则列表读取失败')
    }
    const payload = await response.json()
    rows.value = payload.items ?? []
    total.value = payload.total ?? rows.value.length
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : '网页抓取规则列表读取失败'
  }
}

onMounted(reload)
</script>
