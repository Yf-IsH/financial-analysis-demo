from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
CACHE_DIR = ROOT / ".cache"
STATIC_DIR = ROOT / "static"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"
SEC_FACTS_URL = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
CACHE_TTL_SECONDS = 60 * 60 * 24
USER_AGENT = os.environ.get(
    "SEC_USER_AGENT",
    "FinancialStatementDemo/0.1 contact@example.com",
)


METRIC_LABELS = {
    "revenue": "营业收入",
    "cost_of_revenue": "营业成本",
    "gross_profit": "毛利润",
    "operating_income": "经营利润",
    "net_income": "净利润",
    "eps_diluted": "稀释 EPS",
    "cash": "现金及等价物",
    "current_assets": "流动资产",
    "assets": "总资产",
    "current_liabilities": "流动负债",
    "liabilities": "总负债",
    "equity": "股东权益",
    "inventory": "存货",
    "receivables": "应收账款",
    "operating_cash_flow": "经营活动现金流",
    "capex": "资本开支",
    "investing_cash_flow": "投资活动现金流",
    "financing_cash_flow": "融资活动现金流",
    "dividends": "现金股利",
    "buybacks": "股票回购",
    "accounts_payable": "应付账款",
    "pretax_income": "利润总额/税前利润",
    "income_tax": "所得税费用",
    "interest_expense": "利息费用",
    "depreciation_amortization": "折旧摊销",
    "operating_expenses": "经营费用",
    "short_term_debt": "短期有息债务",
    "long_term_debt": "长期有息债务",
    "eps_basic": "基本 EPS",
}


TAXONOMY_MAP = {
    "revenue": [
        "Revenues",
        "RevenueFromContractWithCustomerExcludingAssessedTax",
        "SalesRevenueNet",
        "SalesRevenueGoodsNet",
        "SalesRevenueServicesNet",
    ],
    "cost_of_revenue": [
        "CostOfRevenue",
        "CostOfGoodsAndServicesSold",
        "CostOfGoodsSold",
        "CostOfServicesRevenue",
    ],
    "gross_profit": ["GrossProfit"],
    "operating_income": ["OperatingIncomeLoss"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "eps_diluted": ["EarningsPerShareDiluted"],
    "cash": [
        "CashAndCashEquivalentsAtCarryingValue",
        "CashCashEquivalentsRestrictedCashAndRestrictedCashEquivalents",
    ],
    "current_assets": ["AssetsCurrent"],
    "assets": ["Assets"],
    "current_liabilities": ["LiabilitiesCurrent"],
    "liabilities": ["Liabilities"],
    "equity": [
        "StockholdersEquity",
        "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    ],
    "inventory": ["InventoryNet"],
    "receivables": ["AccountsReceivableNetCurrent"],
    "operating_cash_flow": ["NetCashProvidedByUsedInOperatingActivities"],
    "capex": [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
    ],
    "investing_cash_flow": ["NetCashProvidedByUsedInInvestingActivities"],
    "financing_cash_flow": ["NetCashProvidedByUsedInFinancingActivities"],
    "dividends": ["PaymentsOfDividends", "PaymentsOfOrdinaryDividends"],
    "buybacks": [
        "PaymentsForRepurchaseOfCommonStock",
        "PaymentsForRepurchaseOfEquity",
    ],
    "accounts_payable": ["AccountsPayableCurrent"],
    "pretax_income": [
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxes",
        "IncomeLossBeforeIncomeTaxes",
    ],
    "income_tax": ["IncomeTaxExpenseBenefit"],
    "interest_expense": ["InterestExpenseNonOperating", "InterestExpense"],
    "depreciation_amortization": [
        "DepreciationDepletionAndAmortization",
        "DepreciationAndAmortization",
        "Depreciation",
    ],
    "operating_expenses": [
        "OperatingExpenses",
        "SellingGeneralAndAdministrativeExpense",
        "SellingGeneralAndAdministrativeExpense",
        "ResearchAndDevelopmentExpense",
    ],
    "short_term_debt": [
        "ShortTermBorrowings",
        "ShortTermDebt",
        "CurrentPortionOfLongTermDebt",
        "LongTermDebtCurrent",
    ],
    "long_term_debt": [
        "LongTermDebtAndFinanceLeaseObligationsNoncurrent",
        "LongTermDebtNoncurrent",
        "LongTermDebt",
    ],
    "eps_basic": ["EarningsPerShareBasic"],
}


STATEMENT_ROWS = {
    "income": [
        "revenue",
        "cost_of_revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "pretax_income",
        "income_tax",
        "interest_expense",
        "operating_expenses",
        "depreciation_amortization",
        "eps_basic",
        "eps_diluted",
    ],
    "balance": [
        "cash",
        "receivables",
        "inventory",
        "current_assets",
        "assets",
        "current_liabilities",
        "accounts_payable",
        "short_term_debt",
        "long_term_debt",
        "liabilities",
        "equity",
    ],
    "cashflow": [
        "operating_cash_flow",
        "capex",
        "investing_cash_flow",
        "financing_cash_flow",
        "dividends",
        "buybacks",
    ],
}


@dataclass
class FactPoint:
    fy: int
    fp: str
    form: str
    filed: str
    start: str
    end: str
    val: float
    unit: str
    frame: str


def ensure_dirs() -> None:
    CACHE_DIR.mkdir(exist_ok=True)


def cache_path(name: str) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", name)
    return CACHE_DIR / safe


def fetch_json(url: str, cache_name: str, ttl: int = CACHE_TTL_SECONDS) -> Any:
    ensure_dirs()
    path = cache_path(cache_name)
    if path.exists() and time.time() - path.stat().st_mtime < ttl:
        return json.loads(path.read_text(encoding="utf-8"))

    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/json",
            "Accept-Encoding": "identity",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"SEC 请求失败：HTTP {exc.code} {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"无法连接 SEC 数据源：{exc.reason}") from exc

    path.write_text(payload, encoding="utf-8")
    return json.loads(payload)


def get_companies() -> list[dict[str, Any]]:
    raw = fetch_json(SEC_TICKERS_URL, "company_tickers.json", ttl=60 * 60 * 24 * 7)
    companies = []
    for row in raw.values():
        companies.append(
            {
                "cik": f"{int(row['cik_str']):010d}",
                "ticker": str(row["ticker"]).upper(),
                "title": str(row["title"]),
            }
        )
    return sorted(companies, key=lambda item: item["ticker"])


def search_companies(query: str, limit: int = 12) -> list[dict[str, Any]]:
    query = query.strip().lower()
    if not query:
        return []
    companies = get_companies()
    exact = []
    prefix = []
    contains = []
    for company in companies:
        ticker = company["ticker"].lower()
        title = company["title"].lower()
        cik = company["cik"].lstrip("0")
        if query == ticker or query == cik:
            exact.append(company)
        elif ticker.startswith(query) or title.startswith(query):
            prefix.append(company)
        elif query in ticker or query in title or query in cik:
            contains.append(company)
    return (exact + prefix + contains)[:limit]


def get_company_by_cik(cik: str) -> dict[str, Any] | None:
    normalized = f"{int(cik):010d}" if cik.isdigit() else cik
    for company in get_companies():
        if company["cik"] == normalized:
            return company
    return None


def get_company_facts(cik: str) -> dict[str, Any]:
    normalized = f"{int(cik):010d}"
    return fetch_json(SEC_FACTS_URL.format(cik=normalized), f"facts_{normalized}.json")


def unit_priority(units: dict[str, Any]) -> tuple[str, list[dict[str, Any]]] | None:
    preferred = ["USD", "shares", "USD/shares", "pure"]
    for unit in preferred:
        if unit in units:
            return unit, units[unit]
    for unit, points in units.items():
        if points:
            return unit, points
    return None


def point_duration_days(point: dict[str, Any]) -> int | None:
    try:
        start = date.fromisoformat(point["start"])
        end = date.fromisoformat(point["end"])
    except (KeyError, ValueError):
        return None
    return (end - start).days


def is_duration_metric(metric: str) -> bool:
    return metric in {
        "revenue",
        "cost_of_revenue",
        "gross_profit",
        "operating_income",
        "net_income",
        "eps_diluted",
        "eps_basic",
        "pretax_income",
        "income_tax",
        "interest_expense",
        "depreciation_amortization",
        "operating_expenses",
        "operating_cash_flow",
        "capex",
        "investing_cash_flow",
        "financing_cash_flow",
        "dividends",
        "buybacks",
    }


def is_cashflow_metric(metric: str) -> bool:
    return metric in {
        "operating_cash_flow",
        "capex",
        "investing_cash_flow",
        "financing_cash_flow",
        "dividends",
        "buybacks",
    }


def accept_point(metric: str, point: dict[str, Any], period: str) -> bool:
    form = point.get("form")
    if form not in {"10-K", "10-Q", "20-F", "40-F"}:
        return False
    fp = point.get("fp")
    if period == "annual" and form in {"10-K", "20-F", "40-F"}:
        if fp not in {"FY", None}:
            return False
        if is_duration_metric(metric):
            days = point_duration_days(point)
            return days is None or 250 <= days <= 380
        return True
    if period == "quarterly" and form == "10-Q":
        if fp not in {"Q1", "Q2", "Q3"}:
            return False
        if is_duration_metric(metric):
            days = point_duration_days(point)
            if is_cashflow_metric(metric):
                return days is not None and 60 <= days <= 285
            return days is not None and 60 <= days <= 120
        return True
    return False


def extract_points(facts: dict[str, Any], metric: str, period: str) -> list[FactPoint]:
    us_gaap = facts.get("facts", {}).get("us-gaap", {})
    collected = []
    for tag in TAXONOMY_MAP[metric]:
        fact = us_gaap.get(tag)
        if not fact:
            continue
        selected = unit_priority(fact.get("units", {}))
        if not selected:
            continue
        unit, raw_points = selected
        points = []
        for point in raw_points:
            if "val" not in point or "fy" not in point or "end" not in point:
                continue
            if not accept_point(metric, point, period):
                continue
            try:
                fy = int(point["fy"])
                val = float(point["val"])
            except (TypeError, ValueError):
                continue
            points.append(
                FactPoint(
                    fy=fy,
                    fp=str(point.get("fp") or ""),
                    form=str(point.get("form") or ""),
                    filed=str(point.get("filed") or ""),
                    start=str(point.get("start") or ""),
                    end=str(point.get("end") or ""),
                    val=val,
                    unit=unit,
                    frame=str(point.get("frame") or ""),
                )
            )
        if points:
            collected.extend(points)
    points = dedupe_points(collected)
    if period == "quarterly" and is_cashflow_metric(metric):
        points = convert_ytd_cashflow_to_quarter(points)
    return points


def convert_ytd_cashflow_to_quarter(points: list[FactPoint]) -> list[FactPoint]:
    converted = []
    ytd_by_year: dict[int, FactPoint] = {}
    for point in points:
        order = fp_order(point.fp)
        days = days_between(point)
        if days is None or days <= 120 or order <= 1:
            converted.append(point)
            ytd_by_year[point.fy] = point
            continue
        previous = ytd_by_year.get(point.fy)
        if previous is not None:
            converted.append(
                FactPoint(
                    fy=point.fy,
                    fp=point.fp,
                    form=point.form,
                    filed=point.filed,
                    start=point.start,
                    end=point.end,
                    val=point.val - previous.val,
                    unit=point.unit,
                    frame=point.frame,
                )
            )
        else:
            converted.append(point)
        ytd_by_year[point.fy] = point
    return converted


def days_between(point: FactPoint) -> int | None:
    try:
        start = date.fromisoformat(point.start)
        end = date.fromisoformat(point.end)
    except ValueError:
        return None
    return (end - start).days


def dedupe_points(points: list[FactPoint]) -> list[FactPoint]:
    by_key: dict[tuple[int, str], FactPoint] = {}
    for point in points:
        key = (point.fy, point.fp)
        current = by_key.get(key)
        if current is None or (point.filed, point.end) > (current.filed, current.end):
            by_key[key] = point
    return sorted(by_key.values(), key=lambda item: (item.fy, item.fp, item.end))


def build_series(facts: dict[str, Any], period: str) -> dict[str, dict[str, Any]]:
    series = {}
    for metric in METRIC_LABELS:
        points = extract_points(facts, metric, period)
        series[metric] = {
            "label": METRIC_LABELS[metric],
            "points": [
                {
                    "period": f"{point.fy}" if period == "annual" else f"{point.fy} {point.fp}",
                    "fy": point.fy,
                    "fp": point.fp,
                    "form": point.form,
                    "filed": point.filed,
                    "start": point.start,
                    "end": point.end,
                    "value": point.val,
                    "unit": point.unit,
                }
                for point in points
            ],
        }
    return series


def collect_periods(series: dict[str, dict[str, Any]]) -> list[str]:
    periods = set()
    order = {}
    for metric in series.values():
        for index, point in enumerate(metric["points"]):
            period = point["period"]
            periods.add(period)
            order[period] = max(order.get(period, 0), point["fy"] * 10 + fp_order(point["fp"]))
    return sorted(periods, key=lambda period: order.get(period, 0))[-8:]


def fp_order(fp: str) -> int:
    return {"Q1": 1, "Q2": 2, "Q3": 3, "FY": 4, "": 4}.get(fp, 0)


def value_for(series: dict[str, dict[str, Any]], metric: str, period: str) -> float | None:
    for point in series.get(metric, {}).get("points", []):
        if point["period"] == period:
            return point["value"]
    return None


def make_statement(series: dict[str, dict[str, Any]], kind: str, periods: list[str]) -> list[dict[str, Any]]:
    rows = []
    for metric in STATEMENT_ROWS[kind]:
        rows.append(
            {
                "metric": metric,
                "label": METRIC_LABELS[metric],
                "values": [value_for(series, metric, period) for period in periods],
            }
        )
    return rows


def safe_div(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator in (None, 0):
        return None
    return numerator / denominator


def add_values(*values: float | None) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return sum(present)


def subtract_values(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return left - right


def average_value(series: dict[str, dict[str, Any]], metric: str, periods: list[str], index: int) -> float | None:
    current = value_for(series, metric, periods[index])
    if current is None:
        return None
    if index == 0:
        return current
    previous = value_for(series, metric, periods[index - 1])
    if previous is None:
        return current
    return (current + previous) / 2


def period_factor(periods: list[str], index: int) -> int:
    return 90 if "Q" in periods[index] else 360


def annualize(value: float | None, periods: list[str], index: int) -> float | None:
    if value is None:
        return None
    if "Q" not in periods[index]:
        return value
    return value * 4


def value_at(series: dict[str, dict[str, Any]], metric: str, periods: list[str], index: int) -> float | None:
    return value_for(series, metric, periods[index])


def interest_bearing_debt(series: dict[str, dict[str, Any]], periods: list[str], index: int) -> float | None:
    return add_values(
        value_at(series, "short_term_debt", periods, index),
        value_at(series, "long_term_debt", periods, index),
    )


def ebit(series: dict[str, dict[str, Any]], periods: list[str], index: int) -> float | None:
    pretax = value_at(series, "pretax_income", periods, index)
    interest = value_at(series, "interest_expense", periods, index)
    if pretax is not None or interest is not None:
        return add_values(pretax, interest)
    return value_at(series, "operating_income", periods, index)


def ebitda(series: dict[str, dict[str, Any]], periods: list[str], index: int) -> float | None:
    return add_values(
        value_at(series, "net_income", periods, index),
        value_at(series, "income_tax", periods, index),
        value_at(series, "interest_expense", periods, index),
        value_at(series, "depreciation_amortization", periods, index),
    )


def fcf(series: dict[str, dict[str, Any]], periods: list[str], index: int) -> float | None:
    ocf = value_at(series, "operating_cash_flow", periods, index)
    capex_value = value_at(series, "capex", periods, index)
    if ocf is None or capex_value is None:
        return None
    return ocf - abs(capex_value)


def turnover_days(turnover: float | None, periods: list[str], index: int) -> float | None:
    if turnover in (None, 0):
        return None
    return period_factor(periods, index) / turnover


def metric_row(
    key: str,
    label: str,
    formula: str,
    meaning: str,
    unit: str,
    group: str,
    values: list[float | None],
    status: str = "available",
    note: str = "",
) -> dict[str, Any]:
    return {
        "metric": key,
        "label": label,
        "formula": formula,
        "meaning": meaning,
        "unit": unit,
        "group": group,
        "status": status,
        "note": note,
        "values": values,
    }


def make_ratios(series: dict[str, dict[str, Any]], periods: list[str]) -> list[dict[str, Any]]:
    rows = []
    gross_margin = []
    operating_margin = []
    net_margin = []
    roa = []
    roe = []
    equity_multiplier = []
    asset_turnover = []
    ar_turnover = []
    ar_days = []
    inventory_turnover = []
    inventory_days = []
    ap_turnover = []
    ap_days = []
    cash_cycle = []
    cost_expense_total = []
    cost_expense_margin = []
    debt_ratio = []
    capital_debt_ratio = []
    interest_coverage = []
    working_capital = []
    current_ratio = []
    quick_ratio = []
    ebitda_values = []
    fcf_values = []
    dividend_payout = []
    roce = []
    accrual_profit = []

    for index, period in enumerate(periods):
        revenue = value_at(series, "revenue", periods, index)
        cost = value_at(series, "cost_of_revenue", periods, index)
        gross_profit = value_at(series, "gross_profit", periods, index)
        operating_income = value_at(series, "operating_income", periods, index)
        net_income = value_at(series, "net_income", periods, index)
        assets = value_at(series, "assets", periods, index)
        liabilities = value_at(series, "liabilities", periods, index)
        equity = value_at(series, "equity", periods, index)
        current_assets = value_at(series, "current_assets", periods, index)
        current_liabilities = value_at(series, "current_liabilities", periods, index)
        inventory = value_at(series, "inventory", periods, index)
        ocf = value_at(series, "operating_cash_flow", periods, index)
        capex_value = value_at(series, "capex", periods, index)
        dividends = value_at(series, "dividends", periods, index)
        pretax = value_at(series, "pretax_income", periods, index)
        interest = value_at(series, "interest_expense", periods, index)
        operating_expenses = value_at(series, "operating_expenses", periods, index)
        avg_assets = average_value(series, "assets", periods, index)
        avg_equity = average_value(series, "equity", periods, index)
        avg_ar = average_value(series, "receivables", periods, index)
        avg_inventory = average_value(series, "inventory", periods, index)
        avg_ap = average_value(series, "accounts_payable", periods, index)
        avg_debt = average_value(series, "short_term_debt", periods, index)
        long_debt_avg = average_value(series, "long_term_debt", periods, index)
        avg_interest_debt = add_values(avg_debt, long_debt_avg)

        gm = safe_div(gross_profit if gross_profit is not None else subtract_values(revenue, cost), revenue)
        om = safe_div(operating_income, revenue)
        nm = safe_div(net_income, revenue)
        at = safe_div(annualize(revenue, periods, index), avg_assets)
        art = safe_div(annualize(revenue, periods, index), avg_ar)
        invt = safe_div(annualize(cost, periods, index), avg_inventory)
        apt = safe_div(annualize(cost, periods, index), avg_ap)
        id_value = interest_bearing_debt(series, periods, index)
        ebit_value = ebit(series, periods, index)
        ebitda_value = ebitda(series, periods, index)
        fcf_value = fcf(series, periods, index)
        cost_exp_total = add_values(cost, operating_expenses, interest)
        roce_denominator = add_values(avg_interest_debt, avg_equity)

        gross_margin.append(gm)
        operating_margin.append(om)
        net_margin.append(nm)
        roa.append(safe_div(annualize(net_income, periods, index), avg_assets))
        roe.append(safe_div(annualize(net_income, periods, index), avg_equity))
        equity_multiplier.append(safe_div(assets, equity))
        asset_turnover.append(at)
        ar_turnover.append(art)
        ar_days.append(turnover_days(art, periods, index))
        inventory_turnover.append(invt)
        inventory_days.append(turnover_days(invt, periods, index))
        ap_turnover.append(apt)
        ap_days.append(turnover_days(apt, periods, index))
        cash_cycle.append(
            None
            if ar_days[-1] is None or inventory_days[-1] is None or ap_days[-1] is None
            else inventory_days[-1] + ar_days[-1] - ap_days[-1]
        )
        cost_expense_total.append(cost_exp_total)
        cost_expense_margin.append(safe_div(pretax, cost_exp_total))
        debt_ratio.append(safe_div(liabilities, assets))
        capital_debt_ratio.append(safe_div(id_value, add_values(id_value, equity)))
        interest_coverage.append(safe_div(ebit_value, interest))
        working_capital.append(subtract_values(current_assets, current_liabilities))
        current_ratio.append(safe_div(current_assets, current_liabilities))
        quick_ratio.append(safe_div(subtract_values(current_assets, inventory), current_liabilities))
        ebitda_values.append(ebitda_value)
        fcf_values.append(fcf_value)
        dividend_payout.append(safe_div(abs(dividends) if dividends is not None else None, net_income))
        roce.append(safe_div(annualize(ebit_value, periods, index), roce_denominator))
        accrual_profit.append(subtract_values(net_income, ocf))

    rows.extend(
        [
            metric_row("roe", "净资产收益率(权益报酬率)", "净利润(归母)/净资产平均余额(归母)", "净利润与股东权益的比值，反映股东的投资回报。", "%", "盈利能力", roe),
            metric_row("roa", "总资产收益率", "净利润(归母)/总资产平均余额", "净利润与总资产的比值，用于观察资产整体盈利效率。", "%", "盈利能力", roa),
            metric_row("net_margin", "销售净利率", "净利润(归母)/营业收入", "一元钱收入产生多少净利润。", "%", "盈利能力", net_margin),
            metric_row("equity_multiplier", "权益倍数", "总资产/股东权益；平均口径为总资产平均余额/净资产平均余额", "反映资本结构和财务杠杆。", "x", "杜邦分析", equity_multiplier),
            metric_row("gross_margin", "毛利率", "(营业收入-营业成本)/营业收入", "一元收入产生多少毛利。", "%", "盈利能力", gross_margin),
            metric_row("operating_margin", "营业利润率", "营业利润/营业收入", "一元收入产生多少营业利润。", "%", "盈利能力", operating_margin),
            metric_row("accrual_profit", "应计利润", "净利润-经营活动现金流量净额", "观察净利润是否有充足现金流支撑。", "", "现金流质量", accrual_profit),
            metric_row("asset_turnover", "总资产周转率(单位:次)", "营业收入/总资产平均余额", "反映企业利用现有资产创收的能力。", "x", "营运效率", asset_turnover),
            metric_row("asset_turnover_days", "总资产周转天数", "360/总资产周转率", "资产完成一次收入周转所需的近似天数。", "天", "营运效率", [turnover_days(v, periods, i) for i, v in enumerate(asset_turnover)]),
            metric_row("ar_turnover", "应收账款周转率(单位:次)", "营业收入/应收账款平均余额", "衡量销售回款能力和客户信用占用。", "x", "营运效率", ar_turnover),
            metric_row("ar_days", "应收账款周转天数", "360/应收账款周转率", "收入形成现金回款的平均天数。", "天", "营运效率", ar_days),
            metric_row("inventory_turnover", "存货周转率(单位:次)", "营业成本/存货平均余额", "企业存货销售、使用效率。", "x", "营运效率", inventory_turnover),
            metric_row("inventory_days", "存货周转天数", "360/存货周转率", "存货从采购/生产到销售的近似天数。", "天", "营运效率", inventory_days),
            metric_row("ap_turnover", "应付账款周转率(单位:次)", "营业成本/应付账款平均余额；以营业成本近似采购成本", "反映支付供应商货款效率或占用供应商资金程度。", "x", "营运效率", ap_turnover, note="采购成本在 SEC companyfacts 中通常不可直接取得，本 demo 按 Excel 说明暂用营业成本近似。"),
            metric_row("ap_days", "应付账款周转天数", "360/应付账款周转率", "企业平均占用供应商账期天数。", "天", "营运效率", ap_days),
            metric_row("cash_conversion_cycle", "现金循环周期", "存货周转天数+应收账款周转天数-应付账款周转天数", "企业从付出现金到收回现金所需的平均时间。", "天", "营运效率", cash_cycle),
            metric_row("cost_expense_margin", "成本费用利润率", "利润总额/成本费用总额", "每消耗一元成本费用创造多少利润总额。", "%", "盈利能力", cost_expense_margin, note="SEC 披露口径与国内报表科目不同，成本费用总额按可得科目近似。"),
            metric_row("cost_expense_total", "成本费用总额", "营业成本+税金及附加+管理费用+销售费用+研发费用+财务费用", "反映企业当期生产经营产生的成本、费用。", "", "成本费用", cost_expense_total, note="税金及附加、销售/管理/研发/财务费用拆分未必完整，使用营业成本、经营费用、利息费用近似。"),
            metric_row("debt_ratio", "资产负债率", "总负债/总资产", "总资产中有多少以负债形式取得。", "%", "偿债能力", debt_ratio),
            metric_row("capital_debt_ratio", "资本负债率", "有息负债/(有息负债+所有者权益)", "反映有息债务融资在资本结构中的比重。", "%", "偿债能力", capital_debt_ratio, note="有息负债按短期债务和长期债务常见 SEC 标签归集。"),
            metric_row("interest_coverage", "利息保障倍数", "息税前收益/利息支出", "衡量经营收益覆盖利息支出的能力。", "x", "偿债能力", interest_coverage),
            metric_row("working_capital", "营运资本", "流动资产-流动负债", "衡量企业短期偿债缓冲。", "", "偿债能力", working_capital),
            metric_row("current_ratio", "流动比率", "流动资产/流动负债", "短期资产覆盖短期负债的倍数。", "x", "偿债能力", current_ratio),
            metric_row("quick_ratio", "速动比率", "(流动资产-存货)/流动负债", "剔除存货后短期资产覆盖短期负债的倍数。", "x", "偿债能力", quick_ratio),
            metric_row("ebitda", "EBITDA", "净利润+所得税费用+利息费用+折旧摊销", "粗略估计企业经营现金盈利能力。", "", "盈利能力", ebitda_values),
            metric_row("free_cash_flow", "自由现金流量", "经营活动产生的现金净流量-资本性支出", "满足再投资后可供债权人、股东分配的现金流。", "", "现金流质量", fcf_values),
            metric_row("dividend_payout", "股利支付率（股息发放率）", "每股现金股利/每股收益；此处用现金股利总额/净利润近似", "净利润中股利分配的占比。", "%", "股东回报", dividend_payout, note="SEC companyfacts 对每股现金股利披露不稳定，本 demo 使用现金股利总额/净利润近似。"),
            metric_row("eps_basic", "每股收益", "归属于普通股股东的当期净利润/加权平均股数", "每股普通股享有的企业净利润。", "", "每股指标", [value_at(series, "eps_basic", periods, i) for i in range(len(periods))]),
            metric_row("eps_diluted", "稀释每股收益", "考虑潜在普通股摊薄后的每股收益", "考虑潜在普通股转换对 EPS 的影响。", "", "每股指标", [value_at(series, "eps_diluted", periods, i) for i in range(len(periods))]),
            metric_row("roce", "投资资本回报率（ROCE）", "息税前收益/资本总额；资本总额=非流动负债（有息负债）+所有者权益", "反映企业运用资本创造经营收益的能力。", "%", "盈利能力", roce, note="资本总额用有息债务平均余额+股东权益平均余额近似。"),
        ]
    )
    return rows


def make_dupont(ratios: list[dict[str, Any]], periods: list[str]) -> dict[str, Any]:
    lookup = {row["metric"]: row for row in ratios}
    net_margin = lookup.get("net_margin", {}).get("values", [])
    asset_turnover = lookup.get("asset_turnover", {}).get("values", [])
    equity_multiplier = lookup.get("equity_multiplier", {}).get("values", [])
    roe = lookup.get("roe", {}).get("values", [])
    dupont_roe = []
    for index in range(len(periods)):
        nm = net_margin[index] if index < len(net_margin) else None
        at = asset_turnover[index] if index < len(asset_turnover) else None
        em = equity_multiplier[index] if index < len(equity_multiplier) else None
        dupont_roe.append(None if nm is None or at is None or em is None else nm * at * em)
    return {
        "formula": "净资产收益率 = 销售净利率 × 总资产周转率 × 权益倍数",
        "periods": periods,
        "rows": [
            {"metric": "net_margin", "label": "销售净利率", "unit": "%", "values": net_margin},
            {"metric": "asset_turnover", "label": "总资产周转率", "unit": "x", "values": asset_turnover},
            {"metric": "equity_multiplier", "label": "权益倍数", "unit": "x", "values": equity_multiplier},
            {"metric": "dupont_roe", "label": "杜邦拆解 ROE", "unit": "%", "values": dupont_roe},
            {"metric": "roe", "label": "实际 ROE", "unit": "%", "values": roe},
        ],
    }


def make_analysis(cik: str, period: str) -> dict[str, Any]:
    company = get_company_by_cik(cik)
    if not company:
        raise ValueError("没有找到该公司")
    facts = get_company_facts(company["cik"])
    series = build_series(facts, period)
    periods = collect_periods(series)
    if not periods:
        raise ValueError("SEC 数据中没有可用的 10-K/10-Q 财务项目")
    ratios = make_ratios(series, periods)
    return {
        "company": company,
        "periodType": period,
        "periods": periods,
        "statements": {
            "income": make_statement(series, "income", periods),
            "balance": make_statement(series, "balance", periods),
            "cashflow": make_statement(series, "cashflow", periods),
        },
        "ratios": ratios,
        "dupont": make_dupont(ratios, periods),
        "trends": {
            key: {
                "label": METRIC_LABELS[key],
                "values": [value_for(series, key, period_name) for period_name in periods],
            }
            for key in [
                "revenue",
                "gross_profit",
                "net_income",
                "operating_cash_flow",
                "assets",
                "liabilities",
                "equity",
            ]
        },
        "source": {
            "companyFacts": SEC_FACTS_URL.format(cik=company["cik"]),
            "note": "数据来自 SEC EDGAR companyfacts API，按常见 US-GAAP 标签自动归集。",
        },
    }


def latest_value(rows: list[dict[str, Any]], metric: str) -> float | None:
    row = next((item for item in rows if item["metric"] == metric), None)
    if not row:
        return None
    for value in reversed(row["values"]):
        if value is not None:
            return value
    return None


def make_compare(cik_a: str, cik_b: str, period: str) -> dict[str, Any]:
    left = make_analysis(cik_a, period)
    right = make_analysis(cik_b, period)
    compare_rows = []
    right_lookup = {row["metric"]: row for row in right["ratios"]}
    for left_row in left["ratios"]:
        right_row = right_lookup.get(left_row["metric"])
        if not right_row:
            continue
        left_value = latest_non_null(left_row["values"]) if left_row else None
        right_value = latest_non_null(right_row["values"]) if right_row else None
        compare_rows.append(
            {
                "metric": left_row["metric"],
                "label": left_row["label"],
                "group": left_row.get("group", ""),
                "formula": left_row.get("formula", ""),
                "meaning": left_row.get("meaning", ""),
                "note": left_row.get("note", ""),
                "left": left_value,
                "right": right_value,
                "spread": None if left_value is None or right_value is None else left_value - right_value,
                "unit": left_row.get("unit") if left_row else None,
            }
        )
    return {
        "left": left["company"],
        "right": right["company"],
        "periodType": period,
        "leftLatestPeriod": left["periods"][-1],
        "rightLatestPeriod": right["periods"][-1],
        "rows": compare_rows,
    }


def latest_non_null(values: list[float | None]) -> float | None:
    for value in reversed(values):
        if value is not None:
            return value
    return None


class DemoHandler(SimpleHTTPRequestHandler):
    def translate_path(self, path: str) -> str:
        parsed = urllib.parse.urlparse(path)
        if parsed.path.startswith("/static/"):
            rel = parsed.path.replace("/static/", "", 1)
            return str(STATIC_DIR / rel)
        return str(STATIC_DIR / "index.html")

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path == "/api/search":
                params = urllib.parse.parse_qs(parsed.query)
                query = params.get("q", [""])[0]
                self.send_json({"results": search_companies(query)})
                return
            if parsed.path == "/api/analysis":
                params = urllib.parse.parse_qs(parsed.query)
                cik = params.get("cik", [""])[0]
                period = params.get("period", ["annual"])[0]
                if period not in {"annual", "quarterly"}:
                    period = "annual"
                self.send_json(make_analysis(cik, period))
                return
            if parsed.path == "/api/compare":
                params = urllib.parse.parse_qs(parsed.query)
                cik_a = params.get("a", [""])[0]
                cik_b = params.get("b", [""])[0]
                period = params.get("period", ["annual"])[0]
                if period not in {"annual", "quarterly"}:
                    period = "annual"
                self.send_json(make_compare(cik_a, cik_b, period))
                return
            return super().do_GET()
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    ensure_dirs()
    host = "127.0.0.1"
    port = int(os.environ.get("PORT", "8000"))
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"财报分析 demo 已启动：http://{host}:{port}")
    print("按 Ctrl+C 停止服务。")
    server.serve_forever()


if __name__ == "__main__":
    main()
