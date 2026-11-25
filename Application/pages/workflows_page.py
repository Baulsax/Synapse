
import json
import logging
import math
from pathlib import Path

from PySide6.QtCore import (
    Signal,
    Qt,
    QSize,
    QTimer,
    QPropertyAnimation,
    QEasingCurve,
    QEventLoop,
)
from PySide6.QtGui import QIcon, QColor
from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QMessageBox,
    QApplication,
    QDialog,
    QGraphicsOpacityEffect,
    QGraphicsDropShadowEffect,
)

from core.app_paths import (
    get_workflows_dir,
    get_templates_dir,
    WORKFLOW_ORDER_FILE,
    ensure_app_data_dirs,
)

from pages.workflows.share import (
    ImportWorkflowDialog,
    create_share_code,
    decode_share_code,
    is_valid_workflow_name,
)

from pages.workflows.widgets import (
    WorkflowSortComboBox,
    WorkflowCard,
    WorkflowListWidget,
)

from pages.workflows.activity import ActivityPanel


logger = logging.getLogger(__name__)


class NewWorkflowDialog(QWidget):
    """In-page modal overlay for creating a blank workflow or template."""

    def __init__(self, templates, parent=None):
        super().__init__(parent)

        self.templates = templates
        self._result = QDialog.DialogCode.Rejected
        self._event_loop = None

        self.setObjectName("new_workflow_overlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, False)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.setStyleSheet("""
            QWidget#new_workflow_overlay {
                background-color: rgba(0, 0, 0, 155);
            }

            QWidget#new_workflow_panel {
                background-color: #20232b;
                color: #eeeeee;
                border: 1px solid #383b46;
                border-radius: 12px;
            }

            QLabel#new_workflow_title {
                color: #eeeeee;
                font-size: 18px;
                font-weight: 600;
                border: none;
                background: transparent;
            }

            QLabel#new_workflow_subtitle {
                color: #a6a9b4;
                font-size: 13px;
                border: none;
                background: transparent;
            }

            QLabel#new_workflow_field_label {
                color: #d5d7df;
                font-size: 12px;
                font-weight: 600;
                border: none;
                background: transparent;
            }

            QLabel#new_workflow_template_description {
                color: #a6a9b4;
                font-size: 12px;
                border: none;
                background: transparent;
            }

            QLineEdit#new_workflow_name {
                background-color: #17191f;
                color: #eeeeee;
                border: 1px solid #393d49;
                border-radius: 7px;
                padding: 10px 12px;
                font-size: 13px;
                selection-background-color: #8b70d6;
                min-height: 20px;
            }

            QLineEdit#new_workflow_name:focus {
                border: 1px solid #8b70d6;
            }

            QComboBox#workflow_sort {
                background-color: #17191f;
                color: #eeeeee;
                border: 1px solid #393d49;
                border-radius: 7px;
                padding: 8px 34px 8px 12px;
                font-size: 10pt;
                min-height: 22px;
            }

            QComboBox#workflow_sort:hover {
                border-color: #555a69;
            }

            QComboBox#workflow_sort:focus {
                border-color: #8b70d6;
            }

            QComboBox#workflow_sort::drop-down {
                width: 32px;
                border: none;
                background: transparent;
            }

            QComboBox#workflow_sort QAbstractItemView {
                background-color: #20232b;
                color: #eeeeee;
                border: 1px solid #393d49;
                border-radius: 7px;
                padding: 5px;
                outline: none;
                font-size: 10pt;
                selection-background-color: #343044;
                selection-color: #ffffff;
            }

            QComboBox#workflow_sort QAbstractItemView::item {
                min-height: 30px;
                padding: 5px 9px;
                border-radius: 5px;
            }

            QComboBox#workflow_sort QAbstractItemView::item:hover {
                background-color: #292d37;
            }

            QPushButton#new_workflow_cancel {
                background-color: #292d37;
                color: #eeeeee;
                border: 1px solid #393d49;
                border-radius: 7px;
                padding: 9px 16px;
                min-width: 72px;
                min-height: 18px;
                font-size: 13px;
                font-weight: 600;
            }

            QPushButton#new_workflow_cancel:hover {
                background-color: #343946;
                border-color: #505665;
            }

            QPushButton#new_workflow_create {
                background-color: #8b70d6;
                color: #ffffff;
                border: 1px solid #8b70d6;
                border-radius: 7px;
                padding: 9px 18px;
                min-width: 72px;
                min-height: 18px;
                font-size: 13px;
                font-weight: 600;
            }

            QPushButton#new_workflow_create:hover {
                background-color: #a78bfa;
                border-color: #a78bfa;
            }

            QPushButton#new_workflow_create:pressed {
                background-color: #765bbd;
                border-color: #765bbd;
            }
        """)

        overlay_layout = QVBoxLayout(self)
        overlay_layout.setContentsMargins(20, 20, 20, 20)
        overlay_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.panel = QWidget(self)
        self.panel.setObjectName("new_workflow_panel")
        self.panel.setFixedWidth(460)

        shadow = QGraphicsDropShadowEffect(self.panel)
        shadow.setBlurRadius(36)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 125))
        self.panel.setGraphicsEffect(shadow)

        overlay_layout.addWidget(
            self.panel,
            0,
            Qt.AlignmentFlag.AlignCenter
        )

        layout = QVBoxLayout(self.panel)
        layout.setContentsMargins(24, 24, 24, 22)
        layout.setSpacing(8)

        title = QLabel("New Workflow")
        title.setObjectName("new_workflow_title")

        subtitle = QLabel(
            "Choose a name and starting point for your workflow."
        )
        subtitle.setObjectName("new_workflow_subtitle")
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)
        layout.addSpacing(12)

        name_label = QLabel("Workflow Name")
        name_label.setObjectName("new_workflow_field_label")

        self.name_input = QLineEdit()
        self.name_input.setObjectName("new_workflow_name")
        self.name_input.setPlaceholderText("Enter a workflow name...")
        self.name_input.setText("My Workflow")
        self.name_input.setMinimumHeight(40)

        layout.addWidget(name_label)
        layout.addWidget(self.name_input)
        layout.addSpacing(8)

        template_label = QLabel("Starting Template")
        template_label.setObjectName("new_workflow_field_label")

        self.template_combo = WorkflowSortComboBox()
        self.template_combo.setObjectName("workflow_sort")
        self.template_combo.setMinimumHeight(40)
        self.template_combo.setMaxVisibleItems(10)

        self.template_combo.addItem("Blank", None)

        for template in self.templates:
            self.template_combo.addItem(
                template["name"],
                template
            )

        self.template_description = QLabel(
            "Start with an empty workflow."
        )
        self.template_description.setObjectName(
            "new_workflow_template_description"
        )
        self.template_description.setWordWrap(True)
        self.template_description.setMinimumHeight(34)

        self.template_combo.currentIndexChanged.connect(
            self._update_template_description
        )

        layout.addWidget(template_label)
        layout.addWidget(self.template_combo)
        layout.addWidget(self.template_description)
        layout.addSpacing(12)

        button_layout = QHBoxLayout()
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(8)
        button_layout.addStretch()

        cancel_button = QPushButton("Cancel")
        cancel_button.setObjectName("new_workflow_cancel")
        cancel_button.clicked.connect(self.reject)

        create_button = QPushButton("Create")
        create_button.setObjectName("new_workflow_create")
        create_button.setDefault(True)
        create_button.clicked.connect(self.accept)

        button_layout.addWidget(cancel_button)
        button_layout.addWidget(create_button)

        layout.addLayout(button_layout)

        self.name_input.setFocus()
        self.name_input.selectAll()

    def exec(self):
        if self.parentWidget() is None:
            return QDialog.DialogCode.Rejected

        self._result = QDialog.DialogCode.Rejected
        self.setGeometry(self.parentWidget().rect())

        self.show()
        self.raise_()
        self.activateWindow()
        self.name_input.setFocus()
        self.name_input.selectAll()

        self._event_loop = QEventLoop(self)
        self._event_loop.exec()

        result = self._result
        self._event_loop = None

        return result

    def accept(self):
        self.done(QDialog.DialogCode.Accepted)

    def reject(self):
        self.done(QDialog.DialogCode.Rejected)

    def done(self, result):
        self._result = result
        self.hide()

        if self._event_loop is not None:
            self._event_loop.quit()

    def closeEvent(self, event):
        self._result = QDialog.DialogCode.Rejected

        if self._event_loop is not None:
            self._event_loop.quit()

        event.accept()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.reject()
            return

        if (
            event.key() in (
                Qt.Key.Key_Return,
                Qt.Key.Key_Enter
            )
            and self.name_input.hasFocus()
        ):
            self.accept()
            return

        super().keyPressEvent(event)

    def resizeEvent(self, event):
        super().resizeEvent(event)

        if self.parentWidget() is not None:
            self.setGeometry(self.parentWidget().rect())

    def _update_template_description(self, index):
        template = self.template_combo.itemData(index)

        if template is None:
            self.template_description.setText(
                "Start with an empty workflow."
            )
        else:
            self.template_description.setText(
                template.get(
                    "description",
                    "Start with this workflow template."
                )
            )

    def selected_template(self):
        return self.template_combo.currentData()


class WorkflowsPage(QWidget):

    workflow_opened = Signal(str)
    workflow_run_requested = Signal(str)
    workflow_delete_requested = Signal(str)

    def __init__(self):
        super().__init__()

        ensure_app_data_dirs()

        self.custom_order = []
        self.workflow_statuses = {}
        self.activity_history = []

        self._load_order()

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(16)

        header_layout = QHBoxLayout()
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.setSpacing(10)

        title = QLabel("My Workflows")
        title.setObjectName("page_title")
        title.setContentsMargins(0, 0, 0, 0)
        title.setIndent(0)
        title.setAlignment(
            Qt.AlignmentFlag.AlignLeft
            | Qt.AlignmentFlag.AlignVCenter
        )
        title.setStyleSheet("""
            QLabel#page_title {
                padding: 0px;
                margin: 0px;
                border: none;
            }
        """)

        download_icon_path = (
            Path(__file__).parent.parent
            / "assets"
            / "download.svg"
        )

        self.import_button = QPushButton("Import")
        self.import_button.setObjectName("secondary_button")
        self.import_button.setIcon(QIcon(str(download_icon_path)))
        self.import_button.setIconSize(QSize(16, 16))
        self.import_button.setFixedHeight(36)
        self.import_button.clicked.connect(
            self.import_workflow
        )

        new_button = QPushButton("+ New Workflow")
        new_button.setObjectName("primary_button")
        new_button.clicked.connect(self.create_workflow)

        header_layout.addWidget(title)
        header_layout.addStretch()
        header_layout.addWidget(self.import_button)
        header_layout.addWidget(new_button)

        layout.addLayout(header_layout)

        toolbar = QHBoxLayout()
        toolbar.setSpacing(10)

        self.search_input = QLineEdit()
        self.search_input.setObjectName("workflow_search")
        self.search_input.setPlaceholderText(
            "Search workflows..."
        )
        self.search_input.textChanged.connect(
            self.refresh_workflows
        )

        self.sort_combo = WorkflowSortComboBox()
        self.sort_combo.setObjectName("workflow_sort")

        self.sort_combo.addItem("Custom order", "custom")
        self.sort_combo.addItem("Name: A to Z", "name_asc")
        self.sort_combo.addItem("Name: Z to A", "name_desc")
        self.sort_combo.addItem("Recently modified", "newest")
        self.sort_combo.addItem("Oldest modified", "oldest")

        self.sort_combo.currentIndexChanged.connect(
            self.refresh_workflows
        )

        toolbar.addWidget(self.search_input, 1)
        toolbar.addWidget(self.sort_combo)

        layout.addLayout(toolbar)

        self.count_label = QLabel("")
        self.count_label.setObjectName("muted")

        layout.addWidget(self.count_label)

        self.workflow_list = WorkflowListWidget()
        self.workflow_list.order_changed.connect(
            self._save_current_order
        )

        layout.addWidget(self.workflow_list, 1)

        self.empty_label = QLabel("No workflows found.")
        self.empty_label.setObjectName("workflow_empty_state")
        self.empty_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.empty_label.hide()

        layout.addWidget(self.empty_label)

        self.activity_panel = ActivityPanel(self)

        # Keep Activity anchored to the bottom-left instead of
        # allowing it to stretch across the entire page.
        layout.addWidget(
            self.activity_panel,
            0,
            Qt.AlignmentFlag.AlignLeft
        )

        self._update_activity_width()

        self.toast = QLabel(self)
        self.toast.setObjectName("workflow_toast")
        self.toast.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.toast.setAttribute(
            Qt.WidgetAttribute.WA_TransparentForMouseEvents
        )

        self.toast.setStyleSheet("""
            QLabel {
                background-color: #252a34;
                color: #f3f4f6;
                border: 1px solid #3a414e;
                border-radius: 8px;
                padding: 12px 18px;
                font-size: 10pt;
            }
        """)

        self.toast.hide()

        self.toast_opacity = QGraphicsOpacityEffect(self.toast)
        self.toast.setGraphicsEffect(self.toast_opacity)

        self.toast_animation = QPropertyAnimation(
            self.toast_opacity,
            b"opacity",
            self
        )

        self.toast_animation.setDuration(350)
        self.toast_animation.setStartValue(1.0)
        self.toast_animation.setEndValue(0.0)
        self.toast_animation.setEasingCurve(
            QEasingCurve.Type.OutCubic
        )
        self.toast_animation.finished.connect(
            self.toast.hide
        )

        self.toast_timer = QTimer(self)
        self.toast_timer.setSingleShot(True)
        self.toast_timer.timeout.connect(
            self._fade_toast
        )

        self.refresh_workflows()

    # ======================================
    # ACTIVITY PANEL LAYOUT
    # ======================================

    def _update_activity_width(self):
        """
        Keep the Activity panel at approximately half the available
        page width while remaining anchored to the left edge.
        """
        margins = self.layout().contentsMargins()

        available_width = max(
            0,
            self.width() - margins.left() - margins.right()
        )

        self.activity_panel.setFixedWidth(
            int(available_width * 0.5)
        )

    # ======================================
    # STATUS AND ACTIVITY UPDATES
    # ======================================

    def set_workflow_statuses(self, statuses):
        self.workflow_statuses = dict(statuses or {})

        for card in self.workflow_list.content.cards:
            card.set_status(
                self.workflow_statuses.get(
                    card.workflow_name,
                    "Idle"
                )
            )

    def set_activity_history(self, history):
        self.activity_history = list(history or [])

        self.activity_panel.set_history(
            self.activity_history
        )

    # ======================================
    # DYNAMIC STORAGE LOCATIONS
    # ======================================

    @property
    def save_folder(self):
        return get_workflows_dir()

    @property
    def order_file(self):
        return WORKFLOW_ORDER_FILE

    @property
    def templates_folder(self):
        return get_templates_dir()

    @property
    def settings_folder(self):
        return self.save_folder / ".synapse_settings"

    def _settings_path(self, workflow_name):
        return (
            self.settings_folder
            / f"{workflow_name}.json"
        )

    # ======================================
    # TEMPLATE DISCOVERY
    # ======================================

    def _load_templates(self):
        templates = []
        seen_names = set()

        templates_folder = self.templates_folder

        try:
            templates_folder.mkdir(
                parents=True,
                exist_ok=True
            )

            template_files = sorted(
                [
                    *templates_folder.glob("*.txt"),
                    *templates_folder.glob("*.json"),
                ],
                key=lambda path: path.name.casefold()
            )

        except Exception:
            logger.exception(
                "Could not access the templates directory: %s",
                templates_folder
            )
            return templates

        for template_path in template_files:
            try:
                if template_path.suffix.casefold() == ".txt":
                    template = self._load_share_code_template(
                        template_path
                    )
                else:
                    template = self._load_json_template(
                        template_path
                    )

                if template is None:
                    continue

                template_name = template["name"]
                normalized_name = template_name.casefold()

                if normalized_name in seen_names:
                    logger.warning(
                        "Skipping duplicate workflow template name '%s': %s",
                        template_name,
                        template_path
                    )
                    continue

                seen_names.add(normalized_name)
                templates.append(template)

            except Exception:
                logger.exception(
                    "Could not load workflow template: %s",
                    template_path
                )

        return templates

    @staticmethod
    def _validate_template_workflow(workflow_data):
        if not isinstance(workflow_data, dict):
            raise ValueError(
                "Template does not contain valid workflow data."
            )

        blocks_data = workflow_data.get("blocks")

        if (
            not isinstance(blocks_data, dict)
            or not isinstance(blocks_data.get("blocks"), list)
        ):
            raise ValueError(
                "Template contains invalid Blockly workspace data."
            )

        return workflow_data

    def _load_share_code_template(self, template_path):
        share_code = template_path.read_text(
            encoding="utf-8-sig"
        ).strip()

        if not share_code:
            raise ValueError("Template file is empty.")

        embedded_name, workflow_data = decode_share_code(
            share_code
        )

        workflow_data = self._validate_template_workflow(
            workflow_data
        )

        template_name = template_path.stem.strip()

        if not template_name:
            template_name = str(
                embedded_name or "Untitled Template"
            ).strip()

        embedded_name = str(
            embedded_name or "an exported workflow"
        ).strip()

        return {
            "name": template_name,
            "description": (
                f"Based on the exported workflow '{embedded_name}'."
            ),
            "workflow": workflow_data,
            "file": template_path,
        }

    def _load_json_template(self, template_path):
        with open(
            template_path,
            "r",
            encoding="utf-8"
        ) as file:
            template_data = json.load(file)

        if not isinstance(template_data, dict):
            raise ValueError(
                "Template must contain a JSON object."
            )

        workflow_data = self._validate_template_workflow(
            template_data.get("workflow")
        )

        template_name = str(
            template_data.get("name")
            or template_path.stem
        ).strip()

        if not template_name:
            template_name = template_path.stem

        description = str(
            template_data.get("description")
            or "Start with this workflow template."
        ).strip()

        return {
            "name": template_name,
            "description": description,
            "workflow": workflow_data,
            "file": template_path,
        }

    # ======================================
    # WORKFLOW FILE STORAGE
    # ======================================

    @staticmethod
    def _write_json_atomic(path, data):
        path = Path(path)
        path.parent.mkdir(
            parents=True,
            exist_ok=True
        )

        temporary_path = path.with_suffix(
            path.suffix + ".tmp"
        )

        with open(
            temporary_path,
            "w",
            encoding="utf-8"
        ) as file:
            json.dump(
                data,
                file,
                indent=4,
                ensure_ascii=False
            )

        temporary_path.replace(path)

    def _load_workflow_data(self, workflow_name):
        workflow_path = (
            self.save_folder / f"{workflow_name}.json"
        )

        with open(
            workflow_path,
            "r",
            encoding="utf-8"
        ) as file:
            workflow_data = json.load(file)

        if not isinstance(workflow_data, dict):
            raise ValueError("Invalid workflow data.")

        return workflow_path, workflow_data

    # ======================================
    # WORKFLOW BLOCK TRAVERSAL
    # ======================================

    @staticmethod
    def _walk_blocks(blocks):
        if not isinstance(blocks, list):
            return

        for block in blocks:
            if not isinstance(block, dict):
                continue

            yield block

            next_data = block.get("next")

            next_block = (
                next_data.get("block")
                if isinstance(next_data, dict)
                else None
            )

            if next_block:
                yield from WorkflowsPage._walk_blocks(
                    [next_block]
                )

            inputs = block.get("inputs", {})

            if isinstance(inputs, dict):
                for input_data in inputs.values():
                    if not isinstance(input_data, dict):
                        continue

                    child = (
                        input_data.get("block")
                        or input_data.get("shadow")
                    )

                    if child:
                        yield from WorkflowsPage._walk_blocks(
                            [child]
                        )

    @staticmethod
    def _workflow_blocks(workflow_data):
        return (
            workflow_data.get("blocks", {}).get("blocks", [])
            if isinstance(workflow_data, dict)
            and isinstance(workflow_data.get("blocks"), dict)
            else []
        )

    def _find_setting_block(self, workflow_data, setting_id):
        for block in self._walk_blocks(
            self._workflow_blocks(workflow_data)
        ):
            if (
                block.get("type") == "automation_workflow_setting"
                and block.get("id") == setting_id
            ):
                return block

        return None

    # ======================================
    # SETTING VALIDATION
    # ======================================

    @staticmethod
    def _valid_setting_type(value):
        setting_type = str(value or "NUMBER").strip().upper()

        if setting_type in ("TEXT", "STRING"):
            return "TEXT"

        return "NUMBER"

    @staticmethod
    def _valid_number(value, fallback=0):
        try:
            number = float(value)

            if not math.isfinite(number):
                return fallback

            return number

        except (TypeError, ValueError, OverflowError):
            return fallback

    @staticmethod
    def _setting_minimum(name, setting_type):
        """
        The Interval setting has a minimum of 1 millisecond.

        Accept both the original default name ("Interval") and the
        more descriptive name ("Interval (ms)") so older workflows
        and newly created workflows receive identical validation.
        """
        normalized_name = str(name or "").strip().casefold()

        if (
            setting_type == "NUMBER"
            and normalized_name in {
                "interval",
                "interval (ms)",
            }
        ):
            return 1

        return None

    @staticmethod
    def _format_setting_number(number):
        if float(number).is_integer():
            return str(int(number))

        return str(number)

    def _load_legacy_setting_values(self, workflow_name):
        path = self._settings_path(workflow_name)

        try:
            with open(
                path,
                "r",
                encoding="utf-8"
            ) as file:
                stored = json.load(file)

            if isinstance(stored, dict):
                return stored

        except FileNotFoundError:
            return {}

        except Exception:
            logger.exception(
                "Could not read legacy settings for workflow %s.",
                workflow_name
            )

        return {}

    # ======================================
    # LEGACY SETTING MIGRATION
    # ======================================

    def _migrate_workflow_settings(
        self,
        workflow_name,
        workflow_path,
        workflow_data
    ):
        legacy_values = self._load_legacy_setting_values(
            workflow_name
        )

        changed = False
        found_settings = False

        for block in self._walk_blocks(
            self._workflow_blocks(workflow_data)
        ):
            if block.get("type") != "automation_workflow_setting":
                continue

            fields = block.get("fields")

            if not isinstance(fields, dict):
                fields = {}
                block["fields"] = fields
                changed = True

            found_settings = True

            setting_id = block.get("id")

            old_default = fields.get(
                "DEFAULT",
                fields.get("VALUE", "0")
            )

            setting_type = self._valid_setting_type(
                fields.get("TYPE", "NUMBER")
            )

            if setting_id in legacy_values:
                value = legacy_values[setting_id]
                setting_type = "NUMBER"
            else:
                value = fields.get(
                    "VALUE",
                    old_default
                )

            if setting_type == "NUMBER":
                value = self._valid_number(
                    value,
                    self._valid_number(old_default, 0)
                )

                minimum = self._setting_minimum(
                    fields.get("NAME"),
                    setting_type
                )

                if minimum is not None:
                    value = max(minimum, value)

                value = self._format_setting_number(value)

            else:
                value = str(
                    value if value is not None else ""
                )

            if fields.get("TYPE") != setting_type:
                fields["TYPE"] = setting_type
                changed = True

            if str(fields.get("VALUE", "")) != value:
                fields["VALUE"] = value
                changed = True

            for obsolete_field in (
                "DEFAULT",
                "MIN",
                "MAX",
                "STEP"
            ):
                if obsolete_field in fields:
                    del fields[obsolete_field]
                    changed = True

        if changed:
            self._write_json_atomic(
                workflow_path,
                workflow_data
            )

        legacy_path = self._settings_path(workflow_name)

        if legacy_path.exists():
            try:
                legacy_path.unlink()
            except Exception:
                logger.exception(
                    "Could not remove legacy settings file for %s.",
                    workflow_name
                )

        return workflow_data

    # ======================================
    # WORKFLOW SETTING DISCOVERY
    # ======================================

    def _get_workflow_settings(self, workflow_data):
        settings = []
        seen_ids = set()

        for block in self._walk_blocks(
            self._workflow_blocks(workflow_data)
        ):
            if block.get("type") != "automation_workflow_setting":
                continue

            setting_id = block.get("id")

            if not setting_id or setting_id in seen_ids:
                continue

            fields = block.get("fields")

            # Keep malformed setting blocks discoverable rather than
            # silently dropping them and hiding the Settings button.
            if not isinstance(fields, dict):
                fields = {}
                block["fields"] = fields

            setting_type = self._valid_setting_type(
                fields.get("TYPE", "NUMBER")
            )

            setting_name = str(
                fields.get("NAME") or "Setting"
            )

            value = fields.get("VALUE", "")

            if setting_type == "NUMBER":
                value = self._valid_number(value, 0)

                minimum = self._setting_minimum(
                    setting_name,
                    setting_type
                )

                if minimum is not None:
                    value = max(minimum, value)

            else:
                minimum = None
                value = str(
                    value if value is not None else ""
                )

            setting = {
                "id": setting_id,
                "name": setting_name,
                "type": setting_type,
                "value": value,
            }

            if minimum is not None:
                setting["minimum"] = minimum

            settings.append(setting)
            seen_ids.add(setting_id)

        return settings

    # ======================================
    # SAVE WORKFLOW SETTING
    # ======================================

    def save_workflow_setting(
        self,
        workflow_name,
        setting_id,
        value
    ):
        """
        Save a card setting directly into its Blockly block.

        The Blockly block remains the single source of truth.
        Interval values below 1 are normalized to 1 before saving.
        """
        try:
            workflow_path, workflow_data = (
                self._load_workflow_data(workflow_name)
            )

            block = self._find_setting_block(
                workflow_data,
                setting_id
            )

            if block is None:
                logger.warning(
                    "Could not find setting block %s in workflow %s.",
                    setting_id,
                    workflow_name
                )
                self.show_toast(
                    "Could not find workflow setting"
                )
                return False

            fields = block.get("fields")

            if not isinstance(fields, dict):
                fields = {}
                block["fields"] = fields

            setting_type = self._valid_setting_type(
                fields.get("TYPE", "NUMBER")
            )

            if setting_type == "NUMBER":
                number = self._valid_number(
                    value,
                    None
                )

                if number is None:
                    # Invalid or empty input for the Interval setting
                    # is corrected to its minimum instead of leaving
                    # the card with an invalid value.
                    minimum = self._setting_minimum(
                        fields.get("NAME"),
                        setting_type
                    )

                    if minimum is None:
                        self.show_toast(
                            "Please enter a valid number"
                        )
                        return False

                    number = float(minimum)

                minimum = self._setting_minimum(
                    fields.get("NAME"),
                    setting_type
                )

                if minimum is not None:
                    number = max(float(minimum), number)

                stored_value = self._format_setting_number(number)

            else:
                stored_value = str(
                    value if value is not None else ""
                )

            fields["VALUE"] = stored_value

            for obsolete_field in (
                "DEFAULT",
                "MIN",
                "MAX",
                "STEP"
            ):
                fields.pop(obsolete_field, None)

            fields["TYPE"] = setting_type

            self._write_json_atomic(
                workflow_path,
                workflow_data
            )

            return True

        except Exception:
            logger.exception(
                "Could not save setting %s for workflow %s.",
                setting_id,
                workflow_name
            )

            self.show_toast(
                "Could not save workflow setting"
            )

            return False

    # ======================================
    # WORKFLOW ENABLED STATE
    # ======================================

    def save_workflow_enabled(self, workflow_name, enabled):
        try:
            workflow_path, workflow_data = (
                self._load_workflow_data(workflow_name)
            )

            workflow_data["enabled"] = bool(enabled)

            self._write_json_atomic(
                workflow_path,
                workflow_data
            )

            return True

        except Exception:
            logger.exception(
                "Could not save enabled state for workflow %s.",
                workflow_name
            )

            self.show_toast(
                "Could not update workflow status"
            )

            return False

    # ======================================
    # TOAST NOTIFICATION
    # ======================================

    def show_toast(self, message):
        self.toast_timer.stop()
        self.toast_animation.stop()

        self.toast.setText(message)
        self.toast_opacity.setOpacity(1.0)

        self.toast.adjustSize()

        self.toast.move(
            max(12, self.width() - self.toast.width() - 28),
            max(12, self.height() - self.toast.height() - 24)
        )

        self.toast.show()
        self.toast.raise_()

        self.toast_timer.start(2200)

    def _fade_toast(self):
        if self.toast.isVisible():
            self.toast_animation.start()

    def resizeEvent(self, event):
        super().resizeEvent(event)

        self._update_activity_width()

        if self.toast.isVisible():
            self.toast.move(
                max(12, self.width() - self.toast.width() - 28),
                max(12, self.height() - self.toast.height() - 24)
            )

    # ======================================
    # EXPORT
    # ======================================

    def export_workflow(self, workflow_name):
        workflow_path = (
            self.save_folder / f"{workflow_name}.json"
        )

        if not workflow_path.exists():
            QMessageBox.warning(
                self,
                "Export Failed",
                "The workflow file could not be found."
            )
            return

        try:
            with open(
                workflow_path,
                "r",
                encoding="utf-8"
            ) as file:
                workflow_data = json.load(file)

            if not isinstance(workflow_data, dict):
                raise ValueError("Invalid workflow data.")

            share_data = dict(workflow_data)
            share_data.pop("enabled", None)

            share_code = create_share_code(
                workflow_name,
                share_data
            )

            QApplication.clipboard().setText(share_code)

            self.show_toast(
                "✓ Workflow copied to clipboard"
            )

        except Exception:
            logger.exception(
                "Could not export workflow %s",
                workflow_name
            )

            QMessageBox.critical(
                self,
                "Export Failed",
                "Could not export this workflow.\n\n"
                "Check the application log for details."
            )

    # ======================================
    # IMPORT
    # ======================================

    def import_workflow(self):
        dialog = ImportWorkflowDialog(self)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        if dialog.workflow_data is None:
            return

        workflow_name = dialog.name_input.text().strip()

        if not is_valid_workflow_name(workflow_name):
            QMessageBox.warning(
                self,
                "Invalid Workflow Name",
                "Please enter a valid workflow name.\n\n"
                'Names cannot contain: < > : " / \\ | ? *'
            )
            return

        ensure_app_data_dirs()

        save_folder = self.save_folder
        save_folder.mkdir(parents=True, exist_ok=True)

        existing_names = {
            path.stem.casefold()
            for path in save_folder.glob("*.json")
        }

        if workflow_name.casefold() in existing_names:
            QMessageBox.warning(
                self,
                "Workflow Already Exists",
                f"A workflow named '{workflow_name}' already exists.\n\n"
                "Choose a different name to avoid overwriting it."
            )
            return

        save_path = save_folder / f"{workflow_name}.json"

        try:
            imported_data = json.loads(
                json.dumps(
                    dialog.workflow_data,
                    ensure_ascii=False
                )
            )

            imported_data["enabled"] = True

            with open(
                save_path,
                "x",
                encoding="utf-8"
            ) as file:
                json.dump(
                    imported_data,
                    file,
                    indent=4,
                    ensure_ascii=False
                )

        except FileExistsError:
            QMessageBox.warning(
                self,
                "Workflow Already Exists",
                "A workflow with that name already exists."
            )
            return

        except Exception as error:
            logger.exception(
                "Could not import workflow %s",
                workflow_name
            )

            QMessageBox.critical(
                self,
                "Import Failed",
                f"Could not import the workflow:\n{error}"
            )
            return

        self.custom_order.append(workflow_name)
        self._save_order()
        self.refresh_workflows()

        self.show_toast(
            f"✓ Imported '{workflow_name}'"
        )

    # ======================================
    # ORDERING
    # ======================================

    def _load_order(self):
        if not self.order_file.exists():
            return

        try:
            with open(
                self.order_file,
                "r",
                encoding="utf-8"
            ) as file:
                data = json.load(file)

            if isinstance(data, list):
                self.custom_order = data

        except Exception:
            self.custom_order = []

    def _save_order(self):
        try:
            ensure_app_data_dirs()

            self.order_file.parent.mkdir(
                parents=True,
                exist_ok=True
            )

            with open(
                self.order_file,
                "w",
                encoding="utf-8"
            ) as file:
                json.dump(
                    self.custom_order,
                    file,
                    indent=4
                )

        except Exception:
            logger.exception(
                "Could not save workflow order."
            )

    def _save_current_order(self):
        visible_names = self.workflow_list.card_names()

        visible_set = set(visible_names)
        visible_index = 0

        updated_order = []

        for name in self.custom_order:
            if name in visible_set:
                if visible_index < len(visible_names):
                    updated_order.append(
                        visible_names[visible_index]
                    )
                    visible_index += 1
            else:
                updated_order.append(name)

        while visible_index < len(visible_names):
            updated_order.append(
                visible_names[visible_index]
            )
            visible_index += 1

        self.custom_order = updated_order
        self._save_order()

    def _get_workflows(self):
        ensure_app_data_dirs()

        workflows_folder = self.save_folder
        workflows_folder.mkdir(parents=True, exist_ok=True)

        workflows = []

        for workflow_file in workflows_folder.glob("*.json"):
            workflows.append({
                "name": workflow_file.stem,
                "modified": workflow_file.stat().st_mtime
            })

        existing_names = {
            item["name"] for item in workflows
        }

        self.custom_order = [
            name for name in self.custom_order
            if name in existing_names
        ]

        for item in workflows:
            if item["name"] not in self.custom_order:
                self.custom_order.append(item["name"])

        self._save_order()

        sort_mode = self.sort_combo.currentData()

        if sort_mode == "custom":
            order_lookup = {
                name: index
                for index, name in enumerate(self.custom_order)
            }

            workflows.sort(
                key=lambda item: order_lookup.get(
                    item["name"],
                    len(order_lookup)
                )
            )

        elif sort_mode == "name_asc":
            workflows.sort(
                key=lambda item: item["name"].lower()
            )

        elif sort_mode == "name_desc":
            workflows.sort(
                key=lambda item: item["name"].lower(),
                reverse=True
            )

        elif sort_mode == "newest":
            workflows.sort(
                key=lambda item: item["modified"],
                reverse=True
            )

        elif sort_mode == "oldest":
            workflows.sort(
                key=lambda item: item["modified"]
            )

        return workflows

    # ======================================
    # REFRESH
    # ======================================

    def refresh_workflows(self):
        self.workflow_list.clear_cards()

        search = self.search_input.text().strip().lower()
        workflows = self._get_workflows()

        visible_workflows = [
            item for item in workflows
            if search in item["name"].lower()
        ]

        self.count_label.setText(
            f"{len(visible_workflows)} workflow"
            + ("" if len(visible_workflows) == 1 else "s")
        )

        custom_sort = (
            self.sort_combo.currentData() == "custom"
        )

        self.workflow_list.set_drag_enabled(
            custom_sort and not search
        )

        self.empty_label.setVisible(
            len(visible_workflows) == 0
        )

        self.workflow_list.setVisible(
            len(visible_workflows) > 0
        )

        for workflow in visible_workflows:
            name = workflow["name"]

            settings = []
            enabled = True
            workflow_path = None
            workflow_data = None

            # Load the workflow independently. A settings migration
            # failure must not prevent settings discovery.
            try:
                workflow_path, workflow_data = (
                    self._load_workflow_data(name)
                )

                stored_enabled = workflow_data.get(
                    "enabled",
                    True
                )

                enabled = (
                    stored_enabled
                    if isinstance(stored_enabled, bool)
                    else True
                )

            except Exception:
                logger.exception(
                    "Could not load workflow data for %s.",
                    name
                )

            if workflow_data is not None:
                # Migration is best-effort. Even if writing a migrated
                # file fails, continue discovering settings from the
                # original data so the Settings button remains present.
                try:
                    workflow_data = self._migrate_workflow_settings(
                        name,
                        workflow_path,
                        workflow_data
                    )

                except Exception:
                    logger.exception(
                        "Could not migrate settings for workflow %s.",
                        name
                    )

                try:
                    settings = self._get_workflow_settings(
                        workflow_data
                    )

                except Exception:
                    logger.exception(
                        "Could not discover settings for workflow %s.",
                        name
                    )
                    settings = []

            card = WorkflowCard(
                name,
                self.workflow_list,
                self.workflow_opened.emit,
                self.workflow_run_requested.emit,
                self.workflow_delete_requested.emit,
                self.export_workflow,
                self.workflow_statuses.get(name, "Idle"),
                settings=settings,
                setting_values={},
                setting_callback=self.save_workflow_setting,
                enabled=enabled,
                enabled_callback=self.save_workflow_enabled
            )

            self.workflow_list.add_card(card)

    # ======================================
    # CREATE
    # ======================================

    def create_workflow(self):
        templates = self._load_templates()

        dialog = NewWorkflowDialog(
            templates,
            self
        )

        if dialog.exec() != QDialog.DialogCode.Accepted:
            dialog.deleteLater()
            return

        workflow_name = dialog.name_input.text().strip()
        selected_template = dialog.selected_template()

        dialog.deleteLater()

        if not workflow_name:
            QMessageBox.warning(
                self,
                "Invalid Name",
                "Please enter a name for your workflow."
            )
            return

        if not is_valid_workflow_name(workflow_name):
            QMessageBox.warning(
                self,
                "Invalid Name",
                "Workflow names cannot contain these characters:\n"
                '< > : " / \\ | ? *'
            )
            return

        ensure_app_data_dirs()

        save_folder = self.save_folder
        save_folder.mkdir(parents=True, exist_ok=True)

        save_path = save_folder / f"{workflow_name}.json"

        existing_names = {
            path.stem.casefold()
            for path in save_folder.glob("*.json")
        }

        if workflow_name.casefold() in existing_names:
            QMessageBox.warning(
                self,
                "Already Exists",
                "A workflow with that name already exists."
            )
            return

        if selected_template is None:
            workflow_data = {
                "blocks": {
                    "languageVersion": 0,
                    "blocks": []
                }
            }
        else:
            try:
                workflow_data = json.loads(
                    json.dumps(
                        selected_template["workflow"],
                        ensure_ascii=False
                    )
                )

            except Exception:
                logger.exception(
                    "Could not copy template %s.",
                    selected_template.get("name", "Unknown")
                )

                QMessageBox.critical(
                    self,
                    "Template Error",
                    "Could not create a copy of this workflow template."
                )
                return

        workflow_data["enabled"] = True

        try:
            self._write_json_atomic(
                save_path,
                workflow_data
            )

        except Exception as error:
            QMessageBox.critical(
                self,
                "Creation Failed",
                f"Could not create workflow:\n{error}"
            )
            return

        self.custom_order.append(workflow_name)
        self._save_order()
        self.refresh_workflows()

        self.show_toast(
            f"✓ Created '{workflow_name}'"
        )

    # ======================================
    # DELETE / RENAME REFRESH
    # ======================================

    def refresh_after_delete(self):
        self.refresh_workflows()

    def rename_workflow(self, old_name, new_name):
        self.custom_order = [
            new_name if name == old_name else name
            for name in self.custom_order
        ]

        if old_name in self.workflow_statuses:
            self.workflow_statuses[new_name] = (
                self.workflow_statuses.pop(old_name)
            )

        self._save_order()
        self.refresh_workflows()
