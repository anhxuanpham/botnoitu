import uvicorn
import threading
import logging
from fastapi import FastAPI
from starlette.responses import JSONResponse, PlainTextResponse
from prometheus_client import start_http_server, Counter, Gauge, generate_latest

# Tắt logging của Uvicorn để không làm lẫn lộn với logs của bot
log = logging.getLogger('uvicorn.error')
log.setLevel(logging.WARNING)

# Định nghĩa Prometheus Metrics (Biến Global)
# 1. Số lần gọi AI (Label: 'success', 'failure')
AI_CALLS_COUNTER = Counter(
    'noitu_total_ai_calls',
    'Total number of calls made to the external AI API',
    ['endpoint_status']
)
# 2. Kích thước từ điển Redis (Gauge để đo lường giá trị hiện tại)
REDIS_HITS_GAUGE = Gauge(
    'noitu_redis_db_size',
    'Current size of the Redis dictionary keys (total unique words)'
)
# 3. Số ván đấu đã hoàn thành
GAMES_COMPLETED_COUNTER = Counter(
    'noitu_games_completed',
    'Total number of Word-Chain games completed'
)

# FastAPI app setup
app = FastAPI(title="W-Lex Monitoring API")


@app.get("/health", response_class=JSONResponse)
async def health_check():
    """Endpoint Health Check: Trả về trạng thái OK."""
    return {"status": "ok", "service": "wlex_bot", "uptime": "running"}


@app.get("/metrics", response_class=PlainTextResponse)
async def metrics_endpoint():
    """Endpoint cho Prometheus để lấy metrics."""
    return PlainTextResponse(generate_latest().decode('utf-8'), media_type="text/plain; version=0.0.4; charset=utf-8")


def start_monitoring_server(port: int = 8000):
    """Khởi động server FastAPI/Prometheus trong một thread riêng."""
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)

    # Khởi động server trong một thread mới để không chặn Discord bot
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    print(f"Monitoring server running on port {port}")
    return thread