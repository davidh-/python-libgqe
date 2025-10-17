# Next.js Client Integration Guide

This guide shows how to integrate the sensor data API into your Next.js dashboard on EC2.

## API Endpoints

Assuming your Pi is accessible via remote.it at `https://your-remoteit-url.com` or via Tailscale/direct IP:

### REST Endpoints

```typescript
// Get current sensor readings
GET /api/current
Response: {
  timestamp: number,
  cpm_h: number,
  cpm_l: number,
  emf: number,
  rf: number,
  ef: number,
  altitude: number,
  latitude: number,
  longitude: number,
  velocity: number
}

// Get historical data
GET /api/history?minutes=5&points=1000
Response: {
  timestamps: number[],
  cpm_h: number[],
  cpm_l: number[],
  emf: number[],
  rf: number[],
  ef: number[],
  altitude: number[],
  velocity: number[]
}

// Get statistics
GET /api/stats
Response: {
  cpm_h: { min: number, max: number, avg: number },
  cpm_l: { min: number, max: number, avg: number },
  emf: { min: number, max: number, avg: number },
  rf: { min: number, max: number, avg: number },
  ef: { min: number, max: number, avg: number },
  altitude: { min: number, max: number, avg: number },
  velocity: { min: number, max: number, avg: number },
  data_points: number,
  time_range_seconds: number
}

// Health check
GET /api/health
Response: { status: string, timestamp: number }
```

### WebSocket Stream

```
ws://your-pi-address:5000/ws/stream
```

## Next.js React Hook Example

Create a custom hook for sensor data:

```typescript
// hooks/useSensorData.ts
import { useState, useEffect, useCallback, useRef } from 'react';

interface SensorData {
  timestamp: number;
  cpm_h: number;
  cpm_l: number;
  emf: number;
  rf: number;
  ef: number;
  altitude: number;
  latitude: number;
  longitude: number;
  velocity: number;
}

interface SensorHistory {
  timestamps: number[];
  cpm_h: number[];
  cpm_l: number[];
  emf: number[];
  rf: number[];
  ef: number[];
  altitude: number[];
  velocity: number[];
}

export function useSensorData(apiUrl: string) {
  const [current, setCurrent] = useState<SensorData | null>(null);
  const [history, setHistory] = useState<SensorHistory | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  // Fetch initial history
  const fetchHistory = useCallback(async (minutes: number = 5) => {
    try {
      const response = await fetch(`${apiUrl}/api/history?minutes=${minutes}`);
      if (!response.ok) throw new Error('Failed to fetch history');
      const data = await response.json();
      setHistory(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    }
  }, [apiUrl]);

  // WebSocket connection
  useEffect(() => {
    const wsUrl = apiUrl.replace('http', 'ws') + '/ws/stream';
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      console.log('WebSocket connected');
      setIsConnected(true);
      setError(null);
    };

    ws.onmessage = (event) => {
      try {
        const data: SensorData = JSON.parse(event.data);
        setCurrent(data);
      } catch (err) {
        console.error('Failed to parse WebSocket message:', err);
      }
    };

    ws.onerror = (event) => {
      console.error('WebSocket error:', event);
      setError('WebSocket connection error');
    };

    ws.onclose = () => {
      console.log('WebSocket disconnected');
      setIsConnected(false);

      // Attempt to reconnect after 5 seconds
      setTimeout(() => {
        console.log('Attempting to reconnect...');
      }, 5000);
    };

    wsRef.current = ws;

    return () => {
      ws.close();
    };
  }, [apiUrl]);

  return {
    current,
    history,
    isConnected,
    error,
    fetchHistory,
  };
}
```

## Component Example

```typescript
// components/SensorDashboard.tsx
'use client';

import { useEffect } from 'react';
import { useSensorData } from '@/hooks/useSensorData';

export default function SensorDashboard() {
  // Replace with your actual API URL (remote.it URL or direct IP)
  const API_URL = process.env.NEXT_PUBLIC_SENSOR_API_URL || 'http://localhost:5000';

  const { current, history, isConnected, error, fetchHistory } = useSensorData(API_URL);

  useEffect(() => {
    // Fetch initial history on mount
    fetchHistory(10); // Last 10 minutes
  }, [fetchHistory]);

  if (error) {
    return (
      <div className="p-4 bg-red-100 text-red-800 rounded">
        Error: {error}
      </div>
    );
  }

  return (
    <div className="p-6 space-y-6">
      {/* Connection Status */}
      <div className={`inline-flex items-center px-3 py-1 rounded-full text-sm ${
        isConnected ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
      }`}>
        <span className={`w-2 h-2 rounded-full mr-2 ${
          isConnected ? 'bg-green-500' : 'bg-red-500'
        }`} />
        {isConnected ? 'Connected' : 'Disconnected'}
      </div>

      {/* Current Readings */}
      {current && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <SensorCard label="CPM High" value={current.cpm_h.toFixed(0)} unit="" />
          <SensorCard label="CPM Low" value={current.cpm_l.toFixed(0)} unit="" />
          <SensorCard label="EMF" value={current.emf.toFixed(3)} unit="mG" />
          <SensorCard label="RF" value={current.rf.toFixed(3)} unit="mW/m²" />
          <SensorCard label="EF" value={current.ef.toFixed(3)} unit="V/m" />
          <SensorCard label="Altitude" value={current.altitude.toFixed(1)} unit="ft" />
          <SensorCard label="Velocity" value={current.velocity.toFixed(1)} unit="mph" />
          <SensorCard
            label="Location"
            value={`${current.latitude.toFixed(5)}, ${current.longitude.toFixed(5)}`}
            unit=""
          />
        </div>
      )}

      {/* Historical Data Chart */}
      {history && (
        <div className="mt-8">
          <h2 className="text-xl font-bold mb-4">Historical Data</h2>
          {/* Integrate with your charting library (Chart.js, Recharts, etc.) */}
          <p className="text-gray-600">
            {history.timestamps.length} data points available
          </p>
        </div>
      )}
    </div>
  );
}

function SensorCard({ label, value, unit }: { label: string; value: string; unit: string }) {
  return (
    <div className="bg-white p-4 rounded-lg shadow">
      <div className="text-sm text-gray-600 mb-1">{label}</div>
      <div className="text-2xl font-bold">
        {value} <span className="text-sm font-normal text-gray-500">{unit}</span>
      </div>
    </div>
  );
}
```

## Environment Variables

Add to your `.env.local`:

```bash
# For local development (via remote.it or Tailscale)
NEXT_PUBLIC_SENSOR_API_URL=http://your-pi-address:5000

# For production (if using a reverse proxy or public endpoint)
NEXT_PUBLIC_SENSOR_API_URL=https://your-domain.com
```

## Fetching Data with Server Components (App Router)

```typescript
// app/dashboard/page.tsx
async function getSensorStats() {
  const res = await fetch(`${process.env.SENSOR_API_URL}/api/stats`, {
    cache: 'no-store', // Always fetch fresh data
  });

  if (!res.ok) throw new Error('Failed to fetch stats');
  return res.json();
}

export default async function DashboardPage() {
  const stats = await getSensorStats();

  return (
    <div>
      <h1>Sensor Statistics</h1>
      <pre>{JSON.stringify(stats, null, 2)}</pre>
    </div>
  );
}
```

## Using with Chart.js or Recharts

Example with Recharts:

```typescript
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, Legend } from 'recharts';

function HistoryChart({ history }: { history: SensorHistory }) {
  // Transform data for Recharts
  const data = history.timestamps.map((timestamp, idx) => ({
    time: new Date(timestamp * 1000).toLocaleTimeString(),
    cpm_h: history.cpm_h[idx],
    cpm_l: history.cpm_l[idx],
    emf: history.emf[idx],
    rf: history.rf[idx],
  }));

  return (
    <LineChart width={800} height={400} data={data}>
      <CartesianGrid strokeDasharray="3 3" />
      <XAxis dataKey="time" />
      <YAxis />
      <Tooltip />
      <Legend />
      <Line type="monotone" dataKey="cpm_h" stroke="#e74c3c" name="CPM High" />
      <Line type="monotone" dataKey="cpm_l" stroke="#27ae60" name="CPM Low" />
      <Line type="monotone" dataKey="emf" stroke="#3498db" name="EMF (mG)" />
      <Line type="monotone" dataKey="rf" stroke="#e67e22" name="RF (mW/m²)" />
    </LineChart>
  );
}
```

## Testing Locally

1. Install dependencies on Pi:
   ```bash
   cd /home/pi/platform-pi/python-libgqe
   pip3 install -r requirements.txt
   ```

2. Run the graph application:
   ```bash
   python3 graph_faster.py
   ```

3. Test endpoints from your EC2 instance:
   ```bash
   # Replace with your remote.it URL or Pi IP
   curl http://your-pi-address:5000/api/health
   curl http://your-pi-address:5000/api/current
   curl http://your-pi-address:5000/api/history?minutes=1
   ```

4. Test WebSocket with wscat:
   ```bash
   npm install -g wscat
   wscat -c ws://your-pi-address:5000/ws/stream
   ```

## Remote.it Configuration

In your remote.it dashboard:
1. Add a new service for TCP port 5000
2. Name it "Sensor API" or similar
3. Use the generated URL in your Next.js app
4. Update NEXT_PUBLIC_SENSOR_API_URL with the remote.it URL

## Security Considerations

1. **Authentication**: Consider adding API key authentication
2. **Rate Limiting**: Add rate limiting for production use
3. **HTTPS**: Use HTTPS in production (CloudFlare Tunnel or reverse proxy)
4. **Firewall**: Only expose port 5000 to trusted networks
5. **CORS**: Restrict CORS to your EC2 domain in production

Example with API key:

```python
# In api_server.py
from functools import wraps

API_KEY = os.environ.get('API_KEY', 'your-secret-key')

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.headers.get('X-API-Key') != API_KEY:
            return jsonify({'error': 'Invalid API key'}), 401
        return f(*args, **kwargs)
    return decorated_function

@app.route('/api/current')
@require_api_key
def get_current():
    # ... existing code
```
