
import logging
import math
import time


logger = logging.getLogger(__name__)


class _BreakLoop(Exception):
    """Exit the nearest enclosing loop."""


class _ContinueLoop(Exception):
    """Skip to the next iteration of the nearest enclosing loop."""


class _ReturnFunction(Exception):
    """Return a value from the current function."""

    def __init__(self, value=None):
        super().__init__()
        self.value = value


class ControlFlowMixin:

    # ======================================
    # EXECUTION CONTEXT
    # ======================================

    def _current_stop_event(self):
        return getattr(
            self._execution_context,
            "stop_event",
            self.stop_event
        )

    def _current_loop_depth(self):
        return getattr(
            self._execution_context,
            "loop_depth",
            0
        )

    def _change_loop_depth(self, amount):
        self._execution_context.loop_depth = (
            self._current_loop_depth() + amount
        )

    def _current_minimum_wait_loop_depth(self):
        return getattr(
            self._execution_context,
            "minimum_wait_loop_depth",
            0
        )

    def _change_minimum_wait_loop_depth(self, amount):
        self._execution_context.minimum_wait_loop_depth = (
            self._current_minimum_wait_loop_depth() + amount
        )

    def _current_function_scopes(self):
        scopes = getattr(
            self._execution_context,
            "function_scopes",
            None
        )

        if scopes is None:
            scopes = []
            self._execution_context.function_scopes = scopes

        return scopes

    def _current_loop_scopes(self):
        scopes = getattr(
            self._execution_context,
            "loop_scopes",
            None
        )

        if scopes is None:
            scopes = []
            self._execution_context.loop_scopes = scopes

        return scopes

    def _set_execution_context(self, stop_event):
        previous = {
            "stop_event": getattr(
                self._execution_context, "stop_event", None
            ),
            "loop_depth": getattr(
                self._execution_context, "loop_depth", None
            ),
            "minimum_wait_loop_depth": getattr(
                self._execution_context,
                "minimum_wait_loop_depth",
                None
            ),
            "function_scopes": getattr(
                self._execution_context, "function_scopes", None
            ),
            "loop_scopes": getattr(
                self._execution_context, "loop_scopes", None
            )
        }

        self._execution_context.stop_event = stop_event
        self._execution_context.loop_depth = 0
        self._execution_context.minimum_wait_loop_depth = 0
        self._execution_context.function_scopes = []
        self._execution_context.loop_scopes = []

        return previous

    def _restore_execution_context(self, previous):
        for name, value in previous.items():
            if value is None:
                try:
                    delattr(self._execution_context, name)
                except AttributeError:
                    pass
            else:
                setattr(self._execution_context, name, value)

    # ======================================
    # FUNCTION DISCOVERY
    # ======================================

    @staticmethod
    def _normalize_function_params(params):
        normalized = []

        if not isinstance(params, list):
            return normalized

        for index, parameter in enumerate(params):
            if isinstance(parameter, dict):
                name = parameter.get("name", "")
                parameter_id = parameter.get("id")

            elif isinstance(parameter, str):
                name = parameter
                parameter_id = None

            else:
                continue

            normalized.append({
                "name": str(name),
                "id": parameter_id,
                "index": index
            })

        return normalized

    @classmethod
    def _get_function_params(cls, block):
        if not isinstance(block, dict):
            return []

        extra_state = block.get("extraState", {})

        if not isinstance(extra_state, dict):
            return []

        return cls._normalize_function_params(
            extra_state.get("params", [])
        )

    @staticmethod
    def _get_function_name(block):
        if not isinstance(block, dict):
            return None

        fields = block.get("fields", {})
        extra_state = block.get("extraState", {})

        name = fields.get("NAME")

        if not name and isinstance(extra_state, dict):
            name = extra_state.get("name")

        if name is None:
            return None

        name = str(name).strip()

        return name or None

    def _initialize_functions(self, workflow_data):
        self._functions.clear()

        top_blocks = (
            workflow_data
            .get("blocks", {})
            .get("blocks", [])
        )

        for block in top_blocks:
            if block.get("type") not in self.FUNCTION_DEFINITION_TYPES:
                continue

            name = self._get_function_name(block)

            if not name:
                logger.warning(
                    "Ignored function definition without a name."
                )
                continue

            if name in self._functions:
                logger.warning(
                    "Duplicate function definition ignored: %s",
                    name
                )
                continue

            self._functions[name] = block

        logger.debug(
            "Loaded %s workflow function(s).",
            len(self._functions)
        )

    # ======================================
    # FUNCTION EXECUTION
    # ======================================

    def _execute_function_call(self, block):
        stop_event = self._current_stop_event()

        if stop_event.is_set():
            return None

        function_name = self._get_function_name(block)

        if not function_name:
            logger.warning("Function call has no valid name.")
            return None

        definition = self._functions.get(function_name)

        if definition is None:
            logger.warning(
                "Function '%s' has no matching definition.",
                function_name
            )
            return None

        scopes = self._current_function_scopes()

        if len(scopes) >= self.MAX_FUNCTION_CALL_DEPTH:
            logger.warning(
                "Maximum function call depth reached: %s",
                function_name
            )
            return None

        definition_params = self._get_function_params(definition)
        argument_values = []

        for index, parameter in enumerate(definition_params):
            argument_block = self._get_input_block(
                block,
                f"ARG{index}"
            )

            if argument_block is None:
                logger.warning(
                    "Function '%s' is missing argument %s.",
                    function_name,
                    parameter["name"]
                )
                argument_values.append(None)
                continue

            argument_values.append(
                self._evaluate_value(argument_block)
            )

        if stop_event.is_set():
            return None

        scope = {}

        for parameter, value in zip(
            definition_params,
            argument_values
        ):
            parameter_name = parameter["name"]
            parameter_id = parameter["id"]

            if parameter_name:
                scope[parameter_name] = value

            if parameter_id:
                scope[parameter_id] = value

        scopes.append(scope)

        result = None

        try:
            body = self._get_input_block(definition, "STACK")

            if body:
                self._execute_chain(body)

            if (
                definition.get("type") == "procedures_defreturn"
                and not stop_event.is_set()
            ):
                result = self._evaluate_value(
                    self._get_input_block(definition, "RETURN")
                )

        except _ReturnFunction as returned:
            result = returned.value

        finally:
            if scopes and scopes[-1] is scope:
                scopes.pop()
            elif scope in scopes:
                scopes.remove(scope)

        return result

    def _get_function_argument(self, block):
        fields = block.get("fields", {})
        variable = fields.get("VAR")

        if isinstance(variable, dict):
            argument_id = variable.get("id")
            argument_name = variable.get("name")
        else:
            argument_id = None
            argument_name = variable

        scopes = self._current_function_scopes()

        for scope in reversed(scopes):
            if argument_id and argument_id in scope:
                return scope[argument_id]

            if argument_name is not None:
                argument_name = str(argument_name)

                if argument_name in scope:
                    return scope[argument_name]

        logger.warning(
            "Function argument '%s' has no active value.",
            argument_name
        )

        return None

    # ======================================
    # VARIABLE HELPERS
    # ======================================

    def _initialize_variables(self, workflow_data):
        self._variables.clear()
        self._variable_names.clear()

        variable_models = workflow_data.get("variables", [])

        for variable in variable_models:
            if not isinstance(variable, dict):
                continue

            variable_id = variable.get("id")
            variable_name = variable.get("name")

            if not variable_id:
                continue

            self._variables[variable_id] = 0

            if variable_name:
                self._variable_names[variable_id] = variable_name

    @staticmethod
    def _get_variable_key(variable_field):
        if isinstance(variable_field, dict):
            return (
                variable_field.get("id")
                or variable_field.get("name")
            )

        if isinstance(variable_field, str):
            return variable_field

        return None

    def _get_scoped_variable(self, variable_field):
        if isinstance(variable_field, dict):
            variable_id = variable_field.get("id")
            variable_name = variable_field.get("name")
        else:
            variable_id = None
            variable_name = variable_field

        # Function parameters take precedence over loop variables.
        for scope in reversed(self._current_function_scopes()):
            if variable_id is not None and variable_id in scope:
                return True, scope[variable_id]

            if variable_name is not None:
                if str(variable_name) in scope:
                    return True, scope[str(variable_name)]

        for scope in reversed(self._current_loop_scopes()):
            if variable_id is not None and variable_id in scope:
                return True, scope[variable_id]

            if variable_name is not None:
                if str(variable_name) in scope:
                    return True, scope[str(variable_name)]

        return False, None

    def _set_scoped_variable(self, variable_field, value):
        if isinstance(variable_field, dict):
            variable_id = variable_field.get("id")
            variable_name = variable_field.get("name")
        else:
            variable_id = None
            variable_name = variable_field

        for scopes in (
            self._current_function_scopes(),
            self._current_loop_scopes()
        ):
            for scope in reversed(scopes):
                if variable_id is not None and variable_id in scope:
                    scope[variable_id] = value
                    return True

                if variable_name is not None:
                    name = str(variable_name)

                    if name in scope:
                        scope[name] = value
                        return True

        return False

    def _create_loop_variable_scope(self, variable_field, value):
        scope = {}

        if isinstance(variable_field, dict):
            variable_id = variable_field.get("id")
            variable_name = variable_field.get("name")
        else:
            variable_id = None
            variable_name = variable_field

        if variable_id:
            scope[variable_id] = value

        if variable_name is not None:
            scope[str(variable_name)] = value

        return scope

    # ======================================
    # LOOP EXECUTION
    # ======================================

    def _run_loop_body(self, body, minimum_wait=False):
        if not body:
            return "complete"

        self._change_loop_depth(1)

        if minimum_wait:
            self._change_minimum_wait_loop_depth(1)

        try:
            self._execute_chain(body)

        except _BreakLoop:
            return "break"

        except _ContinueLoop:
            return "continue"

        finally:
            if minimum_wait:
                self._change_minimum_wait_loop_depth(-1)

            self._change_loop_depth(-1)

        return "complete"

    def _execute_repeat_until_stopped(self, block):
        stop_event = self._current_stop_event()
        body = self._get_input_block(block, "DO")

        if not body:
            logger.warning(
                "Repeat Until Stopped has no actions inside it."
            )
            return

        iterations = 0

        while not stop_event.is_set():
            iteration_start = time.perf_counter()

            result = self._run_loop_body(
                body,
                minimum_wait=True
            )

            if result == "break":
                break

            if stop_event.is_set():
                break

            iterations += 1

            elapsed = time.perf_counter() - iteration_start
            remaining = self.MIN_CONTINUOUS_LOOP_INTERVAL - elapsed

            if remaining > 0:
                stop_event.wait(remaining)
            else:
                time.sleep(0)

        logger.debug(
            "Repeat Until Stopped exited after %s iterations.",
            iterations
        )

    def _execute_repeat(self, block):
        stop_event = self._current_stop_event()
        inputs = block.get("inputs", {})
        fields = block.get("fields", {})

        count_block = (
            inputs.get("TIMES", {}).get("block")
            or inputs.get("TIMES", {}).get("shadow")
        )

        count = self._number_from_block(count_block)

        if block.get("type") == "controls_repeat":
            count = fields.get("TIMES", count)

        try:
            numeric_count = float(count)

            if not math.isfinite(numeric_count):
                return

            count = max(0, int(numeric_count))

        except (TypeError, ValueError, OverflowError):
            logger.warning(
                "Invalid repeat count: %r",
                count
            )
            return

        body = self._get_input_block(block, "DO")

        for _ in range(count):
            if stop_event.is_set():
                break

            result = self._run_loop_body(body)

            if result == "break":
                break

            time.sleep(0)

    def _execute_while_until(self, block):
        stop_event = self._current_stop_event()
        fields = block.get("fields", {})
        mode = fields.get("MODE", "WHILE")

        body = self._get_input_block(block, "DO")

        if not body:
            return

        iterations = 0

        while not stop_event.is_set():
            condition = bool(
                self._evaluate_value(
                    self._get_input_block(block, "BOOL")
                )
            )

            should_run = (
                condition if mode == "WHILE"
                else not condition
            )

            if not should_run:
                break

            result = self._run_loop_body(
                body,
                minimum_wait=True
            )

            if result == "break":
                break

            iterations += 1

            if iterations % 100 == 0:
                time.sleep(0)
            elif not stop_event.is_set():
                stop_event.wait(self.MIN_CONTINUOUS_LOOP_INTERVAL)

    def _execute_for(self, block):
        stop_event = self._current_stop_event()
        fields = block.get("fields", {})

        variable_field = fields.get("VAR")
        start = self._safe_number(
            self._evaluate_value(
                self._get_input_block(block, "FROM")
            )
        )
        end = self._safe_number(
            self._evaluate_value(
                self._get_input_block(block, "TO")
            )
        )
        step = self._safe_number(
            self._evaluate_value(
                self._get_input_block(block, "BY")
            ),
            1
        )

        if step == 0:
            logger.warning("For loop step cannot be zero.")
            return

        if not all(math.isfinite(value) for value in (start, end, step)):
            logger.warning("For loop received an invalid numeric value.")
            return

        body = self._get_input_block(block, "DO")
        if not body:
            return

        current = start
        iterations = 0

        def in_range(value):
            return value <= end if step > 0 else value >= end

        while in_range(current) and not stop_event.is_set():
            scope = self._create_loop_variable_scope(
                variable_field,
                current
            )

            scopes = self._current_loop_scopes()
            scopes.append(scope)

            try:
                result = self._run_loop_body(body)
            finally:
                if scopes and scopes[-1] is scope:
                    scopes.pop()
                elif scope in scopes:
                    scopes.remove(scope)

            if result == "break":
                break

            current += step
            iterations += 1

            if iterations % 100 == 0:
                time.sleep(0)

    def _execute_for_each(self, block):
        stop_event = self._current_stop_event()
        variable_field = block.get("fields", {}).get("VAR")

        values = self._evaluate_value(
            self._get_input_block(block, "LIST")
        )

        if values is None:
            return

        if isinstance(values, dict):
            values = list(values.values())
        elif isinstance(values, (str, list, tuple, set)):
            values = list(values)
        else:
            logger.warning(
                "For Each requires a list, tuple, set, string, or dictionary."
            )
            return

        body = self._get_input_block(block, "DO")
        if not body:
            return

        for index, value in enumerate(values):
            if stop_event.is_set():
                break

            scope = self._create_loop_variable_scope(
                variable_field,
                value
            )

            scopes = self._current_loop_scopes()
            scopes.append(scope)

            try:
                result = self._run_loop_body(body)
            finally:
                if scopes and scopes[-1] is scope:
                    scopes.pop()
                elif scope in scopes:
                    scopes.remove(scope)

            if result == "break":
                break

            if index % 100 == 99:
                time.sleep(0)

    # ======================================
    # CONDITIONAL EXECUTION
    # ======================================

    def _execute_if(self, block):
        inputs = block.get("inputs", {})
        branch_index = 0
        stop_event = self._current_stop_event()

        while not stop_event.is_set():
            condition_name = f"IF{branch_index}"
            body_name = f"DO{branch_index}"

            if condition_name not in inputs:
                break

            condition_block = self._get_input_block(
                block,
                condition_name
            )

            if bool(self._evaluate_value(condition_block)):
                body = self._get_input_block(block, body_name)

                if body:
                    self._execute_chain(body)

                return

            branch_index += 1

        if stop_event.is_set():
            return

        else_body = self._get_input_block(block, "ELSE")

        if else_body:
            self._execute_chain(else_body)
