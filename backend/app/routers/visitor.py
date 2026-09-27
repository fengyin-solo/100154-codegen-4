"""外来人员进站许可接口：登记进站申请，覆盖放行许可、登记进站、登记离站与门禁授权改动。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.visitor import VisitorService

router = APIRouter(prefix="/api/visitor", tags=["外来人员进站许可"])

service = VisitorService()

LIST_FIELDS = ["许可编号", "来访单位", "进站事由", "进站时段", "随行人数", "门禁授权", "许可状态", "登记人"]
STATUSES = ["待受理", "已放行", "已进站", "已离站"]


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按许可编号或来访单位检索"),
    status: str | None = Query(default=None, description="待受理、已放行、已进站、已离站"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按许可编号、来访单位与状态过滤进站许可列表；没有数据时返回空页，不报错。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_entries(keyword=keyword, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出进站许可清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "visitor", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条进站许可明细；历史已离站记录同样可读，不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"进站许可 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条进站申请；缺字段或同单位同时段重复登记时会说明原因而不是静默丢弃。"""
    operator = str(payload.values.get("operator") or "").strip() or "值班员"
    entry, error = service.create_entry(payload.values, operator)
    if error:
        return ActionResult(ok=False, message=error)
    return ActionResult(ok=True, message="进站许可已登记，等待受理放行", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条进站许可执行放行、进站、离站或门禁授权改动；越权与不合规动作会被挡下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    operator = str(payload.values.get("operator") or "").strip() or "值班员"
    role = str(payload.values.get("role") or "").strip() or "值班人员"
    entry, message = service.run_action(entry_id, action, operator=operator, role=role, values=payload.values)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
