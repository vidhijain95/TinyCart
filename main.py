# main.py  – TinyCart (orders + owner‑PIN + stock‑safe + owner approval)
from dotenv import load_dotenv
load_dotenv()  # Load environment variables from .env

import os, uuid, sqlite3, json, hashlib, base64, qrcode
from io import BytesIO
from flask import Flask, render_template, request, redirect, url_for, session, flash
from werkzeug.utils import secure_filename
import smtplib, ssl
from email.message import EmailMessage
from flask import flash, redirect, url_for
 # ───────── Forgot‑PIN flow ─────────
from itsdangerous import URLSafeTimedSerializer
#
#  imports
 

app = Flask(__name__)
app.secret_key = "super-secret"

 
s = URLSafeTimedSerializer(app.secret_key)

# now it's safe to define:
 

 



# — A. enter e‑mail form —



# Gmail sender details
SMTP_USER     = os.getenv("SMTP_USER")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")
SMTP_SERVER   = "smtp.gmail.com"
SMTP_PORT     = 465
SENDER_NAME   = "TinyCart Store"
# ───────── Forgot‑PIN flow ─────────
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



# ───────── Flask & config ──────────
  # <‑‑ add here
             # change in production!

UPLOAD_FOLDER = "static/images"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ───────── DB helpers ──────────────
def db():
    return sqlite3.connect("tinycart.db", detect_types=sqlite3.PARSE_DECLTYPES)

def init_db():
    con = db(); c = con.cursor()
    # stores: one table row per *product*
    c.execute("""CREATE TABLE IF NOT EXISTS stores(
        store_id TEXT,  store_name  TEXT, store_desc TEXT,
        email    TEXT,  owner_phone TEXT, owner_pin TEXT,
        qr_file  TEXT,
        p_name   TEXT,  p_d         TEXT,
        p_p REAL, p_q INTEGER, p_i TEXT)""")

    # orders: one row per order
    c.execute("""CREATE TABLE IF NOT EXISTS orders(
        order_id TEXT PRIMARY KEY, store_id TEXT,
        items_json TEXT, amount REAL,
        customer_name TEXT, customer_phone TEXT, address TEXT,
        status TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""")
    con.commit(); con.close()
init_db()
def alter_db_once():
    with db() as con:
        cur = con.cursor()
        # add missing columns if they don’t exist yet
        for col_sql in (
            "ALTER TABLE orders ADD COLUMN payment_mode TEXT",
            "ALTER TABLE orders ADD COLUMN customer_email TEXT"
        ):
            try: cur.execute(col_sql)
            except sqlite3.OperationalError:
                pass   # already there

alter_db_once()    # run once on every start – harmless if already done


# ───────── tiny helpers ────────────
def _max_stock(store_id: str, pid: int) -> int:
    return db().cursor().execute(
        "SELECT p_q FROM stores WHERE store_id=? LIMIT 1 OFFSET ?",
        (store_id, pid)).fetchone()[0]

def _get_qr(store_id: str):
    row = db().cursor().execute(
        "SELECT qr_file FROM stores WHERE store_id=? LIMIT 1", (store_id,)).fetchone()
    return row[0] if row and row[0] else None

def _order_total(order_id: str):
    row = db().cursor().execute(
        "SELECT amount FROM orders WHERE order_id=?", (order_id,)).fetchone()
    return row[0] if row else 0.0

# ───────── home ────────────────────
@app.route("/")
def home():
    return render_template("homee.html")

# ───────── wizard: choose #products ─
@app.route("/create-store", methods=["GET", "POST"])
def choose_count():
    if request.method == "POST":
        return render_template("add_product.html",
                               count=int(request.form["count"]))
    return render_template("count.html")

# ───────── create store (POST) ─────
# ───────── create store (POST) ─────
# ───────── create store (POST) ───────────────────────────────────────────
@app.route("/submit-store", methods=["POST"])
def submit_store():
    store_id = uuid.uuid4().hex[:8]

    # 🔐 1.  Check the PIN
    raw_pin  = request.form["owner_pin"].strip()
    pin_hash = hashlib.sha256(raw_pin.encode()).hexdigest()

    taken = db().cursor().execute(
        "SELECT 1 FROM stores WHERE owner_pin=? LIMIT 1", (pin_hash,)
    ).fetchone()

    if taken:
        # 🚨 Show message & re‑render the SAME "add_product.html"
        flash("❗ This PIN is already used. Please choose a different, unique PIN.", "error")

        # how many product‑cards were on the form?
        prod_count = len(request.form.getlist("pname[]")) or 1

        return render_template(
            "add_product.html",
            count = prod_count,        # keeps the {% for i in range(count) %} happy
            form  = request.form       # lets you pre‑fill fields if you wish
        )

    # ---- rest of submit_store() unchanged ----


    # EITHER of the next two lines is fine – keep only one:
                        # simplest
    # return redirect(request.referrer or url_for("create_store"))

    # 2️⃣  Optional QR upload  (no deep validation for now)  ──────────────
    qr_name = ""
    f = request.files.get("qr_img")
    if f and f.filename:
        qr_name = secure_filename(f.filename)
        f.save(os.path.join(UPLOAD_FOLDER, qr_name))

    # 3️⃣  Collect product arrays  ────────────────────────────────────────
    p_name  = request.form.getlist("pname[]")
    p_d     = request.form.getlist("pd[]")
    p_p     = request.form.getlist("pp[]")
    p_q     = request.form.getlist("pq[]")

    img_lst = []
    for f in request.files.getlist("pi[]"):
        if f and f.filename:
            fn = secure_filename(f.filename)
            f.save(os.path.join(UPLOAD_FOLDER, fn))
            img_lst.append(fn)
        else:
            img_lst.append("")

    # 4️⃣  Owner e‑mail comes from the <input name="email"> field
    owner_email = request.form.get("email", "").strip()

    # 5️⃣  Insert one row per product  ────────────────────────────────────
    with db() as con:
        for i in range(len(p_name)):
            con.execute(
                """INSERT INTO stores VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    store_id,
                    request.form["storename"],
                    request.form["description"],
                    owner_email,
                    request.form["owner_phone"],
                    pin_hash,
                    qr_name,
                    p_name[i], p_d[i], p_p[i], p_q[i], img_lst[i],
                ),
            )

    # 6️⃣  Show success page with links  ──────────────────────────────────
    public_link = request.host_url.rstrip("/") + url_for("view_store", store_id=store_id)
    return render_template("store_created.html",
                           full_url   = public_link,
                           store_code = store_id)


    # 5️⃣  ─── done!  show success page with the public link ──
    link = request.host_url.rstrip("/") + url_for("view_store", store_id=store_id)
    return render_template("store_created.html", full_url=link, store_code=store_id)

# ───────── view store page (public link) ─────────
@app.route("/store/<store_id>", endpoint="view_store")
def view_store(store_id: str):
    """
    Public storefront.  One product == one DB row in `stores`.
    """
    cur   = db().cursor()
    rows  = cur.execute(
        "SELECT * FROM stores WHERE store_id=?",
        (store_id,)
    ).fetchall()

    if not rows:
        return "Store not found 🤷‍♂️", 404

    # rows[0] holds the general store data (name, desc, owner mail, phone …)
    store_name, store_desc = rows[0][1], rows[0][2]
    owner_email, owner_phone = rows[0][3], rows[0][4]

    return render_template(
        "store.html",
        store_name       = store_name,
        store_description= store_desc,
        owner_email      = owner_email,
        owner_phone      = owner_phone,
        products         = rows,        # the full product list
        store_id         = store_id
    )

# ───────── CART operations ─────────
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
    raw = [i for i in session.get("cart", []) if i["store_id"]==store_id]
    if not raw:
        return render_template("cart_empty.html", store_id=store_id)

    # merge duplicates
    merged = {}
    for it in raw:
        merged[it["product_id"]] = merged.get(it["product_id"], 0) + it["qty"]
    cart = [{"store_id": store_id, "product_id": pid, "qty": qty}
            for pid, qty in merged.items()]
    session["cart"] = cart; session.modified = True

    # build display rows
    items=[]; total=0; c=db().cursor()
    for it in cart:
        name,price,stock,img=c.execute(
            "SELECT p_name,p_p,p_q,p_i FROM stores WHERE store_id=? LIMIT 1 OFFSET ?",
            (store_id,it["product_id"])).fetchone()
        qty=min(it["qty"],stock); it["qty"]=qty
        sub=price*qty; total+=sub
        items.append({"pid":it["product_id"],"name":name,"price":price,
                      "qty":qty,"subtotal":sub,"stock":stock,"img":img})
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

# ───────── ORDER helper ────────────
def _create_order(store_id:str, items:list[dict]):
    """items = [{'pid':0,'qty':3}, …]"""
    amount=0; c=db().cursor()
    for it in items:
        price=c.execute("SELECT p_p FROM stores WHERE store_id=? LIMIT 1 OFFSET ?",
                        (store_id,it["pid"])).fetchone()[0]
        amount+=price*it["qty"]
    order_id=uuid.uuid4().hex[:10]
    c.execute("""INSERT INTO orders
    (order_id,store_id,items_json,amount,
     customer_name,customer_phone,customer_email,address,
     status,payment_mode)
    VALUES(?,?,?,?,?,?,?,?,?,?)""",
    (order_id,store_id,json.dumps(items),amount,
     "","","","",           # will be filled later
     "pending","")
)

    c.connection.commit(); c.connection.close()
    return order_id, amount

# ───────── checkout CART ───────────
@app.route("/checkout-cart", methods=["POST"])
def checkout_cart():
    store_id=request.form["store_id"]
    cart=[i for i in session.get("cart",[]) if i["store_id"]==store_id]
    if not cart: return redirect(url_for("view_cart", store_id=store_id))
    items=[{"pid":i["product_id"],"qty":i["qty"]} for i in cart]
    order_id,total=_create_order(store_id,items)
    return render_template("checkout.html",store_id=store_id,order_id=order_id,
                           product_name="cart items",qty=sum(i['qty'] for i in cart),
                           total=total,is_cart=True)

# ───────── checkout SINGLE ─────────
@app.route("/checkout", methods=["POST"])
def checkout_single():
    store_id=request.form["store_id"]; pid=int(request.form["product_id"]); qty=int(request.form["qty"])
    order_id,_=_create_order(store_id,[{"pid":pid,"qty":qty}])
    name,price=db().cursor().execute(
        "SELECT p_name,p_p FROM stores WHERE store_id=? LIMIT 1 OFFSET ?",
        (store_id,pid)).fetchone()
    return render_template("checkout.html",store_id=store_id,order_id=order_id,
                           product_name=name,qty=qty,total=price*qty,is_cart=False)

# ───────── choose payment ──────────
@app.route("/payment-options", methods=["POST"])
def payment_options():
    order_id  = request.form["order_id"]
    store_id  = request.form["store_id"]
    pay_mode  = request.form["pay_mode"]          # "cod" or "online"

    # 1️⃣  Save customer data + mode
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

    row = db().cursor().execute(
        "SELECT email, store_id FROM stores WHERE store_id=? LIMIT 1", (store_id,)
    ).fetchone()
    if row:
        email, store_id = row
        dashboard_link = url_for("owner_login", store=store_id, _external=True)
        send_email(
            email,
            "🛒 New TinyCart order waiting!",
            f"Hi there!\n\nOrder ID: {order_id}\nPayment mode: {pay_mode.upper()}\n"
            f"Please check your dashboard and approve:\n{dashboard_link}\n\n"
            "You're getting orders — yay! 🎉"
        )


    # 3️⃣  COD  →  straight to success page (still cancellable later)
    if pay_mode == "cod":
        return _finalize(order_id, "Order placed! Pay on delivery.")

    # 4️⃣  ONLINE  →  show QR / await‑payment page
    qr_file = _get_qr(store_id)
    if qr_file:          # custom QR uploaded by owner
        return render_template("await_payment.html",
                               qr_file=qr_file,
                               order_id=order_id,
                               amount=_order_total(order_id))

    # fallback: auto‑generated demo QR
    img  = qrcode.make(f"upi://pay?pa=demo@upi&am={_order_total(order_id)}&cu=INR")
    buf  = BytesIO(); img.save(buf, format="PNG")
    qr64 = base64.b64encode(buf.getvalue()).decode()

    return render_template("await_payment.html",
                           qr=qr64,
                           order_id=order_id,
                           amount=_order_total(order_id))

 
 

# ───────── finalise & deduct stock ──
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

# ───────── cancel order ────────────
@app.route("/cancel/<order_id>")
def cancel_order(order_id):
    con=db(); c=con.cursor()
    row=c.execute("SELECT store_id,status,items_json FROM orders WHERE order_id=?", (order_id,)).fetchone()
    if not row: return "No such order."
    store_id,status,items_json=row
    if status=="paid" and session.get("owner")!=store_id:
        return "Cannot cancel a paid order without owner login.",403
    if status=="paid":
        items=json.loads(items_json)
        for it in items:
            c.execute("""UPDATE stores SET p_q=p_q+? WHERE store_id=? AND
                         rowid IN(SELECT rowid FROM stores WHERE store_id=? LIMIT 1 OFFSET ?)""",
                      (it["qty"],store_id,store_id,it["pid"]))
    c.execute("UPDATE orders SET status='cancelled' WHERE order_id=?", (order_id,))
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
# ───────── update a store + its products ─────────
# ───────── update a store + its products + images ─────────
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
    pnames        = request.form.getlist("pname[]")
    pds           = request.form.getlist("pd[]")
    pqs           = request.form.getlist("pq[]")
    pps           = request.form.getlist("pp[]")
    current_imgs  = request.form.getlist("current_img[]")  # filenames already in DB
    uploaded_imgs = request.files.getlist("pi[]")          # one <input type=file> per card

    # ── optional new store‑level QR ──
    qr_name = None
    qr_file = request.files.get("qr_img")
    if qr_file and qr_file.filename:
        qr_name = secure_filename(qr_file.filename)
        qr_file.save(os.path.join(app.config["UPLOAD_FOLDER"], qr_name))

    with db() as con:
        cur = con.cursor()

        # 1️⃣  update store meta (all rows share same data)
        cur.execute("""
            UPDATE stores
               SET store_name  = ?,
                   store_desc  = ?,
                   email       = ?,
                   owner_phone = ?
                   {qr_sql}
             WHERE store_id    = ?
        """.format(qr_sql=", qr_file = ?" if qr_name else ""),
        (storename, description, email, phone, *( (qr_name,) if qr_name else () ), store_id))

        # 2️⃣  loop over every card
        for idx, rid in enumerate(product_ids):
            # save new product image if uploaded
            new_img_file = uploaded_imgs[idx] if idx < len(uploaded_imgs) else None
            img_name = current_imgs[idx]           # default = keep old
            if new_img_file and new_img_file.filename:
                img_name = secure_filename(new_img_file.filename)
                new_img_file.save(os.path.join(app.config["UPLOAD_FOLDER"], img_name))

            # empty rows (no name + no price) are ignored
            if not pnames[idx].strip() and not pps[idx].strip():
                continue

            if rid:   # -------- existing product --------
                cur.execute("""
                    UPDATE stores
                       SET p_name = ?, p_d = ?, p_q = ?, p_p = ?, p_i = ?
                     WHERE store_id = ? AND rowid = ?
                """, (pnames[idx], pds[idx], pqs[idx], pps[idx], img_name,
                      store_id, rid))
            else:    # -------- brand‑new product --------
                cur.execute("""
                    INSERT INTO stores(
                        store_id, store_name, store_desc,
                        email, owner_phone, owner_pin, qr_file,
                        p_name, p_d, p_p, p_q, p_i
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, (
                    store_id, storename, description,
                    email, phone, "", qr_name or "",      # we don’t change owner_pin here
                    pnames[idx], pds[idx], pps[idx], pqs[idx], img_name
                ))

        con.commit()

    flash("Store updated successfully!", "success")
    return redirect(url_for("owner_orders", store_id=store_id))


# ───────── edit‑store page (prefill the form) ─────────
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




# ───────── owner dashboard: list & manage orders ─────────
 
 
# ───────── owner dashboard: list & manage orders ─────────
# Keep the URL the same but expose it under the endpoint name “owner_orders”.
# ───────── owner dashboard: list & manage orders ─────────
# NOTE:  endpoint is now **owner_orders** so all url_for("owner_orders") links work
# ───────── owner dashboard: list & manage orders ─────────
# ───────── owner dashboard – list / manage orders ─────────
@app.route("/owner/<store_id>/orders", endpoint="owner_orders")
def owner_orders(store_id):
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
        plist = []
        items = json.loads(items_js or "[]")
        for it in items:
            pid, qty = it["pid"], it["qty"]
            name, img = c.execute(
                "SELECT p_name, p_i FROM stores WHERE store_id=? LIMIT 1 OFFSET ?",
                (store_id, pid)
            ).fetchone()
            plist.append({"qty": qty, "name": name, "img": img})

        orders.append({
            "id":         oid,
            "total":      amt,
            "cust_name":  cn    or "—",
            "cust_phone": cp    or "—",
            "cust_mail":  cmail or "—",
            "addr":       addr  or "—",
            "mode":       (mode or "UNKNOWN").upper(),
            "status":     stat,
            "plist":      plist
        })

    return render_template("owner_orders.html",
                           orders=orders, store_id=store_id)

# ────── If owner CANCELS the order ──────
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
    if session.get("owner") != store_id:
        return "Unauthorised", 403

    _finalize(order_id, "🎉 Payment confirmed! Order marked paid.")

    row = db().cursor().execute(
        "SELECT customer_email FROM orders WHERE order_id=?", (order_id,)
    ).fetchone()
    if row and row[0]:
        send_email(row[0],
                   "Order confirmed 🎉",
                   "Your payment was received and your order is now on its way!")

    return redirect(url_for("owner_orders", store_id=store_id))


     
     


# ────── seller cancels any order ──────
@app.route("/owner/<store_id>/cancel/<order_id>", methods=["POST"])
def owner_cancel_order(store_id, order_id):
    if session.get("owner") != store_id:
        return "Unauthorised", 403
    # grab customer email before cancellation
    row = db().cursor().execute(
        "SELECT customer_email FROM orders WHERE order_id=?", (order_id,)
    ).fetchone()
    cancel_order(order_id)
    if row and row[0]:
        send_email(row[0],
                   "Order cancelled 😔",
                   "Unfortunately the seller has cancelled your order. "
                   "Feel free to visit the store again and place a new one.")
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

    

# ─────── optional: call this ONCE to add payment_mode column to DB ───────
def alter_db_add_payment_mode():
    try:
        with db() as con:
            con.execute("ALTER TABLE orders ADD COLUMN payment_mode TEXT")
    except:
        pass
      # ignore if already added


# ───────── run ─────────────────────
if __name__=="__main__":
    app.run(debug=True)
