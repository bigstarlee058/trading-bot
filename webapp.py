import hashlib
import logging
from logging.handlers import RotatingFileHandler
from flask import redirect, render_template, request, session, url_for
from webapp_core import app, get_db, is_logged_in, USER_CREDENTIALS, save_signal, r, p, process_signal_retries
import threading
import webapp_reports
import webapp_dashboard
import webapp_stocks
import webapp_algos
import webapp_ibkr
from datadog import statsd
from core_error import handle_ex, send_sms_alert
import os
import datetime

# Set up logging
log_dir = 'logs'
if not os.path.exists(log_dir):
    os.makedirs(log_dir)

file_handler = RotatingFileHandler(
    os.path.join(log_dir, 'webapp.log'),
    maxBytes=1024 * 1024,  # 1MB
    backupCount=10
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
))
file_handler.setLevel(logging.INFO)
app.logger.addHandler(file_handler)
app.logger.setLevel(logging.INFO)
app.logger.info('Webapp startup')

# Background thread to process signal retries
def run_retry_processor():
    """Start a background thread to process signal retries every 5 seconds"""
    def process_retries_wrapper():
        with app.app_context():
            try:
                process_signal_retries()
            except Exception as e:
                error_text = handle_ex(e, context="process_retries", service="webapp")
                app.logger.error(error_text)
        # Schedule next run
        timer = threading.Timer(5.0, process_retries_wrapper)
        timer.daemon = True
        timer.start()

    # Start the first run after 5 seconds
    timer = threading.Timer(5.0, process_retries_wrapper)
    timer.daemon = True
    timer.start()
    app.logger.info('Started retry processor thread')

# Start the retry processor
run_retry_processor()

# Track which alerts have been sent today to avoid duplicates
signal_alerts_sent = {'date': None, '16:30': set(), '17:00': set()}
order_cancel_done = {'date': None}

def check_expected_signals():
    """Check if expected SOXL and TQQQ signals have arrived after market close"""
    global signal_alerts_sent

    now = datetime.datetime.now()
    current_date = now.date()
    current_time = now.strftime('%H:%M')

    # Skip on weekends
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return

    # Reset alerts tracker if it's a new day
    if signal_alerts_sent['date'] != current_date:
        signal_alerts_sent = {'date': current_date, '16:30': set(), '17:00': set()}

    # Check at 4:30pm and 5pm Eastern
    alert_time = None
    if current_time == '16:30':
        alert_time = '16:30'
        alert_label = '4:30pm'
    elif current_time == '17:00':
        alert_time = '17:00'
        alert_label = '5pm'

    if not alert_time:
        return

    # Query for today's signals
    try:
        db = get_db()
        cursor = db.cursor()

        # Check for SOXL and TQQQ signals received today
        expected_tickers = ['SOXL', 'TQQQ']
        missing_signals = []

        for ticker in expected_tickers:
            # Skip if we already alerted for this ticker at this time
            if ticker in signal_alerts_sent[alert_time]:
                continue

            cursor.execute("""
                SELECT COUNT(*) as count
                FROM signals
                WHERE ticker = ?
                AND DATE(timestamp) = DATE('now', 'localtime')
            """, (ticker,))

            result = cursor.fetchone()
            if result['count'] == 0:
                missing_signals.append(ticker)
                signal_alerts_sent[alert_time].add(ticker)

        # Send SMS alert if any signals are missing
        if missing_signals:
            severity = 'CRITICAL' if alert_time == '17:00' else 'WARNING'
            message = f"{severity}: Missing {alert_label} signals: {', '.join(missing_signals)}"
            if alert_time == '17:00':
                message += " (NQ futures trades may be blocked)"

            app.logger.error(message)
            send_sms_alert(message)

    except Exception as e:
        error_text = handle_ex(e, context="check_expected_signals", service="webapp")
        app.logger.error(error_text)

def cancel_pending_orders():
    """Cancel all pending orders at 10pm after hours close"""
    global order_cancel_done

    now = datetime.datetime.now()
    current_date = now.date()
    current_time = now.strftime('%H:%M')

    # Skip on weekends
    if now.weekday() >= 5:  # Saturday = 5, Sunday = 6
        return

    # Reset cancellation tracker if it's a new day
    if order_cancel_done['date'] != current_date:
        order_cancel_done = {'date': current_date}

    # Run at 10pm Eastern (22:00)
    if current_time != '22:00':
        return

    # Check if we already ran today
    if order_cancel_done.get('done', False):
        return

    try:
        import subprocess
        app.logger.info("Running 10pm order cancellation...")

        # Run cancel-all-orders script with --force flag (skip confirmation)
        result = subprocess.run(
            ['python3', 'cancel-all-orders', '--force'],
            cwd=os.path.dirname(os.path.abspath(__file__)),
            capture_output=True,
            text=True,
            timeout=120
        )

        if result.returncode == 0:
            app.logger.info(f"Order cancellation completed: {result.stdout}")
            # Send SMS if any orders were cancelled
            if 'TOTAL: Cancelled' in result.stdout and 'Cancelled 0 order' not in result.stdout:
                # Extract the total from output
                import re
                match = re.search(r'TOTAL: Cancelled (\d+) order', result.stdout)
                if match:
                    count = match.group(1)
                    send_sms_alert(f"10pm order cleanup: Cancelled {count} pending order(s)")
        else:
            app.logger.error(f"Order cancellation failed: {result.stderr}")
            send_sms_alert(f"ERROR: 10pm order cleanup failed")

        order_cancel_done['done'] = True

    except subprocess.TimeoutExpired:
        app.logger.error("Order cancellation timed out after 120 seconds")
        send_sms_alert("ERROR: 10pm order cleanup timed out")
    except Exception as e:
        error_text = handle_ex(e, context="cancel_pending_orders", service="webapp")
        app.logger.error(error_text)

def run_signal_monitor():
    """Start a background thread to monitor for expected signals and cancel orders at 10pm"""
    def monitor_wrapper():
        with app.app_context():
            try:
                check_expected_signals()
                cancel_pending_orders()
            except Exception as e:
                error_text = handle_ex(e, context="signal_monitor", service="webapp")
                app.logger.error(error_text)
        # Schedule next run in 60 seconds
        timer = threading.Timer(60.0, monitor_wrapper)
        timer.daemon = True
        timer.start()

    # Start the first run after 60 seconds
    timer = threading.Timer(60.0, monitor_wrapper)
    timer.daemon = True
    timer.start()
    app.logger.info('Started signal monitor thread (checks signals + 10pm order cleanup)')

# Start the signal monitor
run_signal_monitor()

# New login route
@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in USER_CREDENTIALS and USER_CREDENTIALS[username] == password:
            session['logged_in'] = True
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Invalid credentials')
    return render_template('login.html')

# New logout route
@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))

# Modify existing routes to require login
@app.route('/')
def index():
    if not is_logged_in():
        return redirect(url_for('login'))
    return redirect(url_for('dashboard'))

# POST /webhook
@app.post("/webhook")
def webhook():
    try:
        # Check if request has the correct content type
        if not request.is_json:
            # Non-JSON request - this is expected sometimes, just return OK
            app.logger.info("Received non-JSON request to webhook endpoint")
            return "ok", 200
            
        # Get the JSON data from the request
        data = request.get_json()
        if not data:
            # Empty JSON is still an issue worth noting
            app.logger.warning("Received empty JSON data")
            return "No data received", 400

        # Save the signal and process it
        save_signal(data)
        return "ok"
    except Exception as e:
        error_text = handle_ex(e, context="webhook", service="webapp")
        app.logger.error(error_text)
        return str(e), 500

# GET /health
@app.get("/health")
def health():
    try:
        # send a message to the redis channel to test connectivity
        r.publish('tradingview', 'health check')
        
        # wait for response
        for i in range(10):
            message = p.get_message()
            if message and message['type'] == 'message' and message['data'] == b'ok':
                return "ok"
        
        raise Exception("Health check failed - no response from broker")
    except Exception as e:
        error_text = handle_ex(e, context="health_check", service="webapp")
        app.logger.error(error_text)
        return str(e), 500

if __name__ == '__main__':
    # Note: When running directly (not via Gunicorn), the retry processor is already started above
    app.run(debug=False)
