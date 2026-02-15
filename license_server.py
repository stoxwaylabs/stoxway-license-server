from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import psycopg2
import os
import random
import string

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_KEY = os.getenv("ADMIN_KEY")


# ===============================
# DATABASE CONNECTION
# ===============================
def get_connection():
    return psycopg2.connect(DATABASE_URL)


# ===============================
# CREATE TABLE
# ===============================
def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            expiry DATE NOT NULL,
            active BOOLEAN DEFAULT TRUE,
            machine_id TEXT
        );
    """)

    conn.commit()
    cur.close()
    conn.close()


def add_machine_column_if_missing():
    conn = get_connection()
    cur = conn.cursor()

    try:
        cur.execute("""
            ALTER TABLE licenses
            ADD COLUMN machine_id TEXT;
        """)
        conn.commit()
    except psycopg2.errors.DuplicateColumn:
        conn.rollback()
    except Exception:
        conn.rollback()

    cur.close()
    conn.close()


# Run both
init_db()
add_machine_column_if_missing()

# ===============================
# HOME
# ===============================
@app.route("/")
def home():
    return "StoxWay License Server Running 🚀"


# ===============================
# VALIDATE LICENSE
# ===============================
@app.route("/validate", methods=["POST"])
def validate_license():
    try:
        data = request.json
        key = data.get("license_key")
        machine_id = data.get("machine_id")

        if not key or not machine_id:
            return jsonify({"status": "invalid"})

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT expiry, active, machine_id
            FROM licenses
            WHERE license_key = %s
        """, (key,))

        result = cur.fetchone()

        if not result:
            return jsonify({"status": "invalid"})

        expiry, active, stored_machine = result

        if not active:
            return jsonify({"status": "disabled"})

        if datetime.now().date() > expiry:
            return jsonify({"status": "expired"})

        if stored_machine is None:
            cur.execute("""
                UPDATE licenses
                SET machine_id = %s
                WHERE license_key = %s
            """, (machine_id, key))
            conn.commit()

        elif stored_machine != machine_id:
            return jsonify({"status": "different_machine"})

        return jsonify({"status": "active"})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ===============================
# GENERATE LICENSE KEY
# ===============================
def generate_license_key():
    parts = []
    for _ in range(4):
        part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=4))
        parts.append(part)
    return "STOX-" + "-".join(parts)


# ===============================
# CREATE LICENSE (ADMIN)
# ===============================
@app.route("/admin/create", methods=["POST"])
def create_license():
    data = request.json

    if data.get("admin_key") != ADMIN_KEY:
        return jsonify({"error": "Unauthorized"}), 403

    days = int(data.get("days", 30))
    expiry_date = datetime.now().date() + timedelta(days=days)

    new_key = generate_license_key()

    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO licenses (license_key, expiry, active)
        VALUES (%s, %s, true)
    """, (new_key, expiry_date))

    conn.commit()
    cur.close()
    conn.close()

    return jsonify({
        "license_key": new_key,
        "expiry": expiry_date.strftime("%Y-%m-%d")
    })


# ===============================
# TOGGLE LICENSE
# ===============================
@app.route("/admin/toggle", methods=["POST"])
def toggle_license():
    data = request.json

    if data.get("admin_key") != ADMIN_KEY:
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
# LIST LICENSES
# ===============================
@app.route("/admin/licenses", methods=["GET"])
def list_licenses():
    try:
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
            expiry_date = r[1]

            if expiry_date:
                expiry_str = expiry_date.strftime("%Y-%m-%d")
            else:
                expiry_str = "N/A"

            data.append({
                "license_key": r[0],
                "expiry": expiry_str,
                "active": r[2]
            })

        return jsonify(data)

    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/admin")
def admin_panel():
    return """
    <html>
    <head>
        <title>StoxWay License Admin</title>
        <style>
            body { font-family: Arial; padding:20px; }
            table { border-collapse: collapse; margin-top:20px; }
            td, th { border:1px solid #ccc; padding:8px; }
            button { padding:5px 10px; }
        </style>
    </head>
    <body>

        <h2>StoxWay License Admin Panel</h2>

        <input id="adminKey" placeholder="Admin Key"/>
        <input id="days" placeholder="Days" value="30"/>
        <button onclick="createLicense()">Create License</button>

        <br><br>
        <button onclick="loadLicenses()">Load Licenses</button>

        <div id="output"></div>

<script>

function createLicense(){
    let key = document.getElementById("adminKey").value;
    let days = document.getElementById("days").value;

    fetch("/admin/create", {
        method:"POST",
        headers:{"Content-Type":"application/json"},
        body:JSON.stringify({
            admin_key:key,
            days:days
        })
    })
    .then(r=>r.json())
    .then(d=>{
        if(d.error){
            alert("Unauthorized");
            return;
        }
        alert("New License: " + d.license_key);
        loadLicenses();
    });
}

function loadLicenses() {
    const key = document.getElementById("adminKey").value;

    fetch(window.location.origin + "/admin/licenses?admin_key=" + key)
    .then(response => {
        if (!response.ok) {
            throw new Error("Server error");
        }
        return response.json();
    })
    .then(data => {

        if (data.error) {
            alert("Unauthorized");
            return;
        }

        let html = "<table>";
        html += "<tr><th>License Key</th><th>Expiry</th><th>Active</th></tr>";

        data.forEach(l => {
            html += `
                <tr>
                    <td>${l.license_key}</td>
                    <td>${l.expiry}</td>
                    <td>${l.active}</td>
                </tr>
            `;
        });

        html += "</table>";

        document.getElementById("output").innerHTML = html;
    })
    .catch(error => {
        console.log(error);
        alert("Error loading licenses");
    });
}

</script>


    </body>
    </html>
    """














