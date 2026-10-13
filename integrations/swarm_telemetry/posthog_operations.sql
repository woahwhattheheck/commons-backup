-- Run as a HogQLQuery in the existing PostHog project.
-- This view covers the last seven days of retained operational metadata.
-- Stable event IDs remove replay copies before per-operation aggregation.
WITH observations AS (
    SELECT DISTINCT
        uuid,
        event,
        distinct_id,
        properties.source_event_id_sha256 AS source_event_id,
        coalesce(properties.operation_id_sha256, '') AS operation_id,
        coalesce(properties.source, 'unknown') AS source,
        coalesce(properties.provider, properties.source, 'unknown') AS provider,
        coalesce(properties.capability, 'unspecified') AS capability,
        coalesce(properties.status, 'unknown') AS status,
        timestamp,
        properties.observed_at AS observed_at,
        toFloat(properties.duration_ms) AS duration_ms,
        toFloat(properties.latency_ms) AS latency_ms,
        toFloat(properties.request_count) AS request_count,
        properties.cache_hit AS cache_hit
    FROM events
    WHERE event = 'commons_swarm_operation'
      AND distinct_id = 'commons-swarm-operations'
      AND timestamp >= now() - INTERVAL 7 DAY
      AND properties.source_event_id_sha256 IS NOT NULL
), operations AS (
    SELECT
        source,
        provider,
        capability,
        if(operation_id = '', concat('event:', source_event_id),
           concat('operation:', operation_id)) AS operation_key,
        max(if(operation_id = '', 0, 1)) AS has_operation_id,
        count() AS observation_count,
        argMax(status, tuple(timestamp, observed_at, source_event_id)) AS latest_status,
        argMax(duration_ms, tuple(timestamp, observed_at, source_event_id)) AS duration_ms,
        argMax(latency_ms, tuple(timestamp, observed_at, source_event_id)) AS latency_ms,
        argMax(request_count, tuple(timestamp, observed_at, source_event_id)) AS request_count,
        argMax(cache_hit, tuple(timestamp, observed_at, source_event_id)) AS cache_hit,
        max(if(status IN ('rate_limit', 'rate_limited', 'throttled'), 1, 0)) AS saw_rate_limit,
        max(if(status IN ('recovered', 'rate_limit_recovered'), 1, 0)) AS saw_recovery
    FROM observations
    GROUP BY source, provider, capability, operation_key
)
SELECT
    source,
    provider,
    capability,
    sum(observation_count) AS retained_observations,
    countIf(has_operation_id = 1) AS distinct_operation_ids,
    countIf(has_operation_id = 0) AS observations_without_operation_id,
    countIf(has_operation_id = 1 AND latest_status IN
        ('completed', 'complete', 'succeeded', 'success', 'merged', 'done')) AS completed_operations,
    countIf(has_operation_id = 0 AND latest_status IN
        ('completed', 'complete', 'succeeded', 'success', 'merged', 'done')) AS completed_observations_without_operation_id,
    countIf(latest_status IN ('failed', 'error', 'cancelled', 'canceled')) AS failed_or_cancelled_groups,
    countIf(latest_status IN ('deferred', 'rate_limit', 'rate_limited', 'throttled')) AS deferred_groups,
    countIf(latest_status = 'uncertain') AS uncertain_groups,
    countIf(saw_rate_limit = 1) AS groups_with_observed_rate_limit,
    countIf(saw_recovery = 1) AS groups_with_observed_recovery,
    countIf(duration_ms IS NOT NULL) AS duration_samples,
    if(countIf(duration_ms IS NOT NULL) = 0, NULL, avg(duration_ms)) AS mean_duration_ms,
    if(countIf(duration_ms IS NOT NULL) = 0, NULL, max(duration_ms)) AS max_duration_ms,
    countIf(latency_ms IS NOT NULL) AS latency_samples,
    if(countIf(latency_ms IS NOT NULL) = 0, NULL, avg(latency_ms)) AS mean_latency_ms,
    if(countIf(latency_ms IS NOT NULL) = 0, NULL, max(latency_ms)) AS max_latency_ms,
    countIf(cache_hit IS NOT NULL) AS cache_samples,
    if(countIf(cache_hit IS NOT NULL) = 0, NULL,
       countIf(cache_hit = true) * 1.0 / countIf(cache_hit IS NOT NULL)) AS cache_hit_fraction,
    countIf(request_count IS NOT NULL) AS request_count_samples,
    if(countIf(request_count IS NOT NULL) = 0, NULL,
       sum(request_count)) AS sum_latest_reported_request_counts
FROM operations
GROUP BY source, provider, capability
ORDER BY retained_observations DESC, source, provider, capability
LIMIT 200
