"""批量跑批：把「生成报告 + 生成回传模板 + 记账」三步压到秒级。

设计约束（来自 06 MVP 验证设计，不可违反）：
- 「是否陌生 / 是否真实」的最终判定**必须由创始人做**，脚本不得代判。
  脚本只做机械校验（≥3 只 + 含成本价 + 有仓位），结果一律记为 `pending`。
- 不托管、不留存真实持仓：报告写到本地 out/ 目录，处理完由人自行删除。

用法：
    # 跑批：处理 submissions/ 下所有 CSV
    python -m scripts.batch --inbox submissions --outdir out/batch --as-of 2026-09-12 --week W1

    # 人工判定后补记（脚本不代判，只记录你的判定）
    python -m scripts.batch --mark "demo-a:real" --week W1
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tickercheck.engine import run_audit  # noqa: E402
from tickercheck.models import DataError, load_holdings  # noqa: E402
from tickercheck.report import render  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
METRICS = os.path.join(ROOT, "notes", "metrics.txt")

REPLY_TEMPLATE = """你好，这是你提交的持仓体检报告（附件 HTML，双击即可打开，无需联网）。

关于这份报告：
1. 它是**规则化打分**的结构化体检，不是评级，也不含任何买卖建议；
2. 所有数据来自你提交的内容，工具只做计算，不联网、不上传、不留存；
3. 报告页眉标注了数据来源与数据截止日期，若数据有误，修正后我可以重跑。

只问一个问题（一句话就行，不用客气）：

    「报告里哪一条是你之前没看到的？」

——这条反馈决定我下一步改什么。谢谢。

（本工具输出仅供数据核查参考，不构成投资建议。）
"""


def _append_metrics(line: str) -> None:
    os.makedirs(os.path.dirname(METRICS), exist_ok=True)
    with open(METRICS, "a", encoding="utf-8") as f:
        f.write(line.rstrip("\n") + "\n")


def _date() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def mechanical_check(portfolio) -> tuple[bool, str]:
    """机械校验是否满足「真实持仓」的硬性口径：≥3 只 + 含成本价 + 有仓位。

    注意：通过仅代表「候选真实」，是否陌生仍须人工判定。
    """
    n = len(portfolio.holdings)
    has_cost = all(h.cost > 0 for h in portfolio.holdings)
    has_weight = portfolio.total_market_value > 0
    ok = n >= 3 and has_cost and has_weight
    reasons = []
    if n < 3:
        reasons.append(f"仅 {n} 只（需 ≥3）")
    if not has_cost:
        reasons.append("缺成本价")
    if not has_weight:
        reasons.append("市值为 0（仓位异常）")
    return ok, ("、".join(reasons) if reasons else "符合真实口径（候选）")


def process(csv_path: str, outdir: str, as_of: str, week: str, source: str) -> int:
    stem = os.path.splitext(os.path.basename(csv_path))[0]
    t0 = time.time()
    try:
        portfolio = load_holdings(csv_path)
    except (DataError, OSError) as exc:
        print(f"  SKIP  {stem}: 数据不合格（{exc}）")
        _append_metrics(f"{_date()} | {week} | submit | 1 | invalid | auto | {stem}: 读取失败 {exc}")
        return 1

    result = run_audit(portfolio)
    html = render(portfolio, result, title=f"持仓体检报告 · {stem}",
                  data_source=source, as_of=as_of)
    html_path = os.path.join(outdir, f"{stem}.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html)

    reply_path = os.path.join(outdir, f"{stem}.reply.txt")
    with open(reply_path, "w", encoding="utf-8") as f:
        f.write(REPLY_TEMPLATE)

    elapsed = time.time() - t0
    ok, reason = mechanical_check(portfolio)

    print(f"  OK    {stem}: {len(portfolio.holdings)} 只 ｜ 评分 {result['total_score']:.0f}"
          f"（{result['grade']}）｜ 耗时 {elapsed:.1f}s ｜ {reason}")
    print(f"        报告 {html_path}")
    print(f"        回传 {reply_path}")

    _append_metrics(
        f"{_date()} | {week} | submit | 1 | pending | auto | "
        f"{stem}: {len(portfolio.holdings)}只, {reason}（陌生性待人工判定）"
    )
    _append_metrics(f"{_date()} | {week} | cost | 1 | - | auto | 单份端到端 {elapsed:.1f} 秒（脚本自动跑批）")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="持仓体检批量跑批 + 回传模板 + 自动记账")
    p.add_argument("--inbox", default="submissions", help="提交目录（内含多个 CSV）")
    p.add_argument("--outdir", default="out/batch", help="输出目录")
    p.add_argument("--as-of", default="", help="数据截止日期（公开报告必填）")
    p.add_argument("--source", default="提交者提供的 CSV", help="数据来源标注")
    p.add_argument("--week", default="W1", help="周次标签，如 W1")
    p.add_argument("--mark", default="", help='人工判定补记，格式 "文件名:real" 或 "文件名:invalid"')
    args = p.parse_args(argv)

    if args.mark:
        if ":" not in args.mark:
            print("[错误] --mark 格式应为 文件名:real 或 文件名:invalid", file=sys.stderr)
            return 2
        stem, verdict = args.mark.split(":", 1)
        if verdict not in {"real", "invalid"}:
            print("[错误] 判定只能是 real 或 invalid", file=sys.stderr)
            return 2
        _append_metrics(
            f"{_date()} | {args.week} | note | 1 | {verdict} | manual | "
            f"{stem}: 创始人人工判定（是否陌生/真实）"
        )
        print(f"已补记判定：{stem} → {verdict}")
        return 0

    inbox = args.inbox if os.path.isabs(args.inbox) else os.path.join(ROOT, args.inbox)
    outdir = args.outdir if os.path.isabs(args.outdir) else os.path.join(ROOT, args.outdir)
    os.makedirs(outdir, exist_ok=True)

    if not os.path.isdir(inbox):
        print(f"[错误] 提交目录不存在：{inbox}", file=sys.stderr)
        return 2

    files = sorted(
        f for f in os.listdir(inbox)
        if f.lower().endswith(".csv") and not f.startswith("_")
    )
    if not files:
        print(f"[提示] {inbox} 下没有待处理的 CSV")
        return 0

    if not args.as_of:
        print("[提醒] 未填 --as-of，公开报告将缺少数据截止日期。", file=sys.stderr)

    print(f"批量跑批：{len(files)} 份 ｜ 数据截止 {args.as_of or '未标注'} ｜ 周次 {args.week}")
    failed = 0
    for name in files:
        failed += process(os.path.join(inbox, name), outdir, args.as_of, args.week, args.source)

    print(f"\n完成：{len(files) - failed} 成功 / {failed} 跳过")
    print(f"记账已追加至 {METRICS}（valid=pending，陌生性须你人工判定后 --mark 补记）")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
