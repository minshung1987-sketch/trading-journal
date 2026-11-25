#!/usr/bin/env python3
"""只更新事件雷達候選清單 data/radar_events.json（每 6 小時由 radar.yml 執行）。"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from feeds import radar_news  # noqa: E402

DATA = Path(__file__).resolve().parent.parent / "data"
today = datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
problems = []
n = radar_news(today, problems, DATA / "radar_events.json")
print(f"事件雷達候選 {n} 則")
for p in problems:
    print(f"::warning::{p}")
