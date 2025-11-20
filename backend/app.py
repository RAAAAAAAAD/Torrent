from flask import Flask, jsonify, request, g
from flask_cors import CORS
import jwt
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from pymongo import MongoClient, ASCENDING, DESCENDING
from bson.objectid import ObjectId
import config

# Mappa dei ruoli per i permessi
ROLE_LEVEL = {
    "user": 1,
    "moderator": 2,
    "admin": 3,
}

app = Flask(__name__)
CORS(app)  # permette al frontend (JS) di chiamare le API

# Connessione a MongoDB
client = MongoClient(config.MONGO_URI)
db = client[config.DB_NAME]


# ----------------- AUTH & RUOLI -----------------

def create_token(user):
    payload = {
        "user_id": str(user["_id"]),
        "role": user["role"],
        "exp": datetime.utcnow() + timedelta(hours=4)
    }
    token = jwt.encode(payload, config.SECRET_KEY, algorithm="HS256")
    return token


def get_current_user():
    if hasattr(g, "current_user"):
        return g.current_user

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        g.current_user = None
        return None

    token = auth_header.split(" ", 1)[1]

    try:
        payload = jwt.decode(token, config.SECRET_KEY, algorithms=["HS256"])
    except jwt.ExpiredSignatureError:
        g.current_user = None
        return None
    except jwt.InvalidTokenError:
        g.current_user = None
        return None

    user_id = payload.get("user_id")
    if not user_id:
        g.current_user = None
        return None

    user = db.users.find_one({"_id": ObjectId(user_id)})
    if not user or user.get("banned"):
        g.current_user = None
        return None

    g.current_user = user
    return user


def require_role(min_role):
    """Decoratore: richiede almeno il ruolo min_role ('user', 'moderator', 'admin')."""
    def decorator(fn):
        def wrapper(*args, **kwargs):
            user = get_current_user()
            if not user:
                return jsonify({"error": "Authentication required"}), 401
            if ROLE_LEVEL.get(user["role"], 0) < ROLE_LEVEL.get(min_role, 0):
                return jsonify({"error": "Forbidden"}), 403
            return fn(*args, **kwargs)
        wrapper.__name__ = fn.__name__
        return wrapper
    return decorator


# ----------------- ENDPOINT DI TEST -----------------

@app.route("/api/health")
def health():
    return jsonify({"status": "ok"})


# ----------------- REGISTER & LOGIN -----------------

@app.route("/api/register", methods=["POST"])
def register():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    email = (data.get("email") or "").strip()
    password = data.get("password") or ""

    errors = []
    if not username:
        errors.append("username obbligatorio")
    if not email:
        errors.append("email obbligatoria")
    if not password or len(password) < 6:
        errors.append("password troppo corta")

    if errors:
        return jsonify({"errors": errors}), 400

    if db.users.find_one({"username": username}):
        return jsonify({"error": "username già esistente"}), 400

    if db.users.find_one({"email": email}):
        return jsonify({"error": "email già registrata"}), 400

    user_doc = {
        "username": username,
        "email": email,
        "password_hash": generate_password_hash(password),
        "role": "user",
        "created_at": datetime.utcnow(),
        "banned": False,
        "ban_reason": None,
        "banned_until": None
    }
    result = db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id

    token = create_token(user_doc)

    return jsonify({
        "token": token,
        "user": {
            "id": str(user_doc["_id"]),
            "username": username,
            "email": email,
            "role": user_doc["role"]
        }
    }), 201


@app.route("/api/login", methods=["POST"])
def login():
    data = request.json or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    user = db.users.find_one({"username": username})
    if not user or not check_password_hash(user["password_hash"], password):
        return jsonify({"error": "Credenziali invalide"}), 401

    if user.get("banned"):
        return jsonify({"error": "Utente bannato"}), 403

    token = create_token(user)
    return jsonify({
        "token": token,
        "user": {
            "id": str(user["_id"]),
            "username": user["username"],
            "email": user["email"],
            "role": user["role"]
        }
    })


# ----------------- TORRENTS: LISTA + FILTRI -----------------

@app.route("/api/torrents", methods=["GET"])
def list_torrents():
    query = {}

    # Filtro per titolo (regex, case-insensitive)
    title = request.args.get("title")
    if title:
        query["title"] = {"$regex": title, "$options": "i"}

    # Filtro per descrizione
    description = request.args.get("description")
    if description:
        query["description"] = {"$regex": description, "$options": "i"}

    # Filtro per categorie (lista separata da virgola: Film,Thriller)
    categories = request.args.get("categories")
    if categories:
        cats = [c.strip() for c in categories.split(",") if c.strip()]
        if cats:
            query["categories"] = {"$in": cats}

    # Filtro per data (created_at) - fromDate/toDate formato "YYYY-MM-DD"
    from_date_str = request.args.get("fromDate")
    to_date_str = request.args.get("toDate")
    date_filter = {}

    if from_date_str:
        try:
            from_date = datetime.fromisoformat(from_date_str)
            date_filter["$gte"] = from_date
        except ValueError:
            pass

    if to_date_str:
        try:
            to_date = datetime.fromisoformat(to_date_str)
            date_filter["$lte"] = to_date
        except ValueError:
            pass

    if date_filter:
        query["created_at"] = date_filter

    # Filtro per dimensione
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

    # Ordinamento
    sort_field = request.args.get("sort", "created_at")
    order = request.args.get("order", "desc").lower()

    allowed_sort_fields = {
        "created_at": "created_at",
        "size": "size",
        "title": "title"
    }
    sort_field = allowed_sort_fields.get(sort_field, "created_at")
    sort_direction = DESCENDING if order == "desc" else ASCENDING

    cursor = db.torrents.find(query).sort(sort_field, sort_direction).limit(100)
    torrents = list(cursor)

    for t in torrents:
        t["_id"] = str(t["_id"])
        if "uploaded_by" in t and isinstance(t["uploaded_by"], ObjectId):
            t["uploaded_by"] = str(t["uploaded_by"])

    return jsonify(torrents)


# ----------------- TORRENTS: CREAZIONE (SOLO USER+) -----------------

@app.route("/api/torrents", methods=["POST"])
@require_role("user")
def create_torrent():
    user = get_current_user()
    data = request.json or {}

    title = (data.get("title") or "").strip()
    description = (data.get("description") or "").strip()
    file_url = (data.get("file_url") or "").strip()

    size = data.get("size")
    try:
        size = float(size) if size is not None and size != "" else None
    except ValueError:
        size = None

    categories = data.get("categories") or []
    if isinstance(categories, str):
        categories = [c.strip() for c in categories.split(",") if c.strip()]

    images = data.get("images") or []
    if isinstance(images, str):
        images = [u.strip() for u in images.split(",") if u.strip()]

    errors = []
    if not title:
        errors.append("title è obbligatorio")
    if not description:
        errors.append("description è obbligatoria")
    if len(description) > 160:
        errors.append("description non può superare 160 caratteri")
    if not file_url:
        errors.append("file_url è obbligatorio")

    if errors:
        return jsonify({"errors": errors}), 400

    now = datetime.utcnow()

    torrent_doc = {
        "title": title,
        "description": description[:160],
        "size": size,
        "categories": categories,
        "images": images,
        "file_url": file_url,
        "created_at": now,
        "uploaded_by": user["_id"],
        "average_rating": 0.0,
        "ratings_count": 0,
        "downloads_count": 0
    }

    result = db.torrents.insert_one(torrent_doc)

    return jsonify({"inserted_id": str(result.inserted_id)}), 201


# ----------------- TORRENTS: DETTAGLIO -----------------

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


# ----------------- COMMENTI -----------------

@app.route("/api/torrents/<torrent_id>/comments", methods=["GET"])
def list_comments(torrent_id):
    try:
        obj_id = ObjectId(torrent_id)
    except:
        return jsonify({"error": "Invalid torrent id"}), 400

    comments = list(
        db.comments
        .find({"torrent_id": obj_id, "deleted": False})
        .sort("created_at", DESCENDING)
    )

    for c in comments:
        c["_id"] = str(c["_id"])
        if "torrent_id" in c and isinstance(c["torrent_id"], ObjectId):
            c["torrent_id"] = str(c["torrent_id"])
        if "author_id" in c and isinstance(c.get("author_id"), ObjectId):
            c["author_id"] = str(c["author_id"])

    return jsonify(comments)


@app.route("/api/torrents/<torrent_id>/comments", methods=["POST"])
@require_role("user")
def add_comment(torrent_id):
    user = get_current_user()

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
    author_name = (data.get("author_name") or user["username"]).strip()

    if rating < 1 or rating > 5:
        return jsonify({"error": "Rating must be between 1 and 5"}), 400
    if not text:
        return jsonify({"error": "Text is required"}), 400

    now = datetime.utcnow()

    comment_doc = {
        "torrent_id": obj_id,
        "author_id": user["_id"],
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
@require_role("user")
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

    comment = db.comments.find_one({"_id": obj_id, "deleted": False})
    if not comment:
        return jsonify({"error": "Comment not found"}), 404

    db.comments.update_one({"_id": obj_id}, {"$set": update_fields})

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
@require_role("moderator")
def delete_comment(comment_id):
    try:
        obj_id = ObjectId(comment_id)
    except:
        return jsonify({"error": "Invalid comment id"}), 400

    comment = db.comments.find_one({"_id": obj_id})
    if not comment:
        return jsonify({"error": "Comment not found"}), 404

    db.comments.update_one(
        {"_id": obj_id},
        {"$set": {"deleted": True, "updated_at": datetime.utcnow()}}
    )

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


# ----------------- DOWNLOAD (SOLO USER+) -----------------

@app.route("/api/torrents/<torrent_id>/download", methods=["POST"])
@require_role("user")
def register_download(torrent_id):
    user = get_current_user()
    try:
        t_id = ObjectId(torrent_id)
    except:
        return jsonify({"error": "Invalid torrent id"}), 400

    torrent = db.torrents.find_one({"_id": t_id})
    if not torrent:
        return jsonify({"error": "Torrent not found"}), 404

    now = datetime.utcnow()

    db.downloads.insert_one({
        "torrent_id": t_id,
        "user_id": user["_id"],
        "downloaded_at": now
    })

    db.torrents.update_one(
        {"_id": t_id},
        {"$inc": {"downloads_count": 1}}
    )

    return jsonify({"status": "ok", "file_url": torrent["file_url"]})


# ----------------- MODERATOR: BAN & DELETE -----------------

@app.route("/api/users/<user_id>/ban", methods=["POST"])
@require_role("moderator")
def ban_user(user_id):
    data = request.json or {}
    reason = (data.get("reason") or "").strip() or "Violazione dei termini"

    try:
        u_id = ObjectId(user_id)
    except:
        return jsonify({"error": "Invalid user id"}), 400

    db.users.update_one(
        {"_id": u_id},
        {"$set": {
            "banned": True,
            "ban_reason": reason,
            "banned_until": None
        }}
    )
    return jsonify({"status": "banned"})


@app.route("/api/torrents/<torrent_id>", methods=["DELETE"])
@require_role("moderator")
def delete_torrent(torrent_id):
    try:
        t_id = ObjectId(torrent_id)
    except:
        return jsonify({"error": "Invalid torrent id"}), 400

    result = db.torrents.delete_one({"_id": t_id})
    db.comments.update_many({"torrent_id": t_id}, {"$set": {"deleted": True}})
    db.downloads.delete_many({"torrent_id": t_id})

    if result.deleted_count == 0:
        return jsonify({"error": "Torrent not found"}), 404

    return jsonify({"status": "deleted"})


# ----------------- ADMIN: STATISTICHE -----------------

@app.route("/api/stats/top-torrents", methods=["GET"])
@require_role("admin")
def stats_top_torrents():
    mode = request.args.get("mode", "downloads")  # downloads | rating

    if mode == "rating":
        sort_field = "average_rating"
    else:
        sort_field = "downloads_count"

    torrents = list(
        db.torrents.find().sort(sort_field, DESCENDING).limit(10)
    )
    for t in torrents:
        t["_id"] = str(t["_id"])
    return jsonify(torrents)


@app.route("/api/stats/new-torrents-per-category", methods=["GET"])
@require_role("admin")
def stats_new_torrents_per_category():
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)

    pipeline = [
        {"$match": {"created_at": {"$gte": week_ago}}},
        {"$unwind": "$categories"},
        {"$group": {"_id": "$categories", "count": {"$sum": 1}}},
        {"$sort": {"count": -1}}
    ]
    results = list(db.torrents.aggregate(pipeline))
    data = [{"category": r["_id"], "count": r["count"]} for r in results]
    return jsonify(data)


@app.route("/api/stats/top-categories", methods=["GET"])
@require_role("admin")
def stats_top_categories():
    from_str = request.args.get("fromDate")
    to_str = request.args.get("toDate")

    match = {}
    if from_str:
        try:
            match.setdefault("downloaded_at", {})["$gte"] = datetime.fromisoformat(from_str)
        except ValueError:
            pass
    if to_str:
        try:
            match.setdefault("downloaded_at", {})["$lte"] = datetime.fromisoformat(to_str)
        except ValueError:
            pass

    pipeline = []
    if match:
        pipeline.append({"$match": match})

    pipeline.extend([
        {"$lookup": {
            "from": "torrents",
            "localField": "torrent_id",
            "foreignField": "_id",
            "as": "torrent"
        }},
        {"$unwind": "$torrent"},
        {"$unwind": "$torrent.categories"},
        {"$group": {"_id": "$torrent.categories", "downloads": {"$sum": 1}}},
        {"$sort": {"downloads": -1}}
    ])

    results = list(db.downloads.aggregate(pipeline))
    data = [{"category": r["_id"], "downloads": r["downloads"]} for r in results]
    return jsonify(data)


# ----------------- MAIN -----------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
