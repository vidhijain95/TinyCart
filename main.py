from flask import Flask, render_template, request, url_for
import sqlite3
import uuid

app = Flask(__name__)

@app.route("/")
def home():
    return render_template("homee.html")

@app.route("/create-store", methods=['GET', 'POST'])
def choose_product_count():
    if request.method == "POST":
        count = int(request.form['count'])
        return render_template('add_product.html', count=count)
    return render_template("count.html")

@app.route('/submit-store', methods=['POST'])
def sumbit_store():
    store_id = str(uuid.uuid4())[:8]
    store_name = request.form['storename']
    email = request.form['email']
    store_description = request.form['description']
    p_name = request.form.getlist('pname[]')
    p_d = request.form.getlist('pd[]')
    p_p = request.form.getlist('pp[]')
    p_q = request.form.getlist('pq[]')
    p_i = request.form.getlist('pi[]')
    conn = sqlite3.connect('tinycart.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS stores(
        store_id TEXT,
        store_name TEXT,
        store_description TEXT,
        email TEXT,
        p_name TEXT,
        p_d TEXT,
        p_p REAL,
        p_q INTEGER,
        p_i TEXT
    )''')
    for i in range(len(p_name)):
        c.execute('''INSERT INTO stores VALUES(?,?,?,?,?,?,?,?,?)''',
        (store_id, store_name, store_description, email, p_name[i], p_d[i], p_p[i], p_q[i], p_i[i]))
    conn.commit()
    conn.close()
    # Build the full URL for the store
    full_url = request.host_url.rstrip('/') + url_for('view_store', store_id=store_id)
    return render_template("store_created.html", full_url=full_url)

@app.route('/store/<store_id>')
def view_store(store_id):
    conn = sqlite3.connect('tinycart.db')
    c = conn.cursor()
    c.execute("SELECT * FROM stores WHERE store_id=?", (store_id,))
    products = c.fetchall()
    conn.close()
    if not products:
        return "STORE NOT FOUND PLEASE CREATE ONE"
    store_name = products[0][1]
    store_description = products[0][2]
    owner_email = products[0][3]
    return render_template("store.html",
                          store_name=store_name,
                          store_description=store_description,
                          owner_email=owner_email,
                          products=products)

if __name__ == '__main__':
    app.run(debug=True)
