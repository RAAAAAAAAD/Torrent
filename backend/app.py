from flask import Flask, jsonify, request
from flask_cors import CORS
from pymongo import MongoClient
from bson.objectid import ObjectId
import config
app = Flask(__name__)
CORS(app)  # permette al frontend (JS) di chiamare le API

# Connessione a MongoDB
client = MongoClient(config.MONGO_URI)
db = client[config.DB_NAME]

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})

# --- Primo endpoint reale: lista torrents ---
@app.route("/api/torrents", methods=["GET"])
def list_torrents():
    torrents = list(db.torrents.find().limit(50))
    for t in torrents:
        t["_id"] = str(t["_id"])
        if "uploaded_by" in t and isinstance(t["uploaded_by"], ObjectId):
            t["uploaded_by"] = str(t["uploaded_by"])
    return jsonify(torrents)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)