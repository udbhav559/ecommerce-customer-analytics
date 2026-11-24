from pathlib import Path
import sqlite3
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "ecommerce.db"

FILES = {
    "orders": "olist_orders_dataset.csv",
    "items": "olist_order_items_dataset.csv",
    "customers": "olist_customers_dataset.csv",
    "products": "olist_products_dataset.csv",
    "payments": "olist_order_payments_dataset.csv",
    "reviews": "olist_order_reviews_dataset.csv",
}

def load_csv(name):
    path = DATA_DIR / FILES[name]
    if not path.exists():
        raise FileNotFoundError(
            f"Missing {path.name}. Download the Olist dataset and place it in {DATA_DIR}"
        )
    return pd.read_csv(path)

def prepare_data():
    orders = load_csv("orders")
    items = load_csv("items")
    customers = load_csv("customers")
    products = load_csv("products")
    payments = load_csv("payments")
    reviews = load_csv("reviews")
    # Load English product category translations
    translation = pd.read_csv(
        DATA_DIR / "product_category_name_translation.csv"
    )

    # Merge English names into the products table
    products = products.merge(
        translation,
        on="product_category_name",
        how="left"
    )
    print(products[
    ["product_category_name", "product_category_name_english"]
    ].head(10))

    # Parse timestamps; invalid or missing values become NaT.
    date_cols = [
        "order_purchase_timestamp",
        "order_delivered_customer_date",
        "order_estimated_delivery_date",
        "order_approved_at",
    ]
    for col in date_cols:
        if col in orders.columns:
            orders[col] = pd.to_datetime(orders[col], errors="coerce")

    # Keep item-level data at one row per order item.
    items["price"] = pd.to_numeric(items["price"], errors="coerce").fillna(0)
    items["freight_value"] = pd.to_numeric(items["freight_value"], errors="coerce").fillna(0)

    # Aggregate one-to-many tables before joining to avoid multiplying order rows.
    order_value = (
        items.groupby("order_id", as_index=False)
        .agg(
            merchandise_revenue=("price", "sum"),
            freight_revenue=("freight_value", "sum"),
            item_count=("order_item_id", "count"),
        )
    )

    payment_summary = (
        payments.groupby("order_id", as_index=False)
        .agg(payment_total=("payment_value", "sum"))
    )

    review_summary = (
        reviews.groupby("order_id", as_index=False)
        .agg(
            review_score=("review_score", "mean"),
            review_count=("review_id", "nunique"),
        )
    )

    # Product categories are translated in the Olist product category translation file.
    # The English category column is optional; fall back to the original category.
    category_col = (
        "product_category_name_english"
        if "product_category_name_english" in products.columns
        else "product_category_name"
    )
    products_small = products[["product_id", category_col]].rename(
        columns={category_col: "product_category"}
    )

    item_products = items.merge(products_small, on="product_id", how="left")
    item_products["product_category"] = item_products["product_category"].fillna("Unknown")
    category_summary = (
        item_products.groupby("order_id", as_index=False)
        .agg(product_categories=("product_category", lambda s: ", ".join(sorted(set(s.astype(str))))))
    )

    # Build an order-level analytical table.
    df = (
        orders.merge(customers[["customer_id", "customer_unique_id", "customer_city", "customer_state"]],
                     on="customer_id", how="left")
        .merge(order_value, on="order_id", how="left")
        .merge(payment_summary, on="order_id", how="left")
        .merge(review_summary, on="order_id", how="left")
        .merge(category_summary, on="order_id", how="left")
    )

    for col in ["merchandise_revenue", "freight_revenue", "item_count", "payment_total"]:
        df[col] = df[col].fillna(0)

    df["order_purchase_timestamp"] = pd.to_datetime(
        df["order_purchase_timestamp"], errors="coerce"
    )
    df["order_month"] = df["order_purchase_timestamp"].dt.to_period("M").astype(str)
    df["delivery_days"] = (
        pd.to_datetime(df["order_delivered_customer_date"], errors="coerce")
        - pd.to_datetime(df["order_purchase_timestamp"], errors="coerce")
    ).dt.total_seconds() / 86400

    df["estimated_delivery_days"] = (
        pd.to_datetime(df["order_estimated_delivery_date"], errors="coerce")
        - pd.to_datetime(df["order_purchase_timestamp"], errors="coerce")
    ).dt.total_seconds() / 86400

    delivered_date = pd.to_datetime(
    df["order_delivered_customer_date"], errors="coerce"
)

    estimated_date = pd.to_datetime(
        df["order_estimated_delivery_date"], errors="coerce"
    )

    df["delivery_status"] = np.select(
        [
            delivered_date.isna(),
            delivered_date > estimated_date
        ],
        [
            "Unknown",
            "Late"
        ],
        default="On time"
    )

    df["review_score"] = pd.to_numeric(df["review_score"], errors="coerce")
    df["customer_unique_id"] = df["customer_unique_id"].fillna("Unknown")

    # Keep only orders with a valid purchase date for time-based analysis.
    df = df[df["order_purchase_timestamp"].notna()].copy()

    # Create an order-item-level table for category and product analysis.
    item_detail = (
        items.merge(orders[["order_id", "order_purchase_timestamp", "order_status"]],
                    on="order_id", how="left")
        .merge(products_small, on="product_id", how="left")
    )
    item_detail["product_category"] = item_detail["product_category"].fillna("Unknown")
    item_detail["price"] = pd.to_numeric(item_detail["price"], errors="coerce").fillna(0)
    item_detail["order_purchase_timestamp"] = pd.to_datetime(
        item_detail["order_purchase_timestamp"], errors="coerce"
    )
    item_detail["order_month"] = item_detail["order_purchase_timestamp"].dt.to_period("M").astype(str)

    # RFM is calculated from delivered orders and merchandise revenue.
    delivered = df[df["order_status"] == "delivered"].copy()
    if delivered.empty:
        delivered = df.copy()

    snapshot_date = delivered["order_purchase_timestamp"].max() + pd.Timedelta(days=1)
    rfm = (
        delivered.groupby("customer_unique_id")
        .agg(
            recency=("order_purchase_timestamp", lambda x: (snapshot_date - x.max()).days),
            frequency=("order_id", "nunique"),
            monetary=("merchandise_revenue", "sum"),
        )
        .reset_index()
    )

    # Quantile scoring with duplicate-edge handling for small/tied datasets.
    def score_series(series, labels, ascending=True):
        ranked = series.rank(method="first", ascending=ascending)
        return pd.qcut(ranked, q=5, labels=labels).astype(int)

    if len(rfm) >= 5:
        rfm["R_score"] = score_series(rfm["recency"], [5, 4, 3, 2, 1], ascending=True)
        rfm["F_score"] = score_series(rfm["frequency"], [1, 2, 3, 4, 5], ascending=True)
        rfm["M_score"] = score_series(rfm["monetary"], [1, 2, 3, 4, 5], ascending=True)
        rfm["RFM_score"] = rfm[["R_score", "F_score", "M_score"]].sum(axis=1)
        rfm["segment"] = np.select(
            [
                rfm["RFM_score"] >= 13,
                (rfm["RFM_score"] >= 10) & (rfm["RFM_score"] < 13),
                (rfm["RFM_score"] >= 7) & (rfm["RFM_score"] < 10),
            ],
            ["Champions", "Loyal / Potential Loyal", "Needs Attention"],
            default="At Risk",
        )
    else:
        rfm["segment"] = "Insufficient data"

    # Cohort month: first purchase month for each customer.
    customer_first = (
        df.groupby("customer_unique_id")["order_purchase_timestamp"]
        .min().dt.to_period("M")
        .astype(str)
        .rename("cohort_month")
    )
    cohort_orders = df[["customer_unique_id", "order_purchase_timestamp"]].copy()
    cohort_orders["order_month"] = cohort_orders["order_purchase_timestamp"].dt.to_period("M").astype(str)
    cohort_orders = cohort_orders.join(customer_first, on="customer_unique_id")
    cohort_orders["order_month_period"] = pd.PeriodIndex(cohort_orders["order_month"], freq="M")
    cohort_orders["cohort_period"] = pd.PeriodIndex(cohort_orders["cohort_month"], freq="M")
    cohort_orders["cohort_index"] = (
        (cohort_orders["order_month_period"].dt.year - cohort_orders["cohort_period"].dt.year) * 12
        + cohort_orders["order_month_period"].dt.month
        - cohort_orders["cohort_period"].dt.month
        + 1
    )
    cohort_counts = (
        cohort_orders.groupby(["cohort_month", "cohort_index"])["customer_unique_id"]
        .nunique()
        .reset_index(name="customers")
    )
    cohort_pivot = cohort_counts.pivot(
        index="cohort_month", columns="cohort_index", values="customers"
    )
    cohort_sizes = cohort_pivot.iloc[:, 0]
    retention = cohort_pivot.divide(cohort_sizes, axis=0)

    # Save tables for SQL practice and dashboard use.
    with sqlite3.connect(DB_PATH) as conn:
        df.to_sql("orders_analytics", conn, if_exists="replace", index=False)
        item_detail.to_sql("order_items_analytics", conn, if_exists="replace", index=False)
        rfm.to_sql("customer_rfm", conn, if_exists="replace", index=False)
        cohort_counts.to_sql("cohort_counts", conn, if_exists="replace", index=False)

    return df, item_detail, rfm, retention

if __name__ == "__main__":
    print("Preparing Olist data...")
    orders_df, items_df, rfm_df, retention_df = prepare_data()
    print(f"Saved database: {DB_PATH}")
    print(f"Orders analysed: {len(orders_df):,}")
    print(f"Unique customers: {orders_df['customer_unique_id'].nunique():,}")
    print(f"RFM customers: {len(rfm_df):,}")
    print("Done. Run: streamlit run app.py")
