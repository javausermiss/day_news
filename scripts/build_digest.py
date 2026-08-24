#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日精选生成器
- 读取 feeds.yaml 里的 RSS 源
- 抓取、去重、按时间过滤
- 可选：DeepSeek AI 摘要（无 Key 时退回原文简介）
- 生成 daily/YYYY-MM-DD.md 并更新 README 里的「今日阅读」列表
"""
import html
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import feedparser
import requests
import yaml

# Windows 控制台默认 GBK，强制 UTF-8 输出，避免打印符号报错
if sys.stdout.encoding and "utf" not in sys.stdout.encoding.lower():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BEIJING = timezone(timedelta(hours=8))
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DAILY_DIR = os.path.join(ROOT, "daily")
HEADERS = {"User-Agent": "Mozilla/5.0 (daily-reads; RSS digest bot)"}


def fetch_feed(url: str, timeout: int = 20) -> feedparser.FeedParserDict:
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    return feedparser.parse(resp.content)


def clean(text, limit: int = 160) -> str:
    """去掉 HTML 标签、转义实体、压缩空白、截断。"""
    if not text:
        return ""
    text = html.unescape(str(text))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"Announce Type:[^\n]*", "", text, flags=re.I)  # 去掉 arXiv 的公告噪音
    text = re.sub(r"^\s*Abstract:\s*", "", text)  # 去掉开头的 Abstract: 前缀
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return text


def ai_summary(title: str, desc: str, api_key: str) -> str:
    """用 DeepSeek 生成一句中文摘要；失败或没 Key 则退回原文简介。"""
    if not api_key:
        return clean(desc, 120)
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
                        "content": "你是每日阅读助手。用一句不超过40字的中文概括这篇科技文章的核心内容。直接输出概括，不要任何前缀或引号。",
                    },
                    {
                        "role": "user",
                        "content": f"标题：{title}\n简介：{clean(desc, 400)}",
                    },
                ],
                "max_tokens": 100,
                "temperature": 0.3,
            },
            timeout=30,
        )
        resp.raise_for_status()
        summary = resp.json()["choices"][0]["message"]["content"].strip()
        return summary if summary else clean(desc, 120)
    except Exception as exc:  # 摘要失败不影响整体
        print(f"  (AI 摘要失败: {exc})")
        return clean(desc, 120)


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

            # 发布时间：优先 published，其次 updated，缺失则视为今天
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
                    "desc": ai_summary(title, entry.get("summary", ""), api_key),
                    "time": ts.astimezone(BEIJING).strftime("%m-%d %H:%M"),
                }
            )
            count += 1
        time.sleep(0.5)  # 对源网站友好一点

    items.sort(key=lambda x: x["time"], reverse=True)
    items = items[:max_total]

    date_str = now.strftime("%Y-%m-%d")
    lines = [
        f"# 📰 每日精选 {date_str}",
        "",
        f"> 共 {len(items)} 篇 · 生成于 {now.strftime('%H:%M')}"
        + (" · ✨ AI 中文摘要" if api_key else " · 原文简介"),
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
            lines.append(f"  {it['desc']}")
        lines.append("")

    os.makedirs(DAILY_DIR, exist_ok=True)
    digest_path = os.path.join(DAILY_DIR, f"{date_str}.md")
    with open(digest_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"✅ 已生成: {digest_path} ({len(items)} 篇)")

    # 更新 README 里的「今日阅读」列表
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
