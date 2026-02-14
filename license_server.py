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
# ===============================
# LIST ALL LICENSES (ADMIN)
# ===============================
@app.route("/admin/licenses", methods=["GET"])
def list_licenses():
    admin_key = request.args.get("admin_key")

    if admin_key != os.getenv("ADMIN_KEY"):
        return jsonify({"error": "Unauthorized"}), 403

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT license_key, expiry, active FROM licenses;")
    rows = cur.fetchall()

    cur.close()
    conn.close()

    data = []
    for r in rows:
        data.append({
            "license_key": r[0],
            "expiry": r[1].strftime("%Y-%m-%d"),
            "active": r[2]
        })

    return jsonify(data)
# ===============================
# TOGGLE LICENSE ACTIVE / DISABLE
# ===============================
@app.route("/admin/toggle", methods=["POST"])
def toggle_license():
    data = request.json

    if data.get("admin_key") != os.getenv("ADMIN_KEY"):
        return jsonify({"error": "Unauthorized"}), 403

    license_key = data.get("license_key")
    active = data.get("active")

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        UPDATE licenses
        SET active = %s
        WHERE license_key = %s
    """, (active, license_key))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"status": "updated"})
# ===============================
# ADMIN WEB PANEL
# ===============================
@app.route("/admin")
def admin_panel():
    return """
    <html>
    <head>
        <title>StoxWay Admin Panel</title>
    </head>
    <body style="font-family: Arial; padding:20px;">
        <h2>StoxWay License Admin Panel</h2>

        <input id="adminKey" placeholder="Enter Admin Key" />
        <button onclick="loadLicenses()">Load Licenses</button>

        <br><br>
        <div id="licenses"></div>

        <script>
        function loadLicenses() {
            let key = document.getElementById("adminKey").value;

            fetch(`/admin/licenses?admin_key=${key}`)
            .then(r => r.json())
            .then(data => {

                if (data.error) {
                    alert("Unauthorized");
                    return;
                }

                let html = "<table border='1' cellpadding='8'>";
                html += "<tr><th>License Key</th><th>Expiry</th><th>Active</th></tr>";

                data.forEach(l => {
                    html += `<tr>
                        <td>${l.license_key}</td>
                        <td>${l.expiry}</td>
                        <td>${l.active}</td>
                    </tr>`;
                });

                html += "</table>";

                document.getElementById("licenses").innerHTML = html;
            });
        }
        </script>
    </body>
    </html>
    """

# ===============================
# RUN SERVER
# ===============================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)




