"""API 서버 진입점"""
import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "src.presentation.api.orderbook_api:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
    )
