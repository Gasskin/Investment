"""
回测：六只 ETF 轮动。

每月首个交易日（六只均有行情的交集日历上），根据各标的「上一自然月」
前复权月收盘涨跌幅，选出月涨幅最大的一只，当日按开盘价买入 1000 元。

标的：159941、513500、513010、513630、159530、159929（TuShare ts_code 带 .SZ/.SH）。

不依赖网页看板与其它回测脚本；token 约定同仓库 README。
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import tushare as ts
from scipy.optimize import brentq
from tushare.stock import cons as ct

ROOT = Path(__file__).resolve().parent

POOL: list[tuple[str, str]] = [
    ("159941", "159941.SZ"),
    ("513500", "513500.SH"),
    ("513010", "513010.SH"),
    ("513630", "513630.SH"),
    ("159530", "159530.SZ"),
    ("159929", "159929.SZ"),
]

YEARS = 5
MONTHLY_BUY = 1000.0


def _token_from_env() -> str:
    for key in ("TUSHARE_TOKEN", "TS_TOKEN"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    return ""


def _token_from_readme() -> str:
    readme = ROOT / "readme.txt"
    if not readme.is_file():
        return ""
    text = readme.read_text(encoding="utf-8", errors="replace")
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if "|" in s:
            t = s.split("|", 1)[1].strip()
            if t:
                return t
    return ""


def _token_from_tushare_home() -> str:
    fp = Path.home() / ct.TOKEN_F_P
    if not fp.is_file():
        return ""
    try:
        df = pd.read_csv(fp)
        return str(df.loc[0]["token"]).strip()
    except Exception:
        return ""


def resolve_token() -> str:
    return _token_from_env() or _token_from_readme() or _token_from_tushare_home()


def _qfq_fund_daily(d: pd.DataFrame, adj: pd.DataFrame | None) -> pd.DataFrame:
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
        return merged.drop(columns=["_td", "adj_factor"], errors="ignore")
    ratio = af.astype(float) / latest
    for col in ("open", "high", "low", "close", "pre_close"):
        if col in merged.columns:
            merged[col] = merged[col].astype(float) * ratio
    return merged.drop(columns=["_td", "adj_factor"], errors="ignore")


def fetch_qfq_ohlc(pro, ts_code: str, start_s: str, end_s: str) -> pd.DataFrame:
    raw = pro.fund_daily(ts_code=ts_code, start_date=start_s, end_date=end_s)
    if raw is None or raw.empty:
        raise RuntimeError(f"fund_daily 为空: {ts_code}")
    fadj = pro.fund_adj(ts_code=ts_code, start_date=start_s, end_date=end_s)
    qfq = _qfq_fund_daily(raw, fadj if fadj is not None and not fadj.empty else None)
    return qfq.sort_values("trade_date").reset_index(drop=True)


def monthly_close_and_return(qfq: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """自然月末前复权收盘、相对上一自然月的涨跌幅。"""
    q = qfq.copy()
    q["_ym"] = pd.to_datetime(q["trade_date"], format="%Y%m%d").dt.to_period("M")
    month_close = q.groupby("_ym", sort=True)["close"].last()
    month_ret = month_close.pct_change()
    return month_close, month_ret


def _npv_monthly_irr_begin(
    monthly_pay: float, n_months: int, final_value: float, r: float
) -> float:
    s = sum(-monthly_pay / (1 + r) ** i for i in range(n_months))
    s += final_value / (1 + r) ** n_months
    return s


def monthly_irr_to_annual(monthly_pay: float, n_months: int, final_value: float) -> float:
    if n_months <= 0 or monthly_pay <= 0:
        return float("nan")
    lo, hi = -0.9999, 10.0
    try:
        r_m = brentq(
            lambda r: _npv_monthly_irr_begin(monthly_pay, n_months, final_value, r),
            lo,
            hi,
        )
    except ValueError:
        return float("nan")
    return (1 + r_m) ** 12 - 1


def main() -> int:
    token = resolve_token()
    if not token:
        print(
            "未找到 TuShare token：请设置 TUSHARE_TOKEN / TS_TOKEN，"
            "或在仓库根目录 readme.txt 首行使用「说明|token」格式。",
            file=sys.stderr,
        )
        return 1

    end = date.today()
    start_bt = end - timedelta(days=int(365 * YEARS))
    data_start = start_bt - timedelta(days=120)
    start_s = data_start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")

    pro = ts.pro_api(token)

    by_code: dict[str, pd.DataFrame] = {}
    month_ret_by_code: dict[str, pd.Series] = {}
    date_sets: list[set[str]] = []

    for short, ts_code in POOL:
        qfq = fetch_qfq_ohlc(pro, ts_code, start_s, end_s)
        qfq["short"] = short
        by_code[ts_code] = qfq
        _, mret = monthly_close_and_return(qfq)
        month_ret_by_code[ts_code] = mret
        date_sets.append(set(qfq["trade_date"].astype(str)))

    common_dates = sorted(set.intersection(*date_sets))
    if len(common_dates) < 50:
        raise RuntimeError("六只 ETF 共同交易日过少")

    cal = pd.DataFrame({"trade_date": common_dates})
    cal["ym"] = pd.to_datetime(cal["trade_date"], format="%Y%m%d").dt.to_period("M")
    cal["first_in_month"] = cal.groupby("ym", sort=False).cumcount() == 0

    start_bt_s = start_bt.strftime("%Y%m%d")
    eligible = cal.index[
        (cal["trade_date"] >= start_bt_s) & cal["first_in_month"]
    ]
    if eligible.empty:
        raise RuntimeError("起始日后无「每月首个共同交易日」")

    positions: dict[str, float] = defaultdict(float)
    total_in = 0.0
    n_months = 0
    idx_by_code = {c: df.set_index("trade_date") for c, df in by_code.items()}

    for i in eligible:
        td = cal.at[i, "trade_date"]
        cur_p = pd.to_datetime(td, format="%Y%m%d").to_period("M")
        prev_p = cur_p - 1

        scores: list[tuple[str, str, str, float]] = []
        for short, ts_code in POOL:
            sret = month_ret_by_code[ts_code]
            if prev_p not in sret.index:
                continue
            r = float(sret.loc[prev_p])
            if pd.isna(r):
                continue
            scores.append((short, ts_code, td, r))

        if len(scores) < len(POOL):
            print(
                f"  [跳过] {td} 上月={prev_p} 部分标的无月涨幅，不参与本月",
                file=sys.stderr,
            )
            continue

        winner_short, winner_code, _, win_r = max(scores, key=lambda x: x[3])
        row = idx_by_code[winner_code].loc[td]
        px = float(row["open"])
        if px <= 0:
            print(f"  [跳过] {td} {winner_code} 开盘价无效", file=sys.stderr)
            continue

        total_in += MONTHLY_BUY
        n_months += 1
        positions[winner_code] += MONTHLY_BUY / px
        print(
            f"  {td} 上月={prev_p} 选中 {winner_short}({winner_code}) "
            f"上月涨跌幅={win_r * 100:.3f}% 开盘价买入 {MONTHLY_BUY:.0f} 元"
        )

    last_td = common_dates[-1]
    final = 0.0
    for ts_code, sh in positions.items():
        if sh <= 0:
            continue
        lc = float(idx_by_code[ts_code].loc[last_td, "close"])
        final += sh * lc

    profit = final - total_in
    ret = profit / total_in if total_in > 0 else float("nan")
    ann = monthly_irr_to_annual(MONTHLY_BUY, n_months, final)

    print(f"\n标的池: {[s for s, _ in POOL]}")
    print(f"共同交易日区间: {common_dates[0]} ~ {common_dates[-1]}")
    print(f"有效定投月数: {n_months}")
    print(f"累计投入: {total_in:,.2f} 元")
    print(f"期末市值（按最后共同交易日收盘前复权）: {final:,.2f} 元")
    print(f"总收益: {profit:,.2f} 元，收益率: {ret * 100:.3f}%")
    print(f"年化收益率（月初等额 IRR 年化）: {ann * 100:.3f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
