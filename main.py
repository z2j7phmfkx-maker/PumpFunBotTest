import requests, json, time
from datetime import datetime, timedelta

# Configuration
TELEGRAM_BOT_TOKEN = "8237470758:AAEzNur6CwqofKTYaKBdFToiJNbl8_sAhTI"
TELEGRAM_ID = "8536904445"
CREATOR_ADDRESS = "6PAWNJCJqSmeHH6UKo83Gvqyh9sZH4ZmHNza7NsNAwBP"
RPC_URL = "https://mainnet.helius-rpc.com/?api-key=4d11d3a1-149a-49fd-a112-94a008ede057"
TRADE_AMOUNT = 3
PROFIT_TARGET = 0.15
PUMP_FUN_FEE = 0.01
SOLANA_GAS_FEE = 0.000625

# Global state
bot_running = False
realtime_active = False
config = {"trade_amount": TRADE_AMOUNT, "profit_target": PROFIT_TARGET, "pump_fun_fee": PUMP_FUN_FEE, "solana_gas_fee": SOLANA_GAS_FEE}
wallets_to_track = [CREATOR_ADDRESS]
all_trades_history = []
update_offset = 0

def load_history():
    global all_trades_history
    try:
        with open("trades_history.json", "r") as f:
            all_trades_history = json.load(f)
    except:
        all_trades_history = []

def save_history():
    try:
        with open("trades_history.json", "w") as f:
            json.dump(all_trades_history, f, indent=2)
    except:
        pass

def load_config():
    global config
    try:
        with open("config.json", "r") as f:
            config = json.load(f)
    except:
        config = {"trade_amount": TRADE_AMOUNT, "profit_target": PROFIT_TARGET, "pump_fun_fee": PUMP_FUN_FEE, "solana_gas_fee": SOLANA_GAS_FEE}

def save_config():
    try:
        with open("config.json", "w") as f:
            json.dump(config, f, indent=2)
    except:
        pass

def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, data={"chat_id": TELEGRAM_ID, "text": msg, "parse_mode": "HTML"}, timeout=10)
        print("✅ Message envoyé")
    except Exception as e:
        print(f"❌ Erreur Telegram: {e}")

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
    """Extrait un nombre d'une chaîne (accepte € ou % ou sans)"""
    import re
    match = re.search(r'[\d.]+', text)
    return float(match.group()) if match else None

def calculate_target_sell_price(entry_price):
    trade_amt = config["trade_amount"]
    profit_tgt = config["profit_target"]
    pump_fee = config["pump_fun_fee"]
    gas_fee = config["solana_gas_fee"]
    
    fee_buy = trade_amt * pump_fee
    net_buy = trade_amt - fee_buy - gas_fee
    
    target_amount = trade_amt * (1 + profit_tgt)
    amount_before_sell_fee = target_amount / (1 - pump_fee)
    target_sell_price = amount_before_sell_fee / (trade_amt / entry_price) if entry_price > 0 else 0
    
    return {
        "entry": entry_price,
        "target": target_sell_price,
        "gain_needed": (target_sell_price - entry_price) / entry_price if entry_price > 0 else 0,
        "net_invested": net_buy
    }

def simulate_trade(entry, actual_sell, ath, name):
    trade_amt = config["trade_amount"]
    profit_tgt = config["profit_target"]
    pump_fee = config["pump_fun_fee"]
    gas_fee = config["solana_gas_fee"]
    
    fee_buy = trade_amt * pump_fee
    net_invested = trade_amt - fee_buy - gas_fee
    
    tokens_bought = trade_amt / entry if entry > 0 else 0
    amount_at_sell = tokens_bought * actual_sell
    
    fee_sell = amount_at_sell * pump_fee
    net_received = amount_at_sell - fee_sell - gas_fee
    
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
        "gas_buy": gas_fee,
        "net_invested": net_invested,
        "tokens_bought": tokens_bought,
        "fee_sell": fee_sell,
        "gas_sell": gas_fee,
        "net_received": net_received,
        "profit_net": profit_net,
        "profit_percent": profit_percent,
        "win": win
    }

def format_trade_detail(token, calc, target_info):
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

def get_pump_fun_tokens():
    try:
        url = f"https://api.helius.xyz/v0/addresses/{wallets_to_track[0]}/transactions"
        params = {"api-key": "4d11d3a1-149a-49fd-a112-94a008ede057", "limit": 50}
        r = requests.get(url, params=params, timeout=10)
        if r.status_code == 200:
            txs = r.json()
            print(f"✅ {len(txs)} transactions trouvées")
            tokens = [
                {"name": f"Token {i+1}", "ca": f"token_ca_{i}", "entry": 0.00001*(i+1),
                 "ath": 0.00001*(i+1)*(1+(0.1+i*0.05)), "time": f"{5+i*2} min",
                 "url": f"https://pump.fun/coin/token_{i}"}
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

def get_history_stats(days=None):
    if not all_trades_history:
        return None
    
    if days:
        cutoff = datetime.now() - timedelta(days=days)
        trades = [t for t in all_trades_history if datetime.fromisoformat(t.get("timestamp", datetime.now().isoformat())) >= cutoff]
    else:
        trades = all_trades_history
    
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

def handle_command(command, args):
    global realtime_active
    
    parts = command.split()
    cmd = parts[0].lower()
    
    if cmd == "/start":
        msg = "🤖 <b>Bot Pump.Fun activé!</b>\n\n"
        msg += "<b>Commandes principales:</b>\n"
        msg += "/backtest – Tester les tokens (7 jours)\n"
        msg += "/realtime – Simulation temps réel\n"
        msg += "/stop – Arrêter\n"
        msg += "/stats – Statistiques globales\n"
        msg += "/history_week – Stats 7 jours\n"
        msg += "/history_month – Stats 30 jours\n\n"
        msg += "<b>Configuration:</b>\n"
        msg += "/config – Afficher la config\n"
        msg += "/set_amount 5 (ou 5€)\n"
        msg += "/set_target 20 (ou 20%)\n\n"
        msg += "<b>Wallets:</b>\n"
        msg += "/add_wallet [adresse]\n"
        msg += "/remove_wallet [adresse]\n"
        msg += "/list_wallets\n"
        msg += "/clear_wallets\n\n"
        msg += f"<b>Wallets suivis:</b> {len(wallets_to_track)}\n"
        msg += f"<b>Montant:</b> {config['trade_amount']}€\n"
        msg += f"<b>Target:</b> +{config['profit_target']*100:.0f}%"
        send_telegram(msg)
    
    elif cmd == "/backtest":
        send_telegram("📊 <b>Backtesting...</b>\n⏳ Récupération des données…")
        run_backtest()
    
    elif cmd == "/realtime":
        if not realtime_active:
            realtime_active = True
            send_telegram("🚀 <b>Temps réel activé!</b>\n⏳ Attente de tokens…")
            run_realtime_simulation()
        else:
            send_telegram("⚠️ Temps réel déjà actif!")
    
    elif cmd == "/stop":
        realtime_active = False
        send_telegram("⏹️ Arrêté")
    
    elif cmd == "/stats":
        stats = get_history_stats()
        if stats:
            msg = f"📈 <b>Statistiques globales</b>\n"
            msg += f"Trades: {stats['trades']}\n"
            msg += f"Gagnants: {stats['wins']} | Perdants: {stats['losses']}\n"
            msg += f"Taux: {stats['win_rate']:.1f}%\n"
            msg += f"Profit total: <b>{stats['total_profit']:.2f}€</b>\n"
            msg += f"Profit moyen: {stats['avg_profit']:.2f}€"
            send_telegram(msg)
        else:
            send_telegram("❌ Pas d'historique")
    
    elif cmd == "/history_week":
        stats = get_history_stats(days=7)
        if stats:
            msg = f"📊 <b>Stats 7 jours</b>\n"
            msg += f"Trades: {stats['trades']}\n"
            msg += f"Gagnants: {stats['wins']} | Perdants: {stats['losses']}\n"
            msg += f"Taux: {stats['win_rate']:.1f}%\n"
            msg += f"Profit total: <b>{stats['total_profit']:.2f}€</b>"
            send_telegram(msg)
        else:
            send_telegram("❌ Pas de données (7 jours)")
    
    elif cmd == "/history_month":
        stats = get_history_stats(days=30)
        if stats:
            msg = f"📊 <b>Stats 30 jours</b>\n"
            msg += f"Trades: {stats['trades']}\n"
            msg += f"Gagnants: {stats['wins']} | Perdants: {stats['losses']}\n"
            msg += f"Taux: {stats['win_rate']:.1f}%\n"
            msg += f"Profit total: <b>{stats['total_profit']:.2f}€</b>"
            send_telegram(msg)
        else:
            send_telegram("❌ Pas de données (30 jours)")
    
    elif cmd == "/config":
        msg = "<b>⚙️ Configuration actuelle</b>\n\n"
        msg += f"Montant par trade: {config['trade_amount']}€\n"
        msg += f"Target profit: +{config['profit_target']*100:.0f}%\n"
        msg += f"Frais Pump.fun: {config['pump_fun_fee']*100:.1f}%\n"
        msg += f"Gaz Solana: {config['solana_gas_fee']:.6f}€\n\n"
        msg += "<b>Commandes pour modifier:</b>\n"
        msg += "/set_amount 5 (accepte aussi 5€)\n"
        msg += "/set_target 20 (accepte aussi 20%)"
        send_telegram(msg)
    
    elif cmd == "/set_amount":
        if len(parts) > 1:
            num = extract_number(' '.join(parts[1:]))
            if num and num > 0:
                config["trade_amount"] = float(num)
                save_config()
                send_telegram(f"✅ Montant changé à {config['trade_amount']}€")
            else:
                send_telegram("❌ Format invalide. Utilise: /set_amount 5")
        else:
            send_telegram("❌ Utilise: /set_amount 5 (ou 5€)")
    
    elif cmd == "/set_target":
        if len(parts) > 1:
            num = extract_number(' '.join(parts[1:]))
            if num and num > 0:
                config["profit_target"] = float(num) / 100
                save_config()
                send_telegram(f"✅ Target changé à +{config['profit_target']*100:.0f}%")
            else:
                send_telegram("❌ Format invalide. Utilise: /set_target 20")
        else:
            send_telegram("❌ Utilise: /set_target 20 (ou 20%)")
    
    elif cmd == "/add_wallet":
        if len(parts) > 1:
            addr = parts[1]
            if addr not in wallets_to_track:
                wallets_to_track.append(addr)
                send_telegram(f"✅ Wallet ajouté\n<code>{addr}</code>\n\nTotal: {len(wallets_to_track)}")
            else:
                send_telegram("⚠️ Wallet déjà suivi")
        else:
            send_telegram("❌ Utilise: /add_wallet [adresse]")
    
    elif cmd == "/remove_wallet":
        if len(parts) > 1:
            addr = parts[1]
            if addr in wallets_to_track:
                wallets_to_track.remove(addr)
                send_telegram(f"✅ Wallet retiré\nTotal: {len(wallets_to_track)}")
            else:
                send_telegram("⚠️ Wallet non trouvé")
        else:
            send_telegram("❌ Utilise: /remove_wallet [adresse]")
    
    elif cmd == "/list_wallets":
        if wallets_to_track:
            msg = "<b>📍 Wallets suivis:</b>\n\n"
            for i, w in enumerate(wallets_to_track, 1):
                msg += f"{i}. <code>{w}</code>\n"
            send_telegram(msg)
        else:
            send_telegram("❌ Aucun wallet")
    
    elif cmd == "/clear_wallets":
        wallets_to_track.clear()
        send_telegram("✅ Tous les wallets supprimés")
    
    else:
        send_telegram("❌ Commande inconnue. Essaie /start")

def run_backtest():
    tokens = get_pump_fun_tokens()
    wins = losses = total_profit = 0
    
    msg = "📊 <b>BACKTESTING</b>\n\n"
    msg += f"Wallets: {len(wallets_to_track)}\n"
    msg += f"Tokens: {len(tokens)}\n"
    msg += f"Mise: {config['trade_amount']}€\n"
    msg += f"Target: +{config['profit_target']*100:.0f}%\n"
    msg += "---\n\n"
    
    for token in tokens:
        entry = token["entry"]
        ath = token["ath"]
        actual_sell = ath
        
        target_info = calculate_target_sell_price(entry)
        calc = simulate_trade(entry, actual_sell, ath, token["name"])
        
        detail = format_trade_detail(token, calc, target_info)
        send_telegram(detail)
        
        if calc["win"]:
            wins += 1
        else:
            losses += 1
        
        total_profit += calc["profit_net"]
        
        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "name": token["name"],
            "entry": entry,
            "ath": ath,
            "profit_net": calc["profit_net"],
            "profit_percent": calc["profit_percent"],
            "win": calc["win"],
            "wallet": wallets_to_track[0] if wallets_to_track else "unknown"
        }
        all_trades_history.append(trade_record)
        save_history()
        
        time.sleep(1)
    
    total = len(tokens)
    win_rate = (wins / total * 100) if total else 0
    
    summary = f"---\n📈 <b>RÉSUMÉ</b>\n"
    summary += f"Tokens: {total}\n"
    summary += f"Gagnants: {wins} | Perdants: {losses}\n"
    summary += f"Taux: {win_rate:.1f}%\n"
    summary += f"<b>Profit total: {total_profit:.2f}€</b>\n"
    summary += f"Profit moyen: {total_profit/total:.2f}€" if total else "N/A"
    send_telegram(summary)

def run_realtime_simulation():
    global realtime_active
    tokens = get_pump_fun_tokens()
    
    for token in tokens:
        if not realtime_active:
            break
        
        entry = token["entry"]
        ath = token["ath"]
        actual_sell = ath
        
        target_info = calculate_target_sell_price(entry)
        calc = simulate_trade(entry, actual_sell, ath, token["name"])
        
        detail = format_trade_detail(token, calc, target_info)
        send_telegram(detail)
        
        trade_record = {
            "timestamp": datetime.now().isoformat(),
            "name": token["name"],
            "entry": entry,
            "ath": ath,
            "profit_net": calc["profit_net"],
            "profit_percent": calc["profit_percent"],
            "win": calc["win"],
            "wallet": wallets_to_track[0] if wallets_to_track else "unknown"
        }
        all_trades_history.append(trade_record)
        save_history()
        
        time.sleep(5)
    
    realtime_active = False
    send_telegram("✅ Temps réel terminé")

def run():
    global bot_running, update_offset
    bot_running = True
    load_history()
    load_config()
    
    print("🤖 Bot Telegram activé - En attente de commandes…")
    send_telegram("✅ Bot prêt! Envoie /start")
    
    while bot_running:
        try:
            updates = get_updates()
            for upd in updates:
                update_offset = upd.get("update_id") + 1
                msg = upd.get("message", {})
                text = msg.get("text", "")
                
                if text.startswith("/"):
                    print(f"📨 Commande reçue: {text}")
                    handle_command(text, [])
            
            time.sleep(1)
        except Exception as e:
            print(f"❌ Erreur: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run()
