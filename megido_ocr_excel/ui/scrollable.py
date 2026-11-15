import customtkinter as ctk


class AutoHideScrollableFrame(ctk.CTkScrollableFrame):
    """Show the scrollbar only while the frame content exceeds its viewport."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._scrollbar_visibility_job: str | None = None
        self._scrollbar_is_visible = True
        self.bind("<Configure>", self._schedule_scrollbar_visibility_update, add="+")
        self._parent_canvas.bind(
            "<Configure>", self._schedule_scrollbar_visibility_update, add="+"
        )
        self._schedule_scrollbar_visibility_update()

    def _schedule_scrollbar_visibility_update(self, _event=None) -> None:
        if self._scrollbar_visibility_job is not None:
            self.after_cancel(self._scrollbar_visibility_job)
        self._scrollbar_visibility_job = self.after_idle(
            self._update_scrollbar_visibility
        )

    def _update_scrollbar_visibility(self) -> None:
        self._scrollbar_visibility_job = None
        bbox = self._parent_canvas.bbox("all")
        if self._orientation == "vertical":
            content_size = 0 if bbox is None else bbox[3] - bbox[1]
            viewport_size = self._parent_canvas.winfo_height()
        else:
            content_size = 0 if bbox is None else bbox[2] - bbox[0]
            viewport_size = self._parent_canvas.winfo_width()

        should_show = viewport_size > 1 and content_size > viewport_size + 1
        if should_show == self._scrollbar_is_visible:
            return
        if should_show:
            self._scrollbar.grid()
        else:
            self._scrollbar.grid_remove()
        self._scrollbar_is_visible = should_show

    def destroy(self) -> None:
        if self._scrollbar_visibility_job is not None:
            self.after_cancel(self._scrollbar_visibility_job)
            self._scrollbar_visibility_job = None
        super().destroy()


