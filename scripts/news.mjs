#!/usr/bin/env node
/* 抓「相關新聞」：每小時由 GitHub Actions 執行，產生 data/news.json。
   - 搜尋字串規則與網站共用 news-keys.js（兩邊完全一致）
   - 來源：Google 新聞 RSS（台灣版＋大陸版：東方財富、華爾街見聞），依發布時間由新到舊排序
   - 範圍：結束日在 7 天內、開始日在 30 天內的事件；同一搜尋字串只查一次（例如處置開始／結束）
   - 某個查詢失敗時沿用上一次的結果，不會把網站弄空
   只用 Node 內建功能，不需要 npm install。 */
process.env.TZ = "Asia/Taipei";
import fs from "node:fs";
import vm from "node:vm";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DAY = 864e5;
const now = new Date();
const TODAY = new Date(now.getFullYear(), now.getMonth(), now.getDate());
const PER_KEY = 12;          // 每個搜尋字串保留幾則
const PAUSE_MS = 700;        // 兩次查詢之間的間隔，避免被 Google 限流

const ctx = vm.createContext({ TODAY, DAY, diffDays: (a, b) => Math.round((a - b) / DAY), Map, Set, Date, Math, String });
vm.runInContext(fs.readFileSync(path.join(ROOT, "news-keys.js"), "utf8"), ctx);
const K = vm.runInContext("({newsKey,cnKey,cnShow,newsRange,newsQ,newsQCN,RSS_TW,RSS_CN})", ctx);

const pd = s => { const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const events = JSON.parse(fs.readFileSync(path.join(ROOT, "data/events.json"), "utf8")).events;
const oldPath = path.join(ROOT, "data/news.json");
let old = { tw: {}, cn: {} };
try { old = JSON.parse(fs.readFileSync(oldPath, "utf8")); } catch {}

/* 同一搜尋字串合併所有事件的日期範圍 */
const jobs = { tw: new Map(), cn: new Map() };
const add = (side, key, a, b) => {
  const j = jobs[side].get(key);
  if (!j) jobs[side].set(key, { a, b });
  else { if (a < j.a) j.a = a; if (b > j.b) j.b = b; }
};
for (const e of events) {
  e.s = pd(e.d); e.en = e.e ? pd(e.e) : e.s;
  if (e.en < TODAY - 7 * DAY || e.s > TODAY.getTime() + 30 * DAY) continue;
  const [a, b] = K.newsRange(e);
  add("tw", K.newsKey(e), a, b);
  if (K.cnShow(e)) add("cn", K.cnKey(e), a, b);
}

const unesc = s => s.replace(/<!\[CDATA\[|\]\]>/g, "").replace(/&lt;/g, "<").replace(/&gt;/g, ">")
  .replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, "&");
const sleep = ms => new Promise(r => setTimeout(r, ms));

async function rss(q, ed) {
  const u = "https://news.google.com/rss/search?" + new URLSearchParams({ q, ...ed });
  for (let i = 0; i < 3; i++) {
    const r = await fetch(u, { headers: { "User-Agent": "Mozilla/5.0 (compatible; investor-calendar-bot/1.0)" } });
    if (r.ok) return r.text();
    if (r.status === 429 || r.status >= 500) { await sleep(20000 * (i + 1)); continue; }
    throw new Error("HTTP " + r.status);
  }
  throw new Error("重試後仍失敗");
}

function parse(xml, a, b) {
  const out = [], seen = new Set();
  for (const it of xml.split("<item>").slice(1)) {
    const g = tag => { const m = it.match(new RegExp("<" + tag + "[^>]*>([\\s\\S]*?)</" + tag + ">")); return m ? unesc(m[1]).trim() : ""; };
    const src = g("source"), link = g("link"), t = Date.parse(g("pubDate"));
    let title = g("title");
    if (src && title.endsWith(" - " + src)) title = title.slice(0, -(src.length + 3));
    if (!title || !link || isNaN(t) || t < a.getTime() || t >= b.getTime() + DAY) continue;
    if (seen.has(title)) continue;           // 同一篇被多家轉載只留最新一則
    seen.add(title);
    out.push([Math.round(t / 60000), src, title, link]);
  }
  return out.sort((x, y) => y[0] - x[0]).slice(0, PER_KEY);
}

const res = { tw: {}, cn: {} };
let ok = 0, fail = 0;
for (const side of ["tw", "cn"]) {
  for (const [key, { a, b }] of jobs[side]) {
    const q = side === "tw" ? K.newsQ(key, a, b) : K.newsQCN(key, a, b);
    try {
      res[side][key] = parse(await rss(q, side === "tw" ? K.RSS_TW : K.RSS_CN), a, b);
      ok++;
    } catch (err) {
      fail++;
      if (old[side] && old[side][key]) res[side][key] = old[side][key];
      console.log(`::warning::${side} 查詢失敗（${err.message}）：${key}`);
    }
    await sleep(PAUSE_MS);
  }
}

/* 一個搜尋字串一行，讓 git 每次只記錄有變動的行 */
const pad = n => String(n).padStart(2, "0");
const upd = `${now.getFullYear()}/${pad(now.getMonth() + 1)}/${pad(now.getDate())} ${pad(now.getHours())}:${pad(now.getMinutes())}`;
const block = o => "{\n" + Object.keys(o).sort().map(k => "  " + JSON.stringify(k) + ":" + JSON.stringify(o[k])).join(",\n") + "\n }";
fs.writeFileSync(oldPath, `{"updated":${JSON.stringify(upd)},\n "tw":${block(res.tw)},\n "cn":${block(res.cn)}\n}\n`);
console.log(`查詢 ${ok + fail} 次（成功 ${ok}、失敗 ${fail}）；台灣 ${jobs.tw.size} 組、陸媒 ${jobs.cn.size} 組`);
if (ok === 0 && fail > 0) process.exit(1);
