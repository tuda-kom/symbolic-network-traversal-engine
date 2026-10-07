from copy import deepcopy
from typing import Optional

import portion as P
from portion import Interval

import ipaddress
import macaddress

# Tracks string to integer mappings: we map string constants used in the graph
# to integers before using them in Portion so it can operate purely on numeric
# intervals. If strings are used, they can be interpreted as variables, causing
# the set operations to be incorrect. See also the function str_const_to_int()
codes: dict[str, int] = {}

# The reverse of the codes-map: maps an int to the corresponding string constant
# when printing symbolic operands / interval values.
labels: dict[int, str] = {}

# Formats a single int value from a portion interval to its
# correct format based ont he given type hint. This can be either
# an IPv4 address, a MAC address, a string constant, or a plain
# integer.
def format_singleton(value: int, type_hint: str) -> str:
    if type_hint == "ipv4":
        return str(ipaddress.IPv4Address(value))
    elif type_hint == "mac":
        return str(macaddress.MAC(value)).replace('-', ':')
    elif type_hint == "code":
        return labels[value]
    else:
        return str(value)

# Formats an atomic interval range to its correct format based
# on the given type hint. This can be either an IPv4 Subnet, an
# IPv4 range, a MAC-address range, a string constant range,
# or a plain integer range
def format_atomic(lower: int, upper: int, type_hint: str) -> str:
    if type_hint == "ipv4":
        lower_addr = ipaddress.IPv4Address(int(lower))
        upper_addr = ipaddress.IPv4Address(int(upper))
        summary = list(ipaddress.summarize_address_range(lower_addr, upper_addr))
        if len(summary) == 1:
            return f"{str(summary [0])}"
        else:
            return f"{str(ipaddress.IPv4Address(int(lower)))}-{str(ipaddress.IPv4Address(int(upper)))}"
    elif type_hint == "mac":
        return str(macaddress.MAC(int(lower))).replace('-', ':') + "-" + str(macaddress.MAC(int(upper))).replace('-', ':')
    elif type_hint == "code":
        return labels[int(lower)] + "-" + labels[int(upper)]
    else:
        return str(lower) + "-" + str(upper)

# Formats the given portion interval based on the given type hint.
# This can be either an empty interval, a singleton, an atomic,
# or a union of multiple atomics. Also implements some special cases,
# like negated IPv4 CIDRs. This function should be used as entrypoint
# for formatting any interval to string.
def format_interval(interval: Interval, type_hint: str) -> str:
    if interval.empty:
        return ""
    elif interval.lower == interval.upper:
        return format_singleton(int(interval.lower), type_hint)
    elif interval.atomic:
        return format_atomic(int(interval.lower), int(interval.upper), type_hint)
    else:
        # Special Case: !<cidr>
        if interval.lower == -P.inf and interval.upper == P.inf:
            formatted = ""
            for i in range(0, len(interval) - 1):
                low = interval[i].upper
                up = interval[i + 1].lower

                if low == up:
                    formatted += format_singleton(low, type_hint) + "|"
                else:
                    formatted += format_atomic(low, up, type_hint) + "|"

            return "!" + formatted[:-1]
        else:
            formatted = ""

            for step in interval:
                lower = step.lower + 1 if step.left == P.OPEN else step.lower
                upper = step.upper - 1 if step.right == P.OPEN else step.upper

                if lower == upper:
                    formatted += format_singleton(lower, type_hint) + "|"
                else:
                    formatted += format_atomic(lower, upper, type_hint) + "|"
            
            if formatted.endswith("|"):
                formatted = formatted[:-1]

            return formatted

# Bundles a portion interval together with meta-information. Also includes string-formatting
# helpers. Symbolic operands are used whenever state variables, match/actions are
# used or evaluated.
class SymbolicOperand:

    # Portion interval that describes the values contained in this operand. In the case of
    # a state variable, it describes all values contained in the state. in the case
    # of a match guard, it captures all allowed values for this match guard.
    operand: Interval

    # Set during parsing, e.g. "ipv4" to aid during pretty-printing to format the output
    # faithfully as it was in the input. Since all strings, ipaddresses etc. are converted
    # to ints internally, we lose the type information. This value attempts to retain it.
    type_hint: str

    def __init__(self, operand: Interval, type_hint: Optional[str]):
        self.operand = operand
        self.type_hint = type_hint

    # Function to convert this operand to a string. Based on the type hint,
    # various custom printers may be used to format the values in the SymPy set.
    # However, there are some cases where sympy cannot resolve the set fully, e.g.
    # when a complement against a universal set is made, e.g. with the operand !10.0.0.0/8.
    # In these cases, manual post-processing is applied to format the output
    # more closely to the syntax found in the schema file.
    def __repr__(self) -> str:
        if self.operand is None:
            return ""
        return format_interval(self.operand, self.type_hint)

    # Function override to hash this object.
    def __hash__(self) -> int:
        return hash((self.operand, self.type_hint))
            
# Bundles multiple state variables into a single object. Contains a dictionary
# that maps variable names to symbolic oprands. Also contains helper functions
# to apply match/actions, check for subsumption etc.
class SymbolicState:
    
    # Maps variable names to symbolic operands
    state: dict[str, SymbolicOperand]

    def __init__(self, state: Optional[dict[str, SymbolicOperand]]):
        self.state = {}
        if state is not None:
            self.state = state

    # Function to convert this state into string representation. The output format is:
    # { <key>: <value>, ... }, where the value is formatted according to the __repr__
    # override of the symbolic operand.
    def __repr__(self) -> str:
        printed: str = "{"
        
        for key in self.state:
            printed += key + ": " + str(self.state[key]) + ", "
        
        # Remove the last ', ' segment
        if len(self.state) > 0:
            printed = printed[:-2]
        
        printed += "}"
        return printed

    # Applies the given match guards to the given state by:
    #   - adding the interval with key to the state if the state does not contain the key
    #   - intersecting the value in the state with the interval of the match guard otherwise
    def narrow_state(self, match_guard: dict[str, SymbolicOperand]):
        for key in match_guard:
            if key in self.state:
                state_value : Interval = self.state[key].operand
                self.state[key].operand = state_value & match_guard[key].operand
            else:
                self.state[key] = deepcopy(match_guard[key])

    # Apply the given actions to the state by overwriting the variables with the values given
    # in the actions dict
    def apply_actions(self, actions: dict[str, SymbolicOperand]):
        for key in actions:
            if actions[key].operand is None:
                if key in self.state:
                    del self.state[key]
            else:
                self.state[key] = deepcopy(actions[key])

    # Checks if the given match guards match the current state. The state matches the guard if
    # for all variables, the intersection does not produce an empty set.
    def matches(self, match_guard: dict[str, SymbolicOperand]) -> bool:
        for key in match_guard:
            if key in self.state:
                intersection : Interval = self.state[key].operand & match_guard[key].operand
                if intersection.empty: 
                    return False
            else:
                # Variables not in the state are considered a wildcard by default
                pass

        return True

    # Returns true if this state subsumes the other state, i.e. for every variable, the other state
    # is fully contained in this state
    def subsumes(self, other_state: "SymbolicState") -> bool:
        for key in other_state.state:
            if key not in self.state:
                # Not contained = wildcard
                continue
                
            other_value: Interval = other_state.state[key].operand
            self_value: Interval = self.state[key].operand

            if not other_value in self_value:
                return False

        return True       

    # Function override to hash this object.
    def __hash__(self) -> int:
        return hash(frozenset(self.state.items()))
    
    # Creates a deepcopy of this state.
    def copy(self) -> "SymbolicState":
        return SymbolicState(deepcopy(self.state))