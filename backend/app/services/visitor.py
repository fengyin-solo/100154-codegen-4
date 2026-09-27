"""外来人员进站许可业务规则。

规则要点：
- 许可状态按 待受理 → 已放行 → 已进站 → 已离站 单向推进，不能跳跃或回退；
- 门禁授权不是任意可写字段，而是由放行/离站动作和管理员的授权开关共同决定，
  只在放行之后才可能生效，保证列表、详情看到的授权状态始终同源一致；
- 进站时核对随行人员，与登记名单不一致则拦下，并指出差在哪一位；
- 门禁授权只能由站点管理员改动；值班人员只能查看、不能改动别人的许可；
- 同一来访单位、进站时段重叠的申请只留一条；
- 历史数据可能缺少新字段（名单、归属、授权痕迹），读取时做归一化，照常可读。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from app.security import ADMIN_ROLE, Operator
from app.store import store

MODULE = "visitor"

REQUIRED_FIELDS = ["来访单位", "进站事由", "进站开始", "进站结束", "随行人员"]

STATUS_PENDING = "待受理"
STATUS_RELEASED = "已放行"
STATUS_ENTERED = "已进站"
STATUS_LEFT = "已离站"
STATUS_ORDER = [STATUS_PENDING, STATUS_RELEASED, STATUS_ENTERED, STATUS_LEFT]

ACTION_RELEASE = "受理放行"
ACTION_ENTER = "登记进站"
ACTION_LEAVE = "登记离站"
ACTION_GRANT = "开启门禁授权"
ACTION_REVOKE = "关闭门禁授权"
# 改变许可状态的动作必须严格沿状态序列前进；授权开关只影响授权、不改状态。
STATUS_ACTIONS = {
    ACTION_RELEASE: STATUS_RELEASED,
    ACTION_ENTER: STATUS_ENTERED,
    ACTION_LEAVE: STATUS_LEFT,
}

# 列表/详情对外的稳定字段顺序，历史数据缺失的字段由视图层补齐。
VIEW_FIELDS = [
    "许可编号", "来访单位", "进站事由", "进站开始", "进站结束",
    "随行人员", "随行人数", "登记人", "登记站点",
]


def _parse_roster(value: Any) -> list[str]:
    """把登记名单统一成去重保序的姓名列表。

    历史数据里名单可能是逗号分隔字符串、列表，甚至字段缺失，都在这里兜底。
    """
    if value is None:
        return []
    if isinstance(value, str):
        raw = value.replace("，", ",").replace("、", ",").replace(";", ",").replace("；", ",").split(",")
    elif isinstance(value, (list, tuple)):
        raw = [str(item) for item in value]
    else:
        raw = [str(value)]
    names: list[str] = []
    for item in raw:
        name = item.strip()
        if name and name not in names:
            names.append(name)
    return names


def _parse_moment(value: Any) -> datetime | None:
    """解析进站时刻，兼容 'YYYY-MM-DD HH:MM'、'YYYY-MM-DDTHH:MM' 与只有日期。"""
    if value is None:
        return None
    text = str(value).strip().replace("T", " ")
    if not text:
        return None
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, pattern)
        except ValueError:
            continue
    return None


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    """把存储行补全成视图结构：名单、人数、授权状态都在这里派生。

    历史数据没有 随行人员/登记人/门禁开关 等字段时不报错，按空值兜底，
    授权状态严格跟随许可状态：待受理即未授权，已离站即已失效。
    """
    view = dict(row)
    roster = _parse_roster(row.get("随行人员"))
    view["随行人员"] = "、".join(roster)
    view["随行人员名单"] = roster
    view["随行人数"] = len(roster)
    view.setdefault("许可编号", row.get("许可编号") or f"VISIT-{int(row.get('id', 0)):04d}")
    view.setdefault("来访单位", "（历史数据，未登记单位）")
    view.setdefault("进站事由", "")
    view.setdefault("登记人", None)
    view.setdefault("登记站点", "本观测场")
    status = str(row.get("status") or STATUS_PENDING)
    view["status"] = status

    manual = bool(row.get("门禁手动开启", False))
    if status == STATUS_PENDING:
        auth_state, auth_effective = "未授权", False
    elif status == STATUS_LEFT:
        auth_state, auth_effective = "已失效", False
    else:
        auth_effective = manual
        auth_state = "已授权" if manual else "已停用"
    view["门禁授权"] = auth_state
    view["门禁授权生效"] = auth_effective
    view["门禁授权记录"] = str(row.get("门禁授权记录") or "（无）")
    return view


def _overlaps(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    """两个半开时段是否重叠；首尾相接不算同时段。"""
    return start_a < end_b and start_b < end_a


class VisitorService:
    """进站许可的登记、流转、授权与核对规则，路由层不做业务判断。"""

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(MODULE)
        views = [normalize_row(row) for row in rows]
        if keyword:
            views = [
                row for row in views
                if keyword in str(row.get("来访单位", ""))
                or keyword in str(row.get("许可编号", ""))
                or keyword in str(row.get("随行人员", ""))
            ]
        if status:
            views = [row for row in views if row.get("status") == status]
        total = len(views)
        start = max(page - 1, 0) * size
        return views[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        row = store.find(MODULE, entry_id)
        return normalize_row(row) if row is not None else None

    def create_entry(
        self, values: dict[str, Any], operator: Operator
    ) -> tuple[dict[str, Any] | None, str, list[str]]:
        """登记进站申请。

        返回 (记录, 错误说明, 缺失字段)：成功时错误说明为空；
        业务规则被拦住时错误说明非空，调用方原样展示给值班人员。
        """
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, "", missing

        roster = _parse_roster(values.get("随行人员"))
        if not roster:
            return None, "随行人员名单不能为空，请至少登记一位随行人员", []

        start = _parse_moment(values.get("进站开始"))
        end = _parse_moment(values.get("进站结束"))
        if start is None or end is None:
            return None, "进站时段格式无法识别，请使用 2026-09-27 09:00 这样的时间", []
        if end <= start:
            return None, "进站结束时刻必须晚于进站开始时刻", []

        unit = str(values.get("来访单位") or "").strip()
        rows = store.rows(MODULE)
        for other in rows:
            other_view = normalize_row(other)
            if str(other_view.get("来访单位") or "").strip() != unit:
                continue
            other_start = _parse_moment(other.get("进站开始"))
            other_end = _parse_moment(other.get("进站结束"))
            if (
                other_start is not None and other_end is not None
                and _overlaps(start, end, other_start, other_end)
            ):
                return (
                    None,
                    f"来访单位「{unit}」在 {other_view['进站开始']}～{other_view['进站结束']} "
                    f"已有进站申请（编号 {other_view['许可编号']}，状态{other_view['status']}），"
                    "同一单位同时段只允许一条申请",
                    [],
                )

        entry: dict[str, Any] = {
            "id": max((int(row.get("id", 0)) for row in rows), default=0) + 1,
            "许可编号": f"VISIT-{max((int(row.get('id', 0)) for row in rows), default=0) + 1:04d}",
            "来访单位": unit,
            "进站事由": str(values.get("进站事由") or "").strip(),
            "进站开始": start.strftime("%Y-%m-%d %H:%M"),
            "进站结束": end.strftime("%Y-%m-%d %H:%M"),
            "随行人员": roster,
            "登记站点": str(values.get("登记站点") or "本观测场").strip() or "本观测场",
            "登记人": operator.name,
            "登记人角色": operator.role,
            "status": STATUS_PENDING,
            "pending": True,
            "abnormal": False,
            "门禁手动开启": False,
            "门禁授权记录": "",
        }
        rows.append(entry)
        return normalize_row(entry), "", []

    def run_action(
        self, entry_id: int, action: str, values: dict[str, Any], operator: Operator
    ) -> tuple[dict[str, Any] | None, str]:
        """对许可执行动作；任何越权、乱序、名单不符都在这里被挡下并说明。"""
        row = store.find(MODULE, entry_id)
        if row is None:
            return None, f"进站许可 {entry_id} 不存在或已归档"
        if action not in STATUS_ACTIONS and action not in (ACTION_GRANT, ACTION_REVOKE):
            return None, f"动作「{action}」不属于进站许可可执行范围"

        view = normalize_row(row)
        owner = row.get("登记人")

        # 门禁授权开关：只有站点管理员能动，值班人员一律挡下并说明许可归属。
        if action in (ACTION_GRANT, ACTION_REVOKE):
            if not operator.is_admin:
                owner_text = owner or "历史数据（无登记人记录）"
                return (
                    None,
                    f"门禁授权只能由站点管理员改动，当前身份为{operator.role}；"
                    f"该许可归属「{owner_text}」，无权改动",
                )

        # 状态流转：值班人员只能动自己登记的许可，别人的许可只可查看。
        if action in STATUS_ACTIONS:
            if not operator.is_admin:
                if owner is None:
                    return None, "该许可为历史数据、未记录登记人，仅站点管理员可处置"
                if owner != operator.name:
                    return (
                        None,
                        f"该进站许可由「{owner}」登记，{operator.role}（{operator.name}）"
                        "只能查看，不能改动别人的进站许可",
                    )

        status = str(row.get("status") or STATUS_PENDING)

        if action == ACTION_RELEASE:
            if status != STATUS_PENDING:
                return None, f"当前状态为「{status}」，只有待受理的许可才能受理放行"
            row["status"] = STATUS_RELEASED
            # 放行即授权：门禁授权从此生效，但之后仍可由管理员手动停用。
            row["门禁手动开启"] = True
            self._append_auth_log(row, f"{operator.name}（{operator.role}）受理放行，门禁授权自动生效")
            message = "已放行，门禁授权已生效"

        elif action == ACTION_ENTER:
            if status != STATUS_RELEASED:
                return None, f"当前状态为「{status}」，只有已放行的许可才能登记进站"
            mismatch = self._check_roster(row, values.get("随行人员"))
            if mismatch:
                return None, mismatch
            row["status"] = STATUS_ENTERED
            message = "随行人员与登记名单一致，已登记进站"

        elif action == ACTION_LEAVE:
            if status != STATUS_ENTERED:
                return None, f"当前状态为「{status}」，只有已进站的许可才能登记离站"
            row["status"] = STATUS_LEFT
            # 离站即收权：授权自动失效，手动开关一并复位，保留操作痕迹。
            row["门禁手动开启"] = False
            self._append_auth_log(row, f"{operator.name}（{operator.role}）登记离站，门禁授权自动失效")
            message = "已登记离站，门禁授权已失效"

        elif action == ACTION_GRANT:
            if status not in (STATUS_RELEASED, STATUS_ENTERED):
                return None, f"当前状态为「{status}」，门禁授权只在放行之后才能开启"
            if row.get("门禁手动开启"):
                return None, "门禁授权当前已生效，无需重复开启"
            row["门禁手动开启"] = True
            self._append_auth_log(row, f"{operator.name}（站点管理员）手动开启门禁授权")
            message = "门禁授权已开启"

        else:  # ACTION_REVOKE
            if status not in (STATUS_RELEASED, STATUS_ENTERED):
                return None, f"当前状态为「{status}」，还未放行，门禁授权本就未生效"
            if not row.get("门禁手动开启"):
                return None, "门禁授权当前已是停用状态，无需重复关闭"
            row["门禁手动开启"] = False
            self._append_auth_log(row, f"{operator.name}（站点管理员）手动关闭门禁授权")
            message = "门禁授权已关闭"

        row["pending"] = row["status"] not in (STATUS_LEFT,)
        return normalize_row(row), message

    @staticmethod
    def _append_auth_log(row: dict[str, Any], text: str) -> None:
        stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        history = str(row.get("门禁授权记录") or "").strip()
        row["门禁授权记录"] = f"{history}\n{stamp} {text}".strip()

    @staticmethod
    def _check_roster(row: dict[str, Any], actual_value: Any) -> str:
        """进站核对：实际到岗名单必须与登记名单逐位一致，否则指出差在哪一位。"""
        registered = _parse_roster(row.get("随行人员"))
        actual = _parse_roster(actual_value)
        if not actual:
            return (
                "进站登记的随行人员为空，无法核对；请按登记名单填报实际到岗人员："
                + "、".join(registered)
            )
        missing = [name for name in registered if name not in actual]
        extra = [name for name in actual if name not in registered]
        if not missing and not extra:
            return ""
        parts: list[str] = ["随行人员与登记名单不一致，进站已拦下"]
        if missing:
            parts.append("登记在册但未到岗：" + "、".join(f"{name}（第{registered.index(name) + 1}位）" for name in missing))
        if extra:
            parts.append("到岗但不在登记名单：" + "、".join(extra))
        parts.append(f"登记 {len(registered)} 人，实到 {len(actual)} 人")
        return "；".join(parts)
