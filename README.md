# Investment（TuShare 数据小工具）

## 你必须遵守的规则（项目约定）

以下为对实现的**硬性要求**，与 `readme.txt` 中第 1、2 条一致（若仓库中保留该文件）：

1. **数据源**  
   只允许通过 **TuShare Pro 提供的 API** 获取数据。若 TuShare **没有**对应能力的接口（或接口对某类标的不可用），须**明确报错或说明原因**，不得用其他数据源凑数。

2. **周期与口径**  
   在 TuShare **已经提供目标周期数据**的前提下，必须通过**该周期接口**取数。  
   **反例**：若要**月 K 涨跌幅**，应使用**月线级**接口得到月收盘等，再计算或读取官方字段；**不得**用 30 根日线自行「拼一个月」来替代月线接口。  
   **允许**：在**没有**官方月线（或官方接口对标的返回空）时，在文档中说明限制后，用**官方日线 + 官方复权因子**按交易所月 K 惯例合成（见下文 ETF 说明）。

3. **价格复权**  
   涉及**需要复权**的证券行情时，采用**前复权（qfq）**。  
   **注意**：主要指数的 `index_daily` / `index_global` 为**指数点位**，不适用股票/ETF 的 qfq/hfq 概念。

4. **网页看板与回测脚本的依赖（架构边界）**  
   - **网页看板相关脚本**（如生成 `snapshot.json` 的拉数脚本、`web/` 前端构建所依赖的 Python 等）**不得**依赖任何**回测**相关脚本。  
   - **回测脚本之间不得互相依赖**：每种回测策略/实验对应**独立**可运行的脚本（或独立入口），**禁止** A 回测 import B 回测的业务逻辑。  
   - **允许**将重复逻辑抽到**通用工具或基类**（例如公共的数据加载、时间对齐、绩效指标计算等），由看板脚本与各回测脚本分别按需引用；通用层本身不应绑定某一回测或看板的专属业务。

## 实现上的约定（实践中发现应这样做）

### Token（`scripts/build_snapshot.py`）

- `resolve_token()` 按顺序读取：环境变量 `TUSHARE_TOKEN` 或 `TS_TOKEN` → 仓库根目录 **`readme.txt`**（首条非空行，支持 `说明|token`，取竖线右侧）→ 用户目录下 TuShare 默认 **`tk.csv`**（`ts.set_token` 写入）。
- **不要把含 token 的文件提交到公开仓库**；CI 使用仓库 Secret **`TUSHARE_TOKEN`**，本机优先环境变量。

### 指数与 ETF（快照脚本内实现）

- **指数（上证、恒生、标普500）**：上证用 `ts.pro_bar(asset='I', freq='D', ma=[120])`；国际指数用 **`pro.index_global`**（`HSI`、`SPX`）；权限以 TuShare 官网为准。  
- **ETF 池**：`fund_daily` + `fund_adj` 前复权后按自然月合成上一月月 K，涨跌幅相对再上一月末收盘；列表见 `scripts/build_snapshot.py` 中 `ETF_POOL`。

### 参考文档

- TuShare 官方：<https://tushare.pro/document/2>

## 运行

```bash
pip install -r requirements.txt
python scripts/build_snapshot.py   # 生成 web/public/snapshot.json
```

## 可视化说明页（GitHub Pages）

- 源码在 `web/`，Vite + Chart.js；`npm run build` 输出到 `docs/`。
- **定时拉数 + 重构网页**：可用 **GitHub Actions**（`.github/workflows/pages.yml`）。
  - 仓库 **Settings → Secrets and variables → Actions** 新建 **`TUSHARE_TOKEN`**（值同 TuShare Pro token，勿写入代码）。
  - **Settings → Pages → Build and deployment**：**Source** 选 **GitHub Actions**（不要与「从分支部署 /docs」混用）。
  - 工作流：`pip install -r requirements.txt` → `python scripts/build_snapshot.py`（写入 `web/public/snapshot.json`）→ `npm ci` && `npm run build` → 上传 `docs/` 并发布。
  - **schedule**：默认每天 **北京时间 08:00**（workflow 内为 UTC `0 0 * * *`）；可在 `.github/workflows/pages.yml` 修改 `cron`；另支持 `push` 与 **workflow_dispatch** 手动运行。
  - 快照步骤带 **`continue-on-error: true`**：未配 Secret 时仍会尝试构建静态页（页面会提示缺 token）；配好 Secret 后即可正常拉数。
- **仅手动发布**：本机执行 `python scripts/build_snapshot.py`（需 token）后 `npm run build`，将 `docs/` 推送到仓库，Pages 选分支 + 文件夹 **`/docs`**。
- 线上页面通过 `snapshot.json` 展示行情表；**json 内无 token**，仅含行情字段。
- **更新 `snapshot.json`**：纯静态托管下浏览器无法直连 TuShare；新数据依赖 **Actions 定时/手动**（`workflow_dispatch`）或本机执行 `python scripts/build_snapshot.py` 后 `npm run build` 再推送。

## 脚本与标的列表

| 脚本 | 作用 |
|------|------|
| `scripts/build_snapshot.py` | 拉取指数 MA120、ETF 上月月 K，生成 `web/public/snapshot.json` 供看板展示（CI / 本机均可） |

---

*若 TuShare 接口或积分策略变更，以官网文档为准；本 README 记录的是当前实现所依据的约定与踩坑结论。*
