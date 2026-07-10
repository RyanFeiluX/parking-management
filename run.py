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
        try:
            from app.main import app
        except Exception:
            import traceback
            import tempfile
            log_path = os.path.join(tempfile.gettempdir(), "parkman_fatal.log")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(f"启动异常时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")
                traceback.print_exc(file=f)
            print(f"[错误] 启动失败，详情请查看: {log_path}")
            input("按 Enter 键退出...")
            raise
        uvicorn.run(app, host="127.0.0.1", port=8080, reload=False)
    else:
        uvicorn.run("app.main:app", host="127.0.0.1", port=8080, reload=True)