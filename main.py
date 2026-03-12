import requests, json, time, re, threading
from datetime import datetime, timedelta
from flask import Flask

# ==== Flask (pour Render) ====
app = Flask(__name__)

@app.route('/')
def health():
    return "OK", 200

def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False)

flask_thread = threading.Thread(target=run_flask, daemon=True)
flask_thread.start()

# ==== Configuration Bot ====
TELEGRAM_BOT_TOKEN = "8237470758:AAEzNur6CwqofKTYaKBdFToiJNbl8_sAhTI"
CREATOR_ADDRESS = "6PAWNJCJqSmeHH6UKo83Gvqyh9sZH4ZmHNza7NsNAwBP"
RPC_URL = "https://mainnet.helius-rpc.com/?api-key=4d11d3a1-149a-49fd-a112-94a008ede057"
HELIUS_API_KEY = "4d11d3a1-149a-49fd-a112-94a008ede057"

TRADE_AMOUNT = 3
PROFIT_TARGET = 0.15
PUMP_FUN_FEE = 0.01
SOLANA_GAS_FEE_MIN = 0.00025
SOLANA_GAS_FEE_MAX = 0.005

# ==== État Global ====
bot_running = False
realtime_active = {}
user_configs = {}
user_wallets = {}
user_history = {}
update_offset = 0

# ==== Charger/Sauvegarder Données Utilisateur ====
def load_user_data(user_id):
    if user_id not in user_configs:
        user_configs[user_id] = {"trade_amount": TRADE_AMOUNT, "profit_target": PROFIT_TARGET}
    if user_id not in user_wallets:
        user_wallets[user_id] = []
    if user_id not in user_history:
        user_history[user_id] = []
    
    try:
        with open(f"config_{user_id}.json", "r") as f:
            user_configs[user_id] = json.load(f)
    except:
        pass
    try:
        with open(f"wallets_{user_id}.json", "r") as f:
            user_wallets[user_id] = json.load(f)
    except:
        pass
    try:
        with open(f"history_{user_id}.json", "r") as f:
            user_history[user_id] = json.load(f)
    except:
        pass

def save_user_data(user_id):
    try:
        with open(f"config_{user_id}.json", "w") as f:
            json.dump(user_configs[user_id], f, indent=2)
        with open(f"wallets_{user_id}.json", "w") as f:
            json.dump(user_wallets[user_id], f, indent=2)
        with open(f"history_{user_id}.json", "w") as f:
            json.dump(user_history[user_id], f, indent=2)
    except:
        pass

# ==== Envoyer Message Telegram ====
def send_telegram(user_id, text):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {"chat_id": user_id, "text": text, "parse_mode": "HTML"}
        requests.post(url, data=data, timeout=5)
    except Exception as e:
        print(f"Erreur send_telegram: {e}")

# ==== Récupérer Updates Telegram ====
def get_updates():
    global update_offset
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
        params = {"offset": update_offset, "timeout": 30}
        resp = requests.get(url, params=params, timeout=35)
        if resp.status_code == 200:
            data = resp.json()
            if data.get("ok") and data.get("result"):
                for update in data["result"]:
                    update_offset = update["update_id"] + 1
                    yield update
    except Exception as e:
        print(f"Erreur get_updates: {e}")

# ==== Extraire Nombre ====
def extract_number(text):
    match = re.search(r"[\d.]+", text)
    return float(match.group()) if match else None

# ==== Prix SOL en EUR ====
def get_sol_price():
    try:
        url = "https://api.coingecko.com/api/v3/simple/price?ids=solana&vs_currencies=eur"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            return resp.json()["solana"]["eur"]
    except:
        pass
    return 150.0  # Fallback

# ==== Récupérer Prix Token ====
def get_token_prices(mint):
    try:
        url = f"https://api.helius.xyz/v0/addresses/{mint}/transactions?api-key={HELIUS_API_KEY}&limit=10"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                entry = float(data[0].get("nativeTransfers", [{}])[0].get("amount", 0)) / 1e9
                ath = entry * 1.25
                return entry if entry > 0 else 0.00001, ath
    except:
        pass
    return 0.00001, 0.000015

# ==== Récupérer Tokens Pump.Fun ====
def get_pump_fun_tokens(user_id):
    tokens = []
    wallets = user_wallets.get(user_id, [])
    
    if not wallets:
        return tokens
    
    wallet = wallets[0]
    try:
        url = f"https://api.helius.xyz/v0/addresses/{wallet}/transactions?api-key={HELIUS_API_KEY}&limit=50"
        resp = requests.get(url, timeout=5)
        if resp.status_code == 200:
            txs = resp.json()
            if isinstance(txs, list):
                for i, tx in enumerate(txs[:5]):
                    name = tx.get("description", f"Token_{i}")
                    ca = tx.get("mint", f"mint_{i}")
                    entry, ath = get_token_prices(ca)
                    tokens.append({
                        "name": name,
                        "ca": ca,
                        "entry": entry,
                        "ath": ath,
                        "url": f"https://pump.fun/coin/{ca}"
                    })
    except Exception as e:
        print(f"Erreur get_pump_fun_tokens: {e}")
    
    return tokens

# ==== Calculer Prix Cible ====
def calculate_target_sell_price(entry_price, target_profit=PROFIT_TARGET):
    buy_fee = entry_price * PUMP_FUN_FEE
    buy_gas = SOLANA_GAS_FEE_MIN
    net_invested = entry_price - buy_fee - buy_gas
    
    target_profit_amount = net_invested * target_profit
    target_gross = net_invested + target_profit_amount
    
    sell_fee = target_gross * PUMP_FUN_FEE
    sell_gas = SOLANA_GAS_FEE_MIN
    
    target_sell = target_gross + sell_fee + sell_gas
    return target_sell

# ==== Simuler Trade ====
def simulate_trade(entry_price, ath_price, target_profit=PROFIT_TARGET):
    buy_fee = entry_price * PUMP_FUN_FEE
    buy_gas = SOLANA_GAS_FEE_MIN
    net_invested = entry_price - buy_fee - buy_gas
    
    actual_sell = min(ath_price, calculate_target_sell_price(entry_price, target_profit))
    sell_fee = actual_sell * PUMP_FUN_FEE
    sell_gas = SOLANA_GAS_FEE_MIN
    net_received = actual_sell - sell_fee - sell_gas
    
    profit_net = net_received - net_invested
    profit_percent = (profit_net / net_invested * 100) if net_invested > 0 else 0
    
    win = profit_percent >= (target_profit * 100)
    
    return {
        "net_invested": net_invested,
        "buy_fee": buy_fee,
        "buy_gas": buy_gas,
        "actual_sell": actual_sell,
        "sell_fee": sell_fee,
        "sell_gas": sell_gas,
        "net_received": net_received,
        "profit_net": profit_net,
        "profit_percent": profit_percent,
        "win": win
    }

# ==== Formater Détail Trade ====
def format_trade_detail(token, calc, target_info, sol_price):
    status = "✅ WIN 🚀" if calc["win"] else "❌ LOSS 📉"
    ath_percent = ((token["ath"] - token["entry"]) / token["entry"] * 100) if token["entry"] > 0 else 0
    
    msg = f"""
<b>{status}</b>
<b>Token:</b> {token['name']}
<b>CA:</b> <code>{token['ca']}</code>
<b>ATH:</b> +{ath_percent:.2f}%
<b>Frais achat:</b> €{calc['buy_fee']:.4f} + €{calc['buy_gas']:.6f}
<b>Frais vente:</b> €{calc['sell_fee']:.4f} + €{calc['sell_gas']:.6f}
<b>Net investi:</b> €{calc['net_invested']:.4f}
<b>Net reçu:</b> €{calc['net_received']:.4f}
<b>Profit net:</b> €{calc['profit_net']:.4f} ({calc['profit_percent']:.2f}%)
<b>Cours SOL:</b> €{sol_price:.2f}
<a href="{token['url']}">Voir sur Pump.fun</a>
"""
    return msg

# ==== Historique Stats ====
def get_history_stats(user_id, days=None):
    history = user_history.get(user_id, [])
    
    if days:
        cutoff = datetime.now() - timedelta(days=days)
        history = [h for h in history if datetime.fromisoformat(h.get("timestamp", "")) > cutoff]
    
    trades = len(history)
    wins = sum(1 for h in history if h.get("win"))
    losses = trades - wins
    win_rate = (wins / trades * 100) if trades > 0 else 0
    total_profit = sum(h.get("profit_net", 0) for h in history)
    avg_profit = total_profit / trades if trades > 0 else 0
    
    return {
        "trades": trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_profit": total_profit,
        "avg_profit": avg_profit
    }

# ==== Gérer Commandes ====
def handle_command(user_id, command_text):
    load_user_data(user_id)
    
    if command_text.startswith("/start"):
        stats = get_history_stats(user_id)
        msg = f"""
<b>🤖 Pump.Fun Bot</b>

<b>Statistiques globales:</b>
📊 Trades: {stats['trades']}
✅ Gagnants: {stats['wins']}
❌ Perdants: {stats['losses']}
📈 Taux: {stats['win_rate']:.1f}%
💰 Profit total: €{stats['total_profit']:.2f}
💵 Moyenne: €{stats['avg_profit']:.2f}

<b>Commandes:</b>
/backtest - Tester les tokens
/realtime - Temps réel
/stats - Stats globales
/config - Configuration
/set_amount - Modifier montant
/set_target - Modifier target
/add_wallet - Ajouter wallet
/list_wallets - Voir wallets
"""
        send_telegram(user_id, msg)
    
    elif command_text.startswith("/backtest"):
        run_backtest(user_id)
    
    elif command_text.startswith("/realtime"):
        realtime_active[user_id] = True
        send_telegram(user_id, "🚀 Temps réel activé!")
        run_realtime_simulation(user_id)
    
    elif command_text.startswith("/stop"):
        realtime_active[user_id] = False
        send_telegram(user_id, "⏹ Temps réel arrêté")
    
    elif command_text.startswith("/stats"):
        stats = get_history_stats(user_id)
        msg = f"""
<b>📊 Statistiques Globales</b>
Trades: {stats['trades']}
Gagnants: {stats['wins']}
Perdants: {stats['losses']}
Taux réussite: {stats['win_rate']:.1f}%
Profit total: €{stats['total_profit']:.2f}
Profit moyen: €{stats['avg_profit']:.2f}
"""
        send_telegram(user_id, msg)
    
    elif command_text.startswith("/history_week"):
        stats = get_history_stats(user_id, days=7)
        msg = f"<b>📈 Derniers 7 jours</b>\nTrades: {stats['trades']}\nGagnants: {stats['wins']}\nProfit: €{stats['total_profit']:.2f}"
        send_telegram(user_id, msg)
    
    elif command_text.startswith("/history_month"):
        stats = get_history_stats(user_id, days=30)
        msg = f"<b>📈 Derniers 30 jours</b>\nTrades: {stats['trades']}\nGagnants: {stats['wins']}\nProfit: €{stats['total_profit']:.2f}"
        send_telegram(user_id, msg)
    
    elif command_text.startswith("/config"):
        cfg = user_configs.get(user_id, {})
        sol_price = get_sol_price()
        msg = f"""
<b>⚙️ Configuration</b>
Montant: €{cfg.get('trade_amount', TRADE_AMOUNT)}
Target: +{cfg.get('profit_target', PROFIT_TARGET)*100:.0f}%
Frais Pump: {PUMP_FUN_FEE*100:.1f}%
Gaz Solana: €{SOLANA_GAS_FEE_MIN:.6f}-€{SOLANA_GAS_FEE_MAX:.6f}
Cours SOL: €{sol_price:.2f}
"""
        send_telegram(user_id, msg)
    
    elif command_text.startswith("/set_amount"):
        amount = extract_number(command_text)
        if amount:
            user_configs[user_id]["trade_amount"] = amount
            save_user_data(user_id)
            send_telegram(user_id, f"✅ Montant: €{amount}")
    
    elif command_text.startswith("/set_target"):
        target = extract_number(command_text)
        if target:
            user_configs[user_id]["profit_target"] = target / 100
            save_user_data(user_id)
            send_telegram(user_id, f"✅ Target: +{target}%")
    
    elif command_text.startswith("/add_wallet"):
        wallet = command_text.replace("/add_wallet", "").strip()
        if wallet and len(wallet) > 30:
            user_wallets[user_id].append(wallet)
            save_user_data(user_id)
            send_telegram(user_id, f"✅ Wallet ajouté: {wallet[:10]}...")
    
    elif command_text.startswith("/remove_wallet"):
        wallet = command_text.replace("/remove_wallet", "").strip()
        if wallet in user_wallets.get(user_id, []):
            user_wallets[user_id].remove(wallet)
            save_user_data(user_id)
            send_telegram(user_id, f"✅ Wallet retiré")
    
    elif command_text.startswith("/list_wallets"):
        wallets = user_wallets.get(user_id, [])
        if wallets:
            msg = "📍 Wallets:\n" + "\n".join([f"{i+1}. {w[:20]}..." for i, w in enumerate(wallets)])
        else:
            msg = "❌ Aucun wallet"
        send_telegram(user_id, msg)
    
    elif command_text.startswith("/clear_wallets"):
        user_wallets[user_id] = []
        save_user_data(user_id)
        send_telegram(user_id, "✅ Wallets effacés")

# ==== Backtest ====
def run_backtest(user_id):
    if not user_wallets.get(user_id, []):
        send_telegram(user_id, "❌ Aucun wallet suivi.\nAjoute un wallet: /add_wallet [adresse]")
        return
    
    tokens = get_pump_fun_tokens(user_id)
    if not tokens:
        send_telegram(user_id, "❌ Aucun token trouvé.\nVérifie que le wallet a créé des tokens sur Pump.fun")
        return
    
    cfg = user_configs.get(user_id, {})
    sol_price = get_sol_price()
    wins = 0
    losses = 0
    total_profit = 0
    
    for token in tokens:
        calc = simulate_trade(token["entry"], token["ath"], cfg.get("profit_target", PROFIT_TARGET))
        msg = format_trade_detail(token, calc, None, sol_price)
        send_telegram(user_id, msg)
        
        if calc["win"]:
            wins += 1
        else:
            losses += 1
        total_profit += calc["profit_net"]
        
        user_history[user_id].append({
            "timestamp": datetime.now().isoformat(),
            "name": token["name"],
            "ca": token["ca"],
            "entry": token["entry"],
            "ath": token["ath"],
            "profit_net": calc["profit_net"],
            "profit_percent": calc["profit_percent"],
            "win": calc["win"]
        })
        
        time.sleep(0.5)
    
    summary = f"""
<b>📊 Résumé Backtest</b>
Tokens: {len(tokens)}
✅ Gagnants: {wins}
❌ Perdants: {losses}
📈 Taux: {(wins/len(tokens)*100):.1f}%
💰 Profit total: €{total_profit:.2f}
"""
    send_telegram(user_id, summary)
    save_user_data(user_id)

# ==== Realtime ====
def run_realtime_simulation(user_id):
    if not user_wallets.get(user_id, []):
        send_telegram(user_id, "❌ Aucun wallet suivi")
        return
    
    while realtime_active.get(user_id, False):
        tokens = get_pump_fun_tokens(user_id)
        if not tokens:
            break
        
        cfg = user_configs.get(user_id, {})
        sol_price = get_sol_price()
        
        for token in tokens:
            if not realtime_active.get(user_id, False):
                break
            
            calc = simulate_trade(token["entry"], token["ath"], cfg.get("profit_target", PROFIT_TARGET))
            msg = format_trade_detail(token, calc, None, sol_price)
            send_telegram(user_id, msg)
            
            user_history[user_id].append({
                "timestamp": datetime.now().isoformat(),
                "name": token["name"],
                "ca": token["ca"],
                "entry": token["entry"],
                "ath": token["ath"],
                "profit_net": calc["profit_net"],
                "profit_percent": calc["profit_percent"],
                "win": calc["win"]
            })
            
            save_user_data(user_id)
            time.sleep(5)
        
        time.sleep(30)
    
    send_telegram(user_id, "✅ Temps réel terminé")

# ==== Heartbeat ====
def heartbeat():
    while True:
        try:
            requests.get(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getMe", timeout=5)
            print("💓 Heartbeat - Bot actif")
        except:
            pass
        time.sleep(600)

# ==== Boucle Principale ====
def run():
    global bot_running
    bot_running = True
    
    heartbeat_thread = threading.Thread(target=heartbeat, daemon=True)
    heartbeat_thread.start()
    
    print("🤖 Bot démarré...")
    
    while bot_running:
        try:
            for update in get_updates():
                if "message" in update:
                    msg = update["message"]
                    user_id = msg.get("from", {}).get("id")
                    text = msg.get("text", "")
                    
                    if user_id and text.startswith("/"):
                        handle_command(user_id, text)
            
            time.sleep(0.5)
        except Exception as e:
            print(f"Erreur run: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run()
