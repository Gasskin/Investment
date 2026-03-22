import "./style.css";

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function fmt4(v) {
  if (v === null || v === undefined || Number.isNaN(Number(v))) return "—";
  return Number(v).toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 4,
  });
}

/** 相对 MA120：(收盘/MA120 − 1) × 100% */
function fmtDevPct(close, ma) {
  const c = Number(close);
  const m = Number(ma);
  if (!Number.isFinite(c) || !Number.isFinite(m) || m === 0) return "—";
  const pct = (c / m - 1) * 100;
  const s = pct.toLocaleString("zh-CN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
    signDisplay: "exceptZero",
  });
  return `${s}%`;
}

function fmtYmd8(s) {
  const x = String(s).replace(/\D/g, "");
  if (x.length !== 8) return String(s);
  return `${x.slice(0, 4)}-${x.slice(4, 6)}-${x.slice(6, 8)}`;
}

/** 各指数 trade_date（多为 YYYYMMDD）中取最晚一天 */
function latestIndexTradeDate(indices) {
  const raw = (indices || []).map((r) => String(r.trade_date ?? "").replace(/\D/g, ""));
  const ok = raw.filter((d) => d.length === 8);
  if (!ok.length) return "";
  ok.sort();
  return ok[ok.length - 1];
}

async function main() {
  const meta = document.getElementById("meta");
  const metaBar = document.getElementById("meta-bar");
  const errEl = document.getElementById("err");
  const tblI = document.querySelector("#tbl-indices tbody");
  const tblE = document.querySelector("#tbl-etfs tbody");
  const etfSub = document.getElementById("etf-sub");

  errEl.hidden = true;
  errEl.textContent = "";

  const url = new URL("snapshot.json", window.location.href);

  try {
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    if (data.generated_at) {
      meta.textContent = `快照生成（北京时间）：${data.generated_at}`;
    } else {
      meta.textContent = "已加载";
    }

    const bar = latestIndexTradeDate(data.indices);
    if (bar && metaBar) {
      metaBar.textContent = `指数日线对应交易日：${fmtYmd8(bar)}（各市场最后交易日可能不同，见上表）`;
      metaBar.hidden = false;
    } else if (metaBar) {
      metaBar.hidden = true;
    }

    if (!data.ok) {
      const parts = [];
      if (data.error) parts.push(data.error);
      if (data.errors?.length) parts.push(data.errors.join("；"));
      if (parts.length) {
        errEl.textContent = parts.join(" ");
        errEl.hidden = false;
      }
    }

    tblI.innerHTML = (data.indices || [])
      .map(
        (r) =>
          `<tr><td>${escapeHtml(r.name)}</td><td class="num">${fmt4(r.close)}</td><td class="num">${fmt4(r.ma120)}</td><td class="num">${fmtDevPct(r.close, r.ma120)}</td></tr>`,
      )
      .join("");

    const ep = data.etfs || {};
    if (ep.period_label) {
      etfSub.textContent = `自然月 ${ep.period_label}${ep.range ? `（${ep.range}）` : ""} · 前复权 · 按涨跌幅降序`;
    }

    const rows = [...(ep.rows || [])].sort(
      (a, b) => Number(b.pct_chg) - Number(a.pct_chg),
    );

    tblE.innerHTML = rows
      .map((r) => {
        const cn = r.csname ? escapeHtml(r.csname) : "—";
        return `<tr><td>${escapeHtml(r.short)}</td><td>${cn}</td><td class="mono">${escapeHtml(r.ts_code)}</td><td class="num">${fmt4(r.open)}</td><td class="num">${fmt4(r.close)}</td><td class="num">${fmt4(r.pct_chg)}</td></tr>`;
      })
      .join("");
  } catch {
    if (metaBar) metaBar.hidden = true;
    meta.textContent = "无 snapshot.json";
    errEl.textContent =
      "请运行：python scripts/build_snapshot.py，再 npm run dev / npm run build。";
    errEl.hidden = false;
    tblI.innerHTML = "";
    tblE.innerHTML = "";
  }
}

main();
