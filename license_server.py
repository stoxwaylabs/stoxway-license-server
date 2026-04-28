from flask import Flask, request, jsonify
from flask_cors import CORS
from datetime import datetime, timedelta
import psycopg2
import os
import random
import string
import pytz
import uuid

ist = pytz.timezone("Asia/Kolkata")

DATABASE_URL = os.getenv("DATABASE_URL")
ADMIN_KEY = os.getenv("ADMIN_KEY")

app = Flask(__name__)
CORS(app)

# ===============================
# LIVE DASHBOARD STORAGE
# ===============================

LIVE_DATA = {
    "BOT": {
        "price": 0,
        "volume_spike": "-",
        "breakout": "-",
        "oi": "-",
        "vwap_dev": "-",
        "score": 0,
        "signal": "START",
        "pcr": None
    },
    "MANUAL_TRADES": [],
    "CANDLES": {}
}


@app.route("/update_dashboard", methods=["POST"])
def update_dashboard():
    global LIVE_DATA

    data = request.json

    if not data:
        return jsonify({"error": "No data"}), 400

    symbol = data.get("symbol", "NIFTY")

    # Update BOT data
    LIVE_DATA["BOT"] = data.get("BOT", LIVE_DATA["BOT"])

    # store candles per symbol
    
    candles = data.get("CANDLES")
    if candles:
        LIVE_DATA["CANDLES"][symbol] = candles
   

    return jsonify({"status": "updated"})
   
   

@app.route("/add_manual_trade", methods=["POST"])
def add_manual_trade():
    global LIVE_DATA

    data = request.json
    trade = data.get("trade")

    if not trade:
        return jsonify({"error": "No trade"}), 400

    # 🔥 JSON (keep for now)
    LIVE_DATA["MANUAL_TRADES"].insert(0, {
        "time": datetime.now(ist).isoformat(),
        "trade": trade
    })
    save_data()

    LIVE_DATA["MANUAL_TRADES"] = LIVE_DATA["MANUAL_TRADES"][:50]

    # 🔥 ADD THIS (DB SAVE)
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO trades (trade, created_at) VALUES (%s, %s)",
            (trade, datetime.now(ist))
        )

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print("❌ DB SAVE ERROR:", e)

    return jsonify({"status": "added"})
    
@app.route("/delete_manual_trade", methods=["POST"])
def delete_manual_trade():

    global LIVE_DATA

    data = request.json
    trade = data.get("trade")

    if not trade:
        return jsonify({"error": "No trade"}), 400

    # 🔥 JSON DELETE (keep for now)
    trades = LIVE_DATA.get("MANUAL_TRADES", [])

    LIVE_DATA["MANUAL_TRADES"] = [
        t for t in trades if t.get("trade") != trade
    ]

    save_data()

    # 🔥 ADD THIS (DB DELETE)
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("DELETE FROM trades WHERE trade = %s", (trade,))

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print("❌ DB DELETE ERROR:", e)

    return jsonify({"status": "deleted"})
@app.route("/get_dashboard", methods=["GET"])
def get_dashboard():
    
    try:
        symbol = request.args.get("symbol", "NIFTY")
        candles = LIVE_DATA["CANDLES"].get(symbol, [])

        # 🔥 FETCH FROM DB
        trades = []

        try:
            conn = get_connection()
            cur = conn.cursor()

            # 🔥 DAILY DELETE
            cur.execute("""
                DELETE FROM trades
                WHERE created_at < NOW() - INTERVAL '1 day'             
            """)
            
            # 🔥 FETCH
            cur.execute("SELECT trade, created_at FROM trades ORDER BY created_at DESC")

            rows = cur.fetchall()
            print("🔥 DEBUG TRADES:", rows[:5])

            for r in rows:
                trades.append({
                    "trade": r[0],
                    "time": r[1].isoformat()
                })

            conn.commit()
            cur.close()
            conn.close()

        except Exception as e:
            print("❌ DB FETCH ERROR:", e)

        return jsonify({
            "BOT": LIVE_DATA["BOT"],
            "MANUAL_TRADES": trades,   # 🔥 NOW FROM DB
            "CANDLES": candles
        })

    except Exception as e:
        print("❌ DASHBOARD CRASH:", e)
        return jsonify({
            "BOT": LIVE_DATA["BOT"],
            "MANUAL_TRADES": [],
            "CANDLES": []
        })
@app.route("/get_token", methods=["GET"])
def get_token():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("SELECT token FROM token_store WHERE id = 1")
    result = cur.fetchone()

    cur.close()
    conn.close()

    if result:
        return jsonify({"token": result[0]})
    else:
        return jsonify({"error": "No token"}), 404


@app.route("/update_token", methods=["POST"])
def update_token():
    try:
        data = request.json
        token = data.get("token")

        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO token_store (id, token)
            VALUES (1, %s)
            ON CONFLICT (id)
            DO UPDATE SET token = EXCLUDED.token
        """, (token,))

        conn.commit()
        cur.close()
        conn.close()
        if token:
            print("🔥 Token Updated:", token[:8], "...")
            print("📡 Request From:", request.remote_addr)

        return jsonify({"status": "updated"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# ===============================
# COMMUNITY SYSTEM
# ===============================

COMMUNITY_DATA = []

# ===============================
# 🔥 PERSISTENCE (MISSING PART)
# ===============================

import json

DATA_FILE = "data.json"

def load_data():
    global COMMUNITY_DATA, LIVE_DATA

    try:
        with open(DATA_FILE, "r") as f:
            data = json.load(f)

            COMMUNITY_DATA = data.get("community", [])
            LIVE_DATA["MANUAL_TRADES"] = data.get("trades", [])

            print("✅ Data Loaded")

    except:
        print("⚠️ Fresh Start")


def save_data():
    try:
        with open(DATA_FILE, "w") as f:
            json.dump({
                "community": COMMUNITY_DATA,
                "trades": LIVE_DATA["MANUAL_TRADES"]
            }, f)
    except Exception as e:
        print("❌ SAVE ERROR:", e)

@app.route("/community_post", methods=["POST"])
def community_post():
    data = request.json

    msg = data.get("message")
    user = data.get("user", "User")
    avatar = data.get("avatar", "📊")
    msg_id = data.get("id") or str(uuid.uuid4())

    if not msg:
        return jsonify({"error": "No message"}), 400

    # 🔥 SAVE TO DB
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute(
            "INSERT INTO community (id, user_name, message, created_at) VALUES (%s, %s, %s, %s)",
            (msg_id, user, msg, datetime.now(ist))
        )

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print("❌ DB COMMUNITY SAVE ERROR:", e)

    return jsonify({"status": "saved"})

@app.route("/get_community", methods=["GET"])
def get_community():
    data = []

    try:
        conn = get_connection()
        cur = conn.cursor()

        # 🔥 DELETE OLD (daily)
        cur.execute("""
            DELETE FROM community
            WHERE created_at < NOW() - INTERVAL '1 day'          
        """)

        # 🔥 FETCH
        cur.execute("SELECT id, user_name, message, created_at FROM community ORDER BY created_at DESC")

        rows = cur.fetchall()

        for r in rows:
            data.append({
                "id": r[0],
                "user": r[1],
                "message": r[2],
                "time": r[3].isoformat()
            })

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print("❌ COMMUNITY DB ERROR:", e)

    return jsonify(data)

@app.route("/delete_community", methods=["POST"])
def delete_community():
    global COMMUNITY_DATA

    data = request.json
    msg_id = data.get("id")

    if not msg_id:
        return jsonify({"status": "error", "msg": "No ID provided"})

    # 🔥 JSON DELETE
    COMMUNITY_DATA = [
        m for m in COMMUNITY_DATA
        if m.get("id") != msg_id
    ]
    save_data()

    # 🔥 ADD THIS (DB DELETE)
    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("DELETE FROM community WHERE id = %s", (msg_id,))

        conn.commit()
        cur.close()
        conn.close()

    except Exception as e:
        print("❌ DB COMMUNITY DELETE ERROR:", e)

    return jsonify({"status": "deleted"})

# ===============================
# DATABASE CONNECTION
# ===============================
def get_connection():
    try:
        return psycopg2.connect(DATABASE_URL)
    except Exception as e:
        print("❌ DB CONNECT ERROR:", e)
        return None

def init_token_table():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS token_store (
            id INT PRIMARY KEY,
            token TEXT
        );
    """)

    conn.commit()
    cur.close()
    conn.close()


# ===============================
# CREATE TABLE
# ===============================
def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # 🔥 EXISTING TABLE
    cur.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            license_key TEXT PRIMARY KEY,
            expiry DATE NOT NULL,
            active BOOLEAN DEFAULT TRUE,
            machine_id TEXT
        );
    """)

    # 🔥 ADD THESE 2 LINES (IMPORTANT)
    cur.execute("CREATE TABLE IF NOT EXISTS trades (trade TEXT, created_at TIMESTAMP);")
    cur.execute("CREATE TABLE IF NOT EXISTS community (id TEXT, user_name TEXT, message TEXT, created_at TIMESTAMP);")

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
try:
    init_db()
    add_machine_column_if_missing()
    init_token_table()   # 👈 ADD THIS
except Exception as e:
    print("❌ DB INIT FAILED:", e)

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
load_data()
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)






















