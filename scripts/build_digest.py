#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日精选生成器 v2（全文版）
- 读取 feeds.yaml 里的 RSS 源
- 抓取、去重、按时间过滤
- 用 trafilatura 抓取文章全文（失败则降级为 RSS 简介）
- 用 DeepSeek 对全文生成 AI 总结，附在文章最后一段
- 生成 daily/YYYY-MM-DD.md（全文用 <details> 折叠收纳）并更新 README
"""
import html
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

import feedparser
import requests
import trafilatura
import yaml

BEIJING = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAILY_DIR = os.path.join(ROOT, "daily")
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
}
FULLTEXT_MAX = 6000  # 全文展示与总结的正文上限（字符）

# Windows 控制台默认 GBK，强制 UTF-8 输出
if sys.stdout.encoding and "utf" not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def clean(text, limit: int = 160) -> str:
    """去掉 HTML 标签、转义实体、压缩空白、截断。"""
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"Announce Type:[^\n]*", "", text, flags=re.I)
    text = re.sub(r"^\s*Abstract:\s*", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def fetch_feed(url: str, timeout: int = 20) -> feedparser.FeedParserDict:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def fetch_fulltext(url: str):
    """抓取网页正文；失败或太短返回 None。"""
    try:
        resp = requests.get(url, headers=HEADERS, timeout=20)
        if resp.status_code != 200:
            return None
        text = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
        if text:
            text = text.strip()
            if len(text) >= 200:  # 太短视为抓取失败（可能是登录墙/JS 页）
                return text[:FULLTEXT_MAX]
    except Exception:
        pass
    return None


def ai_summary(title: str, content: str, api_key: str) -> str:
    """对全文生成一段中文总结；失败或没 Key 返回空串。"""
    if not api_key or not content:
        return ""
    try:
        resp = requests.post(
            "https://api.deepseek.com/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "deepseek-chat",
                "messages": [
                    {
                        "role": "system",
                        "content": "你是资深科技编辑。阅读下面这篇文章，用一段 100~150 字的中文总结其核心内容与亮点。直接输出总结正文，不要任何前缀或引号。",
                    },
                    {
                        "role": "user",
                        "content": f"标题：{title}\n\n正文：\n{content}",
                    },
                ],
                "max_tokens": 300,
                "temperature": 0.3,
            },
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        print(f"  (AI 总结失败: {exc})")
        return ""


def process_item(item: dict, api_key: str) -> dict:
    """抓全文 → 生成 AI 总结。"""
    fulltext = fetch_fulltext(item["link"])
    item["fulltext"] = fulltext
    item["summary"] = ai_summary(item["title"], fulltext, api_key) if fulltext else ""
    return item


def main() -> int:
    with open(os.path.join(ROOT, "feeds.yaml"), encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    settings = cfg.get("settings", {})
    max_age_days = settings.get("max_age_days", 3)
    max_total = settings.get("max_total", 30)
    exclude_keywords = [k.lower() for k in settings.get("exclude_keywords", [])]
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")

    now = datetime.now(BEIJING)
    cutoff = now - timedelta(days=max_age_days)

    items = []
    seen_links = set()
    errors = []

    # 1) 抓 RSS
    for feed in cfg.get("feeds", []):
        name = feed.get("name", "未命名")
        url = feed.get("url", "")
        limit = feed.get("max_items", 5)
        print(f"▶ 抓取: {name}")
        try:
            parsed = fetch_feed(url)
        except Exception as exc:
            errors.append(f"{name} ({exc})")
            print(f"  ✗ 失败: {exc}")
            continue

        count = 0
        for entry in parsed.entries:
            if count >= limit:
                break
            link = entry.get("link", "")
            title = clean(entry.get("title", ""), 200)
            if not link or not title or link in seen_links:
                continue
            if any(k in title.lower() for k in exclude_keywords):
                continue

            ts = None
            for key in ("published_parsed", "updated_parsed"):
                raw = entry.get(key)
                if raw:
                    ts = datetime(*raw[:6], tzinfo=timezone.utc)
                    break
            if ts is None:
                ts = now
            if ts < cutoff:
                continue

            seen_links.add(link)
            items.append(
                {
                    "feed": name,
                    "title": title,
                    "link": link,
                    "desc": clean(entry.get("summary", ""), 120),
                    "time": ts.astimezone(BEIJING).strftime("%m-%d %H:%M"),
                }
            )
            count += 1
        time.sleep(0.3)

    items.sort(key=lambda x: x["time"], reverse=True)
    items = items[:max_total]

    # 2) 并发抓全文 + AI 总结
    print(f"▶ 抓全文 + AI 总结（{len(items)} 篇，并发 6）...")
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(process_item, it, api_key) for it in items]
        done = 0
        for fut in as_completed(futures):
            try:
                fut.result()
            except Exception as exc:
                print(f"  (处理失败: {exc})")
            done += 1
            print(f"  … {done}/{len(items)}")
    n_full = sum(1 for it in items if it["fulltext"])
    n_sum = sum(1 for it in items if it["summary"])
    print(f"✅ 全文抓取成功 {n_full}/{len(items)}，AI 总结 {n_sum} 篇")

    # 3) 生成日报
    date_str = now.strftime("%Y-%m-%d")
    lines = [
        f"# 📰 每日精选 {date_str}",
        "",
        f"> 共 {len(items)} 篇 · 生成于 {now.strftime('%H:%M')}"
        + (f" · 📄 全文 {n_full} 篇" if n_full else "")
        + (f" · ✨ AI 总结 {n_sum} 篇" if n_sum else "")
        + ("" if api_key else " · （未启用 AI）"),
    ]
    if errors:
        lines.append("")
        lines.append("> ⚠️ 以下来源本次抓取失败：" + "；".join(errors))
    lines.append("")

    by_feed = {}
    for item in items:
        by_feed.setdefault(item["feed"], []).append(item)
    for feed_name, feed_items in by_feed.items():
        lines.append(f"## {feed_name}")
        lines.append("")
        for it in feed_items:
            lines.append(f"- [{it['title']}]({it['link']}) <sub>{it['time']}</sub>")
            lines.append("")
            if it["fulltext"]:
                lines.append("<details>")
                lines.append(f"<summary>📄 展开阅读全文（{len(it['fulltext'])} 字）</summary>")
                lines.append("")
                lines.append(it["fulltext"])
                if it["summary"]:
                    lines.append("")
                    lines.append("---")
                    lines.append("")
                    lines.append(f"**🤖 AI 总结：** {it['summary']}")
                lines.append("")
                lines.append("</details>")
            else:
                lines.append("<sub>⚠️ 全文抓取失败，可点击标题回原文查看</sub>")
            lines.append("")

    os.makedirs(DAILY_DIR, exist_ok=True)
    digest_path = os.path.join(DAILY_DIR, f"{date_str}.md")
    with open(digest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ 已生成: {digest_path}")

    # 4) 更新 README
    readme_path = os.path.join(ROOT, "README.md")
    with open(readme_path, encoding="utf-8") as f:
        readme = f.read()
    marker_start = "<!-- DIGEST-LIST:START -->"
    marker_end = "<!-- DIGEST-LIST:END -->"
    recent = sorted(os.listdir(DAILY_DIR), reverse=True)[:7]
    links = "\n".join(f"- [{f[:-3]}](daily/{f})" for f in recent)
    block = f"{marker_start}\n{links}\n{marker_end}"
    if marker_start in readme and marker_end in readme:
        readme = re.sub(
            re.escape(marker_start) + r".*?" + re.escape(marker_end),
            block,
            readme,
            flags=re.S,
        )
    else:
        readme += f"\n\n{block}\n"
    with open(readme_path, "w", encoding="utf-8") as f:
        f.write(readme)

    return 0


if __name__ == "__main__":
    sys.exit(main())
