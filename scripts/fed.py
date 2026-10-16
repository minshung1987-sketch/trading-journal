"""聯準會官網行事曆 → 自動事件（a:1）。由 update.py 每天呼叫。

來源：https://www.federalreserve.gov/newsevents/YYYY-month.htm（本月起共 3 個月）
收：Speeches（演說、座談）、Testimony（國會作證）、Other（假日除外）。
不收：FOMC、褐皮書、統計發布（這些已在手動資料裡）。
官網時間是美東時間，換算成台灣時間後以台灣日期為準。
手動資料裡同一天已有同一位官員的央行事件（例如 IMF 年會座談）就不重複加入。
"""
import html
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")
TW = ZoneInfo("Asia/Taipei")
MONTHS = ["january", "february", "march", "april", "may", "june", "july",
          "august", "september", "october", "november", "december"]
PAGE = "https://www.federalreserve.gov/newsevents/{y}-{m}.htm"
SKIP_SECTIONS = ("FOMC", "Beige", "Statistical")

ROLE = [("Vice Chair for Supervision", "聯準會監理副主席"), ("Vice Chair", "聯準會副主席"),
        ("Chairman", "聯準會主席"), ("Chair", "聯準會主席"), ("Governor", "聯準會理事")]
NAME = {"Warsh": "沃什", "Powell": "鮑爾", "Jefferson": "傑佛遜", "Bowman": "鮑曼",
        "Waller": "沃勒", "Barr": "巴爾", "Cook": "庫克", "Miran": "米蘭", "Kugler": "庫格勒"}
KIND = {"Speech": "演說", "Discussion": "座談", "Testimony": "國會作證",
        "Remarks": "致詞", "Panel": "座談", "Fireside Chat": "爐邊對談"}


def _text(s):
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s))).strip()


def parse_month(page, year, month, url):
    """回傳這個月份頁面上的事件（台灣日期）。"""
    out = []
    parts = re.split(r'<h4 class="col-md-12">', page)[1:]
    for part in parts:
        section = _text(part.split("</h4>", 1)[0])
        if section.startswith(SKIP_SECTIONS):
            continue
        for body in part.split('class="panel-body"')[1:]:
            cols = re.findall(r'<div class="col-xs-(\d+)">(.*?)</div>', body, re.S)
            if len(cols) < 3:
                continue
            tm = _text(cols[0][1])
            mid = cols[1][1]
            day = _text(cols[2][1])
            if not day.isdigit():
                continue
            ps = [_text(p) for p in re.findall(r"<p[^>]*>(.*?)</p>", mid, re.S)]
            ps = [p for p in ps if p and p != "Watch Live"]
            if not ps:
                continue
            head = ps[0]
            m = re.match(r"(.+?)\s+-+\s+(.+)", head)
            kind, who = (m.group(1), m.group(2)) if m else ("", head)
            if kind == "Holiday":
                continue
            tm_ = re.search(r'calendar__title[^>]*>(.*?)</p>', mid, re.S)
            topic = _text(tm_.group(1)) if tm_ else ""
            rest = [p for p in ps[1:] if p != topic]
            where = rest[0] if rest else ""
            out.append(_event(year, month, int(day), tm, kind, who, topic, where, section, url))
    return out


def _event(y, mo, d, tm, kind, who, topic, where, section, url):
    et_day = date(y, mo, d)
    t = re.match(r"(\d{1,2}):(\d{2})\s*([ap])\.?m\.?", tm, re.I)
    tw_day = et_day
    tm_str = ""
    if t:
        h = int(t.group(1)) % 12 + (12 if t.group(3).lower() == "p" else 0)
        et_dt = datetime(y, mo, d, h, int(t.group(2)), tzinfo=ET)
        tw_dt = et_dt.astimezone(TW)
        tw_day = tw_dt.date()
        md = lambda x: f"{x.month}/{x.day}"
        tm_str = (f"美東 {md(et_dt)} {et_dt:%H:%M}，台灣 {md(tw_dt)} {tw_dt:%H:%M}"
                  if tw_day != et_day else f"美東 {et_dt:%H:%M}，台灣 {tw_dt:%H:%M}")

    role = next((zh for en, zh in ROLE if who.startswith(en + " ")), "")
    last = who.split()[-1] if who else ""
    zh_name = NAME.get(last, last)
    kind_zh = KIND.get(kind, kind)
    if role:
        title = f"{role}{zh_name}{kind_zh}：{topic}" if topic else f"{role}{zh_name}{kind_zh}"
    else:
        title = f"聯準會{kind_zh or '活動'}：{topic or who}"
    ev = {"d": tw_day.isoformat(), "c": "cb", "t": title, "st": "o", "u": url, "a": 1}
    if tm_str:
        ev["tm"] = tm_str
    if where:
        ev["pl"] = re.sub(r"^(At|Before) (the |an? )?", "", where)
    note = "聯準會官網行事曆（自動抓取）"
    if role and topic:
        note += f"；{who}"
    ev["n"] = note
    # 主席與國會作證是重點，其餘理事演說列為次要
    if not (role == "聯準會主席" or kind == "Testimony"):
        ev["mn"] = 1
    ev["_who"] = zh_name
    return ev


def months_ahead(today, n=3):
    y, m = today.year, today.month
    for _ in range(n):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


def fetch_fed(get, today_iso, old_fed, manual, problems):
    """抓 3 個月份；抓失敗的月份沿用舊資料，更早的月份保留不動。"""
    today = date.fromisoformat(today_iso)
    fetched, done = [], set()
    for y, m in months_ahead(today):
        url = PAGE.format(y=y, m=MONTHS[m - 1])
        try:
            evs = parse_month(get(url), y, m, url)
            fetched += evs
            done.add(url)
            print(f"聯準會行事曆 {y}-{m:02d}：{len(evs)} 筆")
        except Exception as e:
            problems.append(f"聯準會行事曆 {y}-{m:02d} 失敗：{e}")
    keep = [e for e in old_fed if e.get("u") not in done]

    # 手動資料同一天（台灣日期 ±1）已有同一位官員的央行事件 → 不重複
    def dup(e):
        who = e.pop("_who", "")
        if not who:
            return False
        d = date.fromisoformat(e["d"])
        for x in manual:
            if x.get("c") == "cb" and who in x.get("t", ""):
                if abs((date.fromisoformat(x["d"]) - d).days) <= 1:
                    return True
        return False

    fresh = [e for e in fetched if not dup(e)]
    return sorted(keep + fresh, key=lambda e: (e["d"], e.get("tm", ""), e["t"]))
