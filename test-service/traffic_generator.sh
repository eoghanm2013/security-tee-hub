#!/bin/bash
echo "🚀 Generating continuous traffic to scrs-1913-test service..."
echo "Press Ctrl+C to stop"
echo ""

counter=0
while true; do
    ((counter++))
    
    # Regular requests
    curl -s http://localhost:8888/ > /dev/null 2>&1
    
    # Test endpoint with varying params
    curl -s "http://localhost:8888/test?input=test${counter}" > /dev/null 2>&1
    
    # Health check
    curl -s http://localhost:8888/health > /dev/null 2>&1
    
    # Every 10 requests, send a security test
    if [ $((counter % 10)) -eq 0 ]; then
        curl -s -A "Nessus" http://localhost:8888/admin > /dev/null 2>&1
        echo "✅ Sent $counter requests (including security test)"
    fi
    
    sleep 1
done
