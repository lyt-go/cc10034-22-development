import { createRouter, createWebHistory } from 'vue-router'

import Overview from '@/views/Overview.vue'
import AccessAuditDetail from '@/views/AccessAuditDetail.vue'
import WorkbenchView from '@/views/WorkbenchView.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', name: 'overview', component: Overview },
    {
      path: '/access_audit/:entryId',
      name: 'access_audit_detail',
      component: AccessAuditDetail,
      props: true,
    },
    { path: '/:moduleKey', name: 'module', component: WorkbenchView, props: true },
  ],
})

export default router
