#!/usr/bin/env python3
"""計算各類事件公布後，加權指數與費城半導體指數的歷史波動，產生 data/impact.json。
網站「本週重點」用它來排序：歷史上公布後波動越大的事件類型越重要（不分漲跌）。

方法：
- 股價：Yahoo Finance 日收盤（^TWII 加權指數、^SOX 費城半導體），最近 10 年。
- 反應日：事件公布後第一個有開盤、能反應消息的交易日。
  美國盤中／盤後公布（FOMC、CPI、非農、輝達財報）→ 費半看美國當天（輝達盤後公布看隔天），加權看台灣隔天。
  日銀（台灣上午公布）→ 加權看當天、費半看美國當天；台積電（台灣收盤後）→ 加權看隔天、費半看美國當天。
  結算、四巫日、MSCI 生效 → 看當天。
- 指標：反應日漲跌幅的絕對值（不分漲跌）；和所有交易日的平均比較（倍數）；
  「大波動比例」＝反應日落在所有交易日波動前 20% 的比例（平常就是 20%）。
  另外算最近 3 年（和最近 3 年的平常日比較），因為市場環境會變。
- 歷史日期在 data/impact_dates.json；之後發生的事件從 data/events.json 自動補上，樣本會越來越多。
只用 Python 標準函式庫。
"""
import json
import re
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TW = timezone(timedelta(hours=8))
YEARS = 10
RECENT = 3

# 事件類型：網站用的標題規則、怎麼對應反應日（tw / us：same 當天、next 隔一個交易日、None 不算）
TYPES = {
    "fomc": {"re": r"FOMC 利率決議", "tw": "next", "us": "same"},
    "cpi":  {"re": r"美國\d+月 CPI", "tw": "next", "us": "same"},
    "nfp":  {"re": r"非農就業", "tw": "next", "us": "same"},
    "boj":  {"re": r"日本央行（BOJ）利率決議", "tw": "same", "us": "same"},
    "nvda": {"re": r"（NVDA）.*財報", "tw": "next", "us": "next"},
    "tsmc": {"re": r"台積電（2330）.*法說", "tw": "next", "us": "same"},
    "txo":  {"n": "台指期貨／選擇權結算", "re": r"台指期貨／選擇權月結算", "tw": "same", "us": None},
    "quad": {"n": "四巫日", "re": r"四巫日", "tw": "same", "us": "same"},
    "msci": {"n": "MSCI 季度調整生效", "re": r"MSCI .*審核生效", "tw": "same", "us": None},
}


def prices(symbol, start):
    url = ("https://query1.finance.yahoo.com/v8/finance/chart/" + urllib.request.quote(symbol)
           + f"?period1={int(datetime(start.year, start.month, start.day).timestamp())}"
           + f"&period2={int(datetime.now().timestamp())}&interval=1d")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; investor-calendar-bot/1.0)"})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.load(r)["chart"]["result"][0]
    off = j["meta"].get("gmtoffset", 0)
    closes = j["indicators"]["quote"][0]["close"]
    out = []
    for ts, c in zip(j["timestamp"], closes):
        if c is None:
            continue
        d = datetime.fromtimestamp(ts + off, timezone.utc).date()
        if out and out[-1][0] == d:
            out[-1] = (d, c)
        else:
            out.append((d, c))
    rets = {}
    for (d0, c0), (d1, c1) in zip(out, out[1:]):
        rets[d1] = abs(c1 / c0 - 1) * 100
    return rets


def third_weekday(y, m, wd):
    d = date(y, m, 15)
    return d + timedelta(days=(wd - d.weekday()) % 7)


def rule_dates(kind, start, end):
    out = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        if kind == "txo":
            out.append(third_weekday(y, m, 2))                 # 第三個星期三
        elif kind == "quad" and m in (3, 6, 9, 12):
            out.append(third_weekday(y, m, 4))                 # 第三個星期五
        elif kind == "msci" and m in (2, 5, 8, 11):
            out.append(date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))   # 月底（再對齊交易日）
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return [d for d in out if start <= d <= end]


def reaction(rets_days, d, how, back=False):
    """rets_days 為排序好的交易日。same：當天（休市則下一個，結算類則上一個）；next：之後第一個交易日。"""
    import bisect
    if how == "same":
        i = bisect.bisect_left(rets_days, d)
        if back and (i == len(rets_days) or rets_days[i] != d):
            i -= 1
    else:
        i = bisect.bisect_right(rets_days, d)
    return rets_days[i] if 0 <= i < len(rets_days) else None


def stats(values, base_sorted, base_avg):
    if not values:
        return None
    top20 = base_sorted[int(len(base_sorted) * 0.8)]
    avg = sum(values) / len(values)
    return {"n": len(values), "avg": round(avg, 2), "x": round(avg / base_avg, 2),
            "big": round(sum(v >= top20 for v in values) / len(values) * 100)}


def main():
    today = datetime.now(TW).date()
    start = date(today.year - YEARS, today.month, 1)
    recent = date(today.year - RECENT, today.month, today.day)
    hist = json.loads((DATA / "impact_dates.json").read_text(encoding="utf-8"))["types"]
    events = json.loads((DATA / "events.json").read_text(encoding="utf-8"))["events"]

    try:
        idx = {"tw": prices("^TWII", start - timedelta(days=10)), "us": prices("^SOX", start - timedelta(days=10))}
    except Exception as e:
        print(f"::warning::抓不到股價（{e}），沿用上次的 impact.json")
        return

    out = {"updated": datetime.now(TW).strftime("%Y/%m/%d"), "years": YEARS, "base": {}, "types": {}}
    for k, r in idx.items():
        days = sorted(d for d in r if d >= start)
        vals = sorted(r[d] for d in days)
        rv = sorted(r[d] for d in days if d >= recent)
        out["base"][k] = {"avg": round(sum(vals) / len(vals), 2), "top20": round(vals[int(len(vals) * 0.8)], 2),
                          "days": len(vals), "recent_avg": round(sum(rv) / len(rv), 2),
                          "_days": days, "_sorted": vals, "_rsorted": rv}

    for key, t in TYPES.items():
        ds = set(hist.get(key, {}).get("dates", []))
        for e in events:                                   # 之後的事件從行事曆自動補上
            if re.search(t["re"], e["t"]) and e["d"] < today.isoformat():
                ds.add(e["d"])
        dates = sorted(date.fromisoformat(d) for d in ds)
        if key in ("txo", "quad", "msci"):
            dates = sorted(set(dates) | set(rule_dates(key, start, today - timedelta(days=1))))
        dates = [d for d in dates if start <= d < today]
        res = {"n": t.get("n") or hist.get(key, {}).get("n", key), "u": hist.get(key, {}).get("u", "")}
        for side in ("tw", "us"):
            how = t[side]
            if not how:
                continue
            b = out["base"][side]
            back = key in ("txo", "quad", "msci")
            seen, all_v, rec_v = set(), [], []
            for d in dates:
                rd = reaction(b["_days"], d, how, back)
                if not rd or rd in seen or rd >= today or (rd - d).days > 6:
                    continue
                seen.add(rd)
                all_v.append(idx[side][rd])
                if d >= recent:
                    rec_v.append(idx[side][rd])
            s = stats(all_v, b["_sorted"], b["avg"])
            if s:
                rs = stats(rec_v, b["_rsorted"], sum(b["_rsorted"]) / len(b["_rsorted"]))
                s["recent"] = rs and {"n": rs["n"], "avg": rs["avg"], "x": rs["x"]}
                res[side] = s
        out["types"][key] = res
        print(key, {s: res.get(s) for s in ("tw", "us")})

    for b in out["base"].values():
        b.pop("_days"), b.pop("_sorted"), b.pop("_rsorted")
    (DATA / "impact.json").write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
