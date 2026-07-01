import sys
import uvicorn
import webbrowser
import threading
import time

frozen = getattr(sys, 'frozen', False)

def open_browser():
    time.sleep(2)
    webbrowser.open("http://127.0.0.1:8080")

if __name__ == "__main__":
    threading.Thread(target=open_browser).start()
    if frozen:
        from app.main import app
        uvicorn.run(app, host="127.0.0.1", port=8080, reload=False)
    else:
        uvicorn.run("app.main:app", host="127.0.0.1", port=8080, reload=True)