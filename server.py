# Basic Flask server to talk to Supabase
# - /scan: simulate a scan (RFID + class_code [+ optional hhmm])
# - /class_rfids: return all RFIDs enrolled in a given class
#
# Run locally with:  python server.py

import requests
from flask import Flask, request, jsonify

# Supabase URL and API Key
SUPABASE_URL = "https://kcluhlewilcqjzujgofd.supabase.co"
SUPABASE_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtjbHVobGV3aWxjcWp6dWpnb2ZkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTc1MzYwMzIsImV4cCI6MjA3MzExMjAzMn0.oJsTN0b6rKSrYr9hHgs6NuME1Ar0q2n9fR4TdUq5wNs"

app = Flask(__name__)

# -------------------------------------------------------------------
# Helper: basic headers for Supabase REST
# -------------------------------------------------------------------
def supabase_headers():
    return {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }

# -------------------------------------------------------------------
# 1) /scan – simulate a scan via public.simulate_scan
#    Body (JSON):
#       { "rfid": "JK3323es", "class_code": "ELE-3701" }
#    or { "rfid": "JK3323es", "class_code": "ELE-3701", "hhmm": "1640" }
# -------------------------------------------------------------------
@app.route("/scan", methods=["POST"])
def scan():
    data = request.get_json(silent=True) or {}
    print("Received /scan JSON:", data)

    rfid = data.get("rfid")
    class_code = data.get("class_code")
    hhmm = data.get("hhmm")  # optional time override as string, e.g. "905" or "1640"

    if not rfid or not class_code:
        return jsonify({
            "ok": False,
            "error": "BAD_REQUEST",
            "message": "JSON must include 'rfid' and 'class_code'"
        }), 400

    # Optional: validate hhmm if provided
    if hhmm is not None:
        if not isinstance(hhmm, str) or not (3 <= len(hhmm) <= 4) or not hhmm.isdigit():
            return jsonify({
                "ok": False,
                "error": "BAD_HHMM",
                "message": "hhmm must be a 3–4 digit string like '900' or '1640'"
            }), 400

    # Build RPC payload according to your Postgres function signature:
    # simulate_scan(p_rfid_uid text, p_class_code text, p_hhmm text default null, p_auto_enroll boolean default false)
    payload = {
        "p_rfid_uid": rfid,
        "p_class_code": class_code,
        "p_auto_enroll": False
    }
    if hhmm is not None:
        payload["p_hhmm"] = hhmm

    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/simulate_scan",
            headers=supabase_headers(),
            json=payload,
            timeout=3.0,
        )
    except requests.exceptions.RequestException as e:
        print("Supabase simulate_scan error:", e)
        return jsonify({"ok": False, "error": "SUPABASE_DOWN"}), 502

    print("Supabase simulate_scan response:", resp.status_code, resp.text)

    # Try to parse JSON response from Supabase
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
        }), 502

    return jsonify({
        "ok": True,
        "status": "scan_processed",
        "rpc": payload_resp,
    }), 200

# -------------------------------------------------------------------
# 2) /class_rfids – get all RFIDs for a class code
#    Body (TEXT): "CPE-0002 ALLSTDNT"
#    Returns: JSON { ok, class_code, count, rfids:[...] }
# -------------------------------------------------------------------
@app.route("/class_rfids", methods=["POST"])
def class_rfids():
    """
    Expect raw body like:  CPE-0002 ALLSTDNT
    Returns all RFIDs enrolled in that class.
    """

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

    # Call Supabase RPC: public.rfids_for_class(p_class_code)
    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/rfids_for_class",
            headers=supabase_headers(),
            json={"p_class_code": class_code},
            timeout=3.0,
        )
    except requests.exceptions.RequestException as e:
        print("Supabase rfids_for_class error:", e)
        return jsonify({"ok": False, "error": "SUPABASE_DOWN"}), 502

    print("Supabase rfids_for_class response:", resp.status_code, resp.text)

    if resp.status_code != 200:
        return jsonify({
            "ok": False,
            "error": "SUPABASE_ERROR",
            "status": resp.status_code,
            "body": resp.text,
        }), 502

    try:
        rows = resp.json()  # [{ "rfid_uid": "..." }, ...]
    except ValueError:
        return jsonify({
            "ok": False,
            "error": "BAD_SUPABASE_JSON",
            "body": resp.text,
        }), 502

    rfids = [row["rfid_uid"] for row in rows if row.get("rfid_uid")]

    return jsonify({
        "ok": True,
        "class_code": class_code,
        "count": len(rfids),
        "rfids": rfids,
    }), 200

# -------------------------------------------------------------------
# Optional: simple health check
# -------------------------------------------------------------------
@app.route("/healthz", methods=["GET"])
def healthz():
    return jsonify({"ok": True}), 200

# -------------------------------------------------------------------
# Start the server
# -------------------------------------------------------------------
if __name__ == "__main__":
    # For local testing
    app.run(host="0.0.0.0", port=8080)
