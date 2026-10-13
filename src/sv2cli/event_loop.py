"""Run the native application's event loop; no GUI automation or screen input.

SV2 schedules synthesis with JUCE timers. A CLI plugin host must dispatch its
own thread's messages, just as a DAW would. Sleeping alone produces silence.
"""
import ctypes
import sys
import threading
import time
from .errors import SVError

class EventLoop:
    def __init__(self):
        if sys.platform=="win32":
            from ctypes import wintypes
            class MSG(ctypes.Structure):
                _fields_=[("hwnd",wintypes.HWND),("message",wintypes.UINT),("wParam",wintypes.WPARAM),("lParam",wintypes.LPARAM),("time",wintypes.DWORD),("pt",wintypes.POINT),("lPrivate",wintypes.DWORD)]
            self.MSG=MSG;self.api=ctypes.WinDLL("user32",use_last_error=True)
            self.api.PeekMessageW.argtypes=[ctypes.POINTER(MSG),wintypes.HWND,wintypes.UINT,wintypes.UINT,wintypes.UINT]
            self.api.PeekMessageW.restype=wintypes.BOOL
            self.api.TranslateMessage.argtypes=[ctypes.POINTER(MSG)];self.api.TranslateMessage.restype=wintypes.BOOL
            self.api.DispatchMessageW.argtypes=[ctypes.POINTER(MSG)];self.api.DispatchMessageW.restype=ctypes.c_ssize_t
        elif sys.platform=="darwin":
            self.api=ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
            self.mode=ctypes.c_void_p.in_dll(self.api,"kCFRunLoopDefaultMode")
            self.api.CFRunLoopRunInMode.argtypes=[ctypes.c_void_p,ctypes.c_double,ctypes.c_bool]
            self.api.CFRunLoopRunInMode.restype=ctypes.c_int32
        else:
            raise SVError("Native SV2 VST3 rendering is supported on Windows/macOS. Use the command backend on other environments.","unsupported_platform")

    def wait(self,seconds):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            if sys.platform=="win32":
                msg=self.MSG()
                for _ in range(1000):
                    if not self.api.PeekMessageW(ctypes.byref(msg),None,0,0,1):break
                    self.api.TranslateMessage(ctypes.byref(msg));self.api.DispatchMessageW(ctypes.byref(msg))
                time.sleep(min(.005,max(0,end-time.monotonic())))
            else:
                self.api.CFRunLoopRunInMode(self.mode,min(.02,max(0,end-time.monotonic())),True)

    def run_background(self,fn):
        result=[];error=[]
        def run():
            try:result.append(fn())
            except BaseException as e:error.append(e)
        thread=threading.Thread(target=run,daemon=True);thread.start()
        while thread.is_alive():self.wait(.05)
        thread.join()
        if error:raise error[0]
        return result[0] if result else None
