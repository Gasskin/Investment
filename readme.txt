5000积分|wwpecc0759164f58b88f05b57d0627629bb1d3c75e30b5683b3ed2f3

【你必须遵守的规则】
1.只允许通过TuShare提供的api获取数据，没有对应接口或某类标的不可用时须报错或说明原因，不得用其他数据源凑数。
2.可以对获取的数据进行计算加工，但不允许直接计算目标数据：若TuShare已提供目标周期接口，必须通过该周期取数。例：要月K涨跌幅，应使用月线级接口得到月收盘等；不得用30根日线自行替代月线口径。
   例外（已文档化）：场内ETF的pro.monthly常为空、pro_bar+qfq依赖adj_factor而ETF需fund_adj时，可用官方fund_daily+fund_adj前复权后按自然月合成月K（首交易日开盘、末交易日收盘、月内高低；涨跌相对再上一月末复权收盘）。
3.涉及需要复权的证券行情采用前复权（qfq）。主要指数的index_daily/index_global为指数点位，不适用股票/ETF的qfq/hfq。

【实现上约定 / 踩坑结论】
Token读取顺序（zhishu.py、etfPool.py的resolve_token）：环境变量TUSHARE_TOKEN或TS_TOKEN → 本文件首条非空行「说明|token」取竖线右侧 → 用户目录tk.csv（ts.set_token）。勿将含token的本文件提交公开仓库。

zhishu.py：上证用ts.pro_bar(asset=I,freq=D,ma=[120])，底层index_daily；恒生/标普/日经225用pro.index_global（HSI、SPX、N225，见官网国际指数表），因pro_bar未接index_global；MA120对全球指数日线做rolling。index_global常见需约6000+积分，index_daily约2000+，以官网为准。

etfPool.py：ETF用fund_daily+fund_adj做前复权后合成上一自然月月K；fund_daily/fund_adj常见5000+积分。详见同目录README.md。

运行：pip install tushare pandas；python zhishu.py；python etfPool.py。

ETF池：159941、513500、513010、513630、513000、159530、159929（159*.SZ，513*.SH）。

参考：readme_api.txt；https://tushare.pro/document/2
