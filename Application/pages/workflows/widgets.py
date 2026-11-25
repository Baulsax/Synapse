
import math
from pathlib import Path

from PySide6.QtCore import (
    Signal,
    Qt,
    QSize,
    QMimeData,
    QTimer,
)
from PySide6.QtGui import (
    QDrag,
    QPainter,
    QIcon,
    QTransform,
    QDoubleValidator,
    QFont,
)
from PySide6.QtWidgets import (
    QWidget,
    QHBoxLayout,
    QVBoxLayout,
    QFormLayout,
    QLabel,
    QPushButton,
    QComboBox,
    QFrame,
    QScrollArea,
    QApplication,
    QSizePolicy,
    QStyle,
    QStyleOptionComboBox,
    QDoubleSpinBox,
    QLineEdit,
    QCheckBox,
    QGraphicsOpacityEffect,
)


class CompactDoubleSpinBox(QDoubleSpinBox):

    def textFromValue(self, value):
        text = f"{value:.6f}".rstrip("0").rstrip(".")
        return text or "0"


class WorkflowSortComboBox(QComboBox):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.popup_open = False

        combo_font = QFont(self.font())

        if combo_font.pointSizeF() <= 0:
            combo_font = QFont(QApplication.font())

        if combo_font.pointSizeF() <= 0:
            combo_font.setPointSize(10)

        self.setFont(combo_font)

        popup = self.view()
        popup.setFont(combo_font)
        popup.viewport().setFont(combo_font)

        arrow_path = (
            Path(__file__).parent.parent.parent
            / "assets"
            / "dropdown-arrow.svg"
        )

        self.arrow_icon = QIcon(str(arrow_path))

    def showPopup(self):
        self.popup_open = True
        self.update()
        super().showPopup()
        self.update()

    def hidePopup(self):
        super().hidePopup()
        self.popup_open = False
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)

        if self.arrow_icon.isNull():
            return

        option = QStyleOptionComboBox()
        self.initStyleOption(option)

        arrow_rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox,
            option,
            QStyle.SubControl.SC_ComboBoxArrow,
            self
        )

        pixmap = self.arrow_icon.pixmap(QSize(10, 10))

        if self.popup_open:
            pixmap = pixmap.transformed(
                QTransform().rotate(180),
                Qt.TransformationMode.SmoothTransformation
            )

        x = arrow_rect.center().x() - pixmap.width() // 2
        y = arrow_rect.center().y() - pixmap.height() // 2

        painter = QPainter(self)
        painter.drawPixmap(x, y, pixmap)
        painter.end()


class DragHandle(QLabel):

    def __init__(self, card):
        super().__init__("⠿")

        self.card = card
        self.drag_start = None

        self.setObjectName("workflow_drag_handle")
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_start = event.position().toPoint()

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if (
            self.drag_start is not None
            and event.buttons() & Qt.MouseButton.LeftButton
        ):
            distance = (
                event.position().toPoint() - self.drag_start
            ).manhattanLength()

            if distance >= QApplication.startDragDistance():
                self.card.start_drag(
                    self.mapTo(self.card, self.drag_start)
                )
                self.drag_start = None
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self.drag_start = None
        super().mouseReleaseEvent(event)


class WorkflowCard(QFrame):

    def __init__(
        self,
        workflow_name,
        list_widget,
        edit_callback,
        run_callback,
        delete_callback,
        export_callback,
        status="Idle",
        settings=None,
        setting_values=None,
        setting_callback=None,
        enabled=True,
        enabled_callback=None
    ):
        super().__init__()

        self.workflow_name = workflow_name
        self.list_widget = list_widget
        self.settings = list(settings or [])
        self.setting_values = dict(setting_values or {})
        self.setting_callback = setting_callback
        self.enabled_callback = enabled_callback
        self._enabled = bool(enabled)

        self._pending_setting_corrections = {}

        self.setObjectName("workflow_card")
        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )
        self.setMinimumWidth(0)
        self.setMinimumHeight(82)

        self.card_layout = QVBoxLayout(self)
        self.card_layout.setContentsMargins(16, 12, 16, 12)
        self.card_layout.setSpacing(10)

        # ======================================
        # MAIN CARD ROW
        # ======================================

        self.main_row_container = QWidget()
        self.main_row_container.setObjectName(
            "workflow_card_main_row"
        )

        self.main_row_container.setFixedHeight(58)

        self.main_row_container.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )

        layout = QHBoxLayout(self.main_row_container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.drag_handle = DragHandle(self)

        layout.addWidget(
            self.drag_handle,
            0,
            Qt.AlignmentFlag.AlignVCenter
        )

        # ======================================
        # ENABLE / DISABLE CHECKBOX
        # ======================================

        layout.addSpacing(0)

        self.enabled_checkbox = QCheckBox()
        self.enabled_checkbox.setObjectName(
            "workflow_enabled_checkbox"
        )
        self.enabled_checkbox.setToolTip(
            "Enable or disable automatic triggers for this workflow"
        )
        self.enabled_checkbox.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.enabled_checkbox.setFixedSize(28, 28)
        self.enabled_checkbox.setSizePolicy(
            QSizePolicy.Policy.Fixed,
            QSizePolicy.Policy.Fixed
        )

        self.enabled_checkbox.setStyleSheet("""
            QCheckBox {
                padding-left: 7px;
                padding-right: 7px;
            }
        """)

        self.enabled_checkbox.setChecked(self._enabled)
        self.enabled_checkbox.toggled.connect(
            self._enabled_toggled
        )

        layout.addWidget(
            self.enabled_checkbox,
            0,
            Qt.AlignmentFlag.AlignVCenter
        )

        layout.addSpacing(14)

        # ======================================
        # WORKFLOW DETAILS
        # ======================================

        self.details_widget = QWidget()
        details = QVBoxLayout(self.details_widget)
        details.setContentsMargins(0, 0, 0, 0)
        details.setSpacing(4)
        details.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(10)

        name_label = QLabel(workflow_name)
        name_label.setObjectName("workflow_card_title")
        name_label.setMinimumWidth(0)

        self.status_label = QLabel()
        self.status_label.setObjectName("workflow_status")
        self.status_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.status_label.setMinimumWidth(64)
        self.status_label.setFixedHeight(21)

        title_row.addWidget(name_label)
        title_row.addWidget(self.status_label)
        title_row.addStretch()

        description_label = QLabel("Automation workflow")
        description_label.setObjectName("workflow_card_description")

        details.addLayout(title_row)
        details.addWidget(description_label)

        layout.addWidget(self.details_widget, 1)

        # ======================================
        # ACTIONS
        # ======================================

        layout.addSpacing(14)

        self.actions_widget = QWidget()
        actions = QHBoxLayout(self.actions_widget)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)

        upload_icon_path = (
            Path(__file__).parent.parent.parent
            / "assets"
            / "upload.svg"
        )

        export_button = QPushButton("Export")
        export_button.setObjectName("secondary_button")
        export_button.setIcon(QIcon(str(upload_icon_path)))
        export_button.setIconSize(QSize(16, 16))
        export_button.setToolTip("Export workflow")
        export_button.setFixedSize(88, 32)
        export_button.clicked.connect(
            lambda: export_callback(workflow_name)
        )

        edit_button = QPushButton("Edit")
        edit_button.setObjectName("secondary_button")
        edit_button.clicked.connect(
            lambda: edit_callback(workflow_name)
        )

        self.run_button = QPushButton()
        self.run_button.setObjectName("primary_button")
        self.run_button.clicked.connect(
            lambda: run_callback(workflow_name)
        )

        delete_button = QPushButton("Delete")
        delete_button.setObjectName("danger_button")
        delete_button.clicked.connect(
            lambda: delete_callback(workflow_name)
        )

        for button in (
            edit_button,
            self.run_button,
            delete_button
        ):
            button.setFixedSize(76, 32)

        actions.addWidget(export_button)

        if self.settings:
            self.settings_button = QPushButton("Settings")
            self.settings_button.setObjectName("secondary_button")
            self.settings_button.setFixedSize(150, 32)

            self.settings_button.setCheckable(True)
            self.settings_button.setToolTip(
                "Customize this workflow's exposed settings"
            )
            self.settings_button.toggled.connect(
                self._toggle_settings
            )
            actions.addWidget(self.settings_button)
        else:
            self.settings_button = None

        actions.addWidget(edit_button)
        actions.addWidget(self.run_button)
        actions.addWidget(delete_button)

        layout.addWidget(self.actions_widget, 0)

        self.card_layout.addWidget(self.main_row_container)

        # ======================================
        # DISABLED APPEARANCE
        # ======================================

        self.details_opacity = QGraphicsOpacityEffect(
            self.details_widget
        )
        self.details_widget.setGraphicsEffect(
            self.details_opacity
        )

        self.actions_opacity = QGraphicsOpacityEffect(
            self.actions_widget
        )
        self.actions_widget.setGraphicsEffect(
            self.actions_opacity
        )

        self._apply_enabled_appearance()

        # ======================================
        # EXPANDABLE SETTINGS
        # ======================================

        self.settings_panel = None
        self.setting_inputs = {}

        if self.settings:
            self._create_settings_panel()

        self.set_status(status)

        # Persist any initial values that needed correction.
        for setting_id, corrected_value in (
            self._pending_setting_corrections.items()
        ):
            self._setting_changed(
                setting_id,
                corrected_value
            )

        self._pending_setting_corrections.clear()

    def _enabled_toggled(self, enabled):
        enabled = bool(enabled)

        if callable(self.enabled_callback):
            try:
                result = self.enabled_callback(
                    self.workflow_name,
                    enabled
                )
            except Exception:
                result = False

            if result is False:
                self.enabled_checkbox.blockSignals(True)
                self.enabled_checkbox.setChecked(self._enabled)
                self.enabled_checkbox.blockSignals(False)
                return

        self._enabled = enabled
        self._apply_enabled_appearance()

    def _apply_enabled_appearance(self):
        opacity = 1.0 if self._enabled else 0.58

        self.details_opacity.setOpacity(opacity)
        self.actions_opacity.setOpacity(opacity)

        self.enabled_checkbox.setToolTip(
            "Automatic triggers enabled"
            if self._enabled
            else "Automatic triggers disabled. Manual runs are still available."
        )

    def set_enabled(self, enabled):
        enabled = bool(enabled)

        self._enabled = enabled

        self.enabled_checkbox.blockSignals(True)
        self.enabled_checkbox.setChecked(enabled)
        self.enabled_checkbox.blockSignals(False)

        self._apply_enabled_appearance()

    @staticmethod
    def _setting_minimum(setting):
        setting_type = str(
            setting.get("type", "NUMBER")
        ).strip().upper()

        if setting_type in ("TEXT", "STRING"):
            return None

        name = str(
            setting.get("name") or ""
        ).strip().casefold()

        if name in ("interval", "interval (ms)"):
            return 1.0

        minimum = setting.get("minimum")

        if minimum is None:
            minimum = setting.get("min_value")

        if minimum is None:
            return None

        try:
            minimum = float(minimum)

            if not math.isfinite(minimum):
                return None

            return minimum

        except (TypeError, ValueError, OverflowError):
            return None

    def _create_settings_panel(self):
        self.settings_panel = QFrame()
        self.settings_panel.setObjectName(
            "workflow_settings_panel"
        )

        self.settings_panel.setSizePolicy(
            QSizePolicy.Policy.Ignored,
            QSizePolicy.Policy.Fixed
        )
        self.settings_panel.setMinimumWidth(0)

        self.settings_panel.setStyleSheet("""
            QFrame#workflow_settings_panel {
                background-color: #1d2028;
                border: 1px solid #343945;
                border-radius: 8px;
            }

            QLabel {
                color: #c7cad2;
                border: none;
                background: transparent;
            }

            QLineEdit {
                background-color: #272b35;
                color: #f0f0f3;
                border: 1px solid #3b414e;
                border-radius: 5px;
                padding: 4px 7px;
                min-height: 23px;
                selection-background-color: #a78bfa;
            }

            QLineEdit:focus {
                border: 1px solid #a78bfa;
            }
        """)

        panel_layout = QVBoxLayout(self.settings_panel)
        panel_layout.setContentsMargins(14, 12, 14, 12)
        panel_layout.setSpacing(9)

        heading = QLabel("Workflow Settings")
        heading.setStyleSheet("""
            QLabel {
                color: #e5e7eb;
                font-weight: 600;
                font-size: 9pt;
            }
        """)

        panel_layout.addWidget(heading)

        form = QFormLayout()
        form.setContentsMargins(0, 0, 0, 0)
        form.setHorizontalSpacing(18)
        form.setVerticalSpacing(8)
        form.setLabelAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        form.setFieldGrowthPolicy(
            QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow
        )

        for setting in self.settings:
            setting_id = setting.get("id")

            if not setting_id:
                continue

            name = str(
                setting.get("name") or "Setting"
            )

            setting_type = str(
                setting.get("type", "NUMBER")
            ).upper()

            if setting_type not in ("TEXT", "STRING"):
                setting_type = "NUMBER"

            value = self.setting_values.get(
                setting_id,
                setting.get("value", "")
                if setting_type == "TEXT"
                else setting.get("value", 0)
            )

            editor = QLineEdit()
            editor.setMinimumWidth(150)
            editor.setMaximumWidth(300)

            if setting_type == "NUMBER":
                minimum = self._setting_minimum(setting)

                editor.setValidator(
                    QDoubleValidator(
                        -1e100,
                        1e100,
                        12,
                        editor
                    )
                )

                normalized_value = self._normalize_setting_number(
                    value,
                    minimum
                )

                editor.setText(
                    self._format_number(normalized_value)
                )

                if normalized_value != self._safe_float(value):
                    self.setting_values[setting_id] = (
                        normalized_value
                    )
                    self._pending_setting_corrections[
                        setting_id
                    ] = normalized_value

                # Both Enter and focus loss use the same deferred
                # normalization path. This lets Qt finish committing
                # the editor text before it is visibly corrected.
                editor.returnPressed.connect(
                    lambda key=setting_id, field=editor:
                    self._schedule_number_setting_changed(key, field)
                )

                editor.editingFinished.connect(
                    lambda key=setting_id, field=editor:
                    self._schedule_number_setting_changed(key, field)
                )

            else:
                editor.setText(str(value))

                editor.editingFinished.connect(
                    lambda key=setting_id, field=editor:
                    self._text_setting_changed(key, field)
                )

            editor.setToolTip(
                "Number setting" if setting_type == "NUMBER"
                else "Text setting"
            )

            self.setting_inputs[setting_id] = editor

            label = QLabel(name)
            label.setToolTip(name)

            form.addRow(label, editor)

        panel_layout.addLayout(form)

        hint = QLabel(
            "Changes are saved automatically and apply to the next run."
        )
        hint.setStyleSheet("""
            QLabel {
                color: #858b98;
                font-size: 8pt;
            }
        """)

        panel_layout.addWidget(hint)

        self.settings_panel.hide()
        self.card_layout.addWidget(self.settings_panel)

    @staticmethod
    def _safe_float(value):
        try:
            number = float(value)

            if not math.isfinite(number):
                return None

            return number

        except (TypeError, ValueError, OverflowError):
            return None

    @classmethod
    def _normalize_setting_number(cls, value, minimum=None):
        number = cls._safe_float(value)

        if number is None:
            number = minimum if minimum is not None else 0.0

        if minimum is not None:
            number = max(minimum, number)

        return number

    @staticmethod
    def _format_number(value):
        try:
            number = float(value)

            if number != number or number in (
                float("inf"),
                float("-inf")
            ):
                return "0"

            if number.is_integer():
                return str(int(number))

            return str(number)

        except (TypeError, ValueError, OverflowError):
            return "0"

    def _schedule_number_setting_changed(self, setting_id, editor):
        if editor.property("normalization_pending"):
            return

        editor.setProperty("normalization_pending", True)

        def normalize_after_commit():
            editor.setProperty("normalization_pending", False)

            if editor is None:
                return

            self._number_setting_changed(setting_id, editor)

        QTimer.singleShot(0, normalize_after_commit)

    def _number_setting_changed(self, setting_id, editor):
        text = editor.text().strip()

        setting = next(
            (
                item for item in self.settings
                if item.get("id") == setting_id
            ),
            {}
        )

        minimum = self._setting_minimum(setting)

        try:
            value = float(text)

            if not math.isfinite(value):
                raise ValueError

        except (TypeError, ValueError, OverflowError):
            if minimum is not None:
                value = minimum
            else:
                previous = self.setting_values.get(
                    setting_id,
                    0
                )
                value = self._normalize_setting_number(previous)

        if minimum is not None:
            value = max(minimum, value)

        corrected_text = self._format_number(value)

        # Update the actual visible editor before persisting.
        if editor.text() != corrected_text:
            editor.setText(corrected_text)

        self._setting_changed(setting_id, value)

    def _text_setting_changed(self, setting_id, editor):
        self._setting_changed(
            setting_id,
            editor.text()
        )

    def _toggle_settings(self, expanded):
        if self.settings_panel:
            self.settings_panel.setVisible(expanded)

        if self.settings_button:
            self.settings_button.setText("Settings")

            if expanded:
                self.settings_button.setStyleSheet("""
                    QPushButton {
                        background-color: #292436;
                        color: #e5dcff;
                        border: 1px solid #66549a;
                        border-radius: 6px;
                        font-weight: 600;
                    }

                    QPushButton:hover {
                        background-color: #342b48;
                        border-color: #8068b8;
                    }

                    QPushButton:pressed {
                        background-color: #241f32;
                        border-color: #8068b8;
                    }
                """)
            else:
                self.settings_button.setStyleSheet("")

            self.settings_button.style().unpolish(
                self.settings_button
            )
            self.settings_button.style().polish(
                self.settings_button
            )

        self.updateGeometry()

        if self.list_widget:
            self.list_widget.updateGeometry()

    def _setting_changed(self, setting_id, value):
        self.setting_values[setting_id] = value

        if callable(self.setting_callback):
            result = self.setting_callback(
                self.workflow_name,
                setting_id,
                value
            )

            if result is False:
                self.setting_values[setting_id] = value

    def set_status(self, status):
        status = status if status in (
            "Idle", "Running", "Error"
        ) else "Idle"

        self.status_label.setText(status)

        styles = {
            "Idle": (
                "background: #292d36;"
                "color: #a1a1aa;"
                "border: 1px solid #3a3f4a;"
            ),
            "Running": (
                "background: #202f3c;"
                "color: #67c5f5;"
                "border: 1px solid #31536a;"
            ),
            "Error": (
                "background: #3a252a;"
                "color: #f28b91;"
                "border: 1px solid #63343b;"
            ),
        }

        self.status_label.setStyleSheet(
            "QLabel {"
            + styles[status]
            + "border-radius: 10px;"
            + "padding: 1px 8px;"
            + "font-size: 8pt;"
            + "font-weight: 600;"
            + "}"
        )

        self.run_button.setText(
            "Stop" if status == "Running" else "Run"
        )

        if status == "Running":
            self.run_button.setObjectName("stop_button")
            self.run_button.setStyleSheet(
                """
                QPushButton {
                    background-color: #dc454f;
                    color: #ffffff;
                    border: 1px solid #dc454f;
                    border-radius: 6px;
                    font-weight: 600;
                }

                QPushButton:hover {
                    background-color: #ed535d;
                    border-color: #ed535d;
                }

                QPushButton:pressed {
                    background-color: #bd3540;
                    border-color: #ed535d;
                }
                """
            )
        else:
            self.run_button.setObjectName("primary_button")
            self.run_button.setStyleSheet("")

        self.run_button.style().unpolish(self.run_button)
        self.run_button.style().polish(self.run_button)

    def start_drag(self, hotspot):
        self.list_widget.start_card_drag(self, hotspot)


class WorkflowDropArea(QWidget):

    order_changed = Signal()

    def __init__(self):
        super().__init__()

        self.setAcceptDrops(True)
        self.setObjectName("workflow_drop_area")

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred
        )
        self.setMinimumWidth(0)

        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(4, 4, 4, 12)
        self.layout.setSpacing(10)
        self.layout.addStretch()

        self.cards = []

        self.dragged_card = None
        self.original_index = -1
        self.indicator = None
        self.placeholder = None
        self.drop_success = False

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_card_widths()

    def _update_card_widths(self):
        width = max(
            0,
            self.contentsRect().width()
            - self.layout.contentsMargins().left()
            - self.layout.contentsMargins().right()
        )

        for card in self.cards:
            card.setMinimumWidth(0)
            card.setMaximumWidth(16777215)
            card.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed
            )

            if width > 0:
                card.setFixedWidth(width)

        if self.placeholder:
            self.placeholder.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed
            )

    def clear_cards(self):
        self.cards.clear()
        self._remove_indicator()

        if self.placeholder:
            self.layout.removeWidget(self.placeholder)
            self.placeholder.deleteLater()
            self.placeholder = None

        while self.layout.count():
            item = self.layout.takeAt(0)
            widget = item.widget()

            if widget:
                widget.deleteLater()

        self.layout.addStretch()

    def add_card(self, card):
        self.cards.append(card)

        card.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )

        self.layout.insertWidget(
            self.layout.count() - 1,
            card
        )

        self._update_card_widths()

    def set_drag_enabled(self, enabled):
        self.setAcceptDrops(enabled)

    def _remove_indicator(self):
        if self.indicator:
            self.layout.removeWidget(self.indicator)
            self.indicator.deleteLater()
            self.indicator = None

    def _remove_placeholder(self):
        if self.placeholder:
            self.layout.removeWidget(self.placeholder)
            self.placeholder.deleteLater()
            self.placeholder = None

    def _get_drop_index(self, position):
        for index, card in enumerate(self.cards):
            center_y = card.geometry().center().y()

            if position.y() < center_y:
                return index

        return len(self.cards)

    def _show_insertion_indicator(self, index):
        self._remove_indicator()

        if not self.dragged_card:
            return

        self.indicator = QFrame()
        self.indicator.setObjectName("workflow_drop_indicator")
        self.indicator.setFixedHeight(3)

        layout_index = index

        if self.placeholder and index > self.original_index:
            layout_index += 1

        self.layout.insertWidget(
            layout_index,
            self.indicator
        )

    def start_card_drag(self, card, hotspot):
        if self.dragged_card is not None:
            return

        if card not in self.cards:
            return

        self.dragged_card = card
        self.original_index = self.cards.index(card)
        self.drop_success = False

        self.cards.remove(card)
        self.layout.removeWidget(card)

        self.placeholder = QFrame()
        self.placeholder.setObjectName("workflow_drag_placeholder")
        self.placeholder.setFixedHeight(card.height())
        self.placeholder.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed
        )

        self.layout.insertWidget(
            self.original_index,
            self.placeholder
        )

        card.hide()

        drag = QDrag(card)

        mime_data = QMimeData()
        mime_data.setText(card.workflow_name)
        drag.setMimeData(mime_data)

        pixmap = card.grab()

        transparent_pixmap = pixmap.copy()
        transparent_pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(transparent_pixmap)
        painter.setOpacity(0.65)
        painter.drawPixmap(0, 0, pixmap)
        painter.end()

        drag.setPixmap(transparent_pixmap)
        drag.setHotSpot(hotspot)

        drag.exec(Qt.DropAction.MoveAction)

        self._remove_indicator()
        self._remove_placeholder()

        if not self.drop_success:
            self.cards.insert(self.original_index, card)
            self.layout.insertWidget(self.original_index, card)
            card.show()

        self.dragged_card = None
        self.original_index = -1

        self._update_card_widths()

    def dragEnterEvent(self, event):
        if (
            self.dragged_card
            and event.mimeData().hasText()
            and event.mimeData().text() == self.dragged_card.workflow_name
        ):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        if not self.dragged_card:
            event.ignore()
            return

        index = self._get_drop_index(
            event.position().toPoint()
        )

        self._show_insertion_indicator(index)
        event.acceptProposedAction()

    def dragLeaveEvent(self, event):
        self._remove_indicator()
        event.accept()

    def dropEvent(self, event):
        if not self.dragged_card:
            event.ignore()
            return

        index = self._get_drop_index(
            event.position().toPoint()
        )

        self._remove_indicator()
        self._remove_placeholder()

        card = self.dragged_card

        self.cards.insert(index, card)
        self.layout.insertWidget(index, card)

        card.show()

        self.drop_success = True

        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

        self._update_card_widths()
        self.order_changed.emit()

    def sizeHint(self):
        return QSize(
            600,
            max(300, super().sizeHint().height())
        )


class WorkflowListWidget(QScrollArea):

    order_changed = Signal()

    def __init__(self):
        super().__init__()

        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setObjectName("workflow_list")

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding
        )

        self.setMinimumWidth(0)

        self.content = WorkflowDropArea()
        self.content.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred
        )

        self.setWidget(self.content)

        self.content.order_changed.connect(
            self.order_changed.emit
        )

    def clear_cards(self):
        self.content.clear_cards()

    def add_card(self, card):
        self.content.add_card(card)

    def set_drag_enabled(self, enabled):
        self.content.setAcceptDrops(enabled)

    def start_card_drag(self, card, hotspot):
        self.content.start_card_drag(card, hotspot)

    def card_names(self):
        return [
            card.workflow_name
            for card in self.content.cards
        ]
