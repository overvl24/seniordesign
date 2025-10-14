#Basic Flask server meant to send data to Supabase
#Needs to be run on a server with Flask and Requests installed
#Preferably run on Linux Instance

import requests

#Supabase URL and API Key
SUPABASE_URL = "https://kcluhlewilcqjzujgofd.supabase.co"
SUPABASE_API_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImtjbHVobGV3aWxjcWp6dWpnb2ZkIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTc1MzYwMzIsImV4cCI6MjA3MzExMjAzMn0.oJsTN0b6rKSrYr9hHgs6NuME1Ar0q2n9fR4TdUq5wNs"

#Using flask and requests to create a simple server, JSONify to process JSON data
from flask import Flask, request, jsonify

app = Flask(__name__)

#Process POST request to /clockin endpoint
@app.route('/test', methods=['POST'])
def clockin():
    data = request.get_json()
    print("Received JSON:", data)

    if not data or 'name' not in data or 'rfid' not in data:
        return jsonify({"status": "error", "message": "Invalid JSON format"}), 400

    success = push_to_supabase(data)
    if success:
        return jsonify({"status": "success", "message": "Clock-in recorded"}), 200
    else:
        return jsonify({"status": "error", "message": "Failed to push to Supabase"}), 500

#Function to push data to Supabase
def push_to_supabase(data):
    headers = {
        "apikey": SUPABASE_API_KEY,
        "Authorization": f"Bearer {SUPABASE_API_KEY}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    
    #May need to install requests library via pip on Debian instance
    response = requests.post(f"{SUPABASE_URL}/rest/v1/test", json=data, headers=headers)
    print("Supabase response:", response.status_code, response.text)

    
    # Explicitly return True if status code is 201
    if response.status_code == 201:
        return True
    else:
        return False


#Start the server
if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)

