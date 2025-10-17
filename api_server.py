#!/usr/bin/env python3
"""
API Server for exposing sensor data via REST and WebSocket
Runs alongside graph_faster.py to provide remote access to sensor readings
"""
import json
import time
from datetime import datetime
from threading import Thread, Lock
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_sock import Sock

app = Flask(__name__)
CORS(app)  # Enable CORS for EC2 dashboard access
sock = Sock(app)

# Shared data structure - will be updated by graph_faster.py
shared_data = {
    'current': {
        'timestamp': 0,
        'cpm_h': 0.0,
        'cpm_l': 0.0,
        'emf': 0.0,
        'rf': 0.0,
        'ef': 0.0,
        'altitude': 0.0,
        'latitude': 0.0,
        'longitude': 0.0,
        'velocity': 0.0
    },
    'history': {
        'timestamps': [],
        'cpm_h': [],
        'cpm_l': [],
        'emf': [],
        'rf': [],
        'ef': [],
        'altitude': [],
        'velocity': []
    }
}
data_lock = Lock()

# WebSocket clients
ws_clients = set()
ws_lock = Lock()


def update_shared_data(timestamp, cpm_h, cpm_l, emf, rf, ef, altitude, latitude, longitude, velocity):
    """Called by graph_faster.py to update sensor data"""
    with data_lock:
        # Update current values
        shared_data['current'] = {
            'timestamp': timestamp,
            'cpm_h': cpm_h,
            'cpm_l': cpm_l,
            'emf': emf,
            'rf': rf,
            'ef': ef,
            'altitude': altitude,
            'latitude': latitude,
            'longitude': longitude,
            'velocity': velocity
        }

        # Update history (keep last 1000 points)
        shared_data['history']['timestamps'].append(timestamp)
        shared_data['history']['cpm_h'].append(cpm_h)
        shared_data['history']['cpm_l'].append(cpm_l)
        shared_data['history']['emf'].append(emf)
        shared_data['history']['rf'].append(rf)
        shared_data['history']['ef'].append(ef)
        shared_data['history']['altitude'].append(altitude)
        shared_data['history']['velocity'].append(velocity)

        # Trim to last 1000 points
        max_points = 1000
        for key in shared_data['history']:
            if len(shared_data['history'][key]) > max_points:
                shared_data['history'][key] = shared_data['history'][key][-max_points:]

    # Broadcast to WebSocket clients
    broadcast_to_websockets(shared_data['current'])


def broadcast_to_websockets(data):
    """Send data to all connected WebSocket clients"""
    with ws_lock:
        disconnected = set()
        for ws in ws_clients:
            try:
                ws.send(json.dumps(data))
            except Exception:
                disconnected.add(ws)

        # Remove disconnected clients
        ws_clients.difference_update(disconnected)


# REST API Endpoints

@app.route('/api/health', methods=['GET'])
def health():
    """Health check endpoint"""
    return jsonify({'status': 'ok', 'timestamp': time.time()})


@app.route('/api/current', methods=['GET'])
def get_current():
    """Get current sensor readings"""
    with data_lock:
        return jsonify(shared_data['current'])


@app.route('/api/history', methods=['GET'])
def get_history():
    """Get historical sensor data
    Query params:
    - minutes: number of minutes of history to return (default: 5)
    - points: max number of data points to return (default: 1000)
    """
    minutes = request.args.get('minutes', default=5, type=int)
    max_points = request.args.get('points', default=1000, type=int)

    with data_lock:
        history = shared_data['history'].copy()

    # Filter by time window
    if history['timestamps']:
        cutoff_time = time.time() - (minutes * 60)

        # Find index of first timestamp within window
        start_idx = 0
        for i, ts in enumerate(history['timestamps']):
            if ts >= cutoff_time:
                start_idx = i
                break

        # Slice all arrays from start_idx
        filtered_history = {
            key: values[start_idx:] for key, values in history.items()
        }

        # Downsample if too many points
        if len(filtered_history['timestamps']) > max_points:
            step = len(filtered_history['timestamps']) // max_points
            filtered_history = {
                key: values[::step] for key, values in filtered_history.items()
            }

        return jsonify(filtered_history)

    return jsonify(history)


@app.route('/api/stats', methods=['GET'])
def get_stats():
    """Get statistical summary of recent data"""
    with data_lock:
        history = shared_data['history'].copy()

    if not history['timestamps']:
        return jsonify({'error': 'No data available'}), 404

    def calc_stats(values):
        if not values:
            return {'min': 0, 'max': 0, 'avg': 0}
        return {
            'min': min(values),
            'max': max(values),
            'avg': sum(values) / len(values)
        }

    stats = {
        'cpm_h': calc_stats(history['cpm_h']),
        'cpm_l': calc_stats(history['cpm_l']),
        'emf': calc_stats(history['emf']),
        'rf': calc_stats(history['rf']),
        'ef': calc_stats(history['ef']),
        'altitude': calc_stats(history['altitude']),
        'velocity': calc_stats(history['velocity']),
        'data_points': len(history['timestamps']),
        'time_range_seconds': history['timestamps'][-1] - history['timestamps'][0] if len(history['timestamps']) > 1 else 0
    }

    return jsonify(stats)


# WebSocket endpoint
@sock.route('/ws/stream')
def stream_websocket(ws):
    """WebSocket endpoint for real-time sensor data streaming"""
    with ws_lock:
        ws_clients.add(ws)

    print(f"WebSocket client connected. Total clients: {len(ws_clients)}")

    try:
        # Send current data immediately on connection
        with data_lock:
            ws.send(json.dumps(shared_data['current']))

        # Keep connection alive and handle incoming messages
        while True:
            message = ws.receive(timeout=30)  # 30s timeout
            if message:
                # Echo back or handle commands if needed
                pass
    except Exception as e:
        print(f"WebSocket error: {e}")
    finally:
        with ws_lock:
            ws_clients.discard(ws)
        print(f"WebSocket client disconnected. Total clients: {len(ws_clients)}")


def run_server(host='0.0.0.0', port=5000):
    """Run the Flask server"""
    print(f"Starting API server on {host}:{port}")
    print(f"REST API endpoints:")
    print(f"  GET  http://{host}:{port}/api/health")
    print(f"  GET  http://{host}:{port}/api/current")
    print(f"  GET  http://{host}:{port}/api/history?minutes=5&points=1000")
    print(f"  GET  http://{host}:{port}/api/stats")
    print(f"WebSocket endpoint:")
    print(f"  WS   ws://{host}:{port}/ws/stream")

    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == '__main__':
    # Run standalone for testing
    run_server()
