<template>
  <section class="page detail-page" data-testid="access-audit-detail">
    <header class="page-head">
      <div>
        <h2>审计记录 {{ audit['记录编号'] || `#${entryId}` }}</h2>
        <p class="page-desc">核对本次访问发生时是否取得当事人同意，并出具可追溯的历史用途单。</p>
      </div>
      <div class="page-actions">
        <RouterLink class="btn ghost" to="/access_audit">返回访问审计</RouterLink>
      </div>
    </header>

    <p v-if="loadError" class="error-text" data-testid="detail-error">{{ loadError }}</p>

    <div class="stat-row">
      <article class="stat-card">
        <span class="stat-label">访问主体</span><strong class="stat-value small">{{ audit['访问主体'] || '—' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">目标资源</span><strong class="stat-value small">{{ audit['目标资源'] || '—' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">访问时间</span><strong class="stat-value small">{{ audit['访问时间'] || '—' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">处理目的</span><strong class="stat-value small">{{ audit['处理目的'] || '—' }}</strong>
      </article>
      <article class="stat-card">
        <span class="stat-label">数据主体</span><strong class="stat-value small">{{ audit['数据主体'] || '—' }}</strong>
      </article>
    </div>

    <section class="detail-block">
      <h3>同意登记核对<span class="hint">按访问发生时点判断，访问后撤回不影响当时授权</span></h3>
      <table class="data-table">
        <thead>
          <tr><th>记录编号</th><th>处理目的</th><th>同意时间</th><th>撤回时间</th><th>访问时点判定</th><th>说明</th></tr>
        </thead>
        <tbody>
          <tr
            v-for="consent in consents"
            :key="consent.id"
            :data-testid="`consent-${consent.记录编号}`"
            :data-verdict="consent.核对.判定"
          >
            <td>{{ consent.记录编号 }}</td>
            <td>{{ consent.处理目的 }}</td>
            <td>{{ consent.同意时间 }}</td>
            <td>{{ consent.撤回时间 }}</td>
            <td>
              <span :class="['verdict', consent.核对.可用 ? 'ok' : 'warn']">
                {{ consent.核对.判定 }}
              </span>
            </td>
            <td class="note-cell">{{ consent.核对.说明 }}</td>
          </tr>
          <tr v-if="!consents.length">
            <td colspan="6" class="empty-state">该数据主体暂无同意登记记录</td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="detail-block">
      <h3>用途复核<span class="hint">一笔事件可有多次核查，签署后的结论冻结</span></h3>

      <div class="review-toolbar">
        <label class="inline-field">
          <span>经办人</span>
          <input v-model="operator" data-testid="operator" placeholder="合规专员" />
        </label>
        <button
          class="btn primary"
          data-testid="submit-review"
          type="button"
          :disabled="busy"
          @click="submit"
        >
          {{ openReview ? '提交并归入当前审查' : '提交用途复核' }}
        </button>
        <span v-if="disposition" class="disposition" data-testid="disposition">{{ disposition }}</span>
      </div>

      <p v-if="actionError" class="error-text" data-testid="action-error">{{ actionError }}</p>
      <p v-if="actionMessage" class="ok-text" data-testid="action-message">{{ actionMessage }}</p>

      <article v-if="openReview" class="review-card open" data-testid="open-review">
        <header class="review-head">
          <strong>{{ openReview.复核编号 }}</strong>
          <span class="badge" data-testid="open-review-status">{{ openReview.status }}</span>
          <span class="muted">来源：{{ openReview.来源 }} · 发起人：{{ openReview.发起人 }}</span>
        </header>
        <p class="conclusion" data-testid="open-review-conclusion">
          审查结论：{{ openReview.审查结论 }}
        </p>
        <p class="note-cell">{{ openReview.结论说明 }}</p>
        <p v-if="openReview.冲突提示" class="conflict" data-testid="open-review-conflict">
          {{ openReview.冲突提示 }}
        </p>

        <div class="review-body">
          <div class="review-col">
            <h4>历史用途单</h4>
            <dl class="purpose-doc">
              <dt>单据编号</dt><dd>{{ openReview.用途单.单据编号 }}</dd>
              <dt>判定</dt><dd data-testid="doc-verdict">{{ openReview.用途单.判定 }}</dd>
              <dt>引用建议</dt><dd>{{ openReview.用途单.引用建议 }}</dd>
              <dt>依据</dt><dd>{{ openReview.用途单.依据 }}</dd>
              <dt>版本</dt><dd>v{{ openReview.用途单.版本 }} · {{ openReview.用途单.出具时间 }}</dd>
            </dl>
            <ol class="timeline-list">
              <li v-for="(node, index) in openReview.用途单.时间线" :key="index">
                <span class="timeline-node">{{ node.节点 }}</span>
                <span class="timeline-time">{{ node.时间 }}</span>
                <span class="muted">{{ node.凭据 }}</span>
              </li>
            </ol>
          </div>

          <div class="review-col">
            <h4>签署</h4>
            <p v-if="candidateConsents.length" class="hint">
              访问当时存在覆盖本事件目的的有效同意，签署必须引用对应凭据。
            </p>
            <p v-else class="hint">访问当时没有覆盖本事件目的的有效同意，签署将确认当时无授权。</p>
            <label class="inline-field block">
              <span>引用凭据</span>
              <select v-model="signConsent" data-testid="sign-consent">
                <option :value="null">不引用（确认访问时无有效同意）</option>
                <option v-for="item in candidateConsents" :key="item.记录编号" :value="item.id">
                  {{ item.记录编号 }} · {{ item.处理目的 }}
                </option>
              </select>
            </label>
            <label class="inline-field block">
              <span>签署意见</span>
              <input v-model="signRemark" data-testid="sign-remark" placeholder="可选" />
            </label>
            <button
              class="btn primary"
              data-testid="sign-review"
              type="button"
              :disabled="busy"
              @click="sign"
            >
              签署复核
            </button>

            <h4 class="spaced">补证复核</h4>
            <label class="inline-field block">
              <span>补证原因</span>
              <input v-model="supplementReason" data-testid="supplement-reason" placeholder="必填" />
            </label>
            <label class="inline-field block">
              <span>补充材料</span>
              <input v-model="supplementEvidence" data-testid="supplement-evidence" placeholder="材料编号或说明" />
            </label>
            <button
              class="btn"
              data-testid="supplement-review"
              type="button"
              :disabled="busy"
              @click="supplement(openReview)"
            >
              发起补证复核
            </button>
          </div>
        </div>

        <div v-if="openReview.补证记录.length" class="evidence-log">
          <h4>补证与归并记录</h4>
          <ul>
            <li v-for="(log, index) in openReview.补证记录" :key="index">
              <span class="badge">{{ log.类型 }}</span>
              {{ log.时间 }} · {{ log.操作人 }} · {{ log.原因 }}
              <span v-if="log.材料" class="muted">（{{ log.材料 }}）</span>
            </li>
          </ul>
        </div>
      </article>

      <article
        v-for="review in signedReviews"
        :key="review.id"
        class="review-card signed"
        :data-testid="`signed-review-${review.复核编号}`"
      >
        <header class="review-head">
          <strong>{{ review.复核编号 }}</strong>
          <span class="badge ok">{{ review.status }}</span>
          <span class="muted">签署人：{{ review.签署人 }} · {{ review.签署时间 }}</span>
        </header>
        <p class="conclusion">审查结论：{{ review.审查结论 }}</p>
        <p class="note-cell">{{ review.结论说明 }}</p>
        <dl class="purpose-doc compact">
          <dt>引用凭据</dt><dd data-testid="signed-cited">{{ review.引用同意 || '未引用' }}</dd>
          <dt>用途单</dt><dd>{{ review.用途单.单据编号 }} · v{{ review.用途单.版本 }}</dd>
          <dt>签署意见</dt><dd>{{ review.签署意见 || '—' }}</dd>
          <dt>关联审查</dt><dd>{{ review.关联审查ID ? `#${review.关联审查ID}` : '—' }}</dd>
        </dl>
        <p v-if="review.冲突提示" class="conflict">{{ review.冲突提示 }}</p>
        <div class="review-foot">
          <button
            class="btn"
            type="button"
            :disabled="busy"
            @click="supplement(review)"
          >
            在本次事件上发起补证复核
          </button>
        </div>
      </article>

      <p v-if="!reviews.length" class="empty-state hint-block">
        该事件尚未提交用途复核。核对上方同意登记后提交，服务端会出具历史用途单。
      </p>
    </section>
  </section>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import {
  loadEventPacket,
  signReview,
  submitReview,
  supplementReview,
} from '@/api/purpose-review'
import type { EventPacket, ReviewRow } from '@/api/purpose-review'

const route = useRoute()
const entryId = computed(() => Number(route.params.entryId))
const packet = ref<EventPacket | null>(null)
const loadError = ref('')
const actionError = ref('')
const actionMessage = ref('')
const disposition = ref('')
const busy = ref(false)

const operator = ref('合规专员-林可')
const signConsent = ref<number | null>(null)
const signRemark = ref('')
const supplementReason = ref('')
const supplementEvidence = ref('')

const audit = computed(() => packet.value?.audit ?? {})
const consents = computed(() => packet.value?.consents ?? [])
const reviews = computed(() => packet.value?.reviews ?? [])
const openReview = computed(() => packet.value?.open_review ?? null)
const signedReviews = computed(() => reviews.value.filter((row) => row.status === '已签署'))
const candidateConsents = computed(() => packet.value?.candidates ?? [])

function resetForm() {
  signConsent.value = candidateConsents.value.length === 1
    ? Number(candidateConsents.value[0].id)
    : null
  signRemark.value = ''
  supplementReason.value = ''
  supplementEvidence.value = ''
}

async function reload() {
  try {
    packet.value = await loadEventPacket(entryId.value)
    loadError.value = ''
    resetForm()
  } catch (error) {
    loadError.value = error instanceof Error ? error.message : '用途复核数据读取失败'
  }
}

async function submit() {
  busy.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const result = await submitReview(entryId.value, operator.value)
    if (!result.ok) throw new Error(result.message)
    actionMessage.value = result.message
    disposition.value = result.extra?.处置 ?? ''
    await reload()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '提交复核失败'
    disposition.value = ''
  } finally {
    busy.value = false
  }
}

async function sign() {
  if (!openReview.value) return
  busy.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const result = await signReview(openReview.value.id, operator.value, signConsent.value)
    if (!result.ok) throw new Error(result.message)
    actionMessage.value = result.message
    disposition.value = ''
    await reload()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '签署失败'
  } finally {
    busy.value = false
  }
}

async function supplement(target: ReviewRow) {
  busy.value = true
  actionError.value = ''
  actionMessage.value = ''
  try {
    const result = await supplementReview(
      target.id,
      operator.value,
      supplementReason.value || '补充核查材料',
      supplementEvidence.value,
    )
    if (!result.ok) throw new Error(result.message)
    actionMessage.value = result.message
    disposition.value = result.extra?.处置 ?? ''
    await reload()
  } catch (error) {
    actionError.value = error instanceof Error ? error.message : '补证复核失败'
    disposition.value = ''
  } finally {
    busy.value = false
  }
}

watch(entryId, () => void reload())
onMounted(reload)
</script>

<style scoped>
.detail-block { background: #fff; border: 1px solid var(--border); border-radius: 8px; padding: 14px; margin-bottom: 14px; }
.detail-block h3 { margin: 0 0 10px; font-size: 15px; }
.hint { color: var(--muted); font-size: 12px; font-weight: normal; margin-left: 8px; }
.stat-value.small { font-size: 14px; }
.verdict { font-size: 12px; padding: 2px 8px; border-radius: 999px; }
.verdict.ok { background: #e7f6ec; color: #18794e; }
.verdict.warn { background: #fdecea; color: #b42318; }
.note-cell { color: var(--muted); font-size: 12px; }
.review-toolbar { display: flex; flex-wrap: wrap; gap: 10px; align-items: flex-end; margin-bottom: 10px; }
.inline-field { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: var(--muted); }
.inline-field.block { margin-bottom: 10px; }
.inline-field input, .inline-field select { padding: 6px 8px; border: 1px solid var(--border); border-radius: 6px; font-size: 13px; }
.review-card { border: 1px solid var(--border); border-radius: 8px; padding: 12px; margin-bottom: 12px; }
.review-card.open { border-color: var(--brand); }
.review-card.signed { background: #fafbfc; }
.review-head { display: flex; gap: 10px; align-items: baseline; flex-wrap: wrap; margin-bottom: 6px; }
.badge { font-size: 12px; background: #eef2f7; color: #334155; padding: 1px 8px; border-radius: 999px; }
.badge.ok { background: #e7f6ec; color: #18794e; }
.conclusion { font-size: 14px; font-weight: 600; margin: 4px 0; }
.conflict { background: #fff7e6; border-left: 3px solid #d97706; color: #92400e; padding: 8px 10px; font-size: 12px; border-radius: 4px; }
.review-body { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 10px; }
.review-col h4 { margin: 0 0 8px; font-size: 13px; }
.review-col h4.spaced { margin-top: 16px; }
.purpose-doc { display: grid; grid-template-columns: 90px 1fr; gap: 4px 8px; font-size: 13px; margin: 0 0 10px; }
.purpose-doc dt { color: var(--muted); font-size: 12px; }
.purpose-doc dd { margin: 0; }
.timeline-list { margin: 0; padding-left: 18px; font-size: 12px; }
.timeline-list li { margin-bottom: 4px; }
.timeline-node { font-weight: 600; margin-right: 6px; }
.timeline-time { color: var(--brand); margin-right: 6px; }
.muted { color: var(--muted); font-size: 12px; }
.evidence-log { margin-top: 12px; border-top: 1px dashed var(--border); padding-top: 10px; font-size: 12px; }
.evidence-log ul { margin: 0; padding-left: 16px; }
.evidence-log li { margin-bottom: 4px; }
.disposition { font-size: 12px; color: var(--brand); background: #eef4ff; padding: 4px 10px; border-radius: 999px; }
.ok-text { color: #18794e; font-size: 12px; }
.hint-block { padding: 12px; }
.review-foot { margin-top: 8px; }
@media (max-width: 860px) { .review-body { grid-template-columns: 1fr; } }
</style>
