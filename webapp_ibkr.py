from flask import jsonify, render_template, request, redirect, url_for
from webapp_core import app, get_db, is_logged_in, get_signals
from webapp_ibkr_trades import IBKRTradesFetcher
from core_error import handle_ex
import configparser

########################################################################################
# IBKR TRADES
########################################################################################

def get_account_list():
    """Get list of configured IBKR accounts"""
    config = configparser.ConfigParser()
    config.read('config.ini')

    accounts = []
    for section in config.sections():
        # Skip non-account sections
        if section in ['users', 'inverse-etfs', 'datadog']:
            continue
        if section.startswith('bot-'):
            continue
        if section.startswith('group-'):
            continue

        # Check if this section has IBKR-specific config
        if 'host' in config[section]:
            accounts.append(section)

    return accounts

@app.route('/ibkr_trades')
def ibkr_trades():
    """Display IBKR trade history"""
    if not is_logged_in():
        return redirect(url_for('login'))

    # Get list of accounts
    accounts = get_account_list()

    # Get selected account from query params
    selected_account = request.args.get('account', accounts[0] if accounts else None)
    days_back = int(request.args.get('days', 7))

    if not selected_account:
        return render_template('ibkr_trades.html',
                             error="No IBKR accounts configured",
                             accounts=accounts)

    return render_template('ibkr_trades.html',
                         accounts=accounts,
                         selected_account=selected_account,
                         days_back=days_back)

@app.route('/api/ibkr_fills')
def api_ibkr_fills():
    """API endpoint to fetch IBKR fills"""
    if not is_logged_in():
        return jsonify({'error': 'Not logged in'}), 401

    account = request.args.get('account')
    days_back = int(request.args.get('days', 7))

    if not account:
        return jsonify({'error': 'Account parameter required'}), 400

    try:
        fetcher = IBKRTradesFetcher(account)
        fetcher.connect()

        fills = fetcher.get_fills(days_back=days_back)

        # Convert datetime objects to strings for JSON serialization
        for fill in fills:
            if fill.get('time'):
                fill['time'] = fill['time'].isoformat()

        fetcher.disconnect()

        return jsonify({'fills': fills})

    except Exception as e:
        error_msg = handle_ex(e, context=f"api_ibkr_fills_{account}", service="webapp")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ibkr_trades')
def api_ibkr_trades():
    """API endpoint to fetch IBKR trades/orders"""
    if not is_logged_in():
        return jsonify({'error': 'Not logged in'}), 401

    account = request.args.get('account')
    days_back = int(request.args.get('days', 7))

    if not account:
        return jsonify({'error': 'Account parameter required'}), 400

    try:
        fetcher = IBKRTradesFetcher(account)
        fetcher.connect()

        trades = fetcher.get_trades(days_back=days_back)

        # Convert datetime objects to strings for JSON serialization
        for trade in trades:
            if trade.get('lastFillTime'):
                trade['lastFillTime'] = trade['lastFillTime'].isoformat()

        fetcher.disconnect()

        return jsonify({'trades': trades})

    except Exception as e:
        error_msg = handle_ex(e, context=f"api_ibkr_trades_{account}", service="webapp")
        return jsonify({'error': str(e)}), 500

@app.route('/api/ibkr_slippage')
def api_ibkr_slippage():
    """API endpoint to analyze slippage between IBKR fills and our signals"""
    if not is_logged_in():
        return jsonify({'error': 'Not logged in'}), 401

    account = request.args.get('account')
    days_back = int(request.args.get('days', 7))

    if not account:
        return jsonify({'error': 'Account parameter required'}), 400

    try:
        fetcher = IBKRTradesFetcher(account)
        fetcher.connect()

        # Get fills from IBKR
        fills = fetcher.get_fills(days_back=days_back)

        # Get signals from our database
        signals = get_signals()

        # Analyze slippage
        analysis = fetcher.analyze_slippage(fills, signals)

        # Convert datetime objects to strings for JSON serialization
        for item in analysis:
            if item.get('fill_time'):
                item['fill_time'] = item['fill_time'].isoformat()
            if item.get('signal_time'):
                item['signal_time'] = item['signal_time'].isoformat()

        fetcher.disconnect()

        return jsonify({'analysis': analysis})

    except Exception as e:
        error_msg = handle_ex(e, context=f"api_ibkr_slippage_{account}", service="webapp")
        return jsonify({'error': str(e)}), 500
