#!/usr/bin/env python3
"""
TableCheck 预约时段监控 v3 - 新ばし しみづ
直接解析 /available/timetable API，记录未来8天每个时段的可用状态
"""

import asyncio
import csv
import json
import os
import urllib.parse
from datetime import datetime, timezone, timedelta
from playwright.async_api import async_playwright

JST = timezone(timedelta(hours=9))
URL = "https://www.tablecheck.com/en/shops/shinbashi-shimidu/reserve"
NUM_PEOPLE = 2   # 默认抓取2人座位的可用情况
TARGET_DAYS = 8  # 监控未来N天


def seconds_to_hhmm(sec: int) -> str:
    """将一天内的秒数转为 HH:MM 字符串"""
    h = sec // 3600
    m = (sec % 3600) // 60
    return f"{h:02d}:{m:02d}"


async def scrape():
    now_jst = datetime.now(JST)
    timestamp = now_jst.strftime("%Y-%m-%d %H:%M:%S")
    date_str = now_jst.strftime("%Y%m%d_%H%M%S")

    timetable_data = None   # 目标 API 响应
    timetable_url = None    # 目标 API 完整 URL

    os.makedirs("screenshots", exist_ok=True)
    os.makedirs("api_dumps", exist_ok=True)

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

        # 只捕获目标 timetable API
        async def handle_response(response):
            nonlocal timetable_data, timetable_url
            if "available/timetable" in response.url and response.status == 200:
                try:
                    timetable_url = response.url
                    timetable_data = await response.json()
                    print(f"  [目标API] {response.url[:120]}")
                except Exception as e:
                    print(f"  [目标API] 解析失败: {e}")

        page.on("response", handle_response)

        # 加载页面
        print(f"[{timestamp}] 加载页面...")
        try:
            await page.goto(URL, wait_until="networkidle", timeout=60000)
        except Exception as e:
            print(f"  加载超时，继续: {e}")

        await page.wait_for_timeout(3000)

        # 选择人数 → 触发 timetable API 调用
        party_selectors = [
            f"select[name='num_people']",
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
                    await loc.select_option(str(NUM_PEOPLE))
                    await page.wait_for_timeout(3000)
                    print(f"  已选择人数{NUM_PEOPLE}: {sel}")
                    break
            except Exception:
                continue

        # 如果 API 还没触发，再等一会儿
        if timetable_data is None:
            await page.wait_for_timeout(3000)

        # 用第二次请求补全至 TARGET_DAYS 天（API 固定窗口约6天，无结束日期参数）
        # 将 reservation[start_date] 设为 今天+6，获取后续日期后合并
        if timetable_url and timetable_data:
            parsed = urllib.parse.urlparse(timetable_url)
            params = dict(urllib.parse.parse_qsl(parsed.query))
            start_key = "reservation[start_date]"
            if start_key in params:
                extra_start = (now_jst + timedelta(days=6)).strftime("%Y-%m-%d")
                params[start_key] = extra_start
                extra_url = urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(params)))
                try:
                    resp = await page.request.get(extra_url, timeout=15000)
                    if resp.ok:
                        extra = await resp.json()
                        extra_slots = extra.get("data", {}).get("slots", {})
                        if extra_slots:
                            timetable_data["data"]["slots"].update(extra_slots)
                            print(f"  第二次请求成功，新增 {len(extra_slots)} 天数据（start_date={extra_start}）")
                except Exception as e:
                    print(f"  第二次请求失败: {e}")

        await page.screenshot(path=f"screenshots/{date_str}.png", full_page=True)
        await browser.close()

    # ── 解析 timetable 数据 ────────────────────────────────────────────────
    rows = []  # 每行：[timestamp, date, avail_str, unavail_str, avail_count]

    if timetable_data:
        # 保存原始 API 响应备用
        with open(f"api_dumps/{date_str}.json", "w", encoding="utf-8") as f:
            json.dump(timetable_data, f, ensure_ascii=False, indent=2)

        try:
            slots_by_date = timetable_data["data"]["slots"]
            seconds_list = timetable_data["data"].get("seconds", [])

            # 转换秒→时间，建全局时段标签
            all_times = sorted(set(seconds_list))
            all_time_labels = [seconds_to_hhmm(s) for s in all_times]

            print(f"  全部时段: {all_time_labels}")

            for date, slot_dict in sorted(slots_by_date.items()):
                avail_times = []
                unavail_times = []
                for _ts_key, info in slot_dict.items():
                    t = seconds_to_hhmm(info["seconds"])
                    if info["available"]:
                        avail_times.append(t)
                    else:
                        unavail_times.append(t)

                avail_str = " | ".join(sorted(avail_times)) if avail_times else "-"
                unavail_str = " | ".join(sorted(unavail_times)) if unavail_times else "-"
                rows.append([timestamp, date, avail_str, unavail_str, len(avail_times)])
                print(f"  {date}  可用:{avail_str}  不可:{unavail_str}")

        except Exception as e:
            print(f"  解析出错: {e}")
            rows.append([timestamp, "解析错误", str(e), "", 0])
    else:
        print("  未捕获到 timetable API 响应")
        rows.append([timestamp, "", "未获取到数据", "", 0])

    # ── 写入 CSV ──────────────────────────────────────────────────────────
    csv_file = "availability_log.csv"
    file_exists = os.path.exists(csv_file)

    with open(csv_file, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow([
                "检查时间(JST)", "预约日期",
                "可用时段(HH:MM)", "不可用时段(HH:MM)", "可用数量",
            ])
        writer.writerows(rows)

    total_avail = sum(r[4] for r in rows if isinstance(r[4], int))
    print(f"[{timestamp}] 完成 — {len(rows)} 个日期，共 {total_avail} 个可用时段")

    # 生成可视化 HTML
    try:
        import generate_html
        generate_html.main()
    except Exception as e:
        print(f"  [HTML] 生成失败: {e}")


if __name__ == "__main__":
    asyncio.run(scrape())
