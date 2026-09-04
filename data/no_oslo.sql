WITH zones AS (
  SELECT
    lg_country_code,
    city_name,
    zone_name,
    report_date_local,
    start_datetime_local,
    SUM(session_count) AS sessions,
    SUM(transaction_count) AS transactions,
    SUM(healthy_vendor_availability_session_count) AS healthy_vendor_availability_sessions,
    SUM(availability_session_count) AS availability_session_count
  FROM fulfillment-dwh-production.pandata_datamart.pandora__agg_zone_metrics
  WHERE 1 = 1
    AND ((report_date_local BETWEEN DATE("2025-07-01") AND DATE("2025-07-31"))
     OR (report_date_local BETWEEN DATE("2026-06-01") AND DATE("2026-06-30"))
        )
    AND lg_country_code = "no"
    AND city_name = "Oslo"
  GROUP BY ALL
),

sessions AS (
  SELECT
    lg_country_code,
    lg_city_name AS city_name,
    lg_zone_name AS zone_name,
    business_report_date_local AS report_date_local,
    DATETIME_ADD(
      DATETIME_TRUNC(DATETIME(session_start_timestamp_local), HOUR),
      INTERVAL DIV(EXTRACT(MINUTE FROM DATETIME(session_start_timestamp_local)), 15) * 15 MINUTE
    ) AS start_datetime_local,
    SUM(zone_stats.mean_delay) AS mean_delay,
    COUNT(DISTINCT session_id) AS mean_delay_n
  FROM `fulfillment-dwh-production.pandata_datamart.pandora__core_sessions`
  WHERE 1 =1
    AND ((business_report_date_local BETWEEN DATE("2025-07-01") AND DATE("2025-07-31"))
      OR (business_report_date_local BETWEEN DATE("2026-06-01") AND DATE("2026-06-30"))
        )
    AND zone_stats.mean_delay IS NOT NULL
    AND lg_country_code = "no"
    AND lg_city_name = "Oslo"
  GROUP BY ALL
),

orders AS (
  SELECT
    pandora__agg_orders.lg_country_code,
    pandora__agg_orders.city_name,
    pandora__agg_orders.zone_name,
    pandora__agg_orders.created_date_local,
    DATETIME_ADD(
      DATETIME_TRUNC(pandora__agg_orders.created_at_local, HOUR),
      INTERVAL DIV(EXTRACT(MINUTE FROM pandora__agg_orders.created_at_local), 15) * 15 MINUTE
    ) AS start_datetime_local,
    FLOOR(
    SAFE_DIVIDE(
      SUM(CASE WHEN NOT pandora__agg_orders.is_preorder AND pandora__agg_orders.delivery_status = "completed" THEN pandora__agg_orders.promised_delivery_time_in_minutes END),
      COUNTIF(NOT pandora__agg_orders.is_preorder AND pandora__agg_orders.delivery_status = "completed" AND pandora__agg_orders.promised_delivery_time_in_minutes IS NOT NULL)
      )
    ) + 1 AS promised_delivery_time_bucket_min,
    COUNTIF(pandora__agg_orders.is_gross_order) AS gross_order_count,
    COUNTIF(pandora__agg_orders.is_successful) AS successful_order_count,

    SUM(CASE WHEN pandora__agg_orders.delivery_status = "completed" AND pandora__agg_orders.delivery_distance_in_meters <= outlier_threshold.upper_limit_delivery_distance_in_meters THEN delivery_distance_in_meters END) AS total_delivery_distance_in_meters,
    COUNTIF(pandora__agg_orders.delivery_status = "completed" AND pandora__agg_orders.delivery_distance_in_meters <= outlier_threshold.upper_limit_delivery_distance_in_meters) AS delivery_distance_in_meters_count,

    -- SUM(CASE WHEN pandora__agg_orders.is_successful AND NOT pandora__agg_orders.is_laas_order THEN pandora__agg_orders.user_paid_gmv_eur END) AS total_user_paid_gmv_eur
    SUM(CASE WHEN pandora__agg_orders.is_successful THEN pandora__agg_orders.df_user_paid_incl_vat_eur END) AS total_df_paid_eur,
    SUM(CASE WHEN pandora__agg_orders.is_successful AND pandora__agg_orders.delivery_type = "Own Delivery" THEN order_dps.mapped_dps_df_component.dps_surge_fee_eur END) AS total_surge_fee_eur
  FROM `fulfillment-dwh-production.pandata_datamart.pandora__agg_orders` AS pandora__agg_orders
  LEFT JOIN `fulfillment-dwh-production.pandata_datamart.pandora__order_logistics_delivery_distance_outliers` AS outlier_threshold
        ON pandora__agg_orders.global_entity_id = outlier_threshold.global_entity_id
        AND pandora__agg_orders.lg_country_code = outlier_threshold.lg_country_code
        AND pandora__agg_orders.created_date_local = outlier_threshold.created_date_local
  LEFT JOIN `fulfillment-dwh-production.pandata_datamart.pandora__order_dps` AS order_dps
         ON pandora__agg_orders.global_entity_id = order_dps.global_entity_id
        AND pandora__agg_orders.order_code = order_dps.order_code
        AND pandora__agg_orders.created_date_local = order_dps.order_date_local
  WHERE 1 = 1
    AND ((pandora__agg_orders.created_date_local BETWEEN DATE("2025-07-01") AND DATE("2025-07-31"))
      OR (pandora__agg_orders.created_date_local BETWEEN DATE("2026-06-01") AND DATE("2026-06-30"))
        )
    AND ((order_dps.order_date_local BETWEEN DATE("2025-07-01") AND DATE("2025-07-31"))
      OR (order_dps.order_date_local BETWEEN DATE("2026-06-01") AND DATE("2026-06-30"))
        )
    AND pandora__agg_orders.lg_country_code = "no"
    AND pandora__agg_orders.city_name = "Oslo"
    AND pandora__agg_orders.delivery_type = "Own Delivery"
  GROUP BY ALL
)

SELECT
  orders.lg_country_code,
  orders.city_name,
  orders.zone_name,
  orders.created_date_local,
  promised_delivery_time_bucket_min,
  SUM(orders.gross_order_count) AS gross_orders,
  SUM(orders.successful_order_count) AS successful_orders,
  SAFE_DIVIDE(
    SUM(orders.total_delivery_distance_in_meters),
    SUM(orders.delivery_distance_in_meters_count)
  ) AS distance_order_count,
  SAFE_DIVIDE(
    SUM(orders.total_surge_fee_eur),
    SUM(orders.total_df_paid_eur)
  ) AS surge_multiplier,
  SAFE_DIVIDE(
    SUM(sessions.mean_delay),
    SUM(sessions.mean_delay_n)
  ) AS mean_delay,
  SAFE_DIVIDE(
    SUM(zones.transactions),
    SUM(zones.sessions)
  ) AS cvr,
  SAFE_DIVIDE(
    SUM(zones.healthy_vendor_availability_sessions),
    SUM(zones.availability_session_count)
  ) AS healthy_vendor_availability_sessions
FROM orders
LEFT JOIN zones
       ON orders.lg_country_code = zones.lg_country_code
      AND orders.city_name = zones.city_name
      AND orders.zone_name = zones.zone_name
      AND orders.start_datetime_local = zones.start_datetime_local
LEFT JOIN sessions
       ON orders.lg_country_code = sessions.lg_country_code
      AND orders.city_name = sessions.city_name
      AND orders.zone_name = sessions.zone_name
      AND orders.start_datetime_local = sessions.start_datetime_local
GROUP BY ALL
ORDER BY 1, 2, 3, 4, 5
