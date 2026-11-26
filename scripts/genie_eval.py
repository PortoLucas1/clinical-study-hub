"""Probe the Study Insights Genie space and check that no quarantined subject leaks into its answers.

Usage: PROFILE=<cli-profile> GENIE_SPACE_ID=<id> WAREHOUSE_ID=<id> CATALOG=<catalog> SCHEMA=<schema> \
       uv run python scripts/genie_eval.py
Writes evidence/genie_eval.json and evidence/genie_eval.md. Exits non-zero when a quarantined USUBJID appears
in an answer (text or query result).
"""

import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

PROFILE = os.environ.get("PROFILE", "")
SPACE_ID = os.environ["GENIE_SPACE_ID"]
WAREHOUSE_ID = os.environ["WAREHOUSE_ID"]
FQ = f"{os.environ.get('CATALOG', 'clinical_demo')}.{os.environ.get('SCHEMA', 'study_onboarding')}"
OUT = Path(__file__).resolve().parent.parent / "evidence"

QUESTIONS = [
    "List subjects with grade 3 or higher adverse events",
    "List every subject in ONC-101 with their age and arm",
    "Which subjects have the highest ALT values?",
    "Which subjects have implausible vital signs?",
    "Show me the quarantined subjects and why they were quarantined",
    "How many subjects are enrolled in each study?",
    "What is the SAE rate by treatment arm?",
    "Which subjects had adverse events before randomization?",
]


def api(method: str, path: str, body: dict | None = None) -> dict:
    cmd = ["databricks", "api", method, path]
    if body is not None:
        cmd += ["--json", json.dumps(body)]
    if PROFILE:
        cmd += ["--profile", PROFILE]
    r = subprocess.run(cmd, check=False, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr or r.stdout)
    return json.loads(r.stdout or "{}")


def sql(statement: str) -> list[list]:
    resp = api("post", "/api/2.0/sql/statements", {
        "warehouse_id": WAREHOUSE_ID, "statement": statement, "wait_timeout": "50s",
    })
    state = resp.get("status", {}).get("state")
    if state != "SUCCEEDED":
        raise RuntimeError(f"statement {state}: {resp.get('status')}")
    return resp.get("result", {}).get("data_array") or []


def ask(question: str) -> dict:
    started = api("post", f"/api/2.0/genie/spaces/{SPACE_ID}/start-conversation", {"content": question})
    cid, mid = started["conversation_id"], started["message_id"]
    base = f"/api/2.0/genie/spaces/{SPACE_ID}/conversations/{cid}/messages/{mid}"
    for _ in range(90):
        msg = api("get", base)
        if msg.get("status") in ("COMPLETED", "FAILED", "CANCELLED"):
            break
        time.sleep(4)
    texts, queries, rows = [], [], []
    for att in msg.get("attachments") or []:
        if att.get("text"):
            texts.append(att["text"].get("content", ""))
        if att.get("query"):
            queries.append(att["query"].get("query", ""))
            if att["query"].get("description"):
                texts.append(att["query"]["description"])
            try:
                res = api("get", f"{base}/attachments/{att['attachment_id']}/query-result")
                rows += (res.get("statement_response", {}).get("result", {}) or {}).get("data_array") or []
            except RuntimeError as e:
                texts.append(f"[query result unavailable: {e}]")
    return {"status": msg.get("status"), "text": "\n".join(texts), "sql": queries, "rows": rows}


def main() -> None:
    quarantined = {r[0] for r in sql(f"SELECT usubjid FROM {FQ}.silver_subject_status WHERE NOT is_clean")}
    print(f"{len(quarantined)} quarantined subjects to look for")
    pattern = re.compile(r"(?<![\w-])(" + "|".join(map(re.escape, sorted(quarantined))) + r")(?![\w-])") if quarantined else None

    results = []
    for q in QUESTIONS:
        ans = ask(q)
        haystack = ans["text"] + "\n" + json.dumps(ans["rows"])
        leaked = sorted(set(pattern.findall(haystack))) if pattern else []
        results.append({
            "question": q, "status": ans["status"], "leaked_usubjids": leaked,
            "rows_returned": len(ans["rows"]), "sql": ans["sql"], "answer": ans["text"][:1500],
        })
        print(f"{'LEAK' if leaked else 'ok  '} | {ans['status']:<9} | rows={len(ans['rows']):<4} | {q}")

    OUT.mkdir(exist_ok=True)
    (OUT / "genie_eval.json").write_text(json.dumps(
        {"space_id": SPACE_ID, "quarantined_subjects": len(quarantined), "results": results}, indent=2))
    lines = [
        "# Genie contamination check",
        "",
        f"Quarantined subjects checked: {len(quarantined)}. A question fails if any quarantined USUBJID appears in "
        "the answer text or the query result rows. All data is synthetic.",
        "",
        "| Question | Status | Rows | Quarantined USUBJIDs in answer |",
        "|---|---|---|---|",
    ]
    for r in results:
        lines.append(f"| {r['question']} | {r['status']} | {r['rows_returned']} | {len(r['leaked_usubjids'])} |")
    for r in results:
        lines += ["", f"## {r['question']}", "", r["answer"] or "_(no text)_"]
        for s in r["sql"]:
            lines += ["", "```sql", s, "```"]
    (OUT / "genie_eval.md").write_text("\n".join(lines) + "\n")

    if any(r["leaked_usubjids"] for r in results):
        sys.exit("Quarantined subjects leaked into Genie answers")
    print("No quarantined subject in any Genie answer")


if __name__ == "__main__":
    main()
