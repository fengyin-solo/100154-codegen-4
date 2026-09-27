"""外来人员进站许可业务规则：状态流转、门禁授权权限、随行人员核对都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "visitor"
REQUIRED_FIELDS = ["来访单位", "进站事由", "进站时段"]
STATUS_ORDER = ["待受理", "已放行", "已进站", "已离站"]
GATE_PENDING = "未授权"
GATE_ACTIVE = "已授权"
GATE_REVOKED = "已撤销"
GATE_EXPIRED = "已失效"
ADMIN_ROLE = "站点管理员"

# 状态类动作：推动许可沿 待受理→已放行→已进站→已离站 前进
ACTION_RULES = {"放行许可": "已放行", "登记进站": "已进站", "登记离站": "已离站"}
ACTION_DONE = {"放行许可": "已放行", "登记进站": "已登记进站", "登记离站": "已登记离站"}
# 门禁类动作：只改门禁授权，不动许可状态，且只能由站点管理员执行
GATE_ACTIONS = {"授予门禁": GATE_ACTIVE, "撤销门禁": GATE_REVOKED}


class VisitorService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._normalize(row) for row in store.rows(MODULE)]
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("许可编号", "")) or keyword in str(row.get("来访单位", ""))
            ]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None
        return self._normalize(entry)

    def create_entry(self, values: dict[str, Any], operator: str) -> tuple[dict[str, Any] | None, str]:
        """登记进站申请；返回 (许可, 错误信息)，错误信息为空表示成功。"""
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, f"缺少必填字段：{'、'.join(missing)}"
        attendees = self._parse_attendees(values.get("随行人员"))
        if not attendees:
            return None, "缺少必填字段：随行人员（进站登记必须附随行人员名单）"
        unit = str(values["来访单位"]).strip()
        slot = str(values["进站时段"]).strip()
        for row in store.rows(MODULE):
            if row.get("status") == STATUS_ORDER[-1]:
                continue  # 已离站的是历史记录，不占用同时段名额
            if str(row.get("来访单位")) == unit and str(row.get("进站时段")) == slot:
                return None, (
                    f"同一来访单位同时段只保留一条进站申请：{unit} 在 {slot} "
                    f"已有 {row.get('许可编号')}（{row.get('status')}），本次登记被拦下"
                )
        rows = store.rows(MODULE)
        entry_id = max((int(row.get("id", 0)) for row in rows), default=0) + 1
        entry: dict[str, Any] = {
            "id": entry_id,
            "许可编号": f"VISI-{entry_id:04d}",
            "来访单位": unit,
            "进站事由": str(values["进站事由"]).strip(),
            "进站时段": slot,
            "随行人员": attendees,
            "门禁授权": GATE_PENDING,
            "登记人": operator,
            "status": STATUS_ORDER[0],
            "pending": True,
            "abnormal": False,
        }
        rows.append(self._normalize(entry))
        return entry, ""

    def run_action(
        self,
        entry_id: int,
        action: str,
        *,
        operator: str,
        role: str,
        values: dict[str, Any],
    ) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"进站许可 {entry_id} 不存在或已归档"
        self._normalize(entry)
        if action in GATE_ACTIONS:
            return self._run_gate_action(entry, action, operator, role)
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于进站许可可执行范围"
        ownership = self._ownership_error(entry, operator, role)
        if ownership:
            return None, ownership
        target = ACTION_RULES[action]
        expected = STATUS_ORDER[STATUS_ORDER.index(target) - 1]
        if entry["status"] != expected:
            return None, (
                f"当前状态为「{entry['status']}」，不能执行「{action}」；"
                f"进站许可需按 {'→'.join(STATUS_ORDER)} 顺序推进"
            )
        if action == "登记进站":
            if entry["门禁授权"] != GATE_ACTIVE:
                return None, (
                    f"门禁授权未生效（当前为{entry['门禁授权']}），"
                    "不能登记进站，请站点管理员先授予门禁"
                )
            actual = self._parse_attendees(values.get("实际随行人员"))
            if not actual:
                return None, "登记进站需提交实际到场随行人员名单，用于与登记名单逐一核对"
            problems = self._diff_attendees(entry["随行人员"], actual)
            if problems:
                return None, "随行人员与登记名单不一致，已拦下：" + "；".join(problems)
        entry["status"] = target
        entry["许可状态"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = False
        if action == "登记离站":
            entry["门禁授权"] = GATE_EXPIRED
        return entry, f"进站许可{ACTION_DONE[action]}（{entry['许可编号']}）"

    def _run_gate_action(
        self,
        entry: dict[str, Any],
        action: str,
        operator: str,
        role: str,
    ) -> tuple[dict[str, Any] | None, str]:
        if role != ADMIN_ROLE:
            return None, (
                f"越权改动已被挡下：门禁授权只能由站点管理员改动，"
                f"当前身份为{role}（{operator or '未署名'}）"
            )
        if action == "授予门禁":
            if entry["status"] == STATUS_ORDER[0]:
                return None, "许可尚未放行，门禁授权只在放行之后生效"
            if entry["status"] == STATUS_ORDER[-1]:
                return None, "许可已离站，门禁授权已失效，如需再次进站请重新登记申请"
            entry["门禁授权"] = GATE_ACTIVE
            return entry, f"门禁授权已生效（{entry['许可编号']}）"
        if entry["门禁授权"] != GATE_ACTIVE:
            return None, f"当前门禁授权为「{entry['门禁授权']}」，没有可撤销的授权"
        entry["门禁授权"] = GATE_REVOKED
        return entry, f"门禁授权已撤销（{entry['许可编号']}）"

    @staticmethod
    def _ownership_error(entry: dict[str, Any], operator: str, role: str) -> str | None:
        """值班人员只能改动自己登记的许可，站点管理员不受限；越权时说明许可归属。"""
        if role == ADMIN_ROLE:
            return None
        owner = str(entry.get("登记人") or "")
        if operator and operator == owner:
            return None
        return (
            f"越权改动已被挡下：该进站许可归属{entry.get('来访单位')}，"
            f"由{owner}登记，{role}{operator or '（未署名）'}只能查看，不能改动"
        )

    @staticmethod
    def _diff_attendees(registered: list[str], actual: list[str]) -> list[str]:
        """逐一比对登记名单与实到名单，指出差在哪一位。"""
        problems: list[str] = []
        if len(registered) != len(actual):
            problems.append(f"人数不一致：登记 {len(registered)} 人、实到 {len(actual)} 人")
        for index, name in enumerate(registered):
            if index >= len(actual):
                problems.append(f"第 {index + 1} 位「{name}」登记在册但未到场")
            elif actual[index] != name:
                problems.append(f"第 {index + 1} 位登记为「{name}」，实到为「{actual[index]}」")
        for index, name in enumerate(actual):
            if index >= len(registered):
                problems.append(f"第 {index + 1} 位「{name}」不在登记名单内")
        return problems

    @staticmethod
    def _parse_attendees(raw: Any) -> list[str]:
        """随行人员可以是名单数组，也可以是顿号、逗号或换行分隔的一段文字。"""
        if isinstance(raw, list):
            return [str(name).strip() for name in raw if str(name).strip()]
        if raw is None:
            return []
        text = str(raw)
        for sep in ["，", "、", ",", ";", "；", "\n"]:
            text = text.replace(sep, " ")
        return [name for name in (part.strip() for part in text.split(" ")) if name]

    @staticmethod
    def _normalize(row: dict[str, Any]) -> dict[str, Any]:
        """补齐历史记录缺少的字段，保证旧数据仍然能读取、能展示。"""
        attendees = row.get("随行人员")
        if isinstance(attendees, str):
            attendees = VisitorService._parse_attendees(attendees)
        if not isinstance(attendees, list):
            attendees = []
        row["随行人员"] = [str(name) for name in attendees]
        row["随行人数"] = len(row["随行人员"])
        row.setdefault("门禁授权", GATE_PENDING)
        row.setdefault("登记人", "—")
        row.setdefault("来访单位", "—")
        row.setdefault("进站事由", "—")
        row.setdefault("进站时段", "—")
        row.setdefault("许可编号", f"VISI-{int(row.get('id', 0)):04d}")
        status = str(row.get("status") or STATUS_ORDER[0])
        row["status"] = status
        row["许可状态"] = status
        return row
