"""自检：不依赖 pytest，直接用标准库跑。

运行：
    python -m tests.selftest

覆盖：
1. 评分边界：极端输入下所有分数落在 [0, 100]
2. 集中度逻辑：单一持仓 HHI=1 时结构分应为最低档
3. 盈亏方向：浮盈走 up 类、浮亏走 down 类（红涨绿跌）
4. 报告自包含：产物不含任何外链资源
5. 异常处理：坏数据要报错而不是产出错误报告
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tickercheck.engine import (  # noqa: E402
    run_audit, score_growth, score_quality, score_risk, score_structure, score_valuation,
)
from tickercheck.models import Holding, Portfolio  # noqa: E402
from tickercheck.report import render  # noqa: E402

PASSED: list[str] = []
FAILED: list[str] = []


def check(name: str, cond: bool, extra: str = "") -> None:
    if cond:
        PASSED.append(name)
        print(f"  PASS  {name}")
    else:
        FAILED.append(f"{name} {extra}".strip())
        print(f"  FAIL  {name} {extra}")


def test_score_bounds() -> None:
    extremes = [None, -999, -1, 0, 0.01, 1, 50, 999, 1e6]
    vals = [score_valuation(a, b) for a in extremes for b in extremes]
    vals += [score_growth(a, b) for a in extremes for b in extremes]
    vals += [score_quality(a, b) for a in extremes for b in extremes]
    vals += [score_risk(a) for a in extremes]
    check("评分落在 [0,100]", all(0.0 <= v <= 100.0 for v in vals),
          f"越界值={[v for v in vals if not 0 <= v <= 100][:5]}")


def test_concentration() -> None:
    single = Portfolio([Holding("A", "A", "X", 100, 10, 10)])
    s_single, d_single = score_structure(single)
    spread = Portfolio([Holding(f"C{i}", f"C{i}", f"S{i}", 100, 10, 10) for i in range(10)])
    s_spread, d_spread = score_structure(spread)
    check("单一持仓 HHI=1", abs(d_single["hhi"] - 1.0) < 1e-9, f"hhi={d_single['hhi']}")
    check("分散组合结构分更高", s_spread > s_single, f"{s_spread:.1f} vs {s_single:.1f}")
    check("10 等份 HHI≈0.1", abs(d_spread["hhi"] - 0.1) < 1e-9, f"hhi={d_spread['hhi']}")


def test_pnl_direction() -> None:
    up = Holding("U", "涨", "X", 100, 10, 12)
    down = Holding("D", "跌", "X", 100, 12, 10)
    check("浮盈为正", up.pnl > 0 and up.pnl_pct > 0)
    check("浮亏为负", down.pnl < 0 and down.pnl_pct < 0)
    html = render(Portfolio([up, down]), run_audit(Portfolio([up, down])))
    check("报告含 up 类", 'class="up"' in html)
    check("报告含 down 类", 'class="down"' in html)


def test_report_self_contained() -> None:
    pf = Portfolio([
        Holding("600104", "上汽集团", "汽车", 700, 18.5, 15.2, 12.5, 0.75, 6.2, -8.5, -3.2, 62.0, 28.0),
        Holding("510880", "红利ETF", "红利", 12000, 3.10, 3.35),
    ])
    html = render(pf, run_audit(pf))
    check("报告非空", len(html) > 2000, f"len={len(html)}")
    check("无外链资源", "http://" not in html and "https://" not in html and "<script" not in html)
    check("含免责声明", "不构成投资建议" in html)


def test_bad_input() -> None:
    from tickercheck.models import DataError, load_holdings
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as f:
        f.write("code,name\nA,B\n")
        path = f.name
    try:
        load_holdings(path)
        check("缺少必需列时报错", False, "未抛异常")
    except DataError:
        check("缺少必需列时报错", True)
    finally:
        os.unlink(path)


def main() -> int:
    print("TickerCheck 自检")
    test_score_bounds()
    test_concentration()
    test_pnl_direction()
    test_report_self_contained()
    test_bad_input()
    print(f"\n通过 {len(PASSED)} 项，失败 {len(FAILED)} 项")
    if FAILED:
        for f in FAILED:
            print(f"  - {f}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
