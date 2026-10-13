#!/usr/bin/env python3
"""人工更新 data/events_manual.json 後執行：只重組 data/events.json，不連網抓資料。

events.json = events_manual.json ＋ 目前 events.json 裡的自動事件（a:1），
並加上「新增／變動」標記（見 annotate.py）。

用法：python3 scripts/rebuild.py
"""
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from annotate import annotate  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
TZ = timezone(timedelta(hours=8))


def main():
    now = datetime.now(TZ)
    manual = json.loads((DATA / "events_manual.json").read_text(encoding="utf-8"))
    old = json.loads((DATA / "events.json").read_text(encoding="utf-8")).get("events", [])
    auto = [e for e in old if e.get("a")]
    events = annotate(old, manual + auto, now.strftime("%Y-%m-%d"))
    out = {"updated": now.strftime("%Y/%m/%d %H:%M"), "events": events}
    (DATA / "events.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"合計 {len(events)} 筆（手動 {len(manual)}＋自動 {len(auto)}）")


if __name__ == "__main__":
    main()
