# 🛒 TinyCart – Simple Online Store for Small Sellers

TinyCart is a mini e-commerce platform for small, local sellers who do not sell on platforms like Amazon or Flipkart. It's perfect for handmade or low-quantity products sold via WhatsApp or Instagram.

This app allows sellers to:
- Create their own storefront
- Accept orders online (COD or UPI QR)
- Manage products and stock
- Cancel/refund orders
- View customer orders
- Get notifications via email

---

## ✨ Features

- 🔐 Secure owner dashboard (PIN protected)
- 🛍️ Public customer view for each store
- 📦 Admin approval for each store before it goes live
- 💸 Online or COD payments
- ⌛ Cancel window for customers (default 5 min)
- 📧 Email notifications for:
  - Orders
  - Refunds
  - Admin/store actions

---

## 🗂 Project Structure

```
TinyCart/
├── main.py               # Main Flask app
├── templates/            # All HTML templates (Jinja2)
├── static/images/        # Product & QR images
├── render.yaml           # Render deployment config
├── requirements.txt      # Python dependencies
├── tinycart.db           # SQLite database (auto-created)
├── .env                  # Your secret credentials (DO NOT COMMIT)
```

---

## 🧑‍💻 Built With

- Python (Flask)
- SQLite
- HTML, CSS (Jinja2 templates)
- Gmail SMTP
- Render.com for hosting

---

## 🧪 How to Run Locally in VS Code

1. **Clone the Repository**
   ```bash
   git clone https://github.com/vidhijain95/TinyCart.git
   cd TinyCart
   ```

2. **(Optional) Create a Virtual Environment**
   ```bash
   python -m venv venv
   source venv/bin/activate        # On Mac/Linux
   venv\Scripts\activate           # On Windows
   ```

3. **Install the Required Packages**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the App**
   ```bash
   python main.py
   ```

5. **Access the App**
   Open your browser and go to:
   ```
   http://127.0.0.1:5000
   ```

✅ The database (`tinycart.db`) will be auto-created and all necessary tables initialized automatically.

---

## 🔐 License & Deployment Policy

This project is the original work of **VIDHI**.

You are **NOT permitted** to:
- Remove author credits or license checks from the code
- Redeploy or rebrand the project as your own
- Use it for commercial purposes without written permission

This software includes a deployment protection mechanism. Unauthorized deployments will result in a **403 Forbidden** error with a warning message.

---

### ❤️ Respect the Creator

If you find this project useful or wish to build on it, please:
- Keep credits intact
- Star the repository ⭐
- Link back to the original:  
  [https://github.com/vidhijain95/TinyCart](https://github.com/vidhijain95/TinyCart)

Made with 💖 by **VIDHI**
