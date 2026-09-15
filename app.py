import json
import os
import uuid
from functools import wraps

from flask import Flask, render_template, request, jsonify, g

import firebase_admin
from firebase_admin import credentials, auth as firebase_auth, firestore

app = Flask(__name__)

# סוגי הנסיעה האפשריים לקטע כביש - כל אחד עם צבע משלו בממשק (ראו TRAVEL_TYPES ב-index.html)
VALID_STATUSES = {"drove", "rode", "guided", "walked"}


# ============================================================
# אתחול Firebase Admin - פרטי חשבון השירות (service account) מגיעים
# ממשתנה סביבה FIREBASE_SERVICE_ACCOUNT_JSON (המחרוזת המלאה של קובץ ה-JSON
# שמורידים מ-Firebase Console), כדי שהם לא יישמרו בקוד/ב-git בכלל - רק
# כ"סוד" בהגדרות השרת ב-Render. לפיתוח מקומי אפשר גם קובץ בשם
# firebase-service-account.json בתיקיית הפרויקט (לא ב-git - ראו .gitignore)
# ============================================================
_service_account_json = os.environ.get("FIREBASE_SERVICE_ACCOUNT_JSON")
if _service_account_json:
    _cred = credentials.Certificate(json.loads(_service_account_json))
elif os.path.exists("firebase-service-account.json"):
    _cred = credentials.Certificate("firebase-service-account.json")
else:
    raise RuntimeError(
        "חסרים פרטי חשבון השירות של Firebase - צריך להגדיר את משתנה הסביבה "
        "FIREBASE_SERVICE_ACCOUNT_JSON (בענן) או קובץ firebase-service-account.json "
        "(מקומית). ראו SETUP.md."
    )

firebase_admin.initialize_app(_cred)
db = firestore.client()

# תצורת ה-Web SDK של Firebase - אלו מפתחות ציבוריים (לא סודיים) שמיועדים
# להיות גלויים בדפדפן, הם רק מזהים את הפרויקט. גם הם ממשתני סביבה כדי
# שאפשר יהיה לשנות בלי לגעת בקוד
FIREBASE_WEB_CONFIG = {
    "apiKey": os.environ.get("FIREBASE_API_KEY", ""),
    "authDomain": os.environ.get("FIREBASE_AUTH_DOMAIN", ""),
    "projectId": os.environ.get("FIREBASE_PROJECT_ID", ""),
    "storageBucket": os.environ.get("FIREBASE_STORAGE_BUCKET", ""),
    "messagingSenderId": os.environ.get("FIREBASE_MESSAGING_SENDER_ID", ""),
    "appId": os.environ.get("FIREBASE_APP_ID", ""),
}


def require_auth(f):
    """דקורטור שמוודא שהבקשה מגיעה עם טוקן Firebase תקין בכותרת
    Authorization, ומוציא ממנו בצורה מאובטחת (מאומתת מול שרתי Google - אי
    אפשר לזייף) את כתובת המייל של המשתמש. זו כתובת המייל שמשמשת כמפתח
    לכל הנתונים שלו ב-Firestore - כל משתמש רואה ויכול לשנות רק את שלו."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            return jsonify({"error": "missing auth token"}), 401
        token = header[len("Bearer "):]
        try:
            decoded = firebase_auth.verify_id_token(token)
        except Exception:
            return jsonify({"error": "invalid auth token"}), 401

        email = decoded.get("email")
        if not email:
            return jsonify({"error": "token has no email"}), 401

        g.user_email = email
        return f(*args, **kwargs)

    return wrapper


# ---------- גישה לנתונים של המשתמש המחובר ב-Firestore ----------
# מסמך אחד לכל משתמש (לפי כתובת המייל שלו), עם שדות progress ו-
# trip_segments, ותת-אוסף routes שבו כל מסלול הוא מסמך נפרד (כדי שרשימת
# המסלולים תוכל לגדול בלי הגבלת גודל למסמך יחיד ב-Firestore)

def user_doc_ref():
    return db.collection("users").document(g.user_email)


def routes_collection():
    return user_doc_ref().collection("routes")


def load_progress():
    doc = user_doc_ref().get()
    if doc.exists:
        return doc.to_dict().get("progress") or {}
    return {}


def save_progress(progress):
    user_doc_ref().set({"progress": progress}, merge=True)


def load_trip_segments():
    doc = user_doc_ref().get()
    if doc.exists:
        return doc.to_dict().get("trip_segments") or {}
    return {}


def save_trip_segments(trip_segments):
    user_doc_ref().set({"trip_segments": trip_segments}, merge=True)


def load_routes():
    routes = []
    for snap in routes_collection().stream():
        route = snap.to_dict()
        route["id"] = snap.id
        routes.append(route)
    return routes


def name_from_breakdown(breakdown, fallback):
    """שם אוטומטי למסלול, לפי הכביש/כבישים העיקריים בו - למשל 'כביש 6' או 'כביש 6 ועוד'."""
    if not breakdown:
        return fallback
    main = max(breakdown, key=lambda gr: gr.get("distance_km", 0))
    if len(breakdown) == 1:
        return f'כביש {main["ref"]}'
    return f'כביש {main["ref"]} ועוד {len(breakdown) - 1}'


@app.route("/")
def index():
    return render_template("index.html", firebase_config=FIREBASE_WEB_CONFIG)


# ---------- התחלת עבודה אחרי התחברות: כל הנתונים של המשתמש בבת אחת ----------

@app.route("/api/bootstrap")
@require_auth
def bootstrap():
    return jsonify({
        "email": g.user_email,
        "routes": load_routes(),
        "progress": load_progress(),
    })


# ---------- יומן נסיעות (הפיצ'ר החופשי המקורי) ----------

@app.route("/api/save_route", methods=["POST"])
@require_auth
def save_route():
    data = request.get_json()
    coordinates = data.get("coordinates") if data else None
    breakdown = (data.get("breakdown") or []) if data else []
    if not coordinates:
        return jsonify({"error": "no coordinates"}), 400

    existing_count = len(load_routes())
    new_route = {
        "id": uuid.uuid4().hex[:8],
        "name": name_from_breakdown(breakdown, f"מסלול {existing_count + 1}"),
        "coordinates": coordinates,
        "breakdown": breakdown,
        "auto_synced": False,
    }
    routes_collection().document(new_route["id"]).set(new_route)
    return jsonify({"status": "ok", "route": new_route})


@app.route("/api/update_route/<route_id>", methods=["PUT"])
@require_auth
def update_route(route_id):
    data = request.get_json()
    coordinates = data.get("coordinates") if data else None
    breakdown = (data.get("breakdown") or []) if data else []
    if not coordinates:
        return jsonify({"error": "no coordinates"}), 400

    doc_ref = routes_collection().document(route_id)
    doc = doc_ref.get()
    if not doc.exists:
        return jsonify({"error": "route not found"}), 404

    route = doc.to_dict()
    route["id"] = route_id
    route["coordinates"] = coordinates
    route["breakdown"] = breakdown
    route["name"] = name_from_breakdown(breakdown, route.get("name", "מסלול"))
    route["auto_synced"] = False  # המסלול השתנה - נסמן מחדש את הקטעים המתאימים
    doc_ref.set(route)
    return jsonify({"status": "ok", "route": route})


@app.route("/api/delete_route/<route_id>", methods=["DELETE"])
@require_auth
def delete_route(route_id):
    doc_ref = routes_collection().document(route_id)
    if not doc_ref.get().exists:
        return jsonify({"error": "route not found"}), 404
    doc_ref.delete()
    return jsonify({"status": "ok"})


# ---------- כבישים תלת-ספרתיים + התקדמות ----------
# הערה: רשת הכבישים המשותפת (192 הכבישים) אינה חלק מה-API הזה בכלל -
# היא קובץ סטטי משותף לכולם (static/road_network.json), נשלף ישירות
# בדפדפן דרך /static/road_network.json הרגיל של Flask, בלי צורך בהתחברות
# ובלי תלות במשתמש - כל המשתמשים חולקים את אותה רשת כבישים בסיסית

@app.route("/api/set_segment_status", methods=["POST"])
@require_auth
def set_segment_status():
    """קובע את 'סוג הנסיעה' של קטע כביש ספציפי - drove/rode/guided/walked,
    או null/ריק כדי לנקות את הסימון (חזרה לאפור/לא נסעתי)."""
    data = request.get_json()
    ref = data.get("ref") if data else None
    segment_id = str(data.get("segment_id")) if data and data.get("segment_id") is not None else None
    status = data.get("status") if data else None

    if not ref or not segment_id:
        return jsonify({"error": "missing ref or segment_id"}), 400
    if status is not None and status not in VALID_STATUSES:
        return jsonify({"error": "invalid status"}), 400

    progress = load_progress()
    if status is None:
        progress.setdefault(ref, {}).pop(segment_id, None)
        if not progress.get(ref):
            progress.pop(ref, None)
    else:
        progress.setdefault(ref, {})[segment_id] = status
    save_progress(progress)

    return jsonify({"status": "ok", "segment_status": status})


@app.route("/api/clear_road_progress/<ref>", methods=["POST"])
@require_auth
def clear_road_progress(ref):
    """מנקה בבת אחת את כל הסימונים (כל סוגי הנסיעה) של כביש שלם לפי מספרו
    (ref) - מחזיר את כל הקטעים שלו למצב 'לא נסעתי'. שימושי כשרוצים להתחיל
    לתעד כביש מסוים מחדש מאפס, בלי לעבור קטע-קטע. לא נוגע ב-trip_segments -
    אם קטע כלשהו סומן במקור בגלל מסלול מיומן הנסיעות, ה'ביטול לפי מסלול'
    הרלוונטי פשוט יהפוך לפעולה שלא משנה כלום (כבר נוקה), בלי לקרוס."""
    progress = load_progress()
    cleared_count = len(progress.get(ref, {}))
    if ref in progress:
        del progress[ref]
        save_progress(progress)

    return jsonify({"status": "ok", "cleared_count": cleared_count})


@app.route("/api/mark_segments_driven", methods=["POST"])
@require_auth
def mark_segments_driven():
    """מסמן קבוצת קטעי כביש ב'סוג נסיעה' נתון (status - drove/rode/guided/walked),
    בלי לגעת בקטעים אחרים. בשימוש כדי להמיר מסלולים מיומן הנסיעות לקטעים
    צבועים ברשת הכבישים, כך שהם ייכללו באחוז ההתקדמות.

    אם מגיע trip_id: קודם מנקים כל סימון קודם שהמסלול הזה יצר (כדי ששמירה
    חוזרת - למשל אחרי עריכה, או בחירת סוג נסיעה אחר - תהיה עקבית ולא תשאיר
    שאריות ישנות), ורק אז מסמנים מחדש.

    status=None ("🚫 הסר מקטעים") לא מסמן שום דבר חדש, אלא מנקה בפועל את כל
    הקטעים שב-segments (כל קטעי רשת הכבישים שהמסלול המצויר חופף אליהם עכשיו,
    כפי שהחישוב הגיאומטרי בצד הלקוח זיהה) - גם אם הם סומנו במקור ע"י מסלול
    אחר, סומנו ידנית, או שזו נסיעה חדשה שמציירים במיוחד כדי "למחוק" איתה
    קטעים שסומנו בטעות. ככה "הסר מקטעים" עובד גם על ציור מסלול חדש, לא רק
    על עריכת מסלול קיים.

    בכל מקרה גם שומרים אילו קטעים סומנו בגלל המסלול הזה בדיוק
    (trip_segments) לצורך "ביטול" נפרד מהפאנל, ומסמנים את המסלול
    כ'מסונכרן' כדי שלא ננסה לעבד אותו שוב אוטומטית בכל טעינת דף."""
    data = request.get_json()
    segments = data.get("segments") if data else None
    trip_id = data.get("trip_id") if data else None
    status = data.get("status") if data else None
    if segments is None:
        return jsonify({"error": "no segments"}), 400
    if status is not None and status not in VALID_STATUSES:
        return jsonify({"error": "invalid status"}), 400

    progress = load_progress()
    trip_segments = load_trip_segments()

    unmarked = {}

    def clear_segment(ref, segment_id):
        segment_id = str(segment_id)
        if progress.get(ref, {}).pop(segment_id, None) is not None:
            unmarked.setdefault(ref, []).append(segment_id)

    # שלב 1: מנקים קטעים שהמסלול הזה סימן בפעם קודמת (אם יש), כדי שהתוצאה
    # תהיה תמיד עקבית עם המצב הנוכחי בלבד ולא תצטבר עם סימונים ישנים
    if trip_id and trip_id in trip_segments:
        for ref, segment_ids in trip_segments[trip_id].items():
            for segment_id in segment_ids:
                clear_segment(ref, segment_id)

    # שלב 2: אם נבחר סוג נסיעה - מסמנים את הקטעים החדשים. אחרת ("הסר
    # מקטעים") - מנקים בפועל את כל הקטעים ש-segments מכיל, ללא תלות במי
    # סימן אותם במקור
    marked_count = 0
    if status is not None:
        for ref, segment_ids in segments.items():
            progress.setdefault(ref, {})
            for segment_id in segment_ids:
                segment_id = str(segment_id)
                if not progress[ref].get(segment_id):
                    marked_count += 1
                progress[ref][segment_id] = status
    else:
        for ref, segment_ids in segments.items():
            for segment_id in segment_ids:
                clear_segment(ref, segment_id)

    for ref in list(progress.keys()):
        if not progress[ref]:
            progress.pop(ref, None)

    save_progress(progress)

    if trip_id:
        if status is not None:
            trip_segments[trip_id] = {ref: [str(i) for i in ids] for ref, ids in segments.items()}
        else:
            trip_segments.pop(trip_id, None)
        save_trip_segments(trip_segments)

        route_doc_ref = routes_collection().document(trip_id)
        if route_doc_ref.get().exists:
            route_doc_ref.update({"auto_synced": True})

    return jsonify({"status": "ok", "marked_count": marked_count, "unmarked": unmarked})


@app.route("/api/unmark_trip_segments/<trip_id>", methods=["POST"])
@require_auth
def unmark_trip_segments(trip_id):
    """'בטל' לפי מסלול שלם - מוריד את הסימון (חוזר לאפור) מכל הקטעים שסומנו
    אוטומטית בגלל המסלול הזה, למקרה שהתברר שההתאמה הגיאומטרית טעתה וסימנה
    קטעים שבפועל לא נסעת בהם. לא נוגע בקטעים שסומנו ידנית או בגלל מסלול אחר."""
    trip_segments = load_trip_segments()
    segments = trip_segments.get(trip_id)
    if not segments:
        return jsonify({"status": "ok", "unmarked_count": 0, "unmarked": {}})

    progress = load_progress()
    unmarked = {}
    unmarked_count = 0
    for ref, segment_ids in segments.items():
        if ref not in progress:
            continue
        for segment_id in segment_ids:
            segment_id = str(segment_id)
            if progress[ref].get(segment_id):
                del progress[ref][segment_id]
                unmarked_count += 1
                unmarked.setdefault(ref, []).append(segment_id)
        if not progress.get(ref):
            progress.pop(ref, None)
    save_progress(progress)

    del trip_segments[trip_id]
    save_trip_segments(trip_segments)

    return jsonify({"status": "ok", "unmarked_count": unmarked_count, "unmarked": unmarked})


if __name__ == "__main__":
    # host="0.0.0.0" + PORT ממשתנה סביבה - כדי שזה יעבוד גם מקומית וגם
    # אם מישהו מריץ את זה ישירות (ולא דרך gunicorn, שזו הדרך הרגילה בענן -
    # ראו Procfile)
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
