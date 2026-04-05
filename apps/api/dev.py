from pathlib import Path

import uvicorn

BASE_DIR = Path(__file__).resolve().parent

if __name__ == "__main__":
    uvicorn.run(
        "app.main:app",
        host="127.0.0.1",
        port=8000,
        app_dir=str(BASE_DIR),
        reload=False,
    )
