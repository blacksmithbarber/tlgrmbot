import sys
import logging
import asyncio
import aiohttp
import time
from aiogram import Bot, Dispatcher, types
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ===== CONFIGURATION =====
TOKEN = "8058223183:AAFLgBMV73ywCy44NxVyi-g3kFQovfoJBdw"
NOBITEX_API_TOKEN = "047df3cfc157955ac41ee55fcc68f0b76762f3c2" 
BINANCE_PRICE_URL = "https://api.binance.com/api/v3/ticker/price?symbol={}USDT"
BINANCE_KLINE_URL = "https://api.binance.com/api/v3/klines?symbol={}USDT&interval={}&limit=2"
NOBITEX_PRICE_URL = "https://api.nobitex.ir/v3/orderbook/USDTIRT"
NOBITEX_ORDER_URL = "https://api.nobitex.ir/market/orders/add"


# ===== INITIALIZATION =====
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp = Dispatcher()
logging.basicConfig(level=logging.INFO)

# ===== STATE MANAGEMENT =====
user_states = {}  # Stores user's current context
alert_temp_data = {}  # Temporary storage during alert setup
alerts = {}  # Active alerts: {user_id: [{'symbol': str, 'target_percent': float, 'base_price': float}]}
order_temp_data = {}  # Temporary storage for order creation

# ===== KEYBOARDS =====
main_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="Real Time Price")],
        [KeyboardButton(text="Price Change")],
        [KeyboardButton(text="Alert on Price Change")],
        [KeyboardButton(text="USDT-IRT")]
    ],
    resize_keyboard=True
)

timeframe_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="4 Hrs Change"), KeyboardButton(text="1 D Change")],
        [KeyboardButton(text="1 W Change"), KeyboardButton(text="Back")]
    ],
    resize_keyboard=True
)

# ===== BINANCE API FUNCTIONS =====
async def fetch_real_time_price(symbol: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(BINANCE_PRICE_URL.format(symbol)) as response:
            if response.status == 200:
                data = await response.json()
                return float(data['price'])
            return None

async def fetch_price_change(symbol: str, interval: str):
    async with aiohttp.ClientSession() as session:
        async with session.get(BINANCE_KLINE_URL.format(symbol, interval)) as response:
            if response.status == 200:
                data = await response.json()
                if len(data) >= 2:
                    old_price = float(data[0][4])
                    new_price = float(data[1][4])
                    return ((new_price - old_price) / old_price) * 100
            return None

# ===== NOBITEX API FUNCTIONS =====
async def fetch_real_time_price2():
    async with aiohttp.ClientSession() as session:
        async with session.get(NOBITEX_PRICE_URL) as response:
            if response.status == 200:
                data = await response.json()
                return float(data['lastTradePrice'])
            return None

async def create_order(user_id: int, order_type: str, amount: float, price: float):
    headers = {
        "Authorization": f"Token {NOBITEX_API_TOKEN}",
        "content-type": "application/json"
    }
    data = {
        "type": order_type,
        "srcCurrency": "usdt",
        "dstCurrency": "rls",
        "amount": str(amount),
        "price": str(price),
        "clientOrderId": f"order_{user_id}_{int(time.time())}"
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(NOBITEX_ORDER_URL, headers=headers, json=data) as response:
            if response.status == 200:
                return await response.json()
            return None

# ===== ALERT BACKGROUND TASK =====
async def check_alerts_task():
    while True:
        await asyncio.sleep(60)  # Check every 60 seconds
        for user_id in list(alerts.keys()):
            for alert in list(alerts.get(user_id, [])):
                symbol = alert['symbol']
                target = alert['target_percent']
                base_price = alert['base_price']
                
                current_price = await fetch_real_time_price(symbol)
                if current_price is None:
                    continue
                
                change = ((current_price - base_price) / base_price) * 100
                triggered = (target >= 0 and change >= target) or (target < 0 and change <= target)
                
                if triggered:
                    try:
                        await bot.send_message(
                            user_id,
                            f"🚨 *{symbol}* Alert!\n"
                            f"Current Price: ${current_price:.2f}\n"
                            f"Change from setup: {change:.2f}% (Target: {target}%)"
                        )
                        alerts[user_id].remove(alert)
                        if not alerts[user_id]:
                            del alerts[user_id]
                    except Exception as e:
                        logging.error(f"Alert error for user {user_id}: {e}")

# ===== HANDLERS =====
@dp.message(Command("start"))
async def start_command(message: types.Message):
    await message.answer("Welcome! Choose an option:", reply_markup=main_keyboard)

@dp.message(lambda msg: msg.text == "Real Time Price")
async def handle_real_time_price(message: types.Message):
    await message.answer("Enter cryptocurrency symbol (e.g., BTC, ETH):")
    user_states[message.from_user.id] = "price"

@dp.message(lambda msg: msg.text == "Price Change")
async def handle_price_change_menu(message: types.Message):
    await message.answer("Select timeframe:", reply_markup=timeframe_keyboard)

@dp.message(lambda msg: msg.text == "Alert on Price Change")
async def handle_alert_menu(message: types.Message):
    await message.answer("Enter cryptocurrency symbol (e.g., BTC, ETH):")
    user_states[message.from_user.id] = "alert_symbol"

@dp.message(lambda msg: msg.text == "USDT-IRT")
async def handle_real_time_price2(message: types.Message):
    price = await fetch_real_time_price2()
    if price:
        # Generate buttons for buy/sell orders
        order_keyboard = ReplyKeyboardMarkup(
            keyboard=[
                [KeyboardButton(text="Make Buy Order")],
                [KeyboardButton(text="Make Sell Order")],
                [KeyboardButton(text="Back")]
            ],
            resize_keyboard=True
        )
        await message.answer(f"💰 USDT Price: ريال {price:.2f}", reply_markup=order_keyboard)
        user_states[message.from_user.id] = "usdtirt_order"
        order_temp_data[message.from_user.id] = {"price": price}
    else:
        await message.answer("❌ Failed to fetch USDT price. Please try again.")

@dp.message(lambda msg: msg.text in ["4 Hrs Change", "1 D Change", "1 W Change"])
async def handle_timeframe_selection(message: types.Message):
    timeframe_map = {
        "4 Hrs Change": "4h",
        "1 D Change": "1d",
        "1 W Change": "1w"
    }
    user_states[message.from_user.id] = timeframe_map[message.text]
    await message.answer("Enter cryptocurrency symbol (e.g., BTC, ETH):")

@dp.message(lambda msg: msg.text == "Back")
async def handle_back(message: types.Message):
    await message.answer("Main menu:", reply_markup=main_keyboard)
    user_states.pop(message.from_user.id, None)

@dp.message(lambda msg: msg.text in ["Make Buy Order", "Make Sell Order"])
async def handle_order_creation(message: types.Message):
    user_id = message.from_user.id
    if user_id not in order_temp_data:
        await message.answer("❌ Session expired. Start over.")
        return
    
    price = order_temp_data[user_id]["price"]
    order_type = "buy" if message.text == "Make Buy Order" else "sell"
    
    # Ask for amount
    await message.answer(f"Enter the amount of USDT to {order_type}:")
    user_states[user_id] = f"usdtirt_order_{order_type}"

@dp.message()
async def handle_symbol_input(message: types.Message):
    user_id = message.from_user.id
    text = message.text.strip()
    
    if user_id not in user_states:
        await message.answer("⚠️ Please select an option from the menu first.")
        return
    
    context = user_states[user_id]
    
    # Handle Alert Setup Flow
    if context == "alert_symbol":
        symbol = text.upper()
        if not symbol.isalpha():
            await message.answer("❌ Invalid symbol. Use letters only (e.g., BTC).")
            return
        
        price = await fetch_real_time_price(symbol)
        if not price:
            await message.answer("❌ Invalid symbol or API error. Try again.")
            return
        
        alert_temp_data[user_id] = {"symbol": symbol, "base_price": price}
        user_states[user_id] = "alert_percent"
        await message.answer("Enter target percentage (e.g., +5 for 5% gain, -3 for 3% loss):")
    
    elif context == "alert_percent":
        try:
            percent = float(text.replace('%', '').strip())
        except ValueError:
            await message.answer("❌ Invalid percentage. Enter a number like +5 or -3.")
            return
        
        temp_data = alert_temp_data.get(user_id)
        if not temp_data:
            await message.answer("❌ Session expired. Start over.")
            user_states.pop(user_id, None)
            return
        
        symbol = temp_data["symbol"]
        base_price = temp_data["base_price"]
        alerts.setdefault(user_id, []).append({
            "symbol": symbol,
            "target_percent": percent,
            "base_price": base_price
        })
        
        await message.answer(
            f"✅ Alert set for {symbol}!\n"
            f"Tracking {percent}% change from ${base_price:.2f}."
        )
        del alert_temp_data[user_id]
        user_states.pop(user_id, None)

    # Handle Order Creation Flow
    elif context.startswith("usdtirt_order_"):
        try:
            amount = float(text)
            order_type = context.split("_")[-1]  # "buy" or "sell"
            price = order_temp_data[user_id]["price"]
            
            # Create the order
            order_response = await create_order(user_id, order_type, amount, price)
            if order_response and order_response.get("status") == "ok":
                await message.answer(f"✅ {order_type.capitalize()} order created successfully!")
            else:
                await message.answer("❌ Failed to create order. Please try again.")
        except ValueError:
            await message.answer("❌ Invalid amount. Enter a number.")
        finally:
            user_states.pop(user_id, None)
            order_temp_data.pop(user_id, None)

    # Existing Price and Change Handlers
    else:
        symbol = text.upper()
        if not symbol.isalpha():
            await message.answer("❌ Invalid symbol. Use letters only (e.g., BTC).")
            return
        
        try:
            if context == "price":
                price = await fetch_real_time_price(symbol)
                if price:
                    await message.answer(f"💰 *{symbol}* Price: ${price:.2f}")
                else:
                    await message.answer("❌ Failed to fetch price. Check symbol.")
            
            elif context in ["4h", "1d", "1w"]:
                change = await fetch_price_change(symbol, context)
                if change is not None:
                    timeframe = {"4h": "4 Hours", "1d": "1 Day", "1w": "1 Week"}[context]
                    await message.answer(f"📊 *{symbol}* {timeframe} Change: {change:.2f}%")
                else:
                    await message.answer("❌ Failed to fetch data. Check symbol.")
        
        except Exception as e:
            logging.error(f"Error processing request: {e}")
            await message.answer("❌ An error occurred. Please try again.")

# ===== MAIN =====
async def main():
    asyncio.create_task(check_alerts_task())
    await dp.start_polling(bot)

if __name__ == "__main__":
    if sys.platform.startswith("win"):
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())