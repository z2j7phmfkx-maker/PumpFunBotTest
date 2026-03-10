import requests, json, time
from datetime import datetime, timedelta

# Configuration globale
TELEGRAM_BOT_TOKEN = "8237470758:AAEzNur6CwqofKTYaKBdFToiJNbl8_sAhTI"
CREATOR_ADDRESS = "6PAWNJCJqSmeHH6UKo83Gvqyh9sZH4ZmHNza7NsNAwBP"
RPC_URL = "https://mainnet.helius-rpc.com/?api-key=4d11d3a1-149a-49fd-a112-94a008ede057"
TRADE_AMOUNT = 3
PROFIT_TARGET = 0.15
PUMP_FUN_FEE = 0.01
SOLANA_GAS_FEE = 0.000625

# Stockage par utilisateur
bot_running = False
realtime_active = {}
user_configs = {}
user_wallets = {}
user_history = {}
update_offset = 0

def load_user_data(user_id):
    """Charge ou crée les données pour un utilisateur"""
    if user_id not in user_configs:
        user_configs[user_id] = {"trade_amount": TRADE_AMOUNT, "profit_target": PROFIT_TARGET}
    if user_id not in user_wallets:
        user_wallets[user_id] = [CREATOR_ADDRESS]
    if user_id not in user_history:
        user_history[user_id] = []
    
    # Charge depuis les fichiers s'ils existent
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
    """Sauvegarde les données d'un utilisateur"""
    try:
        with open(f"config_{user_id}.json", "w") as f:
            json.dump(user_configs[user_id], f, indent=2)
        with open(f"wallets_{user_id}.json", "w") as f:
            json.dump(user_wallets[user_id], f, indent=2)
        with open(f"history_{user_id}.json", "w") as f:
            json.dump(user_history[user_id], f, indent=2)
    except:
        pass

def send_telegram(user_id, msg):
    """Envoie un message à UN UTILISATEUR SPÉCIFIQUE"""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": user_id, "text": msg, "parse_mode": "HTML"}, timeout=10)
        print(f"✅ Message envoyé à {user_id}")
    except Exception as e:
        print(f"❌ Erreur: {e}")

def get_updates():
    global update_offset
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    try:
        response = requests.post(url, json={"offset": update_offset, "timeout": 30}, timeout=35)
        data = response.json()
        if data.get("ok"):
            return data.get("result", [])
    except:
        pass
    return []

def extract_number(text):
    import re
    match = re.search(r'[\d.]+', text)
    return float(match.group()) if match else None

def calculate_target_sell_price(user_id, entry_price):
    config = user_configs[user_id]
    trade_amt = config["trade_amount"]
    profit_tgt = config["profit_target"]
    
    fee_buy = trade_amt * PUMP_FUN_FEE
    net_buy = trade_amt - fee_buy - SOLANA_GAS_FEE
    
    target_amount = trade_amt * (1 + profit_tgt)
    amount_before_sell_fee = target_amount / (1 - PUMP_FUN_FEE)
    target_sell_price = amount_before_sell_fee / (trade_amt / entry_price) if entry_price > 0 else 0
    
    return {
        "entry": entry_price,
        "target": target_sell_price,
        "gain_needed": (target_sell_price - entry_price) / entry_price if entry_price > 0 else 0,
        "net_invested": net_buy
    }

def simulate_trade(user_id, entry, actual_sell, ath, name):
    config = user_configs[user_id]
    trade_amt = config["trade_amount"]
    profit_tgt = config["profit_target"]
    
    fee_buy = trade_amt * PUMP_FUN_FEE
    net_invested = trade_amt - fee_buy - SOLANA_GAS_FEE
    
    tokens_bought = trade_amt / entry if entry > 0 else 0
    amount_at_sell = tokens_bought * actual_sell
    
    fee_sell = amount_at_sell * PUMP_FUN_FEE
    net_received = amount_at_sell - fee_sell - SOLANA_GAS_FEE
    
    profit_net = net_received - net_invested
    profit_percent = (profit_net / net_invested * 100) if net_invested > 0 else 0
    gross_gain = (actual_sell - entry) / entry if entry > 0 else 0
    ath_percent = (ath - entry) / entry if entry > 0 else 0
    
    win = profit_percent >= (profit_tgt * 100)
    
    return {
        "name": name,
        "entry": entry,
        "actual_sell": actual_sell,
        "ath": ath,
        "ath_percent": ath_percent,
        "gross_gain": gross_gain,
        "fee_buy": fee_buy,
        "gas_buy": SOLANA_GAS_FEE,
        "net_invested": net_invested,
        "tokens_bought": tokens_bought,
        "fee_sell": fee_sell,
        "gas_sell": SOLANA_GAS_FEE,
        "net_received": net_received,
        "profit_net": profit_net,
        "profit_percent": profit_percent,
        "win": win
    }

def format_trade_detail(user_id, token, calc, target_info):
    config = user_configs[user_id]
    name = token.get("name", "Unknown")
    url = token.get("url", "#")
    status = "✅ WIN" if calc["win"] else "❌ LOSS"
    
    detail = f"{status} <b>{name}</b>\n\n"
    detail += f"<b>📈 Token Info</b>\n"
    detail += f"ATH: +{calc['ath_percent']*100:.2f}% ({calc['ath']:.10f} SOL)\n"
    detail += f"Vente simulée: +{calc['gross_gain']*100:.2f}%\n\n"
    
    detail += f"<b>💰 Prix cible pour +{config['profit_target']*100:.0f}% net</b>\n"
    detail += f"Entrée: {target_info['entry']:.10f} SOL\n"
    detail += f"Cible: {target_info['target']:.10f} SOL\n"
    detail += f"Gain brut requis: +{target_info['gain_needed']*100:.2f}%\n\n"
    
    detail += f"<b>🛒 Achat</b>\n"
    detail += f"Mise: {config['trade_amount']}€\n"
    detail += f"Frais Pump.fun: {calc['fee_buy']:.4f}€\n"
    detail += f"Gaz Solana: {calc['gas_buy']:.6f}€\n"
    detail += f"Net investi: {calc['net_invested']:.4f}€\n\n"
    
    detail += f"<b>📤 Vente</b>\n"
    detail += f"Montant: {calc['net_received']:.4f}€\n"
    detail += f"Frais Pump.fun: {calc['fee_sell']:.4f}€\n"
    detail += f"Gaz Solana: {calc['gas_sell']:.6f}€\n"
    detail += f"Net reçu: {calc['net_received']:.4f}€\n\n"
    
    detail += f"<b>💵 Résultat</b>\n"
    detail += f"Profit net: <b>{calc['profit_net']:.4f}€</b>\n"
    detail += f"Rendement: <b>{calc['profit_percent']:.2f}%</b>\n\n"
    detail += f"🔗 <a href='{url}'>Voir token sur Pump.fun</a>"
    
    return detail

def get_pump_fun_tokens(user_id):
    wallets = user_wallets[user_id]
    try:
        url = f"https://api.helius.xyz/v0/addresses/{wallets[0]}/transactions"
        params = {"api-key": "4d11d3a1-149a-49fd-a112-94a008ede057", "limit": 50}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            txs = r.json()
            tokens = [
                {"name": f"Token {i+1}", "ca": f"token_ca_{i}", "entry": 0.00001*(i+1),
                 "ath": 0.00001*(i+1)*(1+(0.1+i*0.05)), "url": f"https://pump.fun/coin/token_{i}"}
                for i in range(min(5, len(txs)))
            ]
            return tokens
    except Exception as e:
        print(f"⚠️ Erreur API: {e}")
    
    return [
        {"name": "🚀 MOON ROCKET", "ca": "ca1", "entry": 0.0001, "ath": 0.00013, "url": "https://pump.fun/coin/ca1"},
        {"name": "💰 DEGEN COIN", "ca": "ca2", "entry": 0.00001, "ath": 0.000015, "url": "https://pump.fun/coin/ca2"},
        {"name": "🎯 PUMP TEST", "ca": "ca3", "entry": 0.00005, "ath": 0.00003, "url": "https://pump.fun/coin/ca3"},
        {"name": "📈 MEGA PUMP", "ca": "ca4", "entry": 0.000001, "ath": 0.0000013, "url": "https://pump.fun/coin/ca4"},
        {"name": "💀 DEAD COIN", "ca": "ca5", "entry": 0.0001, "ath": 0.00008, "url": "https://pump.fun/coin/ca5"}
    ]

def get_history_stats(user_id, days=None):
    history = user_history[user_id]
    if not history:
        return None
    
    if days:
        cutoff = datetime.now() - timedelta(days=days)
        trades = [t for t in history if datetime.fromisoformat(t.get("timestamp", datetime.now().isoformat())) >= cutoff]
    else:
        trades = history
    
    if not trades:
        return None
    
    wins = sum(1 for t in trades if t.get("win"))
    losses = len(trades) - wins
    total_profit = sum(t.get("profit_net", 0) for t in trades)
    avg_profit = total_profit / len(trades) if trades else 0
    win_rate = (wins / len(trades) * 100) if trades else 0
    
    return {
        "trades": len(trades),
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "total_profit": total_profit,
        "avg_profit": avg_profit
    }

def handle_command(user_id, command):
    global realtime_active
    
    load_user_data(user_id)
    config = user_configs[user_id]
    
    parts = command.split()
    cmd = parts[0].lower()
    
    if cmd == "/start":
        msg = "🤖 <b>Bot Pump.Fun activé!</b>\n\n"
        msg += "<b>Commandes principales:</b>\n"
        msg += "/backtest – Tester les tokens\n"
        msg += "/realtime – Temps réel\n"
        msg += "/stop – Arrêter\n"
        msg += "/stats – Stats globales\n"
        msg += "/history_week – Stats 7j\n"
        msg += "/history_month – Stats 30j\n\n"
        msg += "<b>Configuration:</b>\n"
        msg += "/config – Afficher config\n"
        msg += "/set_amount 5 (ou 5€)\n"
        msg += "/set_target 20 (ou 20%)\n\n"
        msg += "<b>Wallets:</b>\n"
        msg += "/add_wallet [addr]\n"
        msg += "/remove_wallet [addr]\n"
        msg += "/list_wallets\n"
        msg += "/clear_wallets\n\n"
        msg += f"<b>Wallets suivis:</b> {len(user_wallets[user_id])}\n"
        msg += f"<b>Montant:</b> {config['trade_amount']}€\n"
        msg += f"<b>Target:</b> +{config['profit_target']*100:.0f}%"
        send_telegram(user_id, msg)
    
    elif cmd == "/backtest":
        send_telegram(user_id, "📊 <b>Backtesting...</b>\n⏳ Récupération des données…")
        run_backtest(user_id)
    
    elif cmd == "/realtime":
        if not realtime_active.get(user_id, False):
            realtime_active[user_id] = True
            send_telegram(user_id, "🚀 <b>Temps réel activé!</b>\n⏳ Attente de tokens…")
            run_realtime_simulation(user_id)
        else:
            send_telegram(user_id, "⚠️ Temps réel déjà actif!")
    
    elif cmd == "/stop":
        realtime_active[user_id] = False
        send_telegram(user_id, "⏹️ Arrêté")
    
    elif cmd == "/stats":
        stats = get_history_stats(user_id)
        if stats:
            msg = f"📈 <b>Statistiques globales</b>\n"
            msg += f"Trades: {stats['trades']}\n"
            msg += f"Gagnants: {stats['wins']} | Perdants: {stats['losses']}\n"
            msg += f"Taux: {stats['win_rate']:.1f}%\n"
            msg += f"Profit total: <b>{stats['total_profit']:.2f}€</b>\n"
            msg += f"Profit moyen: {stats['avg_profit']:.2f}€"
            send_telegram(user_id, msg)
        else:
            send_telegram(user_id, "❌ Pas d'historique")
    
    elif cmd == "/history_week":
        stats = get_history_stats(user_id, days=7)
        if stats:
            msg = f"📊 <b>Stats 7 jours</b>\n"
            msg += f"Trades: {stats['trades']}\n"
            msg += f"Gagnants: {stats['wins']} | Perdants: {stats['losses']}\n"
            msg += f"Taux: {stats['win_rate']:.1f}%\n"
            msg += f"Profit total: <b>{stats['total_profit']:.2f}€</b>"
            send_telegram(user_id, msg)
        else:
            send_telegram(user_id, "❌ Pas de données")
    
    elif cmd == "/history_month":
        stats = get_history_stats(user_id, days=30)
        if stats:
            msg = f"📊 <b>Stats 30 jours</b>\n"
            msg += f"Trades: {stats['trades']}\n"
            msg += f"Gagnants: {stats['wins']} | Perdants: {stats['losses']}\n"
            msg += f"Taux: {stats['win_rate']:.1f}%\n"
            msg += f"Profit total: <b>{stats['total_profit']:.2f}€</b>"
            send_telegram(user_id, msg)
        else:
            send_telegram(user_id, "❌ Pas de données")
    
    elif cmd == "/config":
        msg = "<b>⚙️ Configuration</b>\n\n"
        msg += f"Montant: {config['trade_amount']}€\n"
        msg += f"Target: +{config['profit_target']*100:.0f}%\n"
        msg += f"Frais Pump: {PUMP_FUN_FEE*100:.1f}%\n"
        msg += f"Gaz Solana: {SOLANA_GAS_FEE:.6f}€"
        send_telegram(user_id, msg)
    
    elif cmd == "/set_amount":
        if len(parts) > 1:
            num = extract_number(' '.join(parts[1:]))
            if num and num > 0:
                user_configs[user_id]["trade_amount"] = float(num)
                save_user_data(user_id)
                send_telegram(user_id, f"✅ Montant: {user_configs[user_id]['trade_amount']}€")
            else:
                send_telegram(user_id, "❌ Format invalide")
        else:
            send_telegram(user_id, "❌ Utilise: /set_amount 5")
    
    elif cmd == "/set_target":
        if len(parts) > 1:
            num = extract_number(' '.join(parts[1:]))
            if num and num > 0:
                user_configs[user_id]["profit_target"] = float(num) / 100
                save_user_data(user_id)
                send_telegram(user_id, f"✅ Target: +{user_configs[user_id]['profit_target']*100:.0f}%")
            else:
                send_telegram(user_id, "❌ Format invalide")
        else:
            send_telegram(user_id, "❌ Utilise: /set_target 20")
    
    elif cmd == "/add_wallet":
        if len(parts) > 1:
            addr = parts[1]
            if addr not in user_wallets[user_id]:
                user_wallets[user_id].append(addr)
                save_user_data(user_id)
                send_telegram(user_id, f"✅ Wallet ajouté\nTotal: {len(user_wallets[user_id])}")
            else:
                send_telegram(user_id, "⚠️ Déjà suivi")
        else:
            send_telegram(user_id, "❌ Utilise: /add_wallet [addr]")
    
    elif cmd == "/remove_wallet":
        if len(parts) > 1:
            addr = parts[1]
            if addr in user_wallets[user_id]:
                user_wallets[user_id].remove(addr)
                save_user_data(user_id)
                send_telegram(user_id, f"✅ Wallet retiré\nTotal: {len(user_wallets[user_id])}")
            else:
                send_telegram(user_id, "⚠️ Non trouvé")
        else:
            send_telegram(user_id, "❌ Utilise: /remove_wallet [addr]")
    
    elif cmd == "/list_wallets":
        if user_wallets[user_id]:
            msg = "<b>📍 Wallets:</b>\n\n"
            for i, w in enumerate(user_wallets[user_id], 1):
                msg += f"{i}. <code>{w}</code>\n"
            send_telegram(user_id, msg)
        else:
            send_telegram(user_id, "❌ Aucun wallet")
    
    elif cmd == "/clear_wallets":
        user_wallets[user_id] = []
        save_user_data(user_id)
        send_telegram(user_id, "✅ Wallets supprimés")
    
    else:
        send_telegram(user_id, "❌ Commande inconnue")

def run_backtest(user_id):
    tokens = get_pump_fun_tokens(user_id)
    config = user_configs[user_id]
    wins = losses = total_profit = 0
    
    for token in tokens:
        entry = token["entry"]
        ath = token["ath"]
        
        target_info = calculate_target_sell_price(user_id, entry)
        calc = simulate_trade(user_id, entry, ath, ath, token["name"])
        
        detail = format_trade_detail(user_id, token, calc, target_info)
        send_telegram(user_id, detail)
        
        if calc["win"]:
            wins += 1
        else:
            losses += 1
        
        total_profit += calc["profit_net"]
        
        user_history[user_id].append({
            "timestamp": datetime.now().isoformat(),
            "name": token["name"],
            "entry": entry,
            "ath": ath,
            "profit_net": calc["profit_net"],
            "profit_percent": calc["profit_percent"],
            "win": calc["win"]
        })
        save_user_data(user_id)
        time.sleep(1)
    
    total = len(tokens)
    win_rate = (wins / total * 100) if total else 0
    
    summary = f"---\n📈 <b>RÉSUMÉ</b>\n"
    summary += f"Tokens: {total} | Gagnants: {wins} | Perdants: {losses}\n"
    summary += f"Taux: {win_rate:.1f}%\n"
    summary += f"<b>Profit total: {total_profit:.2f}€</b>"
    send_telegram(user_id, summary)

def run_realtime_simulation(user_id):
    global realtime_active
    tokens = get_pump_fun_tokens(user_id)
    
    for token in tokens:
        if not realtime_active.get(user_id, False):
            break
        
        entry = token["entry"]
        ath = token["ath"]
        
        target_info = calculate_target_sell_price(user_id, entry)
        calc = simulate_trade(user_id, entry, ath, ath, token["name"])
        
        detail = format_trade_detail(user_id, token, calc, target_info)
        send_telegram(user_id, detail)
        
        user_history[user_id].append({
            "timestamp": datetime.now().isoformat(),
            "name": token["name"],
            "entry": entry,
            "ath": ath,
            "profit_net": calc["profit_net"],
            "profit_percent": calc["profit_percent"],
            "win": calc["win"]
        })
        save_user_data(user_id)
        time.sleep(5)
    
    realtime_active[user_id] = False
    send_telegram(user_id, "✅ Temps réel terminé")

def run():
    global bot_running, update_offset
    bot_running = True
    
    print("🤖 Bot multi-utilisateur activé…")
    
    while bot_running:
        try:
            updates = get_updates()
            for upd in updates:
                update_offset = upd.get("update_id") + 1
                msg = upd.get("message", {})
                text = msg.get("text", "")
                user_id = msg.get("chat", {}).get("id")
                
                if user_id and text.startswith("/"):
                    print(f"📨 {user_id}: {text}")
                    handle_command(user_id, text)
            
            time.sleep(1)
        except Exception as e:
            print(f"❌ Erreur: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run()
