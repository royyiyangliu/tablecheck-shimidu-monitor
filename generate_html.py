#!/usr/bin/env python3
"""从 availability_log.csv 生成可视化 index.html（每次爬虫后自动调用）"""

import csv
import os
from collections import defaultdict, OrderedDict

CSV_FILE = "availability_log.csv"
OUT_FILE = "index.html"


def load_csv():
    rows = []
    if not os.path.exists(CSV_FILE):
        return rows
    with open(CSV_FILE, "r", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        next(reader, None)  # 跳过标题行
        for row in reader:
            if len(row) < 5:
                continue
            date = row[1].strip()
            avail = row[2].strip()
            count_raw = row[4].strip()
            if not date or date in ("解析错误", ""):
                continue
            try:
                count = int(count_raw)
            except ValueError:
                count = 0
            rows.append({
                "timestamp": row[0].strip(),
                "date": date,
                "avail": avail,
                "count": count,
            })
    return rows


def build_pivot(rows):
    # sessions: OrderedDict {timestamp -> {date -> avail_str}}
    sessions = OrderedDict()
    all_dates = set()

    for r in rows:
        ts = r["timestamp"]
        if ts not in sessions:
            sessions[ts] = {}
        sessions[ts][r["date"]] = (r["avail"], r["count"])
        all_dates.add(r["date"])

    sorted_dates = sorted(all_dates)
    # 最新的排前面
    sorted_ts = sorted(sessions.keys(), reverse=True)
    return sorted_ts, sorted_dates, sessions


def render_cell(avail, count):
    if avail is None:
        return '<td class="nd">—</td>'
    if count == 0 or avail == "-":
        return '<td class="none">✗</td>'
    times = [t.strip() for t in avail.split("|")]
    inner = " &nbsp;·&nbsp; ".join(f'<span class="slot">{t}</span>' for t in times)
    return f'<td class="avail">{inner}</td>'


def generate_html(sorted_ts, sorted_dates, sessions):
    last_update = sorted_ts[0] if sorted_ts else "—"

    # 日期列头（省略年份）
    date_ths = "".join(
        f'<th class="date-col">{d[5:]}</th>' for d in sorted_dates
    )

    # 表体
    tbody_rows = []
    for ts in sorted_ts:
        cells = f'<td class="ts-cell">{ts}</td>'
        for date in sorted_dates:
            entry = sessions[ts].get(date)
            if entry is None:
                cells += render_cell(None, 0)
            else:
                cells += render_cell(*entry)
        tbody_rows.append(f"<tr>{cells}</tr>")
    tbody = "\n".join(tbody_rows)

    html = f"""<!DOCTYPE html>
<html lang="zh-Hans">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>新ばし しみづ &#x2014; 预约监控</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic UI",
                 "Segoe UI", sans-serif;
    background: #f0f2f5;
    color: #222;
    padding: 24px 16px 48px;
    font-size: 13px;
  }}
  header {{
    margin-bottom: 20px;
  }}
  h1 {{
    font-size: 1.2rem;
    font-weight: 700;
    color: #1a1a2e;
    margin-bottom: 4px;
  }}
  .meta {{
    color: #888;
    font-size: 0.78rem;
  }}
  .meta strong {{
    color: #555;
  }}
  .table-wrap {{
    overflow-x: auto;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.08);
  }}
  table {{
    border-collapse: collapse;
    background: #fff;
    min-width: 100%;
    white-space: nowrap;
  }}
  thead tr {{
    background: #1a1a2e;
    color: #fff;
  }}
  thead th {{
    padding: 10px 14px;
    font-weight: 600;
    font-size: 0.78rem;
    letter-spacing: 0.02em;
  }}
  th.date-col {{
    min-width: 110px;
  }}
  tbody tr:nth-child(even) td {{
    background-color: #f9f9fb;
  }}
  tbody tr:hover td {{
    background-color: #f0f4ff !important;
  }}
  td {{
    padding: 7px 14px;
    border-bottom: 1px solid #ececec;
    text-align: center;
    vertical-align: middle;
  }}
  td.ts-cell {{
    text-align: left;
    font-size: 0.75rem;
    color: #666;
    white-space: nowrap;
    min-width: 160px;
    font-variant-numeric: tabular-nums;
  }}
  td.avail {{
    background-color: #e6f4ea !important;
  }}
  td.avail .slot {{
    color: #1e6b32;
    font-weight: 600;
    font-size: 0.78rem;
  }}
  td.none {{
    color: #ccc;
    font-size: 0.9rem;
  }}
  td.nd {{
    color: #ddd;
    font-size: 0.9rem;
  }}
  tbody tr:hover td.avail {{
    background-color: #d4edda !important;
  }}
  .legend {{
    margin-top: 12px;
    display: flex;
    gap: 16px;
    font-size: 0.75rem;
    color: #888;
    align-items: center;
  }}
  .legend-item {{
    display: flex;
    align-items: center;
    gap: 4px;
  }}
  .swatch {{
    width: 12px; height: 12px; border-radius: 2px; display: inline-block;
  }}
</style>
</head>
<body>
<header>
  <h1>新ばし しみづ &nbsp;预约时段监控</h1>
  <p class="meta">最近检查：<strong>{last_update} JST</strong> &nbsp;·&nbsp; 共 <strong>{len(sorted_ts)}</strong> 次爬取 &nbsp;·&nbsp; 覆盖 <strong>{len(sorted_dates)}</strong> 个日期</p>
</header>
<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th style="text-align:left">检查时间 (JST)</th>
        {date_ths}
      </tr>
    </thead>
    <tbody>
{tbody}
    </tbody>
  </table>
</div>
<div class="legend">
  <span class="legend-item"><span class="swatch" style="background:#e6f4ea;border:1px solid #a8d5b0"></span>有可用时段</span>
  <span class="legend-item"><span style="color:#ccc;font-size:1rem">✗</span>&nbsp;无可用时段</span>
  <span class="legend-item"><span style="color:#ddd;font-size:1rem">—</span>&nbsp;该次未覆盖此日期</span>
</div>
</body>
</html>
"""
    return html


def main():
    rows = load_csv()
    if not rows:
        print("CSV 为空，跳过 HTML 生成")
        return
    sorted_ts, sorted_dates, sessions = build_pivot(rows)
    html = generate_html(sorted_ts, sorted_dates, sessions)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"  [HTML] 已生成 {OUT_FILE}（{len(sorted_ts)} 次爬取 × {len(sorted_dates)} 个日期）")


if __name__ == "__main__":
    main()
