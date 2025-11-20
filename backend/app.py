from flask import Flask, jsonify, request
from flask_cors import CORS
from datetime import datetime
from pymongo import MongoClient, ASCENDING, DESCENDING
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
    query = {}

    # --- FILTRO PER TITOLO (regex, case-insensitive) ---
    title = request.args.get("title")
    if title:
        query["title"] = {"$regex": title, "$options": "i"}

    # --- FILTRO PER DESCRIPTION (regex, case-insensitive) ---
    description = request.args.get("description")
    if description:
        query["description"] = {"$regex": description, "$options": "i"}

    # --- FILTRO PER CATEGORIES (lista separata da virgola: Film,Thriller) ---
    categories = request.args.get("categories")
    if categories:
        cats = [c.strip() for c in categories.split(",") if c.strip()]
        if cats:
            query["categories"] = {"$in": cats}

    # --- FILTRO PER DATA (created_at) ---
    # fromDate e toDate in formato "YYYY-MM-DD"
    from_date_str = request.args.get("fromDate")
    to_date_str = request.args.get("toDate")
    date_filter = {}

    if from_date_str:
        try:
            from_date = datetime.fromisoformat(from_date_str)
            date_filter["$gte"] = from_date
        except ValueError:
            pass  # se formato sbagliato lo ignoro

    if to_date_str:
        try:
            # aggiungo fine giornata (23:59:59) per includere tutta la data
            to_date = datetime.fromisoformat(to_date_str)
            date_filter["$lte"] = to_date
        except ValueError:
            pass

    if date_filter:
        query["created_at"] = date_filter

    # --- FILTRO PER DIMENSIONE (size in MB) ---
    min_size_str = request.args.get("minSize")
    max_size_str = request.args.get("maxSize")
    size_filter = {}

    if min_size_str:
        try:
            size_filter["$gte"] = float(min_size_str)
        except ValueError:
            pass

    if max_size_str:
        try:
            size_filter["$lte"] = float(max_size_str)
        except ValueError:
            pass

    if size_filter:
        query["size"] = size_filter

    # --- ORDINAMENTO ---
    # sort: nome campo (created_at, size, title...)
    # order: asc | desc
    sort_field = request.args.get("sort", "created_at")
    order = request.args.get("order", "desc").lower()

    # whitelist per sicurezza
    allowed_sort_fields = {
        "created_at": "created_at",
        "size": "size",
        "title": "title"
    }
    sort_field = allowed_sort_fields.get(sort_field, "created_at")

    sort_direction = DESCENDING if order == "desc" else ASCENDING

    # --- ESECUZIONE QUERY ---
    cursor = db.torrents.find(query).sort(sort_field, sort_direction).limit(100)
    torrents = list(cursor)

    # conversione ObjectId in string
    for t in torrents:
        t["_id"] = str(t["_id"])
        if "uploaded_by" in t and isinstance(t["uploaded_by"], ObjectId):
            t["uploaded_by"] = str(t["uploaded_by"])

    return jsonify(torrents)

@app.route("/api/torrents/<torrent_id>", methods=["GET"])
def get_torrent(torrent_id):
    try:
        obj_id = ObjectId(torrent_id)
    except:
        return jsonify({"error": "Invalid id"}), 400

    torrent = db.torrents.find_one({"_id": obj_id})
    if not torrent:
        return jsonify({"error": "Not found"}), 404

    torrent["_id"] = str(torrent["_id"])
    if "uploaded_by" in torrent and isinstance(torrent["uploaded_by"], ObjectId):
        torrent["uploaded_by"] = str(torrent["uploaded_by"])

    return jsonify(torrent)

@app.route("/api/torrents/<torrent_id>/comments", methods=["GET"])
def list_comments(torrent_id):
    try:
        obj_id = ObjectId(torrent_id)
    except:
        return jsonify({"error": "Invalid torrent id"}), 400

    comments = list(db.comments.find({"torrent_id": obj_id, "deleted": False}).sort("created_at", DESCENDING))

    for c in comments:
        c["_id"] = str(c["_id"])
        if "torrent_id" in c and isinstance(c["torrent_id"], ObjectId):
            c["torrent_id"] = str(c["torrent_id"])
        if "author_id" in c and isinstance(c.get("author_id"), ObjectId):
            c["author_id"] = str(c["author_id"])

    return jsonify(comments)

@app.route("/api/torrents/<torrent_id>/comments", methods=["POST"])
def add_comment(torrent_id):
    try:
        obj_id = ObjectId(torrent_id)
    except:
        return jsonify({"error": "Invalid torrent id"}), 400

    data = request.json or {}

    try:
        rating = int(data.get("rating", 0))
    except ValueError:
        rating = 0

    text = (data.get("text") or "").strip()
    author_name = (data.get("author_name") or "Anonimo").strip()

    if rating < 1 or rating > 5:
        return jsonify({"error": "Rating must be between 1 and 5"}), 400
    if not text:
        return jsonify({"error": "Text is required"}), 400

    now = datetime.utcnow()

    comment_doc = {
        "torrent_id": obj_id,
        "author_id": None,  # per ora niente login, quindi None
        "author_name": author_name,
        "rating": rating,
        "text": text[:160],
        "created_at": now,
        "updated_at": now,
        "deleted": False
    }

    result = db.comments.insert_one(comment_doc)

    # Ricalcolo media valutazioni e conteggio sul torrent
    pipeline = [
        {"$match": {"torrent_id": obj_id, "deleted": False}},
        {"$group": {"_id": "$torrent_id", "avgRating": {"$avg": "$rating"}, "count": {"$sum": 1}}}
    ]
    stats = list(db.comments.aggregate(pipeline))
    if stats:
        s = stats[0]
        db.torrents.update_one(
            {"_id": obj_id},
            {
                "$set": {
                    "average_rating": float(round(s["avgRating"], 2)),
                    "ratings_count": int(s["count"])
                }
            }
        )

    return jsonify({"inserted_id": str(result.inserted_id)}), 201

@app.route("/api/comments/<comment_id>", methods=["PUT"])
def update_comment(comment_id):
    try:
        obj_id = ObjectId(comment_id)
    except:
        return jsonify({"error": "Invalid comment id"}), 400

    data = request.json or {}

    update_fields = {}
    if "text" in data:
        update_fields["text"] = data["text"].strip()[:160]
    if "rating" in data:
        try:
            rating = int(data["rating"])
            if 1 <= rating <= 5:
                update_fields["rating"] = rating
        except ValueError:
            pass

    if not update_fields:
        return jsonify({"error": "Nothing to update"}), 400

    update_fields["updated_at"] = datetime.utcnow()

    comment = db.comments.find_one_and_update(
        {"_id": obj_id, "deleted": False},
        {"$set": update_fields},
        return_document=True
    )

    if not comment:
        return jsonify({"error": "Comment not found"}), 404

    # Ricalcolo media per il torrent
    torrent_id = comment["torrent_id"]
    pipeline = [
        {"$match": {"torrent_id": torrent_id, "deleted": False}},
        {"$group": {"_id": "$torrent_id", "avgRating": {"$avg": "$rating"}, "count": {"$sum": 1}}}
    ]
    stats = list(db.comments.aggregate(pipeline))
    if stats:
        s = stats[0]
        db.torrents.update_one(
            {"_id": torrent_id},
            {"$set": {
                "average_rating": float(round(s["avgRating"], 2)),
                "ratings_count": int(s["count"])
            }}
        )

    return jsonify({"status": "updated"})

@app.route("/api/comments/<comment_id>", methods=["DELETE"])
def delete_comment(comment_id):
    try:
        obj_id = ObjectId(comment_id)
    except:
        return jsonify({"error": "Invalid comment id"}), 400

    comment = db.comments.find_one({"_id": obj_id})
    if not comment:
        return jsonify({"error": "Comment not found"}), 404

    db.comments.update_one({"_id": obj_id}, {"$set": {"deleted": True, "updated_at": datetime.utcnow()}})

    # Ricalcolo media per il torrent
    torrent_id = comment["torrent_id"]
    pipeline = [
        {"$match": {"torrent_id": torrent_id, "deleted": False}},
        {"$group": {"_id": "$torrent_id", "avgRating": {"$avg": "$rating"}, "count": {"$sum": 1}}}
    ]
    stats = list(db.comments.aggregate(pipeline))
    if stats:
        s = stats[0]
        db.torrents.update_one(
            {"_id": torrent_id},
            {"$set": {
                "average_rating": float(round(s["avgRating"], 2)),
                "ratings_count": int(s["count"])
            }}
        )
    else:
        db.torrents.update_one(
            {"_id": torrent_id},
            {"$set": {
                "average_rating": 0,
                "ratings_count": 0
            }}
        )

    return jsonify({"status": "deleted"})


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)