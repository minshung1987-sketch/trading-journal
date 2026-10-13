#!/usr/bin/env python3
"""更新 data/events.json

資料來源：
  1. Yahoo 股市「法說會」專頁   https://tw.stock.yahoo.com/calendar/earnings-call
  2. Yahoo 股市「股東會」專頁（主要），玩股網「股東會時間明細表」（補充）  https://www.wantgoo.com/stock/calendar/shareholders-meeting
  3. 證交所、櫃買中心處置公告（開放資料 API）  處置開始／處置結束
  4. data/events_manual.json   （人工整理：央行、美股財報、年度大會…）

任何一個來源抓失敗，就沿用上一次 events.json 裡該類別的資料，不會把網站弄空。
只用 Python 標準函式庫，不需要 pip install。
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TZ = timezone(timedelta(hours=8))

YAHOO_URL = "https://tw.stock.yahoo.com/calendar/earnings-call"
YAHOO_AGM_URL = "https://tw.stock.yahoo.com/calendar/holders-meeting"
WG_PAGE = "https://www.wantgoo.com/stock/calendar/shareholders-meeting"
WG_API = "https://www.wantgoo.com/stock/calendar/shareholders-meeting-data?market=0"

# 這些公司的法說會會顯示成「主要事件」（有倒數、不會被縮成次要）。想加誰就加代號。
BIG = {"2330", "2317", "2454", "2308", "3008", "2408", "2409", "2412", "3711",
       "2382", "3034", "3037", "2303", "2891", "2882", "2603", "3529", "2395"}
# 股東會裡想標成主要事件的公司
BIG_AGM = {"2330", "2317", "2454", "1101", "2603", "2308"}

UA = {"User-Agent": "Mozilla/5.0 (compatible; investor-calendar-bot/1.0)",
      "Accept-Language": "zh-TW,zh;q=0.9"}


def get(url, referer=None):
    headers = dict(UA)
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=40) as r:
        return r.read().decode("utf-8", "replace")


def clean(s):
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", "", s))).strip()


# ---------- Yahoo 法說會 ----------
def parse_yahoo(html):
    """回傳 events list。頁面是伺服器端產生的 HTML，每一列是一個 <li>。"""
    out = []
    for li in re.split(r'<li class="List\(n\)">', html)[1:]:
        li = li.split("</li>")[0]
        m = re.search(r'quote/(\d{4,6}[A-Z]?)\.TWO?"', li)
        if not m:
            continue
        code = m.group(1)
        # 把標籤換成換行，取得依序的文字欄位：名稱, 代號, 日期時間, 類型, 地點, 訊息
        cells = [clean(x) for x in re.sub(r"<[^>]+>", "\n", li).split("\n")]
        cells = [c for c in cells if c]
        dt = next((c for c in cells if re.fullmatch(r"\d{4}/\d\d/\d\d \d\d:\d\d", c)), None)
        if not dt:
            continue
        i = cells.index(dt)
        name = cells[0]
        kind = cells[i + 1] if len(cells) > i + 1 else ""
        place = cells[i + 2] if len(cells) > i + 2 else ""
        info = cells[i + 3] if len(cells) > i + 3 else ""
        d, tm = dt.split(" ")
        d = d.replace("/", "-")
        if "CEO Week" in info or "CEO Week" in place:
            label = "參加 QIC CEO Week"
        elif "座談會" in info:
            label = "財務業務概況座談會"
        else:
            label = "法說會"
        ev = {"d": d, "c": "tw", "t": f"{name}（{code}）{label}", "tm": tm,
              "st": "o", "u": YAHOO_URL, "a": 1}
        pl = place
        if kind == "國外" and place:
            pl = place
        if pl:
            ev["pl"] = pl
        if info:
            ev["n"] = info
        if code not in BIG:
            ev["mn"] = 1
        out.append(ev)
    return out


# ---------- Yahoo 股東會 ----------
def parse_yahoo_agm(html, today):
    """Yahoo 股東會專頁：每一筆是一個 <button>，有 名稱/代號、日期時間、地點。"""
    out = []
    for blk in html.split("<button")[1:]:
        blk = blk.split("</button>")[0].split(">", 1)[-1]
        m = re.search(r'quote/(\d{4,6}[A-Z]?)\.TWO?"', blk)
        if not m:
            continue
        code = m.group(1)
        cells = [clean(x) for x in re.sub(r"<[^>]+>", "\n", blk).split("\n")]
        cells = [c for c in cells if c]
        dt = next((c for c in cells if re.fullmatch(r"\d{4}/\d\d/\d\d \d\d:\d\d", c)), None)
        if not dt:
            continue
        i = cells.index(dt)
        d, tm = dt.split(" ")
        d = d.replace("/", "-")
        if d < today:
            continue
        place = cells[i + 1] if len(cells) > i + 1 else ""
        ev = {"d": d, "c": "agm", "t": f"{cells[0]}（{code}）股東會", "tm": tm,
              "st": "o", "u": YAHOO_AGM_URL, "a": 1}
        if place:
            ev["pl"] = place
        if code not in BIG_AGM:
            ev["mn"] = 1
        out.append(ev)
    return out


def enrich_with_wantgoo(events, wg_events):
    """玩股網能連上時，用它補上「臨時／常會」與「改選董監事」。"""
    info = {}
    for e in wg_events:
        m = re.search(r"（(\d{4,6}[A-Z]?)）(.+)$", e["t"])
        if m:
            info[(m.group(1), e["d"])] = (m.group(2), e.get("n"))
    for e in events:
        m = re.search(r"（(\d{4,6}[A-Z]?)）", e["t"])
        hit = info.get((m.group(1), e["d"])) if m else None
        if hit:
            e["t"] = re.sub(r"股東會$", hit[0], e["t"])
            if hit[1]:
                e["n"] = hit[1]
    return events


# ---------- 玩股網 股東會 ----------
def roc_to_iso(s):
    y, m, d = (int(x) for x in s.strip().split("/"))
    return f"{y + 1911:04d}-{m:02d}-{d:02d}"


def parse_wantgoo(rows, today):
    out = []
    for r in rows:
        try:
            iso = roc_to_iso(r["chineseTime"])
        except Exception:
            continue
        if iso < today:
            continue
        code = r["stockNo"].strip()
        name = r["name"].strip()
        typ = (r.get("type") or "").strip()
        label = "臨時股東會" if "臨時" in typ else "股東常會"
        ev = {"d": iso, "c": "agm", "t": f"{name}（{code}）{label}",
              "st": "o", "u": WG_PAGE, "a": 1}
        loc = re.sub(r"^開會地點[:：]\s*", "", (r.get("location") or "").strip())
        if loc:
            ev["pl"] = loc
        if (r.get("isReElection") or "").strip() == "是":
            ev["n"] = "改選董監事"
        if code not in BIG_AGM:
            ev["mn"] = 1
        out.append(ev)
    return out


# ---------- 處置股（證交所＋櫃買中心） ----------
TWSE_DISP = "https://openapi.twse.com.tw/v1/announcement/punish"
TPEX_DISP = "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information"


def pick(row, *names):
    """依候選欄位名稱取值（兩個開放資料的欄位名稱不同，也可能改版）。"""
    for n in names:
        for k, v in row.items():
            if k.lower() == n.lower() and str(v).strip():
                return str(v).strip()
    return ""


def roc_dates(s):
    """從字串取出所有日期，支援 115/10/08、1151008、2026/10/08，回傳 ISO 字串 list。"""
    out = []
    for y, m, d in re.findall(r"(\d{2,4})[/\-.年](\d{1,2})[/\-.月](\d{1,2})", s) or \
            re.findall(r"(?<!\d)(\d{3})(\d{2})(\d{2})(?!\d)", s):
        y = int(y)
        y = y + 1911 if y < 1911 else y
        try:
            out.append(datetime(y, int(m), int(d)).strftime("%Y-%m-%d"))
        except ValueError:
            pass
    return out


def parse_disp(rows, market):
    """回傳 [{code, name, s, e, nth, mkt}]，只收 4 位數代號的個股。"""
    out = []
    for r in rows:
        code = pick(r, "Code", "SecuritiesCompanyCode", "SecuritiesCode", "StockNo")
        name = pick(r, "Name", "CompanyName", "SecuritiesName", "StockName")
        period = pick(r, "DispositionPeriod", "DisposePeriod", "Period")
        if not re.fullmatch(r"\d{4}", code) or not name:
            continue
        ds = roc_dates(period)
        if len(ds) < 2:
            continue
        nth = pick(r, "NumberOfAnnouncement", "DispositionCount", "Times")
        out.append({"code": code, "name": name, "s": min(ds), "e": max(ds),
                    "nth": nth, "mkt": market})
    return out


def disp_events(p, today):
    """一個處置期間產生「處置開始」「處置結束」兩個事件。"""
    md = lambda iso: f"{int(iso[5:7])}/{int(iso[8:10])}"
    src = "證交所" if p["mkt"] == "twse" else "櫃買中心"
    url = TWSE_DISP if p["mkt"] == "twse" else TPEX_DISP
    note = f"{src}處置公告（資料整理於 {md(today)}）；處置期間 {md(p['s'])}–{md(p['e'])}"
    if len(p["dr"]) > 1:
        note += "；公告 " + str(len(p["dr"])) + " 筆：" + "、".join(
            f"{md(a)}–{md(b)}" for a, b in p["dr"]) + "，合併為連續處置"
    elif p.get("nth"):
        nth = p["nth"]
        note += "；" + (f"第{nth}次處置" if nth.isdigit() else nth)
    base = {"c": "disp", "st": "o", "u": url, "a": 1, "mn": 1,
            "dp": [p["s"], p["e"]], "dr": p["dr"], "mk": p["mkt"]}
    who = f"{p['name']}（{p['code']}）"
    return [dict(base, d=p["s"], t=who + "處置開始", n=note),
            dict(base, d=p["e"], t=who + "處置結束", n=note + "；此日為最後處置日")]


def merge_disp(old_disp, fetched, today):
    """把新公告併進既有的處置期間。已過去的保留；同一檔連續或重疊的公告合併成一段。"""
    periods = {}   # (code, start) -> 舊事件組成的期間
    for e in old_disp:
        m = re.search(r"（(\d{4})）處置(開始|結束)$", e["t"])
        if not m or "dp" not in e:
            continue
        k = (m.group(1), e["dp"][0])
        p = periods.setdefault(k, {"code": m.group(1), "name": e["t"][:m.start()],
                                   "s": e["dp"][0], "e": e["dp"][1],
                                   "dr": e.get("dr") or [e["dp"]], "mkt": e.get("mk", ""),
                                   "evs": [], "changed": False})
        p["evs"].append(e)
    day = timedelta(days=1)
    for f in sorted(fetched, key=lambda x: x["s"]):
        hit = None
        for p in periods.values():
            if p["code"] != f["code"]:
                continue
            ps, pe = (datetime.strptime(x, "%Y-%m-%d") for x in (p["s"], p["e"]))
            fs, fe = (datetime.strptime(x, "%Y-%m-%d") for x in (f["s"], f["e"]))
            # 重疊，或前一段結束後 4 天內（含週末）接著開始，就視為連續
            if fs <= pe + 4 * day and fe >= ps - 4 * day:
                hit = p
                break
        if hit is None:
            periods[(f["code"], f["s"])] = dict(f, dr=[[f["s"], f["e"]]], evs=[], changed=True)
            continue
        if hit["s"] <= f["s"] and f["e"] <= hit["e"]:
            continue   # 已涵蓋在既有期間內，沒有新資訊
        hit["dr"] = sorted(hit["dr"] + [[f["s"], f["e"]]])
        hit["s"], hit["e"] = min(hit["s"], f["s"]), max(hit["e"], f["e"])
        hit["mkt"] = hit["mkt"] or f["mkt"]
        hit["changed"] = True
    out, n_new = [], 0
    for p in periods.values():
        if p["changed"]:
            n_new += 1
            out += disp_events(p, today)
        else:
            out += p["evs"]
    return out, n_new


def fetch_disp(today, old_disp, problems):
    fetched, seen = [], {}
    for mkt, url in (("twse", TWSE_DISP), ("tpex", TPEX_DISP)):
        try:
            rows = json.loads(get(url))
            if not isinstance(rows, list):
                raise ValueError("回傳不是資料列")
            got = parse_disp(rows, mkt)
            if rows and not got:
                print(f"{mkt} 欄位範例：{list(rows[0].keys())}")
            print(f"{mkt} 處置公告：{len(rows)} 筆，個股 {len(got)} 筆")
            for g in got:
                seen.setdefault(g["code"], set()).add(mkt)
            fetched += got
        except Exception as e:
            problems.append(f"{mkt} 處置公告失敗：{e}（沿用上次資料）")
    # 同一代號同時出現在上市與上櫃，資料有疑義，先不收
    both = {c for c, s in seen.items() if len(s) > 1}
    for c in sorted(both):
        problems.append(f"處置股 {c} 同時出現在證交所與櫃買中心，先不收")
    fetched = [f for f in fetched if f["code"] not in both]
    merged, n = merge_disp(old_disp, fetched, today)
    print(f"處置股：新增或延長 {n} 段，合計 {len(merged)} 個事件")
    return merged


def load_json(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def main():
    now = datetime.now(TZ)
    today = now.strftime("%Y-%m-%d")
    manual = load_json(DATA / "events_manual.json", [])
    old = load_json(DATA / "events.json", {"events": []}).get("events", [])
    old_auto = [e for e in old if e.get("a")]
    problems = []

    # Yahoo
    tw = None
    try:
        tw = parse_yahoo(get(YAHOO_URL))
        if len(tw) < 3:
            raise ValueError(f"只解析到 {len(tw)} 筆，疑似頁面改版")
        print(f"Yahoo 法說會：{len(tw)} 筆")
    except Exception as e:
        problems.append(f"Yahoo 法說會失敗：{e}")
        tw = [e for e in old_auto if e["c"] == "tw"]

    # 股東會：Yahoo 為主（較完整），玩股網能連上時用來補「臨時／常會」「改選董監事」
    agm = None
    wg = None
    try:
        rows = json.loads(get(WG_API, referer=WG_PAGE))
        if not isinstance(rows, list) or not rows:
            raise ValueError("回傳不是資料列")
        wg = parse_wantgoo(rows, today)
        print(f"玩股網股東會：{len(wg)} 筆（今天起）")
    except Exception as e:
        print(f"玩股網連不上（{e}），只用 Yahoo 的股東會資料")
    try:
        agm = parse_yahoo_agm(get(YAHOO_AGM_URL), today)
        if not agm:
            raise ValueError("沒有解析到任何一筆，疑似頁面改版")
        if wg:
            agm = enrich_with_wantgoo(agm, wg)
        print(f"Yahoo 股東會：{len(agm)} 筆")
    except Exception as e:
        problems.append(f"Yahoo 股東會失敗：{e}")
        if wg:
            agm = wg
        else:
            problems.append("玩股網也失敗，股東會沿用上次資料")
            agm = [x for x in old_auto if x["c"] == "agm"]

    # 手動資料裡已有的同公司同日期事件（例如台積電）不重複加入
    def key(e):
        m = re.search(r"（(\d{4,6}[A-Z]?)）", e["t"])
        return (m.group(1) if m else e["t"], e["d"], e["c"])
    have = {key(e) for e in manual}
    # 處置股：沿用舊的（含已過去的）再併入今天的公告；失敗只警告，不讓流程失敗
    disp_problems = []
    disp = fetch_disp(today, [e for e in old_auto if e["c"] == "disp"], disp_problems)

    auto = [e for e in tw + agm + disp if key(e) not in have]

    events = manual + auto
    out = {"updated": now.strftime("%Y/%m/%d %H:%M"), "events": events}
    DATA.mkdir(exist_ok=True)
    (DATA / "events.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"合計 {len(events)} 筆（手動 {len(manual)}＋自動 {len(auto)}）")
    for p in problems + disp_problems:
        print("::warning::" + p)
    # 法說會與股東會兩邊都抓不到，才讓流程顯示失敗，方便你在 GitHub 看到
    if len(problems) >= 2:
        sys.exit(1)


if __name__ == "__main__":
    main()
