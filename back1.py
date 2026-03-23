"""
回测：标的 515180.SH（对应跟踪上证指数），近 5 年。

方案1：每月首个交易日按开盘价买入 3000 元。
方案2：每月首个交易日不买入标的，3000 元全部计入存储金；每日开盘若
       上证指数开盘价 / 昨日收盘 MA120 <= 0.94，则按开盘价用全部存储金买入（打日志）。

不依赖网页看板脚本；TuShare token 与环境变量约定同仓库 README。
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
import tushare as ts
from scipy.optimize import brentq
from tushare.stock import cons as ct

ROOT = Path(__file__).resolve().parent

ETF_CODE = "515180.SH"
INDEX_CODE = "000001.SH"
MA_PERIOD = 120
YEARS = 5
MONTHLY_TOTAL = 3000.0
S1_BUY = 3000.0
S2_MONTHLY_STORE = 3000.0
THRESHOLD_RATIO = 0.94


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


def load_data(pro) -> pd.DataFrame:
    end = date.today()
    start_bt = end - timedelta(days=int(365 * YEARS))
    data_start = start_bt - timedelta(days=400)

    start_s = data_start.strftime("%Y%m%d")
    end_s = end.strftime("%Y%m%d")

    idx = pro.index_daily(ts_code=INDEX_CODE, start_date=start_s, end_date=end_s)
    if idx is None or idx.empty:
        raise RuntimeError("未取到上证指数 index_daily")

    raw = pro.fund_daily(ts_code=ETF_CODE, start_date=start_s, end_date=end_s)
    if raw is None or raw.empty:
        raise RuntimeError("未取到 ETF fund_daily")

    fadj = pro.fund_adj(ts_code=ETF_CODE, start_date=start_s, end_date=end_s)
    etf = _qfq_fund_daily(raw, fadj if fadj is not None and not fadj.empty else None)

    idx = idx.sort_values("trade_date").copy()
    idx["trade_date"] = idx["trade_date"].astype(str)
    idx["idx_open"] = idx["open"].astype(float)
    idx["idx_close"] = idx["close"].astype(float)
    idx["ma120"] = idx["idx_close"].rolling(MA_PERIOD, min_periods=MA_PERIOD).mean()
    idx["ma120_prev"] = idx["ma120"].shift(1)

    etf = etf.sort_values("trade_date")
    m = pd.merge(
        etf[["trade_date", "open", "close"]],
        idx[["trade_date", "idx_open", "ma120_prev"]],
        on="trade_date",
        how="inner",
    )
    m = m.rename(columns={"open": "etf_open", "close": "etf_close"})
    m["trade_date"] = m["trade_date"].astype(str)

    if len(m) < MA_PERIOD + 5:
        raise RuntimeError("合并后交易日过少，请检查日期范围或权限")

    m["ym"] = pd.to_datetime(m["trade_date"], format="%Y%m%d").dt.to_period("M")
    m["first_in_month"] = m.groupby("ym", sort=False).cumcount() == 0

    start_bt_s = start_bt.strftime("%Y%m%d")
    eligible = m.index[
        (m["trade_date"] >= start_bt_s)
        & m["first_in_month"]
        & m["ma120_prev"].notna()
    ]
    if eligible.empty:
        raise RuntimeError("在目标起始日后找不到「每月首个交易日」样本，请扩大拉数区间")
    m = m.loc[eligible[0] :].reset_index(drop=True)

    return m


def _npv_monthly_irr_begin(
    monthly_pay: float, n_months: int, final_value: float, r: float
) -> float:
    """r 为月收益率；t=0..n-1 各月初投入 monthly_pay，t=n 末收回 final_value。"""
    s = sum(-monthly_pay / (1 + r) ** i for i in range(n_months))
    s += final_value / (1 + r) ** n_months
    return s


def monthly_irr_to_annual(monthly_pay: float, n_months: int, final_value: float) -> float:
    """等额月初定投 IRR，换算为年化收益率。"""
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


def run_scheme1(m: pd.DataFrame) -> tuple[float, float, float, int]:
    shares = 0.0
    total_in = 0.0
    n_months = 0
    for _, row in m.iterrows():
        if not row["first_in_month"]:
            continue
        n_months += 1
        px = float(row["etf_open"])
        if px <= 0:
            continue
        total_in += S1_BUY
        shares += S1_BUY / px

    last = m.iloc[-1]
    final = shares * float(last["etf_close"]) + 0.0
    profit = final - total_in
    ret = profit / total_in if total_in > 0 else float("nan")
    return final, total_in, ret, n_months


def run_scheme2(m: pd.DataFrame) -> tuple[float, float, float, int]:
    shares = 0.0
    stored = 0.0
    total_in = 0.0
    n_months = 0

    for _, row in m.iterrows():
        td = row["trade_date"]
        px = float(row["etf_open"])
        if px <= 0:
            continue

        if row["first_in_month"]:
            n_months += 1
            total_in += MONTHLY_TOTAL
            stored += S2_MONTHLY_STORE

        ma_prev = row["ma120_prev"]
        idx_open = float(row["idx_open"])
        if (
            pd.notna(ma_prev)
            and float(ma_prev) > 0
            and stored > 0
            and idx_open / float(ma_prev) <= THRESHOLD_RATIO
        ):
            ratio = idx_open / float(ma_prev)
            buy_amt = stored
            shares += buy_amt / px
            print(
                f"  [方案2] {td} 存储金买入 金额={buy_amt:.2f} 元 "
                f"指数开盘/昨日MA120={ratio:.6f} <= {THRESHOLD_RATIO} "
                f"ETF开盘={px:.4f}",
            )
            stored = 0.0

    last = m.iloc[-1]
    final = shares * float(last["etf_close"]) + stored
    profit = final - total_in
    ret = profit / total_in if total_in > 0 else float("nan")
    return final, total_in, ret, n_months


def main() -> int:
    token = resolve_token()
    if not token:
        print(
            "未找到 TuShare token：请设置 TUSHARE_TOKEN / TS_TOKEN，"
            "或在仓库根目录 readme.txt 首行使用「说明|token」格式。",
            file=sys.stderr,
        )
        return 1

    pro = ts.pro_api(token)
    m = load_data(pro)

    first_d, last_d = m.iloc[0]["trade_date"], m.iloc[-1]["trade_date"]
    days = (pd.to_datetime(last_d, format="%Y%m%d") - pd.to_datetime(first_d, format="%Y%m%d")).days
    years_span = days / 365.25 if days > 0 else float(YEARS)

    print(
        f"标的: {ETF_CODE}，指数: {INDEX_CODE}，区间: {first_d} ~ {last_d}（约 {years_span:.2f} 年）\n"
    )

    f1, inv1, r1, n1 = run_scheme1(m)
    ann1 = monthly_irr_to_annual(MONTHLY_TOTAL, n1, f1)

    print("【方案1】每月首个交易日开盘价买入 3000 元")
    print(f"  累计投入: {inv1:,.2f} 元（{n1} 个月）")
    print(f"  期末市值: {f1:,.2f} 元")
    print(f"  总收益: {f1 - inv1:,.2f} 元，收益率: {r1 * 100:.3f}%")
    print(f"  年化收益率（等额月末定投 IRR 年化）: {ann1 * 100:.3f}%\n")

    print(
        "【方案2】每月首个交易日不买标的，3000 元全部进存储金；"
        f"每日开盘若 指数开盘/昨日MA120<={THRESHOLD_RATIO} 则用全部存储金买入（见下方日志）"
    )
    f2, inv2, r2, n2 = run_scheme2(m)
    ann2 = monthly_irr_to_annual(MONTHLY_TOTAL, n2, f2)
    print(f"  累计投入: {inv2:,.2f} 元（{n2} 个月）")
    print(f"  期末市值（含剩余备用金）: {f2:,.2f} 元")
    print(f"  总收益: {f2 - inv2:,.2f} 元，收益率: {r2 * 100:.3f}%")
    print(f"  年化收益率（等额月末定投 IRR 年化）: {ann2 * 100:.3f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
