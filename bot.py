import threading
import time
import asyncio
import os
from web3 import Web3
import telebot
from solana.rpc.websocket_api import connect
from solana.publickey import PublicKey
from dotenv import load_dotenv

# Load environment variables dari file .env
load_dotenv()

#########################
# Konfigurasi Telegram  #
#########################
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
if not TELEGRAM_BOT_TOKEN:
    raise Exception("TELEGRAM_BOT_TOKEN belum diset di file .env")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)

# Menyimpan chat id yang aktif (untuk auto alert) di memori
active_chats_lock = threading.Lock()
active_chats = set()

def send_telegram_message(message):
    with active_chats_lock:
        for chat_id in active_chats:
            try:
                bot.send_message(chat_id, message)
            except Exception as e:
                print(f"Error mengirim pesan ke chat {chat_id}: {e}")

#########################
# Konfigurasi Jaringan  #
#########################
# Untuk Ethereum, gunakan Alchemy RPC. Jika ETHEREUM_RPC tidak diset, maka buat default menggunakan ALCHEMY_API_KEY.
networks = {
    "Ethereum": os.getenv('ETHEREUM_RPC', f"https://eth-mainnet.alchemyapi.io/v2/{os.getenv('ALCHEMY_API_KEY')}"),
    "BSC": os.getenv('BSC_RPC', "https://bsc-dataseed.binance.org/"),
    "Arbitrum": os.getenv('ARBITRUM_RPC', "https://arb1.arbitrum.io/rpc"),
    "Base": os.getenv('BASE_RPC', "https://base-mainnet.chainbase.online")
}
# Lock untuk modifikasi dictionary networks
network_lock = threading.Lock()

#############################################
# Global Data: Daftar Wallet yang Dipantau  #
#############################################
# Menyimpan wallet per chain
wallet_lock = threading.Lock()
wallet_addresses = {
    "Ethereum": [],
    "BSC": [],
    "Arbitrum": [],
    "Base": [],
    "Solana": []
}

# Untuk Solana, simpan thread monitoring per wallet
solana_threads = {}

###############################
# Fungsi Monitoring Jaringan EVM
###############################

def handle_event(event, network_name):
    message = f"[{network_name}] Event terdeteksi:\n{event}"
    print(message)
    send_telegram_message(message)

def monitor_network(network_name, rpc_url):
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.isConnected():
        print(f"Gagal terhubung ke {network_name}")
        return
    print(f"Mulai monitoring {network_name}...")
    while True:
        with wallet_lock:
            # Ambil daftar wallet untuk network ini (bisa saja kosong)
            addresses = wallet_addresses.get(network_name, [])
        if addresses:
            try:
                # Membuat filter log untuk seluruh wallet yang ada di list
                event_filter = w3.eth.filter({"address": addresses})
                time.sleep(5)  # Delay polling 5 detik
                events = event_filter.get_new_entries()
                for event in events:
                    handle_event(event, network_name)
            except Exception as e:
                print(f"Error pada {network_name}: {e}")
                time.sleep(5)
        else:
            time.sleep(5)

###############################
# Fungsi Monitoring Jaringan Solana
###############################

async def monitor_solana(account_pubkey_str):
    solana_ws_endpoint = "wss://api.mainnet-beta.solana.com/"
    try:
        async with connect(solana_ws_endpoint) as client:
            # Subscribe ke perubahan akun Solana
            await client.account_subscribe(PublicKey(account_pubkey_str))
            print(f"Mulai monitoring akun Solana: {account_pubkey_str}")
            while True:
                try:
                    msg = await client.recv()
                    message = f"[Solana] Notifikasi untuk {account_pubkey_str}:\n{msg}"
                    print(message)
                    send_telegram_message(message)
                except Exception as e:
                    print("Error pada Solana:", e)
                    await asyncio.sleep(5)
    except Exception as e:
        print(f"Gagal terhubung ke Solana untuk {account_pubkey_str}: {e}")

def start_solana_monitor(wallet_address):
    asyncio.run(monitor_solana(wallet_address))

###############################
# Bot Telegram: Command Handler
###############################

@bot.message_handler(commands=['start'])
def handle_start(message):
    bot.reply_to(message, "Bot monitoring sudah berjalan. Gunakan /help untuk daftar perintah.")

@bot.message_handler(commands=['help'])
def handle_help(message):
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
    bot.reply_to(message, help_text)

@bot.message_handler(commands=['autoalert'])
def auto_alert(message):
    chat_id = message.chat.id
    with active_chats_lock:
        active_chats.add(chat_id)
    bot.reply_to(message, "Auto alert diaktifkan. Notifikasi akan dikirim ke chat ini.")

@bot.message_handler(commands=['stopalert'])
def stop_alert(message):
    chat_id = message.chat.id
    with active_chats_lock:
        if chat_id in active_chats:
            active_chats.remove(chat_id)
            bot.reply_to(message, "Auto alert dinonaktifkan. Notifikasi tidak akan dikirim ke chat ini.")
        else:
            bot.reply_to(message, "Auto alert belum diaktifkan untuk chat ini.")

@bot.message_handler(commands=['addwallet'])
def add_wallet(message):
    try:
        args = message.text.split()
        if len(args) != 3:
            bot.reply_to(message, "Usage: /addwallet <chain> <wallet_address>")
            return
        chain = args[1].capitalize()
        wallet = args[2]
        if chain not in wallet_addresses:
            bot.reply_to(message, f"Chain {chain} tidak didukung. Supported: {', '.join(wallet_addresses.keys())}")
            return
        with wallet_lock:
            if wallet not in wallet_addresses[chain]:
                wallet_addresses[chain].append(wallet)
        bot.reply_to(message, f"Wallet {wallet} telah ditambahkan untuk {chain}.")
        # Untuk Solana, mulai monitoring wallet tersebut jika belum berjalan
        if chain == "Solana":
            if wallet not in solana_threads:
                t = threading.Thread(target=start_solana_monitor, args=(wallet,), daemon=True)
                t.start()
                solana_threads[wallet] = t
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['removewallet'])
def remove_wallet(message):
    try:
        args = message.text.split()
        if len(args) != 3:
            bot.reply_to(message, "Usage: /removewallet <chain> <wallet_address>")
            return
        chain = args[1].capitalize()
        wallet = args[2]
        if chain not in wallet_addresses:
            bot.reply_to(message, f"Chain {chain} tidak didukung.")
            return
        with wallet_lock:
            if wallet in wallet_addresses[chain]:
                wallet_addresses[chain].remove(wallet)
                bot.reply_to(message, f"Wallet {wallet} telah dihapus dari {chain}.")
            else:
                bot.reply_to(message, f"Wallet {wallet} tidak ditemukan pada {chain}.")
        # Catatan: Untuk Solana, penghentian thread monitoring tidak didukung secara dinamis.
        if chain == "Solana" and wallet in solana_threads:
            bot.reply_to(message, "Catatan: Penghentian monitoring Solana tidak didukung secara dinamis. Bot harus direstart untuk menghentikannya.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['listwallets'])
def list_wallets(message):
    with wallet_lock:
        msg = "Daftar wallet yang dipantau:\n"
        for chain, wallets in wallet_addresses.items():
            if wallets:
                msg += f"{chain}: {', '.join(wallets)}\n"
            else:
                msg += f"{chain}: (tidak ada wallet)\n"
    bot.reply_to(message, msg)

@bot.message_handler(commands=['addnetwork'])
def add_network(message):
    try:
        args = message.text.split()
        if len(args) != 3:
            bot.reply_to(message, "Usage: /addnetwork <chain> <rpc_url>")
            return
        chain = args[1]
        rpc_url = args[2]
        with network_lock:
            if chain in networks:
                bot.reply_to(message, f"Network {chain} sudah ada.")
                return
            networks[chain] = rpc_url
        # Tambahkan entry untuk wallet pada network baru
        with wallet_lock:
            wallet_addresses[chain] = []
        # Mulai thread monitoring untuk network baru (asumsi jaringan ini adalah EVM)
        t = threading.Thread(target=monitor_network, args=(chain, rpc_url), daemon=True)
        t.start()
        bot.reply_to(message, f"Network {chain} berhasil ditambahkan dan monitoring dimulai.")
    except Exception as e:
        bot.reply_to(message, f"Error: {e}")

@bot.message_handler(commands=['listnetworks'])
def list_networks(message):
    msg = "Daftar jaringan EVM yang dipantau:\n"
    with network_lock:
        for chain, rpc in networks.items():
            msg += f"{chain}: {rpc}\n"
    bot.reply_to(message, msg)

#########################
# Main Program          #
#########################

if __name__ == '__main__':
    # Memulai monitoring untuk jaringan EVM yang sudah ada di dictionary 'networks'
    with network_lock:
        for network_name, rpc_url in networks.items():
            t = threading.Thread(target=monitor_network, args=(network_name, rpc_url), daemon=True)
            t.start()
    
    print("Bot Telegram mulai polling...")
    bot.infinity_polling()