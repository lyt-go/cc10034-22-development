/** 用途复核接口：访问审计详情页读取同意核对结果、提交复核、签署与补证。 */

export type ConsentCheck = {
  id: number | null
  记录编号: string
  数据主体: string
  处理目的: string
  同意时间: string
  撤回时间: string
  生效状态: string
  可用: boolean
  判定: string
  说明: string
}

export type ConsentRow = {
  id: number
  记录编号: string
  数据主体: string
  处理目的: string
  同意范围?: string
  同意时间: string
  撤回时间: string
  法律依据?: string
  生效状态: string
  status: string
  核对: ConsentCheck
}

export type TimelineNode = {
  节点: string
  时间: string
  凭据: string
}

export type PurposeDoc = {
  单据编号: string
  记录编号: string
  访问事件: Record<string, string>
  数据主体: string
  处理目的: string
  判定: string
  引用建议: string
  依据: string
  时间线: TimelineNode[]
  出具时间: string
  出具人: string
  版本: number
}

export type EvidenceLog = {
  类型: string
  操作人: string
  原因: string
  材料: string
  时间: string
  关联签署复核?: string
}

export type ReviewRow = {
  id: number
  status: string
  复核编号: string
  审计记录ID: number
  记录编号: string
  访问主体: string
  目标资源: string
  数据主体: string
  处理目的: string
  访问时间: string
  审查结论: string
  结论说明: string
  候选同意: string[]
  引用同意: string
  用途单: PurposeDoc
  来源: string
  关联审查ID: number | null
  发起人: string
  创建时间: string
  签署人: string
  签署时间: string
  签署意见: string
  冲突提示: string
  补证记录: EvidenceLog[]
}

export type EventPacket = {
  audit: Record<string, string | number | boolean>
  consents: ConsentRow[]
  reviews: ReviewRow[]
  open_review: ReviewRow | null
  candidates: ConsentCheck[]
}

export type Disposition = {
  处置: string
  review_id?: number
  复核编号?: string
  原复核编号?: string
  用途单?: PurposeDoc
  候选同意?: string[]
}

export type ReviewAction = {
  ok: boolean
  message: string
  entry: ReviewRow | null
  extra: Disposition | null
}

const BASE = '/api/purpose_review'

async function readJson(response: Response): Promise<ReviewAction> {
  return (await response.json()) as ReviewAction
}

export function loadEventPacket(auditId: number): Promise<EventPacket> {
  return fetch(`${BASE}/for-event/${auditId}`).then((response) => {
    if (!response.ok) throw new Error('用途复核数据读取失败')
    return response.json() as Promise<EventPacket>
  })
}

export function submitReview(auditId: number, operator: string): Promise<ReviewAction> {
  return fetch(`${BASE}/for-event/${auditId}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ operator, reason: '合规抽查' }),
  }).then(readJson)
}

export function signReview(
  reviewId: number,
  signer: string,
  consentId: number | null,
): Promise<ReviewAction> {
  return fetch(`${BASE}/${reviewId}/sign`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ signer, consent_id: consentId }),
  }).then(readJson)
}

export function supplementReview(
  reviewId: number,
  operator: string,
  reason: string,
  evidence: string,
): Promise<ReviewAction> {
  return fetch(`${BASE}/${reviewId}/supplement`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ operator, reason, evidence }),
  }).then(readJson)
}
