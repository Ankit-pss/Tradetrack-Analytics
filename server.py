#!/usr/bin/env python3
"""
TradeTrack Analytics Server
Continuously runs the analytics pipeline and serves the dashboard
"""

from flask import Flask, send_from_directory, jsonify
import subprocess
import os
import threading
import time
from datetime import datetime

ANALYTICS_DIR = os.path.join(os.path.dirname(__file__), 'TradeTrack-Analytics')
DASHBOARD_DIR = os.path.join(ANALYTICS_DIR, 'dashboard')

app = Flask(__name__, static_folder=DASHBOARD_DIR)

SCRIPT_PATH = os.path.join(ANALYTICS_DIR, 'python', 'run_all.py')
DASHBOARD_PATH = os.path.join(DASHBOARD_DIR, 'index.html')

pipeline_running = False
last_run = None
next_run = None

def run_pipeline():
    """Execute the analytics pipeline"""
    global pipeline_running, last_run, next_run

    if pipeline_running:
        print("⏳ Pipeline already running...")
        return

    pipeline_running = True
    print(f"\n🚀 Starting analytics pipeline at {datetime.now().strftime('%H:%M:%S')}")

    try:
        result = subprocess.run(
            ['python3', SCRIPT_PATH],
            cwd=ANALYTICS_DIR,
            capture_output=True,
            text=True,
            timeout=300
        )

        last_run = datetime.now()

        if result.returncode == 0:
            print(f"✅ Pipeline completed successfully at {last_run.strftime('%H:%M:%S')}")
        else:
            print(f"❌ Pipeline error: {result.stderr}")

    except subprocess.TimeoutExpired:
        print("⚠️ Pipeline timeout (5 minutes)")
    except Exception as e:
        print(f"❌ Error running pipeline: {e}")
    finally:
        pipeline_running = False
        next_run = datetime.now()

def pipeline_scheduler():
    """Background thread: run pipeline every 30 seconds"""
    while True:
        time.sleep(30)
        run_pipeline()

# Start scheduler thread on startup
scheduler_thread = threading.Thread(target=pipeline_scheduler, daemon=True)
scheduler_thread.start()

# Initial run
print("🔧 Initializing analytics platform...")
run_pipeline()

@app.route('/')
def serve_dashboard():
    """Serve the analytics dashboard"""
    if not os.path.exists(DASHBOARD_PATH):
        return jsonify({'error': 'Dashboard not found. Run pipeline first.'}), 404
    return send_from_directory(DASHBOARD_DIR, 'index.html')

@app.route('/<path:path>')
def serve_static(path):
    """Serve static files (CSS, JS, data)"""
    return send_from_directory(DASHBOARD_DIR, path)

@app.route('/api/status', methods=['GET'])
def get_status():
    """Get pipeline status"""
    return jsonify({
        'pipeline_running': pipeline_running,
        'last_run': last_run.isoformat() if last_run else None,
        'next_run': next_run.isoformat() if next_run else None
    })

@app.route('/api/run', methods=['POST'])
def trigger_pipeline():
    """Manually trigger the pipeline"""
    if pipeline_running:
        return jsonify({'status': 'Pipeline already running'}), 202

    thread = threading.Thread(target=run_pipeline, daemon=True)
    thread.start()
    return jsonify({'status': 'Pipeline triggered'}), 202

if __name__ == '__main__':
    print("\n" + "="*60)
    print("📊 TradeTrack Analytics Server")
    print("="*60)
    print(f"Dashboard: http://127.0.0.1:5002")
    print(f"API Status: http://127.0.0.1:5002/api/status")
    print(f"Trigger Pipeline: POST http://127.0.0.1:5002/api/run")
    print("="*60 + "\n")

    app.run(debug=False, port=5002, use_reloader=False)
