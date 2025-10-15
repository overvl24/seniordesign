# Basic Flask server to trigger simulate_scan in Supabase
# Run with Flask + Requests installed (Linux instance friendly)

import requests
from flask import Flask, request, jsonify

# Supabase URL and API Key
SUPABASE_URL = "https://kcluhlewilcqjzujgofd.supabase.co"
SUPABASE_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtjbHVobGV3aWxjcWp6dWpnb2ZkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTc1MzYwMzIsImV4cCI6MjA3MzExMjAzMn0.oJsTN0b6rKSrYr9hHgs6NuME1Ar0q2n9fR4TdUq5wNs"

app = Flask(__name__)

# --- New: POST /scan — expects { "class_code": "...", "rfid": "..." } ---
@app.route('/scan', methods=['POST'])
def scan():
    data = request.get_json()
    print("Received JSON:", data)

    if not data or 'class_code' not in data or 'rfid' not in data:
        return jsonify({"status": "error", "message": "JSON must include 'class_code' and 'rfid'"}), 400

    ok, resp_text = simulate_scan_rpc(
        rfid_uid=data['rfid'],
        class_code=data['class_code'],
        auto_enroll=True  # set False if you don't want to auto-enroll unknown students
    )

    if ok:
        return jsonify({"status": "success", "message": "Scan recorded", "detail": resp_text}), 200
    else:
        return jsonify({"status": "error", "message": "Supabase RPC failed", "detail": resp_text}), 500


def simulate_scan_rpc(rfid_uid: str, class_code: str, auto_enroll: bool = True):
    """
    Calls PostgREST RPC: public.simulate_scan(p_rfid_uid text, p_class_code text, p_auto_enroll boolean)
    Example: select * from public.simulate_scan('JK3323es', 'ELE-3701', true);
    """
    url = f"{SUPABASE_URL}/rest/v1/rpc/simulate_scan"
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"  # harmless if function returns void
    }
    payload = {
        "p_rfid_uid": rfid_uid,
        "p_class_code": class_code,
        "p_auto_enroll": auto_enroll
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        print("Supabase RPC response:", resp.status_code, resp.text)
        # PostgREST returns 200 for successful RPC (even if function returns void)
        return (resp.status_code == 200, resp.text)
    except Exception as e:
        return (False, str(e))


if __name__ == '__main__':
    # Change port if your host expects something else (e.g., Render uses PORT env var)
    app.run(host='0.0.0.0', port=8080)
