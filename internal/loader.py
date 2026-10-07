import json5
import os.path
import ipaddress
import macaddress
import logging

from ipaddress import IPv4Address, IPv4Network

import portion as P
from portion import Interval

from internal.graph import NetworkGraph, Node, Edge
from internal.state import SymbolicOperand
from internal.util import is_cidr, is_ip, is_mac, str_const_to_int
from internal.util import is_edge_rejected, is_node_accepted, is_node_rejected

# Parses a label string in the format <key>:<value> <key>:<value>
# Returns a dictionary that maps each key to the label values. Labels
# currently only support string values and thus only exact matches
def parse_labels(label_str: str) -> dict[str, list[SymbolicOperand]]:
    parts: list[str] = label_str.split(" ")
    labels: dict[str, list[SymbolicOperand]] = {}
    
    for part in parts:
        label_split: list[str] = part.split(":")
        label_name: str = label_split[0]
        labels[label_name] = parse_label_operand(label_split[1])

    return labels

# Parses a single label operand in the form:
#
# - value1|value2,value3
# - value3
# - >value4
#
def parse_label_operand(label_value: str) -> list[SymbolicOperand]:
    value_parts: list[str] = label_value.split(",")

    operands: list[SymbolicOperand] = []
    for value in value_parts:
        operands.append(parse_operand(value))

    return operands

# Parses an initial state string into dictionary that maps state variables
# to corresponding portion Intervals. This function can accept two data-types:
# a string or a list. If the input is a string, it must have the format
# <key>:<value> <key>:<value>. If the input string is a list, it is assumed
# that the list contains strings each with one key value pair, so ["<key>:<value>", ...].
def parse_initial_state(label_data) -> dict[str, SymbolicOperand]:
    state_vars: dict[str, SymbolicOperand] = {}

    parts: list[str] = None
    if type(label_data) is str:
        parts = label_data.split(" ")
    elif type(label_data) is list:
        parts = label_data
    else:
        print(f"Error: expected type str or list[str], got {type(label_data)}")
        return None

    for part in parts:
        var_split: list[str] = part.split(":")
        var_name: str = var_split[0]
        var_value: str = var_split[1]
        state_vars[var_name] = parse_operand(var_value)
    
    return state_vars

# Loads a graph schema from a filepath and returns its content as a parsed
# python dictionary. If the file is not found, the function calls exit(1).
def load_schema_file(filepath: str):
    if os.path.isfile(filepath):
        with open(filepath) as f:
            return json5.load(f)
    else:
        print(f"File {filepath} not found, exiting.")
        exit(1)

# Parses the operand of an action or match guard statement. For information
# how these operands may be structured please consult the README. The function
# returns a symbolic operand, which, depending on the parsed content, has a
# type hint set to indicate which format the original data had, e.g. ipv4.
def parse_operand(operand_str: str) -> SymbolicOperand:
    logger = logging.getLogger(__name__)

    # Wildcard operand
    if operand_str == "*":
        return SymbolicOperand(P.closed(-P.inf, P.inf), None)

    # Empty operand can be used e.g. in actions to clear out value from the state
    if operand_str == "":
        return SymbolicOperand(None, None)

    # Currently, braces are not allowed in expressions. If an expression is negated,
    # it applies to the whole operand. Thus we capture this here, and apply it at the end.
    complement: bool = False
    if operand_str.startswith("!"):
        operand_str = operand_str[1:]
        complement = True
        
    # Operand may contain multiple parts which are combined with a union.
    parts: list[str] = operand_str.split("|")

    operand: Interval = P.empty()

    # Type hint is set depending on parsed content: if the parser encounters
    # e.g. an IPv4, it sets the type hint accordingly so that during pretty-printing,
    # the original "type" of the operand can be faithfully reproduced.
    type_hint: str = None

    # Iterate over all parts, union them together after each round.
    for part in parts:
        # Manual ranges have the format <value>-<value>. Both values must be numeric, as
        # ranges for strings are not supported.
        is_manual_range: bool = False
        if "-" in part:
            range_split: list[str] = part.split("-")
            if len(range_split) == 2 and (range_split[0].isnumeric() and range_split[1].isnumeric()) or (is_ip(range_split[0]) and is_ip(range_split[1])) or (is_mac(range_split[0]) and is_mac(range_split[1])):
                is_manual_range = True

        part_interval: Interval = None

        if part == "*":
            part_interval = SymbolicOperand(P.closed(-P.inf, P.inf), None)
        elif part == "":
            part_interval = SymbolicOperand(None, None)
        elif part.startswith((">", "<")):
            # Range defined with comparison operators, e.g. >=100
            if part.startswith((">=", "<=")):
                bigger = part.startswith(">=")
                part = part[2:]

                # For the range we need the numeric value. We thus have to infer
                # the data format, e.g. MAC/IPv4 address, convert it to int, and
                # set the type hint accordingly.
                parsed = None
                if is_ip(part):
                    parsed: int = int(ipaddress.ip_address(part))
                    type_hint = "ipv4"
                elif is_mac(part):
                    parsed: int = int(macaddress.EUI48(part))
                    type_hint = "mac"
                elif part.isnumeric():
                    parsed: int = int(part)
                else:
                    logger.error(f"Cannot build range with value {part}")
                    exit(1)
                
                if bigger:
                    part_interval: Interval = P.closed(parsed, P.inf)
                else:
                    part_interval: Interval = P.closed(-P.inf, parsed)
            else:
                bigger = part.startswith(">")
                part = part[1:]

                # For the range we need the numeric value. We thus have to infer
                # the data format, e.g. MAC/IPv4 address, convert it to int, and
                # set the type hint accordingly.
                parsed = None
                if is_ip(part):
                    parsed: int = int(ipaddress.ip_address(part))
                    type_hint = "ipv4"
                elif is_mac(part):
                    parsed: int = int(macaddress.EUI48(part))
                    type_hint = "mac"
                elif part.isnumeric():
                    parsed: int = int(part)
                else:
                    logger.error(f"Cannot build range with value {part}")
                    exit(1)

                if bigger:
                    parsed += 1
                    part_interval: Interval = P.closed(parsed, P.inf)
                else:
                    parsed -= 1
                    part_interval: Interval = P.closed(-P.inf, parsed)
        elif is_manual_range:
            # Manually defined range: <value>-<value>
            lower: int = None
            higher: int = None

            range_split: list[str] = part.split("-")
            if is_ip(range_split[0]) and is_ip(range_split[1]):
                # Manually defined IP Range
                lower = int(ipaddress.ip_address(range_split[0]))
                higher = int(ipaddress.ip_address(range_split[1]))
                type_hint = "ipv4"
            elif is_mac(range_split[0]) and is_mac(range_split[1]):
                # Manually defined MAC Range
                lower = int(macaddress.EUI48(range_split[0]))
                higher = int(macaddress.EUI48(range_split[1]))
                type_hint = "mac"
            elif range_split[0].isdigit and range_split[1]:
                # Integer range
                lower: int = int(range_split[0])
                higher: int = int(range_split[1])
            else:
                print(f"Error: cannot process range operand {part}")
                exit(1)

            if lower > higher:
                logger.error(f"Found interval definition '{part}': ensure format is <lower>-<higher>.")
                exit(1)

            part_interval: Interval = P.closed(lower, higher)
        # Standalone IPv4/IPv6 address
        elif is_ip(part):
            ip_address = ipaddress.ip_address(part)
            if type(ip_address) is IPv4Address:
                type_hint = "ipv4"
            else:
                type_hint = "ipv6"
            part_interval = P.singleton(int(ip_address))
        # Standalone IPv4/IPv6 network
        elif is_cidr(part):
            ip_network = ipaddress.ip_network(part)
            if type(ip_network) is IPv4Network:
                type_hint = "ipv4"
            else:
                type_hint = "ipv6"
            part_interval: Interval = P.closed(int(ip_network.network_address), int(ip_network.broadcast_address))
        # Standalone MAC address
        elif is_mac(part):
            part_interval = P.singleton(int(macaddress.EUI48(part)))
            type_hint = "mac"
        # Plain numeric value
        elif part.isnumeric():
            part_interval = P.singleton(int(part))
        # If nothing else matched, we interpret the value as a string constant.
        else:
            # Map string constants to ints to let portion operate on plain integers,
            # map them back later when printing them.
            part_interval = P.singleton(str_const_to_int(part))
            type_hint = "code"

        # Keep adding to the existing operand with unions, since each part was split
        # by the '|' operator
        operand = operand | part_interval
    
    # Finally, if initially the operand was negated, negate the result here
    if complement:
        operand = ~operand

    return SymbolicOperand(operand, type_hint)

# Given a dictionary that maps state variable names to match guard or action operands
# as strings, this function constructs a dict with the same keys
# but each value parsed as symbolic operands.
def parse_match_action_dict(input_dict: dict[str, str]) -> dict[str, SymbolicOperand]:
    result: dict[str, SymbolicOperand] = {}
    for key in input_dict:
        result[key] = parse_operand(input_dict[key])
    return result

# Given a dictionary that contains schema file data, e.g. loaded with
# load_schema_file(), this function parses the data into a network graph
# instance. This includes parsing the included data such as match guards
# into their respective symbolic operands.
def load_graph_from_dict(graph_data: dict) -> NetworkGraph:
    nodes: dict[str, Node] = {}
    edges: dict[str, list[Edge]] = {}

    # Parse nodes first
    nodes_list: list = graph_data["nodes"]
    for node_dict in nodes_list:
        node_name: str = node_dict["id"]
        
        node_labels_raw: dict[str] = node_dict.get("labels", {})
        node_labels: dict[str, list[SymbolicOperand]] = {}
        for label in node_labels_raw:
            value = node_labels_raw[label]
            value_operands: list[SymbolicOperand] = parse_label_operand(str(value))
            node_labels [label] = value_operands

        if "id" not in node_labels:
            node_labels["id"] = [SymbolicOperand(P.singleton(str_const_to_int(node_name)), "code")]

        node: Node = Node(node_name, node_labels)
        nodes[node_name] = node

        # Initialize edge list for each node
        edges[node_name] = []

    # Parse edges, including their match/actions
    edges_list: list = graph_data["edges"]
    for edge_dict in edges_list:
        edge_name: str = edge_dict["id"]
        edge_src: str = edge_dict["src"]
        edge_dst: str = edge_dict["dst"]

        match_dict: dict = edge_dict.get("match", None)
        actions_dict: dict = edge_dict.get("actions", None)

        match_guard: dict[str, Interval] = {}
        if match_dict is not None:
            match_guard = parse_match_action_dict(match_dict)

        actions: dict[str, Interval] = {}
        if actions_dict is not None:
            actions = parse_match_action_dict(actions_dict)

        edge_labels_raw: dict[str] = edge_dict.get("labels", {})
        edge_labels: dict[str, list[SymbolicOperand]] = {}
        for label in edge_labels_raw:
            value = edge_labels_raw[label]
            value_operands: list[SymbolicOperand] = parse_label_operand(value)
            edge_labels [label] = value_operands

        if "id" not in edge_labels:
            edge_labels["id"] = [SymbolicOperand(P.singleton(str_const_to_int(edge_name)), "code")]

        edge: Edge = Edge(edge_name, nodes[edge_src], nodes[edge_dst], match_guard, actions, edge_labels)

        edge.match_guard_str = match_dict
        edge.actions_str = actions_dict

        edges[edge_src].append(edge)

    return NetworkGraph(nodes, edges)

# Loads a schema model from a file at the given file path, parses
# the data into a network graph instance and returns it.
def load_from_file(filepath: str) -> NetworkGraph:
    graph_data: dict = load_schema_file(filepath)
    if graph_data is None:
        return None
    
    graph: NetworkGraph = load_graph_from_dict(graph_data)
    return graph

# Pre-computes accept and reject conditions for all nodes and
# edges in the graph. Since the metadata and accept/reject labels 
# are static, we can pre-compute the value and check it instead
def mark_accepts_and_rejects(graph: NetworkGraph, accept_labels: dict[str, list[str]], reject_labels: dict[str, list[str]]):
    for node_name in graph.nodes:
        node = graph.nodes[node_name]
        node.is_accepted = is_node_accepted(node, accept_labels)
        node.is_rejected = is_node_rejected(node, reject_labels)

        for edge in graph.edges[node_name]:
            edge.is_rejected = is_edge_rejected(edge, reject_labels)