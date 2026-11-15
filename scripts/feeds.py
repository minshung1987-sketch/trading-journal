"""機器人與 AI 的會議日期、公司發布候選清單。由 update.py 每天呼叫（GitHub Actions，不用 Claude）。

1. 學術與產業會議（自動上行事曆，a:1，類別 tech）
   資料源：開源的 ccf-deadlines（https://github.com/ccfddl/ccf-deadlines），社群維護的會議日期。
   只收 2026 年以後、日期可解析的場次；手動資料裡已有同一場（名稱相同、日期差 7 天內）就不重複。
   這是第二手資料，備註會寫明；官方日期以各會議官網為準，我每週例行更新時會抽查。
2. 公司發布「候選清單」（不上行事曆，只存 data/radar.json，由每週例行更新人工確認後才加入）
   資料源：NVIDIA、Google DeepMind、Google AI、OpenAI 的官方部落格 RSS。
   只用標題關鍵字粗篩，雜訊多，所以不自動上線。
只用 Python 標準函式庫。
"""
import gzip
import json
import re
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

RAW = "https://raw.githubusercontent.com/ccfddl/ccf-deadlines/main/conference/{}.yml"
# 檔案路徑 → (中文說明, 是否重要；不重要的標為次要)
CONFS = {
    "AI/corl": ("機器人學習研討會", True), "AI/icra": ("IEEE 機器人與自動化國際會議", True),
    "AI/iros": ("IEEE／RSJ 智慧型機器人與系統國際會議", False), "AI/rss": ("機器人：科學與系統會議", False),
    "AI/nips": ("神經資訊處理系統大會", True), "AI/icml": ("國際機器學習大會", True),
    "AI/iclr": ("國際學習表徵會議", False), "AI/cvpr": ("電腦視覺與圖形辨識會議", True),
    "AI/iccv": ("國際電腦視覺大會", False), "AI/eccv": ("歐洲電腦視覺大會", False),
    "AI/aaai": ("AAAI 人工智慧會議", False), "AI/ijcai": ("國際人工智慧聯合會議", False),
    "AI/acl": ("計算語言學學會年會", False), "AI/emnlp": ("自然語言處理經驗方法會議", False),
    "DS/sc": ("超級電腦大會", True), "DS/hotchips": ("Hot Chips 高效能晶片研討會", True),
    "DS/isca": ("國際電腦架構研討會", False), "DS/micro": ("國際微架構研討會", False),
    "DS/hpca": ("高效能電腦架構研討會", False), "DS/asplos": ("架構與程式語言作業系統支援會議", False),
    "DS/dac": ("設計自動化會議", True), "DS/iccad": ("國際電腦輔助設計會議", False),
}
ACR = {"AI/nips": "NeurIPS", "DS/hotchips": "Hot Chips"}
MONTHS = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}
MONTHS.update({k[:3]: v for k, v in list(MONTHS.items())})
MONTHS["sept"] = 9


def parse_date(text):
    """'November 9-11, 2026'、'June 30-July 3, 2026'、'December 8-10 (Sydney), December 9-11 (Atlanta), 2026' → (起, 迄) ISO；解析不了回 None。
    多地點同時舉辦的取最早開始到最晚結束。"""
    t = re.sub(r"\([^)]*\)", "", text.replace("–", "-").replace("—", "-"))
    ym = re.search(r"(20\d\d)\s*$", t.strip()) or re.search(r"(20\d\d)", t)
    if not ym:
        return None
    y = int(ym.group(1))
    spans = []
    for m in re.finditer(r"([A-Za-z]{3,9})\.?\s+(\d{1,2})\s*(?:-\s*(?:([A-Za-z]{3,9})\.?\s+)?(\d{1,2}))?", t):
        m1, d1, m2, d2 = m.groups()
        mo1 = MONTHS.get(m1.lower())
        mo2 = MONTHS.get((m2 or m1).lower())
        if not mo1 or not mo2:
            continue
        spans.append((f"{y}-{mo1:02d}-{int(d1):02d}", f"{y + (mo2 < mo1)}-{mo2:02d}-{int(d2 or d1):02d}"))
    if not spans:
        return None
    a, b = min(a for a, _ in spans), max(b for _, b in spans)
    return (a, b) if (datetime.strptime(b, "%Y-%m-%d") - datetime.strptime(a, "%Y-%m-%d")).days <= 21 else None


def conf_blocks(yml):
    """ccf-deadlines 的 yml 很規則：每個場次是 '- year: …' 開頭、含 link / date / place。"""
    title = (re.search(r"^- title:\s*(.+)$", yml, re.M) or [None, ""])[1].strip()
    out = []
    for blk in re.split(r"\n\s*- year:\s*", yml)[1:]:
        year = re.match(r"(\d{4})", blk)
        link = re.search(r"link:\s*(\S+)", blk)
        date = re.search(r"^\s*date:\s*(.+)$", blk, re.M)
        place = re.search(r"^\s*place:\s*(.+)$", blk, re.M)
        out.append({"year": int(year.group(1)) if year else 0, "link": link.group(1) if link else "",
                    "date": date.group(1).strip().strip("'\"") if date else "", "place": place.group(1).strip().strip("'\"") if place else ""})
    return title, out


def conf_events(get, manual, problems):
    out = []
    for path, (zh, major) in CONFS.items():
        try:
            title, blocks = conf_blocks(get(RAW.format(path)))
        except Exception as e:
            problems.append(f"會議資料 {path} 讀取失敗：{e}")
            continue
        for b in blocks:
            if b["year"] < 2026:
                continue
            rng = parse_date(b["date"])
            if not rng:
                continue
            a, z = rng
            acr = ACR.get(path) or (title.split()[0] if title else path.split("/")[-1].upper())
            # 手動資料已有同一場就略過
            da = datetime.strptime(a, "%Y-%m-%d")
            dup = False
            for e in manual:
                if e.get("c") in ("tech", "ind") and acr.lower() in e.get("t", "").lower():
                    try:
                        if abs((datetime.strptime(e["d"], "%Y-%m-%d") - da).days) <= 7:
                            dup = True
                            break
                    except ValueError:
                        pass
            if dup:
                continue
            ev = {"d": a, "c": "tech", "t": f"{acr} {b['year']}（{zh}）", "st": "o", "a": 1,
                  "u": b["link"] or "https://github.com/ccfddl/ccf-deadlines",
                  "n": "學術會議日期取自開源資料庫 ccf-deadlines（社群維護，第二手資料），官方日期請以會議官網為準"}
            if z != a:
                ev["e"] = z
            if b["place"]:
                ev["pl"] = b["place"]
            if not major:
                ev["mn"] = 1
            out.append(ev)
    return sorted(out, key=lambda e: e["d"])


# ---------- 公司發布候選 ----------
FEEDS = {
    "NVIDIA": "https://blogs.nvidia.com/feed/",
    "Google DeepMind": "https://deepmind.google/blog/rss.xml",
    "Google AI": "https://blog.google/technology/ai/rss/",
    "OpenAI": "https://openai.com/news/rss.xml",
}
HIT = re.compile(r"\b(introduc\w*|launch\w*|announc\w*|unveil\w*|releas\w*|now available|debut\w*|reveal\w*)\b|"
                 r"\b(Gemini|GPT|Claude|GR00T|Cosmos|Isaac|Blackwell|Rubin|Vera|Jetson|Thor|Genie|Veo|Robotics|humanoid)\b", re.I)


def fetch_feed(url):
    """部分網站（例如 DeepMind）不論有沒有要求都回傳 gzip，遇到就解壓縮。"""
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; investor-calendar-bot/1.0)",
                                               "Accept-Encoding": "gzip"})
    with urllib.request.urlopen(req, timeout=40) as r:
        raw = r.read()
    if raw[:2] == b"\x1f\x8b":
        raw = gzip.decompress(raw)
    return raw.decode("utf-8", "replace")


def parse_feed(xml, source):
    root = ET.fromstring(xml.lstrip("\ufeff \r\n\t").encode("utf-8"))
    items = []
    for it in list(root.iter("item")) + list(root.iter("{http://www.w3.org/2005/Atom}entry")):
        def g(tag):
            el = it.find(tag)
            if el is None:
                el = it.find("{http://www.w3.org/2005/Atom}" + tag)
            return el
        t = g("title")
        l = g("link")
        d = next((x for x in (g("pubDate"), g("published"), g("updated")) if x is not None), None)
        if t is None or d is None:
            continue
        link = (l.text or l.get("href") or "").strip() if l is not None else ""
        try:
            dt = parsedate_to_datetime(d.text)
        except Exception:
            try:
                dt = datetime.fromisoformat(d.text.replace("Z", "+00:00"))
            except Exception:
                continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        items.append({"src": source, "title": re.sub(r"\s+", " ", (t.text or "")).strip(), "link": link,
                      "d": dt.astimezone(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")})
    return items


def radar(get, today, problems, path):
    try:
        old = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        old = {"items": []}
    seen = {i["link"]: i for i in old.get("items", [])}
    recent = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=21)).strftime("%Y-%m-%d")
    for src, url in FEEDS.items():
        try:
            for i in parse_feed(fetch_feed(url), src):
                if HIT.search(i["title"]) and i["link"] not in seen and i["d"] >= recent:
                    i["first_seen"] = today
                    seen[i["link"]] = i
        except Exception as e:
            problems.append(f"發布候選 {src} 讀取失敗：{e}")
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=60)).strftime("%Y-%m-%d")
    items = sorted((i for i in seen.values() if i["d"] >= cutoff), key=lambda i: (i["d"], i["src"]), reverse=True)
    path.write_text(json.dumps({"updated": today, "note": "公司官方部落格 RSS 的標題粗篩，只是候選，確認過才加入行事曆", "items": items},
                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return len(items)
