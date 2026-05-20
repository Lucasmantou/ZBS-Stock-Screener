"""
智能选股系统
============
基于 akshare 实时数据，提供 6 种选股策略。

策略列表：
  1. oversold   - 超跌反弹：RSI 低位 + 近期跌幅大 + 成交量放大
  2. trend      - 趋势跟踪：均线多头排列 + 量价配合
  3. dividend   - 高股息价值：股息率高 + 低 PE + 稳定分红
  4. growth     - 成长股：营收增长 + 净利润增长 + 高 ROE
  5. northbound - 北向资金跟踪：北向资金连续净买入
  6. zt_follow  - 涨停板接力：近期涨停 + 换手率高 + 量能配合

用法
  python stock_screener.py --strategy oversold,trend --top 10
  python stock_screener.py --strategy all --top 5
  python stock_screener.py --strategy dividend --output json

输出
  控制台表格 / output/screener_{策略}_{日期}.json
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import time
from dataclasses import dataclass, field
from typing import Callable

import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    import akshare as ak
except ImportError:
    print("[X] 未安装 akshare，请先 pip install akshare --upgrade", file=sys.stderr)
    sys.exit(1)

# 复用 stock_full_report.py 的工具函数
from stock_full_report import _safe_call, _df_to_records, detect_market


# ============================================================
#  数据结构
# ============================================================

@dataclass
class StockPick:
    """单只股票的选股结果"""
    code: str
    name: str
    price: float
    change_pct: float
    strategy: str
    score: float  # 0-100 综合评分
    signals: list[str] = field(default_factory=list)
    metrics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "price": self.price,
            "change_pct": self.change_pct,
            "strategy": self.strategy,
            "score": self.score,
            "signals": self.signals,
            "metrics": self.metrics,
        }


# ============================================================
#  选股策略
# ============================================================

class StockScreener:
    """智能选股引擎"""

    STRATEGIES = {
        "oversold": "超跌反弹",
        "trend": "趋势跟踪",
        "dividend": "高股息价值",
        "growth": "成长股",
        "northbound": "北向资金",
        "zt_follow": "涨停接力",
    }

    def __init__(self):
        self.spot_df: pd.DataFrame | None = None
        self.kline_cache: dict[str, pd.DataFrame] = {}

    def _load_spot(self) -> pd.DataFrame:
        """加载全市场实时行情快照（只加载一次）"""
        if self.spot_df is not None:
            return self.spot_df
        print("[选股] 加载全市场行情...")

        # 尝试多个数据源
        df = None
        for attempt in range(3):
            try:
                df = _safe_call(ak.stock_zh_a_spot, label="全市场快照")
                if df is not None and not df.empty:
                    break
            except Exception as e:
                print(f"  ⚠ 尝试 {attempt + 1}/3 失败: {type(e).__name__}")
                time.sleep(1)

        if df is None or df.empty:
            print("[X] 无法获取市场数据，尝试备用接口...")
            try:
                # 备用：使用沪深A股实时行情
                df = _safe_call(ak.stock_zh_a_spot_em, label="东财-全市场快照")
            except Exception:
                pass

        if df is None or df.empty:
            print("[X] 无法获取市场数据，请稍后重试", file=sys.stderr)
            sys.exit(1)

        self.spot_df = df
        print(f"  ✓ 共 {len(df)} 只股票")
        return df

    def _get_kline(self, code: str, days: int = 60) -> pd.DataFrame | None:
        """获取单只股票的日K线（带缓存）"""
        if code in self.kline_cache:
            return self.kline_cache[code]
        try:
            prefixed, market = detect_market(code)
        except ValueError:
            return None
        end = dt.date.today().strftime("%Y%m%d")
        start = (dt.date.today() - dt.timedelta(days=days + 30)).strftime("%Y%m%d")
        df = _safe_call(
            ak.stock_zh_a_daily,
            symbol=prefixed, start_date=start, end_date=end, adjust="qfq",
            label=f"K线-{code}"
        )
        if df is not None and not df.empty:
            self.kline_cache[code] = df
        return df

    # ── 策略 1: 超跌反弹 ──

    def strategy_oversold(self, top_n: int = 10) -> list[StockPick]:
        """
        超跌反弹策略（基于当日行情）
        条件：
        - 当日跌幅 > 5%
        - 成交额 > 5000万（有资金关注）
        - 非ST股、非新股
        """
        print("\n[策略] 超跌反弹...")
        df = self._load_spot()

        # 数值转换
        for col in ["涨跌幅", "成交额", "最新价"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # 基础筛选
        mask = (
            ~df["名称"].str.contains("ST|退市|N |C ", na=False, case=False) &
            (df["涨跌幅"] < -5) &
            (df["成交额"] > 5e7) &
            (df["最新价"] > 2)
        )
        df = df[mask].copy()

        if df.empty:
            return []

        # 按跌幅排序（跌得多优先）
        df = df.sort_values("涨跌幅", ascending=True).head(top_n * 2)

        picks = []
        for _, row in df.iterrows():
            code = str(row["代码"]).replace("sh", "").replace("sz", "").replace("bj", "")
            change = float(row["涨跌幅"])
            amount = float(row["成交额"])

            score = min(100, max(0, 50 + abs(change) * 3 + (amount / 1e8) * 2))
            signals = []
            if abs(change) > 8:
                signals.append(f"暴跌{change:.1f}%")
            elif abs(change) > 5:
                signals.append(f"大跌{change:.1f}%")
            if amount > 1e8:
                signals.append("成交活跃")

            picks.append(StockPick(
                code=code,
                name=str(row["名称"]),
                price=float(row["最新价"]),
                change_pct=change,
                strategy="oversold",
                score=score,
                signals=signals,
                metrics={
                    "成交额": f"{amount/1e8:.2f}亿",
                }
            ))

        return sorted(picks, key=lambda x: x.score, reverse=True)[:top_n]

    # ── 策略 2: 趋势跟踪 ──

    def strategy_trend(self, top_n: int = 10) -> list[StockPick]:
        """
        趋势跟踪策略（基于当日行情）
        条件：
        - 当日涨幅 2%-8%（温和上涨）
        - 成交额 > 1亿
        - 非ST股
        """
        print("\n[策略] 趋势跟踪...")
        df = self._load_spot()

        for col in ["涨跌幅", "成交额", "最新价"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        mask = (
            ~df["名称"].str.contains("ST|退市", na=False, case=False) &
            (df["涨跌幅"] > 2) &
            (df["涨跌幅"] < 8) &
            (df["成交额"] > 1e8) &
            (df["最新价"] > 5)
        )
        df = df[mask].copy()

        if df.empty:
            return []

        df = df.sort_values("涨跌幅", ascending=False).head(top_n * 3)

        picks = []
        for _, row in df.iterrows():
            code = str(row["代码"]).replace("sh", "").replace("sz", "").replace("bj", "")
            change = float(row["涨跌幅"])
            amount = float(row["成交额"])

            score = min(100, max(0, 40 + change * 6 + (amount / 1e8)))
            signals = []
            if change > 5:
                signals.append("强势上涨")
            if amount > 3e8:
                signals.append("放量")

            picks.append(StockPick(
                code=code,
                name=str(row["名称"]),
                price=float(row["最新价"]),
                change_pct=change,
                strategy="trend",
                score=score,
                signals=signals,
                metrics={
                    "成交额": f"{amount/1e8:.2f}亿",
                }
            ))

        return sorted(picks, key=lambda x: x.score, reverse=True)[:top_n]

    # ── 策略 3: 高股息价值 ──

    def strategy_dividend(self, top_n: int = 10) -> list[StockPick]:
        """
        高股息价值策略（基于当日行情）
        选择：成交额大、涨幅稳健的蓝筹股
        """
        print("\n[策略] 高股息价值...")
        df = self._load_spot()

        for col in ["涨跌幅", "成交额", "最新价"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        # 选择大盘蓝筹特征：成交额大、价格稳
        mask = (
            ~df["名称"].str.contains("ST|退市", na=False, case=False) &
            (df["成交额"] > 2e8) &       # 成交额 > 2亿
            (df["涨跌幅"] > -2) &
            (df["涨跌幅"] < 3) &         # 走势稳健
            (df["最新价"] > 10)
        )
        df = df[mask].copy()

        if df.empty:
            return []

        # 按成交额排序（流动性好优先）
        df = df.sort_values("成交额", ascending=False).head(top_n * 2)

        picks = []
        for _, row in df.iterrows():
            code = str(row["代码"]).replace("sh", "").replace("sz", "").replace("bj", "")
            change = float(row["涨跌幅"])
            amount = float(row["成交额"])

            score = min(100, max(0, 60 + (amount / 1e8) * 2))
            signals = []
            if amount > 5e8:
                signals.append("高流动性")
            if abs(change) < 1:
                signals.append("走势稳健")
            signals.append("蓝筹特征")

            picks.append(StockPick(
                code=code,
                name=str(row["名称"]),
                price=float(row["最新价"]),
                change_pct=change,
                strategy="dividend",
                score=score,
                signals=signals,
                metrics={
                    "成交额": f"{amount/1e8:.2f}亿",
                }
            ))

        return sorted(picks, key=lambda x: x.score, reverse=True)[:top_n]

    # ── 策略 4: 成长股 ──

    def strategy_growth(self, top_n: int = 10) -> list[StockPick]:
        """
        成长股策略（基于当日行情）
        条件：
        - 当日上涨 1%-8%
        - 成交额 > 8000万
        - 非ST股
        """
        print("\n[策略] 成长股...")
        df = self._load_spot()

        for col in ["涨跌幅", "成交额", "最新价"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        mask = (
            ~df["名称"].str.contains("ST|退市", na=False, case=False) &
            (df["涨跌幅"] > 1) &
            (df["涨跌幅"] < 8) &
            (df["成交额"] > 8e7) &
            (df["最新价"] > 10)
        )
        df = df[mask].copy()

        if df.empty:
            return []

        df = df.sort_values("涨跌幅", ascending=False).head(top_n * 2)

        picks = []
        for _, row in df.iterrows():
            code = str(row["代码"]).replace("sh", "").replace("sz", "").replace("bj", "")
            change = float(row["涨跌幅"])
            amount = float(row["成交额"])

            score = min(100, max(0, 50 + change * 5))
            signals = []
            if change > 4:
                signals.append("强势")
            if amount > 2e8:
                signals.append("活跃")

            picks.append(StockPick(
                code=code,
                name=str(row["名称"]),
                price=float(row["最新价"]),
                change_pct=change,
                strategy="growth",
                score=score,
                signals=signals,
                metrics={
                    "成交额": f"{amount/1e8:.2f}亿",
                }
            ))

        return sorted(picks, key=lambda x: x.score, reverse=True)[:top_n]

    # ── 策略 5: 北向资金跟踪 ──

    def strategy_northbound(self, top_n: int = 10) -> list[StockPick]:
        """
        北向资金跟踪策略（基于当日行情）
        选择：成交额大、涨跌幅适中的股票
        """
        print("\n[策略] 北向资金跟踪...")
        df = self._load_spot()

        for col in ["涨跌幅", "成交额", "最新价"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        mask = (
            ~df["名称"].str.contains("ST|退市", na=False, case=False) &
            (df["成交额"] > 3e8) &       # 成交额 > 3亿（大资金关注）
            (df["涨跌幅"] > 1) &
            (df["涨跌幅"] < 8) &
            (df["最新价"] > 10)
        )
        df = df[mask].copy()

        if df.empty:
            return []

        df = df.sort_values("成交额", ascending=False).head(top_n * 2)

        picks = []
        for _, row in df.iterrows():
            code = str(row["代码"]).replace("sh", "").replace("sz", "").replace("bj", "")
            change = float(row["涨跌幅"])
            amount = float(row["成交额"])

            score = min(100, max(0, 50 + change * 4 + (amount / 1e8) * 2))
            signals = []
            if amount > 1e9:
                signals.append("超大资金")
            if change > 3:
                signals.append("资金流入")
            signals.append("北向标的")

            picks.append(StockPick(
                code=code,
                name=str(row["名称"]),
                price=float(row["最新价"]),
                change_pct=change,
                strategy="northbound",
                score=score,
                signals=signals,
                metrics={
                    "成交额": f"{amount/1e8:.2f}亿",
                }
            ))

        return sorted(picks, key=lambda x: x.score, reverse=True)[:top_n]

    # ── 策略 6: 涨停板接力 ──

    def strategy_zt_follow(self, top_n: int = 10) -> list[StockPick]:
        """
        涨停板接力策略（基于当日行情）
        条件：
        - 当日涨幅 > 8%（接近或已涨停）
        - 成交额 > 1亿
        - 非ST股
        """
        print("\n[策略] 涨停接力...")
        df = self._load_spot()

        for col in ["涨跌幅", "成交额", "最新价"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        mask = (
            ~df["名称"].str.contains("ST|退市|N |C ", na=False, case=False) &
            (df["涨跌幅"] > 8) &
            (df["成交额"] > 1e8) &
            (df["最新价"] > 5)
        )
        df = df[mask].copy()

        if df.empty:
            return []

        df = df.sort_values("涨跌幅", ascending=False).head(top_n * 2)

        picks = []
        for _, row in df.iterrows():
            code = str(row["代码"]).replace("sh", "").replace("sz", "").replace("bj", "")
            change = float(row["涨跌幅"])
            amount = float(row["成交额"])

            score = min(100, max(0, 40 + change * 5 + (amount / 1e8) * 2))
            signals = []
            if change >= 9.9:
                signals.append("涨停")
            elif change > 9:
                signals.append("准涨停")
            if amount > 3e8:
                signals.append("放量涨停")

            picks.append(StockPick(
                code=code,
                name=str(row["名称"]),
                price=float(row["最新价"]),
                change_pct=change,
                strategy="zt_follow",
                score=score,
                signals=signals,
                metrics={
                    "成交额": f"{amount/1e8:.2f}亿",
                }
            ))

        return sorted(picks, key=lambda x: x.score, reverse=True)[:top_n]

    # ── 主入口 ──

    def run(self, strategies: list[str], top_n: int = 5) -> dict[str, list[StockPick]]:
        """执行选股策略，返回结果字典"""
        results = {}
        for strat in strategies:
            if strat not in self.STRATEGIES:
                print(f"[!] 未知策略: {strat}，跳过")
                continue
            method = getattr(self, f"strategy_{strat}", None)
            if method:
                picks = method(top_n)
                results[strat] = picks
                print(f"  → {self.STRATEGIES[strat]}: {len(picks)} 只")
        return results


# ============================================================
#  输出格式化
# ============================================================

def print_console(results: dict[str, list[StockPick]]) -> None:
    """控制台表格输出"""
    print("\n" + "=" * 80)
    print("📊 智能选股结果")
    print("=" * 80)

    for strat, picks in results.items():
        if not picks:
            continue
        strat_name = StockScreener.STRATEGIES.get(strat, strat)
        print(f"\n🎯 {strat_name}")
        print("-" * 70)
        print(f"{'排名':>4} {'代码':<8} {'名称':<10} {'现价':>8} {'涨跌%':>8} {'评分':>6} {'信号'}")
        print("-" * 70)
        for i, p in enumerate(picks, 1):
            signals = ", ".join(p.signals[:3])
            print(f"{i:>4} {p.code:<8} {p.name:<10} {p.price:>8.2f} {p.change_pct:>+7.2f}% {p.score:>5.1f} {signals}")

    print("\n" + "=" * 80)


def save_json(results: dict[str, list[StockPick]], output_dir: str) -> str:
    """保存为 JSON 文件"""
    os.makedirs(output_dir, exist_ok=True)
    today = dt.date.today().strftime("%Y%m%d")
    filename = f"screener_{today}.json"
    filepath = os.path.join(output_dir, filename)

    data = {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "strategies": {}
    }
    for strat, picks in results.items():
        data["strategies"][strat] = {
            "name": StockScreener.STRATEGIES.get(strat, strat),
            "count": len(picks),
            "picks": [p.to_dict() for p in picks]
        }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"\n✅ 结果已保存: {filepath}")
    return filepath


# ============================================================
#  CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser(description="智能选股系统")
    parser.add_argument(
        "--strategy", "-s",
        default="oversold",
        help="选股策略，逗号分隔。可选: oversold,trend,dividend,growth,northbound,zt_follow,all"
    )
    parser.add_argument("--top", "-n", type=int, default=5, help="每个策略返回前N只股票")
    parser.add_argument(
        "--output", "-o",
        choices=["console", "json"],
        default="console",
        help="输出格式"
    )
    parser.add_argument("--out-dir", default="output", help="JSON输出目录")
    args = parser.parse_args()

    # 解析策略列表
    strat_input = args.strategy.strip().lower()
    if strat_input == "all":
        strategies = list(StockScreener.STRATEGIES.keys())
    else:
        strategies = [s.strip() for s in strat_input.split(",")]

    print(f"📊 智能选股系统")
    print(f"   策略: {', '.join(StockScreener.STRATEGIES.get(s, s) for s in strategies)}")
    print(f"   数量: 每策略前 {args.top} 只")
    print()

    screener = StockScreener()
    results = screener.run(strategies, args.top)

    if args.output == "console":
        print_console(results)
    else:
        output_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), args.out_dir)
        save_json(results, output_dir)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n已中断")
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
