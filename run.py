import sys
import os
import uvicorn
import webbrowser
import threading
import time

frozen = getattr(sys, 'frozen', False)


def find_available_port(start_port=8080, max_attempts=4):
    import socket
    for port in range(start_port, start_port + max_attempts):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", port))
                return port
        except OSError:
            continue
    return None


def open_browser(port):
    time.sleep(2)
    webbrowser.open(f"http://127.0.0.1:{port}")


if __name__ == "__main__":
    port = find_available_port()
    if not port:
        print("[错误] 无法找到可用端口，应用启动失败")
        input("按 Enter 键退出...")
        sys.exit(1)

    threading.Thread(target=open_browser, args=(port,)).start()
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
        uvicorn.run(app, host="127.0.0.1", port=port, reload=False)
    else:
        uvicorn.run("app.main:app", host="127.0.0.1", port=port, reload=True)
