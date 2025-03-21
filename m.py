import telebot
from telebot import types
import os
import re
import json
from datetime import datetime
import requests
import threading
import time

# =======================
# === Configuration ====
# =======================
BOT_TOKEN = "8125722013:AAENJ0KuQIhFgUcvT7-CGgMgsxjLu5mAEBA"           # Replace with your bot token
ADMIN_ID = 6689922327               # Replace with your Telegram numeric admin ID
wallet_address = "YOUR_DEFAULT_WALLET_ADDRESS"  # Initial wallet address

bot = telebot.TeleBot(BOT_TOKEN, parse_mode="HTML")

# Price configuration using dynamic config file
PRICE_CONFIG = {
    "star_usd": 0.05,
    "premium_usd": {"3": 12, "6": 16, "12": 29}
}

def load_config():
    global PRICE_CONFIG
    try:
        with open('config.json', 'r') as f:
            PRICE_CONFIG = json.load(f)
    except:
        save_config()

def save_config():
    with open('config.json', 'w') as f:
        json.dump(PRICE_CONFIG, f)

load_config()

# Global price dictionaries
premium_prices = {}
star_prices = {}

# Global order counter and orders storage
order_counter = 1
orders_data = {}

# Global set for registered user IDs (for broadcast purposes)
registered_users = set()

# Load registered users from file to preserve persistent data
def load_registered_users_from_file():
    global registered_users
    if os.path.exists("users.txt"):
        with open("users.txt", "r", encoding="utf-8") as f:
            content = f.read()
        user_ids = re.findall(r"User ID: <code>(\d+)</code>", content)
        registered_users = set(map(int, user_ids))

load_registered_users_from_file()

# Temporary state dictionaries:
user_state = {}
admin_state = {}

# ================================
# === File and User Update Functions ===
# ================================
def append_to_file(filename, text):
    with open(filename, "a", encoding="utf-8") as f:
        f.write(text + "\n")

def read_file(filename):
    if os.path.exists(filename):
        with open(filename, "r", encoding="utf-8") as f:
            return f.read()
    return ""

def write_file(filename, content):
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)

def add_user(user_id, username):
    global registered_users
    if user_id in registered_users:
        return
    reg_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    block = (f"Name: <b>{username}</b>\n"
             f"Username: <b>{username}</b>\n"
             f"User ID: <code>{user_id}</code>\n"
             f"⭐️ Premium: No\n"
             f"📆 Registration: {reg_date}\n"
             f"🛒 Orders: 0")
    append_to_file("users.txt", block + "\n")
    registered_users.add(user_id)

def update_user_purchase(user_id):
    content = read_file("users.txt")
    blocks = content.strip().split("\n\n")
    new_blocks = []
    for block in blocks:
        if f"<code>{user_id}</code>" in block:
            lines = block.splitlines()
            try:
                count = int(lines[-1].split(":")[1].strip())
            except Exception:
                count = 0
            count += 1
            lines[-1] = f"🛒 Orders: {count}"
            new_blocks.append("\n".join(lines))
        else:
            new_blocks.append(block)
    write_file("users.txt", "\n\n".join(new_blocks))

# ================================
# === Price Updater (Every 30 Minutes) ===
# ================================
def update_prices():
    global premium_prices, star_prices
    try:
        r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=TONUSDT")
        data = r.json()
        price_ton = float(data["price"])
    except Exception as e:
        print("Error fetching TON price:", e)
        return
    new_premium = {k: (PRICE_CONFIG["premium_usd"][k] / price_ton) * 1.08 for k in PRICE_CONFIG["premium_usd"]}
    premium_prices = {k: f"{new_premium[k]:.4f} TON" for k in new_premium}
    new_star = {}
    for key in ["50", "100", "150", "250", "500", "750", "1000"]:
        count = float(key)
        new_star[key] = (count * PRICE_CONFIG["star_usd"] / price_ton) * 1.08
    star_prices = {k: f"{new_star[k]:.4f} TON" for k in new_star}
    print("Prices updated at", datetime.now(), ":", premium_prices, star_prices)

def price_updater():
    while True:
        update_prices()
        time.sleep(1800)

threading.Thread(target=price_updater, daemon=True).start()

# ================================
# === Navigation Buttons Helper ===
# ================================
def add_nav_buttons(markup, home_cb, back_cb):
    btn_home = types.InlineKeyboardButton("🏠 Home", callback_data=home_cb)
    btn_back = types.InlineKeyboardButton("🔙 Back", callback_data=back_cb)
    markup.row(btn_home, btn_back)

# ================================
# === Main Panels ===
# ================================
def show_admin_panel(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_orders = types.InlineKeyboardButton("🔹 Orders", callback_data="admin_orders")
    btn_send = types.InlineKeyboardButton("🔹 Send Message", callback_data="admin_send")
    btn_wallet = types.InlineKeyboardButton("🔹 Update Wallet", callback_data="admin_wallet")
    btn_price = types.InlineKeyboardButton("🔹 Update Prices", callback_data="admin_price")
    btn_info = types.InlineKeyboardButton("🔹 File Info", callback_data="admin_info")
    btn_report = types.InlineKeyboardButton("🔹 Order Report", callback_data="admin_report_orders")
    btn_users = types.InlineKeyboardButton("🔹 Users", callback_data="admin_users")
    markup.add(btn_orders, btn_send, btn_wallet, btn_price, btn_info, btn_report, btn_users)
    add_nav_buttons(markup, "admin_home", "admin_home")
    text = (
        "<blockquote><b>Admin Panel</b></blockquote>\n"
        "Please choose one of the options below.\n\n"
        "<b>Usage Guide:</b>\n"
        "1️⃣ Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons to return to the main menu.\n"
        "2️⃣ To view orders, click 'Orders' or 'Order Report'.\n"
        "3️⃣ To send a message to a specific user, choose 'Send Message' then 'Send to Specific'."
    )
    bot.send_message(chat_id, text, reply_markup=markup)

def show_user_panel(chat_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    btn_buy = types.InlineKeyboardButton("💫 خرید", callback_data="user_buy")
    btn_support = types.InlineKeyboardButton("💬 پشتیبانی", callback_data="user_support")
    markup.add(btn_buy, btn_support)
    add_nav_buttons(markup, "user_home", "user_home")
    text = (
        "<blockquote><b>منوی کاربر</b></blockquote>\n"
        "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.\n\n"
        "<b>راهنمای استفاده:</b>\n"
        "1️⃣ از دکمه‌های <code>🏠 خانه</code> یا <code>🔙 بازگشت</code> استفاده کنید.\n"
        "2️⃣ برای خرید، گزینه 'خرید' را انتخاب کرده و مراحل را به دقت دنبال کنید.\n"
        "3️⃣ برای پشتیبانی، گزینه 'پشتیبانی' را انتخاب کنید."
    )
    bot.send_message(chat_id, text, reply_markup=markup)

# ===============================
# === /start Command Handler ===
# ===============================
@bot.message_handler(commands=['start'])
def start_handler(message):
    global order_counter
    user_id = message.from_user.id
    username = message.from_user.username if message.from_user.username else "NoUsername"
    add_user(user_id, username)
    registered_users.add(user_id)
    if user_id in user_state:
        user_state.pop(user_id)
    if user_id in admin_state:
        admin_state.pop(user_id)
    if user_id == ADMIN_ID:
        show_admin_panel(message.chat.id)
    else:
        show_user_panel(message.chat.id)

# ===============================
# === Callback Query Handler ===
# ===============================
@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    user_id = call.from_user.id
    data = call.data
    if data == "copy_userid":
        bot.send_message(call.message.chat.id, f"Your User ID: <code>{user_id}</code>", parse_mode="HTML")
        return
    if data in ["admin_home", "user_home"]:
        if user_id == ADMIN_ID:
            show_admin_panel(call.message.chat.id)
        else:
            show_user_panel(call.message.chat.id)
        return
    if data.startswith("go_back_"):
        if user_id == ADMIN_ID:
            show_admin_panel(call.message.chat.id)
        else:
            show_user_panel(call.message.chat.id)
        return
    if str(user_id) == str(ADMIN_ID) and data.startswith("admin_"):
        handle_admin_callbacks(call)
    elif data.startswith("user_") or data.startswith("buy_") or data.startswith("purchase_"):
        handle_user_callbacks(call)
    elif data.startswith("complete_order_"):
        order_id = int(data.split("_")[-1])
        if order_id in orders_data:
            admin_state[ADMIN_ID] = {"action": "complete_order", "order_id": order_id}
            bot.edit_message_text(
                "<blockquote><b>Order Completion Process</b></blockquote>\n\n"
                "Step 1: Please enter the <b>numeric user ID</b> of the order's requestor to confirm completion.\n"
                "For example, if the requestor's ID is <code>6584136799</code>, type that number.\n\n"
                "Usage: Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons.",
                chat_id=call.message.chat.id,
                message_id=call.message.message_id,
                parse_mode="HTML"
            )
        else:
            bot.answer_callback_query(call.id, text="Order not found.")
    elif data == "admin_send_select":
        bot.edit_message_text(
            "Please enter the <b>numeric user ID</b> of the target user.\n\n"
            "Usage: After entering the ID, use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons.",
            chat_id=call.message.chat.id,
            message_id=call.message.message_id,
            parse_mode="HTML"
        )
        admin_state[ADMIN_ID] = {"action": "get_target_id"}

# ===============================
# === Admin Callback Handling (English) ===
# ===============================
def handle_admin_callbacks(call):
    global wallet_address
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    data = call.data
    if data == "admin_orders":
        orders_text = read_file("request.txt")
        if not orders_text.strip():
            orders_text = "No orders recorded."
        text = (
            "<blockquote><b>Orders</b></blockquote>\n"
            "-------------------------\n\n"
            f"{orders_text}\n\n"
            "<b>Usage:</b>\n"
            "1️⃣ To complete an order, click the 'Complete Order' button below that order.\n"
            "2️⃣ Follow the on-screen instructions to confirm order completion.\n"
            "3️⃣ Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons to navigate."
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
    elif data == "admin_send":
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_all = types.InlineKeyboardButton("Send to All", callback_data="admin_send_all")
        btn_select = types.InlineKeyboardButton("Send to Specific", callback_data="admin_send_select")
        markup.add(btn_all, btn_select)
        add_nav_buttons(markup, "admin_home", "admin_home")
        text = (
            "<blockquote><b>Send Message</b></blockquote>\n\n"
            "<b>Usage:</b>\n"
            "1️⃣ To send a message to all users, choose 'Send to All'.\n"
            "2️⃣ To send a message to a specific user, choose 'Send to Specific' then enter the user's numeric ID.\n"
            "3️⃣ Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons to navigate."
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    elif data == "admin_wallet":
        text = (
            "<blockquote><b>Update Wallet</b></blockquote>\n\n"
            "<b>Usage:</b>\n"
            "1️⃣ Please enter the new wallet address.\n"
            "2️⃣ After sending, the updated wallet will be saved and the admin panel will reappear.\n"
            "3️⃣ Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons to navigate."
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
        admin_state[ADMIN_ID] = {"action": "update_wallet"}
    elif data == "admin_price":
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_stars = types.InlineKeyboardButton("Set Stars USD", callback_data="admin_set_star_usd")
        btn_premium = types.InlineKeyboardButton("Set Premium USD", callback_data="admin_set_premium")
        markup.add(btn_stars, btn_premium)
        add_nav_buttons(markup, "admin_home", "admin_home")
        text = (
            "<blockquote><b>Update Prices</b></blockquote>\n\n"
            "<b>Usage:</b>\n"
            "1️⃣ Select the option (Stars or Premium) to update.\n"
            "2️⃣ Send the new price in the specified format.\n"
            "   - For Stars: enter the new USD value per star (e.g., <code>0.05</code>).\n"
            "   - For Premium: enter in the format: <code>duration price</code> (e.g., <code>3 12</code>).\n"
            "3️⃣ Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons to navigate."
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    elif data == "admin_set_star_usd":
        text = (
            "<blockquote><b>Set Stars USD Price</b></blockquote>\n"
            "Please enter new price per star in USD.\n"
            "Example: <code>0.05</code>"
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
        admin_state[ADMIN_ID] = {"action": "update_star_price"}
    elif data == "admin_set_premium":
        text = (
            "<blockquote><b>Set Premium USD Prices</b></blockquote>\n"
            "Send in format: <code>duration price</code>\n"
            "Example for 3 months: <code>3 12</code>"
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
        admin_state[ADMIN_ID] = {"action": "update_premium_price"}
    elif data == "admin_info":
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_messages = types.InlineKeyboardButton("View messages.txt", callback_data="admin_info_messages")
        btn_requests = types.InlineKeyboardButton("View request.txt", callback_data="admin_info_requests")
        btn_users = types.InlineKeyboardButton("View users.txt", callback_data="admin_info_users")
        markup.add(btn_messages, btn_requests, btn_users)
        add_nav_buttons(markup, "admin_home", "admin_home")
        text = (
            "<blockquote><b>File Information</b></blockquote>\n\n"
            "<b>Usage:</b>\n"
            "The entire file will be sent as a .txt document.\n"
            "Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons to navigate."
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    elif data == "admin_info_messages":
        try:
            with open("messages.txt", "rb") as doc:
                bot.send_document(chat_id, doc, caption="Messages Log")
        except Exception as e:
            bot.send_message(chat_id, "Error sending file: " + str(e))
    elif data == "admin_info_requests":
        try:
            with open("request.txt", "rb") as doc:
                bot.send_document(chat_id, doc, caption="Requests Log")
        except Exception as e:
            bot.send_message(chat_id, "Error sending file: " + str(e))
    elif data == "admin_info_users":
        try:
            with open("users.txt", "rb") as doc:
                bot.send_document(chat_id, doc, caption="Users List")
        except Exception as e:
            bot.send_message(chat_id, "Error sending file: " + str(e))
    elif data == "admin_send_all":
        text = (
            "<blockquote><b>Send Message to All</b></blockquote>\n\n"
            "<b>Usage:</b>\n"
            "Enter the message to send to all users and then use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons."
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
        admin_state[ADMIN_ID] = {"action": "broadcast_all"}
    elif data == "admin_users":
        content = read_file("users.txt")
        if not content.strip():
            content = "No users registered."
        else:
            blocks = content.split("\n\n")
            formatted = "\n\n".join(blocks)
            content = formatted
        bot.send_message(chat_id,
            "<blockquote><b>Users List</b></blockquote>\n\n" + content +
            "\n<b>Usage:</b> Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons.",
            parse_mode="HTML"
        )
    elif data == "admin_report_orders":
        if not orders_data:
            text = (
                "<blockquote><b>Order Report</b></blockquote>\n\n"
                "No orders recorded.\n\n"
                "<b>Usage:</b> Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons."
            )
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
        else:
            text = "<blockquote><b>Order Report</b></blockquote>\n\n"
            markup = types.InlineKeyboardMarkup()
            counter = 1
            emoji_map = {1:"1️⃣", 2:"2️⃣", 3:"3️⃣", 4:"4️⃣", 5:"5️⃣"}
            for oid in sorted(orders_data.keys()):
                order = orders_data[oid]
                emoji_num = emoji_map.get(counter, f"{counter}.")
                order_text = (
                    f"{emoji_num} <b>Order {oid}</b>:\n"
                    f"Requestor: {order['requester_link']}\n"
                    f"User ID: <code>{order['user_id']}</code>\n"
                    f"Username: <code>{order['username']}</code>\n"
                    f"Receiver: <code>{order['receiver']}</code>\n"
                    f"Time: <code>{order['time']}</code>\n"
                    f"TX: <code>{order['tx']}</code>\n"
                    f"Detail: <code>{order['detail']}</code>\n"
                    f"Status: <code>{order['status']}</code>\n\n"
                )
                text += order_text
                if order['status'] == "Pending":
                    btn = types.InlineKeyboardButton(f"Complete Order {oid}", callback_data=f"complete_order_{oid}")
                    markup.add(btn)
                counter += 1
            add_nav_buttons(markup, "admin_home", "admin_home")
            bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")

# ===============================
# === User Callback Handling (Persian) ===
def handle_user_callbacks(call):
    global wallet_address
    chat_id = call.message.chat.id
    message_id = call.message.message_id
    data = call.data
    user_id = call.from_user.id
    if data == "user_buy":
        markup = types.InlineKeyboardMarkup(row_width=2)
        btn_stars = types.InlineKeyboardButton("🌟 خرید ستارز", callback_data="buy_stars")
        btn_premium = types.InlineKeyboardButton("💎 خرید پرمیوم", callback_data="buy_premium")
        markup.add(btn_stars, btn_premium)
        add_nav_buttons(markup, "user_home", "user_home")
        text = (
            "<blockquote><b>منوی خرید</b></blockquote>\n\n"
            "لطفاً یکی از گزینه‌های زیر را انتخاب کنید.\n\n"
            "<b>راهنمای استفاده:</b>\n"
            "1️⃣ از دکمه‌های <code>🏠 خانه</code> یا <code>🔙 بازگشت</code> استفاده کنید."
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    elif data == "buy_stars":
        markup = types.InlineKeyboardMarkup(row_width=2)
        for amount, price in star_prices.items():
            btn = types.InlineKeyboardButton(f"{amount} عدد - {price}", callback_data=f"buy_stars_{amount}")
            markup.add(btn)
        add_nav_buttons(markup, "user_buy", "user_home")
        text = (
            "<blockquote><b>خرید ستارز</b></blockquote>\n\n"
            "لطفاً مقدار مورد نظر را انتخاب کنید.\n\n"
            "<b>راهنمای استفاده:</b>\n"
            "1️⃣ از دکمه‌های <code>🏠 خانه</code> یا <code>🔙 بازگشت</code> استفاده کنید."
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    elif data.startswith("buy_stars_"):
        selected_amount = data.split("_")[-1]
        price = star_prices.get(selected_amount, "0 TON")
        text = (
            "<blockquote><b>⚡️ خرید ستارز</b></blockquote>\n\n"
            f"لطفاً مبلغ <code>{price}</code> را به آدرس زیر واریز کنید:\n"
            f"► <code>{wallet_address}</code>\n\n"
            "⮕ در قسمت memo، آیدی شما: <code>{}</code> قرار دهید.\n\n"
            "سپس نام کاربری دریافت کننده (بدون @) را وارد کنید.\n\n"
            "<b>راهنمای استفاده:</b>\n"
            "1️⃣ برای کپی آیدی، روی <code>آیدی</code> کلیک کنید.\n"
            "2️⃣ از دکمه‌های <code>🏠 خانه</code> یا <code>🔙 بازگشت</code> استفاده کنید."
        ).format(user_id)
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
        user_state[user_id] = {"state": "awaiting_receiver", "order": {"type": "stars", "amount": selected_amount, "price": price}}
    elif data == "buy_premium":
        markup = types.InlineKeyboardMarkup(row_width=1)
        btn_3 = types.InlineKeyboardButton("💠 خرید پرمیوم 3 ماهه - " + premium_prices.get("3", "N/A"), callback_data="buy_premium_3")
        btn_6 = types.InlineKeyboardButton("💠 خرید پرمیوم 6 ماهه - " + premium_prices.get("6", "N/A"), callback_data="buy_premium_6")
        btn_12 = types.InlineKeyboardButton("💠 خرید پرمیوم 1 ساله - " + premium_prices.get("12", "N/A"), callback_data="buy_premium_12")
        markup.add(btn_3, btn_6, btn_12)
        add_nav_buttons(markup, "user_buy", "user_home")
        text = (
            "<blockquote><b>خرید پرمیوم</b></blockquote>\n\n"
            "لطفاً مدت مورد نظر را انتخاب کنید.\n\n"
            "<b>راهنمای استفاده:</b>\n"
            "1️⃣ از دکمه‌های <code>🏠 خانه</code> یا <code>🔙 بازگشت</code> استفاده کنید."
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, reply_markup=markup, parse_mode="HTML")
    elif data.startswith("buy_premium_"):
        duration_key = data.split("_")[-1]
        price = premium_prices.get(duration_key, "0 TON")
        if duration_key == "3":
            duration_text = "3 ماهه"
        elif duration_key == "6":
            duration_text = "6 ماهه"
        elif duration_key == "12":
            duration_text = "1 ساله"
        else:
            duration_text = duration_key
        text = (
            f"<blockquote><b>⚡️ خرید پرمیوم {duration_text}</b></blockquote>\n\n"
            f"لطفاً مبلغ <code>{price}</code> را به آدرس زیر واریز کنید:\n"
            f"► <code>{wallet_address}</code>\n\n"
            "⮕ در قسمت memo، آیدی شما: <code>{}</code> قرار دهید.\n\n"
            "سپس نام کاربری دریافت کننده (بدون @) را وارد کنید.\n\n"
            "<b>راهنمای استفاده:</b>\n"
            "1️⃣ برای کپی آیدی، روی <code>آیدی</code> کلیک کنید.\n"
            "2️⃣ از دکمه‌های <code>🏠 خانه</code> یا <code>🔙 بازگشت</code> استفاده کنید."
        ).format(user_id)
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
        user_state[user_id] = {"state": "awaiting_receiver", "order": {"type": "premium", "duration": duration_text, "price": price}}
    elif data == "user_support":
        text = (
            "<blockquote><b>پشتیبانی</b></blockquote>\n\n"
            "لطفاً پیام پشتیبانی خود را وارد کنید.\n\n"
            "<b>راهنمای استفاده:</b>\n"
            "1️⃣ پس از نوشتن پیام، از دکمه‌های <code>🏠 خانه</code> یا <code>🔙 بازگشت</code> استفاده کنید."
        )
        bot.edit_message_text(text, chat_id=chat_id, message_id=message_id, parse_mode="HTML")
        user_state[user_id] = {"state": "awaiting_support"}

# ===============================
# === Order Completion Process (Admin) ===
# ===============================
@bot.message_handler(func=lambda message: True)
def message_handler(message):
    global wallet_address, order_counter
    user_id = message.from_user.id
    chat_id = message.chat.id
    text_in = message.text.strip()
    append_to_file("messages.txt", f"{user_id} | {text_in}")
    if str(user_id) == str(ADMIN_ID) and user_id in admin_state:
        action = admin_state[user_id]["action"]
        if action == "update_wallet":
            wallet_address = text_in
            bot.send_message(chat_id,
                f"<b>Wallet updated</b>\nNew wallet: <code>{wallet_address}</code>\n\nUsage: Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons.",
                parse_mode="HTML"
            )
            admin_state.pop(user_id)
            show_admin_panel(chat_id)
            return
        elif action == "update_star_price":
            try:
                new_price = float(text_in)
                PRICE_CONFIG["star_usd"] = new_price
                save_config()
                update_prices()
                bot.send_message(chat_id,
                    f"<b>Stars USD price updated</b>\nNew star price: <code>{new_price}</code> USD per unit.\n\nUsage: Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons.",
                    parse_mode="HTML"
                )
            except Exception as e:
                bot.send_message(chat_id, f"❌ Error: {e}\nPlease try again.")
            admin_state.pop(user_id)
            show_admin_panel(chat_id)
            return
        elif action == "update_premium_price":
            try:
                duration, price_val = text_in.split()
                PRICE_CONFIG["premium_usd"][duration] = float(price_val)
                save_config()
                update_prices()
                bot.send_message(chat_id,
                    f"<b>Premium USD price updated</b>\nFor {duration} months: <code>{price_val}</code> USD.\n\nUsage: Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons.",
                    parse_mode="HTML"
                )
            except Exception as e:
                bot.send_message(chat_id, f"❌ Error: {e}\nPlease try again.")
            admin_state.pop(user_id)
            show_admin_panel(chat_id)
            return
        elif action == "broadcast_all":
            count = 0
            for uid in registered_users:
                try:
                    bot.send_message(uid, f"<b>Admin Message:</b>\n{text_in}", parse_mode="HTML")
                    count += 1
                except Exception:
                    continue
            bot.send_message(chat_id,
                f"<b>Message sent</b> to {count} users.\n\nUsage: Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons.",
                parse_mode="HTML"
            )
            admin_state.pop(user_id)
            show_admin_panel(chat_id)
            return
        elif action == "get_target_id":
            try:
                target_id = int(text_in)
                if target_id not in registered_users:
                    bot.send_message(chat_id, "❌ User not registered. Please try again.")
                    return
                admin_state[ADMIN_ID] = {"action": "send_select", "target": target_id}
                bot.send_message(chat_id,
                    "Please enter the message to send to the user.\n\nUsage: Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons.",
                    parse_mode="HTML"
                )
            except Exception:
                bot.send_message(chat_id, "❌ Invalid ID. Please try again.")
            return
        elif action == "send_select":
            target = admin_state[user_id]["target"]
            if message.reply_to_message:
                bot.forward_message(target, chat_id, message.reply_to_message.message_id)
            else:
                bot.send_message(target, f"<b>Admin Message:</b>\n{text_in}", parse_mode="HTML")
            bot.send_message(chat_id,
                f"<b>Message sent</b> to user <code>{target}</code>.\n\nUsage: Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons.",
                parse_mode="HTML"
            )
            admin_state.pop(user_id)
            show_admin_panel(chat_id)
            return
        elif action == "complete_order":
            order_id = admin_state[user_id]["order_id"]
            if order_id in orders_data:
                expected_id = orders_data[order_id]['user_id']
                try:
                    entered_id = int(text_in)
                except:
                    bot.send_message(chat_id, "❌ Please enter a valid numeric ID.")
                    return
                if entered_id == expected_id:
                    try:
                        bot.send_message(expected_id,
                            "<b>Your order has been completed.</b>\nPlease contact support for further details.",
                            parse_mode="HTML"
                        )
                    except Exception:
                        pass
                    bot.send_message(chat_id,
                        f"<b>Order {order_id} completed successfully.</b>\n\nUsage: Use the <code>🏠 Home</code> or <code>🔙 Back</code> buttons.",
                        parse_mode="HTML"
                    )
                    del orders_data[order_id]
                    admin_state.pop(user_id)
                    show_admin_panel(chat_id)
                    return
                else:
                    bot.send_message(chat_id, "❌ The entered ID does not match the requestor's ID. Please try again.")
                    return
    if user_id in user_state:
        state = user_state[user_id]["state"]
        if state == "awaiting_receiver":
            user_state[user_id]["order"]["receiver"] = text_in
            bot.send_message(chat_id,
                "<b>✅ دریافت کننده ثبت شد.</b>\nحال TX تراکنش خود را ارسال کنید.\n\nراهنمای استفاده:\n1️⃣ برای کپی آیدی روی <code>آیدی</code> کلیک کنید.\n2️⃣ از دکمه‌های <code>🏠 خانه</code> یا <code>🔙 بازگشت</code> استفاده کنید.",
                parse_mode="HTML"
            )
            user_state[user_id]["state"] = "awaiting_tx"
            return
        elif state == "awaiting_tx":
            tx = text_in
            order = user_state[user_id]["order"]
            order["tx"] = tx
            order_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            username = message.from_user.username if message.from_user.username else "NoUsername"
            if order["type"] == "stars":
                order_detail = f"Purchase Stars ({order['amount']} units)"
            else:
                order_detail = f"Purchase Premium ({order.get('duration','')})"
            current_order_id = order_counter
            full_record = (
                f"Requestor: <a href='tg://user?id={user_id}'>{username}</a>\n"
                f"User ID: <code>{user_id}</code>\n"
                f"Username: <code>{username}</code>\n"
                f"Receiver: <code>{order.get('receiver','')}</code>\n"
                f"Time: <code>{order_date}</code>\n"
                f"TX: <code>{tx}</code>\n"
                f"Detail: <code>{order_detail}</code>\n"
                f"Status: <code>Pending</code>"
            )
            orders_data[order_counter] = {
                "order_id": order_counter,
                "requester_link": f"<a href='tg://user?id={user_id}'>{username}</a>",
                "user_id": user_id,
                "username": username,
                "receiver": order.get("receiver", ""),
                "time": order_date,
                "tx": tx,
                "detail": order_detail,
                "status": "Pending"
            }
            append_to_file("request.txt", full_record + "\n-------------------------------------")
            bot.send_message(chat_id,
                "<b>✅ سفارش شما ثبت شد.</b>\nپس از بررسی نتیجه به شما اطلاع داده می‌شود.\n\nراهنمای استفاده:\n1️⃣ از دکمه‌های <code>🏠 خانه</code> یا <code>🔙 بازگشت</code> استفاده کنید.",
                parse_mode="HTML"
            )
            update_user_purchase(user_id)
            order_counter += 1
            user_state.pop(user_id)
            bot.send_message(ADMIN_ID, "🔔 New order received:\n" + full_record, parse_mode="HTML")
            return
        elif state == "awaiting_support":
            support_msg = f"📩 Support from user <code>{user_id}</code>:\n{text_in}"
            try:
                bot.send_message(ADMIN_ID, support_msg, parse_mode="HTML")
                bot.send_message(chat_id,
                    "<b>✅ پشتیبانی: پیام شما ارسال شد.</b>\n\nراهنمای استفاده:\n1️⃣ از دکمه‌های <code>🏠 خانه</code> یا <code>🔙 بازگشت</code> استفاده کنید.",
                    parse_mode="HTML"
                )
            except Exception:
                bot.send_message(chat_id, "❌ خطا در ارسال پیام پشتیبانی.")
            user_state.pop(user_id)
            return
    bot.send_message(chat_id,
        "<b>⚠️ لطفاً از دکمه‌های منو استفاده نمایید.</b>\n\nراهنمای استفاده:\n1️⃣ از دکمه‌های <code>🏠 خانه</code> یا <code>🔙 بازگشت</code> استفاده کنید.",
        parse_mode="HTML"
    )

@bot.message_handler(content_types=['photo', 'video', 'document', 'audio'])
def handle_media(message):
    if message.from_user.id != ADMIN_ID:
        bot.forward_message(ADMIN_ID, message.chat.id, message.message_id)

bot.infinity_polling()