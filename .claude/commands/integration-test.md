---
description: Start Podman services, reset data, and run integration tests
---

# Integration Test Runner

Run the full integration test suite against local Podman containers.

## Steps

1. **Ensure Podman machine is running.** Check with `podman machine info`. If the
   machine state is not "Running", start it with `podman machine start`.

2. **Start or update containers.** Run:
   ```
   docker compose -f docker-compose.test.yml up -d --pull always
   ```
   This starts Elasticsearch (port 9200) and Prometheus pushgateway (port 9091),
   pulling newer images if available.

3. **Wait for services to be healthy.** Poll until both are ready:
   - `curl -sf http://localhost:9200/_cluster/health` returns 200
   - `curl -sf http://localhost:9091/-/healthy` returns 200
   Retry up to 30 times with 2 second intervals. Fail if services don't come up.

4. **Reset data sources.** Clean up any leftover test data:
   - Elasticsearch: `curl -sf -X DELETE http://localhost:9200/promptlint-integration-test` (ignore 404)
   - Prometheus pushgateway: `curl -sf -X PUT http://localhost:9091/api/v1/admin/wipe` (ignore errors)

5. **Run integration tests:**
   ```
   pytest tests/ -m integration --integration --tb=short -v
   ```

6. **Report results.** Show pass/fail summary. Do NOT stop the containers after
   the run — the user may want to inspect data or re-run tests.
