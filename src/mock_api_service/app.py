from fastapi import FastAPI
import os # For accessing environment variables

app = FastAPI()

@app.get("/")
async def hello_mock_api():
    return {"message": "Hello from Mock API Service!"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("MOCK_API_PORT", 8001))
    uvicorn.run(app, host="0.0.0.0", port=port)