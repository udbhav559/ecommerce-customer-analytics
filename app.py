import streamlit as st
import pandas as pd
import plotly.express as px
import sqlite3
from pathlib import Path
from analysis import prepare_data, DB_PATH

st.set_page_config(page_title="E-commerce Analytics", page_icon="📊", layout="wide")

st.title("📊 E-commerce Sales & Customer Analytics")
st.caption("Portfolio project using the Brazilian Olist public e-commerce dataset")

@st.cache_data
def load_tables():
    if not DB_PATH.exists():
        prepare_data()
    with sqlite3.connect(DB_PATH) as conn:
        orders = pd.read_sql_query("SELECT * FROM orders_analytics", conn)
        items = pd.read_sql_query("SELECT * FROM order_items_analytics", conn)
        rfm = pd.read_sql_query("SELECT * FROM customer_rfm", conn)
        cohorts = pd.read_sql_query("SELECT * FROM cohort_counts", conn)
    return orders, items, rfm, cohorts

try:
    orders, items, rfm, cohorts = load_tables()
except Exception as exc:
    st.error(f"Could not load the dataset: {exc}")
    st.info("Check that the six required Olist CSV files are inside the project's data/ folder.")
    st.stop()

orders["order_purchase_timestamp"] = pd.to_datetime(orders["order_purchase_timestamp"], errors="coerce")
orders["order_month"] = orders["order_purchase_timestamp"].dt.to_period("M").astype(str)
orders["delivery_days"] = pd.to_numeric(orders["delivery_days"], errors="coerce")
orders["review_score"] = pd.to_numeric(orders["review_score"], errors="coerce")
orders["merchandise_revenue"] = pd.to_numeric(orders["merchandise_revenue"], errors="coerce").fillna(0)
if "is_late" not in orders.columns:
    orders["is_late"] = (
        pd.to_datetime(orders["order_delivered_customer_date"], errors="coerce")
        >
        pd.to_datetime(orders["order_estimated_delivery_date"], errors="coerce")
    )
else:
    orders["is_late"] = (
        orders["is_late"].astype(str).str.lower().isin(["true", "1"])
    )

# Sidebar filters
st.sidebar.header("Filters")
statuses = sorted(orders["order_status"].dropna().unique().tolist())
selected_statuses = st.sidebar.multiselect("Order status", statuses, default=statuses)
cities = sorted(orders["customer_city"].dropna().unique().tolist())
selected_cities = st.sidebar.multiselect("Customer city (optional)", cities)
date_min = orders["order_purchase_timestamp"].min().date()
date_max = orders["order_purchase_timestamp"].max().date()
date_range = st.sidebar.date_input("Purchase date range", value=(date_min, date_max))

filtered = orders[orders["order_status"].isin(selected_statuses)].copy()
if selected_cities:
    filtered = filtered[filtered["customer_city"].isin(selected_cities)]
if isinstance(date_range, tuple) and len(date_range) == 2:
    start_date, end_date = date_range
    filtered = filtered[
        filtered["order_purchase_timestamp"].dt.date.between(start_date, end_date)
    ]

delivered = filtered[filtered["order_status"] == "delivered"]
total_orders = filtered["order_id"].nunique()
total_customers = filtered["customer_unique_id"].nunique()
total_sales = filtered["merchandise_revenue"].sum()
avg_order_value = delivered["merchandise_revenue"].mean() if not delivered.empty else 0
late_rate = delivered["is_late"].mean() * 100 if not delivered.empty else 0

# Navigation
page = st.sidebar.radio(
    "Dashboard section",
    ["Executive Overview", "Customer Analytics", "Product Analytics", "Delivery & Reviews"]
)

if page == "Executive Overview":
    st.subheader("Executive Sales Overview")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Merchandise sales", f"R$ {total_sales:,.0f}")
    c2.metric("Orders", f"{total_orders:,}")
    c3.metric("Unique customers", f"{total_customers:,}")
    c4.metric("Avg. delivered order value", f"R$ {avg_order_value:,.2f}")

    monthly = (
        filtered.groupby("order_month", as_index=False)
        .agg(revenue=("merchandise_revenue", "sum"), orders=("order_id", "nunique"))
        .sort_values("order_month")
    )
    col1, col2 = st.columns(2)
    with col1:
        st.plotly_chart(px.line(monthly, x="order_month", y="revenue",
                                markers=True, title="Monthly merchandise revenue",
                                labels={"order_month": "Month", "revenue": "Revenue (R$)"}),
                         use_container_width=True)
    with col2:
        st.plotly_chart(px.bar(monthly, x="order_month", y="orders",
                               title="Monthly order volume",
                               labels={"order_month": "Month", "orders": "Orders"}),
                         use_container_width=True)

    st.markdown("#### Order status distribution")
    status_df = filtered["order_status"].value_counts().rename_axis("status").reset_index(name="orders")
    st.plotly_chart(px.pie(status_df, names="status", values="orders", hole=0.45),
                    use_container_width=True)

elif page == "Customer Analytics":
    st.subheader("Customer Behaviour & Segmentation")
    delivered_ids = set(delivered["customer_unique_id"].dropna())
    rfm_filtered = rfm[rfm["customer_unique_id"].isin(delivered_ids)].copy()
    repeat_rate = (
        delivered.groupby("customer_unique_id")["order_id"].nunique().gt(1).mean() * 100
        if not delivered.empty else 0
    )
    a, b, c = st.columns(3)
    a.metric("Repeat customer rate", f"{repeat_rate:.1f}%")
    b.metric("Customers segmented", f"{len(rfm_filtered):,}")
    c.metric("Average historical spend", f"R$ {rfm_filtered['monetary'].mean():,.2f}" if not rfm_filtered.empty else "R$ 0")

    if not rfm_filtered.empty:
        seg = rfm_filtered["segment"].value_counts().rename_axis("segment").reset_index(name="customers")
        st.plotly_chart(px.bar(seg, x="segment", y="customers", title="RFM customer segments"),
                        use_container_width=True)
        st.caption("RFM = Recency (days since last purchase), Frequency (number of orders), Monetary (merchandise spend).")
        st.dataframe(rfm_filtered.sort_values("monetary", ascending=False).head(30),
                     use_container_width=True)
    else:
        st.warning("No delivered customers in the selected filters.")

    if not cohorts.empty:
        st.markdown("#### Cohort retention data")
        cohort_pivot = cohorts.pivot(index="cohort_month", columns="cohort_index", values="customers")
        sizes = cohort_pivot.iloc[:, 0]
        retention = cohort_pivot.divide(sizes, axis=0) * 100
        st.plotly_chart(px.imshow(retention, aspect="auto", color_continuous_scale="Blues",
                                  labels=dict(x="Months since first purchase", y="Cohort month", color="Retention %"),
                                  title="Customer cohort retention (%)"),
                        use_container_width=True)

elif page == "Product Analytics":
    st.subheader("Product & Category Performance")
    product_filtered = items.copy()
    product_filtered["order_purchase_timestamp"] = pd.to_datetime(
        product_filtered["order_purchase_timestamp"], errors="coerce"
    )
    if isinstance(date_range, tuple) and len(date_range) == 2:
        product_filtered = product_filtered[
            product_filtered["order_purchase_timestamp"].dt.date.between(date_range[0], date_range[1])
        ]
    category = (
        product_filtered.groupby("product_category", as_index=False)
        .agg(revenue=("price", "sum"), items_sold=("order_item_id", "count"))
        .sort_values("revenue", ascending=False)
        .head(15)
    )
    st.plotly_chart(px.bar(category.sort_values("revenue"), x="revenue", y="product_category",
                            orientation="h", title="Top 15 product categories by merchandise revenue",
                            labels={"revenue": "Revenue (R$)", "product_category": "Category"}),
                    use_container_width=True)
    st.dataframe(category, use_container_width=True)

elif page == "Delivery & Reviews":
    st.subheader("Delivery Performance & Customer Satisfaction")
    if not delivered.empty:
        avg_delivery = delivered["delivery_days"].mean()
        late_percentage = delivered["is_late"].mean() * 100
        avg_review = delivered["review_score"].mean()
    else:
        avg_delivery, late_percentage, avg_review = 0, 0, 0

    a, b, c = st.columns(3)
    a.metric("Average delivery time", f"{avg_delivery:.1f} days")
    b.metric("Late delivery rate", f"{late_percentage:.1f}%")
    c.metric("Average review score", f"{avg_review:.2f}/5")

    review_data = delivered.dropna(subset=["review_score"]).copy()
    if not review_data.empty:
        review_data["delivery_group"] = review_data["is_late"].map({True: "Late", False: "On time / unknown"})
        review_summary = review_data.groupby("delivery_group", as_index=False)["review_score"].mean()
        st.plotly_chart(px.bar(review_summary, x="delivery_group", y="review_score",
                                title="Average review score by delivery status",
                                labels={"delivery_group": "Delivery status", "review_score": "Average review score"}),
                        use_container_width=True)
        st.caption("This comparison is descriptive; it does not establish that delivery delay caused a lower review score.")
    else:
        st.info("No review data available for the selected filters.")

st.divider()
st.caption("Data source: Brazilian E-Commerce Public Dataset by Olist. Merchandise revenue excludes freight.")
