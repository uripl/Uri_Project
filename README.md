# תזרים ועוד — דשבורד פיננסי לליווי עסקים

כלי ויזואלי לניהול חובות, הכנסות צפויות, הוצאות שוטפות ותזרים מזומנים, מותאם
לעבודה של מלווה כלכלי שמשרת בעלי עסקים בריטיינר. הדשבורד מציג בכל רגע איפה
העסק עומד ומתי מגיעים לתזרים בריא.

## תכולה

- **סקירה** — KPIs (יתרת מזומן, סך חוב פתוח, חוב באיחור, הכנסה צפויה ל-30 יום)
  ועקומת תזרים מצטברת ל-12 חודשים קדימה, כולל תאריך חציית 0.
- **חובות** — רשימת חובות עם Aging (0-30 / 31-60 / 61-90 / 90+), הוספה,
  סימון "שולם" ותשלומים חלקיים.
- **תזרים** — בר-צ'ארט שבועי/חודשי של כניסות מול יציאות, ורישום תנועות ידני.
- **הכנסות צפויות** — חוזים וחשבוניות עתידיות עם סבירות (probability) — נכנס
  משוקלל לעקומת התזרים.
- **הוצאות שוטפות** — שכירות, משכורות, קבועות. תדירות חודשית/שבועית. נכלל
  אוטומטית בעקומה.
- **לקוחות** — ניהול לקוחות (multi-tenant). כיום לקוח אחד; הארכיטקטורה
  תומכת בריבוי לקוחות מהיום הראשון.

## מבנה

```
core/        # שכבת הנתונים והחישובים
  db.py            # אתחול ה-Store (Sheets בפרודקשן, MemoryStore בטסטים)
  store.py         # שכבת אחסון: SheetsStore, MemoryStore
  models.py        # Tenant, Debt, ExpectedIncome, RecurringExpense, CashEvent
  repository.py    # שאילתות מסוננות לפי tenant_id (enforcement)
  forecast.py      # cumulative_cash_curve, zero_crossing_date, aging_buckets
  formatting.py
ui/          # רכיבי UI משותפים
  rtl.py
  tenant_selector.py
pages/       # 6 דפי Streamlit
tests/       # pytest על forecast (משתמש ב-MemoryStore — אין צורך ב-credentials)
seed.py      # יצירת לקוח דמו עם נתונים
app.py       # entry point
```

## אחסון נתונים

הפרויקט משתמש ב-**Google Sheets** כ-DB. החלוקה: workbook אחד עם 5 גליונות
(tenants / debts / expected_incomes / recurring_expenses / cash_events).
כשמשתנים credentials, האפליקציה יוצרת את ה-workbook אוטומטית במייל של
ה-Service Account. אם לא נמצאו credentials כלל (למשל בטסטים) — נופל ל-
`MemoryStore` בזיכרון.

### הקמה ראשונה (חד-פעמית)

1. **Google Cloud:** ב-[console.cloud.google.com](https://console.cloud.google.com),
   צור פרויקט חדש, הפעל את **Google Sheets API** ואת **Google Drive API**.
2. **Service Account:** צור Service Account, הורד את ה-JSON.
3. **Streamlit secrets:** העתק את התוכן ל-`.streamlit/secrets.toml`
   (ראה `.streamlit/secrets.toml.example`).
4. **שיתוף:** הוסף את כתובת ה-Gmail שלך ב-`editor_email` כדי שתקבל גישה
   אוטומטית ל-workbook שייווצר.

## הרצה

```bash
pip install -r requirements.txt
python seed.py            # מאכלס את הגליון בלקוח דמו ונתונים סינתטיים
streamlit run app.py
```

הדשבורד יפתח ב-`http://localhost:8501`.

## בדיקות

```bash
pytest
```

הטסטים מכסים את עקומת התזרים, חישוב Aging, רישום תנועה אוטומטי בסימון
חוב כשולם, ובידוד נתונים בין לקוחות. הם רצים כנגד `MemoryStore` בלבד —
אין צורך ב-credentials של גוגל כדי להריץ את ה-suite.

## עקרונות ארכיטקטוניים

1. **Multi-tenant מהיום הראשון.** כל טבלה כוללת `tenant_id`, וכל פונקציית
   repository מקבלת `tenant_id` כפרמטר חובה. מעבר מלקוח אחד ל-N לקוחות לא
   דורש שינויי קוד — רק `INSERT` ל-`tenants`.

2. **`cash_events` כטבלה אחידה.** כל תנועה (תשלום חוב, קבלת חשבונית, רישום
   ידני) שומרת את ה-`source_type` ו-`source_id`. ככה שומרים heritage לכל תנועה
   ויכולים להגיע אחורה ל-debt/income המקורי.

3. **תחזית מנותקת מהיסטוריה.** עקומת התזרים בנויה מ:
   `current_balance` (הכולל היסטוריה של `cash_events`) + תחזית עתידית של
   חובות פתוחים, הכנסות צפויות (משוקללות ב-probability), והוצאות שוטפות.
   אין כפילויות.

4. **כל החישובים בקובץ אחד (`core/forecast.py`).** קל לבדוק עם pytest, קל
   להחליף או לשפר את האלגוריתם בלי לגעת ב-UI.

## הרחבות עתידיות (מחוץ לסקופ MVP)

- Login + הרשאות ללקוח / שיתוף
- אינטגרציה עם בנק / חשבונית ירוקה
- ייצוא דוחות ל-PDF
- התראות (מייל/וואטסאפ) על חובות מתקרבים
- תרחישי "what-if" (דחייה/פריסה של חוב)
