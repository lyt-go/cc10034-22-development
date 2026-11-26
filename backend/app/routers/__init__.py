"""业务路由汇总：跨模块链接路由必须先于通用资源路由注册。"""
from __future__ import annotations

from app.routers import cross_links, purpose_review, resource

ROUTERS = [cross_links, purpose_review, resource]
