"""数据模型：持仓与组合层指标。

设计原则：
1. 纯标准库，不引入任何第三方依赖，保证零配置可运行。
2. 所有金额单位为人民币元，比率类字段为百分数（如 roe=15.2 表示 15.2%）。
3. 输入允许缺失：缺失字段用 None 表示，评分时按中性值处理并在报告中标注。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional


# CSV 列名 -> 字段类型。float 字段允许为空。
CSV_SCHEMA: Dict[str, type] = {
    "code": str,
    "name": str,
    "sector": str,
    "shares": float,
    "cost": float,      # 买入成本价（每股）
    "price": float,     # 现价（每股）
    "pe": float,        # 市盈率（可为空）
    "pb": float,        # 市净率（可为空）
    "roe": float,       # 净资产收益率 %
    "profit_yoy": float,    # 净利同比 %
    "revenue_yoy": float,   # 营收同比 %
    "debt_ratio": float,    # 资产负债率 %
    "vol_annual": float,    # 年化波动率 %
}

REQUIRED_COLUMNS = ["code", "name", "sector", "shares", "cost", "price"]


class DataError(ValueError):
    """输入数据不合格。"""


@dataclass
class Holding:
    code: str
    name: str
    sector: str
    shares: float
    cost: float
    price: float
    pe: Optional[float] = None
    pb: Optional[float] = None
    roe: Optional[float] = None
    profit_yoy: Optional[float] = None
    revenue_yoy: Optional[float] = None
    debt_ratio: Optional[float] = None
    vol_annual: Optional[float] = None
    scores: Dict[str, float] = field(default_factory=dict)
    flags: List[str] = field(default_factory=list)

    @property
    def market_value(self) -> float:
        return self.shares * self.price

    @property
    def cost_value(self) -> float:
        return self.shares * self.cost

    @property
    def pnl(self) -> float:
        return self.market_value - self.cost_value

    @property
    def pnl_pct(self) -> float:
        if self.cost_value == 0:
            return 0.0
        return self.pnl / self.cost_value * 100.0

    @property
    def total_score(self) -> float:
        """个券总分 = 四维加权（不含组合层结构分）。"""
        w = {"valuation": 0.30, "growth": 0.20, "quality": 0.30, "risk": 0.20}
        if not self.scores:
            return 0.0
        return sum(self.scores.get(k, 0.0) * v for k, v in w.items())


@dataclass
class Portfolio:
    holdings: List[Holding]

    @property
    def total_market_value(self) -> float:
        return sum(h.market_value for h in self.holdings)

    @property
    def total_cost_value(self) -> float:
        return sum(h.cost_value for h in self.holdings)

    @property
    def total_pnl(self) -> float:
        return self.total_market_value - self.total_cost_value

    @property
    def total_pnl_pct(self) -> float:
        if self.total_cost_value == 0:
            return 0.0
        return self.total_pnl / self.total_cost_value * 100.0

    def weights(self) -> List[float]:
        total = self.total_market_value
        if total <= 0:
            return [0.0] * len(self.holdings)
        return [h.market_value / total for h in self.holdings]

    def sector_weights(self) -> Dict[str, float]:
        total = self.total_market_value
        out: Dict[str, float] = {}
        if total <= 0:
            return out
        for h in self.holdings:
            out[h.sector] = out.get(h.sector, 0.0) + h.market_value / total
        return out

    def hhi(self) -> float:
        """赫芬达尔指数：sum(w^2)，取值 [1/n, 1]，越大越集中。"""
        ws = self.weights()
        return sum(w * w for w in ws)


def load_holdings(path: str) -> Portfolio:
    """从 CSV 读取持仓。缺失字段填 None，不做任何金额假设。"""
    with open(path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            raise DataError("CSV 为空或缺少表头")
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            raise DataError(f"CSV 缺少必需列: {', '.join(missing)}")

        holdings: List[Holding] = []
        for i, row in enumerate(reader, start=2):
            try:
                holding = Holding(
                    code=(row.get("code") or "").strip(),
                    name=(row.get("name") or "").strip(),
                    sector=(row.get("sector") or "未分类").strip(),
                    shares=float(row["shares"]),
                    cost=float(row["cost"]),
                    price=float(row["price"]),
                    pe=_opt_float(row.get("pe")),
                    pb=_opt_float(row.get("pb")),
                    roe=_opt_float(row.get("roe")),
                    profit_yoy=_opt_float(row.get("profit_yoy")),
                    revenue_yoy=_opt_float(row.get("revenue_yoy")),
                    debt_ratio=_opt_float(row.get("debt_ratio")),
                    vol_annual=_opt_float(row.get("vol_annual")),
                )
            except (TypeError, ValueError) as exc:
                raise DataError(f"第 {i} 行数据无法解析: {exc}") from exc
            if holding.shares <= 0 or holding.price <= 0:
                raise DataError(f"第 {i} 行 shares/price 必须为正数")
            holdings.append(holding)

    if not holdings:
        raise DataError("CSV 中没有任何持仓记录")
    return Portfolio(holdings)


def _opt_float(raw: Optional[str]) -> Optional[float]:
    if raw is None:
        return None
    s = str(raw).strip()
    if s == "" or s.lower() in {"na", "none", "null", "-"}:
        return None
    return float(s)


def iter_holdings(portfolio: Portfolio) -> Iterable[Holding]:
    return portfolio.holdings
