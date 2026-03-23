# Tushare Pro API 文档

## 基础信息

### 代码规范

| 交易所 | 后缀 | 示例 |
|--------|------|------|
| 上交所 | .SH | 600000.SH |
| 深交所 | .SZ | 000001.SZ |
| 北交所 | .BJ | 830001.BJ |
| 港交所 | .HK | 00001.HK |

### 调用方式
```python
import tushare as ts
pro = ts.pro_api('your_token')
```

---

## 一、股票数据

### 1.1 基础数据

#### 股票列表 `stock_basic`
```python
df = pro.stock_basic(exchange='', list_status='L', fields='ts_code,name,industry,list_date')
```
| 参数 | 说明 |
|------|------|
| ts_code | 股票代码 |
| name | 名称 |
| market | 市场类别 |
| list_status | 上市状态 L/D/P |

#### 交易日历 `trade_cal`
```python
df = pro.trade_cal(exchange='SSE', start_date='20250101', end_date='20251231')
```
| 参数 | 说明 |
|------|------|
| exchange | 交易所 |
| start_date | 开始日期 |
| end_date | 结束日期 |
| is_open | 是否交易 0/1 |

#### 上市公司信息 `stock_company`
```python
df = pro.stock_company(ts_code='600000.SH', fields='ts_code,chairman,manager,reg_capital')
```

### 1.2 行情数据

#### 日线行情 `daily`
```python
df = pro.daily(ts_code='000001.SZ', start_date='20250101', end_date='20250601')
```
| 输出字段 | 说明 |
|----------|------|
| ts_code | 代码 |
| trade_date | 日期 |
| open/high/low/close | OHLC |
| pre_close | 昨收 |
| pct_chg | 涨跌幅% |
| vol | 成交量(手) |
| amount | 成交额(千元) |

#### 复权因子 `adj_factor`
```python
df = pro.adj_factor(ts_code='000001.SZ', start_date='20250101')
```
| 输出字段 | 说明 |
|----------|------|
| adj_factor | 复权因子 |

#### 周线 `weekly` / 月线 `monthly`
```python
df = pro.weekly(ts_code='000001.SZ', start_date='20250101')
df = pro.monthly(ts_code='000001.SZ', start_date='20250101')
```

### 1.3 财务数据

#### 利润表 `income`
```python
df = pro.income(ts_code='600000.SH', period='20250331')
```
| 主要字段 | 说明 |
|----------|------|
| total_revenue | 营业总收入 |
| revenue | 营业收入 |
| total_cogs | 营业总成本 |
| n_income | 净利润 |
| basic_eps | 基本每股收益 |

#### 资产负债表 `balancesheet`
```python
df = pro.balancesheet(ts_code='600000.SH', period='20250331')
```
| 主要字段 | 说明 |
|----------|------|
| total_cur_assets | 流动资产合计 |
| total_cur_liab | 流动负债合计 |
| total_liab | 负债合计 |
| total_hldr_eqy_inc_min_int | 股东权益合计 |

#### 现金流量表 `cashflow`
```python
df = pro.cashflow(ts_code='600000.SH', period='20250331')
```
| 主要字段 | 说明 |
|----------|------|
| n_cashflow_act | 经营现金流净额 |
| free_cashflow | 自由现金流 |

#### 业绩预告 `forecast`
```python
df = pro.forecast(ts_code='600000.SH', period='20250630')
```
| 字段 | 说明 |
|------|------|
| type | 预告类型 |
| p_change_min/max | 变动幅度 |
| net_profit_min/max | 预告净利润 |

#### 分红送股 `dividend`
```python
df = pro.dividend(ts_code='600000.SH')
```
| 字段 | 说明 |
|------|------|
| stk_div | 每股送转 |
| cash_div | 每股分红 |
| record_date | 股权登记日 |
| ex_date | 除权除息日 |

---

## 二、ETF专题

### ETF基本信息 `etf_basic`
```python
df = pro.etf_basic(list_status='L')
```
| 字段 | 说明 |
|------|------|
| ts_code | ETF代码 |
| csname | 中文简称 |
| index_code | 跟踪指数代码 |
| mgr_name | 管理人 |
| list_date | 上市日期 |

### ETF日线行情 `fund_daily`
```python
df = pro.fund_daily(ts_code='510300.SH', start_date='20250101')
```
| 字段 | 说明 |
|------|------|
| open/high/low/close | OHLC |
| vol | 成交量(手) |
| amount | 成交额(千元) |

### ETF复权因子 `fund_adj`
```python
df = pro.fund_adj(ts_code='510300.SH', start_date='20250101')
```

### ETF份额规模 `etf_share_size`
```python
df = pro.etf_share_size(ts_code='510300.SH', start_date='20250101')
```
| 字段 | 说明 |
|------|------|
| total_share | 总份额(万份) |
| total_size | 总规模(万元) |
| nav | 基金净值 |

### ETF历史分钟 `stk_mins`
```python
df = pro.stk_mins(ts_code='510300.SH', freq='1min', 
                  start_date='2025-06-01 09:00:00', end_date='2025-06-01 15:00:00')
```
| freq参数 | 说明 |
|----------|------|
| 1min/5min/15min/30min/60min | 分钟频度 |

### ETF实时日线 `rt_etf_k`
```python
df = pro.rt_etf_k(ts_code='5*.SH')  # 通配符获取所有沪市ETF
```

---

## 三、指数专题

### 指数基本信息 `index_basic`
```python
df = pro.index_basic(market='SSE')  # SSE/SZSE
```
| 字段 | 说明 |
|------|------|
| ts_code | 指数代码 |
| name | 指数名称 |
| base_date | 基期 |
| base_point | 基点 |
| publisher | 发布方 |

### 指数日线行情 `index_daily`
```python
df = pro.index_daily(ts_code='000001.SH', start_date='20250101')
```
| 字段 | 说明 |
|------|------|
| open/high/low/close | OHLC |
| vol | 成交量(万手) |
| amount | 成交额(亿元) |
| pct_chg | 涨跌幅% |

### 指数周线 `index_weekly` / 月线 `index_monthly`
```python
df = pro.index_weekly(ts_code='000001.SH', start_date='20250101')
df = pro.index_monthly(ts_code='000001.SH', start_date='20250101')
```

### 指数成分权重 `index_weight`
```python
df = pro.index_weight(index_code='000300.SH', start_date='20250101')
```
| 字段 | 说明 |
|------|------|
| con_code | 成分股代码 |
| weight | 权重(%) |

### 大盘指数每日指标 `index_dailybasic`
```python
df = pro.index_dailybasic(ts_code='000001.SH', start_date='20250101')
```
| 字段 | 说明 |
|------|------|
| pe | 市盈率 |
| pb | 市净率 |
| total_mv | 总市值 |
| circ_mv | 流通市值 |

### 申万行业分类 `index_classify`
```python
df = pro.index_classify(level='L1', src='SW')  # L1/L2/L3
```
| 字段 | 说明 |
|------|------|
| index_code | 行业代码 |
| industry_name | 行业名称 |

### 申万行业成分 `index_member_all`
```python
df = pro.index_member_all(index_code='850131.SI')
```

### 申万行业行情 `sw_daily`
```python
df = pro.sw_daily(ts_code='850131.SI', start_date='20250101')
```

### 中信行业成分 `ci_index_member`
```python
df = pro.ci_index_member(index_code='CI005001')
```

### 中信行业行情 `ci_daily`
```python
df = pro.ci_daily(ts_code='CI005001.CI', start_date='20250101')
```

### 国际主要指数 `index_global`
```python
df = pro.index_global(ts_code='IXIC.GI', start_date='20250101')
```
| 常用指数代码 | 说明 |
|--------------|------|
| IXIC.GI | 纳斯达克指数 |
| DJI.GI | 道琼斯指数 |
| SPX.GI | 标普500 |
| N225.GI | 日经225 |
| FTSE.GI | 富时100 |

---

## 四、积分权限汇总

| 积分 | 可用接口 |
|------|----------|
| 120+ | stock_company |
| 500+ | fund_daily |
| 600+ | fund_adj, index_weekly, index_monthly |
| 2000+ | stock_basic, trade_cal, daily, adj_factor, income, balancesheet, cashflow, forecast, dividend, index_daily, index_weight, index_classify |
| 5000+ | sw_daily, ci_index_member, ci_daily |
| 6000+ | index_global |
| 8000+ | etf_basic, etf_index, etf_share_size |
| 单独申请 | stk_mins, rt_etf_k, rt_min, idx_mins, rt_idx_k |

---

## 参考链接

- 官方文档: https://tushare.pro/document/2
- 股票数据: https://tushare.pro/document/2?doc_id=14
- ETF专题: https://tushare.pro/document/2?doc_id=384
- 指数专题: https://tushare.pro/document/2?doc_id=93
