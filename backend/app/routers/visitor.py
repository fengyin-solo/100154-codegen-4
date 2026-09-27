"""外来人员进站许可接口：登记申请、状态推进、门禁授权与进站名单核对。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.security import Operator, get_operator
from app.services.visitor import STATUS_ORDER, VIEW_FIELDS, VisitorService

router = APIRouter(prefix="/api/visitor", tags=["外来人员进站许可"])

service = VisitorService()


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按来访单位、许可编号或随行人员检索"),
    status: str | None = Query(default=None, description="待受理、已放行、已进站、已离站"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按来访单位与状态过滤进站许可；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/statuses")
def status_meta() -> dict[str, Any]:
    """许可状态序列与展示字段，供前端渲染推进按钮与表头。"""
    return {"statuses": STATUS_ORDER, "fields": VIEW_FIELDS}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict[str, Any]:
    """读取单条进站许可明细；历史数据缺字段时由服务层补齐，不存在才报错。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"进站许可 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload, operator: Operator = Depends(get_operator)) -> ActionResult:
    """登记一条进站申请；缺字段、时段非法或同单位同时段重复都说明原因。"""
    entry, error, missing = service.create_entry(payload.values, operator)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if error:
        return ActionResult(ok=False, message=error)
    return ActionResult(ok=True, message="进站申请已登记，等待受理", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(
    entry_id: int, payload: EntryPayload, operator: Operator = Depends(get_operator)
) -> ActionResult:
    """推进许可状态或开关门禁授权；越权、乱序、名单不符都会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action, payload.values, operator)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
