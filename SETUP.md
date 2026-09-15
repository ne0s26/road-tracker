# הקמה: מ-Firebase ועד אתר חי בענן

מדריך צעד-אחר-צעד להקמת האפליקציה כאתר שעובד תמיד, עם התחברות עם Google
ושמירת נתונים לכל משתמש בנפרד. כל השלבים כאן צריך לבצע פעם אחת בלבד
(בהקמה הראשונית) - אחר כך האתר פשוט עובד.

חלק מהשלבים (יצירת חשבונות, אישור תנאי שימוש, לחיצה על כפתורים
באתרים חיצוניים) חייבים להתבצע על ידך - אלו דברים שאני לא יכול לעשות
במקומך. כתבתי כאן בדיוק מה ללחוץ, שלב אחר שלב.

---

## שלב 1: יצירת פרויקט Firebase (בחינם)

1. גלוש אל https://console.firebase.google.com והתחבר עם חשבון Google שלך.
2. "Add project" (הוסף פרויקט) → תן שם, למשל `road-tracker` → אפשר לכבות
   Google Analytics (לא נחוץ לאפליקציה הזו) → "Create project".

### 1.1 הפעלת Google Sign-In

1. בתפריט הצד: **Build → Authentication** → "Get started".
2. בטאב **Sign-in method**, בחר **Google** מהרשימה → הפעל (Enable) →
   בחר "Project support email" (המייל שלך) → **Save**.

### 1.2 הפעלת Firestore (מסד הנתונים)

1. בתפריט הצד: **Build → Firestore Database** → "Create database".
2. מיקום (Location): כדאי לבחור אזור קרוב, למשל `eur3 (europe-west)`.
3. מצב אבטחה: בחר **Start in production mode** (לא test mode) - זה בסדר,
   כי כל הגישה לנתונים עוברת דרך השרת שלנו עם אימות, לא ישירות מהדפדפן.
4. "Create" וממתינים כדקה עד שמסד הנתונים מוכן.

### 1.3 הוספת "אפליקציית Web" - לקבלת המפתחות הציבוריים

1. במסך הראשי של הפרויקט (Project Overview), לחץ על סמל ה-**Web** `</>`
   כדי להוסיף אפליקציית web.
2. תן שם (למשל `road-tracker-web`) → **Register app**.
3. תופיע בלוק קוד עם `firebaseConfig = { apiKey: "...", authDomain: "...", ... }`
   - **שמור את השורות האלה בצד**, נצטרך אותן בשלב 3. אפשר תמיד לחזור
     ולראות אותן שוב ב: **Project settings (⚙️) → General → Your apps**.
4. "Continue to console" (אין צורך להוסיף את סקריפט ה-SDK ידנית - זה כבר
   מוטמע בקוד של האפליקציה).

### 1.4 יצירת מפתח חשבון שירות (Service Account) - לשרת

זה הסוד שמאפשר לשרת (לא לדפדפן) לגשת ל-Firestore ולאמת משתמשים.

1. **Project settings (⚙️) → Service accounts**.
2. לחץ **Generate new private key** → אשר → יורד קובץ JSON למחשב שלך.
3. שמור את הקובץ הזה **בתיקיית הפרויקט** (`road-tracker-web`) בשם מדויק:
   ```
   firebase-service-account.json
   ```
   הקובץ הזה כבר מוגדר ב-`.gitignore` - **לעולם לא** יעלה ל-GitHub, גם אם
   תעשה `git add .` בטעות. זהו סוד אמיתי - אסור לשתף אותו עם אף אחד.

---

## שלב 2: יבוא הנתונים הקיימים שלך (אופציונלי, אם כבר יש לך התקדמות שמורה)

אם כבר סימנת התקדמות/מסלולים בגרסה הישנה (הקבצים `progress.json`,
`routes.json`, `trip_segments.json`), אפשר להעביר אותם ל-Firestore לפני
שהאתר עולה, כדי שלא תאבד כלום:

```bash
pip install firebase-admin
python migrate_to_firestore.py your-email@gmail.com
```

(תשתמש בדיוק בכתובת המייל שאיתה תתחבר עם Google באפליקציה). פרטים
נוספים בראש הקובץ `migrate_to_firestore.py`.

---

## שלב 3: העלאה ל-GitHub

Render (שירות האחסון בענן, שלב 4) פורס אתרים ישירות מ-GitHub.

1. אם עוד אין לך חשבון GitHub: https://github.com/signup
2. צור repository חדש (יכול להיות **Private**): https://github.com/new
3. בתיקיית הפרויקט במחשב שלך, הרץ (אם עוד לא הרצת `git init` בעבר):
   ```bash
   git init
   git add .
   git commit -m "התחלה: אפליקציית מעקב כבישים רב-משתמשית"
   git branch -M main
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```
   **ודא** ש-`firebase-service-account.json` **לא** מופיע ב-`git status`
   לפני ה-commit (הוא אמור להיות מוסתר אוטומטית בזכות `.gitignore`).

---

## שלב 4: פריסה ל-Render (חינמי, תמיד פועל)

1. גלוש אל https://render.com והירשם (אפשר עם חשבון GitHub - הכי נוח).
2. **New + → Blueprint**.
3. חבר את חשבון ה-GitHub שלך (אם עדיין לא) ובחר את ה-repository שיצרת.
4. Render יזהה אוטומטית את הקובץ `render.yaml` שכבר נמצא בפרויקט ויציע
   ליצור שירות בשם `road-tracker`. לחץ **Apply**.
5. Render יבקש למלא את משתני הסביבה הסודיים (מסומנים `sync: false`
   ב-`render.yaml`). מלא אותם כך:

   | משתנה | מאיפה מגיע |
   |---|---|
   | `FIREBASE_SERVICE_ACCOUNT_JSON` | **תוכן שלם** של הקובץ `firebase-service-account.json` (פתח אותו בעורך טקסט, העתק הכל, כולל הסוגריים המסולסלים) |
   | `FIREBASE_API_KEY` | מתוך `firebaseConfig` בשלב 1.3 → `apiKey` |
   | `FIREBASE_AUTH_DOMAIN` | מתוך `firebaseConfig` → `authDomain` |
   | `FIREBASE_PROJECT_ID` | מתוך `firebaseConfig` → `projectId` |
   | `FIREBASE_STORAGE_BUCKET` | מתוך `firebaseConfig` → `storageBucket` |
   | `FIREBASE_MESSAGING_SENDER_ID` | מתוך `firebaseConfig` → `messagingSenderId` |
   | `FIREBASE_APP_ID` | מתוך `firebaseConfig` → `appId` |

6. לחץ **Deploy** / **Create Web Service**. הבנייה הראשונה לוקחת כמה דקות
   (מתקין את התלויות מ-`requirements.txt`). בסיום תקבל כתובת קבועה,
   בסגנון: `https://road-tracker-xxxx.onrender.com`.

   **הערה על התוכנית החינמית של Render**: השירות "נרדם" אחרי כ-15 דקות
   בלי גלישה, ואז "מתעורר" תוך כ-30-60 שניות בכניסה הראשונה אחרי הרדימה
   (הכניסות הבאות מהירות כרגיל). זה עדיין נחשב "תמיד עובד" - האתר תמיד
   זמין בכתובת הקבועה שלו, פשוט לפעמים הטעינה הראשונה איטית יותר. אין
   הגבלת זמן חיים לשירות עצמו (בשונה מ-Postgres החינמי של Render, שאנחנו
   לא משתמשים בו כלל - הנתונים שלנו ב-Firestore, לא ב-Postgres).

---

## שלב 5: הרשאת הדומיין של Render ב-Firebase

Google מסרבת להתחבר מדומיינים לא מוכרים - צריך לאשר את הכתובת של Render:

1. חזרה ל-Firebase Console → **Authentication → Settings → Authorized domains**.
2. **Add domain** → הדבק את הדומיין של Render **בלי** `https://`, למשל:
   `road-tracker-xxxx.onrender.com`
3. שמור.

---

## סיימת! 🎉

גלוש לכתובת של Render, לחץ "התחבר עם Google", ותתחיל לעקוב אחרי הכבישים.
כל מי שיתחבר עם חשבון Google משלו יראה את ההתקדמות שלו בלבד - הנתונים
מופרדים לפי כתובת מייל.

### עדכון האתר בעתיד

כל `git push` ל-branch `main` גורם ל-Render לבנות ולפרוס גרסה חדשה
אוטומטית - אין צורך לעשות שום דבר נוסף ב-Render.

### פתרון בעיות נפוצות

- **"חסרים פרטי חשבון השירות של Firebase"** בלוגים של Render - משתנה
  הסביבה `FIREBASE_SERVICE_ACCOUNT_JSON` ריק/חסר/לא תקין. ודא שהעתקת
  את **כל** תוכן קובץ ה-JSON, כולל `{` ו-`}`.
- **שגיאת "unauthorized domain" בהתחברות עם Google** - חזור לשלב 5,
  ודא שהדומיין המדויק של Render מופיע ברשימת ה-authorized domains.
- **מסך לבן / "שגיאה בטעינת הנתונים"** - פתח את כלי הפיתוח של הדפדפן
  (F12) → טאב Console, ותחפש שגיאה אדומה - היא בדרך כלל תצביע בדיוק על
  איזה משתנה סביבה חסר או שגוי.
