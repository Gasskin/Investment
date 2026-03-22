"""
查询指定 ETF 上一自然月的月线行情：开盘价、收盘价、涨跌幅。

TuShare 说明（实测）：
- pro.monthly / pro_bar(asset=E,freq=M) 对场内 ETF 常返回空行；pro_bar 带 adj='qfq' 时依赖
  adj_factor，ETF 无此数据会直接返回 None。
- 官方 ETF 日线为 fund_daily，复权因子为 fund_adj。此处用 fund_daily + fund_adj 做前复权后，
  按交易所月 K 惯例合成「上一自然月」：开盘=该月首个交易日开盘，收盘=最后交易日收盘，
  涨跌相对「上一自然月」最后复权收盘计算。

Token：zhishu.resolve_token()
"""

from __future__ import annotations

import sys
from calendar import monthrange
from datetime import date, timedelta
from typing import Any

import pandas as pd
import tushare as ts

from zhishu import resolve_token

ETF_POOL: list[tuple[str, str]] = [
    ("159941", "159941.SZ"),
    ("513500", "513500.SH"),
    ("513010", "513010.SH"),
    ("513630", "513630.SH"),
    ("513000", "513000.SH"),
    ("159530", "159530.SZ"),
    ("159929", "159929.SZ"),
]


def _shift_month(y: int, m: int, delta: int) -> tuple[int, int]:
    m += delta
    while m > 12:
        y += 1
        m -= 12
    while m < 1:
        y -= 1
        m += 12
    return y, m


def _prev_calendar_month(ref: date | None = None) -> tuple[int, int, str, str]:
    t = ref or date.today()
    first_this = t.replace(day=1)
    last_prev = first_this - timedelta(days=1)
    y, m = last_prev.year, last_prev.month
    _, last_day = monthrange(y, m)
    start_s = date(y, m, 1).strftime("%Y%m%d")
    end_s = date(y, m, last_day).strftime("%Y%m%d")
    return y, m, start_s, end_s


def _qfq_fund_daily(d: pd.DataFrame, adj: pd.DataFrame | None) -> pd.DataFrame:
    """前复权：价 * adj_factor / 区间内最新复权因子（保持窗口内最新价与不复权一致）。"""
    out = d.sort_values("trade_date").copy()
    out["trade_date"] = out["trade_date"].astype(str)
    if adj is None or adj.empty:
        return out
    a = adj.sort_values("trade_date").copy()
    a["trade_date"] = a["trade_date"].astype(str)
    latest = float(a["adj_factor"].iloc[-1])
    if latest == 0 or pd.isna(latest):
        return out
    out_dt = pd.to_datetime(out["trade_date"], format="%Y%m%d")
    a_dt = pd.to_datetime(a["trade_date"], format="%Y%m%d")
    left = out.assign(_td=out_dt).sort_values("_td")
    right = a.assign(_td=a_dt).sort_values("_td")[["_td", "adj_factor"]]
    merged = pd.merge_asof(left, right, on="_td", direction="backward")
    af = merged["adj_factor"].ffill().bfill()
    if af.isna().all():
        return out.drop(columns=["_td"], errors="ignore")
    ratio = af.astype(float) / latest
    for col in ("open", "high", "low", "close", "pre_close"):
        if col in merged.columns:
            merged[col] = merged[col].astype(float) * ratio
    return merged.drop(columns=["_td", "adj_factor"], errors="ignore")


def _aggregate_calendar_month(
    qfq: pd.DataFrame, y: int, m: int
) -> tuple[pd.Series | None, float | None]:
    """从已前复权的日线中取某一自然月的合成月 K；返回 (月内行聚合, 该月最后交易日收盘)。"""
    ym = f"{y:04d}{m:02d}"
    sub = qfq[qfq["trade_date"].astype(str).str.startswith(ym)].copy()
    if sub.empty:
        return None, None
    sub = sub.sort_values("trade_date")
    first = sub.iloc[0]
    last = sub.iloc[-1]
    month_close = float(last["close"])
    agg = pd.Series(
        {
            "trade_date": str(last["trade_date"]),
            "open": float(first["open"]),
            "close": month_close,
            "high": float(sub["high"].astype(float).max()),
            "low": float(sub["low"].astype(float).min()),
        }
    )
    return agg, month_close


def fetch_prev_month_bar(pro: Any, ts_code: str, prev_y: int, prev_m: int) -> pd.Series:
    """上一自然月月 K（前复权），涨跌幅相对再上一月末收盘。"""
    ppy, ppm = _shift_month(prev_y, prev_m, -1)
    range_start = date(ppy, ppm, 1).strftime("%Y%m%d")
    _, ld = monthrange(prev_y, prev_m)
    range_end = date(prev_y, prev_m, ld).strftime("%Y%m%d")

    adj_start = _shift_month(prev_y, prev_m, -24)
    adj_start_s = date(adj_start[0], adj_start[1], 1).strftime("%Y%m%d")

    raw = pro.fund_daily(ts_code=ts_code, start_date=range_start, end_date=range_end)
    if raw is None or raw.empty:
        raise RuntimeError("fund_daily 返回空")

    fadj = pro.fund_adj(ts_code=ts_code, start_date=adj_start_s, end_date=range_end)
    qfq = _qfq_fund_daily(raw, fadj if fadj is not None and not fadj.empty else None)

    prev_bar, prev_close_end = _aggregate_calendar_month(qfq, ppy, ppm)
    cur_bar, _ = _aggregate_calendar_month(qfq, prev_y, prev_m)
    if cur_bar is None:
        raise RuntimeError(f"无 {prev_y}-{prev_m:02d} 交易日数据")
    if prev_bar is None or prev_close_end is None or prev_close_end == 0:
        raise RuntimeError("无法取得再上一月末复权收盘，无法计算月涨跌幅")

    pct = (float(cur_bar["close"]) - prev_close_end) / prev_close_end * 100.0
    out = cur_bar.copy()
    out["pct_chg"] = pct
    return out


def main() -> int:
    token = resolve_token()
    if not token:
        print(
            "未找到 TuShare token（readme.txt / tk.csv / 环境变量），参见 zhishu.py 说明",
            file=sys.stderr,
        )
        return 1

    pro = ts.pro_api(token)
    prev_y, prev_m, m_start, m_end = _prev_calendar_month()

    print(
        f"上一自然月: {prev_y}-{prev_m:02d}（{m_start}～{m_end}）  "
        f"前复权(fund_adj) 由 fund_daily 合成月K\n"
    )
    print(f"{'代码':<8} {'ts_code':<12} {'trade_date':<10} {'open':>10} {'close':>10} {'pct_chg%':>10}")

    failed = False
    for short, ts_code in ETF_POOL:
        try:
            row = fetch_prev_month_bar(pro, ts_code, prev_y, prev_m)
            td = str(row["trade_date"])
            o = float(row["open"])
            c = float(row["close"])
            pct = float(row["pct_chg"])
            print(f"{short:<8} {ts_code:<12} {td:<10} {o:>10.4f} {c:>10.4f} {pct:>10.2f}")
        except Exception as e:
            failed = True
            print(f"{short:<8} {ts_code:<12} {'-':<10} {'-':>10} {'-':>10} {'-':>10}")
            print(f"  -> {ts_code}: {e}", file=sys.stderr)

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
