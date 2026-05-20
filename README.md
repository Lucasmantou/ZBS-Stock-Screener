# ZBS Stock Research

> 基于akshare的A股个股深度研究与智能选股系统
>
> 选股策略 → 智能筛选 → 深度分析 → 生成专业HTML研报

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)

---

## 功能特性

- **智能选股** - 6种策略：超跌反弹、趋势跟踪、高股息价值、成长股、北向资金、涨停接力
- **自动数据获取** - 基于akshare获取全维度股票数据（K线、财务、新闻、龙虎榜等13类数据源）
- **五段式分析框架** - Part I 宏观定位 → Part II 产业链拆解 → Part III 质量评分 → Part IV 估值与赔率 → Part V 跟踪结论
- **专业HTML报告** - 深色/浅色双主题、响应式布局、ECharts图表
- **真实K线数据** - 含MA5/20/60均线、成交量柱分色
- **产业链可视化** - SVG图表展示上中下游关系
- **评分系统** - 五维度质量评分（基本面、产业匹配、弹性、估值、治理）

---

## 快速开始

### 智能选股

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 运行选股
python stock_screener.py --strategy oversold --top 10    # 超跌反弹
python stock_screener.py --strategy trend --top 10       # 趋势跟踪
python stock_screener.py --strategy all --top 5          # 全部策略
```

**6种选股策略：**

| 策略 | 说明 |
|------|------|
| oversold | 超跌反弹：当日跌幅大，成交活跃 |
| trend | 趋势跟踪：温和上涨，放量 |
| dividend | 高股息价值：蓝筹特征，走势稳健 |
| growth | 成长股：上涨趋势，成交活跃 |
| northbound | 北向资金：大资金关注 |
| zt_follow | 涨停接力：接近涨停，放量 |

### 个股深度分析

直接对话触发：

```
用户：分析 600519 股票
用户：分析贵州茅台
用户：个股分析 000066
```

AI会自动执行完整的三阶段流程：
1. **Phase 1**：运行 `python zbs_collect.py 600519` 采集数据
2. **Phase 2**：AI深度分析，生成MD报告
3. **Phase 3**：AI手写HTML，生成可视化报告

**输出文件：**
- `output/data_600519.json` - 原始数据
- `output/zbs-贵州茅台.md` - 分析报告
- `output/zbs-贵州茅台.html` - 可视化报告

### 手动运行

```bash
# 仅数据采集
python zbs_collect.py 000066

# 查看报告
cd output && python -m http.server 8899
# 浏览器访问 http://localhost:8899/zbs-中国长城.html
```

---

## 项目结构

```
zbs-stock-research/
├── src/                        # 核心模块
│   ├── __init__.py
│   ├── data_fetcher.py         # 数据采集（Phase 1模块版）
│   ├── analyzer.py             # 分析框架配置（Part I-V）
│   ├── html_renderer.py        # HTML渲染器（Jinja2模板）
│   └── utils.py                # 工具函数
├── shared/                     # 共享模板
│   ├── template_base.css       # CSS设计系统（v5.0）
│   └── template_base.js        # 交互逻辑（v5.0）
├── zbs_collect.py              # 独立数据采集脚本
├── stock_screener.py           # 智能选股系统
├── requirements.txt            # 依赖包
├── config.yaml                 # 配置文件
├── docs/                       # 文档
├── output/                     # 输出目录
└── README.md
```

---

## 五段式分析框架

### Part I：宏观与周期定位

- 经济周期映射
- 政策与环境扫描
- 核心矛盾提炼

### Part II：产业链深度拆解

- 题材来源判断
- 产业链图谱
- 业务线拆解与趋势三要素
- 价值链利润分布

### Part III：公司筛选与质量评分

- 正面筛选清单
- 不碰清单
- 五维度质量评分（100分制）

### Part IV：估值与赔率

- 估值方法选择
- 资金面分析
- 技术面分析
- 三档目标价
- 盈亏比量化

### Part V：跟踪计划与综合结论

- 分层跟踪锚点
- 执行清单
- 综合结论
- 五维综合评分

---

## 技术栈

- **数据获取**: akshare（A股全维度数据源）
- **数据分析**: pandas, numpy
- **图表渲染**: ECharts 5.5.1
- **HTML生成**: Python Jinja2 模板引擎
- **样式设计**: CSS3（双主题 + 响应式）

---

## 数据来源

- K线数据：akshare（新浪日K，前复权）
- 财务数据：akshare（东财/同花顺）
- 资金流向：akshare（东财个股版）
- 龙虎榜：akshare（东财）
- 新闻/研报：akshare（东财）

---

## 免责声明

本工具仅供学习研究使用，不构成任何投资建议。

股市有风险，投资需谨慎。使用本工具产生的任何投资决策及其后果，均由使用者自行承担。

---

## 许可证

[MIT License](LICENSE)

---

## 致谢

- [akshare](https://github.com/akfamily/akshare) - 开源A股数据源
- [ECharts](https://echarts.apache.org/) - 可视化图表库
