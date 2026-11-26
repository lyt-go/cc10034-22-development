# 数据安全计算与隐私保护平台

面向数据脱敏、差分隐私、安全聚合与访问审计的数据安全计算与隐私保护平台。

这是一个前后端分离的管理平台：前端 Vue 3 + Vite + TypeScript，后端 FastAPI（Python）。
两边各自独立启动，前端 dev server 已关掉自动打开页面，启动后按终端打印的地址手工打开。

## 目录结构

```text
.
├── frontend/                 Vue 3 + Vite + TypeScript 前端
│   ├── src/views/WorkbenchView.vue|tsx  全部模块共享工作台
│   ├── src/views/AccessAuditDetail.vue  访问审计详情页（用途复核）
│   ├── src/data/modules.ts              18个业务模块配置
│   ├── src/api/              统一请求封装
│   └── vite.config.ts        dev server 配置（open: false）
├── backend/                  FastAPI（Python） 后端
│   ├── app/routers/resource.py  通用查询/导出/登记/动作接口
│   ├── app/routers/purpose_review.py  访问审计用途复核接口
│   ├── app/services/<key>.py    每个模块独立领域逻辑
│   ├── app/services/base.py     共享服务骨架
│   └── app/store.py          内存数据仓库与示例数据
├── .gitignore
└── docker-compose.yml
```

## 启动

### 后端

```bash
cd backend
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
./run.sh
```

健康检查：`curl http://127.0.0.1:8000/api/health`

### 前端

```bash
cd frontend
npm ci
npm run dev
```

前端默认监听 `http://127.0.0.1:5173/`，dev server 不会自动打开浏览器，
需要自己访问。`/api` 由 vite 代理到后端 `http://127.0.0.1:8000`。

## 业务模块

| 模块 | 目录 | 业务对象 | 主要字段 |
| --- | --- | --- | --- |
| 脱敏规则 | `mask_rule` | 脱敏规则 | 规则编号、目标字段、脱敏算法 |
| 隐私预算 | `privacy_budget` | 隐私预算 | 预算编号、数据集名称、总预算Epsilon |
| 噪声引擎 | `noise_engine` | 噪声配置 | 配置编号、噪声机制、Epsilon值 |
| 安全聚合 | `secure_agg` | 聚合任务 | 任务编号、数据源列表、聚合函数 |
| 访问审计 | `access_audit` | 审计记录 | 记录编号、访问主体、目标资源 |
| 用途复核 | `purpose_review` | 用途复核单 | 复核编号、审计记录ID、审查结论 |
| 授权审批 | `grant_approval` | 授权申请 | 申请编号、申请人、目标数据 |
| 分级分类 | `classify_tag` | 分级标签 | 标签编号、数据资源、安全等级 |
| 联邦训练 | `federated_train` | 训练任务 | 任务编号、参与节点、模型类型 |
| 梯度加密 | `gradient_encrypt` | 加密配置 | 配置编号、加密方案、密钥长度 |
| 假名化 | `pseudonym` | 假名映射 | 映射编号、原始标识、假名标识 |
| K匿名检查 | `k_anonymity` | 匿名检查 | 检查编号、数据集名称、准标识符列 |
| 差分查询 | `differential_sql` | 查询记录 | 查询编号、查询语句、查询用户 |
| 密文索引 | `encrypt_index` | 索引条目 | 条目编号、加密域、索引类型 |
| 数据水印 | `watermark` | 水印记录 | 水印编号、目标数据集、水印算法 |
| 同意登记 | `consent_registry` | 同意记录 | 记录编号、数据主体、处理目的 |
| 风险扫描 | `risk_scan` | 扫描任务 | 任务编号、扫描范围、扫描规则 |
| 策略下发 | `deploy_policy` | 策略分发 | 分发编号、策略内容、目标节点 |
| 异常检测 | `anomaly_detect` | 异常规则 | 规则编号、检测维度、检测算法 |

## 约定

- 全部模块共享`frontend/src/views/WorkbenchView.vue|tsx`和一套资源路由。
- 每个模块仍保留独立`backend/app/services/<模块>.py`；纯前端保留
  `frontend/src/domain/<模块>.ts`，用于承载真实业务差异并维持36题位容量。
- 列表接口统一返回 `{ items, total, page, size }`，动作接口统一返回 `{ ok, message }`。
- 状态流转只允许在 `app/services` 里改，路由层不做业务判断。

## 访问审计详情页：用途复核

访问审计列表每行的「用途复核」进入 `/access_audit/:id` 详情页。专员提交要检查的
访问事件后，服务端按**访问发生时点**核对同意登记，并出具历史用途单。

接口（`backend/app/routers/purpose_review.py`）：

| 方法 | 路径 | 作用 |
| --- | --- | --- |
| GET | `/api/purpose_review/for-event/{audit_id}` | 事件、同意核对结果、已有复核 |
| POST | `/api/purpose_review/for-event/{audit_id}` | 提交复核并出具历史用途单 |
| POST | `/api/purpose_review/{review_id}/sign` | 签署复核（可指定引用凭据） |
| POST | `/api/purpose_review/{review_id}/supplement` | 补证复核 |

判定规则（`backend/app/services/purpose_review.py`）：

1. **按访问时点判断**：访问发生后撤回同意，不追溯为访问时无授权。
   撤回时间与访问时间重合时，视为访问前已撤回。
2. **凭据必须覆盖本次目的**：访问当时若存在覆盖该处理目的的有效同意，签署必须
   引用这条凭据；其他用途的同意不能借用。访问后才签署的同意只能标为
   「访问后补登同意，不追溯」，不能作为授权引用。
3. **历史结论冻结**：签署后 `签署存档` 不再改动。补证或补录只能
   - 归入该事件仍在进行的待核查复核（结论按最新核查更新，并给出冲突提示），或
   - 在该事件上另立一次待核查事项（原签署结论保持签署时状态）。
4. **补录归并**：`consent_registry` 登记新记录后，`create_effects` 会把凭据
   归入同主体、同目的访问事件对应的复核，并在返回值 `extra.purpose_reviews`
   中说明是「归入当前审查」还是「形成该事件上另一次待核查事项」。

复核单不进入运营概览统计（`Store.AUXILIARY_MODULES`），只在审计详情页读取。

领域：数据工程
子方向：数据分析与数据应用
