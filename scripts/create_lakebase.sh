#!/usr/bin/env bash
# Create the Lakebase Postgres (Autoscaling) project that stores Study Hub submissions and approvals.
set -euo pipefail
PROFILE="${PROFILE:-DEFAULT}"
PROJECT_ID="${PROJECT_ID:-study-hub}"

if ! databricks postgres get-project "projects/${PROJECT_ID}" --profile "$PROFILE" >/dev/null 2>&1; then
  databricks postgres create-project "$PROJECT_ID" \
    --json '{"spec": {"display_name": "Clinical Study Hub"}}' \
    --profile "$PROFILE"
fi

databricks postgres list-branches "projects/${PROJECT_ID}" --profile "$PROFILE" -o json
databricks postgres list-databases "projects/${PROJECT_ID}/branches/production" --profile "$PROFILE" -o json
