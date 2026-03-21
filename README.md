# Investment（TuShare 数据小工具）

## 你必须遵守的规则（项目约定）

以下为对实现的**硬性要求**，与 `readme.txt` 中第 1、2 条一致：

1. **数据源**  
   只允许通过 **TuShare Pro 提供的 API** 获取数据。若 TuShare **没有**对应能力的接口（或接口对某类标的不可用），须**明确报错或说明原因**，不得用其他数据源凑数。

2. **周期与口径**  
   在 TuShare **已经提供目标周期数据**的前提下，必须通过**该周期接口**取数。  
   **反例**：若要**月 K 涨跌幅**，应使用**月线级**接口得到月收盘等，再计算或读取官方字段；**不得**用 30 根日线自行「拼一个月」来替代月线接口。  
   **允许**：在**没有**官方月线（或官方接口对标的返回空）时，在文档中说明限制后，用**官方日线 + 官方复权因子**按交易所月 K 惯例合成（见下文 ETF 说明）。

3. **价格复权**  
   涉及**需要复权**的证券行情时，采用**前复权（qfq）**。  
   **注意**：主要指数的 `index_daily` / `index_global` 为**指数点位**，不适用股票/ETF 的 qfq/hfq 概念。

## 实现上的约定（实践中发现应这样做）

### Token

- `zhishu.py`、`etfPool.py` 通过 `resolve_token()` 按顺序读取：  
  环境变量 `TUSHARE_TOKEN` 或 `TS_TOKEN` → 与本脚本同目录的 **`readme.txt`**（首条非空行，支持 `说明|token`，取竖线右侧）→ 用户目录下 TuShare 默认 **`tk.csv`**（`ts.set_token` 写入）。
- **不要把含 token 的 `readme.txt` 提交到公开仓库**；更稳妥是使用 `ts.set_token` 或仅本地环境变量。

### 指数脚本 `zhishu.py`

- **上证**：`ts.pro_bar(asset='I', freq='D', ma=[120])`，底层为 `index_daily`；MA120 使用 SDK 对收盘的均线计算。  
- **恒生、标普**：`pro_bar` **未**接入 `index_global`，使用 **`pro.index_global`**（代码 `HSI`、`SPX`，与[官方国际指数表](https://tushare.pro/document/2?doc_id=211)一致）；MA120 对返回日线做 rolling。  
- **权限**：`index_global` 通常需较高积分（文档常见为约 **6000+**）；`index_daily` 约 **2000+**（以 TuShare 官网为准）。

### ETF 脚本 `etfPool.py`

- **现象**：`pro.monthly` 对场内 ETF 常返回**空表**；`pro_bar(..., adj='qfq')` 依赖 **`adj_factor`**，ETF 无此数据时 SDK 会直接 **`return None`**。ETF 复权应使用 **`fund_adj`**。  
- **做法**：用官方 **`fund_daily`** + **`fund_adj`** 做前复权后，按**自然月**合成「上一自然月」月 K（首交易日开盘、末交易日收盘、月内高低），月涨跌幅相对**再上一月**末复权收盘计算。  
- **权限**：`fund_daily` / `fund_adj` 常见为 **5000+** 积分（见 `readme_api.txt` 与官网）。

### 参考文档

- 项目内 **`readme_api.txt`**：常用接口速查与积分档摘要。  
- TuShare 官方：<https://tushare.pro/document/2>

## 运行

```bash
pip install tushare pandas
python zhishu.py    # 上证 / 恒生 / 标普：最新收盘与 MA120
python etfPool.py   # 指定 ETF 池：上一自然月月 K（前复权）及月涨跌幅
```

## 可视化说明页（GitHub Pages）

- 源码在 `web/`，Vite + Chart.js；`npm run build` 输出到 `docs/`。
- **定时拉数 + 重构网页**：可用 **GitHub Actions**（`.github/workflows/pages.yml`）。
  - 仓库 **Settings → Secrets and variables → Actions** 新建 **`TUSHARE_TOKEN`**（值同 TuShare Pro token，勿写入代码）。
  - **Settings → Pages → Build and deployment**：**Source** 选 **GitHub Actions**（不要与「从分支部署 /docs」混用）。
  - 工作流：`pip install -r requirements.txt` → `python scripts/build_snapshot.py`（写入 `web/public/snapshot.json`）→ `npm ci` && `npm run build` → 上传 `docs/` 并发布。
  - **schedule**：默认每天 02:15 UTC，可在 workflow 里改 `cron`；另支持 `push` 到 `main`/`master`（限定路径）与 **workflow_dispatch** 手动运行。
  - 快照步骤带 **`continue-on-error: true`**：未配 Secret 时仍会尝试构建静态页（页面会提示缺 token）；配好 Secret 后即可正常拉数。
- **仅手动发布**：本机执行 `python scripts/build_snapshot.py`（需 token）后 `npm run build`，将 `docs/` 推送到仓库，Pages 选分支 + 文件夹 **`/docs`**。
- 线上页面通过 `snapshot.json` 展示行情表；**json 内无 token**，仅含行情字段。

## 脚本与标的列表

| 脚本        | 作用 |
|-------------|------|
| `zhishu.py` | 上证指数、恒生指数、标普500：最新价与 MA120 |
| `etfPool.py` | ETF：`159941`、`513500`、`513010`、`513630`、`159530`、`159929`（`ts_code` 分别为 `.SZ` / `.SH`） |
| `scripts/build_snapshot.py` | 聚合上述逻辑，生成 `web/public/snapshot.json` 供静态页展示（CI / 本机均可） |

---

*若 TuShare 接口或积分策略变更，以官网文档为准；本 README 记录的是当前实现所依据的约定与踩坑结论。*
