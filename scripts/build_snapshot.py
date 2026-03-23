"""
为静态站点生成 web/public/snapshot.json（供 GitHub Actions 或本机构建前执行）。

依赖环境变量 TUSHARE_TOKEN（或 TS_TOKEN）；CI 中应使用仓库 Secret，勿提交 token。
"""

from __future__ import annotations

import json
import os
import sys
from calendar import monthrange
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import tushare as ts
from tushare.stock import cons as ct

ROOT = Path(__file__).resolve().parent.parent

MA_PERIOD = 120
START_LOOKBACK_DAYS = 400

ETF_POOL: list[tuple[str, str]] = [
    ("159941", "159941.SZ"),
    ("513500", "513500.SH"),
    ("513010", "513010.SH"),
    ("513630", "513630.SH"),
    ("159530", "159530.SZ"),
    ("159929", "159929.SZ"),
]


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


def _start_date_str() -> str:
    d = datetime.now().date() - timedelta(days=START_LOOKBACK_DAYS)
    return d.strftime("%Y%m%d")


def _end_date_str() -> str:
    return datetime.now().date().strftime("%Y%m%d")


def fetch_shanghai_pro_bar(pro, start_date: str, end_date: str) -> pd.DataFrame:
    df = ts.pro_bar(
        ts_code="000001.SH",
        asset="I",
        freq="D",
        start_date=start_date,
        end_date=end_date,
        ma=[MA_PERIOD],
        api=pro,
    )
    if df is None or df.empty:
        raise RuntimeError("未取到上证指数数据（pro_bar asset=I）")
    return df


def fetch_global_daily(pro, ts_code: str, start_date: str) -> pd.DataFrame:
    df = pro.index_global(ts_code=ts_code, start_date=start_date)
    if df is None or df.empty:
        raise RuntimeError(
            f"未取到数据: {ts_code}（index_global），请检查代码、日期范围或积分权限"
        )
    return df


def latest_close_and_ma120_from_pro_bar(df: pd.DataFrame) -> tuple[str, float, float]:
    col = f"ma{MA_PERIOD}"
    if col not in df.columns:
        raise RuntimeError(f"pro_bar 结果中无 {col}，请确认 ma=[{MA_PERIOD}]")
    work = df.copy()
    work["_td"] = work["trade_date"].astype(str)
    last = work.loc[work["_td"].idxmax()]
    trade_date = str(last["trade_date"])
    close = float(last["close"])
    ma120 = float(last[col]) if pd.notna(last[col]) else float("nan")
    if pd.isna(ma120):
        raise RuntimeError("MA120 无效（历史可能不足或首条为 NaN），请扩大 start_date")
    return trade_date, close, ma120


def latest_close_and_ma120_rolling(df: pd.DataFrame) -> tuple[str, float, float]:
    work = df.sort_values("trade_date").copy()
    work["trade_date"] = work["trade_date"].astype(str)
    if len(work) < MA_PERIOD:
        raise RuntimeError(f"历史不足 {MA_PERIOD} 条，当前 {len(work)} 条")
    work["ma120"] = work["close"].astype(float).rolling(
        window=MA_PERIOD, min_periods=MA_PERIOD
    ).mean()
    last = work.iloc[-1]
    trade_date = str(last["trade_date"])
    close = float(last["close"])
    ma120 = float(last["ma120"])
    if pd.isna(ma120):
        raise RuntimeError("MA120 无效")
    return trade_date, close, ma120


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


def _beijing_iso() -> str:
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def _etf_csname_by_code(pro, ts_codes: list[str]) -> dict[str, str]:
    want = set(ts_codes)
    out = {c: "" for c in ts_codes}
    try:
        df = pro.etf_basic(list_status="L", fields="ts_code,csname")
        if df is None or df.empty:
            return out
        for _, r in df.iterrows():
            tc = str(r["ts_code"]).strip()
            if tc in want:
                out[tc] = str(r.get("csname") or "").strip()
    except Exception as e:
        print(f"etf_basic 拉取简称失败（可忽略）：{e}", file=sys.stderr)
    return out


def main() -> int:
    out_path = ROOT / "web" / "public" / "snapshot.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    token = resolve_token()
    if not token:
        payload = {
            "ok": False,
            "generated_at": _beijing_iso(),
            "error": "未配置 TUSHARE_TOKEN（或 TS_TOKEN），请在 CI Secrets 或本机环境中设置。",
            "indices": [],
            "etfs": {"period_label": "", "rows": []},
        }
        out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print("已写入占位 snapshot.json（无 token）", file=sys.stderr)
        return 1

    pro = ts.pro_api(token)
    start_date = _start_date_str()
    end_date = _end_date_str()

    indices: list[dict] = []
    index_errors: list[str] = []

    try:
        df_sz = fetch_shanghai_pro_bar(pro, start_date, end_date)
        t, close, ma120 = latest_close_and_ma120_from_pro_bar(df_sz)
        indices.append(
            {
                "name": "上证指数",
                "code": "000001.SH",
                "trade_date": t,
                "close": round(close, 4),
                "ma120": round(ma120, 4),
            }
        )
    except Exception as e:
        index_errors.append(f"上证指数: {e}")

    for name, code in [("恒生指数", "HSI"), ("标普500", "SPX")]:
        try:
            df = fetch_global_daily(pro, code, start_date)
            t, close, ma120 = latest_close_and_ma120_rolling(df)
            indices.append(
                {
                    "name": name,
                    "code": code,
                    "trade_date": t,
                    "close": round(close, 4),
                    "ma120": round(ma120, 4),
                }
            )
        except Exception as e:
            index_errors.append(f"{name} ({code}): {e}")

    prev_y, prev_m, m_start, m_end = _prev_calendar_month()
    period_label = f"{prev_y}-{prev_m:02d}"
    pool_codes = [c for _, c in ETF_POOL]
    csname_map = _etf_csname_by_code(pro, pool_codes)

    etf_rows: list[dict] = []
    etf_errors: list[str] = []

    for short, ts_code in ETF_POOL:
        try:
            row = fetch_prev_month_bar(pro, ts_code, prev_y, prev_m)
            etf_rows.append(
                {
                    "short": short,
                    "ts_code": ts_code,
                    "csname": csname_map.get(ts_code, ""),
                    "trade_date": str(row["trade_date"]),
                    "open": round(float(row["open"]), 4),
                    "close": round(float(row["close"]), 4),
                    "pct_chg": round(float(row["pct_chg"]), 2),
                }
            )
        except Exception as e:
            etf_errors.append(f"{short} ({ts_code}): {e}")

    etf_rows.sort(key=lambda r: r["pct_chg"], reverse=True)

    ok = not index_errors and not etf_errors and len(indices) == 3 and len(etf_rows) == len(
        ETF_POOL
    )

    payload = {
        "ok": ok,
        "generated_at": _beijing_iso(),
        "indices": indices,
        "etfs": {
            "period_label": period_label,
            "range": f"{m_start}～{m_end}",
            "rows": etf_rows,
            "sorted_by": "pct_chg_desc",
        },
        "errors": index_errors + etf_errors,
    }

    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写入 {out_path.relative_to(ROOT)}，ok={ok}，indices={len(indices)}，etfs={len(etf_rows)}")
    if payload["errors"]:
        for err in payload["errors"]:
            print(err, file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
