from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime
import psycopg2
import os

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv("DATABASE_URL")

def get_connection():
    return psycopg2.connect(DATABASE_URL)

# Create table if not exists
def init_db():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            expiry DATE NOT NULL,
            active BOOLEAN DEFAULT TRUE
        );
    """)
    conn.commit()
    cur.close()
    conn.close()

init_db()

@app.route("/")
def home():
    return "StoxWay License Server Running 🚀"

@app.route("/validate", methods=["POST"])
def validate_license():
    data = request.json
    key = data.get("license_key")

    if not key:
        return jsonify({"status": "invalid"})

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT expiry, active FROM licenses WHERE license_key = %s;", (key,))
    result = cur.fetchone()

    cur.close()
    conn.close()

    if not result:
        return jsonify({"status": "invalid"})

    expiry, active = result

    if not active:
        return jsonify({"status": "disabled"})

    if datetime.now().date() > expiry:
        return jsonify({"status": "expired"})

    return jsonify({
        "status": "active",
        "expiry": expiry.strftime("%Y-%m-%d")
    })
@app.route("/add-license", methods=["POST"])
def add_license():
    data = request.json

    admin_key = data.get("admin_key")
    if admin_key != os.getenv("ADMIN_KEY"):
        return jsonify({"error": "Unauthorized"}), 403

    license_key = data.get("license_key")
    expiry = data.get("expiry")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO licenses (license_key, expiry, active)
        VALUES (%s, %s, true)
        ON CONFLICT (license_key)
        DO UPDATE SET expiry = EXCLUDED.expiry, active = true
    """, (license_key, expiry))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"status": "license added"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)





