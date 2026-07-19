from __future__ import annotations

from tkinter import Misc, TclError

from customtkinter.windows.widgets.appearance_mode.appearance_mode_tracker import (
    AppearanceModeTracker,
)
from customtkinter.windows.widgets.scaling.scaling_tracker import ScalingTracker


def destroy_tk_root(root: Misc) -> None:
    """Destroy a short-lived test root without leaking CustomTkinter callbacks."""
    AppearanceModeTracker.app_list = [
        app for app in AppearanceModeTracker.app_list if app is not root
    ]
    try:
        pending_jobs = root.tk.splitlist(root.tk.call("after", "info"))
    except TclError:
        pending_jobs = ()
    for job in pending_jobs:
        try:
            # Calling Tcl directly also works after a child widget has removed the
            # Python command that CustomTkinter originally scheduled.
            root.tk.call("after", "cancel", job)
        except TclError:
            pass

    try:
        root.destroy()
    finally:
        if not AppearanceModeTracker.app_list:
            AppearanceModeTracker.update_loop_running = False
        if not ScalingTracker.window_widgets_dict:
            ScalingTracker.update_loop_running = False
