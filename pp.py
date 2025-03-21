import asyncio
import aiohttp
import time
import threading
import json
import os
from datetime import datetime
from telebot import TeleBot, types

# =================== Initial Configuration =================== 😎🚀💡🔥🎉
BOT_TOKEN = "7920663137:AAGHf8LcrfEUZgflJlxfmnq7kd6ZRvIugxA"
ADMIN_ID = "6689922327"

# Free API endpoints (all free!)
BINANCE_API_URL = "https://api.binance.com/api/v3/ticker/24hr?symbol={}USDT"
COINGECKO_API_URL = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&ids={}"
COINCAP_API_URL = "https://api.coincap.io/v2/assets"
COINPAPRIKA_API_URL = "https://api.coinpaprika.com/v1/tickers"

DATA_FILE = 'data.txt'
ERRORS_FILE = 'errors.txt'
ADS_FILE = 'ads.txt'  # File to store ad text

bot = TeleBot(BOT_TOKEN)

# =================== Global Cache ===================
CACHE_DURATION = 30  # seconds
price_cache = {}  # { symbol: { "timestamp": ..., "data": {...} } }

# =================== Data Structures =================== 📊🗂️💾🔀📁
data = {
    'users': {},           # {user_id: {username, full_name, join_date}}
    'custom_prices': {},   # {user_id: [coin1, coin2, ...]}
    'blocked_users': set()  # user IDs as strings
}
data["ad"] = "Buy crypto with us! Visit our site."  # default ad text

# last_price_message: keys will be chat keys (user_id for private, chat_id for groups/channels)
# Value: (chat_id, message_id, is_private)
last_price_message = {}

# ------------------- Data Loading & Saving -------------------
def load_data():
    try:
        with open(DATA_FILE, 'r', encoding='utf-8') as f:
            loaded = json.load(f)
            data['users'] = loaded.get('users', {})
            data['custom_prices'] = loaded.get('custom_prices', {})
            data['blocked_users'] = set(loaded.get('blocked_users', []))
    except (FileNotFoundError, json.JSONDecodeError):
        pass

def save_data():
    with open(DATA_FILE, 'w', encoding='utf-8') as f:
        json.dump({
            'users': data['users'],
            'custom_prices': data['custom_prices'],
            'blocked_users': list(data['blocked_users'])
        }, f)

load_data()

def load_ad():
    if os.path.exists(ADS_FILE):
        try:
            with open(ADS_FILE, 'r', encoding='utf-8') as f:
                ad_text = f.read().strip()
                if ad_text:
                    data["ad"] = ad_text
        except Exception as e:
            log_error(f"Error loading ad: {str(e)}")
    else:
        try:
            with open(ADS_FILE, 'w', encoding='utf-8') as f:
                f.write(data["ad"])
        except Exception as e:
            log_error(f"Error creating ads file: {str(e)}")

load_ad()

# =================== Error Logging ===================
def log_error(error):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with open(ERRORS_FILE, 'a', encoding='utf-8') as f:
        f.write(f"[{timestamp}] {error}\n")

# =================== Free API Price Fetching Functions ===================
async def fetch_price_binance(session, symbol):
    try:
        url = BINANCE_API_URL.format(symbol.upper())
        async with session.get(url) as response:
            if response.status == 200:
                resp = await response.json()
                if 'lastPrice' in resp and 'priceChangePercent' in resp:
                    return {
                        'price': float(resp['lastPrice']),
                        'change24': float(resp['priceChangePercent']),
                        'high': float(resp['highPrice']),
                        'low': float(resp['lowPrice']),
                        'source': 'Binance'
                    }
    except Exception as e:
        log_error(f"Binance error for {symbol}: {str(e)}")
    return None

async def fetch_price_coingecko(session, symbol):
    try:
        url = COINGECKO_API_URL.format(symbol.lower())
        async with session.get(url) as response:
            if response.status == 200:
                result = await response.json()
                if result and isinstance(result, list) and len(result) > 0:
                    coin = result[0]
                    return {
                        'price': float(coin['current_price']),
                        'change24': float(coin['price_change_percentage_24h']),
                        'high': float(coin['high_24h']),
                        'low': float(coin['low_24h']),
                        'source': 'CoinGecko'
                    }
    except Exception as e:
        log_error(f"CoinGecko error for {symbol}: {str(e)}")
    return None

async def fetch_price_coincap(session, symbol):
    try:
        async with session.get(COINCAP_API_URL) as response:
            if response.status == 200:
                data_resp = await response.json()
                if "data" in data_resp:
                    for coin in data_resp["data"]:
                        if coin.get("symbol", "").upper() == symbol.upper():
                            return {
                                'price': float(coin.get("priceUsd", 0)),
                                'change24': float(coin.get("changePercent24Hr", 0)),
                                'high': 0,
                                'low': 0,
                                'source': 'CoinCap'
                            }
    except Exception as e:
        log_error(f"CoinCap error for {symbol}: {str(e)}")
    return None

async def fetch_price_coinpaprika(session, symbol):
    try:
        async with session.get(COINPAPRIKA_API_URL) as response:
            if response.status == 200:
                tickers = await response.json()
                for coin in tickers:
                    if coin.get("symbol", "").upper() == symbol.upper():
                        quotes = coin.get("quotes", {}).get("USD", {})
                        return {
                            'price': float(quotes.get("price", 0)),
                            'change24': float(quotes.get("percent_change_24h", 0)),
                            'high': 0,
                            'low': 0,
                            'source': 'CoinPaprika'
                        }
    except Exception as e:
        log_error(f"CoinPaprika error for {symbol}: {str(e)}")
    return None

async def fetch_price(session, symbol):
    symbol_upper = symbol.upper()
    now = time.time()
    # Return cached result if available and fresh
    if symbol_upper in price_cache and (now - price_cache[symbol_upper]["timestamp"] < CACHE_DURATION):
        return symbol_upper, price_cache[symbol_upper]["data"]
    # Otherwise, try the free APIs in order
    for func in [fetch_price_binance, fetch_price_coingecko, fetch_price_coincap, fetch_price_coinpaprika]:
        result = await func(session, symbol)
        if result is not None:
            price_cache[symbol_upper] = {"timestamp": now, "data": result}
            return symbol_upper, result
    log_error(f"Price not found for {symbol}")
    fallback = {'price': 0, 'change24': 0, 'high': 0, 'low': 0, 'source': 'NotFound'}
    price_cache[symbol_upper] = {"timestamp": now, "data": fallback}
    return symbol_upper, fallback

async def get_prices(chat_key, is_private):
    # In private chats, use user-specific custom coins; in groups/channels, use a default list.
    if is_private:
        coins = ['TRUMP'] + list(data['custom_prices'].get(chat_key, []))
    else:
        coins = ['TRUMP']  # Default for groups/channels (customize as needed)
    async with aiohttp.ClientSession() as session:
        tasks = [fetch_price(session, coin) for coin in coins]
        results = await asyncio.gather(*tasks, return_exceptions=True)
    prices = {}
    for res in results:
        if isinstance(res, tuple):
            symbol, info = res
            prices[symbol] = info
    return prices

# =================== Format Price Message with Creative Design ===================
def format_message(prices):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    header = "═════ **“PRICES”** ═════"
    divider = "---------------------"
    message = f"{header}\n"
    for symbol, info in prices.items():
        price = info.get('price', 0)
        change = info.get('change24', 0)
        high = info.get('high', 0)
        low = info.get('low', 0)
        source = info.get('source', '')
        message += f"> **{symbol}** (*{source}*):\n"
        message += f"> **💰 Price:** `$ {price:.4f}`\n"
        message += f"> **📈 24h Change:** `||{change:.2f}%||`\n"
        message += f"> **🔺 High:** `$ {high:.4f}` | **🔻 Low:** `$ {low:.4f}`\n"
        message += f"{divider}\n"
    message += f"**Updated:** _{now}_\n"
    message += f"> **Ads:**\n> {data['ad']}\n{header}"
    return message

# =================== Sending & Updating the Price Message ===================
async def send_price_update(chat_id, key, is_private, message_id=None):
    prices = await get_prices(key, is_private)
    if prices:
        markup = types.InlineKeyboardMarkup()
        btn_refresh = types.InlineKeyboardButton("🔄 Refresh", callback_data="refresh")
        btn_support = types.InlineKeyboardButton("✉️ Support", callback_data="support")
        markup.row(btn_refresh, btn_support)
        if is_private:
            btn_add = types.InlineKeyboardButton("➕ Add Coin", callback_data="inline_addcoin")
            btn_remove = types.InlineKeyboardButton("➖ Remove Coin", callback_data="inline_removecoin")
            markup.row(btn_add, btn_remove)
            if key == ADMIN_ID:
                btn_admin = types.InlineKeyboardButton("🛠️ Admin Panel", callback_data="admin_panel")
                markup.add(btn_admin)
        text = format_message(prices)
        try:
            if message_id:
                bot.edit_message_text(text, chat_id, message_id, parse_mode='Markdown', reply_markup=markup)
            else:
                msg = bot.send_message(chat_id, text, parse_mode='Markdown', reply_markup=markup)
                last_price_message[key] = (chat_id, msg.message_id, is_private)
        except Exception as e:
            log_error(f"Error updating price message for {key}: {str(e)}")

# =================== Background Auto-Update Every 30 Seconds ===================
def background_update():
    while True:
        time.sleep(30)
        for key, (chat_id, msg_id, is_private) in list(last_price_message.items()):
            if key in data['blocked_users']:
                continue
            try:
                asyncio.run(send_price_update(chat_id, key, is_private, msg_id))
            except Exception as e:
                log_error(f"Background update error for {key}: {str(e)}")

update_thread = threading.Thread(target=background_update, daemon=True)
update_thread.start()

# =================== Inline Menu Callbacks ===================
@bot.message_handler(commands=['start'])
def start(message):
    if message.chat.type == "private":
        key = str(message.from_user.id)
        is_private = True
        if key not in data['users']:
            data['users'][key] = {
                'username': message.from_user.username,
                'full_name': f"{message.from_user.first_name} {message.from_user.last_name or ''}",
                'join_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            save_data()
    else:
        key = str(message.chat.id)
        is_private = False
    asyncio.run(send_price_update(message.chat.id, key, is_private))

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    if call.message.chat.type == "private":
        key = str(call.from_user.id)
        is_private = True
    else:
        key = str(call.message.chat.id)
        is_private = False

    if call.data == "refresh":
        asyncio.run(send_price_update(call.message.chat.id, key, is_private, call.message.message_id))
        bot.answer_callback_query(call.id, "🔄 Prices refreshed!")
    elif call.data == "inline_addcoin" and is_private:
        msg = bot.send_message(call.message.chat.id, "**Enter the coin symbol to add:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_add_coin, key)
        bot.answer_callback_query(call.id)
    elif call.data == "inline_removecoin" and is_private:
        msg = bot.send_message(call.message.chat.id, "**Enter the coin symbol to remove:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_remove_coin, key)
        bot.answer_callback_query(call.id)
    elif call.data == "support":
        msg = bot.send_message(call.message.chat.id, "**Type your support message:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_support, key)
        bot.answer_callback_query(call.id)
    elif call.data == "admin_panel":
        if key == ADMIN_ID:
            admin_markup = types.InlineKeyboardMarkup()
            btn_users = types.InlineKeyboardButton("👥 Users List", callback_data="admin_users")
            btn_errors = types.InlineKeyboardButton("❗ Errors Log", callback_data="admin_errors")
            btn_block = types.InlineKeyboardButton("🚫 Block User", callback_data="admin_block")
            btn_ads = types.InlineKeyboardButton("📝 Manage Ads", callback_data="admin_ads")
            btn_back = types.InlineKeyboardButton("↩️ Back", callback_data="back")
            admin_markup.row(btn_users, btn_errors)
            admin_markup.row(btn_block, btn_ads)
            admin_markup.add(btn_back)
            bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=admin_markup)
            bot.answer_callback_query(call.id)
        else:
            bot.answer_callback_query(call.id, "⛔️ Admin only!")
    elif call.data == "admin_users" and key == ADMIN_ID:
        try:
            filename = f"users_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
            with open(filename, 'w', encoding='utf-8') as f:
                headers = ['Name', 'Username', 'User ID', 'Join Date']
                f.write("\t".join(headers) + "\n")
                for uid, info in data['users'].items():
                    line = f"{info.get('full_name','')}\t{info.get('username','')}\t{uid}\t{info.get('join_date','')}\n"
                    f.write(line)
            with open(filename, 'rb') as f:
                bot.send_document(call.message.chat.id, f, caption="**👥 Users List**", parse_mode='Markdown')
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Error: {str(e)}", parse_mode='Markdown')
        bot.answer_callback_query(call.id, "✅ Users list sent!")
    elif call.data == "admin_errors" and key == ADMIN_ID:
        try:
            with open(ERRORS_FILE, 'rb') as f:
                bot.send_document(call.message.chat.id, f, caption="**❗ Errors Log**", parse_mode='Markdown')
        except Exception as e:
            bot.send_message(call.message.chat.id, f"❌ Error: {str(e)}", parse_mode='Markdown')
        bot.answer_callback_query(call.id, "✅ Errors log sent!")
    elif call.data == "admin_block" and key == ADMIN_ID:
        msg = bot.send_message(call.message.chat.id, "**Enter the User ID to block:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_block_user)
        bot.answer_callback_query(call.id)
    elif call.data == "admin_ads" and key == ADMIN_ID:
        msg = bot.send_message(call.message.chat.id, "**Enter the new ad text:**", parse_mode='Markdown')
        bot.register_next_step_handler(msg, process_update_ads)
        bot.answer_callback_query(call.id)
    elif call.data == "back":
        asyncio.run(send_price_update(call.message.chat.id, key, is_private, call.message.message_id))
        bot.answer_callback_query(call.id, "↩️ Back to main menu!")

# =================== Next-Step Handlers ===================
def process_add_coin(message, key):
    try:
        coin = message.text.strip().upper()
        if key not in data['custom_prices']:
            data['custom_prices'][key] = []
        if coin not in data['custom_prices'][key]:
            data['custom_prices'][key].append(coin)
            save_data()
            bot.reply_to(message, f"✅ **{coin}** added!", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"ℹ️ **{coin}** is already in your list.", parse_mode='Markdown')
        asyncio.run(send_price_update(message.chat.id, key, True, last_price_message[key][1]))
    except Exception as e:
        log_error(f"Add coin error: {str(e)}")
        bot.reply_to(message, "❌ **Error adding coin.**", parse_mode='Markdown')

def process_remove_coin(message, key):
    try:
        coin = message.text.strip().upper()
        if coin in data['custom_prices'].get(key, []):
            data['custom_prices'][key].remove(coin)
            save_data()
            bot.reply_to(message, f"❌ **{coin}** removed!", parse_mode='Markdown')
        else:
            bot.reply_to(message, f"ℹ️ **{coin}** is not in your list.", parse_mode='Markdown')
        asyncio.run(send_price_update(message.chat.id, key, True, last_price_message[key][1]))
    except Exception as e:
        log_error(f"Remove coin error: {str(e)}")
        bot.reply_to(message, "❌ **Error removing coin.**", parse_mode='Markdown')

def process_support(message, key):
    try:
        support_msg = message.text.strip()
        support_text = f"> **Support Message**\n> From: **{message.from_user.first_name}** (@{message.from_user.username}) [ID: {key}]\n\n||{support_msg}||"
        bot.send_message(ADMIN_ID, support_text, parse_mode='Markdown')
        bot.reply_to(message, "✅ **Your support message has been sent!**", parse_mode='Markdown')
    except Exception as e:
        log_error(f"Support error: {str(e)}")
        bot.reply_to(message, "❌ **Error sending support message.**", parse_mode='Markdown')

def process_block_user(message):
    try:
        uid = message.text.strip()
        data['blocked_users'].add(uid)
        save_data()
        bot.reply_to(message, f"🚫 **User {uid} blocked!**", parse_mode='Markdown')
    except Exception as e:
        log_error(f"Block user error: {str(e)}")
        bot.reply_to(message, "❌ **Error blocking user.**", parse_mode='Markdown')

def process_update_ads(message):
    try:
        new_ad = message.text.strip()
        data["ad"] = new_ad
        with open(ADS_FILE, 'w', encoding='utf-8') as f:
            f.write(new_ad)
        bot.reply_to(message, "✅ **Ad text updated!**", parse_mode='Markdown')
    except Exception as e:
        log_error(f"Update ads error: {str(e)}")
        bot.reply_to(message, "❌ **Error updating ad text.**", parse_mode='Markdown')

# =================== Start the Bot ===================
if __name__ == '__main__':
    bot.polling(none_stop=True)
