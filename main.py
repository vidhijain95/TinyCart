from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env
    
CANCEL_WINDOW_MINUTES = 1       # demo value (1 min). Use 2880 for 2 days.
from werkzeug.security import generate_password_hash, check_password_hash
import os, sqlite3, uuid, hashlib
from flask import Flask, render_template, request, redirect, session, flash, url_for
import os, uuid, sqlite3, json, hashlib, base64, qrcode
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import smtplib, ssl
from email.message import EmailMessage
 
from datetime import datetime, timedelta

import sqlite3
 
from flask import flash, redirect, url_for
  
from itsdangerous import URLSafeTimedSerializer

 

app = Flask(__name__)
app.secret_key = os.getenv('SECRET_KEY')

 
s = URLSafeTimedSerializer(app.secret_key)

 



# Gmail sender details
SMTP_USER     = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_SERVER   = "smtp.gmail.com"
SMTP_PORT     = 465
SENDER_NAME   = "TinyCart Store"
 
@app.route("/forgot-pin", methods=["GET", "POST"])
def forgot_pin():
    store_id = (request.args.get("store") or
                request.form.get("store_id", "")).strip()

    if request.method == "POST":
        if not store_id:
            flash("Enter your Store ID.", "error")
            return redirect(url_for("forgot_pin"))

        row = db().cursor().execute(
            "SELECT email FROM stores WHERE store_id=? LIMIT 1", (store_id,)
        ).fetchone()

        if not row:
            flash("❌ Store ID not found.", "error")
            return redirect(url_for("forgot_pin"))

        email = row[0]
        token = s.dumps({"sid": store_id, "em": email}, salt="pin-reset")
        link  = url_for("reset_pin", token=token, _external=True)

        send_email(email,
                   "Reset your TinyCart PIN",
                   f"Hello!\nClick this link within 10 minutes to set a new PIN:\n{link}")

        flash("✅ Reset link sent to the registered owner e‑mail.", "info")
        return redirect(url_for("owner_login", store=store_id))

    return render_template("forgot_pin.html", store_id=store_id)


@app.route("/reset-pin/<token>", methods=["GET", "POST"])
def reset_pin(token):
    try:
        data = s.loads(token, salt="pin-reset", max_age=600)   # 10 min
    except SignatureExpired:
        return "This reset link has expired. ⏰"
    except BadSignature:
        return "Invalid or tampered link."

    store_id = data["sid"]
    email    = data["em"]

    if request.method == "POST":
        new_pin = request.form["pin"].strip()
        if not new_pin.isdigit() or not 4 <= len(new_pin) <= 6:
            flash("PIN must be 4‑6 digits.", "error")
            return redirect(request.url)

        new_hash = hashlib.sha256(new_pin.encode()).hexdigest()

        clash = db().cursor().execute(
            "SELECT 1 FROM stores WHERE owner_pin=? LIMIT 1", (new_hash,)
        ).fetchone()
        if clash:
            flash("❌ PIN already in use. Choose another.", "error")
            return redirect(request.url)

        with db() as con:
            con.execute("UPDATE stores SET owner_pin=? WHERE store_id=? AND email=?",
                        (new_hash, store_id, email))
        flash("✅ PIN updated. Please log in.", "info")
        return redirect(url_for("owner_login", store=store_id))

    return render_template("reset_pin.html")




def send_email(to_addr: str, subj: str, body: str):
    """Tiny email sender via Gmail."""
    msg = EmailMessage()
    msg["From"] = f"{SENDER_NAME} <{SMTP_USER}>"
    msg["To"]   = to_addr
    msg["Subject"] = subj
    msg.set_content(body)

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT, context=ctx) as s:
        s.login(SMTP_USER, SMTP_PASSWORD)
        s.send_message(msg)



 
UPLOAD_FOLDER = "static/images"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ───────── DB helpers ──────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))  # folder where main.py lives
DB_PATH  = os.path.join(BASE_DIR, "tinycart.db")       # always use this file

def db():
    return sqlite3.connect(DB_PATH, detect_types=sqlite3.PARSE_DECLTYPES)

def init_db():
    """Create tables if they don't exist (run once at startup)."""
    with db() as con:
        c = con.cursor()

        # stores: one row per *product*
        c.execute("""CREATE TABLE IF NOT EXISTS stores(
            store_id TEXT,  store_name  TEXT, store_desc TEXT,
            email    TEXT,  owner_phone TEXT, owner_pin TEXT,
            qr_file  TEXT,
            p_name   TEXT,  p_d         TEXT,
            p_p REAL, p_q INTEGER, p_i TEXT,
            approved INTEGER DEFAULT 0,                          -- admin flag
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP       -- NEW column
        )""")

        # orders: one row per order
        c.execute("""CREATE TABLE IF NOT EXISTS orders(
            order_id TEXT PRIMARY KEY, store_id TEXT,
            items_json TEXT, amount REAL,
            customer_name TEXT, customer_phone TEXT, address TEXT,
            status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            payment_mode TEXT, customer_email TEXT
        )""")

init_db()   # create tables the first time

def alter_db_once():
    """
    Add any new columns to old databases.
    Runs at every startup but each ALTER is wrapped in try/except.
    """
    with db() as con:
        cur = con.cursor()
        for col_sql in (
            "ALTER TABLE stores ADD COLUMN approved INTEGER DEFAULT 0",
            "ALTER TABLE stores ADD COLUMN created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP",
            "ALTER TABLE orders ADD COLUMN payment_mode TEXT",
            "ALTER TABLE orders ADD COLUMN customer_email TEXT",
            "ALTER TABLE orders ADD COLUMN updated_at TIMESTAMP",
            "ALTER TABLE orders ADD COLUMN cancelled INTEGER DEFAULT 0",       # ✅ Add this
            "ALTER TABLE orders ADD COLUMN cancelled_by TEXT"

        ):
            try:
                cur.execute(col_sql)
            except sqlite3.OperationalError:
                pass   # column already exists

alter_db_once()

# New admin tables + approved flag (run once at startup)
def _ensure_admin_tables():
    """Create admin_users table and make sure approved column exists only once."""
    with db() as con:
        # 1️⃣ Create admin_users table if not exists
        con.execute("""
            CREATE TABLE IF NOT EXISTS admin_users(
                email         TEXT PRIMARY KEY,
                password_hash TEXT NOT NULL
            )
        """)
        # 2️⃣ Try adding approved column — ignore if already exists
        try:
            con.execute("ALTER TABLE stores ADD COLUMN approved INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass  # column already exists, so ignore

_ensure_admin_tables()  # 🟢 Call it right away like init_db
print("🗄️  TinyCart DB path =", DB_PATH)
def add_created_at_column():
    with db() as con:
        try:
            con.execute("ALTER TABLE stores ADD COLUMN created_at TIMESTAMP")
            print("✅ created_at column added (no default)")
        except sqlite3.OperationalError as e:
            print("⚠️", e)
 

 
 
def _max_stock(store_id: str, pid: int) -> int:
    row = db().cursor().execute(
        "SELECT p_q FROM stores WHERE store_id=? LIMIT 1 OFFSET ?",
        (store_id, pid)).fetchone()

    return row[0] if row else 0   # if product is missing, return 0 stock


def _get_qr(store_id: str):
    row = db().cursor().execute(
        "SELECT qr_file FROM stores WHERE store_id=? LIMIT 1", (store_id,)).fetchone()
    return row[0] if row and row[0] else None

def _order_total(order_id: str):
    row = db().cursor().execute(
        "SELECT amount FROM orders WHERE order_id=?", (order_id,)).fetchone()
    return row[0] if row else 0.0

 
@app.route("/")
def home():
    return render_template("homee.html")

 
@app.route("/create-store", methods=["GET", "POST"])
def choose_count():
    if request.method == "POST":
        return render_template("add_product.html",
                               count=int(request.form["count"]))
    return render_template("count.html")

 
@app.route("/submit-store", methods=["POST"])
def submit_store():
    """Wizard POST: create the new store + its products, then show success page."""
    store_id = uuid.uuid4().hex[:8]                   # short public code

    # 1️⃣  owner‑PIN must be unique ------------------------------------------------
    raw_pin  = request.form["owner_pin"].strip()
    pin_hash = hashlib.sha256(raw_pin.encode()).hexdigest()

    if db().cursor().execute(
        "SELECT 1 FROM stores WHERE owner_pin=? LIMIT 1", (pin_hash,)
    ).fetchone():
        flash("❗ This PIN is already used. Please choose a different, unique PIN.", "addproduct")
        prod_count = len(request.form.getlist("pname[]")) or 1
        return render_template("add_product.html", count=prod_count, form=request.form)

    # 2️⃣  optional store‑level QR upload -----------------------------------------
    qr_name = ""
    f = request.files.get("qr_img")
    if f and f.filename:
        qr_name = secure_filename(f.filename)
        f.save(os.path.join(UPLOAD_FOLDER, qr_name))

    # 3️⃣  collect product arrays --------------------------------------------------
    p_name = request.form.getlist("pname[]")
    p_d    = request.form.getlist("pd[]")
    p_p    = request.form.getlist("pp[]")
    p_q    = request.form.getlist("pq[]")

    img_lst = []
    for f in request.files.getlist("pi[]"):
        if f and f.filename:
            fn = secure_filename(f.filename)
            f.save(os.path.join(UPLOAD_FOLDER, fn))
            img_lst.append(fn)
        else:
            img_lst.append("")

    # 4️⃣  general owner data ------------------------------------------------------
    owner_email  = request.form.get("email", "").strip()
    owner_phone  = request.form["owner_phone"].strip()
    store_name   = request.form["storename"].strip()
    store_desc   = request.form["description"].strip()

    # 5️⃣  insert one DB row per product ------------------------------------------
    with db() as con:
        for i in range(len(p_name)):
            con.execute("""
                INSERT INTO stores(
                    store_id, store_name, store_desc,
                    email, owner_phone, owner_pin, qr_file,
                    p_name,  p_d,   p_p,  p_q,  p_i,
                    approved, created_at
                )
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                store_id, store_name, store_desc,
                owner_email, owner_phone, pin_hash, qr_name,
                p_name[i], p_d[i], p_p[i], p_q[i], img_lst[i],
                0,datetime.now()  # ← inserted manually
            ))


    # 6️  notify TinyCart admin ---------------------------------------------------
    send_email(
        "tinycart9005@gmail.com",
        "🆕 Store awaiting approval",
        f"Store ID: {store_id}\n"
        f"Store name: {store_name}\n\n"
        "Visit the admin dashboard to approve or reject."
    )

    # 7️  success page ------------------------------------------------------------
    public_link = url_for("view_store", store_id=store_id, _external=True)
    return render_template("store_created.html",
                           full_url=public_link,
                           store_code=store_id)
 
@app.route("/store/<store_id>", endpoint="view_store")
def view_store(store_id: str):
    """
    Public storefront. One product == one DB row in `stores`.
    """

    cur = db().cursor()
    rows = cur.execute(
        "SELECT * FROM stores WHERE store_id=? AND approved=1",
        (store_id,)
    ).fetchall()

    if not rows:
        return "Store not found or not yet approved.", 404

    # rows[0] holds the general store data (name, desc, owner mail, phone …)
    store_name, store_desc = rows[0][1], rows[0][2]
    owner_email, owner_phone = rows[0][3], rows[0][4]

    return render_template(
        "store.html",
        store_name        = store_name,
        store_description = store_desc,
        owner_email       = owner_email,
        owner_phone       = owner_phone,
        products          = rows,        # the full product list
        store_id          = store_id
    )

 
@app.route("/add-to-cart", methods=["POST"])
def add_to_cart():
    store_id = request.form["store_id"]
    pid      = int(request.form["product_id"])
    qty      = int(request.form["qty"])
    stock    = _max_stock(store_id, pid)

    cart = session.get("cart", [])
    existing = next((i for i in cart if i["store_id"]==store_id and i["product_id"]==pid), None)
    if existing:
        existing["qty"] = min(existing["qty"] + qty, stock)
    else:
        cart.append({"store_id": store_id, "product_id": pid, "qty": min(qty, stock)})
    session["cart"] = cart; session.modified = True
    return redirect(url_for("view_store", store_id=store_id))

@app.route("/cart/<store_id>")
def view_cart(store_id):
    raw = [i for i in session.get("cart", []) if i["store_id"] == store_id]
    if not raw:
        return render_template("cart_empty.html", store_id=store_id)

    # merge duplicates
    merged = {}
    for it in raw:
        merged[it["product_id"]] = merged.get(it["product_id"], 0) + it["qty"]
    cart = [{"store_id": store_id, "product_id": pid, "qty": qty}
            for pid, qty in merged.items()]
    session["cart"] = cart
    session.modified = True

    # build display rows
    items = []
    total = 0
    c = db().cursor()
    cleaned_cart = []

    for it in cart:
        row = c.execute(
            "SELECT p_name, p_p, p_q, p_i FROM stores WHERE store_id=? LIMIT 1 OFFSET ?",
            (store_id, it["product_id"])
        ).fetchone()

        if not row:
            # remove deleted product from session cart
            session["cart"] = [x for x in session["cart"] if not (x["store_id"] == store_id and x["product_id"] == it["product_id"])]
            session.modified = True
            continue

        name, price, stock, img = row
        qty = min(it["qty"], stock)
        it["qty"] = qty
        sub = price * qty
        total += sub
        items.append({
            "pid": it["product_id"],
            "name": name,
            "price": price,
            "qty": qty,
            "subtotal": sub,
            "stock": stock,
            "img": img
        })

    return render_template("cart.html", items=items, total=total, store_id=store_id)

@app.route("/remove-from-cart/<store_id>/<int:pid>")
def remove_from_cart(store_id,pid):
    session["cart"]=[i for i in session.get("cart",[])
                     if not(i["store_id"]==store_id and i["product_id"]==pid)]
    return redirect(url_for("view_cart", store_id=store_id))

@app.route("/update-cart", methods=["POST"])
def update_cart():
    store_id=request.form["store_id"]; pid=int(request.form["product_id"]); qty=int(request.form["qty"])
    stock=_max_stock(store_id,pid); qty=max(1,min(qty,stock))
    for it in session.get("cart",[]):
        if it["store_id"]==store_id and it["product_id"]==pid: it["qty"]=qty
    session.modified=True
    return redirect(url_for("view_cart", store_id=store_id))

 
def _create_order(store_id: str, items: list[dict]):
    """items = [{'pid': 0, 'qty': 3}, …]"""
    amount = 0
    c = db().cursor()
    final_items = []

    for it in items:
        row = c.execute(
            "SELECT p_name, p_p, p_i FROM stores WHERE store_id=? LIMIT 1 OFFSET ?",
            (store_id, it["pid"])
        ).fetchone()

        if not row:
            continue  # Product deleted — skip it

        name, price, img = row
        qty = it["qty"]
        amount += price * qty

        final_items.append({
            "pid": it["pid"],
            "qty": qty,
            "name": name,
            "img": img
        })

    order_id = uuid.uuid4().hex[:10]

    c.execute("""INSERT INTO orders
        (order_id, store_id, items_json, amount,
         customer_name, customer_phone, customer_email, address,
         status, payment_mode)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        order_id, store_id,
        json.dumps(final_items),  # 🆕 includes name and img
        amount,
        "", "", "", "",           # customer fields filled later
        "pending", ""
    ))

    c.connection.commit()
    c.connection.close()
    return order_id, amount


# 
@app.route("/checkout-cart", methods=["POST"])
def checkout_cart():
    store_id = request.form["store_id"]
    cart = [i for i in session.get("cart", []) if i["store_id"] == store_id]
    if not cart:
        return redirect(url_for("view_cart", store_id=store_id))

    # filter valid products only
    items = []
    c = db().cursor()
    for i in cart:
        row = c.execute(
            "SELECT 1 FROM stores WHERE store_id=? LIMIT 1 OFFSET ?",
            (store_id, i["product_id"])
        ).fetchone()
        if row:
            items.append({"pid": i["product_id"], "qty": i["qty"]})
        else:
            # remove deleted product from cart
            session["cart"] = [x for x in session["cart"]
                               if not (x["store_id"] == store_id and x["product_id"] == i["product_id"])]
            session.modified = True

    if not items:
        return redirect(url_for("view_cart", store_id=store_id))

    order_id, total = _create_order(store_id, items)
    return render_template("checkout.html",
                           store_id=store_id,
                           order_id=order_id,
                           product_name="cart items",
                           qty=sum(i['qty'] for i in items),
                           total=total,
                           is_cart=True)


# Buy now (older)
@app.route("/checkout", methods=["POST"])
def checkout_single():
    store_id=request.form["store_id"]; pid=int(request.form["product_id"]); qty=int(request.form["qty"])
    order_id,_=_create_order(store_id,[{"pid":pid,"qty":qty}])
    name,price=db().cursor().execute(
        "SELECT p_name,p_p FROM stores WHERE store_id=? LIMIT 1 OFFSET ?",
        (store_id,pid)).fetchone()
    return render_template("checkout.html",store_id=store_id,order_id=order_id,
                           product_name=name,qty=qty,total=price*qty,is_cart=False)

 
@app.route("/payment-options", methods=["POST"])
def payment_options():
    order_id  = request.form["order_id"]
    store_id  = request.form["store_id"]
    pay_mode  = request.form["pay_mode"]           # "cod" or "online"

    #  save customer data + payment mode
    with db() as con:
        con.execute("""
            UPDATE orders
               SET customer_name  = ?,
                   customer_phone = ?,
                   customer_email = ?,
                   address        = ?,
                   payment_mode   = ?
             WHERE order_id       = ?
        """, (
            request.form["customer_name"].strip(),
            request.form["customer_phone"].strip(),
            request.form["customer_email"].strip(),
            request.form["address"].strip(),
            pay_mode,
            order_id,
        ))

    #  SAVE EMAIL IN SESSION FOR CUSTOMER DASHBOARD
    session['customer_email'] = request.form["customer_email"].strip()
    _deduct_stock(order_id)


    #  Notify store owner about EVERY new order (COD or ONLINE)
    owner_email_row = db().cursor().execute(
        "SELECT email FROM stores WHERE store_id=? LIMIT 1", (store_id,)
    ).fetchone()
    if owner_email_row and owner_email_row[0]:
        dashboard_link = url_for('owner_login', store=store_id, _external=True)
        send_email(
            owner_email_row[0],
            "🎒 New TinyCart order – action needed!",
            f"Hi there!\n\n"
            f"Order ID: {order_id}\n"
            f"Payment mode: {pay_mode.upper()}\n\n"
            f"Please check your dashboard and approve:\n{dashboard_link}\n\n"
            "You're getting orders — yay! 🎉"
        )

    #   COD   
    if pay_mode == "cod":
        # send confirmation email to customer
        cust_email = request.form["customer_email"].strip()
        if cust_email:
            send_email(
                cust_email,
                "Your TinyCart order is confirmed 🛍️",
                "Thank you for ordering with TinyCart!\n\n"
                "Your payment will be collected on delivery.\n"
                "You’ll receive a second email once the seller marks it paid.\n\n"
                f"Order ID: {order_id}"
            )

        # simple thank‑you page – order stays PENDING until seller clicks “Paid”
        qty = sum(i["qty"] for i in json.loads(
            db().cursor().execute(
                "SELECT items_json FROM orders WHERE order_id=?", (order_id,)
            ).fetchone()[0]
        ))
        return render_template(
            "order_complete.html",
            message="Order placed! Please pay cash on delivery.",
            pname="your items",
            qty=qty,
            store_id=store_id
        )

    #  ONLINE   (notify owner, then show QR)
    owner_email_row = db().cursor().execute(
        "SELECT email FROM stores WHERE store_id=? LIMIT 1", (store_id,)
    ).fetchone()
    if owner_email_row and owner_email_row[0]:
        dashboard_link = url_for("owner_login", store=store_id, _external=True)
        send_email(
            owner_email_row[0],
            "🎒 New TinyCart order – awaiting payment!",
            f"Order ID: {order_id}\n"
            f"Payment mode: ONLINE\n\n"
            f"Open dashboard to approve:\n{dashboard_link}"
        )

    # show QR page
    qr_file = _get_qr(store_id)
    if qr_file:                       # custom UPI QR
        return render_template("await_payment.html",
                               qr_file=qr_file,
                               order_id=order_id,
                               amount=_order_total(order_id))

    # fallback demo QR
    img  = qrcode.make(f"upi://pay?pa=demo@upi&am={_order_total(order_id)}&cu=INR")
    buf  = BytesIO(); img.save(buf, format="PNG")
    qr64 = base64.b64encode(buf.getvalue()).decode()
    return render_template("await_payment.html",
                           qr=qr64,
                           order_id=order_id,
                           amount=_order_total(order_id))


 
def _finalize(order_id:str, msg:str):
    con=db(); c=con.cursor()
    row=c.execute("SELECT store_id,items_json,status FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row: con.close(); return "Order not found."
    store_id,items_json,status=row
    if status!="pending":
        con.close(); flash("Order already processed."); return redirect(url_for("view_store",store_id=store_id))

    items=json.loads(items_json)
    for it in items:
        stock=_max_stock(store_id,it["pid"])
        if stock<it["qty"]:
            con.close(); return "<h3>Insufficient stock, order halted.</h3>"
        c.execute("""UPDATE stores SET p_q=p_q-? WHERE store_id=? AND
                     rowid IN(SELECT rowid FROM stores WHERE store_id=? LIMIT 1 OFFSET ?)""",
                  (it["qty"],store_id,store_id,it["pid"]))
    c.execute("UPDATE orders SET status='paid' WHERE order_id=?", (order_id,))
    con.commit(); con.close()
    session["cart"]=[i for i in session.get("cart",[]) if i["store_id"]!=store_id]
    return render_template("order_complete.html",message=msg,
                           pname="your items",qty=sum(i['qty'] for i in items),
                           store_id=store_id)
def _deduct_stock(order_id: str):
    """Only deduct stock for the order — don’t change order status."""
    con = db(); c = con.cursor()
    row = c.execute("SELECT store_id, items_json FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        con.close()
        return

    store_id, items_json = row
    items = json.loads(items_json)
    for it in items:
        stock = _max_stock(store_id, it["pid"])
        if stock >= it["qty"]:
            c.execute("""UPDATE stores SET p_q=p_q-? WHERE store_id=? AND
                         rowid IN(SELECT rowid FROM stores WHERE store_id=? LIMIT 1 OFFSET ?)""",
                      (it["qty"], store_id, store_id, it["pid"]))
    con.commit()
    con.close()

 
@app.route("/cancel/<order_id>")
def cancel_order(order_id):
    con = db(); c = con.cursor()
    row = c.execute("SELECT store_id, status, items_json FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row:
        return "No such order."
    store_id, status, items_json = row

    # Always restore stock, whether paid or pending
    items = json.loads(items_json)
    for it in items:
        c.execute("""UPDATE stores SET p_q = p_q + ? WHERE store_id = ? AND
                     rowid IN (SELECT rowid FROM stores WHERE store_id = ? LIMIT 1 OFFSET ?)""",
                  (it["qty"], store_id, store_id, it["pid"]))

    # Cancel the order
    c.execute("UPDATE orders SET status = 'cancelled' WHERE order_id = ?", (order_id,))
    con.commit(); con.close()
    return "Order cancelled."

# ───────── owner login & dashboard ─────────
@app.route("/owner-login", methods=["GET", "POST"])
def owner_login():
    """
    Owner arrives either via:
      • Direct link  /owner-login?store=<store_id>
      • Manual visit, then types Store‑ID + PIN
    After successful PIN check we save the store‑id in session["owner"].
    """
    preset = request.args.get("store", "").strip()        # prefills form
    if request.method == "POST":
        store_id = request.form["store_id"].strip()
        pin_hash = hashlib.sha256(request.form["pin"].encode()).hexdigest()

        ok = db().cursor().execute(
            "SELECT 1 FROM stores WHERE store_id=? AND owner_pin=? LIMIT 1",
            (store_id, pin_hash)
        ).fetchone()

        if ok:
            session["owner"] = store_id
            return redirect(url_for("owner_orders", store_id=store_id))

        flash("Wrong PIN")          # bad credentials
        preset = store_id           # keep what they typed

    return render_template("owner_login.html", store_id=preset)
 
from datetime import datetime  # Ensure this is imported at the top

@app.route("/update-store", methods=["POST"])
def update_store():
    store_id = session.get("owner")
    if not store_id:
        return "Unauthorized", 403

    # ── general store data ──
    storename   = request.form["storename"]
    description = request.form["description"]
    email       = request.form["email"]
    phone       = request.form["owner_phone"]

    # ── product arrays ──
    product_ids   = request.form.getlist("product_id[]")   # rowid or ""
    delete_ids    = request.form.getlist("delete_product[]")  # newly added
    pnames        = request.form.getlist("pname[]")
    pds           = request.form.getlist("pd[]")
    pqs           = request.form.getlist("pq[]")
    pps           = request.form.getlist("pp[]")
    current_imgs  = request.form.getlist("current_img[]")
    uploaded_imgs = request.files.getlist("pi[]")

    # ── optional new store‑level QR ──
    qr_name = None
    qr_file = request.files.get("qr_img")
    if qr_file and qr_file.filename:
        qr_name = secure_filename(qr_file.filename)
        qr_file.save(os.path.join(app.config["UPLOAD_FOLDER"], qr_name))

    with db() as con:
        cur = con.cursor()

        # ── update shared store data ──
        if qr_name:
            cur.execute("""
                UPDATE stores
                   SET store_name  = ?,
                       store_desc  = ?,
                       email       = ?,
                       owner_phone = ?,
                       qr_file     = ?
                 WHERE store_id    = ?
            """, (storename, description, email, phone, qr_name, store_id))
        else:
            cur.execute("""
                UPDATE stores
                   SET store_name  = ?,
                       store_desc  = ?,
                       email       = ?,
                       owner_phone = ?
                 WHERE store_id    = ?
            """, (storename, description, email, phone, store_id))

        # ── process each product card ──
        for idx, rid in enumerate(product_ids):
            if rid and rid in delete_ids:
                # DELETE selected product
                cur.execute("DELETE FROM stores WHERE store_id = ? AND rowid = ?", (store_id, rid))
                continue

            # Get form data
            name = pnames[idx].strip()
            desc = pds[idx].strip()
            qty_raw = pqs[idx].strip()
            price_raw = pps[idx].strip()

            # Handle images
            new_img_file = uploaded_imgs[idx] if idx < len(uploaded_imgs) else None
            img_name = current_imgs[idx].strip() if idx < len(current_imgs) else ""

            # Determine final image (if uploaded, use it; else keep old one)
            if new_img_file and new_img_file.filename:
                img_name = secure_filename(new_img_file.filename)
                new_img_file.save(os.path.join(app.config["UPLOAD_FOLDER"], img_name))

            # ❗ Validate required fields
            if not (name or desc or qty_raw or price_raw or img_name):
                continue

            if not name or not desc or not qty_raw or not price_raw:
                flash("❗ Please fill all product details (name, description, quantity, price).", "error")
                return redirect(url_for("edit_store", store_id=store_id))

            if not rid and not img_name:
                flash("❗ Please upload an image for all new products.", "error")
                return redirect(url_for("edit_store", store_id=store_id))

            try:
                qty = int(qty_raw)
                price = float(price_raw)
            except ValueError:
                flash("❗ Quantity must be an integer and price must be a number.", "error")
                return redirect(url_for("edit_store", store_id=store_id))

            if rid:
                # UPDATE existing product
                cur.execute("""
                    UPDATE stores
                       SET p_name = ?, p_d = ?, p_q = ?, p_p = ?, p_i = ?
                     WHERE store_id = ? AND rowid = ?
                """, (name, desc, qty, price, img_name, store_id, rid))
            else:
                # INSERT new product
                cur.execute("""
                    INSERT INTO stores(
                        store_id, store_name, store_desc,
                        email, owner_phone, owner_pin, qr_file,
                        p_name, p_d, p_p, p_q, p_i, approved, created_at
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    store_id, storename, description,
                    email, phone, "", qr_name or "",
                    name, desc, price, qty, img_name,
                    1, datetime.now()
                ))

        con.commit()

    flash("Store updated successfully!", "success")
    return redirect(url_for("owner_orders", store_id=store_id))

@app.route("/edit-store/<store_id>")
def edit_store(store_id):
    if session.get("owner") != store_id:
        return "Unauthorized", 403

    add_count = int(request.args.get("add_count", 3))  # default = 3

    with db() as con:
        cur = con.cursor()
        cur.execute("""
            SELECT store_name, store_desc, email, owner_phone
              FROM stores
             WHERE store_id = ?
             LIMIT 1
        """, (store_id,))
        store = cur.fetchone()

        cur.execute("""
            SELECT rowid, p_name, p_d, p_q, p_p, p_i
              FROM stores
             WHERE store_id = ?
        """, (store_id,))
        products = cur.fetchall()

    return render_template(
        "edit_store.html",
        store     = store,
        products  = products,
        store_id  = store_id,
        add_count = add_count
    )



 
@app.route("/owner/<store_id>/orders", endpoint="owner_orders")
def owner_orders(store_id):
    row = db().cursor().execute(
        "SELECT approved FROM stores WHERE store_id=? LIMIT 1",
        (store_id,)
    ).fetchone()

    if not row or row[0] != 1:
        return "⏳  Your store is awaiting TinyCart approval.", 403
    if session.get("owner") != store_id:
        return "Not authorised", 403

    c = db().cursor()
    rows = c.execute("""
        SELECT order_id, amount,
               customer_name, customer_phone, customer_email, address,
               payment_mode, status, items_json, created_at
        FROM   orders
        WHERE  store_id = ?
        ORDER  BY created_at DESC
    """, (store_id,)).fetchall()

    orders = []
    for oid, amt, cn, cp, cmail, addr, mode, stat, items_js, ts in rows:
        if not (cn and cp and cmail) or (mode is None or mode.upper() not in ["COD", "ONLINE"]):
            continue

        plist = []
        items = json.loads(items_js or "[]")
        for it in items:
            name = it.get("name", "Item")
            img = it.get("img", "")
            qty = it["qty"]
            plist.append({"qty": qty, "name": name, "img": img})

        if stat == "paid":
            stat_icon = "✅"
        elif stat in ["cancelled", "cancelled-by-customer", "cancelled-by-owner"]:
            stat_icon = "❌"
        else:
            stat_icon = "—"

        orders.append({
            "id": oid,
            "total": amt,
            "cust_name": cn,
            "cust_phone": cp,
            "cust_mail": cmail,
            "addr": addr,
            "mode": mode.upper(),
            "status": ("cancelled-by-owner" if stat.lower() == "cancelled" and mode.upper() == "ONLINE" else stat.strip().lower()),

            "stat_icon": stat_icon,
            "plist": plist
        })

    return render_template("owner_orders.html",
                           orders=orders,
                           store_id=store_id)



@app.route("/owner/<store_id>/cancel-refund/<int:order_id>", methods=["POST"])
def cancel_and_refund(store_id, order_id):
    if session.get("owner") != store_id:
        return "Not authorised", 403

    c = db().cursor()
    row = c.execute("""
        SELECT payment_mode, customer_email, status
        FROM orders
        WHERE order_id = ? AND store_id = ?
    """, (order_id, store_id)).fetchone()

    if not row:
        return "Order not found", 404

    mode, email, status = row

    # Allow cancellation only if paid and ONLINE
    if mode.upper() != "ONLINE" or status != "paid":
        flash("Only ONLINE + paid orders can be refunded.", "error")
        return redirect(request.referrer or "/")

    # Mark as cancelled
    with db() as con:
        con.execute("""
            UPDATE orders
            SET status = 'cancelled-by-owner',
                cancelled = 1,
                cancelled_by = 'owner'
            WHERE order_id = ?
        """, (order_id,))

    # Send refund confirmation email
    if email:
        send_email(
            email,
            "Refund Credited 💸",
            "Your refund has been credited for the cancelled order.\n\n"
            "Please check your account. Thanks for shopping with us!"
        )

    flash("Order cancelled and refund email sent to customer.", "info")
    return redirect(url_for("owner_orders", store_id=store_id))

 
@app.route("/order-cancelled/<order_id>")
def order_cancelled(order_id: str):
    c = db().cursor()
    row = c.execute(
        "SELECT store_id FROM orders WHERE order_id=?", (order_id,)
    ).fetchone()
    if not row:
        return "Order not found", 404

    return render_template("order_cancelled.html", store_id=row[0])

# ───────── mark order as PAID (only for online/QR orders) ─────────
@app.route("/owner/<store_id>/mark-paid/<order_id>", methods=["POST"])
def owner_mark_paid(store_id, order_id):
    # 🛡  protect the route, but compare as strings
    if str(session.get("owner")) != str(store_id):
        return "Unauthorised", 403

    # Get payment mode and email
    row = db().cursor().execute(
        "SELECT payment_mode, customer_email FROM orders WHERE order_id=?", (order_id,)
    ).fetchone()

    if row:
        mode, email = row

        if mode == "ONLINE":
            with db() as con:
                con.execute("""
                    UPDATE orders
                       SET status = 'paid',
                           updated_at = CURRENT_TIMESTAMP
                     WHERE order_id = ?
                """, (order_id,))
        else:
            # COD → update status and stock
            with db() as con:
                con.execute("""
                    UPDATE orders
                       SET status = 'paid',
                           updated_at = CURRENT_TIMESTAMP
                     WHERE order_id = ?
                """, (order_id,))
            _finalize(order_id, "🎉 Payment confirmed! Order marked paid.")

        # Send e-mail to customer
        if email:
            if mode == "ONLINE":
                send_email(
                    email,
                    "Online payment received – thank you! 🎉",
                    "We’ve received your online payment. Your order has been marked as paid.\n\n"
                    f"Order ID: {order_id}\n"
                    "Thanks for shopping with TinyCart!"
                )
            else:  # COD
                send_email(
                    email,
                    "Payment received – thank you! 🎉",
                    "We’ve received your payment on delivery. Thank you for shopping with us!\n\n"
                    f"Order ID: {order_id}\n"
                    "Happy shopping with TinyCart!"
                )

    return redirect(url_for("owner_orders", store_id=store_id))

 
@app.route("/owner/<store_id>/cancel/<order_id>", methods=["POST"])
def owner_cancel_order(store_id, order_id):
    if session.get("owner") != store_id:
        return "Unauthorised", 403

    # get payment mode, status, and email
    row = db().cursor().execute(
        "SELECT payment_mode, status, customer_email FROM orders WHERE order_id=?",
        (order_id,)
    ).fetchone()

    if not row:
        flash("Order not found.")
        return redirect(url_for("owner_orders", store_id=store_id))

    mode, status, email = row

    # prevent cancel after paid (COD only)
    if status == "paid" and mode == "COD":
        flash("You cannot cancel a paid COD order.")
        return redirect(url_for("owner_orders", store_id=store_id))

    # cancel the order
    cancel_order(order_id)

    # send email based on status/mode
  # send email based on status/mode
    if email:
        if status == "paid" and mode.upper() == "ONLINE":
            send_email(
                email,
                "Order Cancelled – Refund Initiated 💸",
                "We're sorry to inform you that your order has been cancelled by the seller.\n"
                "Since you had paid online, your refund will be processed within 2 working days.\n\n"
                f"Order ID: {order_id}\n"
                "Thank you for shopping with TinyCart."
            )
        else:
            send_email(
                email,
                "Order Cancelled 😔",
                "Unfortunately the seller has cancelled your order.\n\n"
                f"Order ID: {order_id}\n"
                "You can visit the store to explore and place a new order anytime."
            )


    flash("Order cancelled.")
    return redirect(url_for("owner_orders", store_id=store_id))





@app.route("/order-status/<order_id>")
def order_status(order_id: str):
    """Polled by the waiting page so the buyer knows when seller marked it paid."""
    row = db().cursor().execute(
        "SELECT status FROM orders WHERE order_id=?", (order_id,)
    ).fetchone()
    return {"status": row[0] if row else "none"}


@app.route("/order-done/<order_id>")
def order_done(order_id: str):
    c = db().cursor()
    row = c.execute(
        "SELECT store_id, status, items_json FROM orders WHERE order_id=?",
        (order_id,)
    ).fetchone()
    if not row:
        return "Order not found", 404

    store_id, status, items_json = row
    if status != "paid":
        return "Order still awaiting seller approval …", 202

    qty = sum(i["qty"] for i in json.loads(items_json))
    return render_template(
        "order_complete.html",
        message="Payment received! Your order will be shipped soon.",
        pname="your items",
        qty=qty,
        store_id=store_id
    )
 
from datetime import datetime
import json
from flask import session, redirect, render_template

 
@app.route("/customer-dashboard")
def customer_dashboard():
    WINDOW_MIN = 5  # 5-minute cancel window

    cust_email = session.get("customer_email")
    if not cust_email:
        return redirect("/")

    c = db().cursor()
    rows = c.execute("""
        SELECT order_id, store_id, amount, items_json,
               status, created_at, payment_mode, updated_at
        FROM   orders
        WHERE  customer_email = ?
        ORDER  BY created_at DESC
    """, (cust_email,)).fetchall()

    orders = []
    for oid, sid, amt, items_js, stat, created_at, mode, updated_at in rows:
        store_name = c.execute("SELECT store_name FROM stores WHERE store_id=? LIMIT 1",
                               (sid,)).fetchone()
        store_name = store_name[0] if store_name else sid
        store_url = url_for("view_store", store_id=sid)

        plist = []
        for it in json.loads(items_js or "[]"):
            img = it.get("img", "")
            qty = it["qty"]
            img_url = url_for("static", filename=f"images/{img}") if img \
                      else url_for("static", filename="images/no_image.png")
            plist.append({"qty": qty, "img_url": img_url})

        t_start = None
        base_time = updated_at if (mode == "ONLINE" and stat == "paid") else created_at

        if isinstance(base_time, datetime):
            t_start = base_time
        else:
            for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
                try:
                    t_start = datetime.strptime(base_time, fmt)
                    break
                except:
                    continue

        remaining_txt = "Invalid time"
        can_cancel = False

        if t_start:
            elapsed = (datetime.utcnow() - t_start).total_seconds()
            remaining_sec = max(WINDOW_MIN * 60 - int(elapsed), 0)

            can_cancel = (stat in ["pending", "paid"]) and remaining_sec > 0
            remaining_txt = (
                "Expired" if remaining_sec == 0 else
                f"{remaining_sec // 60} min" if remaining_sec >= 60 else
                f"{remaining_sec} sec"
            )

        orders.append({
            "id": oid,
            "store_id": sid,
            "store_name": store_name,
            "store_url": store_url,
            "total": amt,
            "plist": plist,
            "stat": stat,
            "remaining_txt": remaining_txt,
            "can_cancel": can_cancel
        })

    return render_template("customer_dashboard.html",
                           orders=orders,
                           customer_email=cust_email)




 
@app.route("/customer-cancel/<order_id>", methods=["POST"])
def customer_cancel(order_id):
    WINDOW_MIN = 5  # Cancel window = 5 minutes

    with db() as con:
        c = con.cursor()
        row = c.execute("""
            SELECT store_id, status, payment_mode, created_at, updated_at, customer_email
            FROM orders WHERE order_id = ?
        """, (order_id,)).fetchone()

        if not row:
            flash("Order not found.", "error")
            return redirect(request.referrer or "/")

        store_id, status, mode, created_at, updated_at, cust_email = row

        # Determine start time for timer
        try:
            base_time = updated_at if status == 'paid' else created_at
            if isinstance(base_time, str):
                base_time = datetime.strptime(base_time.split(".")[0], "%Y-%m-%d %H:%M:%S")
        except Exception:
            base_time = datetime.utcnow()

        #  Only allow cancel if status is pending or paid
        if status not in ("pending", "paid"):
            flash("This order can no longer be cancelled.", "error")
            return redirect(request.referrer or "/")

        #  Cancel window expired?
        if (datetime.utcnow() - base_time).total_seconds() > WINDOW_MIN * 60:
            flash("Cancel window has expired.", "error")
            return redirect(request.referrer or "/")

        #  Restore product quantity
        items_row = c.execute("SELECT items_json FROM orders WHERE order_id=?", (order_id,)).fetchone()
        if items_row:
            items = json.loads(items_row[0])
            for it in items:
                c.execute("""UPDATE stores SET p_q = p_q + ? WHERE store_id = ? AND
                             rowid IN (SELECT rowid FROM stores WHERE store_id = ? LIMIT 1 OFFSET ?)""",
                          (it["qty"], store_id, store_id, it["pid"]))

        #  Cancel the order
        c.execute("UPDATE orders SET status='cancelled-by-customer' WHERE order_id=?", (order_id,))

        # ✉ Notify store owner
        owner_email = c.execute(
            "SELECT email FROM stores WHERE store_id=? LIMIT 1", (store_id,)
        ).fetchone()
        if owner_email and owner_email[0]:
            send_email(
                owner_email[0],
                "Order cancelled by customer ❌",
                f"The customer has cancelled order {order_id}.\n"
                f"Payment mode: {mode.upper()}\n"
                "Please refund if it was paid online."
            )

    flash("Order cancelled. Confirmation sent.", "info")
    return redirect(url_for("customer_dashboard"))



def alter_db_add_payment_mode():
    try:
        with db() as con:
            con.execute("ALTER TABLE orders ADD COLUMN payment_mode TEXT")
    except:
        pass
      # ignore if already added
@app.route("/owner/<store_id>/send-refund/<order_id>", methods=["POST"])
def send_refund_email(store_id, order_id):
    if session.get("owner") != store_id:
        return "Not authorised", 403

    c = db().cursor()
    row = c.execute("""
        SELECT customer_email, payment_mode, status
        FROM orders
        WHERE order_id = ? AND store_id = ?
    """, (order_id, store_id)).fetchone()

    if not row:
        flash("Order not found.", "error")
        return redirect(request.referrer or "/")

    email, mode, status = row

    if not email or mode.upper() != "ONLINE" or "cancelled" not in status:
        flash("Refund mail not applicable.", "error")
        return redirect(request.referrer or "/")

    send_email(
        email,
        "Refund Credited 💸",
        f"Hi! Your refund for the cancelled order ({order_id}) has been successfully credited.\n\n"
        "Please check your account or contact support if it hasn't appeared yet.\n"
        "Thank you for shopping with TinyCart!"
    )

    flash("Refund confirmation email sent to customer.", "info")
    return redirect(url_for("owner_orders", store_id=store_id))

def get_products_by_store():
    """
    Returns a dict: {store_id: [(p_name, p_i_filename), ...]}
    """
    cur = db().cursor()
    rows = cur.execute(
        "SELECT store_id, p_name, p_i FROM stores ORDER BY rowid"
    ).fetchall()

    prod_dict = {}
    for sid, pname, pimg in rows:
        prod_dict.setdefault(sid, []).append((pname, pimg))
    return prod_dict



@app.route("/tiny-admin/stores")
def tiny_admin_stores():
    if not session.get("is_tinycart_admin"):
        return "❌  Not accessible to you", 403

    # main store rows (one per store, newest first)
    rows = db().cursor().execute("""
        SELECT store_id, store_name, email, owner_phone, approved, MAX(created_at) AS created_at
        FROM stores
        GROUP BY store_id
        ORDER BY MAX(created_at) DESC
    """).fetchall()

    # extra dict with product lists
    product_map = get_products_by_store()

    return render_template("tiny_admin_dashboard.html",
                           rows=rows,
                           product_map=product_map)




@app.post("/tiny-admin/approve/<store_id>")
def tiny_admin_approve(store_id):
    if not session.get("is_tinycart_admin"):  # guard
        return "❌", 403

    with db() as con:
        con.execute("UPDATE stores SET approved=1 WHERE store_id=?", (store_id,))

    # mail the seller
    email = db().cursor().execute(
        "SELECT email FROM stores WHERE store_id=? LIMIT 1", (store_id,)
    ).fetchone()[0]
    send_email(
        email,
        "🎉 Your TinyCart store is live!",
        "Hi!\nTinyCart has approved your store. "
        "Share your public link and start selling!\n\n"
        f"Link: {request.host_url.rstrip('/')}/store/{store_id}"
    )
    return redirect("/tiny-admin/stores")


@app.post("/tiny-admin/reject/<store_id>")
def tiny_admin_reject(store_id):
    if not session.get("is_tinycart_admin"):
        return "❌", 403

    with db() as con:
        con.execute("UPDATE stores SET approved=-1 WHERE store_id=?", (store_id,))

    email = db().cursor().execute(
        "SELECT email FROM stores WHERE store_id=? LIMIT 1", (store_id,)
    ).fetchone()[0]
    send_email(
        email,
        "Store request declined 😔",
        "We’re sorry, but your store didn’t meet TinyCart’s guidelines.\n"
        "Feel free to contact us for details."
    )
    return redirect("/tiny-admin/stores")

@app.route("/admin-dashboard")
def admin_dashboard():
    if session.get("admin_email") != "tinycart9005@gmail.com":
        return "Not authorized", 403
 

@app.route("/admin-login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        pwd   = request.form["password"]

        row = db().cursor().execute(
            "SELECT password_hash FROM admin_users WHERE email=? LIMIT 1",
            (email,)
        ).fetchone()

        if row and check_password_hash(row[0], pwd):
            session["is_tinycart_admin"] = True
            session["admin_email"]       = email
            return redirect("/tiny-admin/stores")

        flash("❌  Invalid e‑mail or password", "error")

    return render_template("admin_login.html")
 

    # Your dashboard logic

#  run 
if __name__=="__main__":
    app.run(debug=True)