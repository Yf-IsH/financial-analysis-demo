# Financial Analysis Demo

一个本地运行的财务报表分析 Demo。输入美股上市公司名称或股票代码后，应用会从 SEC EDGAR 的真实 XBRL 数据中读取公司财务事实数据，整理三大表、计算专业财务指标、展示时间趋势，并支持两家公司专业指标对比。

## 功能

- 公司搜索：支持公司名称、Ticker、CIK 模糊搜索。
- 三大表查看：利润表、资产负债表、现金流量表。
- 专业指标计算：根据 `需要包含的财务指标.xlsx` 纳入可由当前数据源计算或近似计算的专业指标。
- 指标说明：点击指标名称可查看公式、内涵和数据口径说明。
- 杜邦分析：单独展示 `净资产收益率 = 销售净利率 × 总资产周转率 × 权益倍数`。
- 时间趋势：展示收入、净利润、经营现金流、资产、负债、权益等关键项目趋势。
- 同行对比：输入另一家公司后，对比专业财务指标。

## 环境要求

- Python 3.10 或更高版本
- 可以访问互联网，用于首次下载 SEC EDGAR 数据
- 浏览器：Chrome、Edge、Firefox、Safari 均可

本项目当前只使用 Python 标准库，不依赖第三方 Python 包。仍然提供 `requirements.txt`，方便后续扩展和标准化部署。

## 快速开始

1. 进入项目目录：

```powershell
cd "D:\HuaweiMoveData\Users\chenb\Desktop\财报分析demo"
```

2. 可选：创建并激活虚拟环境。

Windows PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux：

```bash
python3 -m venv .venv
source .venv/bin/activate
```

3. 安装依赖：

```powershell
pip install -r requirements.txt
```

当前版本没有第三方依赖，因此这一步会很快完成。

4. 启动应用：

```powershell
python app.py
```

5. 在浏览器打开：

```text
http://127.0.0.1:8000
```

## 数据源

数据来自 SEC EDGAR 公开接口：

- `https://www.sec.gov/files/company_tickers.json`
- `https://data.sec.gov/api/xbrl/companyfacts/CIK##########.json`

应用不会使用样例数据。首次查询时会联网下载 SEC 数据，缓存会写入本目录下的 `.cache/` 文件夹。`.cache/` 已加入 `.gitignore`，不会提交到 GitHub。

## 配置项

可以通过环境变量调整默认行为：

- `PORT`：本地服务端口，默认 `8000`
- `SEC_USER_AGENT`：访问 SEC API 时使用的 User-Agent

示例：

```powershell
$env:PORT="8080"
$env:SEC_USER_AGENT="financial-analysis-demo your-email@example.com"
python app.py
```

## 常见问题

### 端口 8000 被占用

换一个端口启动：

```powershell
$env:PORT="8080"
python app.py
```

然后打开：

```text
http://127.0.0.1:8080
```

### 首次查询较慢

首次查询需要下载 SEC 公司列表和公司财报事实数据。下载完成后会缓存到 `.cache/`，同一家公司后续查询会更快。

### 无法连接 SEC 数据源

请检查网络连接、代理/VPN、防火墙设置。SEC API 需要公网访问。

### 某些指标为空

SEC XBRL 标签在不同公司之间可能存在披露差异。应用会在常见 US-GAAP 标签之间做兼容匹配，但如果某家公司没有披露对应科目，页面会显示为空值。

## 指标覆盖说明

页面只展示可计算或可合理近似的指标。仅靠 SEC companyfacts 无法可靠计算的市净率、市盈率、每股净资产、股利收益率、本量利分析系列公式、杠杆系数没有放入页面。

部分指标使用 SEC 可得科目近似：

- 应付账款周转率：采购成本暂用营业成本近似。
- 成本费用总额/成本费用利润率：按营业成本、经营费用、利息费用等可得科目近似。
- 股利支付率：用现金股利总额/净利润近似。
- ROCE：资本总额用有息债务平均余额+股东权益平均余额近似。

## 项目结构

```text
.
├── app.py
├── requirements.txt
├── README.md
├── static/
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── 需要包含的财务指标.xlsx
└── 财务报表分析材料.pdf
```

## 说明

本 Demo 适合用于课程展示和初步财务分析，不构成投资建议。
