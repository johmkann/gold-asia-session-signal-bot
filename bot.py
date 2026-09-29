#!/usr/bin/env python3
"""
Gold Asia Session Signal Bot
Strategy: OP + MLP (Asia session only)
- OP = Open at 05:00 ICT
- Direction from 5-min candle close vs OP
- MLP filter
- Fixed TP $16 | SL = Prev Day High/Low ± $4
- Max 1-2 signals per day
"""

import os
import time
import logging
from datetime import datetime, timedelta, time as dtime
from zoneinfo import ZoneInfo

import yfinance as yf
import pandas as pd
from dotenv import load_dotenv
from telegram import Bot
from telegram.error import TelegramError
from apscheduler.schedulers.blocking import BlockingScheduler

load_dotenv()

# ====================== CONFIG ======================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHANNEL_ID = os.getenv("TELEGRAM_CHANNEL_ID")

ICT = ZoneInfo("Asia/Phnom_Penh")  # Cambodia time UTC+7

ASIA_START = dtime(5, 0)   # 05:00 ICT
ASIA_END   = dtime(14, 0)  # 14:00 ICT

TP_DISTANCE = 16.0
SL_BUFFER   = 4.0
MAX_SIGNALS_PER_DAY = 2

# ====================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger(__name__)

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# State
op_price = None
mlp_price = None
prev_day_high = None
prev_day_low = None
signals_today = 0
last_signal_date = None
last_status = None  # to avoid spamming same status


def is_asia_session(now: datetime) -> bool:
    t = now.time()
    return ASIA_START <= t < ASIA_END


def get_previous_day_ohlc():
    """Get previous trading day High / Low for MLP and SL"""
    ticker = yf.Ticker("GC=F")  # Gold futures as proxy
    df = ticker.history(period="5d", interval="1d")
    if len(df) < 2:
        raise ValueError("Not enough daily data")
    prev = df.iloc[-2]
    return float(prev["High"]), float(prev["Low"])


def get_current_price():
    """Get latest gold price (approximate with yfinance)"""
    ticker = yf.Ticker("GC=F")
    data = ticker.history(period="1d", interval="1m")
    if data.empty:
        data = ticker.history(period="1d", interval="5m")
    if data.empty:
        raise ValueError("Cannot fetch current price")
    return float(data["Close"].iloc[-1])


def get_recent_5m_close():
    """Get the last closed 5-minute candle close"""
    ticker = yf.Ticker("GC=F")
    df = ticker.history(period="1d", interval="5m")
    if len(df) < 2:
        raise ValueError("Not enough 5m data")
    # Use the previous completed candle
    return float(df["Close"].iloc[-2])


def calculate_levels(direction: str, op: float, prev_high: float, prev_low: float):
    if direction == "BUY":
        tp = round(op + TP_DISTANCE, 2)
        sl = round(prev_low - SL_BUFFER, 2)
    else:
        tp = round(op - TP_DISTANCE, 2)
        sl = round(prev_high + SL_BUFFER, 2)
    return tp, sl


def format_signal(direction: str, op: float, tp: float, sl: float, strength: str = ""):
    emoji = "🟢" if direction == "BUY" else "🔴"
    strength_text = f" ({strength})" if strength else ""

    msg = (
        f"{emoji} <b>GOLD ASIA SESSION SIGNAL</b>\n\n"
        f"<b>Direction:</b> {direction}{strength_text}\n"
        f"<b>OP:</b> {op:.2f}\n\n"
        f"<b>TP:</b> {tp:.2f}  (+${TP_DISTANCE:.0f})\n"
        f"<b>SL:</b> {sl:.2f}\n\n"
        f"Time: {datetime.now(ICT).strftime('%Y-%m-%d %H:%M ICT')}\n"
        f"#XAUUSD #Gold #AsiaSession"
    )
    return msg


def format_status(text: str):
    return f"⏳ <b>Status Update</b>\n\n{text}\n\nTime: {datetime.now(ICT).strftime('%H:%M ICT')}"


async def send_message(text: str):
    try:
        await bot.send_message(
            chat_id=TELEGRAM_CHANNEL_ID,
            text=text,
            parse_mode="HTML",
            disable_web_page_preview=True,
        )
        logger.info("Message sent to channel")
    except TelegramError as e:
        logger.error(f"Telegram error: {e}")


def reset_daily_state(now: datetime):
    global signals_today, last_signal_date, op_price, mlp_price, prev_day_high, prev_day_low, last_status
    today = now.date()
    if last_signal_date != today:
        signals_today = 0
        last_signal_date = today
        op_price = None
        mlp_price = None
        prev_day_high = None
        prev_day_low = None
        last_status = None
        logger.info("Daily state reset")


def check_and_signal():
    global op_price, mlp_price, prev_day_high, prev_day_low, signals_today, last_status

    now = datetime.now(ICT)
    reset_daily_state(now)

    if not is_asia_session(now):
        return

    if signals_today >= MAX_SIGNALS_PER_DAY:
        return

    try:
        # Record OP once at/after 05:00
        if op_price is None and now.time() >= ASIA_START:
            # Use current price as OP approximation when bot starts after 05:00
            # Ideally the bot should be running before 05:00 to capture exact open
            op_price = get_current_price()
            prev_day_high, prev_day_low = get_previous_day_ohlc()
            mlp_price = round((prev_day_high + prev_day_low) / 2, 2)
            logger.info(f"OP set to {op_price:.2f} | MLP = {mlp_price:.2f}")

        if op_price is None:
            return

        current = get_current_price()
        five_min_close = get_recent_5m_close()

        # Determine direction from 5-min close
        if five_min_close > op_price:
            direction = "BUY"
        elif five_min_close < op_price:
            direction = "SELL"
        else:
            return  # exactly at OP – no signal

        # MLP filter
        between = False
        if direction == "BUY":
            if mlp_price > op_price and op_price < current < mlp_price:
                between = True
        else:  # SELL
            if mlp_price < op_price and mlp_price < current < op_price:
                between = True

        if between:
            status = (
                f"Price is between OP ({op_price:.2f}) and MLP ({mlp_price:.2f}).\n"
                f"Waiting for 5-min close beyond MLP for stronger confirmation."
            )
            if status != last_status:
                import asyncio
                asyncio.run(send_message(format_status(status)))
                last_status = status
            return

        # Strong confirmation
        strength = ""
        if direction == "BUY" and current > max(op_price, mlp_price):
            strength = "Strong"
        elif direction == "SELL" and current < min(op_price, mlp_price):
            strength = "Strong"

        tp, sl = calculate_levels(direction, op_price, prev_day_high, prev_day_low)

        msg = format_signal(direction, op_price, tp, sl, strength)

        import asyncio
        asyncio.run(send_message(msg))

        signals_today += 1
        last_status = None
        logger.info(f"Signal sent: {direction} | Signals today: {signals_today}")

    except Exception as e:
        logger.error(f"Error in check_and_signal: {e}")


def main():
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
        logger.error("Please set TELEGRAM_BOT_TOKEN and TELEGRAM_CHANNEL_ID in .env")
        return

    logger.info("Gold Asia Session Signal Bot started")
    logger.info(f"Scanning {ASIA_START} – {ASIA_END} ICT")

    scheduler = BlockingScheduler(timezone=str(ICT))

    # Check every 5 minutes during Asia session
    scheduler.add_job(
        check_and_signal,
        trigger="cron",
        day_of_week="mon-fri",
        hour="5-13",
        minute="*/5",
        id="asia_scan",
    )

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped")


if __name__ == "__main__":
    main()
