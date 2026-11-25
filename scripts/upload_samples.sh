#!/usr/bin/env bash
# Generate synthetic study packages and upload them to the samples volume.
set -euo pipefail
PROFILE="${PROFILE:-DEFAULT}"
CATALOG="${CATALOG:-clinical_demo}"
SCHEMA="${SCHEMA:-study_onboarding}"
cd "$(dirname "$0")/.."

uv run --with openpyxl python src/data_gen/generate_studies.py --out data/samples
for f in data/samples/*.zip; do
  databricks fs cp --overwrite "$f" "dbfs:/Volumes/${CATALOG}/${SCHEMA}/samples/$(basename "$f")" --profile "$PROFILE"
done
databricks fs ls "dbfs:/Volumes/${CATALOG}/${SCHEMA}/samples" --profile "$PROFILE"
