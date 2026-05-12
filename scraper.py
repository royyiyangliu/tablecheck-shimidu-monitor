#!/usr/bin/env python3
"""
TableCheck 预约时段监控 - 新ばし しみづ
每次运行抓取可预约时段，追加到 availability_log.csv
同时保存截图和 API 响应供分析
"""

import asyncio
import csv
import json
import os
import re
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))
URL = "https://www.tablecheck.com/en/shops/shinbashi-shimidu/reserve"
SHOP_SLUG = "shinbashi-shimidu"


async def scrape():
    now_jst = datetime.now(JST)
    timestamp = now_jst.strftime("%Y-%m-%d %H:%M:%S")
    date_str = now_jst.strftime("%Y%m%d_%H%M%S")

    captured_api_data = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            timezone_id="Asia/Tokyo",
            viewport={"width": 1280, "height": 900},
        )
        page = await context.new_page()

        # 拦截所有 API 响应，寻找含时段信息的 JSON
        async def handle_response(response):
            url = response.url
            keywords = ["availability", "slot", "timeslot", "schedule",
                        "opening", "seat", "reserve", "booking"]
            if any(kw in url.lower() for kw in keywords):
                try:
                    data = await response.json()
                    captured_api_data.append({"url": url, "status": response.status, "data": data})
                    print(f"  [API] {response.status} {url}")
                except Exception:
                    pass
            elif SHOP_SLUG in url and response.status == 200:
                try:
                    data = await response.json()
                    body_str = json.dumps(data).lower()
                    if any(k in body_str for k in ["time", "slot", "seat", "available"]):
                        captured_api_data.append({"url": url, "status": response.status, "data": data})
                        print(f"  [API-shop] {url}")
                except Exception:
                    pass

        page.on("response", handle_response)

        # 加载页面
        print(f"[{timestamp}] 正在加载页面...")
        try:
            await page.goto(URL, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"  页面加载超时，继续执行: {e}")

        # 等待 JS 渲染
        await page.wait_for_timeout(6000)

        # 保存截图
        os.makedirs("screenshots", exist_ok=True)
        await page.screenshot(
            path=f"screenshots/{date_str}.png", full_page=True
        )
        print(f"  截图已保存: screenshots/{date_str}.png")

        # ── DOM 提取时段 ──────────────────────────────────────────────
        slots_data = {}  # {日期字符串: [时间1, 时间2, ...]}

        slot_selectors = [
            "[data-timeslot]",
            "[class*='timeslot' i]",
            "[class*='time-slot' i]",
            "[class*='TimeSlot']",
            "[class*='Slot']",
            "button[data-time]",
            "li[data-time]",
            ".reserve-timeslot",
            ".slots-container button",
            "#timetable-collapse button",
            "button[class*='time']",
        ]

        for sel in slot_selectors:
            try:
                elements = await page.query_selector_all(sel)
                if not elements:
                    continue
                print(f"  DOM 命中 {len(elements)} 个元素，选择器: {sel}")
                for el in elements:
                    text = (await el.text_content() or "").strip()
                    date_attr = await el.get_attribute("data-date")
                    time_attr = await el.get_attribute("data-time")
                    label = time_attr or text
                    if not label:
                        continue
                    key = date_attr or "未知日期"
                    slots_data.setdefault(key, []).append(label)
                break
            except Exception:
                continue

        # 兜底：从页面正文用正则提取时间字符串
        if not slots_data:
            try:
                body_text = await page.inner_text("body")
                times = re.findall(r"\b([01]?\d|2[0-3]):[0-5]\d\b", body_text)
                times = sorted(set(times))
                if times:
                    slots_data["正则提取"] = times
                    print(f"  正则提取时间: {times}")
            except Exception:
                pass

        # 保存 API JSON
        if captured_api_data:
            os.makedirs("api_dumps", exist_ok=True)
            with open(f"api_dumps/{date_str}.json", "w", encoding="utf-8") as f:
                json.dump(captured_api_data, f, ensure_ascii=False, indent=2)
            print(f"  保存 {len(captured_api_data)} 条 API 响应 → api_dumps/{date_str}.json")

        # 保存 HTML（仅首次，用于分析页面结构）
        if not os.path.exists(".structure_analyzed"):
            os.makedirs("html_dumps", exist_ok=True)
            html = await page.content()
            with open(f"html_dumps/{date_str}.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  HTML 已保存（首次运行）: html_dumps/{date_str}.html")

        await browser.close()

    # ── 写入 CSV ──────────────────────────────────────────────────────
    csv_file = "availability_log.csv"
    file_exists = os.path.exists(csv_file)

    with open(csv_file, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["检查时间(JST)", "预约日期", "可用时段", "API响应数", "备注"])

        if slots_data:
            for date, times in slots_data.items():
                writer.writerow([
                    timestamp,
                    date,
                    " | ".join(times),
                    len(captured_api_data),
                    "",
                ])
        else:
            writer.writerow([
                timestamp,
                "",
                "",
                len(captured_api_data),
                "DOM未找到时段，请查看 api_dumps/ 和 screenshots/",
            ])

    found = sum(len(v) for v in slots_data.values())
    print(f"[{timestamp}] 完成 — DOM时段: {found} 个，API响应: {len(captured_api_data)} 条")


if __name__ == "__main__":
    asyncio.run(scrape())
