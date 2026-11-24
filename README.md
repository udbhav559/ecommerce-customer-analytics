# E-commerce Sales & Customer Analytics

An end-to-end data analytics portfolio project using the Brazilian Olist public e-commerce dataset.

## Tech stack
Python, Pandas, NumPy, SQLite, SQL, Plotly, Streamlit.

## Setup
1. Download and extract the Olist dataset from Kaggle:
   https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce
2. Put these six CSV files in `data/`:
   - `olist_orders_dataset.csv`
   - `olist_order_items_dataset.csv`
   - `olist_customers_dataset.csv`
   - `olist_products_dataset.csv`
   - `olist_order_payments_dataset.csv`
   - `olist_order_reviews_dataset.csv`
3. Create and activate a virtual environment (optional but recommended).
4. Install dependencies:
   `pip install -r requirements.txt`
5. Build the SQLite database:
   `python analysis.py`
6. Run the dashboard:
   `streamlit run app.py`

## SQL practice
The `sql/business_analysis_queries.sql` file contains 15 example business queries, including aggregations, CTEs and window functions. Run them against the generated `ecommerce.db` database using a SQLite client.

## Notes
- The project uses historical Olist data from 2016–2018.
- Merchandise revenue is calculated from item prices; freight is kept separate.
- One-to-many payment, review and item tables are aggregated before joining to the order-level table to reduce double counting.
- The cohort and RFM analyses are descriptive, not predictive.
