# Basic Flask server to talk to Supabase
# - /scan: simulate a scan (RFID + class_code [+ optional hhmm])
# - /class_rfids: return all RFIDs enrolled in a given class (via RPC rfids_for_class)
# - /getclasses: return all classes (class_code) when receiving command GETCLASSES
# - /version_update: write a version number (via RPC set_version)
#
# Run locally with:
#   python server.py
#
# Deploy on Render: set Start Command to:
#   gunicorn server:app

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
# -------------------------------------------------------------------
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

    rfids = [row.get("rfid_uid") for row in rows if row.get("rfid_uid")]

    return jsonify({
        "ok": True,
        "class_code": class_code,
        "count": len(rfids),
        "rfids": rfids,
    }), 200

# -------------------------------------------------------------------
# 3) /getclasses – list all class codes
#    Body (TEXT): "GETCLASSES"
#    Returns: JSON { ok, count, class_codes:[...] }
# -------------------------------------------------------------------
@app.route("/getclasses", methods=["POST"])
def getclasses():
    raw = request.get_data(as_text=True).strip()
    print("Received /getclasses raw body:", repr(raw))

    if not raw:
        return jsonify({
            "ok": False,
            "error": "EMPTY_BODY",
            "message": "Expected 'GETCLASSES'"
        }), 400

    parts = raw.split()
    if len(parts) != 1:
        return jsonify({
            "ok": False,
            "error": "BAD_FORMAT",
            "message": "Expected exactly: GETCLASSES"
        }), 400

    cmd = parts[0].upper()
    if cmd != "GETCLASSES":
        return jsonify({
            "ok": False,
            "error": "UNKNOWN_COMMAND",
            "command": parts[0],
            "expected": "GETCLASSES"
        }), 400

    # Pull directly from Supabase table classes (PostgREST)
    # GET /rest/v1/classes?select=class_code&order=class_code.asc
    try:
        resp = requests.get(
            f"{SUPABASE_URL}/rest/v1/classes",
            headers={
                "apikey": SUPABASE_API_KEY,
                "Authorization": f"Bearer {SUPABASE_API_KEY}",
                "Accept": "application/json",
            },
            params={
                "select": "class_code",
                "order": "class_code.asc"
            },
            timeout=3.0,
        )
    except requests.exceptions.RequestException as e:
        print("Supabase get classes error:", e)
        return jsonify({"ok": False, "error": "SUPABASE_DOWN"}), 502

    print("Supabase classes response:", resp.status_code, resp.text)

    if resp.status_code != 200:
        return jsonify({
            "ok": False,
            "error": "SUPABASE_ERROR",
            "status": resp.status_code,
            "body": resp.text,
        }), 502

    try:
        rows = resp.json()  # [{ "class_code": "..." }, ...]
    except ValueError:
        return jsonify({
            "ok": False,
            "error": "BAD_SUPABASE_JSON",
            "body": resp.text,
        }), 502

    class_codes = [r.get("class_code") for r in rows if r.get("class_code")]

    return jsonify({
        "ok": True,
        "count": len(class_codes),
        "class_codes": class_codes
    }), 200

# -------------------------------------------------------------------
# 4) /version_update – set current system version
#    Body (TEXT): "VERSIONUPDATE 1.7"
# -------------------------------------------------------------------
@app.route("/version_update", methods=["POST"])
def version_update():
    raw = request.get_data(as_text=True).strip()
    print("Received /version_update raw body:", repr(raw))

    if not raw:
        return jsonify({
            "ok": False,
            "error": "EMPTY_BODY",
            "message": "Expected 'VERSIONUPDATE <version>'"
        }), 400

    parts = raw.split()
    if len(parts) != 2:
        return jsonify({
            "ok": False,
            "error": "BAD_FORMAT",
            "message": "Expected exactly: VERSIONUPDATE <version>"
        }), 400

    cmd, new_version = parts[0], parts[1]
    if cmd.upper() != "VERSIONUPDATE":
        return jsonify({
            "ok": False,
            "error": "UNKNOWN_COMMAND",
            "command": cmd,
            "expected": "VERSIONUPDATE"
        }), 400

    # Basic version validation: allow digits and dots only
    if not all(c.isdigit() or c == "." for c in new_version) or new_version.startswith(".") or new_version.endswith("."):
        return jsonify({
            "ok": False,
            "error": "BAD_VERSION",
            "message": "Version must look like '1.7' or '1.7.2' (digits and dots only)"
        }), 400

    try:
        resp = requests.post(
            f"{SUPABASE_URL}/rest/v1/rpc/set_version",
            headers=supabase_headers(),
            json={"new_version": new_version},
            timeout=3.0,
        )
    except requests.exceptions.RequestException as e:
        print("Supabase set_version error:", e)
        return jsonify({"ok": False, "error": "SUPABASE_DOWN"}), 502

    print("Supabase set_version response:", resp.status_code, resp.text)

    if resp.status_code not in (200, 204):
        return jsonify({
            "ok": False,
            "error": "SUPABASE_ERROR",
            "status": resp.status_code,
            "body": resp.text,
        }), 502

    return jsonify({
        "ok": True,
        "status": "version_updated",
        "current_version": new_version
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
    app.run(host="0.0.0.0", port=8080)
