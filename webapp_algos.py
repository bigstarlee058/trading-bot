import os
import glob
from flask import render_template, request, redirect, url_for
from webapp_core import app, is_logged_in
from datetime import datetime
import markdown

# Path to trading strategies directory
STRATEGIES_DIR = os.path.join(os.path.dirname(__file__), '..', 'trading-strategies')

########################################################################################
# ALGORITHMS STATUS
########################################################################################
@app.route('/algorithms')
def algorithms():
    if not is_logged_in():
        return redirect(url_for('login'))

    # Get all performance*.md files
    pattern = os.path.join(STRATEGIES_DIR, 'performance*.md')
    files = glob.glob(pattern)

    # Sort by modification time (newest first)
    files.sort(key=os.path.getmtime, reverse=True)

    # Extract just the filename and last modified time
    reports = []
    for filepath in files:
        filename = os.path.basename(filepath)
        mtime = datetime.fromtimestamp(os.path.getmtime(filepath))
        reports.append({
            'filename': filename,
            'modified': mtime
        })

    # Check if a specific report is selected
    selected = request.args.get('report')
    report_content = None
    report_html = None

    if selected:
        # Security: only allow reading files from the strategies directory
        real_strategies = os.path.realpath(STRATEGIES_DIR)
        selected_path = os.path.realpath(os.path.join(STRATEGIES_DIR, selected))

        # Ensure the file is within the strategies directory
        if os.path.exists(selected_path) and selected_path.startswith(real_strategies + os.sep):
            try:
                with open(selected_path, 'r') as f:
                    report_content = f.read()
                    # Convert markdown to HTML with tables extension
                    report_html = markdown.markdown(report_content, extensions=['tables', 'fenced_code'])
            except Exception as e:
                app.logger.error(f"Error reading report {selected}: {e}")

    return render_template('algos.html',
                          reports=reports,
                          selected=selected,
                          report_html=report_html)
