"""
为静态站点生成 web/public/snapshot.json（供 GitHub Actions 或本机构建前执行）。

依赖环境变量 TUSHARE_TOKEN（或 TS_TOKEN）；CI 中应使用仓库 Secret，勿提交 token。
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tushare as ts

import etfPool
import zhishu


def _beijing_iso() -> str:
    """快照生成时间，固定为 Asia/Shanghai（北京时间）ISO 字符串。"""
    return datetime.now(ZoneInfo("Asia/Shanghai")).isoformat(timespec="seconds")


def _etf_csname_by_code(pro, ts_codes: list[str]) -> dict[str, str]:
    """TuShare etf_basic 字段 csname 为中文简称；需积分以官网为准。"""
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

    token = zhishu.resolve_token()
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
    start_date = zhishu._start_date_str()
    end_date = zhishu._end_date_str()

    indices: list[dict] = []
    index_errors: list[str] = []

    try:
        df_sz = zhishu.fetch_shanghai_pro_bar(pro, start_date, end_date)
        t, close, ma120 = zhishu.latest_close_and_ma120_from_pro_bar(df_sz)
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

    for name, code in [("恒生指数", "HSI"), ("标普500", "SPX"), ("日经225", "N225")]:
        try:
            df = zhishu.fetch_global_daily(pro, code, start_date)
            t, close, ma120 = zhishu.latest_close_and_ma120_rolling(df)
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

    prev_y, prev_m, m_start, m_end = etfPool._prev_calendar_month()
    period_label = f"{prev_y}-{prev_m:02d}"
    pool_codes = [c for _, c in etfPool.ETF_POOL]
    csname_map = _etf_csname_by_code(pro, pool_codes)

    etf_rows: list[dict] = []
    etf_errors: list[str] = []

    for short, ts_code in etfPool.ETF_POOL:
        try:
            row = etfPool.fetch_prev_month_bar(pro, ts_code, prev_y, prev_m)
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

    ok = not index_errors and not etf_errors and len(indices) == 4 and len(etf_rows) == len(
        etfPool.ETF_POOL
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
