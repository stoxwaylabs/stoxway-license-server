from flask import Flask, request, jsonify
from datetime import datetime
import json
import os

app = Flask(__name__)

LICENSE_FILE = "licenses.json"

def load_licenses():
    if not os.path.exists(LICENSE_FILE):
        return {}
    with open(LICENSE_FILE, "r") as f:
        return json.load(f)

@app.route("/validate", methods=["POST"])
def validate_license():
    data = request.json
    key = data.get("license_key")

    licenses = load_licenses()

    if key not in licenses:
        return jsonify({"status": "invalid"})

    lic = licenses[key]

    if not lic.get("active", False):
        return jsonify({"status": "disabled"})

    expiry = datetime.strptime(lic["expiry"], "%Y-%m-%d")
    if datetime.now() > expiry:
        return jsonify({"status": "expired"})

    return jsonify({
        "status": "active",
        "expiry": lic["expiry"]
    })

@app.route("/")
def home():
    return "StoxWay License Server Running"

if __name__ == "__main__":
    app.run()
