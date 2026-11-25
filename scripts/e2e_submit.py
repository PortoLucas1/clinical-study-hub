"""Drive the Study Hub app API end to end: create -> upload -> submit -> approve.

Usage: uv run python scripts/e2e_submit.py data/samples/CARD-202_study_package.zip [--no-approve]
Requires DATABRICKS_APP_URL and a bearer token in DATABRICKS_TOKEN (databricks auth token).
"""

import json
import os
import re
import sys
import urllib.request
import zipfile
from pathlib import Path

DOMAINS = {
    "demographics": "dm", "adverse_events": "ae", "vital_signs": "vs", "exposure": "ex",
    "disposition": "ds", "site_visits": "sv", "central_lab_results": "lb", "study_metadata": "meta",
}


def call(method: str, path: str, body: bytes | None = None, headers: dict | None = None):
    req = urllib.request.Request(os.environ["DATABRICKS_APP_URL"] + path, data=body, method=method)
    req.add_header("Authorization", f"Bearer {os.environ['DATABRICKS_TOKEN']}")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read() or b"{}")


def main(zip_path: str, approve: bool) -> None:
    path = Path(zip_path)
    with zipfile.ZipFile(path) as z:
        manifest = [
            {"path": i.filename, "size": i.file_size,
             "domain": DOMAINS.get(re.sub(r"\.[^.]+$", "", i.filename.split("/")[-1]).lower())}
            for i in z.infolist() if not i.is_dir()
        ]
        meta_name = next(n for n in z.namelist() if n.endswith("study_metadata.json"))
        meta = json.loads(z.read(meta_name))

    created = call("POST", "/api/submissions", json.dumps({
        "study_id": meta["study_id"], "file_name": path.name, "file_size": path.stat().st_size,
        "study_title": meta.get("title"), "phase": meta.get("phase"), "indication": meta.get("indication"),
        "therapeutic_area": meta.get("therapeutic_area"), "sponsor": meta.get("sponsor"),
        "notes": "Automated end-to-end validation", "manifest": manifest,
    }).encode(), {"Content-Type": "application/json"})
    sid = created["submission_id"]
    print("created", sid)

    call("POST", f"/api/files/files/upload?path={urllib.request.quote(created['upload_path'])}", path.read_bytes(),
         {"Content-Type": "application/zip"})
    print("uploaded", created["upload_path"])
    print("submitted", call("POST", f"/api/submissions/{sid}/submit")["status"])

    if approve:
        approved = call("POST", f"/api/submissions/{sid}/approve", b'{"comment":"Package complete, approved for processing"}',
                        {"Content-Type": "application/json", "x-demo-persona": "admin"})
        print("approved", approved["status"], approved.get("run_url"))


if __name__ == "__main__":
    main(sys.argv[1], "--no-approve" not in sys.argv)
