"""依固定規則推算的「資金流／制度性」交易日程 → 自動事件（a:1，類別 mkt）。由 update.py 每天呼叫。

這些事件不是某一則公告，而是每年、每季固定發生的制度性資金流動（作帳、節稅、庫藏股靜默期、
申報截止、指數審核等）。日期依規則推算；遇到週末或休市日自動調整（休市日讀 events_manual.json
裡的「台股休市／美股休市」事件，證交所公布 2027 年休市日後會自動校正）。
每條規則都附上說明規則的來源網址。
"""
from datetime import date, timedelta

START = date(2026, 7, 1)    # 從這天開始產生（之前的不補）
AHEAD = 400                 # 往後產生多少天

U_WINDOW = "https://www.stockfeel.com.tw/?p=126208"
U_PENSION = "https://www.cnbc.com/2020/06/23/theres-a-wave-of-selling-estimated-to-be-in-the-billions-thats-about-to-hit-the-stock-market.html"
U_BUYBACK = "https://www.cnbc.com/2018/10/12/companies-buying-their-own-shares-could-fuel-the-next-market-rally.html"
U_13F = "https://www.ecfr.gov/current/title-17/section-240.13f-1"
U_CTAX = "https://www.irs.gov/publications/p509"
U_TWFS = "https://law.moj.gov.tw/LawClass/LawSingle.aspx?pcode=G0400001&flno=36"
U_HF = "https://www.hedgeco.net/news/?p=9183"
U_MF = "https://www.sec.gov/Archives/edgar/data/0000825063/000165558926000598/c485bpos.htm"
U_TAXLOSS = "https://www.luxalgo.com/library/concept/tax-loss-selling-season/"
U_TW50 = "https://www.yuantaetfs.com/product/detail/0051/"
U_MSCI = "https://news.cnyes.com/news/id/6481342"

SEARCH_NOTE = "（市場慣例、非法規強制；說明來自財經媒體報導）"
OFFICIAL = "（依官方規定：{}）"


def holidays(manual, market):
    """market: "台股" 或 "美股"。"""
    out = set()
    for e in manual:
        if e.get("c") == "mkt" and e.get("t", "").startswith(market + "休市"):
            d = date.fromisoformat(e["d"])
            end = date.fromisoformat(e["e"]) if e.get("e") else d
            while d <= end:
                out.add(d)
                d += timedelta(days=1)
    for y in range(2026, 2029):            # 兩邊都固定休元旦
        out.add(date(y, 1, 1))
    return out


def trading(d, hol):
    return d.weekday() < 5 and d not in hol


def next_td(d, hol):
    while not trading(d, hol):
        d += timedelta(days=1)
    return d


def prev_td(d, hol):
    while not trading(d, hol):
        d -= timedelta(days=1)
    return d


def month_end(y, m):
    return (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))


def third_friday(y, m):
    d = date(y, m, 15)
    return d + timedelta(days=(4 - d.weekday()) % 7)


def md(d):
    return f"{d.month}/{d.day}"


def ev(d, t, n, u, st="o", e=None, **kw):
    x = {"d": d.isoformat(), "c": "mkt", "t": t, "st": st, "u": u, "n": n, "a": 1}
    if e and e != d:
        x["e"] = e.isoformat()
    x.update(kw)
    return x


def build(manual, today_iso):
    today = date.fromisoformat(today_iso)
    tw, us = holidays(manual, "台股"), holidays(manual, "美股")
    last = today + timedelta(days=AHEAD)
    out = []

    for y in range(START.year, last.year + 2):
        # ---- 每季 ----
        for q, m in enumerate((3, 6, 9, 12), 1):
            qe = month_end(y, m)
            tw_last, us_last = prev_td(qe, tw), prev_td(qe, us)
            label = {6: "半年底", 12: "年底"}.get(m, "季底")
            weight = {12: "一年中最重要的一次", 6: "半年績效結算，重要性僅次於年底"}.get(m, "")
            out.append(ev(next_td(date(y, m, 16), tw), f"{label}作帳期（投信、基金績效結算）",
                          f"季底前約兩週，投信常集中買進、拉抬持股（尤其中小型股、尾盤）讓基金淨值好看；{weight + '；' if weight else ''}"
                          f"作帳是統計傾向，不保證發生。最後交易日 {md(tw_last)}，結束後常見獲利了結。{SEARCH_NOTE}",
                          U_WINDOW, e=tw_last))
            out.append(ev(prev_td(us_last - timedelta(days=1), us), "美國退休基金季底再平衡",
                          "股票漲多、債券落後時，大型退休基金會在季底最後一兩個交易日賣股買債調回目標比例（反之則買股）；"
                          f"規模依當季股債表現差異而定，常見數百億美元。美股季底最後交易日 {md(us_last)}。{SEARCH_NOTE}",
                          U_PENSION, e=us_last))
            nq = date(y + (m == 12), m % 12 + 1, 1)
            out.append(ev(next_td(nq, tw), "新季首個交易日（季初調節）",
                          f"上一季作帳結束、新一季開始：作帳股常遭獲利了結，資金重新布局；"
                          f"{'外資與法人年初重新配置，' if m == 12 else ''}留意前一季強勢股的回檔。{SEARCH_NOTE}",
                          U_WINDOW))
            # 庫藏股靜默期：約季底前兩週開始，到財報公布後 1–2 天；以季後約 4 週（財報高峰過後）為大致結束
            out.append(ev(next_td(date(y, m, 16), us), "美股庫藏股靜默期開始（約）",
                          "多數美國公司在季底前約兩週至財報公布後 1–2 天暫停自行買回股票，買盤支撐變少；"
                          "各公司規定不同，有 10b5-1 計畫者仍可照常買回，並非法規強制。"
                          f"大型公司多在季後 3–5 週公布財報後陸續恢復。{SEARCH_NOTE}",
                          U_BUYBACK, st="e"))
            out.append(ev(next_td(qe + timedelta(days=30), us), "美股庫藏股靜默期大致結束（財報高峰過後）",
                          "多數大型公司已公布財報，庫藏股買盤陸續恢復；實際依各公司規定。" + SEARCH_NOTE,
                          U_BUYBACK, st="e"))
            # 13F：季後 45 天
            out.append(ev(next_td(qe + timedelta(days=45), us), f"13F 持股申報截止（{y} 年第 {q} 季）",
                          "管理資產逾 1 億美元的機構須在季後 45 天內申報美股持股，巴菲特（波克夏）、避險基金等的增減持名單在截止前後陸續曝光，常引發話題股波動；遇假日順延。"
                          + OFFICIAL.format("美國聯邦法規 17 CFR 240.13f-1"), U_13F))
            # 美國企業季度預繳稅（4、6、9、12 月 15 日）
            tm = {1: 4, 2: 6, 3: 9, 4: 12}[q]
            out.append(ev(next_td(date(y, tm, 15), us), "美國企業季度預繳稅日",
                          "日曆年度的美國企業在 4、6、9、12 月 15 日預繳所得稅，資金從銀行體系流入財政部帳戶，"
                          "短期資金面（附買回利率）可能偏緊；遇假日順延。" + OFFICIAL.format("美國國稅局 Publication 509 稅務日曆"), U_CTAX))
            # 避險基金贖回通知（季後一個半月：2、5、8、11 月 15 日前後；年底最重要）
            hm = {1: 5, 2: 8, 3: 11, 4: 2}[q]
            hy = y + (q == 4)
            out.append(ev(prev_td(date(hy, hm, 15), us),
                          "避險基金年底贖回通知截止（常見 11/15）" if hm == 11 else "避險基金季度贖回通知截止（常見）",
                          "許多避險基金要求季末贖回須提前約 45 天通知，截止前後基金可能先行減碼、賣出流動性較好的持股；"
                          "各基金規定不同。" + SEARCH_NOTE, U_HF, st="e"))
            # 台灣 50／中型 100（含高股息 0056 於 6、12 月）季度審核：第三個星期五收盤後生效
            eff = prev_td(third_friday(y, m), tw)
            extra = "、0056（臺灣高股息）" if m in (6, 12) else ""
            out.append(ev(eff, f"台灣50／中型100{'／高股息' if extra else ''}指數 {m} 月審核換股",
                          f"證交所與富時每季審核，3、6、9、12 月第三個星期五後的下一個交易日生效；0050、006208、0051{extra} 等 ETF 在當天收盤前後調整持股，"
                          "被納入或剔除的個股尾盤常有大量被動買賣；審核結果約於兩週前公布，以證交所公告為準。"
                          "日期依元大投信 0051 產品頁所載規則推算；高股息指數（0056）6、12 月同步審核為媒體報導。",
                          U_TW50, st="e"))

        # ---- 每年 ----
        out.append(ev(prev_td(date(y, 10, 31), us), "美國共同基金會計年度結算（多數基金 10/31）",
                      "許多美國共同基金以 10/31 為會計年度結束日（配合消費稅分配規定），9～10 月常見基金為調整配息而實現損益、"
                      "賣出虧損部位；11～12 月再輪到散戶節稅賣壓。" + SEARCH_NOTE, U_MF))
        out.append(ev(next_td(date(y, 12, 1), us), "美股年底節稅賣壓期開始（至年底）",
                      "投資人在 12 月賣出虧損部位抵稅，當年跌深的股票承壓；1 月初常見回補（「一月效應」）。" + SEARCH_NOTE,
                      U_TAXLOSS))
        # 00878（MSCI 指數）：5 月底、11 月底生效
        for mm in (5, 11):
            out.append(ev(prev_td(month_end(y, mm), tw), f"00878 成分股調整生效（{mm} 月半年度審核）",
                          "國泰永續高股息（00878）追蹤 MSCI 指數，每年 5 月底、11 月底隨 MSCI 審核生效；規模龐大，"
                          "被納入或剔除的個股在生效日尾盤常有大量買賣。名單約在生效前兩週公布。" + SEARCH_NOTE,
                          U_MSCI, st="e"))
        # 台股財報公告截止（一般上市櫃公司；金融業與 F 股另有期限）
        for mm, dd, name, yy in ((3, 31, f"{y - 1} 年度財報", y), (5, 15, "第一季財報", y),
                                 (8, 14, "第二季財報", y), (11, 14, "第三季財報", y)):
            out.append(ev(next_td(date(yy, mm, dd), tw), f"台股{name}公告截止",
                          "一般上市櫃公司的法定公告期限（金融保險業、F 股與部分大型公司期限不同；遇假日順延）。"
                          "截止前有不少公司密集公布，逾期未公布可能被打入全額交割或停止交易。" + OFFICIAL.format("證券交易法第 36 條：年報 3 個月內、季報 45 日內"), U_TWFS))

    return sorted((x for x in out if START <= date.fromisoformat(x["d"]) <= last),
                  key=lambda x: (x["d"], x["t"]))
