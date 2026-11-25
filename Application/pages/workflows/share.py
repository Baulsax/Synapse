
import base64
import json
import zlib

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QLineEdit,
    QMessageBox,
    QDialogButtonBox,
    QTextEdit,
)

from pathlib import Path


SHARE_CODE_PREFIX = "AS1:"
SHARE_FORMAT = "automation-studio-workflow"
SHARE_FORMAT_VERSION = 1

MAX_SHARE_CODE_LENGTH = 8 * 1024 * 1024
MAX_DECOMPRESSED_SIZE = 10 * 1024 * 1024


def is_valid_workflow_name(name):
    name = name.strip()

    if not name:
        return False

    invalid_characters = '<>:"/\\|?*'

    if any(char in name for char in invalid_characters):
        return False

    if name.endswith(".") or name.endswith(" "):
        return False

    reserved_names = {
        "CON", "PRN", "AUX", "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }

    return name.upper() not in reserved_names


def create_share_code(workflow_name, workflow_data):
    package = {
        "format": SHARE_FORMAT,
        "version": SHARE_FORMAT_VERSION,
        "name": workflow_name,
        "workflow": workflow_data,
    }

    json_data = json.dumps(
        package,
        ensure_ascii=False,
        separators=(",", ":")
    ).encode("utf-8")

    compressed = zlib.compress(json_data, level=9)

    encoded = base64.urlsafe_b64encode(
        compressed
    ).decode("ascii").rstrip("=")

    return SHARE_CODE_PREFIX + encoded


def decode_share_code(share_code):
    share_code = share_code.strip()

    if not share_code.startswith(SHARE_CODE_PREFIX):
        raise ValueError(
            "This doesn't look like a Synapse workflow share code."
        )

    if len(share_code) > MAX_SHARE_CODE_LENGTH:
        raise ValueError(
            "This share code is too large to import."
        )

    encoded = share_code[len(SHARE_CODE_PREFIX):]

    if not encoded:
        raise ValueError("The share code is empty.")

    try:
        padded = encoded + ("=" * (-len(encoded) % 4))

        compressed = base64.b64decode(
            padded,
            altchars=b"-_",
            validate=True
        )

        decompressor = zlib.decompressobj()

        json_data = decompressor.decompress(
            compressed,
            MAX_DECOMPRESSED_SIZE + 1
        )

        if len(json_data) > MAX_DECOMPRESSED_SIZE:
            raise ValueError(
                "The imported workflow is too large."
            )

        if decompressor.unconsumed_tail:
            raise ValueError(
                "The imported workflow is too large."
            )

        json_data += decompressor.flush()

        if len(json_data) > MAX_DECOMPRESSED_SIZE:
            raise ValueError(
                "The imported workflow is too large."
            )

        if not decompressor.eof:
            raise ValueError(
                "The share code appears to be incomplete."
            )

        package = json.loads(json_data.decode("utf-8"))

    except ValueError:
        raise

    except Exception as error:
        raise ValueError(
            "The share code is invalid or corrupted."
        ) from error

    if not isinstance(package, dict):
        raise ValueError("The share code contains invalid data.")

    if package.get("format") != SHARE_FORMAT:
        raise ValueError(
            "This isn't a supported workflow format."
        )

    if package.get("version") != SHARE_FORMAT_VERSION:
        raise ValueError(
            "This workflow was exported using an unsupported format version."
        )

    workflow_name = package.get("name")
    workflow_data = package.get("workflow")

    if not isinstance(workflow_name, str) or not workflow_name.strip():
        raise ValueError(
            "The share code doesn't contain a valid workflow name."
        )

    if not isinstance(workflow_data, dict):
        raise ValueError(
            "The share code doesn't contain valid workflow data."
        )

    blocks = workflow_data.get("blocks")

    if not isinstance(blocks, dict):
        raise ValueError(
            "The workflow data is missing its Blockly workspace."
        )

    if not isinstance(blocks.get("blocks"), list):
        raise ValueError(
            "The workflow contains an invalid Blockly workspace."
        )

    return workflow_name.strip(), workflow_data


class ImportWorkflowDialog(QDialog):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setWindowTitle("Import Workflow")
        self.setMinimumWidth(480)
        self.setMinimumHeight(390)

        self.workflow_data = None
        self.original_name = ""
        self.name_manually_edited = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 18)
        layout.setSpacing(12)

        title = QLabel("Import Workflow")
        title.setObjectName("page_title")

        description = QLabel(
            "Paste a Synapse workflow share code below."
        )
        description.setObjectName("muted")
        description.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(description)

        code_label = QLabel("Share Code")
        code_label.setObjectName("property_label")
        layout.addWidget(code_label)

        self.code_input = QTextEdit()
        self.code_input.setObjectName("workflow_import_code")
        self.code_input.setPlaceholderText(
            "Paste workflow code here..."
        )
        self.code_input.setAcceptRichText(False)
        self.code_input.setMinimumHeight(115)
        self.code_input.textChanged.connect(
            self.validate_share_code
        )

        layout.addWidget(self.code_input)

        self.status_label = QLabel(
            "Waiting for a share code..."
        )
        self.status_label.setObjectName("muted")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        name_label = QLabel("Workflow Name")
        name_label.setObjectName("property_label")
        layout.addWidget(name_label)

        self.name_input = QLineEdit()
        self.name_input.setObjectName("workflow_import_name")
        self.name_input.setPlaceholderText(
            "Original workflow name"
        )
        self.name_input.textEdited.connect(
            self.on_name_edited
        )

        layout.addWidget(self.name_input)
        layout.addStretch()

        self.button_box = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
        )

        self.import_button = self.button_box.button(
            QDialogButtonBox.StandardButton.Ok
        )

        self.import_button.setText("Import Workflow")
        self.import_button.setEnabled(False)
        self.import_button.setObjectName("primary_button")

        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)

        layout.addWidget(self.button_box)

    def on_name_edited(self, _text):
        self.name_manually_edited = True

    def validate_share_code(self):
        code = self.code_input.toPlainText().strip()

        if not code:
            self.workflow_data = None
            self.original_name = ""
            self.import_button.setEnabled(False)
            self.status_label.setText(
                "Waiting for a share code..."
            )
            return

        try:
            workflow_name, workflow_data = decode_share_code(code)

            self.workflow_data = workflow_data
            self.original_name = workflow_name

            if not self.name_manually_edited:
                self.name_input.setText(workflow_name)

            self.status_label.setText(
                f"Valid workflow detected: {workflow_name}"
            )
            self.import_button.setEnabled(True)

        except ValueError as error:
            self.workflow_data = None
            self.original_name = ""
            self.import_button.setEnabled(False)
            self.status_label.setText(str(error))
