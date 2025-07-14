# 🛒 TinyCart – Simple Online Store for Small Sellers

TinyCart is a mini e-commerce platform for small, local sellers who do not sell on platforms like Amazon or Flipkart. It's perfect for handmade or low-quantity products sold via WhatsApp or Instagram.

This app allows sellers to:
- Create their own storefront
- Accept orders online (COD or UPI QR)
- Manage products and stock
- Cancel/refund orders
- View customer orders
- Get notifications via email

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
## 🧑‍💻 Built With

- Python (Flask)
- SQLite
- HTML, CSS (Jinja2 templates)
- Gmail SMTP
- Render.com for hosting

## 💡 License

This project is built for learning and demo use. You may modify and deploy it for real-world use at your own risk.
