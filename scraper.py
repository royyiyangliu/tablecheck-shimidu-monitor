#!/usr/bin/env python3
"""
TableCheck 预约时段监控 v2 - 新ばし しみづ
每次运行：加载页面 → 尝试页面交互 → 捕获 API + DOM 时段 → 写 CSV
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


async def scrape():
    now_jst = datetime.now(JST)
    timestamp = now_jst.strftime("%Y-%m-%d %H:%M:%S")
    date_str = now_jst.strftime("%Y%m%d_%H%M%S")

    captured_api_data = []

    # 提前建目录，确保 git add 时路径存在
    for d in ("screenshots", "api_dumps", "html_dumps"):
        os.makedirs(d, exist_ok=True)

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

        # 捕获所有 JSON 响应（不做关键词过滤，全量保留）
        async def handle_response(response):
            ct = response.headers.get("content-type", "")
            if "json" in ct and response.status == 200:
                try:
                    data = await response.json()
                    captured_api_data.append({"url": response.url, "data": data})
                    print(f"  [API] {response.url[:90]}")
                except Exception:
                    pass

        page.on("response", handle_response)

        # ── 加载页面 ─────────────────────────────────────────────────────
        print(f"[{timestamp}] 加载页面...")
        try:
            await page.goto(URL, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"  加载超时，继续: {e}")

        await page.wait_for_timeout(3000)
        await page.screenshot(path=f"screenshots/{date_str}_1_load.png", full_page=True)

        # 首次运行保存 HTML，用于人工分析页面结构
        if not os.path.exists(".structure_analyzed"):
            html = await page.content()
            with open(f"html_dumps/{date_str}.html", "w", encoding="utf-8") as f:
                f.write(html)
            print(f"  HTML已保存: html_dumps/{date_str}.html")

        # ── 尝试交互：选择套餐/人数 ──────────────────────────────────────
        # TableCheck 页面通常需要先选套餐再选人数才会出现时间表
        clicked_menu = False
        menu_selectors = [
            "[class*='course' i] button",
            "[class*='menu' i] button",
            "[class*='Course'] button",
            "[class*='Menu'] button",
            "button[class*='course' i]",
            "li[class*='course' i]",
            "ul > li:first-child button",   # 列表第一项
            "button[class*='reserve']",
        ]
        for sel in menu_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0 and await loc.is_visible(timeout=2000):
                    await loc.click(timeout=3000)
                    await page.wait_for_timeout(2000)
                    print(f"  已点击套餐: {sel}")
                    clicked_menu = True
                    break
            except Exception:
                continue

        if not clicked_menu:
            print("  未找到套餐按钮，跳过套餐选择")

        await page.screenshot(path=f"screenshots/{date_str}_2_menu.png", full_page=True)

        # 选择人数（2人）
        party_selectors = [
            "select[name='num_people']",
            "select[name*='num' i]",
            "select[class*='party' i]",
            "select[class*='guest' i]",
            "[class*='party-size'] select",
            "[class*='PartySize'] select",
        ]
        for sel in party_selectors:
            try:
                loc = page.locator(sel).first
                if await loc.count() > 0:
                    await loc.select_option("2")
                    await page.wait_for_timeout(2000)
                    print(f"  已选择人数2: {sel}")
                    break
            except Exception:
                continue

        # 等待时间表渲染
        await page.wait_for_timeout(4000)
        await page.screenshot(path=f"screenshots/{date_str}_3_slots.png", full_page=True)

        # ── DOM 提取时段 ──────────────────────────────────────────────────
        slots_dom = {}  # {日期: [时间, ...]}
        dom_selectors = [
            "[data-timeslot]",
            "[class*='timeslot' i]",
            "[class*='time-slot' i]",
            "[class*='TimeSlot']",
            "button[data-time]",
            "li[data-time]",
            ".timetable button",
            "#timetable-collapse button",
            "button[class*='time' i]",
        ]
        for sel in dom_selectors:
            try:
                elements = await page.query_selector_all(sel)
                if not elements:
                    continue
                print(f"  DOM命中 {len(elements)} 个，选择器: {sel}")
                for el in elements:
                    text = (await el.text_content() or "").strip()
                    d_attr = await el.get_attribute("data-date") or "未知日期"
                    t_attr = await el.get_attribute("data-time") or text
                    if t_attr:
                        slots_dom.setdefault(d_attr, []).append(t_attr)
                break
            except Exception:
                continue

        # 兜底：从页面文本提取完整 HH:MM 时间（非捕获组，捕获全匹配）
        slots_text = []
        try:
            body_text = await page.inner_text("body")
            # 非捕获组：匹配 HH:MM 整体
            slots_text = sorted(set(re.findall(r"\b(?:[01]?\d|2[0-3]):[0-5]\d\b", body_text)))
            if slots_text:
                print(f"  文本时间: {slots_text}")
        except Exception as e:
            print(f"  文本提取失败: {e}")

        await browser.close()

    # ── 保存 API JSON ─────────────────────────────────────────────────────
    if captured_api_data:
        api_file = f"api_dumps/{date_str}.json"
        with open(api_file, "w", encoding="utf-8") as f:
            json.dump(captured_api_data, f, ensure_ascii=False, indent=2)
        print(f"  API: {len(captured_api_data)} 条 → {api_file}")
    else:
        # 写一个占位文件，确保目录被 git 追踪
        with open("api_dumps/.gitkeep", "w") as f:
            pass

    # ── 写入 CSV ──────────────────────────────────────────────────────────
    csv_file = "availability_log.csv"
    file_exists = os.path.exists(csv_file)

    with open(csv_file, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "检查时间(JST)", "预约日期", "DOM时段(竖线分隔)",
                "文本时间", "API响应数", "备注",
            ])
        if slots_dom:
            for date, times in slots_dom.items():
                writer.writerow([
                    timestamp, date, " | ".join(times),
                    " | ".join(slots_text), len(captured_api_data), "",
                ])
        else:
            note = "DOM无时段" + ("，文本有时间" if slots_text else "，文本也无时间")
            writer.writerow([
                timestamp, "", "",
                " | ".join(slots_text), len(captured_api_data), note,
            ])

    total_dom = sum(len(v) for v in slots_dom.values())
    print(f"[{timestamp}] 完成 — DOM:{total_dom} 文本:{len(slots_text)} API:{len(captured_api_data)}")


if __name__ == "__main__":
    asyncio.run(scrape())
