# Remote.it Setup Guide

## Current Services (Already Configured)
- RTSP video stream (TCP port)
- WebRTC via mediamtx (TCP port)

## New Service Required for Sensor API

### Service Configuration

**Service Type:** HTTP (or TCP if HTTP not available)
- **Port:** 5000
- **Protocol:** TCP
- **Service Name:** "Sensor API" (or similar)
- **Description:** "REST API and WebSocket for sensor data streaming"

### Step-by-Step Setup

1. **Log into remote.it Dashboard**
   - Go to https://remote.it
   - Navigate to your Raspberry Pi device

2. **Add New Service**
   - Click "Add Service" or "+" button
   - Select service type: **HTTP** (preferred) or **TCP**
   - Local Port: **5000**
   - Service Name: **Sensor API**
   - Click "Add" or "Save"

3. **Get Service URL**
   - Once created, you'll get a URL like:
     - HTTP: `https://abc123def456.p18.rt3.io:33000`
     - TCP: `proxy-abc123def456.rt3.io:33000`
   - Copy this URL for use in your Next.js dashboard

4. **Test the Connection**
   ```bash
   # From your EC2 instance or local machine
   curl https://your-remoteit-url/api/health
   ```

## Complete Remote.it Service List

After setup, you should have these services configured:

| Service Name | Protocol | Local Port | Purpose |
|-------------|----------|------------|---------|
| RTSP Stream | TCP | 8554 | Video streaming (RTSP) |
| WebRTC | TCP | 8889 | WebRTC video streaming via mediamtx |
| Sensor API | HTTP/TCP | 5000 | REST API + WebSocket sensor data |

## WebSocket Considerations with Remote.it

**Important:** WebSocket connections work through remote.it, but there are some considerations:

### Option 1: WebSocket over remote.it (Works, but may have limitations)
- Remote.it supports WebSocket tunneling
- May have higher latency than direct connections
- Connection URL format:
  ```
  ws://your-remoteit-url/ws/stream
  # or with HTTPS:
  wss://your-remoteit-url/ws/stream
  ```

### Option 2: Use REST API with Polling (More reliable through remote.it)
- If WebSocket is unreliable through remote.it, fall back to polling
- Poll `/api/current` every 500ms - 1s for near-real-time data
- More predictable behavior through tunnels

### Option 3: Use Server-Sent Events (Alternative to WebSocket)
If WebSocket doesn't work reliably through remote.it, you can modify `api_server.py` to use SSE:

```python
@app.route('/api/stream-sse')
def stream_sse():
    def generate():
        while True:
            with data_lock:
                data = json.dumps(shared_data['current'])
            yield f"data: {data}\n\n"
            time.sleep(0.1)  # 10 updates per second

    return Response(generate(), mimetype='text/event-stream')
```

## Firewall Configuration (If Needed)

If you're running a firewall on the Pi, ensure port 5000 is open:

```bash
# UFW (Ubuntu Firewall)
sudo ufw allow 5000/tcp

# iptables
sudo iptables -A INPUT -p tcp --dport 5000 -j ACCEPT
sudo iptables-save > /etc/iptables/rules.v4
```

## Next.js Environment Variables

Update your `.env.local` on EC2:

```bash
# Remote.it URLs
NEXT_PUBLIC_RTSP_URL=proxy-abc123.rt3.io:33001
NEXT_PUBLIC_WEBRTC_URL=https://def456.p18.rt3.io:33002
NEXT_PUBLIC_SENSOR_API_URL=https://ghi789.p18.rt3.io:33003
```

## Testing the Setup

### 1. Test from Pi Locally
```bash
# On the Pi
curl http://localhost:5000/api/health
curl http://localhost:5000/api/current

# Test WebSocket
pip3 install websocket-client
python3 -c "from websocket import create_connection; ws = create_connection('ws://localhost:5000/ws/stream'); print(ws.recv()); ws.close()"
```

### 2. Test from EC2 via Remote.it
```bash
# On EC2 instance
curl https://your-remoteit-url/api/health
curl https://your-remoteit-url/api/current
curl https://your-remoteit-url/api/history?minutes=1

# Test WebSocket (install wscat first: npm install -g wscat)
wscat -c wss://your-remoteit-url/ws/stream
```

### 3. Monitor Logs on Pi
```bash
# Watch Flask logs
journalctl -u your-service-name -f

# Or if running manually
python3 graph_faster.py
# You should see: "Starting API server on 0.0.0.0:5000"
```

## Alternatives to Remote.it (For Better Performance)

### 1. Tailscale (Recommended)
**Pros:**
- Direct peer-to-peer connections (low latency)
- No bandwidth limits
- Free for personal use
- Works great with WebSocket

**Setup:**
```bash
# On Pi
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# On EC2
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up

# Both devices now on same VPN network
# Access Pi at: http://100.x.x.x:5000
```

**Next.js Config:**
```bash
NEXT_PUBLIC_SENSOR_API_URL=http://100.64.1.2:5000
```

### 2. CloudFlare Tunnel
**Pros:**
- No port forwarding needed
- Free tier available
- HTTPS automatically
- Good for HTTP/WebSocket

**Setup on Pi:**
```bash
# Install cloudflared
curl -L https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm64.deb -o cloudflared.deb
sudo dpkg -i cloudflared.deb

# Authenticate
cloudflared tunnel login

# Create tunnel
cloudflared tunnel create sensor-api

# Configure tunnel (create config.yml)
cat > ~/.cloudflared/config.yml << EOF
tunnel: YOUR_TUNNEL_ID
credentials-file: /home/pi/.cloudflared/YOUR_TUNNEL_ID.json

ingress:
  - hostname: sensors.yourdomain.com
    service: http://localhost:5000
  - service: http_status:404
EOF

# Run tunnel
cloudflared tunnel run sensor-api
```

**Next.js Config:**
```bash
NEXT_PUBLIC_SENSOR_API_URL=https://sensors.yourdomain.com
```

### 3. WireGuard VPN
**Pros:**
- Fastest VPN protocol
- Direct connections
- Full control

**Cons:**
- Requires manual setup
- Need public IP or relay server

### Comparison Table

| Solution | Latency | Setup Complexity | Cost | WebSocket Support |
|----------|---------|------------------|------|-------------------|
| Remote.it | Medium-High | Easy | Free tier | Works, may have issues |
| Tailscale | Low | Easy | Free (personal) | Excellent |
| CloudFlare Tunnel | Low-Medium | Medium | Free tier | Excellent |
| WireGuard | Very Low | Hard | Free | Excellent |
| ngrok | Medium | Easy | Paid for production | Good |

## Recommended Approach

**For Production:**
1. **Tailscale** - Best balance of ease and performance
2. **CloudFlare Tunnel** - If you need public access without VPN

**For Development/Testing:**
1. **Remote.it** - Works fine for initial testing
2. **ngrok** - Quick temporary access

## Auto-start Configuration (Systemd)

Create a systemd service to auto-start the sensor API:

```bash
sudo nano /etc/systemd/system/sensor-api.service
```

```ini
[Unit]
Description=ELDAEON Sensor API Server
After=network.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/platform-pi/python-libgqe
Environment="DISPLAY=:0"
ExecStart=/usr/bin/python3 /home/pi/platform-pi/python-libgqe/graph_faster.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable sensor-api
sudo systemctl start sensor-api
sudo systemctl status sensor-api
```

## Monitoring & Debugging

### Check if API is running
```bash
sudo netstat -tlnp | grep :5000
# or
sudo ss -tlnp | grep :5000
```

### Check remote.it connectivity
```bash
# On Pi
sudo systemctl status remoteit

# View logs
sudo journalctl -u remoteit -f
```

### Check API logs
```bash
# If using systemd
sudo journalctl -u sensor-api -f

# If running manually
python3 graph_faster.py 2>&1 | tee api.log
```

## Security Best Practices

1. **Use API Keys** - Add authentication to your API endpoints
2. **Rate Limiting** - Prevent abuse with rate limiting
3. **HTTPS Only** - Use HTTPS in production (CloudFlare or reverse proxy)
4. **IP Whitelisting** - Restrict access to your EC2 IP if possible
5. **Monitor Access** - Log all API requests for security auditing

Example with API key in remote.it URL:
```bash
# Add to your Next.js fetch calls
headers: {
  'X-API-Key': process.env.SENSOR_API_KEY
}
```
