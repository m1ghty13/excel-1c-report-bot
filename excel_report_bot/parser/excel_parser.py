"""Parse .xlsx sales reports into a structured ParseResult dataclass."""
import pandas as pd
from dataclasses import dataclass, field

LOW_STOCK_THRESHOLD = 5
TOP_PRODUCTS_COUNT = 5
TOP_CATEGORIES_COUNT = 3

ABC_A_THRESHOLD = 0.80   # top products covering 80% of revenue → class A
ABC_B_THRESHOLD = 0.95   # next products up to 95% → class B, rest → C

COLUMN_ALIASES: dict[str, list[str]] = {
    "product":  ["товар", "наименование", "продукт", "name", "item"],
    "quantity": ["количество", "кол-во", "qty", "count"],
    "revenue":  ["сумма", "выручка", "amount", "revenue", "продажи"],
    "stock":    ["остаток", "остатки", "stock", "balance"],
    "category": ["категория", "category", "group"],
    "date":     ["дата", "date", "день"],
}


@dataclass
class ParseResult:
    """Structured result of parsing one xlsx file."""
    file_name:      str
    revenue:        float
    positions:      int
    avg_check:      float        # revenue / len(rows), NOT revenue / unique_products
    top_products:   list[dict]   # [{"name", "revenue", "share_pct"}] top-5 by revenue
    top_categories: list[dict]   # [{"name", "revenue"}] top-3 by revenue
    low_stock:      list[str]    # product names where 0 < stock < LOW_STOCK_THRESHOLD
    zero_stock:     list[str]    # product names where stock == 0
    date_from:      str | None   # "YYYY-MM-DD" earliest date in file
    date_to:        str | None   # "YYYY-MM-DD" latest date in file
    period_days:    int | None   # (date_to - date_from).days + 1
    # ABC analysis: {"A": [...], "B": [...], "C": [...]} product names per class
    abc_analysis:   dict[str, list[str]] = field(default_factory=lambda: {"A": [], "B": [], "C": []})
    # Daily revenue: [{"date": "YYYY-MM-DD", "revenue": float}] sorted by date
    daily_revenue:  list[dict] = field(default_factory=list)

    def to_summary_dict(self) -> dict:
        """Serialize to summary_json structure stored in DB."""
        return {
            "top_products":   self.top_products,
            "low_stock":      self.low_stock,
            "zero_stock":     self.zero_stock,
            "top_categories": self.top_categories,
            "period_days":    self.period_days,
            "abc_analysis":   self.abc_analysis,
            "daily_revenue":  self.daily_revenue,
        }


def _normalize(s: str) -> str:
    """Lowercase and strip a string."""
    return str(s).lower().strip()


def _detect_columns(df_columns: list[str]) -> dict[str, str]:
    """Map logical column names to actual DataFrame column names."""
    mapping: dict[str, str] = {}
    normalized = {_normalize(c): c for c in df_columns}
    for logical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in normalized:
                mapping[logical] = normalized[alias]
                break
    return mapping


def parse_excel(file_path: str, file_name: str) -> ParseResult:
    """Parse an xlsx file and return a ParseResult."""
    df = pd.read_excel(file_path, engine="openpyxl")
    col = _detect_columns(list(df.columns))

    # Rename detected columns to logical names for uniform access
    rename_map = {v: k for k, v in col.items()}
    df = df.rename(columns=rename_map)

    # --- Core metrics ---
    df["revenue"] = pd.to_numeric(df["revenue"], errors="coerce").fillna(0)
    total_revenue = float(df["revenue"].sum())
    positions = len(df)
    # avg_check = revenue / number of rows (transactions), not unique products
    avg_check = total_revenue / positions if positions > 0 else 0.0

    # --- Top products (top-5 by revenue) ---
    if "product" in df.columns:
        product_rev = (
            df.groupby("product")["revenue"]
            .sum()
            .sort_values(ascending=False)
            .head(TOP_PRODUCTS_COUNT)
        )
        top_products = [
            {
                "name": str(name),
                "revenue": float(rev),
                "share_pct": round(float(rev) / total_revenue * 100, 1) if total_revenue else 0.0,
            }
            for name, rev in product_rev.items()
        ]
    else:
        top_products = []

    # --- Top categories (top-3 by revenue) ---
    if "category" in df.columns:
        cat_rev = (
            df.groupby("category")["revenue"]
            .sum()
            .sort_values(ascending=False)
            .head(TOP_CATEGORIES_COUNT)
        )
        top_categories = [
            {"name": str(name), "revenue": float(rev)}
            for name, rev in cat_rev.items()
        ]
    else:
        top_categories = []

    # --- ABC analysis ---
    # Sort ALL products by revenue descending, assign class by cumulative share
    abc_analysis: dict[str, list[str]] = {"A": [], "B": [], "C": []}
    if "product" in df.columns and total_revenue > 0:
        all_product_rev = (
            df.groupby("product")["revenue"]
            .sum()
            .sort_values(ascending=False)
        )
        cumulative = 0.0
        for name, rev in all_product_rev.items():
            cumulative += float(rev)
            share = cumulative / total_revenue
            if share <= ABC_A_THRESHOLD:
                abc_analysis["A"].append(str(name))
            elif share <= ABC_B_THRESHOLD:
                abc_analysis["B"].append(str(name))
            else:
                abc_analysis["C"].append(str(name))
        # Edge case: last product that pushes us past threshold still gets correct class
        # The loop handles it correctly since we check cumulative after adding

    # --- Stock alerts ---
    low_stock: list[str] = []
    zero_stock: list[str] = []
    if "stock" in df.columns and "product" in df.columns:
        df["stock"] = pd.to_numeric(df["stock"], errors="coerce").fillna(-1)
        # Per-product: use the last known stock value
        stock_by_product = df.groupby("product")["stock"].last()
        for name, stock_val in stock_by_product.items():
            if stock_val == 0:
                zero_stock.append(str(name))
            elif 0 < stock_val < LOW_STOCK_THRESHOLD:
                low_stock.append(str(name))

    # --- Date range + daily revenue ---
    date_from: str | None = None
    date_to: str | None = None
    period_days: int | None = None
    daily_revenue: list[dict] = []
    if "date" in df.columns:
        df["_date"] = pd.to_datetime(df["date"], errors="coerce")
        valid = df.dropna(subset=["_date"])
        if not valid.empty:
            d_from = valid["_date"].min()
            d_to = valid["_date"].max()
            date_from = d_from.strftime("%Y-%m-%d")
            date_to = d_to.strftime("%Y-%m-%d")
            period_days = (d_to - d_from).days + 1
            # Daily revenue: group by date, sum revenue
            daily_series = (
                valid.groupby(valid["_date"].dt.date)["revenue"]
                .sum()
                .sort_index()
            )
            daily_revenue = [
                {"date": str(d), "revenue": float(r)}
                for d, r in daily_series.items()
            ]

    return ParseResult(
        file_name=file_name,
        revenue=total_revenue,
        positions=positions,
        avg_check=avg_check,
        top_products=top_products,
        top_categories=top_categories,
        low_stock=low_stock,
        zero_stock=zero_stock,
        date_from=date_from,
        date_to=date_to,
        period_days=period_days,
        abc_analysis=abc_analysis,
        daily_revenue=daily_revenue,
    )
