"""幫事件加上「新增」「變動」標記，給網站顯示「新」「改」小標籤用。

比對上一版 events.json 與這一版：
  fs  第一次出現的日期（YYYY-MM-DD）；"0" 表示啟用此功能前就已存在
  cg  最近一次變動 {"on": 日期, "what": "日期 10/28→10/21；預估→官方"}
同一事件的認定：類別＋標題相同。標題相同但日期不同的（例如財報改期），視為同一事件的日期變動。
"""
from collections import defaultdict


def _md(iso):
    return f"{int(iso[5:7])}/{int(iso[8:10])}" if iso else "—"


def _diff(old, new):
    what = []
    if old.get("d") != new.get("d"):
        what.append(f"日期 {_md(old.get('d'))}→{_md(new.get('d'))}")
    elif old.get("e") != new.get("e"):
        what.append(f"結束日 {_md(old.get('e'))}→{_md(new.get('e'))}")
    if old.get("st") == "e" and new.get("st") == "o":
        what.append("預估→官方")
    if old.get("tm") and new.get("tm") and old["tm"] != new["tm"]:
        what.append("時間更新")
    return "；".join(what)


def annotate(old_events, new_events, today):
    """回傳加好 fs / cg 的 new_events（就地修改）。"""
    baseline = not any("fs" in e for e in old_events)
    pool = defaultdict(list)
    for o in old_events:
        pool[(o.get("c"), o.get("t"))].append(o)

    unmatched = []
    for n in new_events:
        cands = pool.get((n.get("c"), n.get("t")))
        hit = next((o for o in cands or [] if o.get("d") == n.get("d")), None)
        if hit:
            cands.remove(hit)
            _carry(hit, n, today)
        else:
            unmatched.append(n)
    # 同標題但日期不同：依日期順序一對一配對，視為改期
    for n in sorted(unmatched, key=lambda e: e.get("d", "")):
        cands = pool.get((n.get("c"), n.get("t")))
        if cands:
            hit = min(cands, key=lambda o: o.get("d", ""))
            cands.remove(hit)
            _carry(hit, n, today)
        else:
            n["fs"] = "0" if baseline else today
            n.pop("cg", None)
    return new_events


def _carry(old, new, today):
    new["fs"] = old.get("fs", "0")
    what = _diff(old, new)
    if what:
        new["cg"] = {"on": today, "what": what}
    elif old.get("cg"):
        new["cg"] = old["cg"]
    else:
        new.pop("cg", None)
