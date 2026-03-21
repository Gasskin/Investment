"""
查询上证指数、恒生指数、标普500的最新收盘价及 MA120。

- 上证指数：官方通用行情 ts.pro_bar(asset='I')，底层等同 index_daily；MA120 通过 ma=[120]
  由 SDK 按文档「动态计算」（与直接调 index_daily 再 rolling 等价）。
- 恒生、标普：pro_bar 未接入 index_global（仅沪深指数走 asset='I'），故仍用 pro.index_global。

Token 读取顺序（无需必须设环境变量）：
1) 环境变量 TUSHARE_TOKEN 或 TS_TOKEN（若已设则优先）
2) 与本脚本同目录的 readme.txt：首条非空行，支持「说明|token」取竖线右侧
3) 用户目录下 TuShare 默认凭证 tk.csv（与 ts.set_token 相同）

权限：index_daily / pro_bar 指数日线约 2000+；index_global 约 6000+。
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import tushare as ts
from tushare.stock import cons as ct

MA_PERIOD = 120
START_LOOKBACK_DAYS = 400


def _token_from_env() -> str:
    for key in ("TUSHARE_TOKEN", "TS_TOKEN"):
        v = os.environ.get(key, "").strip()
        if v:
            return v
    return ""


def _token_from_readme() -> str:
    readme = Path(__file__).resolve().parent / "readme.txt"
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
    """使用 pro_bar 返回的 ma{N} 列；勿对 DataFrame 按日期重排，否则会与 SDK 均线错位。"""
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


def main() -> int:
    token = resolve_token()
    if not token:
        print(
            "未找到 TuShare token：请在 readme.txt 首行写入「说明|你的token」，"
            "或在 Python 中执行 import tushare as ts; ts.set_token('...')，或设置环境变量 TUSHARE_TOKEN",
            file=sys.stderr,
        )
        return 1

    pro = ts.pro_api(token)
    start_date = _start_date_str()
    end_date = _end_date_str()

    rows: list[tuple[str, str, str, float, float]] = []

    try:
        df_sz = fetch_shanghai_pro_bar(pro, start_date, end_date)
        t, close, ma120 = latest_close_and_ma120_from_pro_bar(df_sz)
        rows.append(("上证指数", "000001.SH", t, close, ma120))
    except Exception as e:
        print(f"[失败] 上证指数: {e}", file=sys.stderr)
        return 1

    for name, code in [("恒生指数", "HSI"), ("标普500", "SPX")]:
        try:
            df = fetch_global_daily(pro, code, start_date)
            t, close, ma120 = latest_close_and_ma120_rolling(df)
            rows.append((name, code, t, close, ma120))
        except Exception as e:
            print(f"[失败] {name} ({code}): {e}", file=sys.stderr)
            return 1

    print(f"{'指数':<10} {'代码':<12} {'交易日':<10} {'收盘':>12} {'MA120':>12}")
    for name, code, t, close, ma120 in rows:
        print(f"{name:<10} {code:<12} {t:<10} {close:>12.2f} {ma120:>12.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
