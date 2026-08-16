from flask import Flask, send_from_directory, jsonify, request
import sqlite3
import os
import subprocess
import threading
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__, static_folder='../client')

DATABASE = os.path.join(os.path.dirname(__file__), 'database.db')

def get_db():
    """Establish and return a database connection."""
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Initialize the database with the required tables and columns."""
    with app.app_context():
        conn = get_db()
        # Create trades table
        conn.execute('''
            CREATE TABLE IF NOT EXISTS trades (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                date TEXT NOT NULL,
                asset TEXT NOT NULL,
                type TEXT NOT NULL,
                entry_price REAL NOT NULL,
                stoploss REAL,
                target REAL,
                exit_price REAL,
                quantity REAL NOT NULL,
                strategy TEXT,
                notes TEXT,
                profit_loss REAL,
                photo TEXT
            )
        ''')
        
        # Check and add new columns for backward compatibility
        columns = [col['name'] for col in conn.execute('PRAGMA table_info(trades)').fetchall()]
        if 'mistakes' not in columns:
            conn.execute('ALTER TABLE trades ADD COLUMN mistakes TEXT')
        if 'risk_amount' not in columns:
            conn.execute('ALTER TABLE trades ADD COLUMN risk_amount REAL')
        if 'reward_amount' not in columns:
            conn.execute('ALTER TABLE trades ADD COLUMN reward_amount REAL')
        if 'exit_date' not in columns:
            conn.execute('ALTER TABLE trades ADD COLUMN exit_date TEXT')
            
        conn.commit()
        conn.close()

# Initialize DB on startup
init_db()

@app.route('/')
def index():
    """Serve the main frontend application."""
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/<path:path>')
def static_files(path):
    """Serve static files for the frontend."""
    return send_from_directory(app.static_folder, path)

def trigger_analytics_pipeline():
    """Run the analytics pipeline in background"""
    try:
        analytics_dir = os.path.join(os.path.dirname(__file__), '..', 'TradeTrack-Analytics')
        script_path = os.path.join(analytics_dir, 'python', 'run_all.py')

        if os.path.exists(script_path):
            subprocess.run(['python3', script_path], cwd=analytics_dir, capture_output=True, timeout=300)
            print("✅ Analytics pipeline completed successfully")
        else:
            print("⚠️ Analytics script not found at", script_path)
    except subprocess.TimeoutExpired:
        print("⚠️ Analytics pipeline timeout (5 minutes)")
    except Exception as e:
        print(f"❌ Analytics error: {e}")

@app.route('/api/run-analytics', methods=['POST'])
def run_analytics():
    """Trigger analytics pipeline to run in background"""
    thread = threading.Thread(target=trigger_analytics_pipeline, daemon=True)
    thread.start()
    return jsonify({'status': 'Analytics pipeline started in background'}), 202

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Retrieve basic trading statistics and equity curve data."""
    conn = get_db()
    
    where_clauses = []
    params = []
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    strategy = request.args.get('strategy')
    asset = request.args.get('asset')
    
    if start_date:
        where_clauses.append('date >= ?')
        params.append(start_date)
    if end_date:
        where_clauses.append('date <= ?')
        params.append(end_date)
    if strategy:
        where_clauses.append('strategy = ?')
        params.append(strategy)
    if asset:
        where_clauses.append('asset = ?')
        params.append(asset)
        
    where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''
    
    trades = conn.execute(f'SELECT * FROM trades {where_sql} ORDER BY date ASC', params).fetchall()
    conn.close()
    
    total_trades = len(trades)
    
    if total_trades == 0:
        return jsonify({
            'total_profit': 0, 'win_rate': 0, 'total_trades': 0,
            'best_trade': 0, 'worst_trade': 0, 'equity_curve': [],
            'winning_trades': 0, 'losing_trades': 0, 'expectancy': 0,
            'running_peak_equity': 0, 'current_drawdown': 0, 'max_drawdown': 0
        })

    closed_trades = [t for t in trades if t['exit_price'] is not None]
    total_profit = sum(t['profit_loss'] for t in closed_trades) if closed_trades else 0
    winning_trades = [t for t in closed_trades if t['profit_loss'] > 0]
    losing_trades = [t for t in closed_trades if t['profit_loss'] <= 0]
    
    win_rate = (len(winning_trades) / len(closed_trades)) * 100 if closed_trades else 0
    best_trade = max((t['profit_loss'] for t in closed_trades), default=0)
    worst_trade = min((t['profit_loss'] for t in closed_trades), default=0)
    
    avg_win = sum(t['profit_loss'] for t in winning_trades) / len(winning_trades) if winning_trades else 0
    avg_loss = abs(sum(t['profit_loss'] for t in losing_trades)) / len(losing_trades) if losing_trades else 0
    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)
    
    equity_curve = []
    current_equity = 0
    peak_equity = 0
    max_drawdown = 0

    for t in closed_trades:
        current_equity += t['profit_loss']
        if current_equity > peak_equity:
            peak_equity = current_equity
        dd = peak_equity - current_equity
        if dd > max_drawdown:
            max_drawdown = dd
            
        equity_curve.append({'date': t['date'], 'equity': round(current_equity, 2)})
        
    current_drawdown = peak_equity - current_equity

    return jsonify({
        'total_profit': round(total_profit, 2),
        'win_rate': round(win_rate, 2),
        'total_trades': total_trades,
        'best_trade': round(best_trade, 2),
        'worst_trade': round(worst_trade, 2),
        'equity_curve': equity_curve,
        'winning_trades': len(winning_trades),
        'losing_trades': len(closed_trades) - len(winning_trades),
        'expectancy': round(expectancy, 2),
        'running_peak_equity': round(peak_equity, 2),
        'current_drawdown': round(current_drawdown, 2),
        'max_drawdown': round(max_drawdown, 2)
    })

@app.route('/api/trades', methods=['GET', 'POST'])
def handle_trades():
    """Handle creating new trades and retrieving the list of trades."""
    if request.method == 'POST':
        is_json = request.is_json
        data = request.json if is_json else request.form
        
        date = data.get('date', datetime.now().strftime("%Y-%m-%dT%H:%M"))
        asset = data.get('asset', '').upper()
        trade_type = data.get('type', 'BUY').upper()
        entry_price = float(data.get('entry_price', 0))
        stoploss = float(data.get('stoploss', 0)) if data.get('stoploss') else None
        target = float(data.get('target', 0)) if data.get('target') else None
        exit_price_raw = data.get('exit_price')
        exit_price = float(exit_price_raw) if exit_price_raw else None
        quantity = float(data.get('quantity', 0))
        strategy = data.get('strategy', 'None')
        notes = data.get('notes', '')
        mistakes = data.get('mistakes', '')
        risk_amount = float(data.get('risk_amount')) if data.get('risk_amount') else None
        reward_amount = float(data.get('reward_amount')) if data.get('reward_amount') else None
        exit_date = data.get('exit_date', None)
        
        photo_filename = None
        if not is_json and 'photo' in request.files:
            file = request.files['photo']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                unique_filename = f"{datetime.now().strftime('%Y%md%H%M%S')}_{filename}"
                upload_folder = os.path.join(app.static_folder, 'uploads')
                os.makedirs(upload_folder, exist_ok=True)
                file.save(os.path.join(upload_folder, unique_filename))
                photo_filename = f"/uploads/{unique_filename}"
        
        profit_loss = None
        if exit_price is not None:
            eth_qty = quantity / 100.0
            if trade_type == 'BUY':
                profit_loss = (exit_price - entry_price) * eth_qty
            else: # SELL
                profit_loss = (entry_price - exit_price) * eth_qty
            if not exit_date:
                exit_date = datetime.now().strftime("%Y-%m-%dT%H:%M")

        conn = get_db()
        conn.execute('''
            INSERT INTO trades (date, asset, type, entry_price, stoploss, target, exit_price, quantity, strategy, notes, profit_loss, photo, mistakes, risk_amount, reward_amount, exit_date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (date, asset, trade_type, entry_price, stoploss, target, exit_price, quantity, strategy, notes, profit_loss, photo_filename, mistakes, risk_amount, reward_amount, exit_date))
        conn.commit()
        conn.close()

        trigger_analytics_pipeline()
        return jsonify({'status': 'success', 'message': 'Trade added successfully'})
    
    else: # GET
        start_date = request.args.get('start_date')
        end_date = request.args.get('end_date')
        strategy = request.args.get('strategy')
        asset = request.args.get('asset')
        
        where_clauses = []
        params = []
        if start_date:
            where_clauses.append('date >= ?')
            params.append(start_date)
        if end_date:
            where_clauses.append('date <= ?')
            params.append(end_date)
        if strategy:
            where_clauses.append('strategy = ?')
            params.append(strategy)
        if asset:
            where_clauses.append('asset = ?')
            params.append(asset)
            
        where_sql = ('WHERE ' + ' AND '.join(where_clauses)) if where_clauses else ''
        
        conn = get_db()
        trades = conn.execute(f'SELECT * FROM trades {where_sql} ORDER BY date DESC', params).fetchall()
        trades_list = [dict(t) for t in trades]
        conn.close()
        return jsonify(trades_list)

@app.route('/api/trades/<int:trade_id>', methods=['PUT', 'DELETE'])
def update_delete_trade(trade_id):
    """Update an existing trade or delete it entirely."""
    conn = get_db()
    
    if request.method == 'DELETE':
        trade = conn.execute('SELECT photo FROM trades WHERE id = ?', (trade_id,)).fetchone()
        if trade and trade['photo']:
            photo_path = os.path.join(app.static_folder, trade['photo'].lstrip('/'))
            if os.path.exists(photo_path):
                os.remove(photo_path)
        conn.execute('DELETE FROM trades WHERE id = ?', (trade_id,))
        conn.commit()
        conn.close()
        return jsonify({'status': 'success', 'message': 'Trade deleted'})
        
    elif request.method == 'PUT':
        is_json = request.is_json
        
        if is_json and len(request.json) <= 2 and 'exit_price' in request.json:
            exit_price = float(request.json.get('exit_price', 0))
            exit_date = request.json.get('exit_date', datetime.now().strftime("%Y-%m-%dT%H:%M"))
            trade = conn.execute('SELECT type, entry_price, quantity FROM trades WHERE id = ?', (trade_id,)).fetchone()
            if not trade:
                conn.close()
                return jsonify({'status': 'error', 'message': 'Trade not found'}), 404
                
            trade_type = trade['type']
            entry_price = trade['entry_price']
            quantity = trade['quantity']

            eth_qty = quantity / 100.0
            if trade_type == 'BUY':
                profit_loss = (exit_price - entry_price) * eth_qty
            else: # SELL
                profit_loss = (entry_price - exit_price) * eth_qty

            conn.execute('''
                UPDATE trades SET exit_price = ?, profit_loss = ?, exit_date = ? WHERE id = ?
            ''', (exit_price, profit_loss, exit_date, trade_id))
            conn.commit()
            conn.close()
            trigger_analytics_pipeline()
            return jsonify({'status': 'success', 'message': 'Trade closed successfully'})
            
        else:
            data = request.json if is_json else request.form
            
            date = data.get('date', datetime.now().strftime("%Y-%m-%dT%H:%M"))
            asset = data.get('asset', '').upper()
            trade_type = data.get('type', 'BUY').upper()
            entry_price = float(data.get('entry_price', 0))
            stoploss = float(data.get('stoploss', 0)) if data.get('stoploss') else None
            target = float(data.get('target', 0)) if data.get('target') else None
            exit_price_raw = data.get('exit_price')
            exit_price = float(exit_price_raw) if exit_price_raw else None
            quantity = float(data.get('quantity', 0))
            strategy = data.get('strategy', 'None')
            notes = data.get('notes', '')
            mistakes = data.get('mistakes', '')
            risk_amount = float(data.get('risk_amount')) if data.get('risk_amount') else None
            reward_amount = float(data.get('reward_amount')) if data.get('reward_amount') else None
            exit_date = data.get('exit_date')
            
            trade = conn.execute('SELECT photo FROM trades WHERE id = ?', (trade_id,)).fetchone()
            photo_filename = trade['photo'] if trade else None

            if not is_json and 'photo' in request.files:
                file = request.files['photo']
                if file and file.filename != '':
                    if photo_filename:
                        old_photo_path = os.path.join(app.static_folder, photo_filename.lstrip('/'))
                        if os.path.exists(old_photo_path):
                            os.remove(old_photo_path)

                    filename = secure_filename(file.filename)
                    unique_filename = f"{datetime.now().strftime('%Y%md%H%M%S')}_{filename}"
                    upload_folder = os.path.join(app.static_folder, 'uploads')
                    os.makedirs(upload_folder, exist_ok=True)
                    file.save(os.path.join(upload_folder, unique_filename))
                    photo_filename = f"/uploads/{unique_filename}"
            
            profit_loss = None
            if exit_price is not None:
                eth_qty = quantity / 100.0
                if trade_type == 'BUY':
                    profit_loss = (exit_price - entry_price) * eth_qty
                else:
                    profit_loss = (entry_price - exit_price) * eth_qty
                if not exit_date:
                    exit_date = datetime.now().strftime("%Y-%m-%dT%H:%M")

            conn.execute('''
                UPDATE trades SET
                    date=?, asset=?, type=?, entry_price=?, stoploss=?, target=?,
                    exit_price=?, quantity=?, strategy=?, notes=?, profit_loss=?, photo=?,
                    mistakes=?, risk_amount=?, reward_amount=?, exit_date=?
                WHERE id=?
            ''', (date, asset, trade_type, entry_price, stoploss, target, exit_price, quantity, strategy, notes, profit_loss, photo_filename, mistakes, risk_amount, reward_amount, exit_date, trade_id))
            conn.commit()
            conn.close()
            trigger_analytics_pipeline()
            return jsonify({'status': 'success', 'message': 'Trade updated successfully'})

@app.route('/api/analytics', methods=['GET'])
def get_analytics():
    """Retrieve advanced analytics, performance metrics, and insights."""
    conn = get_db()
    
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')
    strategy = request.args.get('strategy')
    asset = request.args.get('asset')
    
    where_clauses = ['exit_price IS NOT NULL']
    params = []
    
    if start_date:
        where_clauses.append('date >= ?')
        params.append(start_date)
    if end_date:
        where_clauses.append('date <= ?')
        params.append(end_date)
    if strategy:
        where_clauses.append('strategy = ?')
        params.append(strategy)
    if asset:
        where_clauses.append('asset = ?')
        params.append(asset)
        
    where_sql = 'WHERE ' + ' AND '.join(where_clauses)
    trades = conn.execute(f'SELECT * FROM trades {where_sql} ORDER BY date ASC', params).fetchall()
    conn.close()

    if not trades:
        return jsonify({'status': 'error', 'message': 'No closed trades available for analytics.'})

    profits = []
    losses = []
    equity_curve = []
    
    current_equity = 0
    peak_equity = 0
    max_drawdown = 0

    current_streak_type = None
    current_streak = 0
    max_win_streak = 0
    max_loss_streak = 0

    total_risk_amount = 0
    total_rr_ratio = 0
    risk_trades_count = 0

    asset_data = {}
    strategy_data = {}
    day_of_week_data = {i: {'trades': 0, 'profit': 0, 'wins': 0} for i in range(7)}
    hour_data = {i: {'trades': 0, 'profit': 0, 'wins': 0} for i in range(24)}
    daily_pnl = {}
    
    session_data = {
        'Morning': {'trades': 0, 'profit': 0, 'wins': 0},
        'Afternoon': {'trades': 0, 'profit': 0, 'wins': 0},
        'Night': {'trades': 0, 'profit': 0, 'wins': 0}
    }
    
    mistake_data = {}
    duration_vs_profit = []
    position_size_vs_outcome = []
    
    for t in trades:
        pnl = t['profit_loss']
        is_win = pnl > 0
        is_loss = pnl < 0
        
        if is_win:
            profits.append(pnl)
            if current_streak_type == 'WIN':
                current_streak += 1
            else:
                current_streak_type = 'WIN'
                current_streak = 1
            max_win_streak = max(max_win_streak, current_streak)
        elif is_loss:
            losses.append(pnl)
            if current_streak_type == 'LOSS':
                current_streak += 1
            else:
                current_streak_type = 'LOSS'
                current_streak = 1
            max_loss_streak = max(max_loss_streak, current_streak)
        else:
            current_streak_type = None
            current_streak = 0

        current_equity += pnl
        equity_curve.append({'date': t['date'], 'equity': current_equity})
        
        if current_equity > peak_equity:
            peak_equity = current_equity
        
        drawdown = peak_equity - current_equity
        if drawdown > max_drawdown:
            max_drawdown = drawdown

        # Risk & RR
        if t['risk_amount']:
            risk_amount = t['risk_amount']
            total_risk_amount += risk_amount
            if risk_amount > 0 and t['reward_amount']:
                total_rr_ratio += (t['reward_amount'] / risk_amount)
            elif risk_amount > 0:
                total_rr_ratio += (abs(pnl) / risk_amount)
            risk_trades_count += 1
        else:
            eth_qty = t['quantity'] / 100.0
            if t['stoploss'] and t['entry_price'] and t['stoploss'] > 0:
                risk_points = abs(t['entry_price'] - t['stoploss'])
                risk_amount = risk_points * eth_qty
                total_risk_amount += risk_amount
                
                if risk_amount > 0 and pnl > 0:
                    total_rr_ratio += (pnl / risk_amount)
                elif risk_amount > 0 and pnl < 0:
                    total_rr_ratio += (pnl / risk_amount)
                    
                risk_trades_count += 1

        asset = t['asset']
        if asset not in asset_data:
            asset_data[asset] = {'total': 0, 'wins': 0, 'profit': 0, 'profits': [], 'losses': []}
        asset_data[asset]['total'] += 1
        asset_data[asset]['profit'] += pnl
        if is_win:
            asset_data[asset]['wins'] += 1
            asset_data[asset]['profits'].append(pnl)
        elif is_loss:
            asset_data[asset]['losses'].append(pnl)

        strat = t['strategy']
        if strat not in strategy_data:
            strategy_data[strat] = {'total': 0, 'wins': 0, 'profit': 0}
        strategy_data[strat]['total'] += 1
        strategy_data[strat]['profit'] += pnl
        if is_win: strategy_data[strat]['wins'] += 1

        try:
            dt = datetime.strptime(t['date'], "%Y-%m-%dT%H:%M")
        except:
            try:
                dt = datetime.strptime(t['date'][:16], "%Y-%m-%dT%H:%M")
            except:
                dt = datetime.now()

        dow = dt.weekday()
        hr = dt.hour
        
        session = 'Night'
        if 6 <= hr < 12:
            session = 'Morning'
        elif 12 <= hr < 18:
            session = 'Afternoon'
            
        session_data[session]['trades'] += 1
        session_data[session]['profit'] += pnl
        if is_win: session_data[session]['wins'] += 1
        
        day_of_week_data[dow]['trades'] += 1
        day_of_week_data[dow]['profit'] += pnl
        if is_win: day_of_week_data[dow]['wins'] += 1
        
        hour_data[hr]['trades'] += 1
        hour_data[hr]['profit'] += pnl
        if is_win: hour_data[hr]['wins'] += 1

        day_str = t['date'].split('T')[0]
        if day_str not in daily_pnl:
            daily_pnl[day_str] = {'trades': 0, 'profit': 0}
        daily_pnl[day_str]['trades'] += 1
        daily_pnl[day_str]['profit'] += pnl
        
        if 'mistakes' in t.keys() and t['mistakes']:
            tags = [m.strip() for m in t['mistakes'].split(',')]
            for m in tags:
                if m:
                    mistake_data[m] = mistake_data.get(m, 0) + 1
                    
        duration_minutes = None
        if 'exit_date' in t.keys() and t['exit_date']:
            try:
                exit_dt = datetime.strptime(t['exit_date'], "%Y-%m-%dT%H:%M")
                duration_minutes = (exit_dt - dt).total_seconds() / 60
            except:
                pass
        
        duration_vs_profit.append({
            'duration_minutes': duration_minutes,
            'profit': pnl
        })
        
        position_size_vs_outcome.append({
            'quantity': t['quantity'],
            'profit': pnl
        })

    total_trades = len(trades)
    total_wins = len(profits)
    total_losses = len(losses)
    
    gross_profit = sum(profits)
    gross_loss = abs(sum(losses))
    total_net = gross_profit - gross_loss
    
    win_rate = (total_wins / total_trades) * 100 if total_trades > 0 else 0
    avg_win = gross_profit / total_wins if total_wins > 0 else 0
    avg_loss = gross_loss / total_losses if total_losses > 0 else 0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else (gross_profit if gross_profit > 0 else 0)
    
    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * avg_loss)
    
    avg_risk = total_risk_amount / risk_trades_count if risk_trades_count > 0 else 0
    avg_rr = total_rr_ratio / risk_trades_count if risk_trades_count > 0 else 0
    
    current_win_streak = current_streak if current_streak_type == 'WIN' else 0
    current_loss_streak = current_streak if current_streak_type == 'LOSS' else 0

    formatted_assets = []
    for a, d in asset_data.items():
        aw = sum(d['profits'])/len(d['profits']) if len(d['profits']) > 0 else 0
        al = abs(sum(d['losses']))/len(d['losses']) if len(d['losses']) > 0 else 0
        pf = (sum(d['profits']) / abs(sum(d['losses']))) if abs(sum(d['losses'])) > 0 else sum(d['profits'])
        formatted_assets.append({
            'asset': a,
            'total': d['total'],
            'win_rate': (d['wins'] / d['total']) * 100 if d['total'] > 0 else 0,
            'total_net': d['profit'],
            'avg_win': aw,
            'avg_loss': al,
            'profit_factor': pf
        })

    formatted_strats = []
    for s, d in strategy_data.items():
        formatted_strats.append({
            'strategy': s,
            'total': d['total'],
            'win_rate': (d['wins'] / d['total']) * 100 if d['total'] > 0 else 0,
            'profit': d['profit']
        })

    insights = []
    dow_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    best_dow = max(day_of_week_data.items(), key=lambda x: x[1]['profit'])
    if best_dow[1]['profit'] > 0:
        insights.append(f"Most profitable day of the week is {dow_names[best_dow[0]]} (${best_dow[1]['profit']:.2f}).")

    if formatted_assets:
        best_asset = max(formatted_assets, key=lambda x: x['total_net'])
        if best_asset['total_net'] > 0:
            insights.append(f"{best_asset['asset']} is your best performing asset (${best_asset['total_net']:.2f}).")
        
    if avg_loss > avg_win * 1.5 and avg_win > 0:
        insights.append("Warning: Your average loss is significantly larger than your average win. Consider tighter stop losses.")
        
    overtrading_days = [d for d, val in daily_pnl.items() if val['trades'] > 5]
    if overtrading_days:
        insights.append(f"Overtrading detected on {len(overtrading_days)} days (more than 5 trades). Ensure you are waiting for quality setups.")
        
    if max_loss_streak >= 4:
        insights.append(f"You had a losing streak of {max_loss_streak} trades. Have a rule to walk away after consecutive losses.")
        
    avg_qty = sum(t['quantity'] for t in trades)/len(trades) if trades else 0
    large_size_losses = [x for x in position_size_vs_outcome if x['profit'] < 0 and x['quantity'] > avg_qty]
    if len(large_size_losses) > len(losses) * 0.5 and len(losses) > 0:
        insights.append("Warning: Majority of your losses occur with above-average position sizes.")
        
    bad_overtrading_days = [d for d, val in daily_pnl.items() if val['trades'] >= 3 and val['profit'] < 0]
    if bad_overtrading_days:
        insights.append(f"You lost money on {len(bad_overtrading_days)} days where you took 3 or more trades. Avoid forcing trades.")

    return jsonify({
        'status': 'success',
        'performance': {
            'total_trades': total_trades,
            'win_rate': round(win_rate, 2),
            'total_net': round(total_net, 2),
            'gross_profit': round(gross_profit, 2),
            'gross_loss': round(gross_loss, 2),
            'avg_profit_per_trade': round(total_net / total_trades, 2) if total_trades else 0,
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'largest_win': round(max(profits), 2) if profits else 0,
            'largest_loss': round(min(losses), 2) if losses else 0,
            'profit_factor': round(profit_factor, 2),
            'expectancy': round(expectancy, 2)
        },
        'equity': {
            'curve': equity_curve,
            'max_drawdown': round(max_drawdown, 2),
            'running_peak_equity': round(peak_equity, 2),
            'current_drawdown': round(peak_equity - current_equity, 2)
        },
        'risk': {
            'current_win_streak': current_win_streak,
            'current_loss_streak': current_loss_streak,
            'max_win_streak': max_win_streak,
            'max_loss_streak': max_loss_streak,
            'avg_risk_per_trade': round(avg_risk, 2),
            'avg_rr_ratio': round(avg_rr, 2)
        },
        'by_asset': formatted_assets,
        'by_strategy': formatted_strats,
        'by_day_of_week': {dow_names[k]: v for k, v in day_of_week_data.items()},
        'by_hour': hour_data,
        'session_classification': session_data,
        'daily_pnl': daily_pnl,
        'mistake_summary': mistake_data,
        'advanced': {
            'duration_vs_profit': duration_vs_profit,
            'position_size_vs_outcome': position_size_vs_outcome,
            'cumulative_profit': current_equity
        },
        'insights': insights,
        'distribution': {
            'profits': profits,
            'losses': losses
        }
    })

if __name__ == '__main__':
    app.run(debug=True, port=5001)
