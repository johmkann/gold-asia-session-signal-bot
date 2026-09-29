# Gold Asia Session Signal Bot

Telegram bot that automatically posts Gold (XAUUSD) trading signals during the **Asia session** using the OP + MLP strategy.

## Strategy Summary

- **Session**: Asia only (05:00 – 14:00 ICT / UTC+7)
- **OP**: Open price at 05:00 AM ICT
- **Direction**: Based on 5-minute candle close above/below OP
- **MLP Filter**: (Previous Day High + Low) / 2  
  - If price is between OP and MLP → Wait for close beyond MLP
- **Take Profit**: Fixed **$16** from OP
- **Stop Loss**: Previous Day High/Low ± $4
- **Max trades**: 1–2 per day
- **Goal**: Trade with institutional direction during Asia session

## Features

- Scans the entire Asia session
- Posts signals + status updates to your Telegram channel
- Simple clean message format (Buy/Sell + TP + SL)
- Designed for 1–2 high-quality trades per day

## Requirements

- Python 3.10+
- Telegram Bot Token
- Telegram Channel (bot must be admin)
- Free or paid gold price data source

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your values
4. Run the bot:
   ```bash
   python bot.py
   ```

## Important Notes

- This bot is for **signal generation only**. It does not execute trades.
- For reliable 5-minute data, a proper market data provider is recommended (broker API, Twelve Data, etc.).
- Always do your own research and risk management.
- Trading involves risk of loss.

## License

MIT
