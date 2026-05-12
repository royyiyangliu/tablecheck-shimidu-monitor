# 新ばし しみづ 预约监控

自动抓取 [TableCheck 预约页](https://www.tablecheck.com/en/shops/shinbashi-shimidu/reserve) 的可用时段，寻找每日开放规律。

## 运行时间

每天北京/东京时间（JST）：11:01 / 11:10 / 12:01 / 12:10

## 输出文件

| 文件 | 说明 |
|------|------|
| `availability_log.csv` | 主数据文件，每次检查追加一行 |
| `screenshots/` | 每次运行的页面截图 |
| `api_dumps/` | 捕获的 API JSON 响应（含完整时段数据） |
| `html_dumps/` | 首次运行的 HTML（用于分析页面结构） |

## 手动触发

在 GitHub 仓库页面 → Actions → TableCheck 预约监控 → Run workflow

## 数据字段说明

- **检查时间(JST)**：本次运行时间
- **预约日期**：可预约的具体日期
- **可用时段**：该日期下所有可选时段，以 `|` 分隔
- **API响应数**：捕获到的 API 调用数量（>0 表示有原始 JSON 数据可分析）
