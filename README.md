# Telegram Stock Screener Bot — Setup Guide

Ye bot NSE (India) ka daily bhavcopy data check karta hai aur top gainers
nikalta hai jinka **delivery % < 25** hai (default threshold; change kar sakte ho).

---

## Step 1: Telegram Bot Banao
1. Telegram open karo, search karo **@BotFather**
2. `/newbot` bhejo, naam aur username do (username `_bot` se end hona chahiye)
3. BotFather tumhe ek **token** dega, kuch is type ka:
   `123456789:ABCdefGhIjkLmNoPQRstuVWXyz`
4. Ye token copy kar lo — isi se bot chalega.

## Step 2: Apna Chat ID nikalo (sirf daily auto-message ke liye, optional)
1. Apne naye bot ko Telegram pe khol kar `/start` bhejo
2. Browser me ye URL kholo (apna token daal kar):
   `https://api.telegram.org/bot<TOKEN>/getUpdates`
3. Response me `"chat":{"id": 123456789` jaisa number milega — wahi tumhara CHAT_ID hai.

## Step 3: Files install karo
```bash
cd telegram_stock_bot
pip install -r requirements.txt
```

## Step 4: Token set karo
Terminal me (Linux/Mac):
```bash
export BOT_TOKEN="yaha_apna_token_daalo"
export CHAT_ID="yaha_apna_chat_id_daalo"     # optional — daily auto-send ke liye
```
Windows (PowerShell):
```powershell
$env:BOT_TOKEN="yaha_apna_token_daalo"
$env:CHAT_ID="yaha_apna_chat_id_daalo"
```

Agar threshold ya count badalna ho (default: delivery < 25%, top 20):
```bash
export DELIVERY_THRESHOLD="25"
export TOP_N="20"
```

## Step 5: Bot chalao
```bash
python bot.py
```
Terminal me "Bot start ho gaya, polling shuru..." dikhega — matlab bot live hai.

## Step 6: Telegram pe use karo
- Bot ko `/start` bhejo
- `/top20` bhejo → fresh list aa jaayegi

Agar `CHAT_ID` set kiya hai, to bot **har trading day shaam 7:00 PM IST** par
khud-ba-khud list bhej dega (NSE ka bhavcopy file usually 6:30–7 PM tak
publish ho jaata hai).

---

## Important Notes
- **Weekends/holidays**: NSE par data nahi hota, bot automatically pichle
  trading day ka data le lega.
- **NSE site change ho sakti hai**: Ye unofficial archive URL use karta hai
  (`archives.nseindia.com`). Kabhi-kabhi NSE apna structure change kar deta
  hai — tab fetch fail hoga, tab URL/headers update karne padenge.
- **24x7 chalane ke liye**: Apne laptop ko hamesha on rakhna padega, ya
  isko kisi free/paid server (Railway, Render, AWS EC2, VPS, etc.) pe deploy
  karo taaki ye continuously chalta rahe.
- Ye sirf ek **screening/data tool** hai — koi buy/sell recommendation nahi
  deta. Trading decision khud research kar ke lena.

## File Structure
```
telegram_stock_bot/
├── bot.py              # main bot code
├── requirements.txt    # dependencies
└── README.md           # ye file
```
