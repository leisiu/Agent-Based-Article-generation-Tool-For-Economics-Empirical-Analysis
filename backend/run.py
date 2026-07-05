import uvicorn
import sys
import os

if __name__ == '__main__':
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

    print("Starting backend server...")
    print("Address: http://0.0.0.0:8000")
    print("API Docs: http://0.0.0.0:8000/docs")

    uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=False)
