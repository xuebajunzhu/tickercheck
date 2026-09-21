"""评分引擎：五维体检 + 风险标记 + 核查清单。

合规底线（硬编码，不可绕过）：
本模块只输出**结构化体检结果**与**待核查项**，
绝不生成"买入 / 卖出 / 加仓 / 减仓"等任何交易方向性表述。
"""

from __future__ import annotations

from typing import Dict, List, Tuple

from .models import Holding, Portfolio

WEIGHTS: Dict[str, float] = {
    "valuation": 0.30,   # 估值
    "growth": 0.20,      # 成长
    "quality": 0.30,     # 质量
    "risk": 0.20,        # 风险
}

# 组合层结构分在总分中的权重（个券四维加权后占 1 - 该值）
STRUCTURE_WEIGHT = 0.15

NEUTRAL = 50.0  # 数据缺失时的中性分


def _band(value: float, bands: List[Tuple[float, float]], default: float) -> float:
    """bands: [(阈值, 分数)]，按阈值升序，返回第一个 value < 阈值 对应的分数。"""
    for threshold, score in bands:
        if value < threshold:
            return score
    return default


def _clamp(x: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, x))


def score_valuation(pe: float | None, pb: float | None) -> float:
    """估值分：PE 越低越好（负 PE 视为亏损，给低分），PB 同理。"""
    if pe is None:
        pe_s = NEUTRAL
    elif pe <= 0:
        pe_s = 25.0          # 亏损企业，PE 无意义
    else:
        pe_s = _band(pe, [(10, 92), (20, 78), (30, 62), (50, 45), (80, 32)], 22)

    if pb is None:
        pb_s = NEUTRAL
    elif pb <= 0:
        pb_s = 30.0
    else:
        pb_s = _band(pb, [(1, 92), (2, 80), (3, 66), (5, 50), (8, 36)], 26)

    return _clamp(0.6 * pe_s + 0.4 * pb_s)


def score_growth(profit_yoy: float | None, revenue_yoy: float | None) -> float:
    def one(v: float | None) -> float:
        if v is None:
            return NEUTRAL
        if v >= 50:
            return 95.0
        if v >= 30:
            return 85.0
        if v >= 15:
            return 72.0
        if v >= 5:
            return 58.0
        if v >= 0:
            return 42.0
        if v >= -15:
            return 28.0
        return 15.0

    return _clamp(0.6 * one(profit_yoy) + 0.4 * one(revenue_yoy))


def score_quality(roe: float | None, debt_ratio: float | None) -> float:
    if roe is None:
        roe_s = NEUTRAL
    elif roe >= 20:
        roe_s = 95.0
    elif roe >= 15:
        roe_s = 85.0
    elif roe >= 10:
        roe_s = 70.0
    elif roe >= 5:
        roe_s = 52.0
    elif roe >= 0:
        roe_s = 35.0
    else:
        roe_s = 20.0

    if debt_ratio is None:
        debt_s = NEUTRAL
    elif debt_ratio <= 30:
        debt_s = 92.0
    elif debt_ratio <= 50:
        debt_s = 76.0
    elif debt_ratio <= 70:
        debt_s = 56.0
    elif debt_ratio <= 85:
        debt_s = 36.0
    else:
        debt_s = 22.0

    return _clamp(0.6 * roe_s + 0.4 * debt_s)


def score_risk(vol_annual: float | None) -> float:
    if vol_annual is None:
        return NEUTRAL
    return _clamp(
        _band(vol_annual, [(15, 92), (25, 78), (35, 62), (50, 42), (70, 28)], 18)
    )


def score_structure(portfolio: Portfolio) -> Tuple[float, Dict[str, float]]:
    """组合层结构分：分散度 / 第一大持仓 / 行业集中度。"""
    n = len(portfolio.holdings)
    weights = portfolio.weights()
    if n <= 0:
        return NEUTRAL, {}

    hhi = portfolio.hhi()
    min_hhi = 1.0 / n
    # HHI 归一化：越接近完全分散（1/n）得分越高
    if hhi <= min_hhi:
        hhi_s = 100.0
    else:
        hhi_s = _clamp(100.0 * (1.0 - (hhi - min_hhi) / (1.0 - min_hhi)))

    top1 = max(weights) if weights else 0.0
    if top1 <= 0.15:
        top1_s = 100.0
    elif top1 <= 0.25:
        top1_s = 82.0
    elif top1 <= 0.35:
        top1_s = 62.0
    elif top1 <= 0.50:
        top1_s = 40.0
    else:
        top1_s = 20.0

    sector_w = portfolio.sector_weights()
    max_sector = max(sector_w.values()) if sector_w else 0.0
    if max_sector <= 0.30:
        sector_s = 100.0
    elif max_sector <= 0.45:
        sector_s = 80.0
    elif max_sector <= 0.60:
        sector_s = 58.0
    elif max_sector <= 0.75:
        sector_s = 38.0
    else:
        sector_s = 20.0

    structure = _clamp(0.40 * hhi_s + 0.35 * top1_s + 0.25 * sector_s)
    detail = {
        "hhi": hhi,
        "hhi_score": hhi_s,
        "top1_weight": top1,
        "top1_score": top1_s,
        "max_sector_weight": max_sector,
        "sector_score": sector_s,
    }
    return structure, detail


def _flag_holding(h: Holding) -> List[str]:
    """个券级风险标记（只陈述事实，不给方向）。"""
    flags: List[str] = []
    if h.pnl_pct <= -20:
        flags.append(f"浮亏 {h.pnl_pct:.1f}%（深度套牢区间）")
    if h.pe is not None and h.pe <= 0:
        flags.append("PE 为负：最新口径处于亏损")
    if h.debt_ratio is not None and h.debt_ratio > 70:
        flags.append(f"资产负债率 {h.debt_ratio:.1f}%，高于 70%")
    if h.roe is not None and h.roe < 5:
        flags.append(f"ROE {h.roe:.1f}%，低于 5%")
    if h.vol_annual is not None and h.vol_annual > 40:
        flags.append(f"年化波动率 {h.vol_annual:.1f}%，波动偏高")
    if h.profit_yoy is not None and h.profit_yoy < -15:
        flags.append(f"净利同比 {h.profit_yoy:.1f}%，业绩承压")
    missing = [
        label
        for label, v in [
            ("PE", h.pe), ("PB", h.pb), ("ROE", h.roe),
            ("净利同比", h.profit_yoy), ("营收同比", h.revenue_yoy),
            ("资产负债率", h.debt_ratio), ("年化波动率", h.vol_annual),
        ]
        if v is None
    ]
    if missing:
        flags.append("数据缺失（按中性分处理）：" + "、".join(missing))
    return flags


def _flag_portfolio(portfolio: Portfolio, detail: Dict[str, float]) -> List[str]:
    flags: List[str] = []
    top1 = detail.get("top1_weight", 0.0)
    if top1 > 0.35:
        top_holding = max(portfolio.holdings, key=lambda x: x.market_value)
        flags.append(
            f"第一大持仓 {top_holding.name} 占比 {top1 * 100:.1f}%，超过 35% 集中度阈值"
        )
    max_sector = detail.get("max_sector_weight", 0.0)
    if max_sector > 0.55:
        sector = max(portfolio.sector_weights().items(), key=lambda kv: kv[1])[0]
        flags.append(f"行业「{sector}」占比 {max_sector * 100:.1f}%，行业集中度偏高")
    if len(portfolio.holdings) < 5:
        flags.append(f"持仓仅 {len(portfolio.holdings)} 只，分散度不足")
    losses = [h for h in portfolio.holdings if h.pnl < 0]
    if losses and portfolio.total_market_value > 0:
        loss_ratio = sum(h.market_value for h in losses) / portfolio.total_market_value
        if loss_ratio > 0.5:
            flags.append(f"浮亏持仓占市值 {loss_ratio * 100:.1f}%，组合整体承压")
    return flags


def _checklist(portfolio: Portfolio, detail: Dict[str, float]) -> List[str]:
    """核查清单：下一步该核实的**事实**，不是交易建议。"""
    items: List[str] = []
    worst = sorted(portfolio.holdings, key=lambda h: h.total_score)[:2]
    for h in worst:
        items.append(
            f"核实 {h.name}（{h.code}）的盈利可持续性与最新一期财报口径，"
            f"当前四维加权分 {h.total_score:.0f}"
        )
    top1 = detail.get("top1_weight", 0.0)
    if top1 > 0.35:
        items.append(
            f"确认第一大持仓占比 {top1 * 100:.1f}% 是主动选择还是历史累积结果，"
            "并写下自己能接受的单一持仓上限"
        )
    if any(h.pe is None or h.roe is None for h in portfolio.holdings):
        items.append("补齐缺失的 PE / ROE 字段后重新体检，避免中性分掩盖真实分化")
    items.append("为组合设定一个再平衡触发阈值（如单一持仓超过 X%），写成文字留存")
    return items[:5]


def grade(score: float) -> Tuple[str, str]:
    """返回 (评级, 颜色 hex)。评分用语义色，与涨跌红绿习惯区分。"""
    if score >= 80:
        return "健康", "#0EA5E9"
    if score >= 65:
        return "基本健康", "#22C55E"
    if score >= 50:
        return "亚健康", "#F59E0B"
    if score >= 35:
        return "预警", "#F97316"
    return "高危", "#EF4444"


def run_audit(portfolio: Portfolio) -> Dict:
    """执行体检，返回报告所需的全部结构化结果。"""
    for h in portfolio.holdings:
        h.scores = {
            "valuation": score_valuation(h.pe, h.pb),
            "growth": score_growth(h.profit_yoy, h.revenue_yoy),
            "quality": score_quality(h.roe, h.debt_ratio),
            "risk": score_risk(h.vol_annual),
        }
        h.flags = _flag_holding(h)

    structure, detail = score_structure(portfolio)
    weights = portfolio.weights()

    # 个券加权分（按市值加权，避免小仓位绑架总分）
    if portfolio.total_market_value > 0:
        holding_avg = sum(
            h.total_score * w for h, w in zip(portfolio.holdings, weights)
        )
    else:
        holding_avg = sum(h.total_score for h in portfolio.holdings) / len(portfolio.holdings)

    total = _clamp((1 - STRUCTURE_WEIGHT) * holding_avg + STRUCTURE_WEIGHT * structure)
    label, color = grade(total)

    dim_scores = {
        "估值": sum(h.scores["valuation"] * w for h, w in zip(portfolio.holdings, weights)),
        "成长": sum(h.scores["growth"] * w for h, w in zip(portfolio.holdings, weights)),
        "质量": sum(h.scores["quality"] * w for h, w in zip(portfolio.holdings, weights)),
        "风险": sum(h.scores["risk"] * w for h, w in zip(portfolio.holdings, weights)),
        "结构": structure,
    }

    return {
        "total_score": total,
        "grade": label,
        "color": color,
        "dim_scores": {k: round(v, 1) for k, v in dim_scores.items()},
        "structure_detail": detail,
        "holding_avg_score": round(holding_avg, 1),
        "portfolio_flags": _flag_portfolio(portfolio, detail),
        "checklist": _checklist(portfolio, detail),
        "weights": weights,
    }
