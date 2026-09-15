"""
סקריפט הרצה חד-פעמית: מעביר את הנתונים הקיימים מהגרסה הישנה (חד-משתמשית,
קבצי JSON מקומיים) אל Firestore, תחת המשתמש שלך (לפי כתובת המייל).

--- איך מריצים ---
1. ודא שכבר עברת על SETUP.md והשלמת את הקמת פרויקט ה-Firebase (כולל
   Firestore ו-Google Sign-In), והורדת קובץ "מפתח חשבון שירות" (service
   account key) מ-Firebase Console.
2. שים את קובץ המפתח בתיקיית הפרויקט הזו בשם בדיוק:
       firebase-service-account.json
   (הקובץ הזה כבר ב-.gitignore - הוא סוד ולא יעלה ל-git בטעות)
3. ודא שהקבצים הישנים progress.json / routes.json / trip_segments.json
   (אלו שהאפליקציה הישנה יצרה) נמצאים גם הם בתיקייה הזו.
4. התקן תלויות אם עוד לא: pip install firebase-admin
5. הרץ:
       python migrate_to_firestore.py your-email@gmail.com
   (חשוב: תשתמש באותה כתובת מייל בדיוק שאיתה תתחבר עם Google באפליקציה -
   זו כתובת המייל שמשמשת כ"מפתח" לנתונים שלך ב-Firestore)

הסקריפט אפשר להריץ שוב בלי נזק (idempotent) - מסלולים מיובאים לפי ה-id
הקיים שלהם, אז הרצה חוזרת רק תדרוס אותם מחדש לאותם ערכים, לא תשכפל.
"""

import json
import os
import sys


def main():
    if len(sys.argv) != 2:
        print("שימוש: python migrate_to_firestore.py your-email@gmail.com")
        sys.exit(1)

    user_email = sys.argv[1].strip()
    if "@" not in user_email:
        print(f"'{user_email}' לא נראית ככתובת מייל תקינה - בדוק ונסה שוב")
        sys.exit(1)

    if not os.path.exists("firebase-service-account.json"):
        print(
            "לא נמצא firebase-service-account.json בתיקייה הזו.\n"
            "הורד את קובץ מפתח חשבון השירות מ-Firebase Console ושים אותו כאן\n"
            "(ראו SETUP.md, שלב הקמת Firebase Admin SDK)."
        )
        sys.exit(1)

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        print("חסרה הספרייה firebase-admin. הרץ קודם: pip install firebase-admin")
        sys.exit(1)

    cred = credentials.Certificate("firebase-service-account.json")
    firebase_admin.initialize_app(cred)
    db = firestore.client()

    user_ref = db.collection("users").document(user_email)

    progress = _load_json("progress.json", default={})
    trip_segments = _load_json("trip_segments.json", default={})
    routes = _load_json("routes.json", default=[])

    print(f"נמצאו: {len(progress)} כבישים עם התקדמות, {len(routes)} מסלולים ביומן הנסיעות.")

    # progress + trip_segments נשמרים כשדות על מסמך המשתמש עצמו
    user_ref.set({"progress": progress, "trip_segments": trip_segments}, merge=True)
    print("✔ progress ו-trip_segments הועלו.")

    # כל מסלול הופך למסמך נפרד תחת users/{email}/routes/{route_id}
    routes_col = user_ref.collection("routes")
    for i, route in enumerate(routes):
        route_id = route.get("id") or f"migrated-{i}"
        route_data = dict(route)
        route_data.pop("id", None)  # ה-id הוא כבר שם המסמך, לא צריך גם כשדה בתוכו
        routes_col.document(route_id).set(route_data, merge=True)

    print(f"✔ {len(routes)} מסלולים הועלו.")
    print(f"\nההעברה הושלמה בהצלחה עבור {user_email}.")
    print("אפשר עכשיו להתחבר עם המייל הזה באפליקציה ולראות את כל הנתונים הישנים.")


def _load_json(filename, default):
    if not os.path.exists(filename):
        print(f"(לא נמצא {filename} - מדלג, ממשיך עם ברירת מחדל ריקה)")
        return default
    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    main()
