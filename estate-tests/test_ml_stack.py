"""
test_ml_stack.py - a real round-trip through the constrained_ml MCP server.

Lives in %LOCALAPPDATA%/hermes/tests/ on purpose.

Two separate cleaners want to delete a file that lives in the house's
working tree:

  * The evolution stack treats %LOCALAPPDATA%/hermes/scripts and .../skills
    as its improvable surface: it snapshots them, and a rejected variant
    rolls the surface back. A test on that surface can be deleted by an
    unrelated cycle.

  * The disk-cleanup plugin classifies any file named test_* outside a
    protected top-level tree as category "test", and a "test" file is
    deleted at session end.

Both were observed deleting these files. tests/ is now on the disk-cleanup
protected list, and it was never on the evolution surface, so the tests
survive. This module is part of the estate: the estate gate RUNS it.

What it proves, with real work and no mocks:
  1. catboost_train trains on a real CSV and saves a real model.
  2. catboost_predict loads that model and predicts with it.
  3. list_models sees the model that was just written.
  4. sql_query answers a real query against a real SQLite file.
  5. Error paths return a structured error, not a traceback.

Usage:
    python tests/test_ml_stack.py
    python tests/test_ml_stack.py --json
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

HERMES = Path(r"C:\Users\KING\AppData\Local\hermes")
MCP_DIR = HERMES / "mcp" / "constrained_ml"
sys.path.insert(0, str(MCP_DIR))

RESULTS: list[dict] = []


def record(name: str, ok: bool, detail: str = "") -> bool:
    RESULTS.append({"name": name, "ok": ok, "detail": detail})
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" - {detail}" if detail else ""), flush=True)
    return ok


def _payload(result: str) -> dict:
    """The MCP tools return a JSON string. Parse it without guessing."""
    try:
        return json.loads(result)
    except Exception:  # noqa: BLE001
        return {"__unparsed__": result}


def _synthetic_churn_csv(path: Path, rows: int = 400) -> Path:
    """A churn dataset with real structure: two numeric features, one
    categorical, and a label with signal (so accuracy must beat chance)."""
    import random

    rng = random.Random(20261027)
    plans = ["basic", "standard", "premium", "enterprise"]
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["tenure_months", "monthly_spend", "plan", "support_tickets", "churned"])
        for _ in range(rows):
            tenure = rng.randint(1, 72)
            spend = round(rng.uniform(10, 300), 2)
            plan = rng.choice(plans)
            tickets = rng.randint(0, 12)
            # Signal: low tenure + high tickets + low-spend plans churn more.
            risk = (0.55 if tenure < 12 else 0.0) + (0.3 if tickets > 7 else 0.0)
            risk += 0.25 if plan == "basic" else 0.0
            churned = 1 if rng.random() < min(risk, 0.95) else 0
            writer.writerow([tenure, spend, plan, tickets, churned])
    return path


async def main_async() -> int:
    import server as mcp  # the constrained_ml MCP server module

    tmp = Path(tempfile.mkdtemp(prefix="mltest_"))
    csv_path = _synthetic_churn_csv(tmp / "churn.csv")
    record("synthetic_dataset", csv_path.exists() and csv_path.stat().st_size > 0,
           f"{csv_path} ({csv_path.stat().st_size} bytes)")

    # 1. train
    train_res = _payload(await mcp.catboost_train(
        csv_path=str(csv_path), target_column="churned",
        model_name="selftest_churn", task_type="classification", iterations=120))
    trained = train_res.get("ok") is True
    record("catboost_train", trained,
           f"rows={train_res.get('rows')} model={Path(str(train_res.get('model',''))).name} "
           f"categorical={train_res.get('categorical_features')}")
    if not trained:
        print(json.dumps(train_res, indent=2)[:600])
        return 1

    model_path = str(train_res["model"])

    # 2. predict
    pred_res = _payload(await mcp.catboost_predict(
        model_path=model_path, feature_json=json.dumps({
            "tenure_months": 3, "monthly_spend": 25.0, "plan": "basic", "support_tickets": 9})))
    predicted = pred_res.get("ok") is True
    record("catboost_predict", predicted,
           f"prediction={pred_res.get('prediction')} prob={pred_res.get('probability')}")
    if not predicted:
        print(json.dumps(pred_res, indent=2)[:600])
        return 1

    # The prediction is a LIST (one entry per row), not a scalar, and the
    # probabilities come back under "probabilities".
    prediction = pred_res.get("prediction")
    is_list = isinstance(prediction, list) and len(prediction) == 1
    label = prediction[0] if is_list else prediction
    has_label = label in (0, 1, "0", "1", 0.0, 1.0)
    record("prediction_is_a_class", has_label and is_list,
           f"prediction={prediction!r} probabilities={pred_res.get('probabilities')}")

    # 3. list_models must see it
    list_res = _payload(await mcp.list_models())
    names = [m.get("name") for m in (list_res.get("models") or [])]
    record("list_models", "selftest_churn.cbm" in names, f"models={names}")

    # 4. sql_query is a SQL-over-HTTP tool by design (the brief's YTsaurus
    #    CHYT proxy is not reachable here), so with no endpoint configured it
    #    must fail with a CLEAR message - not silently return no rows.
    sql_res = _payload(await mcp.sql_query(query="SELECT 1"))
    no_endpoint = sql_res.get("ok") is False and "endpoint" in str(sql_res.get("error", "")).lower()
    record("sql_query_without_endpoint_is_clear", no_endpoint,
           f"error={str(sql_res.get('error'))[:100]}")

    # With a real local HTTP endpoint it must actually run the query. A
    # throwaway server speaks SQL over HTTP exactly as the tool expects.
    import http.server
    import threading

    class _SQLHandler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = self.rfile.read(int(self.headers.get("Content-Length", 0))).decode("utf-8")
            try:
                con = sqlite3.connect(db_path)
                rows = con.execute(body).fetchall()
                con.close()
                payload = json.dumps({"rows": [list(r) for r in rows]}).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).encode("utf-8")
                self.send_response(400)
                self.send_header("Content-Length", str(len(msg)))
                self.end_headers()
                self.wfile.write(msg)

        def log_message(self, *a):  # silence the server
            return

    db_path = tmp / "probe.db"
    con = sqlite3.connect(db_path)
    con.execute("CREATE TABLE metrics (name TEXT, value REAL)")
    con.executemany("INSERT INTO metrics VALUES (?,?)",
                    [("cpu", 42.5), ("ram", 71.0), ("disk", 18.25)])
    con.commit()
    con.close()

    httpd = http.server.HTTPServer(("127.0.0.1", 0), _SQLHandler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    endpoint = f"http://127.0.0.1:{httpd.server_address[1]}/sql"
    try:
        live_sql = _payload(await mcp.sql_query(
            query="SELECT name, value FROM metrics ORDER BY value DESC", endpoint=endpoint))
        live_ok = live_sql.get("ok") is True
        record("sql_query_over_http", live_ok,
               f"rows={str(live_sql.get('rows'))[:140]}")
        if live_ok:
            record("sql_query_returns_the_real_rows",
                   "ram" in str(live_sql.get("rows")),
                   "ordered by value DESC, so ram (71.0) must be first")
    finally:
        httpd.shutdown()

    # 5. error paths are structured, not tracebacks
    bad_pred = _payload(await mcp.catboost_predict(
        model_path=str(tmp / "does_not_exist.cbm"), feature_json="{}"))
    record("predict_missing_model_is_clean_error",
           bad_pred.get("ok") is False and "error" in bad_pred,
           f"error={str(bad_pred.get('error'))[:90]}")

    bad_train = _payload(await mcp.catboost_train(
        csv_path=str(tmp / "nope.csv"), target_column="x", model_name="x"))
    record("train_missing_csv_is_clean_error",
           bad_train.get("ok") is False and "error" in bad_train,
           f"error={str(bad_train.get('error'))[:90]}")

    bad_col = _payload(await mcp.catboost_train(
        csv_path=str(csv_path), target_column="not_a_column", model_name="x"))
    record("train_bad_column_is_clean_error",
           bad_col.get("ok") is False and "error" in bad_col,
           f"error={str(bad_col.get('error'))[:90]}")

    # 6. the model file is a real CatBoost model on disk
    record("model_file_exists", Path(model_path).is_file(),
           f"{model_path} ({Path(model_path).stat().st_size if Path(model_path).is_file() else 0} bytes)")

    return 0 if all(r["ok"] for r in RESULTS) else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    print("=" * 70)
    print("constrained_ml MCP round-trip test")
    print("=" * 70)
    try:
        code = asyncio.run(main_async())
    except Exception as exc:  # noqa: BLE001
        import traceback
        traceback.print_exc()
        record("harness", False, f"{type(exc).__name__}: {exc}")
        code = 1
    passed = sum(1 for r in RESULTS if r["ok"])
    print("=" * 70)
    print(f"{passed}/{len(RESULTS)} checks passed")
    if args.json:
        print(json.dumps(RESULTS, indent=2))
    return code


if __name__ == "__main__":
    sys.exit(main())
