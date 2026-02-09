#!/bin/bash
echo "🔒 Sending Security Attack Patterns to trigger ASM..."
echo ""

# 1. SQL Injection attempts
echo "1. SQL Injection attacks..."
curl -s "http://localhost:8888/test?input=' OR '1'='1" > /dev/null
curl -s "http://localhost:8888/test?input=1' UNION SELECT * FROM users--" > /dev/null
curl -s "http://localhost:8888/test?input=admin'--" > /dev/null
echo "   ✅ Sent 3 SQL injection attempts"

# 2. Path Traversal attempts
echo "2. Path Traversal attacks..."
curl -s "http://localhost:8888/test?input=../../etc/passwd" > /dev/null
curl -s "http://localhost:8888/test?input=../../../etc/shadow" > /dev/null
curl -s "http://localhost:8888/test?input=....//....//....//etc/passwd" > /dev/null
echo "   ✅ Sent 3 path traversal attempts"

# 3. XSS attempts
echo "3. Cross-Site Scripting (XSS) attacks..."
curl -s "http://localhost:8888/test?input=<script>alert('xss')</script>" > /dev/null
curl -s "http://localhost:8888/test?input=<img src=x onerror=alert(1)>" > /dev/null
curl -s "http://localhost:8888/test?input=javascript:alert(document.cookie)" > /dev/null
echo "   ✅ Sent 3 XSS attempts"

# 4. Command Injection
echo "4. Command Injection attacks..."
curl -s "http://localhost:8888/test?input=; cat /etc/passwd" > /dev/null
curl -s "http://localhost:8888/test?input=| ls -la" > /dev/null
curl -s "http://localhost:8888/test?input=\`whoami\`" > /dev/null
echo "   ✅ Sent 3 command injection attempts"

# 5. Security Scanner User-Agents
echo "5. Security Scanner detections..."
curl -s -A "Nessus" http://localhost:8888/ > /dev/null
curl -s -A "Acunetix" http://localhost:8888/ > /dev/null
curl -s -A "Nikto" http://localhost:8888/ > /dev/null
curl -s -A "sqlmap" http://localhost:8888/ > /dev/null
curl -s -A "Burp Suite" http://localhost:8888/ > /dev/null
echo "   ✅ Sent 5 scanner detections"

# 6. LDAP Injection
echo "6. LDAP Injection attacks..."
curl -s "http://localhost:8888/test?input=*)(uid=*" > /dev/null
curl -s "http://localhost:8888/test?input=admin)(&(password=*))" > /dev/null
echo "   ✅ Sent 2 LDAP injection attempts"

# 7. Server-Side Request Forgery (SSRF)
echo "7. SSRF attempts..."
curl -s "http://localhost:8888/test?input=http://169.254.169.254/latest/meta-data/" > /dev/null
curl -s "http://localhost:8888/test?input=http://localhost:8126/telemetry" > /dev/null
echo "   ✅ Sent 2 SSRF attempts"

# 8. Shell Shock
echo "8. Shell Shock attempts..."
curl -s -H "User-Agent: () { :; }; echo vulnerable" http://localhost:8888/ > /dev/null
echo "   ✅ Sent 1 Shell Shock attempt"

echo ""
echo "🎯 Total: ~30 security attack patterns sent!"
echo "These should trigger ASM Threat Detection rules"
