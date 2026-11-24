-- 1. Total merchandise revenue and orders
SELECT
    ROUND(SUM(merchandise_revenue), 2) AS merchandise_revenue,
    COUNT(DISTINCT order_id) AS total_orders
FROM orders_analytics;

-- 2. Monthly merchandise revenue
SELECT
    order_month,
    ROUND(SUM(merchandise_revenue), 2) AS revenue
FROM orders_analytics
GROUP BY order_month
ORDER BY order_month;

-- 3. Average order value for delivered orders
SELECT
    ROUND(AVG(merchandise_revenue), 2) AS average_order_value
FROM orders_analytics
WHERE order_status = 'delivered';

-- 4. Order status distribution
SELECT order_status, COUNT(*) AS order_count
FROM orders_analytics
GROUP BY order_status
ORDER BY order_count DESC;

-- 5. Top customer cities by number of orders
SELECT customer_city, COUNT(DISTINCT order_id) AS orders
FROM orders_analytics
GROUP BY customer_city
ORDER BY orders DESC
LIMIT 10;

-- 6. Repeat customers (more than one delivered order)
SELECT COUNT(*) AS repeat_customers
FROM (
    SELECT customer_unique_id
    FROM orders_analytics
    WHERE order_status = 'delivered'
    GROUP BY customer_unique_id
    HAVING COUNT(DISTINCT order_id) > 1
);

-- 7. Top customers by merchandise spend
SELECT customer_unique_id,
       ROUND(SUM(merchandise_revenue), 2) AS total_spend
FROM orders_analytics
WHERE order_status = 'delivered'
GROUP BY customer_unique_id
ORDER BY total_spend DESC
LIMIT 20;

-- 8. Average delivery days by customer state
SELECT customer_state,
       ROUND(AVG(delivery_days), 2) AS avg_delivery_days
FROM orders_analytics
WHERE order_status = 'delivered'
  AND delivery_days IS NOT NULL
GROUP BY customer_state
ORDER BY avg_delivery_days;

-- 9. Late delivery percentage
SELECT
    ROUND(100.0 * SUM(CASE WHEN is_late = 1 THEN 1 ELSE 0 END)
          / NULLIF(COUNT(*), 0), 2) AS late_delivery_pct
FROM orders_analytics
WHERE order_status = 'delivered';

-- 10. Average review score by late-delivery status
SELECT
    CASE WHEN is_late = 1 THEN 'Late' ELSE 'On time / unknown' END AS delivery_status,
    ROUND(AVG(review_score), 2) AS avg_review_score
FROM orders_analytics
WHERE order_status = 'delivered'
  AND review_score IS NOT NULL
GROUP BY delivery_status;

-- 11. Top product categories by merchandise revenue
SELECT product_category,
       ROUND(SUM(price), 2) AS category_revenue,
       COUNT(*) AS items_sold
FROM order_items_analytics
GROUP BY product_category
ORDER BY category_revenue DESC
LIMIT 15;

-- 12. RFM customer segments
SELECT segment,
       COUNT(*) AS customers,
       ROUND(AVG(monetary), 2) AS average_monetary_value
FROM customer_rfm
GROUP BY segment
ORDER BY customers DESC;

-- 13. Monthly order count using a window function
SELECT
    order_month,
    COUNT(DISTINCT order_id) AS monthly_orders,
    SUM(COUNT(DISTINCT order_id)) OVER (
        ORDER BY order_month
        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
    ) AS cumulative_orders
FROM orders_analytics
GROUP BY order_month
ORDER BY order_month;

-- 14. Rank customer states by merchandise revenue
WITH state_revenue AS (
    SELECT customer_state,
           SUM(merchandise_revenue) AS revenue
    FROM orders_analytics
    GROUP BY customer_state
)
SELECT customer_state,
       ROUND(revenue, 2) AS revenue,
       DENSE_RANK() OVER (ORDER BY revenue DESC) AS revenue_rank
FROM state_revenue
ORDER BY revenue_rank;

-- 15. Customers with multiple delivered orders and their order frequency
SELECT customer_unique_id,
       COUNT(DISTINCT order_id) AS delivered_orders
FROM orders_analytics
WHERE order_status = 'delivered'
GROUP BY customer_unique_id
HAVING COUNT(DISTINCT order_id) > 1
ORDER BY delivered_orders DESC;
