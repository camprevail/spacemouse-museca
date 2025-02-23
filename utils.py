import ctypes

def pid_from_window(windowName):
    hwnd = ctypes.windll.user32.FindWindowW(windowName, None)

    if hwnd:
        process_id = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(process_id))
        return process_id.value
    else:
        return None
