
import logging
import math
import random


logger = logging.getLogger(__name__)


class ValuesMixin:

    # ======================================
    # VALUE HELPERS
    # ======================================

    @staticmethod
    def _safe_number(value, default=0):
        try:
            number = float(value)

            if not math.isfinite(number):
                return default

            return number

        except (TypeError, ValueError, OverflowError):
            return default

    @staticmethod
    def _get_input_block(block, input_name):
        if not block:
            return None

        input_data = block.get("inputs", {}).get(input_name, {})
        return input_data.get("block") or input_data.get("shadow")

    def _evaluate_value(self, block):
        with self._execution_lock:
            return self._evaluate_value_unlocked(block)

    def _evaluate_workflow_setting(self, block):
        """
        Resolve a workflow setting using its configured type and value.

        NUMBER settings return finite numeric values.
        TEXT settings return their configured string values.

        Interval (ms) settings always have a minimum value of 1.
        """
        fields = block.get("fields", {})

        setting_type = str(
            fields.get("TYPE", "NUMBER")
        ).upper()

        value = fields.get("VALUE", 0)

        if setting_type == "TEXT":
            return str(value) if value is not None else ""

        number = self._safe_number(value, 0)

        setting_name = str(
            fields.get("NAME", "")
        ).strip().casefold()

        if setting_name == "interval (ms)":
            return max(1, number)

        return number

    def _evaluate_value_unlocked(self, block):
        if not block or self._current_stop_event().is_set():
            return None

        block_type = block.get("type")
        fields = block.get("fields", {})

        # ------------------------------
        # Basic values
        # ------------------------------

        if block_type == "math_number":
            return self._safe_number(fields.get("NUM", 0))

        if block_type == "automation_workflow_setting":
            return self._evaluate_workflow_setting(block)

        if block_type == "text":
            return str(fields.get("TEXT", ""))

        if block_type == "logic_boolean":
            return fields.get("BOOL", "TRUE") == "TRUE"

        if block_type == "logic_null":
            return None

        # ------------------------------
        # Function arguments
        # ------------------------------

        if block_type in self.FUNCTION_ARGUMENT_TYPES:
            return self._get_function_argument(block)

        # ------------------------------
        # Variables
        # ------------------------------

        if block_type == "variables_get":
            found, scoped_value = self._get_scoped_variable(
                fields.get("VAR")
            )

            if found:
                return scoped_value

            variable_key = self._get_variable_key(
                fields.get("VAR")
            )

            if variable_key is None:
                logger.warning(
                    "Get Variable block has no valid variable."
                )
                return None

            return self._variables.get(variable_key, 0)

        # ------------------------------
        # Logic
        # ------------------------------

        if block_type == "logic_compare":
            left = self._evaluate_value(
                self._get_input_block(block, "A")
            )
            right = self._evaluate_value(
                self._get_input_block(block, "B")
            )

            return self._compare_values(
                left,
                right,
                fields.get("OP", "EQ")
            )

        if block_type == "logic_operation":
            operator = fields.get("OP", "AND")

            left = bool(self._evaluate_value(
                self._get_input_block(block, "A")
            ))

            if operator == "AND" and not left:
                return False

            if operator == "OR" and left:
                return True

            right = bool(self._evaluate_value(
                self._get_input_block(block, "B")
            ))

            return left and right if operator == "AND" else left or right

        if block_type == "logic_negate":
            return not bool(
                self._evaluate_value(
                    self._get_input_block(block, "BOOL")
                )
            )

        if block_type == "logic_ternary":
            condition = self._evaluate_value(
                self._get_input_block(block, "IF")
            )

            input_name = "THEN" if condition else "ELSE"

            return self._evaluate_value(
                self._get_input_block(block, input_name)
            )

        if block_type == "logic_is_empty":
            value = self._evaluate_value(
                self._get_input_block(block, "VALUE")
            )
            return value is None or value == "" or value == []

        # ------------------------------
        # Arithmetic
        # ------------------------------

        if block_type == "math_arithmetic":
            left = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "A")
                )
            )
            right = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "B")
                )
            )

            operator = fields.get("OP", "ADD")

            operations = {
                "ADD": lambda: left + right,
                "MINUS": lambda: left - right,
                "MULTIPLY": lambda: left * right,
                "DIVIDE": lambda: left / right,
                "POWER": lambda: left ** right,
            }

            return self._safe_math_operation(
                operator,
                operations
            )

        if block_type == "math_modulo":
            dividend = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "DIVIDEND")
                )
            )
            divisor = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "DIVISOR")
                )
            )

            if divisor == 0:
                logger.warning("Modulo by zero.")
                return 0

            return dividend % divisor

        if block_type == "math_single":
            value = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "NUM")
                )
            )

            return self._evaluate_math_single(
                value,
                fields.get("OP", "ROOT")
            )

        if block_type == "math_round":
            value = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "NUM")
                )
            )

            operation = fields.get("OP", "ROUND")

            if operation == "ROUNDUP":
                return math.ceil(value)

            if operation == "ROUNDDOWN":
                return math.floor(value)

            return round(value)

        if block_type == "math_trig":
            value = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "NUM")
                )
            )

            operation = fields.get("OP", "SIN")
            return self._evaluate_trig(value, operation)

        if block_type == "math_random_int":
            minimum = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "FROM")
                )
            )
            maximum = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "TO")
                )
            )

            low = math.ceil(min(minimum, maximum))
            high = math.floor(max(minimum, maximum))

            if low > high:
                return low

            return random.randint(low, high)

        if block_type == "math_random_float":
            return random.random()

        if block_type == "math_constrain":
            value = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "VALUE")
                )
            )
            minimum = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "LOW")
                )
            )
            maximum = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "HIGH")
                )
            )

            low, high = sorted((minimum, maximum))
            return max(low, min(high, value))

        if block_type == "math_number_property":
            value = self._safe_number(
                self._evaluate_value(
                    self._get_input_block(block, "NUMBER_TO_CHECK")
                )
            )
            property_name = fields.get("PROPERTY", "EVEN")

            if property_name == "EVEN":
                return value.is_integer() and int(value) % 2 == 0
            if property_name == "ODD":
                return value.is_integer() and int(value) % 2 != 0
            if property_name == "WHOLE":
                return value.is_integer()
            if property_name == "POSITIVE":
                return value > 0
            if property_name == "NEGATIVE":
                return value < 0
            if property_name == "DIVISIBLE_BY":
                divisor = self._safe_number(
                    self._evaluate_value(
                        self._get_input_block(block, "DIVISOR")
                    )
                )
                return divisor != 0 and value % divisor == 0
            if property_name == "PRIME":
                return self._is_prime(value)

        # ------------------------------
        # Text
        # ------------------------------

        if block_type == "text_join":
            pieces = []

            for name in self._ordered_input_names(block, "ADD"):
                pieces.append(
                    self._string_value(
                        self._evaluate_value(
                            self._get_input_block(block, name)
                        )
                    )
                )

            return "".join(pieces)

        if block_type == "text_length":
            value = self._evaluate_value(
                self._get_input_block(block, "VALUE")
            )
            return len(self._string_value(value))

        if block_type == "text_isEmpty":
            value = self._evaluate_value(
                self._get_input_block(block, "VALUE")
            )
            return value is None or str(value) == ""

        if block_type == "text_changeCase":
            value = self._string_value(
                self._evaluate_value(
                    self._get_input_block(block, "TEXT")
                )
            )
            case = fields.get("CASE", "UPPERCASE")

            if case == "LOWERCASE":
                return value.lower()
            if case == "TITLECASE":
                return value.title()

            return value.upper()

        if block_type == "text_trim":
            value = self._string_value(
                self._evaluate_value(
                    self._get_input_block(block, "TEXT")
                )
            )
            mode = fields.get("MODE", "BOTH")

            if mode == "LEFT":
                return value.lstrip()
            if mode == "RIGHT":
                return value.rstrip()

            return value.strip()

        if block_type == "text_indexOf":
            value = self._string_value(
                self._evaluate_value(
                    self._get_input_block(block, "VALUE")
                )
            )
            find = self._string_value(
                self._evaluate_value(
                    self._get_input_block(block, "FIND")
                )
            )
            end = fields.get("END", "FIRST")

            index = (
                value.find(find)
                if end == "FIRST"
                else value.rfind(find)
            )

            return index

        if block_type == "text_charAt":
            value = self._string_value(
                self._evaluate_value(
                    self._get_input_block(block, "VALUE")
                )
            )

            where = fields.get("WHERE", "FROM_START")

            if where == "FIRST":
                index = 0
            elif where == "LAST":
                index = len(value) - 1
            elif where == "FROM_END":
                index = -1 - int(self._safe_number(
                    self._evaluate_value(
                        self._get_input_block(block, "AT")
                    )
                ))
            elif where == "RANDOM":
                index = random.randrange(len(value)) if value else -1
            else:
                index = int(self._safe_number(
                    self._evaluate_value(
                        self._get_input_block(block, "AT")
                    )
                ))

            try:
                return value[index]
            except (IndexError, TypeError):
                return ""

        if block_type == "text_getSubstring":
            value = self._string_value(
                self._evaluate_value(
                    self._get_input_block(block, "STRING")
                )
            )

            start = self._text_index(
                value,
                fields.get("WHERE1", "FROM_START"),
                self._get_input_block(block, "AT1")
            )

            end = self._text_index(
                value,
                fields.get("WHERE2", "FROM_END"),
                self._get_input_block(block, "AT2")
            )

            if start is None or end is None:
                return ""

            start = max(0, min(len(value), start))
            end = max(0, min(len(value), end))

            if end < start:
                return ""

            return value[start:end + 1]

        if block_type == "text_append":
            variable_field = fields.get("VAR")
            variable_key = self._get_variable_key(variable_field)

            if variable_key is None:
                return None

            append_value = self._string_value(
                self._evaluate_value(
                    self._get_input_block(block, "TEXT")
                )
            )

            found, current = self._get_scoped_variable(variable_field)

            if found:
                self._set_scoped_variable(
                    variable_field,
                    self._string_value(current) + append_value
                )
            else:
                with self._execution_lock:
                    current = self._string_value(
                        self._variables.get(variable_key, "")
                    )
                    self._variables[variable_key] = current + append_value

            return None

        # ------------------------------
        # Function return values
        # ------------------------------

        if block_type in self.FUNCTION_CALL_TYPES:
            return self._execute_function_call(block)

        logger.warning(
            "Unsupported value block: %s",
            block_type
        )
        return None

    # ======================================
    # VALUE OPERATION HELPERS
    # ======================================

    @staticmethod
    def _string_value(value):
        if value is None:
            return ""

        if isinstance(value, bool):
            return "true" if value else "false"

        if isinstance(value, float) and value.is_integer():
            return str(int(value))

        return str(value)

    @staticmethod
    def _ordered_input_names(block, prefix):
        inputs = block.get("inputs", {})
        indexed = []

        for name in inputs:
            if not name.startswith(prefix):
                continue

            suffix = name[len(prefix):]

            if suffix.isdigit():
                indexed.append((int(suffix), name))

        indexed.sort()
        return [name for _, name in indexed]

    @staticmethod
    def _is_prime(value):
        if not value.is_integer():
            return False

        number = int(value)

        if number < 2:
            return False

        if number == 2:
            return True

        if number % 2 == 0:
            return False

        limit = int(math.sqrt(number))

        for divisor in range(3, limit + 1, 2):
            if number % divisor == 0:
                return False

        return True

    @staticmethod
    def _evaluate_math_single(value, operation):
        try:
            operations = {
                "ROOT": lambda: math.sqrt(value),
                "ABS": lambda: abs(value),
                "NEG": lambda: -value,
                "LN": lambda: math.log(value),
                "LOG10": lambda: math.log10(value),
                "EXP": lambda: math.exp(value),
                "POW10": lambda: 10 ** value
            }

            result = operations.get(operation)

            if result is None:
                logger.warning(
                    "Unsupported single-number operation: %s",
                    operation
                )
                return 0

            return ValuesMixin._valid_math_result(result())

        except (ArithmeticError, OverflowError, ValueError):
            logger.warning(
                "Single-number operation failed: %s",
                operation,
                exc_info=True
            )
            return 0

    @staticmethod
    def _evaluate_trig(value, operation):
        try:
            operations = {
                "SIN": lambda: math.sin(math.radians(value)),
                "COS": lambda: math.cos(math.radians(value)),
                "TAN": lambda: math.tan(math.radians(value)),
                "ASIN": lambda: math.degrees(math.asin(value)),
                "ACOS": lambda: math.degrees(math.acos(value)),
                "ATAN": lambda: math.degrees(math.atan(value))
            }

            result = operations.get(operation)

            if result is None:
                logger.warning(
                    "Unsupported trigonometry operation: %s",
                    operation
                )
                return 0

            return ValuesMixin._valid_math_result(result())

        except (ArithmeticError, OverflowError, ValueError):
            logger.warning(
                "Trigonometry operation failed: %s",
                operation,
                exc_info=True
            )
            return 0

    @staticmethod
    def _valid_math_result(value):
        if isinstance(value, complex) or not math.isfinite(value):
            return 0

        return value

    def _safe_math_operation(self, operator, operations):
        operation = operations.get(operator)

        if operation is None:
            logger.warning(
                "Unsupported arithmetic operator: %s",
                operator
            )
            return 0

        try:
            return self._valid_math_result(operation())

        except (ArithmeticError, OverflowError, ValueError):
            logger.warning(
                "Arithmetic operation failed: %s",
                operator,
                exc_info=True
            )
            return 0

    def _text_index(self, text, where, at_block):
        if where == "FIRST":
            return 0

        if where == "LAST":
            return len(text) - 1

        if where == "FROM_START":
            return int(self._safe_number(
                self._evaluate_value(at_block)
            ))

        if where == "FROM_END":
            return len(text) - 1 - int(self._safe_number(
                self._evaluate_value(at_block)
            ))

        if where == "RANDOM":
            return random.randrange(len(text)) if text else None

        return None

    # ======================================
    # COMPARISON HELPERS
    # ======================================

    @staticmethod
    def _compare_values(left, right, operator):
        if operator in ("EQ", "NEQ"):
            equal = left == right
            return equal if operator == "EQ" else not equal

        try:
            if operator == "LT":
                return left < right

            if operator == "LTE":
                return left <= right

            if operator == "GT":
                return left > right

            if operator == "GTE":
                return left >= right

        except TypeError:
            return False

        logger.warning(
            "Unsupported comparison operator: %s",
            operator
        )
        return False

    def _number_from_block(self, block):
        return self._safe_number(
            self._evaluate_value(block),
            0
        )
