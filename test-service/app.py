"""
SCRS-1913 Test Service
Simple Flask app to test Threat Protection initialization
"""
from flask import Flask, request, jsonify
from dotenv import load_dotenv
import os

# Load environment variables from .env
load_dotenv()

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        'status': 'running',
        'service': os.getenv('DD_SERVICE', 'unknown'),
        'env': os.getenv('DD_ENV', 'unknown'),
        'appsec_enabled': os.getenv('DD_APPSEC_ENABLED', 'not set'),
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy'})

@app.route('/test')
def test():
    """Test endpoint for triggering security rules"""
    user_input = request.args.get('input', '')
    return jsonify({
        'message': 'Test endpoint',
        'user_input': user_input,
        'appsec_status': os.getenv('DD_APPSEC_ENABLED', 'not set')
    })

@app.route('/admin')
def admin():
    """Endpoint that might trigger security detection"""
    return jsonify({'message': 'Admin endpoint'})

if __name__ == '__main__':
    print("=" * 60)
    print("SCRS-1913 Test Service Starting")
    print("=" * 60)
    print(f"DD_SERVICE: {os.getenv('DD_SERVICE', 'NOT SET')}")
    print(f"DD_ENV: {os.getenv('DD_ENV', 'NOT SET')}")
    print(f"DD_APPSEC_ENABLED: {os.getenv('DD_APPSEC_ENABLED', 'NOT SET')}")
    print(f"DD_REMOTE_CONFIGURATION_ENABLED: {os.getenv('DD_REMOTE_CONFIGURATION_ENABLED', 'NOT SET')}")
    print("=" * 60)
    
    port = int(os.getenv('PORT', 8888))
    app.run(host='0.0.0.0', port=port, debug=False)

