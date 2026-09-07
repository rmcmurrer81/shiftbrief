from pathlib import Path
import json, os, subprocess, sys, time, urllib.request, webbrowser

ROOT=Path(__file__).resolve().parent
URL='http://127.0.0.1:8797'

def ready():
    try:
        with urllib.request.urlopen(URL+'/api/state',timeout=1) as response:
            return json.load(response).get('app')=='ShiftBrief'
    except (OSError,ValueError):
        return False

def main():
    if ready():
        webbrowser.open(URL)
        return
    runtime=ROOT/'.venv'/('Scripts/python.exe' if os.name=='nt' else 'bin/python')
    logs=ROOT/'data';logs.mkdir(exist_ok=True)
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with (logs/'launcher.log').open('a',encoding='utf-8') as log:
        if not runtime.exists():
            runtime=Path(sys.executable).with_name('python.exe') if os.name=='nt' else Path(sys.executable)
        process=subprocess.Popen([str(runtime),str(ROOT/'server.py')],cwd=ROOT,stdout=log,stderr=log,creationflags=flags)
        for _ in range(120):
            if ready():
                webbrowser.open(URL)
                return
            if process.poll() is not None:
                raise RuntimeError('ShiftBrief could not start. See data/launcher.log. Port 8797 may already be in use.')
            time.sleep(.25)
    raise RuntimeError('ShiftBrief did not become ready. See data/launcher.log.')

if __name__=='__main__':
    try:main()
    except Exception as exc:
        try:
            import tkinter as tk
            from tkinter import messagebox
            root=tk.Tk();root.withdraw();messagebox.showerror('ShiftBrief',str(exc));root.destroy()
        except Exception:
            print(str(exc),file=sys.stderr)
