"""报告渲染：输出**单文件自包含 HTML**（内嵌 CSS，无任何外部资源）。

配色约定：
- 涨跌：红涨绿跌（中国市场习惯）
- 评分：语义色（青→绿→琥珀→红），与涨跌无关
"""

from __future__ import annotations

import html
from datetime import datetime
from typing import Dict

from .models import Portfolio

CSS = """
:root{--bg:#F0F7F7;--card:#FFFFFF;--ink:#0F172A;--muted:#64748B;--line:#E2E8F0;
--up:#E11D48;--down:#16A34A;--accent:#0EA5E9;}
*{box-sizing:border-box}
body{margin:0;padding:32px 20px;background:var(--bg);color:var(--ink);
font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
line-height:1.6;-webkit-font-smoothing:antialiased}
.wrap{max-width:960px;margin:0 auto}
h1{font-size:24px;margin:0 0 4px}
h2{font-size:17px;margin:28px 0 12px;padding-left:10px;border-left:3px solid var(--accent)}
.sub{color:var(--muted);font-size:13px;margin-bottom:20px}
.card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:20px;
box-shadow:0 1px 3px rgba(15,23,42,.06);margin-bottom:16px}
.hero{display:flex;align-items:center;gap:24px;flex-wrap:wrap}
.score{font-size:52px;font-weight:700;line-height:1}
.badge{display:inline-block;padding:4px 12px;border-radius:999px;color:#fff;font-size:13px;font-weight:600}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:14px;margin-top:8px}
.kv div{font-size:13px;color:var(--muted)}
.kv b{display:block;font-size:19px;color:var(--ink);font-weight:600;margin-top:2px}
.bar{height:10px;background:#E8EEF2;border-radius:999px;overflow:hidden;margin:6px 0 0}
.bar span{display:block;height:100%;border-radius:999px}
.dim{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:16px}
.dim .lab{font-size:13px;color:var(--muted);display:flex;justify-content:space-between}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{padding:9px 8px;border-bottom:1px solid var(--line);text-align:right;white-space:nowrap}
th{color:var(--muted);font-weight:600;font-size:12px}
th:first-child,td:first-child,th:nth-child(2),td:nth-child(2){text-align:left}
tbody tr:hover{background:#F8FAFB}
.up{color:var(--up);font-weight:600}
.down{color:var(--down);font-weight:600}
ul{margin:0;padding-left:20px}
li{margin-bottom:7px;font-size:14px}
.flag{background:#FFF7ED;border:1px solid #FED7AA;border-radius:10px;padding:14px 18px}
.check{background:#F0F9FF;border:1px solid #BAE6FD;border-radius:10px;padding:14px 18px}
.disc{color:var(--muted);font-size:12px;border-top:1px solid var(--line);padding-top:14px;margin-top:24px}
.tag{display:inline-block;background:#F1F5F9;color:#475569;border-radius:6px;padding:1px 7px;
font-size:11px;margin:2px 4px 0 0}
@media(max-width:640px){body{padding:16px 10px}.score{font-size:40px}.hero{gap:12px}}
"""

DISCLAIMER = (
    "本工具输出的是基于你输入数据做的结构化体检结果，仅用于信息整理与自我核查，"
    "不构成投资建议、买卖依据或任何形式的收益承诺。所有评分为规则化计算的参考值，"
    "不预测未来走势。数据准确性取决于你提供的 CSV，请自行校验后再使用。"
)


def _cls(v: float) -> str:
    return "up" if v > 0 else ("down" if v < 0 else "")


def _pct(v: float) -> str:
    return f"{v:+.2f}%"


def _money(v: float) -> str:
    return f"{v:,.0f}"


def _bar_color(score: float) -> str:
    if score >= 80:
        return "#0EA5E9"
    if score >= 65:
        return "#22C55E"
    if score >= 50:
        return "#F59E0B"
    return "#EF4444"


def render(
    portfolio: Portfolio,
    result: Dict,
    title: str = "持仓体检报告",
    data_source: str = "本地 CSV（用户提供）",
    as_of: str = "",
) -> str:
    e = html.escape
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = result["total_score"]
    as_of_show = e(as_of) if as_of else '<span style="color:#EF4444">未标注（请补填 --as-of）</span>'

    # 总览卡片
    hero = f"""
    <div class="card">
      <div class="hero">
        <div>
          <div class="score" style="color:{result['color']}">{total:.0f}</div>
          <div style="margin-top:6px"><span class="badge" style="background:{result['color']}">{e(result['grade'])}</span></div>
        </div>
        <div style="flex:1;min-width:240px">
          <div class="kv">
            <div>总市值（元）<b>{_money(portfolio.total_market_value)}</b></div>
            <div>总成本（元）<b>{_money(portfolio.total_cost_value)}</b></div>
            <div>总盈亏（元）<b class="{_cls(portfolio.total_pnl)}">{portfolio.total_pnl:+,.0f}</b></div>
            <div>总收益率<b class="{_cls(portfolio.total_pnl_pct)}">{_pct(portfolio.total_pnl_pct)}</b></div>
          </div>
        </div>
      </div>
    </div>"""

    # 五维评分
    dims = "".join(
        f"""<div>
          <div class="lab"><span>{e(k)}</span><b>{v:.0f}</b></div>
          <div class="bar"><span style="width:{max(2, min(100, v)):.0f}%;background:{_bar_color(v)}"></span></div>
        </div>"""
        for k, v in result["dim_scores"].items()
    )

    # 持仓明细
    rows = ""
    for h, w in zip(portfolio.holdings, result["weights"]):
        flags = "".join(f'<span class="tag">{e(f)}</span>' for f in h.flags)
        rows += f"""<tr>
          <td>{e(h.code)}</td>
          <td>{e(h.name)}<br>{flags}</td>
          <td>{e(h.sector)}</td>
          <td>{w * 100:.1f}%</td>
          <td>{_money(h.market_value)}</td>
          <td class="{_cls(h.pnl)}">{h.pnl:+,.0f}</td>
          <td class="{_cls(h.pnl_pct)}">{_pct(h.pnl_pct)}</td>
          <td><b>{h.total_score:.0f}</b></td>
        </tr>"""

    # 结构诊断
    d = result["structure_detail"]
    struct = f"""
    <div class="card">
      <h2>结构诊断</h2>
      <div class="kv">
        <div>持仓数量<b>{len(portfolio.holdings)} 只</b></div>
        <div>集中度 HHI<b>{d.get('hhi', 0):.3f}</b></div>
        <div>第一大持仓占比<b>{d.get('top1_weight', 0) * 100:.1f}%</b></div>
        <div>最大行业占比<b>{d.get('max_sector_weight', 0) * 100:.1f}%</b></div>
        <div>结构得分<b>{result['dim_scores'].get('结构', 0):.0f}</b></div>
      </div>
    </div>"""

    pf = "".join(f"<li>{e(x)}</li>" for x in result["portfolio_flags"]) or "<li>未触发组合级风险阈值。</li>"
    ck = "".join(f"<li>{e(x)}</li>" for x in result["checklist"])

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title><style>{CSS}</style></head>
<body><div class="wrap">
<h1>{e(title)}</h1>
<div class="sub">生成时间 {now} ｜ 数据截止 {as_of_show} ｜ 数据来源 {e(data_source)} ｜ 持仓体检卡 TickerCheck</div>
{hero}
<div class="card"><h2>五维评分</h2><div class="dim">{dims}</div></div>
<div class="card"><h2>持仓明细</h2>
<table><thead><tr>
<th>代码</th><th>名称</th><th>行业</th><th>权重</th><th>市值</th><th>盈亏</th><th>收益率</th><th>评分</th>
</tr></thead><tbody>{rows}</tbody></table></div>
{struct}
<div class="card flag"><h2>风险标记（事实陈述）</h2><ul>{pf}</ul></div>
<div class="card check"><h2>下一步核查清单</h2><ul>{ck}</ul></div>
<div class="disc">{e(DISCLAIMER)}</div>
</div></body></html>"""
