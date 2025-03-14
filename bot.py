import threading
import time
import os
from web3 import Web3
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext
from dotenv import load_dotenv

# Muat variabel lingkungan dari file .env
load_dotenv()

#########################
# Konfigurasi Telegram  #
#########################
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    raise Exception("TELEGRAM_BOT_TOKEN belum diset di file .env")

# Global bot instance akan diset nanti dari updater.bot
tg_bot = None

# Menyimpan chat id yang aktif (untuk auto alert) secara in‑memory
active_chats_lock = threading.Lock()
active_chats = set()

def send_telegram_message(message: str):
    with active_chats_lock:
        for chat_id in active_chats:
            try:
                tg_bot.send_message(chat_id=chat_id, text=message)
            except Exception as e:
                print(f"Error mengirim pesan ke chat {chat_id}: {e}")

#########################
# Konfigurasi Jaringan  #
#########################
# Jika ETHEREUM_RPC tidak diset, gunakan Alchemy API Key untuk membuat endpoint.
networks = {
    "Ethereum": os.getenv('ETHEREUM_RPC', f"https://eth-mainnet.g.alchemy.com/v2/{os.getenv('ALCHEMY_API_KEY')}"),
    "BSC": os.getenv('BSC_RPC', "https://bsc-dataseed.binance.org/"),
    "Arbitrum": os.getenv('ARBITRUM_RPC', "https://arb1.arbitrum.io/rpc"),
    "Base": os.getenv('BASE_RPC', "https://base-mainnet.chainbase.online")
}
network_lock = threading.Lock()

#############################################
# Global Data: Daftar Wallet yang Dipantau  #
#############################################
# Menyimpan wallet untuk masing-masing chain
wallet_lock = threading.Lock()
wallet_addresses = {
    "Ethereum": [],
    "BSC": [],
    "Arbitrum": [],
    "Base": []
}

###############################
# Fungsi Monitoring Jaringan EVM
###############################

def handle_event(event, network_name: str):
    message = f"[{network_name}] Event terdeteksi:\n{event}"
    print(message)
    send_telegram_message(message)

def monitor_network(network_name: str, rpc_url: str):
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"Gagal terhubung ke {network_name} menggunakan RPC: {rpc_url}")
        return
    print(f"Mulai monitoring {network_name}...")
    while True:
        with wallet_lock:
            addresses = wallet_addresses.get(network_name, [])
        if addresses:
            try:
                # Membuat filter log untuk wallet yang terdaftar pada network ini
                event_filter = w3.eth.filter({"address": addresses})
                time.sleep(5)  # Polling setiap 5 detik
                events = event_filter.get_new_entries()
                for event in events:
                    handle_event(event, network_name)
            except Exception as e:
                print(f"Error pada {network_name}: {e}")
                time.sleep(5)
        else:
            time.sleep(5)

###############################
# Handler Perintah Bot Telegram
###############################

def start(update: Update, context: CallbackContext):
    update.message.reply_text("Bot monitoring sudah berjalan. Gunakan /help untuk daftar perintah.")

def help_command(update: Update, context: CallbackContext):
    help_text = (
        "Perintah yang tersedia:\n"
        "/autoalert - Aktifkan notifikasi otomatis untuk chat ini.\n"
        "/stopalert - Nonaktifkan notifikasi otomatis untuk chat ini.\n"
        "/addwallet <chain> <wallet_address> - Tambahkan wallet ke monitoring. Contoh: /addwallet Ethereum 0xAbc...\n"
        "/removewallet <chain> <wallet_address> - Hapus wallet dari monitoring.\n"
        "/listwallets - Tampilkan daftar wallet yang dipantau.\n"
        "/addnetwork <chain> <rpc_url> - Tambahkan jaringan EVM baru untuk dimonitor secara otomatis.\n"
        "/listnetworks - Tampilkan daftar jaringan EVM yang dipantau."
    )
    update.message.reply_text(help_text)

def autoalert(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    with active_chats_lock:
        active_chats.add(chat_id)
    update.message.reply_text("Auto alert diaktifkan. Notifikasi akan dikirim ke chat ini.")

def stopalert(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    with active_chats_lock:
        if chat_id in active_chats:
            active_chats.remove(chat_id)
            update.message.reply_text("Auto alert dinonaktifkan. Notifikasi tidak akan dikirim ke chat ini.")
        else:
            update.message.reply_text("Auto alert belum diaktifkan untuk chat ini.")

def addwallet(update: Update, context: CallbackContext):
    try:
        args = context.args
        if len(args) != 2:
            update.message.reply_text("Usage: /addwallet <chain> <wallet_address>")
            return
        chain = args[0].capitalize()
        wallet = args[1]
        if chain not in wallet_addresses:
            update.message.reply_text(f"Chain {chain} tidak didukung. Supported: {', '.join(wallet_addresses.keys())}")
            return
        with wallet_lock:
            if wallet not in wallet_addresses[chain]:
                wallet_addresses[chain].append(wallet)
        update.message.reply_text(f"Wallet {wallet} telah ditambahkan untuk {chain}.")
    except Exception as e:
        update.message.reply_text(f"Error: {e}")

def removewallet(update: Update, context: CallbackContext):
    try:
        args = context.args
        if len(args) != 2:
            update.message.reply_text("Usage: /removewallet <chain> <wallet_address>")
            return
        chain = args[0].capitalize()
        wallet = args[1]
        if chain not in wallet_addresses:
            update.message.reply_text(f"Chain {chain} tidak didukung.")
            return
        with wallet_lock:
            if wallet in wallet_addresses[chain]:
                wallet_addresses[chain].remove(wallet)
                update.message.reply_text(f"Wallet {wallet} telah dihapus dari {chain}.")
            else:
                update.message.reply_text(f"Wallet {wallet} tidak ditemukan pada {chain}.")
    except Exception as e:
        update.message.reply_text(f"Error: {e}")

def listwallets(update: Update, context: CallbackContext):
    with wallet_lock:
        msg = "Daftar wallet yang dipantau:\n"
        for chain, wallets in wallet_addresses.items():
            if wallets:
                msg += f"{chain}: {', '.join(wallets)}\n"
            else:
                msg += f"{chain}: (tidak ada wallet)\n"
    update.message.reply_text(msg)

def addnetwork(update: Update, context: CallbackContext):
    try:
        args = context.args
        if len(args) != 2:
            update.message.reply_text("Usage: /addnetwork <chain> <rpc_url>")
            return
        chain = args[0]
        rpc_url = args[1]
        with network_lock:
            if chain in networks:
                update.message.reply_text(f"Network {chain} sudah ada.")
                return
            networks[chain] = rpc_url
        with wallet_lock:
            wallet_addresses[chain] = []
        t = threading.Thread(target=monitor_network, args=(chain, rpc_url), daemon=True)
        t.start()
        update.message.reply_text(f"Network {chain} berhasil ditambahkan dan monitoring dimulai.")
    except Exception as e:
        update.message.reply_text(f"Error: {e}")

def listnetworks(update: Update, context: CallbackContext):
    msg = "Daftar jaringan EVM yang dipantau:\n"
    with network_lock:
        for chain, rpc in networks.items():
            msg += f"{chain}: {rpc}\n"
    update.message.reply_text(msg)

#########################
# Main Program          #
#########################
def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    global tg_bot
    tg_bot = updater.bot  # Simpan bot instance global untuk fungsi pengiriman notifikasi

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("autoalert", autoalert))
    dp.add_handler(CommandHandler("stopalert", stopalert))
    dp.add_handler(CommandHandler("addwallet", addwallet, pass_args=True))
    dp.add_handler(CommandHandler("removewallet", removewallet, pass_args=True))
    dp.add_handler(CommandHandler("listwallets", listwallets))
    dp.add_handler(CommandHandler("addnetwork", addnetwork, pass_args=True))
    dp.add_handler(CommandHandler("listnetworks", listnetworks))

    # Mulai monitoring untuk jaringan yang sudah ada
    with network_lock:
        for network_name, rpc_url in networks.items():
            t = threading.Thread(target=monitor_network, args=(network_name, rpc_url), daemon=True)
            t.start()

    updater.start_polling()
    print("Bot Telegram mulai polling...")
    updater.idle()

if __name__ == '__main__':
    main()