# server.py
# Flask middle server + CTQ instrumentation for scan latency
#
# Run locally:  python server.py
# Then simulate scan: curl -X POST http://127.0.0.1:8080/scan -H "Content-Type: application/json" -d '{"rfid":"JK3323es","class_code":"ELE-3701"}'

import time
import uuid
import requests
from flask import Flask, request, jsonify

SUPABASE_URL = "https://kcluhlewilcqjzujgofd.supabase.co"
SUPABASE_API_KEY = "YOUR_KEY_HERE"  # keep your key if you want; better as env var in production

app = Flask(__name__)

# In-memory metrics store (fine for testing)
SCAN_METRICS = {}  # trace_id -> dict

def now_ms() -> int:
    return time.time_ns() // 1_000_000

def supabase_headers():
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

# ------------------------------------------------------------
# /scan – simulate a scan via public.simulate_scan
# Adds trace_id + server_received_ms into payload (if your RPC ignores extra keys, you're fine)
# ------------------------------------------------------------
@app.route("/scan", methods=["POST"])
def scan():
    data = request.get_json(silent=True) or {}
    print("Received /scan JSON:", data)

    rfid = data.get("rfid")
    class_code = data.get("class_code")
    hhmm = data.get("hhmm")  # optional

    if not rfid or not class_code:
        return jsonify({
            "ok": False,
            "error": "BAD_REQUEST",
            "message": "JSON must include 'rfid' and 'class_code'"
        }), 400

    if hhmm is not None:
        if not isinstance(hhmm, str) or not (3 <= len(hhmm) <= 4) or not hhmm.isdigit():
            return jsonify({
                "ok": False,
                "error": "BAD_HHMM",
                "message": "hhmm must be a 3–4 digit string like '900' or '1640'"
            }), 400

    # CTQ start
    trace_id = uuid.uuid4().hex
    t0 = now_ms()

    SCAN_METRICS[trace_id] = {
        "trace_id": trace_id,
        "rfid": rfid,
        "class_code": class_code,
        "t0_ms": t0,
        "t_supabase_done_ms": None,
        "t_ui_received_ms": None,
        "t_ui_rendered_ms": None,
    }

    # Your existing RPC signature:
    # simulate_scan(p_rfid_uid text, p_class_code text, p_hhmm text default null, p_auto_enroll boolean default false)
    payload = {
        "p_rfid_uid": rfid,
        "p_class_code": class_code,
        "p_auto_enroll": False,
        # Instrumentation fields (only safe if your RPC ignores extras; if it doesn't, remove these two lines)
        "trace_id": trace_id,
        "server_received_ms": t0,
    }
    if hhmm is not None:
        payload["p_hhmm"] = hhmm

    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/simulate_scan",
            headers=supabase_headers(),
            json=payload,
            timeout=5.0,
        )
    except requests.exceptions.RequestException as e:
        print("Supabase simulate_scan error:", e)
        return jsonify({"ok": False, "error": "SUPABASE_DOWN"}), 502

    print("Supabase simulate_scan response:", resp.status_code, resp.text)

    # Mark Supabase completion time (RPC returned)
    SCAN_METRICS[trace_id]["t_supabase_done_ms"] = now_ms()

    try:
        payload_resp = resp.json()
    except ValueError:
        payload_resp = {"raw": resp.text}

    if resp.status_code != 200:
        return jsonify({
            "ok": False,
            "error": "SUPABASE_ERROR",
            "status": resp.status_code,
            "body": payload_resp,
            "trace_id": trace_id
        }), 502

    return jsonify({
        "ok": True,
        "status": "scan_processed",
        "trace_id": trace_id,
        "t0_ms": t0,
        "rpc": payload_resp,
    }), 200

# ------------------------------------------------------------
# UI ACK endpoint
# UI calls this when it receives/renders the scan event
# Body JSON: { "trace_id": "...", "stage": "received" | "rendered" }
# ------------------------------------------------------------
@app.route("/ui_ack", methods=["POST"])
def ui_ack():
    data = request.get_json(silent=True) or {}
    trace_id = data.get("trace_id")
    stage = data.get("stage", "rendered")

    if not trace_id or trace_id not in SCAN_METRICS:
        return jsonify({"ok": False, "error": "UNKNOWN_TRACE_ID"}), 404

    t = now_ms()
    if stage == "received":
        SCAN_METRICS[trace_id]["t_ui_received_ms"] = t
    elif stage == "rendered":
        SCAN_METRICS[trace_id]["t_ui_rendered_ms"] = t
    else:
        return jsonify({"ok": False, "error": "BAD_STAGE"}), 400

    return jsonify({"ok": True, "trace_id": trace_id, "stage": stage, "t_ms": t}), 200

# ------------------------------------------------------------
# Metrics endpoint for test runner
# ------------------------------------------------------------
@app.route("/metrics/<trace_id>", methods=["GET"])
def metrics(trace_id):
    m = SCAN_METRICS.get(trace_id)
    if not m:
        return jsonify({"ok": False, "error": "UNKNOWN_TRACE_ID"}), 404

    t0 = m["t0_ms"]
    t_sb = m["t_supabase_done_ms"]
    t_ui = m["t_ui_rendered_ms"]

    out = dict(m)
    out["ctq_mid_to_supabase_ms"] = (t_sb - t0) if (t_sb and t0) else None
    out["ctq_end_to_end_ms"] = (t_ui - t0) if (t_ui and t0) else None
    out["ctq_supabase_to_ui_ms"] = (t_ui - t_sb) if (t_ui and t_sb) else None
    out["ok"] = True
    return jsonify(out), 200

# ------------------------------------------------------------
# /class_rfids – unchanged from you
# ------------------------------------------------------------
@app.route("/class_rfids", methods=["POST"])
def class_rfids():
    raw = request.get_data(as_text=True).strip()
    print("Received /class_rfids raw body:", repr(raw))

    if not raw:
        return jsonify({
            "ok": False,
            "error": "EMPTY_BODY",
            "message": "Expected '<CLASS_CODE> ALLSTDNT'"
        }), 400

    parts = raw.split()
    if len(parts) != 2:
        return jsonify({
            "ok": False,
            "error": "BAD_FORMAT",
            "message": "Expected exactly: <CLASS_CODE> ALLSTDNT"
        }), 400

    class_code, cmd = parts[0], parts[1]
    if cmd.upper() != "ALLSTDNT":
        return jsonify({
            "ok": False,
            "error": "UNKNOWN_COMMAND",
            "command": cmd,
            "expected": "ALLSTDNT"
        }), 400

    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/rfids_for_class",
            headers=supabase_headers(),
            json={"p_class_code": class_code},
            timeout=5.0,
        )
    except requests.exceptions.RequestException as e:
        print("Supabase rfids_for_class error:", e)
        return jsonify({"ok": False, "error": "SUPABASE_DOWN"}), 502

    if resp.status_code != 200:
        return jsonify({
            "ok": False,
            "error": "SUPABASE_ERROR",
            "status": resp.status_code,
            "body": resp.text,
        }), 502

    rows = resp.json()  # [{ "rfid_uid": "..." }, ...]
    rfids = [row["rfid_uid"] for row in rows if row.get("rfid_uid")]

    return jsonify({
        "ok": True,
        "class_code": class_code,
        "count": len(rfids),
        "rfids": rfids,
    }), 200

@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"ok": True}), 200

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
