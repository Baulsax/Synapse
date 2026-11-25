
import logging
import threading


logger = logging.getLogger(__name__)


class UIMixin:

    # ======================================
    # UI RUNTIME
    # ======================================

    @classmethod
    def _get_ui_geometry(cls, fields):
        return {
            "x": cls._safe_integer(fields.get("X", 10), 10),
            "y": cls._safe_integer(fields.get("Y", 10), 10),
            "width": cls._safe_integer(fields.get("WIDTH", 200), 200),
            "height": cls._safe_integer(fields.get("HEIGHT", 30), 30)
        }

    @staticmethod
    def _safe_integer(value, default=0):
        try:
            return int(float(value))
        except (TypeError, ValueError, OverflowError):
            return default

    def create_ui_window(
        self,
        window_id,
        title="Workflow Window",
        width=400,
        height=300
    ):
        if not self.ui_runtime:
            logger.warning("No UI runtime is connected.")
            return

        window_id = str(window_id)

        with self._ui_window_lock:
            self._ui_windows_active = True
            self._ui_window_ids.add(window_id)

        self.ui_runtime.submit(
            self.ui_workflow_id,
            "create_window",
            {
                "window_id": window_id,
                "title": str(title),
                "width": width,
                "height": height
            }
        )

    def create_ui_label(
        self,
        window_id,
        widget_id,
        text="Label",
        geometry=None
    ):
        if not self.ui_runtime:
            return

        payload = {
            "window_id": str(window_id),
            "widget_id": str(widget_id),
            "text": text
        }

        if geometry is not None:
            payload["geometry"] = geometry

        self.ui_runtime.submit(
            self.ui_workflow_id,
            "create_label",
            payload
        )

    def create_ui_button(
        self,
        window_id,
        widget_id,
        text="Button",
        geometry=None
    ):
        if not self.ui_runtime:
            return

        payload = {
            "window_id": str(window_id),
            "widget_id": str(widget_id),
            "text": text
        }

        if geometry is not None:
            payload["geometry"] = geometry

        self.ui_runtime.submit(
            self.ui_workflow_id,
            "create_button",
            payload
        )

    def set_ui_text(self, widget_id, text):
        if not self.ui_runtime:
            return

        self.ui_runtime.submit(
            self.ui_workflow_id,
            "set_text",
            {
                "widget_id": str(widget_id),
                "text": text
            }
        )

    def close_ui_window(self, window_id):
        if not self.ui_runtime:
            return

        self.ui_runtime.submit(
            self.ui_workflow_id,
            "close_window",
            {
                "window_id": str(window_id)
            }
        )

    def handle_ui_window_closed(self):
        with self._ui_window_lock:
            self._ui_windows_active = False
            self._ui_window_ids.clear()

        self.stop()

    # ======================================
    # UI BUTTON EVENTS
    # ======================================

    def handle_ui_button_click(self, widget_id):
        workflow_data = self._workflow_data

        if not workflow_data:
            return

        top_blocks = (
            workflow_data
            .get("blocks", {})
            .get("blocks", [])
        )

        for block in top_blocks:
            if block.get("type") != "automation_ui_button_clicked":
                continue

            fields = block.get("fields", {})

            if str(fields.get("BUTTON_ID", "")) != str(widget_id):
                continue

            body = block.get(
                "next", {}
            ).get("block")

            if not body:
                continue

            button_id = str(widget_id)
            stop_event = threading.Event()

            with self._button_execution_lock:
                existing = self._button_executions.get(
                    button_id, []
                )

                existing = [
                    execution
                    for execution in existing
                    if execution["thread"].is_alive()
                ]

                self._button_executions[button_id] = existing

                if (
                    existing
                    and not self.allow_multiple_ui_executions
                ):
                    logger.debug(
                        "Ignored button click: execution already active "
                        "for button %s.",
                        button_id
                    )
                    continue

                execution = {
                    "stop_event": stop_event,
                    "thread": None
                }

                thread = threading.Thread(
                    target=self._execute_ui_event,
                    args=(button_id, body, stop_event, execution),
                    daemon=True
                )

                execution["thread"] = thread
                existing.append(execution)

                thread.start()

    def _execute_ui_event(
        self,
        button_id,
        body,
        stop_event,
        execution
    ):
        previous = self._set_execution_context(stop_event)
        execution_error = None

        self._notify_lifecycle(
            "button_started",
            button_id
        )

        try:
            self._execute_chain(body)

        except Exception as exc:
            execution_error = exc
            self.last_error = str(exc) or type(exc).__name__

            logger.exception(
                "UI button event execution failed."
            )

            self._notify_lifecycle(
                "error",
                self.last_error
            )

        finally:
            try:
                self._release_all_keys()
            except Exception:
                logger.exception(
                    "Failed to release held inputs after UI button execution."
                )

            self._restore_execution_context(previous)

            with self._button_execution_lock:
                executions = self._button_executions.get(
                    button_id, []
                )

                if execution in executions:
                    executions.remove(execution)

                if not executions:
                    self._button_executions.pop(
                        button_id, None
                    )

            if execution_error is None:
                self._notify_lifecycle(
                    "button_completed",
                    button_id
                )
