
// ==========================================
// INPUT CAPTURE FIELD
// ==========================================

class InputCaptureField extends Blockly.FieldTextInput {
    constructor() {
        super("Click to add an input");
    }

    showEditor_() {
        const block = this.getSourceBlock();

        if (window.bridge && block) {
            window.bridge.request_input_capture(block.id);
        }
    }
}


// ==========================================
// SHARED INPUT BLOCK CREATION
// ==========================================

function createInputBlock(type, label, device, control, colour) {
    Blockly.Blocks[type] = {
        init: function () {
            this.appendDummyInput()
                .appendField(label);

            this.setOutput(true, "automation_input");
            this.setColour(colour);

            this.setTooltip(
                `Use ${label} as an input trigger.`
            );

            this.inputDevice = device;
            this.inputControl = control;
        },

        saveExtraState: function () {
            return {
                device: device,
                control: control
            };
        }
    };
}


// ==========================================
// KEYBOARD INPUTS
// ==========================================

const KEY_GROUPS = {
    "Letters": [
        ...Array.from("ABCDEFGHIJKLMNOPQRSTUVWXYZ")
            .map(key => [key, key])
    ],

    "Numbers": [
        ...Array.from("0123456789")
            .map(key => [key, key])
    ],

    "Function Keys": [
        ...Array.from({ length: 24 }, (_, i) => {
            const key = `F${i + 1}`;
            return [key, key];
        })
    ],

    "Punctuation": [
        ["Semicolon ;", ";"],
        ["Apostrophe '", "'"],
        ["Slash /", "/"],
        ["Backslash \\", "\\"],
        ["Comma ,", ","],
        ["Period .", "."],
        ["Grave Accent `", "`"],
        ["Left Bracket [", "["],
        ["Right Bracket ]", "]"],
        ["Equals =", "="],
        ["Minus -", "-"]
    ],

    "Modifiers": [
        ["Shift", "SHIFT"],
        ["Ctrl", "CTRL"],
        ["Alt", "ALT"],
        ["Left Windows", "LWIN"],
        ["Right Windows", "RWIN"]
    ],

    "Navigation": [
        ["Up", "UP"],
        ["Down", "DOWN"],
        ["Left", "LEFT"],
        ["Right", "RIGHT"],
        ["Home", "HOME"],
        ["End", "END"],
        ["Page Up", "PAGEUP"],
        ["Page Down", "PAGEDOWN"]
    ],

    "Editing": [
        ["Backspace", "BACKSPACE"],
        ["Delete", "DELETE"],
        ["Insert", "INSERT"],
        ["Enter", "ENTER"],
        ["Tab", "TAB"],
        ["Escape", "ESC"],
        ["Space", "SPACE"]
    ],

    "Numpad": [
        ...Array.from({ length: 10 }, (_, i) => [
            `Numpad ${i}`,
            `NUM${i}`
        ]),
        ["Numpad Add", "NUM_ADD"],
        ["Numpad Subtract", "NUM_SUBTRACT"],
        ["Numpad Multiply", "NUM_MULTIPLY"],
        ["Numpad Divide", "NUM_DIVIDE"],
        ["Numpad Decimal", "NUM_DECIMAL"],
        ["Num Lock", "NUMLOCK"]
    ],

    "System": [
        ["Caps Lock", "CAPSLOCK"],
        ["Print Screen", "PRINTSCREEN"],
        ["Scroll Lock", "SCROLLLOCK"],
        ["Pause", "PAUSE"],
        ["Application Menu", "APPS"]
    ]
};


const KEY_TYPE_MAP = {};

function keyBlockType(label, control) {
    const slug = control
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "_");

    const type = `automation_key_${slug}`;

    createInputBlock(
        type,
        label,
        "Keyboard",
        control,
        210
    );

    KEY_TYPE_MAP[control] = type;

    return type;
}


const keyboardToolbox = [];

for (const [groupName, keys] of Object.entries(KEY_GROUPS)) {
    const contents = keys.map(([label, control]) => ({
        kind: "block",
        type: keyBlockType(label, control)
    }));

    keyboardToolbox.push({
        kind: "category",
        name: groupName,
        colour: "#6495c8",
        contents
    });
}


// ==========================================
// KEYBOARD ACTION OPTIONS
// ==========================================

const KEY_ACTION_OPTIONS = Object.values(KEY_GROUPS)
    .flat()
    .map(([label, control]) => [label, control]);


// ==========================================
// MOUSE INPUTS
// ==========================================

const MOUSE_INPUTS = [
    ["Left Button", "LEFT"],
    ["Right Button", "RIGHT"],
    ["Middle Button", "MIDDLE"],
    ["Side Button 1", "X1"],
    ["Side Button 2", "X2"],
    ["Scroll Up", "SCROLL_UP"],
    ["Scroll Down", "SCROLL_DOWN"]
];

const mouseToolbox = [];

for (const [label, control] of MOUSE_INPUTS) {
    const type = `automation_mouse_${control.toLowerCase()}`;

    createInputBlock(
        type,
        label,
        "Mouse",
        control,
        140
    );

    mouseToolbox.push({
        kind: "block",
        type
    });
}


// ==========================================
// LISTENER INPUT
// ==========================================

Blockly.Blocks["automation_input_listener"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Listen for:")
            .appendField(
                new InputCaptureField(),
                "CONTROL"
            )
            .appendField(
                new Blockly.FieldTextInput(""),
                "DEVICE"
            );

        this.getField("DEVICE").setVisible(false);

        this.setOutput(true, "automation_input");
        this.setColour(45);

        this.setTooltip(
            "Capture a keyboard or permitted mouse input. " +
            "Left, right and middle mouse clicks cannot be captured."
        );
    }
};


// ==========================================
// GLOBAL VARIABLE
// ==========================================

Blockly.Blocks["automation_workflow_setting"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Global Variable")
            .appendField(
                new Blockly.FieldTextInput("Interval"),
                "NAME"
            );

        this.appendDummyInput()
            .appendField("Type:")
            .appendField(
                new Blockly.FieldDropdown([
                    ["Number", "NUMBER"],
                    ["Text", "TEXT"]
                ]),
                "TYPE"
            );

        this.appendDummyInput()
            .appendField("Value:")
            .appendField(
                new Blockly.FieldTextInput("1000"),
                "VALUE"
            );

        this.setInputsInline(false);
        this.setOutput(true, "Number");
        this.setColour(45);

        this.setTooltip(
            "Create a global variable with a number or text value. " +
            "Its value can be customized directly from the workflow card."
        );

        this.setOnChange(function () {
            if (!this.outputConnection) {
                return;
            }

            const type = this.getFieldValue("TYPE");

            this.outputConnection.setCheck(
                type === "TEXT" ? "String" : "Number"
            );

            const rawValue = this.getFieldValue("VALUE");

            if (type === "NUMBER") {
                const numericValue = Number(rawValue);

                if (
                    String(rawValue).trim() === "" ||
                    !Number.isFinite(numericValue)
                ) {
                    this.setWarningText(
                        "Enter a valid number for this global variable."
                    );
                    return;
                }
            }

            this.setWarningText(null);
        });
    }
};


// ==========================================
// TIMING
// ==========================================

Blockly.Blocks["automation_wait"] = {
    init: function () {
        this.appendValueInput("DURATION")
            .setCheck("Number")
            .appendField("Wait for");

        this.appendDummyInput()
            .appendField("milliseconds");

        this.setInputsInline(true);
        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(285);

        this.setTooltip(
            "Pause the workflow for the connected number of milliseconds. " +
            "Minimum duration: 1 millisecond inside continuous loops."
        );
    }
};


// ==========================================
// MOUSE ACTIONS
// ==========================================

Blockly.Blocks["automation_left_click"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Left Click");

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(140);

        this.setTooltip("Perform a left mouse click.");
    }
};


Blockly.Blocks["automation_mouse_click"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Click")
            .appendField(
                new Blockly.FieldDropdown([
                    ["Left Button", "LEFT"],
                    ["Right Button", "RIGHT"],
                    ["Middle Button", "MIDDLE"],
                    ["Side Button 1", "X1"],
                    ["Side Button 2", "X2"]
                ]),
                "BUTTON"
            );

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(140);

        this.setTooltip(
            "Click the selected mouse button."
        );
    }
};


Blockly.Blocks["automation_mouse_move"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Move Mouse to X:")
            .appendField(
                new Blockly.FieldNumber(0),
                "X"
            )
            .appendField("Y:")
            .appendField(
                new Blockly.FieldNumber(0),
                "Y"
            );

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(140);

        this.setTooltip(
            "Move the mouse cursor to an absolute screen position."
        );
    }
};


Blockly.Blocks["automation_mouse_scroll"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Scroll")
            .appendField(
                new Blockly.FieldNumber(1),
                "AMOUNT"
            )
            .appendField("notches");

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(140);

        this.setTooltip(
            "Scroll vertically. Positive values scroll up; negative values scroll down."
        );
    }
};


// ==========================================
// KEYBOARD ACTIONS
// ==========================================

Blockly.Blocks["automation_key_press"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Press Key")
            .appendField(
                new Blockly.FieldDropdown(KEY_ACTION_OPTIONS),
                "KEY"
            );

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(210);

        this.setTooltip(
            "Press and immediately release the selected key."
        );
    }
};


Blockly.Blocks["automation_key_down"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Key Down")
            .appendField(
                new Blockly.FieldDropdown(KEY_ACTION_OPTIONS),
                "KEY"
            );

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(210);

        this.setTooltip(
            "Hold the selected key down until a Key Up action releases it."
        );
    }
};


Blockly.Blocks["automation_key_up"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Key Up")
            .appendField(
                new Blockly.FieldDropdown(KEY_ACTION_OPTIONS),
                "KEY"
            );

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(210);

        this.setTooltip(
            "Release a previously held key."
        );
    }
};


Blockly.Blocks["automation_type_text"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Type Text:")
            .appendField(
                new Blockly.FieldTextInput("Hello world"),
                "TEXT"
            );

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(210);

        this.setTooltip(
            "Type the supplied text using the keyboard."
        );
    }
};


// ==========================================
// TRIGGERS
// ==========================================

Blockly.Blocks["automation_input_trigger"] = {
    init: function () {
        this.appendValueInput("INPUT")
            .setCheck("automation_input")
            .appendField("When this input is pressed:");

        this.appendDummyInput()
            .appendField("Action:")
            .appendField(
                new Blockly.FieldDropdown([
                    ["Start workflow", "START"],
                    ["Toggle start / stop", "TOGGLE"],
                    ["Stop workflow", "STOP"]
                ]),
                "MODE"
            );

        this.setNextStatement(true);
        this.setColour(45);

        this.setTooltip(
            "Run this workflow when the connected input is pressed."
        );
    }
};


Blockly.Blocks["automation_stop_if_input"] = {
    init: function () {
        this.appendValueInput("INPUT")
            .setCheck("automation_input")
            .appendField("Stop workflow if input pressed:");

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(45);

        this.setTooltip(
            "Stop this workflow when the connected input is pressed."
        );
    }
};


// ==========================================
// LOOPS
// ==========================================

Blockly.Blocks["automation_repeat_until_stopped"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Repeat until stopped");

        this.appendStatementInput("DO")
            .appendField("Do");

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(120);

        this.setTooltip(
            "Continuously repeat these actions until stopped. " +
            "The engine enforces a minimum 1 ms interval per iteration."
        );
    }
};


Blockly.Blocks["automation_break_loop"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Break Loop");

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(120);

        this.setTooltip(
            "Exit the nearest enclosing loop."
        );
    }
};


// ==========================================
// UI GEOMETRY
// ==========================================

function addElementGeometry(block) {
    const geometryInput = block.appendDummyInput(
        "GEOMETRY_INTERNAL"
    );

    geometryInput
        .appendField(
            new Blockly.FieldDropdown([
                ["Automatic", "AUTO"],
                ["Custom", "CUSTOM"]
            ]),
            "LAYOUT"
        )
        .appendField(
            new Blockly.FieldNumber(10, -10000, 10000),
            "X"
        )
        .appendField(
            new Blockly.FieldNumber(10, -10000, 10000),
            "Y"
        )
        .appendField(
            new Blockly.FieldNumber(200, 1, 2000),
            "WIDTH"
        )
        .appendField(
            new Blockly.FieldNumber(30, 1, 2000),
            "HEIGHT"
        );

    geometryInput.setVisible(false);
}


// ==========================================
// UI BLOCKS
// ==========================================

// Create Window

Blockly.Blocks["automation_ui_create_window"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Create Window");

        this.appendDummyInput()
            .appendField("Window ID:")
            .appendField(
                new Blockly.FieldTextInput("main"),
                "WINDOW_ID"
            );

        this.appendDummyInput()
            .appendField("Title:")
            .appendField(
                new Blockly.FieldTextInput("My Window"),
                "TITLE"
            );

        this.appendDummyInput()
            .appendField("Width:")
            .appendField(
                new Blockly.FieldNumber(400, 100, 2000),
                "WIDTH"
            )
            .appendField("Height:")
            .appendField(
                new Blockly.FieldNumber(300, 100, 2000),
                "HEIGHT"
            );

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(285);

        this.setTooltip(
            "Create and show a standalone window. " +
            "Use its Window ID when adding widgets."
        );
    }
};


// Create Label

Blockly.Blocks["automation_ui_create_label"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Create Label");

        this.appendDummyInput()
            .appendField("Window ID:")
            .appendField(
                new Blockly.FieldTextInput("main"),
                "WINDOW_ID"
            );

        this.appendDummyInput()
            .appendField("Widget ID:")
            .appendField(
                new Blockly.FieldTextInput("label1"),
                "WIDGET_ID"
            );

        this.appendValueInput("TEXT")
            .setCheck("String")
            .appendField("Text:");

        addElementGeometry(this);

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(285);

        this.setTooltip(
            "Add a text label to an existing window. " +
            "Position and size can be adjusted in the Properties panel."
        );
    }
};


// Create Button

Blockly.Blocks["automation_ui_create_button"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Create Button");

        this.appendDummyInput()
            .appendField("Window ID:")
            .appendField(
                new Blockly.FieldTextInput("main"),
                "WINDOW_ID"
            );

        this.appendDummyInput()
            .appendField("Widget ID:")
            .appendField(
                new Blockly.FieldTextInput("button1"),
                "WIDGET_ID"
            );

        this.appendValueInput("TEXT")
            .setCheck("String")
            .appendField("Text:");

        addElementGeometry(this);

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(285);

        this.setTooltip(
            "Add a clickable button to an existing window. " +
            "Position and size can be adjusted in the Properties panel."
        );
    }
};


// Set Text

Blockly.Blocks["automation_ui_set_text"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("Set Text");

        this.appendDummyInput()
            .appendField("Widget ID:")
            .appendField(
                new Blockly.FieldTextInput("label1"),
                "WIDGET_ID"
            );

        this.appendValueInput("TEXT")
            .setCheck("String")
            .appendField("New Text:");

        this.setPreviousStatement(true);
        this.setNextStatement(true);
        this.setColour(285);

        this.setTooltip(
            "Change the displayed text of an existing label or button."
        );
    }
};


// When Button Clicked

Blockly.Blocks["automation_ui_button_clicked"] = {
    init: function () {
        this.appendDummyInput()
            .appendField("When Button Clicked");

        this.appendDummyInput()
            .appendField("Button ID:")
            .appendField(
                new Blockly.FieldTextInput("button1"),
                "BUTTON_ID"
            );

        this.setNextStatement(true);
        this.setColour(45);

        this.setTooltip(
            "Run the connected actions whenever the specified button is clicked."
        );
    }
};


// ==========================================
// TOOLBOX
// ==========================================

const workspace = Blockly.inject("blocklyDiv", {
    media: "../node_modules/blockly/media/",

    toolbox: {
        kind: "categoryToolbox",
        contents: [
            {
                kind: "category",
                name: "Triggers",
                colour: "#e6a23c",
                contents: [
                    { kind: "block", type: "automation_input_trigger" },
                    { kind: "block", type: "automation_stop_if_input" }
                ]
            },
            {
                kind: "category",
                name: "Keyboard",
                colour: "#6495c8",
                contents: keyboardToolbox
            },
            {
                kind: "category",
                name: "Mouse",
                colour: "#5b9a52",
                contents: mouseToolbox
            },
            {
                kind: "category",
                name: "Input",
                colour: "#e6a23c",
                contents: [
                    { kind: "block", type: "automation_input_listener" }
                ]
            },
            {
                kind: "category",
                name: "UI",
                colour: "#a78bfa",
                contents: [
                    { kind: "block", type: "automation_ui_create_window" },
                    { kind: "block", type: "automation_ui_create_label" },
                    { kind: "block", type: "automation_ui_create_button" },
                    { kind: "block", type: "automation_ui_set_text" },
                    { kind: "block", type: "automation_ui_button_clicked" }
                ]
            },
            {
                kind: "category",
                name: "Functions",
                categorystyle: "procedure_category",
                custom: "PROCEDURE"
            },
            {
                kind: "category",
                name: "Logic",
                categorystyle: "logic_category",
                contents: [
                    { kind: "block", type: "controls_if" },
                    { kind: "block", type: "logic_compare" },
                    { kind: "block", type: "logic_operation" },
                    { kind: "block", type: "logic_negate" },
                    { kind: "block", type: "logic_boolean" },
                    { kind: "block", type: "logic_null" },
                    { kind: "block", type: "logic_ternary" }
                ]
            },
            {
                kind: "category",
                name: "Loops",
                colour: "#5b9a52",
                contents: [
                    { kind: "block", type: "automation_repeat_until_stopped" },
                    { kind: "block", type: "controls_repeat_ext" },
                    { kind: "block", type: "controls_whileUntil" },
                    { kind: "block", type: "controls_for" },
                    { kind: "block", type: "controls_forEach" },
                    { kind: "block", type: "controls_flow_statements" },
                    { kind: "block", type: "automation_break_loop" }
                ]
            },
            {
                kind: "category",
                name: "Math",
                categorystyle: "math_category",
                contents: [
                    { kind: "block", type: "math_number" },
                    { kind: "block", type: "math_arithmetic" },
                    { kind: "block", type: "math_single" },
                    { kind: "block", type: "math_trig" },
                    { kind: "block", type: "math_round" },
                    { kind: "block", type: "math_modulo" },
                    { kind: "block", type: "math_random_int" },
                    { kind: "block", type: "math_random_float" },
                    { kind: "block", type: "math_constrain" },
                    {
                        kind: "block",
                        type: "math_change",
                        inputs: {
                            DELTA: {
                                block: {
                                    type: "math_number",
                                    fields: {
                                        NUM: 1
                                    }
                                }
                            }
                        }
                    }
                ]
            },
            {
                kind: "category",
                name: "Text",
                categorystyle: "text_category",
                contents: [
                    { kind: "block", type: "text" },
                    { kind: "block", type: "text_join" },
                    { kind: "block", type: "text_length" },
                    { kind: "block", type: "text_isEmpty" },
                    { kind: "block", type: "text_changeCase" },
                    { kind: "block", type: "text_trim" },
                    { kind: "block", type: "text_indexOf" },
                    { kind: "block", type: "text_charAt" },
                    { kind: "block", type: "text_getSubstring" }
                ]
            },
            {
                kind: "category",
                name: "Variables",
                custom: "SYNAPSE_VARIABLE",
                categorystyle: "variable_category"
            },
            {
                kind: "category",
                name: "Timing",
                categorystyle: "math_category",
                contents: [
                    {
                        kind: "block",
                        type: "automation_wait",
                        inputs: {
                            DURATION: {
                                shadow: {
                                    type: "math_number",
                                    fields: {
                                        NUM: 1000
                                    }
                                }
                            }
                        }
                    }
                ]
            },
            {
                kind: "category",
                name: "Actions",
                colour: "#5b9a52",
                contents: [
                    { kind: "block", type: "automation_key_press" },
                    { kind: "block", type: "automation_key_down" },
                    { kind: "block", type: "automation_key_up" },
                    { kind: "block", type: "automation_type_text" },
                    { kind: "block", type: "automation_mouse_click" },
                    { kind: "block", type: "automation_mouse_move" },
                    { kind: "block", type: "automation_mouse_scroll" },
                    { kind: "block", type: "automation_left_click" }
                ]
            }
        ]
    },

    theme: Blockly.Theme.defineTheme("automationTheme", {
        base: Blockly.Themes.Classic,
        componentStyles: {
            workspaceBackgroundColour: "#17171d",
            toolboxBackgroundColour: "#22222b",
            toolboxForegroundColour: "#eeeeee",
            flyoutBackgroundColour: "#292934",
            flyoutForegroundColour: "#eeeeee",
            flyoutOpacity: 1,
            scrollbarColour: "#555566",
            insertionMarkerColour: "#ffffff",
            insertionMarkerOpacity: 0.3
        }
    }),

    grid: {
        spacing: 25,
        length: 3,
        colour: "#30303a",
        snap: true
    },

    zoom: {
        controls: true,
        wheel: true,
        startScale: 1,
        maxScale: 2,
        minScale: 0.5,
        scaleSpeed: 1.1
    },

    trashcan: true
});


// ==========================================
// WAIT MINIMUM NORMALIZATION
// ==========================================

let isNormalizingWaitBlocks = false;


// Tracks fields that already have live validators.
const waitMinimumValidatedFields = new WeakSet();


function isInsideMinimumWaitLoop(block) {
    if (!block || typeof block.getSurroundParent !== "function") {
        return false;
    }

    let parent = block.getSurroundParent();

    while (parent) {
        if (
            parent.type === "automation_repeat_until_stopped" ||
            parent.type === "controls_whileUntil"
        ) {
            return true;
        }

        parent = parent.getSurroundParent();
    }

    return false;
}


// Resolve the Wait block through an output block's actual connection.
// Supports both math_number and automation_workflow_setting blocks.
function getOwningWaitBlock(valueBlock) {
    if (
        !valueBlock ||
        valueBlock.isDisposed() ||
        !valueBlock.outputConnection
    ) {
        return null;
    }

    const targetConnection =
        valueBlock.outputConnection.targetConnection;

    if (!targetConnection) {
        return null;
    }

    const waitBlock = targetConnection.getSourceBlock();

    if (
        !waitBlock ||
        waitBlock.isDisposed() ||
        waitBlock.type !== "automation_wait"
    ) {
        return null;
    }

    if (
        waitBlock.getInputTargetBlock("DURATION") !== valueBlock
    ) {
        return null;
    }

    return waitBlock;
}


// Determine whether a connected value block is a numeric value
// that should be constrained by the minimum Wait duration.
function isNumericWaitValueBlock(block) {
    if (!block || block.isDisposed()) {
        return false;
    }

    if (block.type === "math_number") {
        return true;
    }

    if (block.type === "automation_workflow_setting") {
        return block.getFieldValue("TYPE") === "NUMBER";
    }

    return false;
}


// Install a live validator on the relevant numeric field.
// The connected Wait and loop are checked dynamically each time
// the user edits the field.
function installWaitMinimumValidator(valueBlock, fieldName) {
    if (
        !valueBlock ||
        valueBlock.isDisposed()
    ) {
        return;
    }

    const valueField = valueBlock.getField(fieldName);

    if (
        !valueField ||
        typeof valueField.setValidator !== "function" ||
        waitMinimumValidatedFields.has(valueField)
    ) {
        return;
    }

    valueField.setValidator(function (newValue) {
        if (
            valueBlock.isDisposed() ||
            !isNumericWaitValueBlock(valueBlock)
        ) {
            return newValue;
        }

        const waitBlock = getOwningWaitBlock(valueBlock);

        if (
            !waitBlock ||
            !isInsideMinimumWaitLoop(waitBlock)
        ) {
            return newValue;
        }

        const numericValue = Number(newValue);

        if (
            !Number.isFinite(numericValue) ||
            numericValue < 1
        ) {
            return "1";
        }

        return newValue;
    });

    waitMinimumValidatedFields.add(valueField);
}


// Normalize a connected value block's displayed field value.
function normalizeConnectedWaitValue(valueBlock) {
    if (!isNumericWaitValueBlock(valueBlock)) {
        return;
    }

    let fieldName;

    if (valueBlock.type === "math_number") {
        fieldName = "NUM";
    }
    else if (valueBlock.type === "automation_workflow_setting") {
        fieldName = "VALUE";
    }
    else {
        return;
    }

    installWaitMinimumValidator(
        valueBlock,
        fieldName
    );

    const rawValue = valueBlock.getFieldValue(fieldName);
    const numericValue = Number(rawValue);

    if (
        !Number.isFinite(numericValue) ||
        numericValue < 1
    ) {
        valueBlock.setFieldValue("1", fieldName);
    }
}


function normalizeWaitBlockMinimums() {
    if (isNormalizingWaitBlocks) {
        return;
    }

    isNormalizingWaitBlocks = true;

    try {
        for (const block of workspace.getAllBlocks(false)) {
            if (block.type !== "automation_wait") {
                continue;
            }

            if (!isInsideMinimumWaitLoop(block)) {
                continue;
            }

            const durationBlock = block.getInputTargetBlock(
                "DURATION"
            );

            if (!durationBlock) {
                continue;
            }

            normalizeConnectedWaitValue(durationBlock);
        }
    }
    finally {
        isNormalizingWaitBlocks = false;
    }
}


// ==========================================
// VARIABLE TYPE PICKER
// ==========================================

function getWorkspaceVariableMap(targetWorkspace) {
    if (
        !targetWorkspace ||
        typeof targetWorkspace.getVariableMap !== "function"
    ) {
        return null;
    }

    return targetWorkspace.getVariableMap();
}


function getSortedWorkspaceVariables(targetWorkspace) {
    const variableMap = getWorkspaceVariableMap(targetWorkspace);

    if (!variableMap) {
        return [];
    }

    return variableMap
        .getAllVariables()
        .filter(variable => {
            return (
                variable &&
                typeof variable.name === "string" &&
                variable.name.trim().length > 0 &&
                typeof variable.type === "string"
            );
        })
        .sort((a, b) => {
            return a.name.localeCompare(
                b.name,
                undefined,
                { sensitivity: "base" }
            );
        });
}


function createTypedVariable(targetWorkspace, variableType, name) {
    const variableMap = getWorkspaceVariableMap(targetWorkspace);

    if (!variableMap || typeof variableMap.createVariable !== "function") {
        console.error("Blockly variable map is unavailable.");
        return false;
    }

    const allowedTypes = [
        "Number",
        "String",
        "Colour"
    ];

    if (!allowedTypes.includes(variableType)) {
        console.error("Unsupported Blockly variable type:", variableType);
        return false;
    }

    const trimmedName = String(name || "").trim();

    if (!trimmedName) {
        return false;
    }

    const normalizedName = trimmedName.toLowerCase();

    const variables = variableMap.getAllVariables();

    const duplicate = variables.find(variable => {
        if (!variable || typeof variable.name !== "string") {
            return false;
        }

        return variable.name.trim().toLowerCase() === normalizedName;
    });

    if (duplicate) {
        return false;
    }

    try {
        variableMap.createVariable(
            trimmedName,
            variableType
        );

        return true;
    }
    catch (error) {
        console.error(
            "Unable to create Blockly variable:",
            error
        );

        return false;
    }
}


function showVariableTypePicker(targetWorkspace) {
    if (!getWorkspaceVariableMap(targetWorkspace)) {
        console.error("Unable to open variable picker: invalid workspace.");
        return;
    }

    const overlay = document.createElement("div");

    overlay.style.cssText = `
        position: fixed;
        inset: 0;
        z-index: 10000;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(0, 0, 0, 0.58);
        font-family: Arial, sans-serif;
    `;

    const dialog = document.createElement("div");

    dialog.style.cssText = `
        width: 340px;
        max-width: calc(100vw - 40px);
        padding: 24px;
        border: 1px solid #383b46;
        border-radius: 12px;
        background: #20232b;
        color: #eeeeee;
        box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
    `;

    const heading = document.createElement("div");
    heading.textContent = "Create Variable";

    heading.style.cssText = `
        margin-bottom: 8px;
        font-size: 18px;
        font-weight: 600;
    `;

    const description = document.createElement("div");
    description.textContent = "Choose a type and enter a name for your variable.";

    description.style.cssText = `
        margin-bottom: 18px;
        color: #a6a9b4;
        font-size: 13px;
        line-height: 1.5;
    `;

    const options = [
        ["Number", "Number", "Store numeric values."],
        ["Text", "String", "Store text values."],
        ["Color", "Colour", "Store color values."]
    ];

    let selectedType = null;

    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.placeholder = "Variable name";
    nameInput.autocomplete = "off";
    nameInput.spellcheck = false;

    nameInput.style.cssText = `
        display: block;
        box-sizing: border-box;
        width: 100%;
        margin: 0 0 14px;
        padding: 11px 12px;
        border: 1px solid #393d49;
        border-radius: 7px;
        outline: none;
        background: #17191f;
        color: #eeeeee;
        font-size: 14px;
    `;

    const optionContainer = document.createElement("div");

    const errorMessage = document.createElement("div");
    errorMessage.style.cssText = `
        display: none;
        margin: 8px 0 12px;
        color: #f08080;
        font-size: 12px;
        line-height: 1.4;
    `;

    const buttonRow = document.createElement("div");

    buttonRow.style.cssText = `
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        margin-top: 16px;
    `;

    function closeDialog() {
        if (overlay.parentNode) {
            overlay.parentNode.removeChild(overlay);
        }

        document.removeEventListener("keydown", escapeHandler);
    }

    function showError(message) {
        errorMessage.textContent = message;
        errorMessage.style.display = "block";
    }

    function clearError() {
        errorMessage.textContent = "";
        errorMessage.style.display = "none";
    }

    function updateOptionStyles() {
        for (const option of optionContainer.children) {
            const isSelected = option.dataset.variableType === selectedType;

            option.style.borderColor = isSelected
                ? "#a78bfa"
                : "#393d49";

            option.style.background = isSelected
                ? "#343044"
                : "#292d37";
        }
    }

    for (const [label, variableType, descriptionText] of options) {
        const option = document.createElement("button");

        option.type = "button";
        option.dataset.variableType = variableType;

        option.style.cssText = `
            display: flex;
            flex-direction: column;
            align-items: flex-start;
            width: 100%;
            margin: 0 0 8px;
            padding: 12px 14px;
            border: 1px solid #393d49;
            border-radius: 8px;
            background: #292d37;
            color: #eeeeee;
            text-align: left;
            cursor: pointer;
        `;

        const optionTitle = document.createElement("span");
        optionTitle.textContent = label;

        optionTitle.style.cssText = `
            margin-bottom: 4px;
            font-size: 14px;
            font-weight: 600;
        `;

        const optionDescription = document.createElement("span");
        optionDescription.textContent = descriptionText;

        optionDescription.style.cssText = `
            color: #a6a9b4;
            font-size: 12px;
        `;

        option.appendChild(optionTitle);
        option.appendChild(optionDescription);

        option.addEventListener("click", function () {
            selectedType = variableType;
            clearError();
            updateOptionStyles();
        });

        option.addEventListener("mouseenter", function () {
            if (selectedType !== variableType) {
                option.style.background = "#343947";
            }
        });

        option.addEventListener("mouseleave", function () {
            updateOptionStyles();
        });

        optionContainer.appendChild(option);
    }

    function createButton(label, primary) {
        const button = document.createElement("button");

        button.type = "button";
        button.textContent = label;

        button.style.cssText = `
            padding: 10px 15px;
            border: 1px solid ${primary ? "#a78bfa" : "#393d49"};
            border-radius: 7px;
            background: ${primary ? "#8b70d6" : "#292d37"};
            color: #ffffff;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        `;

        return button;
    }

    const cancelButton = createButton("Cancel", false);
    const createButtonElement = createButton("Create Variable", true);

    cancelButton.addEventListener("click", closeDialog);

    createButtonElement.addEventListener("click", function () {
        const name = nameInput.value.trim();

        if (!selectedType) {
            showError("Choose a variable type first.");
            return;
        }

        if (!name) {
            showError("Enter a name for your variable.");
            return;
        }

        const created = createTypedVariable(
            targetWorkspace,
            selectedType,
            name
        );

        if (!created) {
            showError(
                `A variable named "${name}" may already exist, or the name is invalid.`
            );
            return;
        }

        closeDialog();
    });

    nameInput.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
            event.preventDefault();
            createButtonElement.click();
        }
    });

    function escapeHandler(event) {
        if (event.key === "Escape") {
            closeDialog();
        }
    }

    buttonRow.appendChild(cancelButton);
    buttonRow.appendChild(createButtonElement);

    dialog.appendChild(heading);
    dialog.appendChild(description);
    dialog.appendChild(nameInput);
    dialog.appendChild(optionContainer);
    dialog.appendChild(errorMessage);
    dialog.appendChild(buttonRow);

    overlay.appendChild(dialog);

    overlay.addEventListener("click", function (event) {
        if (event.target === overlay) {
            closeDialog();
        }
    });

    document.addEventListener("keydown", escapeHandler);

    document.body.appendChild(overlay);
}


// ==========================================
// DELETE VARIABLE PICKER
// ==========================================

function deleteWorkspaceVariable(targetWorkspace, variableId) {
    const variableMap = getWorkspaceVariableMap(targetWorkspace);

    if (
        !variableMap ||
        typeof variableMap.getVariableById !== "function" ||
        typeof variableMap.deleteVariable !== "function"
    ) {
        console.error("Blockly variable map cannot delete variables.");
        return false;
    }

    if (!variableId) {
        return false;
    }

    try {
        // Resolve the variable model from its ID.
        const variable = variableMap.getVariableById(variableId);

        if (!variable) {
            console.warn(
                "Cannot delete variable because it no longer exists:",
                variableId
            );

            return false;
        }

        // Delete the variable through Blockly's VariableMap API.
        // This also removes blocks that use the variable.
        variableMap.deleteVariable(variable);

        return true;
    }
    catch (error) {
        console.error(
            "Unable to delete variable:",
            error
        );

        return false;
    }
}


function showDeleteVariablePicker(targetWorkspace) {
    if (!getWorkspaceVariableMap(targetWorkspace)) {
        console.error("Unable to open delete dialog: invalid workspace.");
        return;
    }

    const variables = getSortedWorkspaceVariables(targetWorkspace);

    const overlay = document.createElement("div");

    overlay.style.cssText = `
        position: fixed;
        inset: 0;
        z-index: 10000;
        display: flex;
        align-items: center;
        justify-content: center;
        background: rgba(0, 0, 0, 0.58);
        font-family: Arial, sans-serif;
    `;

    const dialog = document.createElement("div");

    dialog.style.cssText = `
        width: 360px;
        max-width: calc(100vw - 40px);
        padding: 24px;
        border: 1px solid #383b46;
        border-radius: 12px;
        background: #20232b;
        color: #eeeeee;
        box-shadow: 0 16px 48px rgba(0, 0, 0, 0.4);
    `;

    const heading = document.createElement("div");
    heading.textContent = "Delete Variable";

    heading.style.cssText = `
        margin-bottom: 8px;
        font-size: 18px;
        font-weight: 600;
    `;

    const description = document.createElement("div");
    description.textContent = variables.length
        ? "Choose a variable to permanently remove it from this workflow."
        : "There are no created variables to delete.";

    description.style.cssText = `
        margin-bottom: 18px;
        color: #a6a9b4;
        font-size: 13px;
        line-height: 1.5;
    `;

    const selectLabel = document.createElement("div");
    selectLabel.textContent = "Variable";

    selectLabel.style.cssText = `
        margin-bottom: 7px;
        color: #c6c8d0;
        font-size: 12px;
        font-weight: 600;
    `;

    const variableSelect = document.createElement("select");

    variableSelect.style.cssText = `
        display: block;
        box-sizing: border-box;
        width: 100%;
        padding: 11px 12px;
        border: 1px solid #393d49;
        border-radius: 7px;
        outline: none;
        background: #17191f;
        color: #eeeeee;
        font-size: 14px;
    `;

    for (const variable of variables) {
        const option = document.createElement("option");

        option.value = variable.getId();

        const typeName = {
            Number: "Number",
            String: "Text",
            Colour: "Color"
        }[variable.type] || variable.type;

        option.textContent = `${variable.name} (${typeName})`;

        variableSelect.appendChild(option);
    }

    if (variables.length === 0) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No variables available";
        variableSelect.appendChild(option);
        variableSelect.disabled = true;
    }

    variableSelect.disabled = variables.length === 0;

    variableSelect.style.opacity = variables.length === 0
        ? "0.55"
        : "1";

    const warning = document.createElement("div");
    warning.textContent =
        "Blocks using this variable will also be removed.";

    warning.style.cssText = `
        margin-top: 12px;
        color: #d69b72;
        font-size: 12px;
        line-height: 1.5;
    `;

    const errorMessage = document.createElement("div");

    errorMessage.style.cssText = `
        display: none;
        margin-top: 10px;
        color: #f08080;
        font-size: 12px;
        line-height: 1.4;
    `;

    const buttonRow = document.createElement("div");

    buttonRow.style.cssText = `
        display: flex;
        justify-content: flex-end;
        gap: 8px;
        margin-top: 20px;
    `;

    function closeDialog() {
        if (overlay.parentNode) {
            overlay.parentNode.removeChild(overlay);
        }

        document.removeEventListener("keydown", escapeHandler);
    }

    function createButton(label, primary, danger = false) {
        const button = document.createElement("button");

        button.type = "button";
        button.textContent = label;

        button.style.cssText = `
            padding: 10px 15px;
            border: 1px solid ${
                danger ? "#b65c65" :
                primary ? "#a78bfa" :
                "#393d49"
            };
            border-radius: 7px;
            background: ${
                danger ? "#8f414b" :
                primary ? "#8b70d6" :
                "#292d37"
            };
            color: #ffffff;
            font-size: 13px;
            font-weight: 600;
            cursor: pointer;
        `;

        return button;
    }

    const cancelButton = createButton("Cancel", false);
    const deleteButton = createButton(
        "Delete Variable",
        false,
        true
    );

    deleteButton.disabled = variables.length === 0;

    if (variables.length === 0) {
        deleteButton.style.opacity = "0.45";
        deleteButton.style.cursor = "not-allowed";
    }

    cancelButton.addEventListener("click", closeDialog);

    deleteButton.addEventListener("click", function () {
        const variableId = variableSelect.value;

        if (!variableId) {
            errorMessage.textContent = "Select a variable first.";
            errorMessage.style.display = "block";
            return;
        }

        const deleted = deleteWorkspaceVariable(
            targetWorkspace,
            variableId
        );

        if (!deleted) {
            errorMessage.textContent =
                "The variable could not be deleted.";

            errorMessage.style.display = "block";
            return;
        }

        closeDialog();
    });

    function escapeHandler(event) {
        if (event.key === "Escape") {
            closeDialog();
        }
    }

    buttonRow.appendChild(cancelButton);
    buttonRow.appendChild(deleteButton);

    dialog.appendChild(heading);
    dialog.appendChild(description);
    dialog.appendChild(selectLabel);
    dialog.appendChild(variableSelect);
    dialog.appendChild(warning);
    dialog.appendChild(errorMessage);
    dialog.appendChild(buttonRow);

    overlay.appendChild(dialog);

    overlay.addEventListener("click", function (event) {
        if (event.target === overlay) {
            closeDialog();
        }
    });

    document.addEventListener("keydown", escapeHandler);

    document.body.appendChild(overlay);
}


// ==========================================
// DYNAMIC VARIABLES FLYOUT
// ==========================================

workspace.registerButtonCallback(
    "SYNAPSE_CREATE_VARIABLE",
    function (button) {
        const targetWorkspace = button.getTargetWorkspace();

        // Wait until Blockly has completed its current toolbox event
        // before displaying the variable creation dialog.
        setTimeout(function () {
            showVariableTypePicker(targetWorkspace);
        }, 0);
    }
);


workspace.registerButtonCallback(
    "SYNAPSE_DELETE_VARIABLE",
    function (button) {
        const targetWorkspace = button.getTargetWorkspace();

        // Defer the dialog until Blockly has finished its toolbox event.
        setTimeout(function () {
            showDeleteVariablePicker(targetWorkspace);
        }, 0);
    }
);


function createVariableFlyoutBlocks(targetWorkspace) {
    if (
        !Blockly.VariablesDynamic ||
        typeof Blockly.VariablesDynamic.flyoutCategoryBlocks !== "function"
    ) {
        console.error(
            "Blockly's dynamic variable flyout API is unavailable."
        );

        return [];
    }

    try {
        return Blockly.VariablesDynamic.flyoutCategoryBlocks(
            targetWorkspace
        );
    }
    catch (error) {
        console.error(
            "Unable to generate Blockly variable flyout:",
            error
        );

        return [];
    }
}


workspace.registerToolboxCategoryCallback(
    "SYNAPSE_VARIABLE",
    function (targetWorkspace) {
        // Create button.
        const createButton = Blockly.utils.xml.createElement("button");

        createButton.setAttribute(
            "text",
            "Create Variable"
        );

        createButton.setAttribute(
            "callbackKey",
            "SYNAPSE_CREATE_VARIABLE"
        );

        // Delete button.
        const deleteButton = Blockly.utils.xml.createElement("button");

        deleteButton.setAttribute(
            "text",
            "Delete Variable"
        );

        deleteButton.setAttribute(
            "callbackKey",
            "SYNAPSE_DELETE_VARIABLE"
        );

        // Global variable block.
        // Its internal type remains unchanged for compatibility.
        const globalVariableBlock = Blockly.utils.xml.createElement("block");

        globalVariableBlock.setAttribute(
            "type",
            "automation_workflow_setting"
        );

        // Use Blockly's own dynamic variable flyout generator.
        const variableBlocks = createVariableFlyoutBlocks(
            targetWorkspace
        );

        return [
            createButton,
            deleteButton,
            globalVariableBlock,
            ...variableBlocks
        ];
    }
);


// ==========================================
// PERSISTENT BLOCK SELECTION
// ==========================================

let selectedBlockId = null;

const SELECTED_BLOCK_CLASS = "automation-persistent-selection";


function installPersistentSelectionStyle() {
    const style = document.createElement("style");

    style.textContent = `
        .blocklyBlockCanvas .${SELECTED_BLOCK_CLASS} > .blocklyPath {
            stroke: #ff9f43 !important;
            stroke-width: 3px !important;
        }

        .blocklyFlyout .blocklySelected > .blocklyPath {
            stroke: none !important;
            stroke-width: 0 !important;
            filter: none !important;
        }
    `;

    document.head.appendChild(style);
}

installPersistentSelectionStyle();


function getBlockById(blockId) {
    if (!blockId) {
        return null;
    }

    const block = workspace.getBlockById(blockId);

    if (!block || block.isDisposed()) {
        return null;
    }

    return block;
}


function removePersistentHighlight(block) {
    if (!block || block.isDisposed()) {
        return;
    }

    const svgRoot = block.getSvgRoot();

    if (svgRoot) {
        svgRoot.classList.remove(
            SELECTED_BLOCK_CLASS
        );
    }
}


function addPersistentHighlight(block) {
    if (!block || block.isDisposed()) {
        return;
    }

    const svgRoot = block.getSvgRoot();

    if (svgRoot) {
        svgRoot.classList.add(
            SELECTED_BLOCK_CLASS
        );
    }
}


function setSelectedBlock(block) {
    if (block && (
        block.isDisposed() ||
        block.workspace !== workspace
    )) {
        return;
    }

    const newBlockId = block ? block.id : null;

    if (selectedBlockId === newBlockId) {
        if (block) {
            addPersistentHighlight(block);
        }

        return;
    }

    const previousBlock = getBlockById(selectedBlockId);

    removePersistentHighlight(previousBlock);

    selectedBlockId = newBlockId;

    if (block) {
        addPersistentHighlight(block);
    }
}


function clearSelectedBlock() {
    setSelectedBlock(null);
}


function getCurrentlySelectedBlock() {
    const block = getBlockById(selectedBlockId);

    if (!block) {
        selectedBlockId = null;
        return null;
    }

    return block;
}


// ==========================================
// SERIALIZATION
// ==========================================

function getWorkflowData() {
    return Blockly.serialization.workspaces.save(workspace);
}


// ==========================================
// MOUSE COORDINATE CAPTURE
// ==========================================

window.setMouseMoveCoordinates = function (x, y) {
    const block = getCurrentlySelectedBlock();

    if (!block || block.type !== "automation_mouse_move") {
        return false;
    }

    block.setFieldValue(String(x), "X");
    block.setFieldValue(String(y), "Y");

    return true;
};


window.bridge = null;


// ==========================================
// BLOCK SELECTION / INSPECTOR
// ==========================================

function getSelectedBlockData(block) {
    if (!block || block.isDisposed()) {
        return null;
    }

    const fields = {};

    for (const input of block.inputList || []) {
        for (const field of input.fieldRow || []) {
            if (!field.name) {
                continue;
            }

            try {
                fields[field.name] = block.getFieldValue(field.name);
            }
            catch (error) {
                console.warn(
                    "Unable to read Blockly field:",
                    field.name,
                    error
                );
            }
        }
    }

    return {
        id: block.id,
        type: block.type,
        fields: fields,
        isUiElement: [
            "automation_ui_create_label",
            "automation_ui_create_button"
        ].includes(block.type)
    };
}


function reportSelectedBlock(block = getCurrentlySelectedBlock()) {
    if (!window.bridge) {
        return;
    }

    const blockData = getSelectedBlockData(block);

    if (!blockData) {
        window.bridge.clear_selected_block();
        return;
    }

    window.bridge.report_selected_block(
        JSON.stringify(blockData)
    );
}


// ==========================================
// DEFERRED SELECTION REFRESH
// ==========================================

let selectionRefreshScheduled = false;

function scheduleSelectedBlockRefresh() {
    if (selectionRefreshScheduled) {
        return;
    }

    selectionRefreshScheduled = true;

    requestAnimationFrame(() => {
        requestAnimationFrame(() => {
            selectionRefreshScheduled = false;

            const block = getCurrentlySelectedBlock();

            if (!block) {
                return;
            }

            addPersistentHighlight(block);
            reportSelectedBlock(block);
        });
    });
}


// ==========================================
// DESELECT WHEN CLICKING EMPTY WORKSPACE
// ==========================================

function installWorkspaceBackgroundDeselect() {
    const workspaceSvg = workspace.getParentSvg();

    if (!workspaceSvg) {
        return;
    }

    workspaceSvg.addEventListener("click", function (event) {
        if (event.button !== 0) {
            return;
        }

        const target = event.target;

        if (!(target instanceof Element)) {
            return;
        }

        if (!target.closest(".blocklyMainBackground")) {
            return;
        }

        clearSelectedBlock();
        reportSelectedBlock(null);
    });
}

installWorkspaceBackgroundDeselect();


// ==========================================
// PYTHON BRIDGE
// ==========================================

new QWebChannel(qt.webChannelTransport, function (channel) {

    window.bridge = channel.objects.bridge;

    let isLoadingWorkflow = false;


    // --------------------------------------
    // WORKSPACE EVENTS
    // --------------------------------------

    workspace.addChangeListener(function (event) {

        if (
            event.workspaceId &&
            event.workspaceId !== workspace.id
        ) {
            return;
        }

        // Keep connected numeric Wait values at or above 1 ms
        // inside the loops that enforce the minimum interval.
        // This now handles both math_number and global variables.
        normalizeWaitBlockMinimums();


        // ----------------------------------
        // BLOCK SELECTION
        // ----------------------------------

        if (event.type === Blockly.Events.SELECTED) {
            if (!event.newElementId) {
                return;
            }

            const selectedBlock = getBlockById(
                event.newElementId
            );

            if (
                !selectedBlock ||
                selectedBlock.workspace !== workspace
            ) {
                return;
            }

            setSelectedBlock(selectedBlock);
            scheduleSelectedBlockRefresh();

            return;
        }


        // ----------------------------------
        // SELECTED BLOCK CHANGES
        // ----------------------------------

        if (event.type === Blockly.Events.BLOCK_CHANGE) {
            const selectedBlock = getCurrentlySelectedBlock();

            if (
                selectedBlock &&
                selectedBlock.id === event.blockId
            ) {
                scheduleSelectedBlockRefresh();
            }
        }


        // ----------------------------------
        // SELECTED BLOCK DELETED
        // ----------------------------------

        if (
            event.type === Blockly.Events.BLOCK_DELETE &&
            selectedBlockId === event.blockId
        ) {
            clearSelectedBlock();
            reportSelectedBlock(null);
        }


        // ----------------------------------
        // WORKFLOW MODIFICATION TRACKING
        // ----------------------------------

        if (isLoadingWorkflow || event.isUiEvent) {
            return;
        }

        bridge.mark_workflow_changed();
    });


    // --------------------------------------
    // PROPERTY EDITS FROM PYTHON
    // --------------------------------------

    bridge.property_change_requested.connect(function (
        blockId,
        propertyName,
        value
    ) {
        const block = getBlockById(blockId);

        if (!block) {
            return;
        }

        const field = block.getField(propertyName);

        if (!field) {
            console.warn(
                `Block ${blockId} has no field named ${propertyName}.`
            );
            return;
        }

        try {
            const isGeometryProperty = [
                "X",
                "Y",
                "WIDTH",
                "HEIGHT"
            ].includes(propertyName);

            if (
                isGeometryProperty &&
                [
                    "automation_ui_create_label",
                    "automation_ui_create_button"
                ].includes(block.type)
            ) {
                block.setFieldValue("CUSTOM", "LAYOUT");
            }

            block.setFieldValue(
                String(value),
                propertyName
            );

            if (selectedBlockId === blockId) {
                scheduleSelectedBlockRefresh();
            }
        }
        catch (error) {
            console.error(
                "Unable to update Blockly property:",
                propertyName,
                error
            );
        }
    });


    // --------------------------------------
    // INPUT CAPTURE
    // --------------------------------------

    bridge.input_captured.connect(function (
        blockId,
        deviceName,
        control
    ) {
        const block = getBlockById(blockId);

        if (!block || block.type !== "automation_input_listener") {
            return;
        }

        block.setFieldValue(control, "CONTROL");
        block.setFieldValue(deviceName, "DEVICE");
    });


    // --------------------------------------
    // SAVE WORKFLOW
    // --------------------------------------

    window.saveWorkflow = function () {
        // Normalize once more immediately before serialization.
        normalizeWaitBlockMinimums();

        bridge.receive_workflow(
            JSON.stringify(getWorkflowData()),
            bridge.workflow_name
        );
    };


    // --------------------------------------
    // LOAD WORKFLOW
    // --------------------------------------

    bridge.workflow_loaded.connect(function (workflowJson) {
        const workflowData = JSON.parse(workflowJson);

        isLoadingWorkflow = true;

        clearSelectedBlock();
        bridge.clear_selected_block();

        Blockly.Events.disable();

        try {
            Blockly.serialization.workspaces.load(
                workflowData,
                workspace
            );
        }
        finally {
            Blockly.Events.enable();
        }

        // Loading disables Blockly events, so normalize after the
        // workspace has been restored and before marking it saved.
        normalizeWaitBlockMinimums();

        isLoadingWorkflow = false;

        bridge.mark_workflow_saved();
        reportSelectedBlock(null);
    });


    window.loadWorkflow = function () {
        bridge.load_workflow();
    };


    reportSelectedBlock(null);

});
