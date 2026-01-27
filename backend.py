from flask import Flask, jsonify, request, send_file, render_template
from flask_cors import CORS
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
import json
import os
import uuid
from datetime import datetime, timedelta
import random

app = Flask(__name__)
CORS(app)
auth = HTTPBasicAuth()

# ==================== SECURITY CONFIG ====================
# Ye credentials Render environment variables se load karein
USERS = {
    "saad123": generate_password_hash("saad123")
}

@auth.verify_password
def verify_password(username, password):
    if username in USERS and check_password_hash(USERS.get(username), password):
        return username
    return None

# ==================== FILE UPLOAD CONFIG ====================
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'apk', 'json', 'mp4', 'webm'}
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==================== INITIAL DATA STRUCTURE ====================
INITIAL_DATA = {
    "apps": [],
    "categories": [],
    "analytics": {
        "total_downloads": 0,
        "total_ratings": 0,
        "daily_stats": {},
        "category_stats": {}
    },
    "config": {
        "privacy_policy": "https://yourdomain.com/privacy",
        "support_email": "support@yourdomain.com",
        "admin_email": "admin@yourdomain.com",
        "website_url": "https://yourdomain.com"
    }
}

# ==================== HELPER FUNCTIONS ====================
def load_data():
    try:
        with open('data.json', 'r') as f:
            return json.load(f)
    except:
        save_data(INITIAL_DATA)
        return INITIAL_DATA

def save_data(data):
    with open('data.json', 'w') as f:
        json.dump(data, f, indent=2)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_app_id():
    data = load_data()
    if not data["apps"]:
        return 1
    return max(app["id"] for app in data["apps"]) + 1

# ==================== PUBLIC ROUTES (No Auth Required) ====================
@app.route('/')
def home():
    return jsonify({
        "message": "App Store Backend API",
        "version": "1.0.0",
        "endpoints": {
            "get_apps": "/api/apps",
            "get_featured": "/api/apps/featured",
            "search_apps": "/api/search?q=query",
            "rate_app": "/api/rate/[id] (POST)",
            "get_categories": "/api/categories"
        },
        "admin_panel": "/admin"
    })

@app.route('/api/apps', methods=['GET'])
def get_all_apps():
    data = load_data()
    
    # Sorting options
    sort_by = request.args.get('sort', 'newest')  # newest, popular, rating, name
    
    apps = data["apps"].copy()
    
    if sort_by == 'newest':
        apps.sort(key=lambda x: x.get("release_date", ""), reverse=True)
    elif sort_by == 'popular':
        apps.sort(key=lambda x: x.get("downloads", 0), reverse=True)
    elif sort_by == 'rating':
        apps.sort(key=lambda x: x.get("rating", 0), reverse=True)
    elif sort_by == 'name':
        apps.sort(key=lambda x: x.get("name", "").lower())
    
    return jsonify({
        "apps": apps,
        "total": len(apps),
        "categories": data["categories"],
        "config": data["config"]
    })

@app.route('/api/apps/featured', methods=['GET'])
def get_featured_apps():
    data = load_data()
    
    # Random featured OR specifically marked featured
    featured_apps = [app for app in data["apps"] if app.get("featured", False)]
    
    # If no featured apps, return random 3 apps
    if not featured_apps and data["apps"]:
        featured_apps = random.sample(data["apps"], min(3, len(data["apps"])))
    
    return jsonify({
        "featured_apps": featured_apps,
        "count": len(featured_apps)
    })

@app.route('/api/apps/<int:app_id>', methods=['GET'])
def get_app(app_id):
    data = load_data()
    
    for app in data["apps"]:
        if app["id"] == app_id:
            return jsonify(app)
    
    return jsonify({"error": "App not found"}), 404

@app.route('/api/search', methods=['GET'])
def search_apps():
    query = request.args.get('q', '').lower()
    category = request.args.get('category', '')
    
    data = load_data()
    results = []
    
    for app in data["apps"]:
        if (query in app["name"].lower() or 
            query in app["description"].lower() or
            query in app.get("tags", "").lower()):
            
            if category and app.get("category") != category:
                continue
                
            results.append(app)
    
    return jsonify({
        "results": results,
        "query": query,
        "count": len(results)
    })

@app.route('/api/categories', methods=['GET'])
def get_categories():
    data = load_data()
    return jsonify({
        "categories": data["categories"],
        "count": len(data["categories"])
    })

@app.route('/api/rate/<int:app_id>', methods=['POST'])
def rate_app(app_id):
    data = load_data()
    
    # Find app
    app_index = None
    for i, app in enumerate(data["apps"]):
        if app["id"] == app_id:
            app_index = i
            break
    
    if app_index is None:
        return jsonify({"error": "App not found"}), 404
    
    rating_data = request.json
    rating = rating_data.get("rating", 0)
    review = rating_data.get("review", "")
    user = rating_data.get("user", "Anonymous")
    
    # Validate rating (1-5)
    if not 1 <= rating <= 5:
        return jsonify({"error": "Rating must be between 1 and 5"}), 400
    
    # Add rating to app
    if "ratings" not in data["apps"][app_index]:
        data["apps"][app_index]["ratings"] = []
    
    new_rating = {
        "id": str(uuid.uuid4()),
        "user": user,
        "rating": rating,
        "review": review,
        "date": datetime.now().isoformat(),
        "reply": None
    }
    
    data["apps"][app_index]["ratings"].append(new_rating)
    
    # Update average rating
    ratings = data["apps"][app_index]["ratings"]
    avg_rating = sum(r["rating"] for r in ratings) / len(ratings)
    data["apps"][app_index]["rating"] = round(avg_rating, 1)
    
    # Update analytics
    data["analytics"]["total_ratings"] += 1
    
    save_data(data)
    
    return jsonify({
        "message": "Rating submitted successfully",
        "app_id": app_id,
        "new_rating": avg_rating,
        "total_ratings": len(ratings)
    })

@app.route('/api/download/<int:app_id>', methods=['GET'])
def download_app(app_id):
    data = load_data()
    
    # Find app
    for app in data["apps"]:
        if app["id"] == app_id:
            # Increment download count
            app["downloads"] = app.get("downloads", 0) + 1
            
            # Update analytics
            data["analytics"]["total_downloads"] += 1
            
            today = datetime.now().strftime("%Y-%m-%d")
            if today not in data["analytics"]["daily_stats"]:
                data["analytics"]["daily_stats"][today] = {"downloads": 0, "ratings": 0}
            data["analytics"]["daily_stats"][today]["downloads"] += 1
            
            # Update category stats
            category = app.get("category", "Unknown")
            if category not in data["analytics"]["category_stats"]:
                data["analytics"]["category_stats"][category] = {"downloads": 0, "apps": 0}
            data["analytics"]["category_stats"][category]["downloads"] += 1
            
            save_data(data)
            
            # Return download link or file
            apk_path = app.get("apk_path", f"uploads/app_{app_id}.apk")
            if os.path.exists(apk_path):
                return send_file(apk_path, as_attachment=True)
            else:
                return jsonify({
                    "message": "App found but APK not available",
                    "download_link": app.get("external_link", "")
                })
    
    return jsonify({"error": "App not found"}), 404

# ==================== ADMIN ROUTES (Auth Required) ====================
@app.route('/admin', methods=['GET'])
@auth.login_required
def admin_panel():
    data = load_data()
    return jsonify({
        "admin_panel": True,
        "total_apps": len(data["apps"]),
        "total_downloads": data["analytics"]["total_downloads"],
        "total_ratings": data["analytics"]["total_ratings"],
        "available_endpoints": [
            "/admin/add-app",
            "/admin/delete-app/[id]",
            "/admin/update-app/[id]",
            "/admin/analytics",
            "/admin/upload-file",
            "/admin/update-config"
        ]
    })

@app.route('/admin/add-app', methods=['POST'])
@auth.login_required
def admin_add_app():
    data = load_data()
    app_data = request.json
    
    # Validate required fields
    required_fields = ["name", "description", "category"]
    for field in required_fields:
        if field not in app_data:
            return jsonify({"error": f"Missing required field: {field}"}), 400
    
    # Generate new app ID
    new_id = generate_app_id()
    
    # Create app object
    new_app = {
        "id": new_id,
        "name": app_data["name"],
        "description": app_data["description"],
        "category": app_data["category"],
        "downloads": 0,
        "rating": 0,
        "ratings": [],
        "featured": app_data.get("featured", False),
        "release_date": app_data.get("release_date", datetime.now().strftime("%Y-%m-%d")),
        "last_update": datetime.now().isoformat(),
        "version": app_data.get("version", "1.0.0"),
        "size": app_data.get("size", "0 MB"),
        "privacy_policy": app_data.get("privacy_policy", data["config"]["privacy_policy"]),
        "support_email": app_data.get("support_email", data["config"]["support_email"]),
        "developer": app_data.get("developer", "Unknown"),
        "tags": app_data.get("tags", []),
        "whats_new": app_data.get("whats_new", ""),
        "requirements": app_data.get("requirements", "Android 5.0+"),
        "icon_url": f"/api/icon/{new_id}",
        "screenshot_urls": app_data.get("screenshots", []),
        "video_url": app_data.get("video_url", ""),
        "apk_path": f"uploads/app_{new_id}.apk",
        "external_link": app_data.get("external_link", "")
    }
    
    # Add to data
    data["apps"].append(new_app)
    
    # Update categories if new
    if app_data["category"] not in data["categories"]:
        data["categories"].append(app_data["category"])
    
    # Update category stats
    category = app_data["category"]
    if category not in data["analytics"]["category_stats"]:
        data["analytics"]["category_stats"][category] = {"downloads": 0, "apps": 0}
    data["analytics"]["category_stats"][category]["apps"] += 1
    
    save_data(data)
    
    return jsonify({
        "message": "App added successfully",
        "app_id": new_id,
        "app": new_app
    })

@app.route('/admin/upload-file', methods=['POST'])
@auth.login_required
def admin_upload_file():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        
        return jsonify({
            "message": "File uploaded successfully",
            "filename": filename,
            "filepath": filepath,
            "url": f"/api/files/{filename}",
            "size": os.path.getsize(filepath)
        })
    
    return jsonify({"error": "File type not allowed"}), 400

@app.route('/admin/analytics', methods=['GET'])
@auth.login_required
def admin_analytics():
    data = load_data()
    
    # Calculate daily stats for last 7 days
    daily_stats = []
    for i in range(7):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        stats = data["analytics"]["daily_stats"].get(date, {"downloads": 0, "ratings": 0})
        daily_stats.append({
            "date": date,
            "downloads": stats["downloads"],
            "ratings": stats["ratings"]
        })
    
    # Top apps by downloads
    top_apps = sorted(data["apps"], key=lambda x: x.get("downloads", 0), reverse=True)[:5]
    
    # Category distribution
    category_dist = []
    for category, stats in data["analytics"]["category_stats"].items():
        category_dist.append({
            "category": category,
            "apps": stats["apps"],
            "downloads": stats["downloads"]
        })
    
    return jsonify({
        "analytics": {
            "total_downloads": data["analytics"]["total_downloads"],
            "total_ratings": data["analytics"]["total_ratings"],
            "total_apps": len(data["apps"]),
            "daily_stats": daily_stats,
            "top_apps": top_apps,
            "category_distribution": category_dist,
            "average_rating": sum(app.get("rating", 0) for app in data["apps"]) / len(data["apps"]) if data["apps"] else 0
        }
    })

@app.route('/admin/update-config', methods=['POST'])
@auth.login_required
def admin_update_config():
    data = load_data()
    config_data = request.json
    
    # Update config
    for key, value in config_data.items():
        if key in data["config"]:
            data["config"][key] = value
    
    save_data(data)
    
    return jsonify({
        "message": "Config updated successfully",
        "config": data["config"]
    })

@app.route('/admin/reply-rating/<int:app_id>/<rating_id>', methods=['POST'])
@auth.login_required
def admin_reply_rating(app_id, rating_id):
    data = load_data()
    
    # Find app and rating
    for app in data["apps"]:
        if app["id"] == app_id and "ratings" in app:
            for rating in app["ratings"]:
                if rating["id"] == rating_id:
                    reply_data = request.json
                    rating["reply"] = {
                        "admin": auth.current_user(),
                        "message": reply_data.get("message", ""),
                        "date": datetime.now().isoformat()
                    }
                    
                    save_data(data)
                    return jsonify({
                        "message": "Reply added successfully",
                        "rating": rating
                    })
    
    return jsonify({"error": "Rating not found"}), 404

# ==================== FILE SERVING ====================
@app.route('/api/files/<filename>')
def serve_file(filename):
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(filepath):
        return send_file(filepath)
    return jsonify({"error": "File not found"}), 404

@app.route('/api/icon/<int:app_id>')
def serve_icon(app_id):
    # Try to find app's icon
    data = load_data()
    for app in data["apps"]:
        if app["id"] == app_id:
            icon_path = app.get("icon_path", f"uploads/icon_{app_id}.png")
            if os.path.exists(icon_path):
                return send_file(icon_path)
    
    # Return default icon
    default_icon = "uploads/default_icon.png"
    if os.path.exists(default_icon):
        return send_file(default_icon)
    
    return jsonify({"error": "Icon not found"}), 404

# ==================== ERROR HANDLERS ====================
@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def server_error(error):
    return jsonify({"error": "Internal server error"}), 500

# ==================== MAIN ====================
if __name__ == '__main__':
    # Initialize data file
    load_data()
    
    # Create default files if not exist
    if not os.path.exists('uploads/default_icon.png'):
        # You can add a default icon here
        pass
    
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
