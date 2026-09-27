"""操作人上下文：从请求头识别当前身份与角色。

平台暂无独立登录体系，前端在顶栏切换「值班人员 / 站点管理员」身份，
每个写请求带上 X-Operator-Name、X-Operator-Role。
HTTP 头只允许 ASCII，姓名/角色含中文，因此请求头统一放 base64(UTF-8) 文本；
识别不到、解码失败或角色不可信时按最小权限（值班人员）处理，
避免越权默认成管理员。
"""
from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass

from fastapi import Header

ADMIN_ROLE = "站点管理员"
DUTY_ROLE = "值班人员"
ROLES = (ADMIN_ROLE, DUTY_ROLE)
DEFAULT_OPERATOR = "值班人员"


@dataclass(frozen=True)
class Operator:
    """当前操作人：姓名 + 角色，权限判断只认角色不认前端传的按钮显隐。"""

    name: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == ADMIN_ROLE


def _decode_header(value: str | None) -> str:
    """解码 base64(UTF-8) 请求头；任何异常都按空值处理，转最小权限。"""
    if not value:
        return ""
    try:
        return base64.b64decode(value, validate=True).decode("utf-8").strip()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        return ""


def get_operator(
    x_operator_name: str | None = Header(default=None, alias="X-Operator-Name"),
    x_operator_role: str | None = Header(default=None, alias="X-Operator-Role"),
) -> Operator:
    """从请求头解析操作人；角色不可信或缺失时降为值班人员。"""
    name = _decode_header(x_operator_name) or DEFAULT_OPERATOR
    role = _decode_header(x_operator_role)
    if role not in ROLES:
        role = DUTY_ROLE
    return Operator(name=name, role=role)
