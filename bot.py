import os
import json
import logging
import threading
from flask import Flask, request, jsonify
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from dotenv import load_dotenv

# Muat konfigurasi dari file .env
load_dotenv()

# Konfigurasi dasar
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_USER_ID = int(os.getenv("TELEGRAM_USER_ID", "611044696"))
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "5000"))

# Global flags dan data
auto_alert_active = False
monitored_addresses = set()  # Menyimpan wallet address yang dimonitor

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO
)
logger = logging.getLogger(__name__)

# Inisialisasi bot Telegram
updater = Updater(token=TELEGRAM_BOT_TOKEN, use_context=True)
dispatcher = updater.dispatcher
bot = updater.bot

# ---------------------------
# Handler Command Telegram
# ---------------------------
def start(update: Update, context: CallbackContext):
    # Hanya izinkan user tertentu
    if update.effective_user.id != TELEGRAM_USER_ID:
        update.message.reply_text("Unauthorized")
        return
    text = (
        "Selamat datang di Bot Transfer Alert.\n\n"
        "Command yang tersedia:\n"
        "/autoalert - Aktifkan notifikasi transfer secara real-time\n"
        "/stopalert - Hentikan notifikasi\n"
        "/addaddress <wallet_address> - Tambah wallet address\n"
        "/removeaddress <wallet_address> - Hapus wallet address"
    )
    update.message.reply_text(text)

def autoalert(update: Update, context: CallbackContext):
    global auto_alert_active
    if update.effective_user.id != TELEGRAM_USER_ID:
        update.message.reply_text("Unauthorized")
        return
    if auto_alert_active:
        update.message.reply_text("Error: Auto alert sudah aktif.")
        return
    if not monitored_addresses:
        update.message.reply_text("Error: Belum ada wallet address. Tambahkan menggunakan /addaddress")
        return
    auto_alert_active = True
    update.message.reply_text("Auto alert diaktifkan. Memantau transfer secara real-time.")
    logger.info("Auto alert diaktifkan.")

def stopalert(update: Update, context: CallbackContext):
    global auto_alert_active
    if update.effective_user.id != TELEGRAM_USER_ID:
        update.message.reply_text("Unauthorized")
        return
    if not auto_alert_active:
        update.message.reply_text("Auto alert belum aktif.")
        return
    auto_alert_active = False
    update.message.reply_text("Auto alert dihentikan.")
    logger.info("Auto alert dihentikan.")

def addaddress(update: Update, context: CallbackContext):
    if update.effective_user.id != TELEGRAM_USER_ID:
        update.message.reply_text("Unauthorized")
        return
    if len(context.args) != 1:
        update.message.reply_text("Usage: /addaddress <wallet_address>")
        return
    address = context.args[0].strip()
    if address in monitored_addresses:
        update.message.reply_text("Address sudah ditambahkan.")
        return
    monitored_addresses.add(address)
    update.message.reply_text(f"Address {address} berhasil ditambahkan.")
    logger.info(f"Address ditambahkan: {address}")

def removeaddress(update: Update, context: CallbackContext):
    if update.effective_user.id != TELEGRAM_USER_ID:
        update.message.reply_text("Unauthorized")
        return
    if len(context.args) != 1:
        update.message.reply_text("Usage: /removeaddress <wallet_address>")
        return
    address = context.args[0].strip()
    if address not in monitored_addresses:
        update.message.reply_text("Address tidak ditemukan.")
        return
    monitored_addresses.remove(address)
    update.message.reply_text(f"Address {address} berhasil dihapus.")
    logger.info(f"Address dihapus: {address}")

# Daftarkan command handler ke dispatcher
dispatcher.add_handler(CommandHandler("start", start))
dispatcher.add_handler(CommandHandler("autoalert", autoalert))
dispatcher.add_handler(CommandHandler("stopalert", stopalert))
dispatcher.add_handler(CommandHandler("addaddress", addaddress, pass_args=True))
dispatcher.add_handler(CommandHandler("removeaddress", removeaddress, pass_args=True))

# ---------------------------
# Endpoint Webhook (Flask)
# ---------------------------
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def alchemy_webhook():
    """
    Endpoint ini menerima notifikasi webhook dari Alchemy Notify API.
    Pastikan URL endpoint ini didaftarkan pada dashboard Alchemy.
    """
    global auto_alert_active
    try:
        data = request.get_json()
        logger.info("Menerima webhook: %s", data)
        
        # Jika auto alert belum aktif, abaikan notifikasi
        if not auto_alert_active:
            logger.info("Auto alert tidak aktif. Webhook diabaikan.")
            return jsonify({"status": "ignored", "message": "Auto alert tidak aktif."})
        
        # Parsing data notifikasi (sesuaikan dengan payload dari Alchemy)
        event = data.get("event", "unknown")
        tx_hash = data.get("txHash", "N/A")
        # Asumsikan payload memiliki key "address" untuk wallet address
        address = data.get("address", "").lower()
        
        # Cek apakah address yang terdeteksi termasuk dalam monitored_addresses
        if address not in {addr.lower() for addr in monitored_addresses}:
            logger.info("Address %s tidak termasuk dalam daftar monitor.", address)
            return jsonify({"status": "ignored", "message": "Address tidak dipantau."})
        
        # Format pesan notifikasi
        message = (
            f"*Transfer Alert!*\n"
            f"Event   : {event}\n"
            f"Address : {address}\n"
            f"TxHash  : {tx_hash}"
        )
        if (value := data.get("value")):
            message += f"\nValue   : {value}"
        
        # Kirim pesan notifikasi ke Telegram
        bot.send_message(chat_id=TELEGRAM_USER_ID, text=message, parse_mode="Markdown")
        logger.info("Notifikasi transfer dikirim ke Telegram.")
        return jsonify({"status": "success"})
    except Exception as e:
        logger.exception("Terjadi error saat memproses webhook:")
        return jsonify({"status": "error", "message": str(e)}), 500

def run_flask():
    app.run(host=HOST, port=PORT)

def main():
    # Jalankan server Flask di thread terpisah
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    # Mulai polling bot Telegram
    updater.start_polling()
    logger.info("Bot Telegram berjalan.")
    updater.idle()

if __name__ == '__main__':
    main()