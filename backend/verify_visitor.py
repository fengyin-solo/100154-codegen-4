"""外来人员进站许可业务规则端到端验证（FastAPI TestClient）。

覆盖：登记/历史数据可读、状态推进、授权只在放行后生效、名单核对拦截、
值班越权拦截、管理员改授权、同单位同时段唯一、列表-详情一致性。
"""
import base64

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def h(name: str, role: str) -> dict[str, str]:
    return {"X-Operator-Name": b64(name), "X-Operator-Role": b64(role)}


ADMIN = h("站点管理员", "站点管理员")
DUTY_ZHOU = h("周凯", "值班人员")
DUTY_LIN = h("林晓", "值班人员")
DUTY_NEW = h("新值班员", "值班人员")

passed = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global passed
    assert cond, f"[FAIL] {name}: {detail}"
    passed += 1
    print(f"[ok] {name}")


def post(path, body, headers):
    return client.post(path, json=body, headers=headers)


# 0. 历史数据（id=1，缺随行人员/登记人）仍可读，且授权随状态派生为已失效
r = client.get("/api/visitor/1")
check("历史数据仍可读取", r.status_code == 200, r.text)
d = r.json()
check("历史数据名单缺字段兜底为空、人数0", d["随行人员"] == "" and d["随行人数"] == 0, str(d))
check("历史数据已离站授权已失效", d["门禁授权"] == "已失效" and d["门禁授权生效"] is False, str(d["门禁授权"]))

# 1. 列表读得到 5 条种子
r = client.get("/api/visitor?size=200")
items = r.json()["items"]
check("种子许可共5条", r.json()["total"] == 5, str(r.json()["total"]))
check("列表行授权与名单字段一致", all("门禁授权" in x and "随行人数" in x for x in items))

# 2. 缺字段登记被拦
r = post("/api/visitor", {"values": {"来访单位": "某单位"}}, DUTY_ZHOU)
check("缺必填字段被拦", r.json()["ok"] is False and "缺少必填字段" in r.json()["message"], r.text)

# 3. 时段倒置被拦
r = post("/api/visitor", {"values": {
    "来访单位": "时序测试单位", "进站事由": "检修",
    "进站开始": "2026-10-01 15:00", "进站结束": "2026-10-01 14:00",
    "随行人员": "张三、李四",
}}, DUTY_ZHOU)
check("时段倒置被拦", r.json()["ok"] is False and "结束时刻必须晚于" in r.json()["message"], r.text)

# 4. 同单位同时段重叠被拦，并指出已有申请
r = post("/api/visitor", {"values": {
    "来访单位": "省大气探测技术保障中心", "进站事由": "顺访",
    "进站开始": "2026-09-28 10:00", "进站结束": "2026-09-28 11:00",
    "随行人员": ["王建军"],
}}, DUTY_ZHOU)
check("同单位同时段唯一被拦", r.json()["ok"] is False and "VISIT-0002" in r.json()["message"], r.text)

# 4b. 同单位不重叠时段允许登记（首尾相接也允许）
r = post("/api/visitor", {"values": {
    "来访单位": "省大气探测技术保障中心", "进站事由": "复查",
    "进站开始": "2026-09-28 12:00", "进站结束": "2026-09-28 13:00",
    "随行人员": "王建军,李志强",
}}, DUTY_ZHOU)
new_id = r.json().get("entry", {}).get("id")
check("同单位非重叠时段可登记", r.json()["ok"] is True, r.text)
check("名单字符串自动归一化为2人", r.json()["entry"]["随行人数"] == 2, r.text)

# 5. 待受理时门禁未授权，值班人员无法开授权
r = client.get(f"/api/visitor/{new_id}")
check("待受理授权未生效", r.json()["门禁授权"] == "未授权", str(r.json()["门禁授权"]))
r = post(f"/api/visitor/{new_id}/actions", {"values": {"action": "开启门禁授权"}}, DUTY_ZHOU)
check("值班员开授权被挡并说明归属",
      r.json()["ok"] is False and "只能由站点管理员改动" in r.json()["message"] and "周凯" in r.json()["message"], r.text)

# 6. 待受理不能直接登记进站（乱序拦截）
r = post(f"/api/visitor/{new_id}/actions", {"values": {"action": "登记进站", "随行人员": ["王建军", "李志强"]}}, DUTY_ZHOU)
check("跳过放行直接进站被拦", r.json()["ok"] is False and "只有已放行" in r.json()["message"], r.text)

# 7. 别的值班人员不能放行这条周凯的许可
r = post(f"/api/visitor/{new_id}/actions", {"values": {"action": "受理放行"}}, DUTY_LIN)
check("非归属值班员放行被拦并说明归属", r.json()["ok"] is False and "由「周凯」登记" in r.json()["message"], r.text)

# 8. 归属值班员放行成功，门禁授权自动生效
r = post(f"/api/visitor/{new_id}/actions", {"values": {"action": "受理放行"}}, DUTY_ZHOU)
check("归属值班员放行成功", r.json()["ok"] is True and r.json()["entry"]["status"] == "已放行", r.text)
check("放行后授权生效", r.json()["entry"]["门禁授权"] == "已授权" and r.json()["entry"]["门禁授权生效"] is True, r.text)

# 9. 进站名单核对：缺1人（少李志强）+ 多1人（陌生王五），要指出差在哪一位
r = post(f"/api/visitor/{new_id}/actions", {"values": {"action": "登记进站", "随行人员": ["王建军", "王五"]}}, DUTY_ZHOU)
msg = r.json()["message"]
check("名单不符进站被拦", r.json()["ok"] is False and "进站已拦下" in msg, r.text)
check("指出哪位没到（含位次）", "李志强（第2位）" in msg, msg)
check("指出哪位多出", "王五" in msg and "不在登记名单" in msg, msg)
check("给出人数差异", "登记 2 人，实到 2 人" in msg, msg)
check("名单不符状态仍停留在已放行", client.get(f"/api/visitor/{new_id}").json()["status"] == "已放行")

# 10. 名单一致进站成功
r = post(f"/api/visitor/{new_id}/actions", {"values": {"action": "登记进站", "随行人员": ["李志强", "王建军"]}}, DUTY_ZHOU)
check("名单一致(顺序无关)进站成功", r.json()["ok"] is True and r.json()["entry"]["status"] == "已进站", r.text)

# 11. 管理员关闭授权（进站期间）生效；值班员关闭被拦
r = post(f"/api/visitor/{new_id}/actions", {"values": {"action": "关闭门禁授权"}}, DUTY_ZHOU)
check("值班员关授权被拦", r.json()["ok"] is False and "只能由站点管理员改动" in r.json()["message"], r.text)
r = post(f"/api/visitor/{new_id}/actions", {"values": {"action": "关闭门禁授权"}}, ADMIN)
check("管理员关闭授权成功", r.json()["ok"] is True and r.json()["entry"]["门禁授权"] == "已停用", r.text)
r = post(f"/api/visitor/{new_id}/actions", {"values": {"action": "开启门禁授权"}}, ADMIN)
check("管理员重开授权成功", r.json()["ok"] is True and r.json()["entry"]["门禁授权生效"] is True, r.text)

# 12. 离站后授权自动失效
r = post(f"/api/visitor/{new_id}/actions", {"values": {"action": "登记离站"}}, DUTY_ZHOU)
check("离站成功", r.json()["ok"] is True and r.json()["entry"]["status"] == "已离站", r.text)
check("离站后授权自动失效", r.json()["entry"]["门禁授权"] == "已失效" and r.json()["entry"]["门禁授权生效"] is False, r.text)
# 详情与列表里的同一条数据一致
r = client.get(f"/api/visitor/{new_id}")
check("详情与列表授权一致", r.json()["门禁授权"] == "已失效", r.text)
lst = [x for x in client.get("/api/visitor?size=200").json()["items"] if x["id"] == new_id][0]
check("返回列表刷新后授权仍一致", lst["门禁授权"] == "已失效" and "门禁授权自动失效" in lst["门禁授权记录"], str(lst))

# 13. 已离站不能再操作开关授权
r = post(f"/api/visitor/{new_id}/actions", {"values": {"action": "开启门禁授权"}}, ADMIN)
check("离站后不能开授权", r.json()["ok"] is False and "只在放行之后" in r.json()["message"], r.text)

# 14. 身份头缺失/伪造时降为值班最小权限
r = post(f"/api/visitor/3/actions", {"values": {"action": "关闭门禁授权"}},
         h("hacker", "超级管理员"))
check("伪造角色被降级并拦截", r.json()["ok"] is False and "只能由站点管理员改动" in r.json()["message"], r.text)

# 15. 管理员可处置任意许可（放行待受理的种子 2）
r = post("/api/visitor/2/actions", {"values": {"action": "受理放行"}}, ADMIN)
check("管理员可跨归属放行", r.json()["ok"] is True and r.json()["entry"]["status"] == "已放行", r.text)

# 16. 新建许可归属当前操作人，新值班员只可查看他人许可
r = post("/api/visitor", {"values": {
    "来访单位": "全新来访单位", "进站事由": "测试归属",
    "进站开始": "2026-11-01 09:00", "进站结束": "2026-11-01 10:00",
    "随行人员": ["钱七"],
}}, DUTY_NEW)
nid2 = r.json()["entry"]["id"]
r = post(f"/api/visitor/{nid2}/actions", {"values": {"action": "受理放行"}}, DUTY_ZHOU)
check("新值班员的许可他人不可动", r.json()["ok"] is False and "由「新值班员」登记" in r.json()["message"], r.text)
check("但列表可查看", any(x["id"] == nid2 for x in client.get("/api/visitor?size=200").json()["items"]))

# 17. 状态筛选
r = client.get("/api/visitor?status=待受理")
check("按状态筛选", r.json()["total"] == 0 or all(x["status"] == "待受理" for x in r.json()["items"]))
r = client.get("/api/visitor?status=已离站")
check("已离站含历史与新完成", r.json()["total"] >= 3, str(r.json()["total"]))

print(f"\n全部 {passed} 项断言通过 ✅")
