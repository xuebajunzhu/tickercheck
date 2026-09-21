"""命令行入口。

用法：
    python -m tickercheck.cli --input samples/holdings.csv --out out/report.html
    python -m tickercheck.cli --input samples/holdings.csv --json   # 仅输出 JSON 摘要

依赖：Python 3.9+ 标准库，无需安装任何包。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

from .engine import run_audit
from .models import DataError, load_holdings
from .report import render


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        prog="tickercheck",
        description="持仓体检卡：把持仓 CSV 变成一份单文件 HTML 体检报告",
    )
    p.add_argument("--input", "-i", required=True, help="持仓 CSV 路径")
    p.add_argument("--out", "-o", default="out/report.html", help="HTML 报告输出路径")
    p.add_argument("--title", "-t", default="持仓体检报告", help="报告标题")
    p.add_argument("--json", action="store_true", help="同时在 stdout 输出 JSON 摘要")
    p.add_argument("--source", default="本地 CSV（用户提供）", help="数据来源标注（合规必填）")
    p.add_argument("--as-of", default="", help="数据截止日期，如 2026-09-12（合规必填）")
    p.add_argument("--quiet", "-q", action="store_true", help="不打印中文摘要")
    args = p.parse_args(argv)

    try:
        portfolio = load_holdings(args.input)
    except (DataError, OSError) as exc:
        print(f"[错误] 读取持仓失败：{exc}", file=sys.stderr)
        return 2

    result = run_audit(portfolio)

    out_dir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(out_dir, exist_ok=True)
    html = render(portfolio, result, title=args.title,
                  data_source=args.source, as_of=args.as_of)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(html)

    if not args.as_of:
        print("[提醒] 未填 --as-of，报告将显示数据截止「未标注」，公开前请补填。",
              file=sys.stderr)

    if not args.quiet:
        print(f"体检完成：{len(portfolio.holdings)} 只持仓")
        print(f"综合评分 {result['total_score']:.0f} / 100（{result['grade']}）")
        print("五维：" + "  ".join(f"{k} {v:.0f}" for k, v in result["dim_scores"].items()))
        print(f"总市值 {portfolio.total_market_value:,.0f} 元，"
              f"总盈亏 {portfolio.total_pnl:+,.0f} 元（{portfolio.total_pnl_pct:+.2f}%）")
        if result["portfolio_flags"]:
            print("风险标记：")
            for x in result["portfolio_flags"]:
                print(f"  - {x}")
        print(f"报告已生成：{os.path.abspath(args.out)}")

    if args.json:
        print(json.dumps({
            "total_score": round(result["total_score"], 1),
            "grade": result["grade"],
            "dim_scores": result["dim_scores"],
            "total_market_value": round(portfolio.total_market_value, 2),
            "total_pnl": round(portfolio.total_pnl, 2),
            "total_pnl_pct": round(portfolio.total_pnl_pct, 2),
            "flags": result["portfolio_flags"],
            "checklist": result["checklist"],
        }, ensure_ascii=False, indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
