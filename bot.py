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

#########################
# Konfigurasi Jaringan  #
#########################
ALCHEMY_API_KEY = os.getenv('ALCHEMY_API_KEY')
if not ALCHEMY_API_KEY:
    raise Exception("ALCHEMY_API_KEY belum diset di file .env")

# Gunakan endpoint RPC dari .env atau default dengan ALCHEMY_API_KEY
ETHEREUM_RPC = os.getenv('ETHEREUM_RPC', f"https://eth-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}")
BSC_RPC = os.getenv('BSC_RPC', f"https://bnb-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}")
ARBITRUM_RPC = os.getenv('ARBITRUM_RPC', f"https://arb-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}")
BASE_RPC = os.getenv('BASE_RPC', f"https://base-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}")
UNICHAIN_RPC = os.getenv('UNICHAIN_RPC', f"https://unichain-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}")
SONEIUM_RPC = os.getenv('SONEIUM_RPC', f"https://soneium-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}")
OP_MAINNET_RPC = os.getenv('OP_MAINNET_RPC', f"https://opt-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}")
POLYGON_RPC = os.getenv('POLYGON_RPC', f"https://polygon-mainnet.g.alchemy.com/v2/{ALCHEMY_API_KEY}")

# Daftar jaringan yang dipantau
networks = {
    "Ethereum": ETHEREUM_RPC,
    "BSC": BSC_RPC,
    "Arbitrum": ARBITRUM_RPC,
    "Base": BASE_RPC,
    "Unichain": UNICHAIN_RPC,
    "Soneium": SONEIUM_RPC,
    "OP Mainnet": OP_MAINNET_RPC,
    "Polygon": POLYGON_RPC
}
network_lock = threading.Lock()

# Mapping URL explorer untuk masing-masing jaringan
explorer_urls = {
    "Ethereum": "https://etherscan.io/tx/",
    "BSC": "https://bscscan.com/tx/",
    "Arbitrum": "https://arbiscan.io/tx/",
    "Base": "https://basescan.org/tx/",
    "Unichain": "https://unichainscan.com/tx/",   # Sesuaikan jika perlu
    "Soneium": "https://soneiumscan.com/tx/",       # Sesuaikan jika perlu
    "OP Mainnet": "https://optimistic.etherscan.io/tx/",
    "Polygon": "https://polygonscan.com/tx/"
}

#############################################
# Global Data: Daftar Wallet yang Dipantau  #
#############################################
# Hanya jaringan EVM (yang mendukung alamat dengan format "0x")
wallet_lock = threading.Lock()
wallet_addresses = {
    "Ethereum": [],
    "BSC": [],
    "Arbitrum": [],
    "Base": [],
    "Unichain": [],
    "Soneium": [],
    "OP Mainnet": [],
    "Polygon": []
}

#########################################
# Global Data: Chat ID untuk Notifikasi #
#########################################
active_chats_lock = threading.Lock()
active_chats = set()

# Instance bot Telegram (akan di-set di main())
tg_bot = None

#############################################
# Fungsi Pengiriman Notifikasi Telegram      #
#############################################
def send_telegram_message(message: str):
    with active_chats_lock:
        for chat_id in active_chats:
            try:
                tg_bot.send_message(chat_id=chat_id, text=message)
            except Exception as e:
                print(f"Error sending message to chat {chat_id}: {e}")

#############################################
# Fungsi Monitoring Jaringan EVM             #
#############################################
def handle_event(event, network_name: str):
    # Ambil transaction hash dari event (jika ada)
    tx_hash = None
    if "transactionHash" in event:
        tx_hash = Web3.toHex(event["transactionHash"])
    message = f"[{network_name}] Event detected:\n{event}"
    if tx_hash:
        explorer_link = explorer_urls.get(network_name, "") + tx_hash
        message += f"\nTransaction Hash: {tx_hash}\nExplorer: {explorer_link}"
    print(message)
    send_telegram_message(message)

def monitor_network(network_name: str, rpc_url: str):
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        print(f"Failed to connect to {network_name} using RPC: {rpc_url}")
        return
    print(f"Started monitoring on {network_name}...")
    while True:
        with wallet_lock:
            addresses = wallet_addresses.get(network_name, [])
        if addresses:
            try:
                event_filter = w3.eth.filter({"address": addresses})
                time.sleep(5)  # Polling interval
                events = event_filter.get_new_entries()
                for event in events:
                    handle_event(event, network_name)
            except Exception as e:
                print(f"Error on {network_name}: {e}")
                time.sleep(5)
        else:
            time.sleep(5)

#############################################
# Handler Perintah Bot Telegram            #
#############################################
def start(update: Update, context: CallbackContext):
    update.message.reply_text("Bot monitoring is running. Use /help for the command list.")

def help_command(update: Update, context: CallbackContext):
    help_text = (
        "Available commands:\n"
        "/autoalert - Enable auto notifications for this chat.\n"
        "/stopalert - Disable auto notifications for this chat.\n"
        "/addwallet <chain> <wallet_address> - Add a wallet for monitoring. Example: /addwallet Ethereum 0xAbc...\n"
        "/addall <wallet_address> - Add a wallet to ALL networks (if address starts with '0x').\n"
        "/removewallet <chain> <wallet_address> - Remove a wallet from monitoring.\n"
        "/listwallets - List monitored wallets.\n"
        "/addnetwork <chain> <rpc_url> - Add a new EVM network for monitoring.\n"
        "/listnetworks - List monitored networks."
    )
    update.message.reply_text(help_text)

def autoalert(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    with active_chats_lock:
        active_chats.add(chat_id)
    update.message.reply_text("Auto alert enabled. Notifications will be sent to this chat.")

def stopalert(update: Update, context: CallbackContext):
    chat_id = update.message.chat_id
    with active_chats_lock:
        if chat_id in active_chats:
            active_chats.remove(chat_id)
            update.message.reply_text("Auto alert disabled. Notifications will no longer be sent to this chat.")
        else:
            update.message.reply_text("Auto alert was not enabled for this chat.")

def addwallet(update: Update, context: CallbackContext):
    try:
        args = context.args
        if len(args) != 2:
            update.message.reply_text("Usage: /addwallet <chain> <wallet_address>")
            return
        chain = args[0].capitalize()
        wallet = args[1]
        if chain not in wallet_addresses:
            update.message.reply_text(f"Chain {chain} not supported. Supported: {', '.join(wallet_addresses.keys())}")
            return
        with wallet_lock:
            if wallet not in wallet_addresses[chain]:
                wallet_addresses[chain].append(wallet)
        update.message.reply_text(f"Wallet {wallet} added for {chain}.")
    except Exception as e:
        update.message.reply_text(f"Error: {e}")

def addall(update: Update, context: CallbackContext):
    try:
        args = context.args
        if len(args) != 1:
            update.message.reply_text("Usage: /addall <wallet_address>")
            return
        wallet = args[0]
        if not wallet.startswith("0x"):
            update.message.reply_text("The wallet address must start with '0x'.")
            return
        with wallet_lock:
            for chain in wallet_addresses.keys():
                if wallet not in wallet_addresses[chain]:
                    wallet_addresses[chain].append(wallet)
        update.message.reply_text(f"Wallet {wallet} added to all networks.")
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
            update.message.reply_text(f"Chain {chain} not supported.")
            return
        with wallet_lock:
            if wallet in wallet_addresses[chain]:
                wallet_addresses[chain].remove(wallet)
                update.message.reply_text(f"Wallet {wallet} removed from {chain}.")
            else:
                update.message.reply_text(f"Wallet {wallet} not found in {chain}.")
    except Exception as e:
        update.message.reply_text(f"Error: {e}")

def listwallets(update: Update, context: CallbackContext):
    with wallet_lock:
        msg = "Monitored wallets:\n"
        for chain, wallets in wallet_addresses.items():
            if wallets:
                msg += f"{chain}: {', '.join(wallets)}\n"
            else:
                msg += f"{chain}: (none)\n"
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
                update.message.reply_text(f"Network {chain} already exists.")
                return
            networks[chain] = rpc_url
        with wallet_lock:
            wallet_addresses[chain] = []
        t = threading.Thread(target=monitor_network, args=(chain, rpc_url), daemon=True)
        t.start()
        update.message.reply_text(f"Network {chain} added and monitoring started.")
    except Exception as e:
        update.message.reply_text(f"Error: {e}")

def listnetworks(update: Update, context: CallbackContext):
    msg = "Monitored networks:\n"
    with network_lock:
        for chain, rpc in networks.items():
            msg += f"{chain}: {rpc}\n"
    update.message.reply_text(msg)

#############################################
# Main Program                             #
#############################################
def main():
    updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
    global tg_bot
    tg_bot = updater.bot

    dp = updater.dispatcher
    dp.add_handler(CommandHandler("start", start))
    dp.add_handler(CommandHandler("help", help_command))
    dp.add_handler(CommandHandler("autoalert", autoalert))
    dp.add_handler(CommandHandler("stopalert", stopalert))
    dp.add_handler(CommandHandler("addwallet", addwallet, pass_args=True))
    dp.add_handler(CommandHandler("addall", addall, pass_args=True))
    dp.add_handler(CommandHandler("removewallet", removewallet, pass_args=True))
    dp.add_handler(CommandHandler("listwallets", listwallets))
    dp.add_handler(CommandHandler("addnetwork", addnetwork, pass_args=True))
    dp.add_handler(CommandHandler("listnetworks", listnetworks))

    # Mulai monitoring untuk semua jaringan yang telah dikonfigurasi
    with network_lock:
        for network_name, rpc_url in networks.items():
            t = threading.Thread(target=monitor_network, args=(network_name, rpc_url), daemon=True)
            t.start()

    updater.start_polling()
    print("Telegram bot polling started...")
    updater.idle()

if __name__ == '__main__':
    main()