import re

import ipaddress
import macaddress
import portion as P
from portion import Interval

from internal.state import SymbolicState, SymbolicOperand, codes, labels
from internal.graph import NetworkGraph
from internal.graph import Node, Edge

# Reads the 'speed' label of the given edge and parses the encoded speed, e.g. 10G, into
# a bits-per-second numberic. If no speed label is present, infinity is returned.
def get_flow_capacity(edge: Edge) -> float:
    speed_bytes = float("inf")
    
    if "speed" in edge.labels:
        speed_values = edge.labels["speed"]    
        if len(speed_values) > 1:
            logger.error(f"Got multiple values for speed label on edge {edge.name}: {speed_values}")
            exit(1)
        speed_parsed = parse_speed_label(str(speed_values [0]))
        if speed_parsed is None:
            emit_error(f"Speed Label {speed_value} is invalid, expected <number>[K,M,G,T]")
            exit(1)

        speed_bytes = speed_parsed

    return speed_bytes

# Get a label and divisor to format a network link speed. For example,
# for 20000000000.0, so 20*1e9, the function returns "G" and 1e9. To format:
#
# f"{speed / divisor}{label}"
#
def get_speed_unit_step(speed: float):
    speed_labels = ["K", "M", "G", "T"]
    label = ""
    divisor = 1

    while speed > 1000:
        label = speed_labels.pop(0)
        speed /= 1000
        divisor *= 1000

    return label, divisor

# Formats a bits-per-second value into a pretty-print string.
# For example, an input of 1000.0 results in 1K.
def format_speed(speed: float) -> str:
    label, divisor = get_speed_unit_step(speed)
    divided = speed / divisor
    return f"{int(divided)}{label}" if divided.is_integer() else f"{speed / divisor}{label}"

# Prunes the given path result set. Pruning is defined as excluding paths
# from the result set that are prefixes of longer paths.
def prune_paths(paths: list[tuple[SymbolicState, list[Edge]]]) -> list[tuple[SymbolicState, list[Edge]]]:
    # Sort paths by length descending
    paths_sorted = paths[:]
    paths_sorted.sort(key=lambda path: len(path [1]), reverse=True)

    # Work through pruned paths: add all paths that are not already in the list
    pruned_paths = []
    for final_state, path in paths_sorted:
        prune = False
        for pruned_path in pruned_paths:
            # Pruned paths [1] = edge list, index 0 is final state
            # The slice returns the first edges in the list, which we
            # compare to the current path. If they match, the shorter
            # path is a prefix of the longer path -> prune the shorter path
            if pruned_path [1] [:len(path)] == path:
                prune = True
                break

        if not prune:
            pruned_paths.append((final_state, path))

    return pruned_paths

def parse_speed_label(input: str) -> int:
    speed_steps = [
        [re.compile(r"\d+(?:\.\d+)?T"), 1e12],
        [re.compile(r"\d+(?:\.\d+)?G"), 1e9],
        [re.compile(r"\d+(?:\.\d+)?M"), 1e6],
        [re.compile(r"\d+(?:\.\d+)?K"), 1e3]
    ]

    for pattern, multiplier in speed_steps:
        if pattern.fullmatch(input):
            input = input[:-1]
            speed_bytes = float(input) * multiplier
            return speed_bytes

    pattern_bytes = re.compile(r"\d+")
    if pattern_bytes.fullmatch(input):
        return int(input)

    return None

# Returns true iff the given node is rejected by the given reject label set.
# A reject is defined that at least one of the reject labels matches a node
# label. Labels that are present in the reject set but not in the node label
# set do not lead to an rejected node.
def is_node_rejected(node: Node, reject_labels: dict[str, SymbolicOperand]):
    for key in reject_labels:
        if key in node.labels:
            reject_operands: list[SymbolicOperand] = reject_labels[key]
            node_operands: list[SymbolicOperand] = node.labels[key]

            for node_operand in node_operands:
                match = True
                for reject_operand in reject_operands:
                    intersection : Interval = node_operand.operand & reject_operand.operand
                    match &= not intersection.empty

                if match:
                    return True
    
    return False

# Returns true iff the given edge is rejected by the given reject label set.
# A reject is defined that at least one of the reject labels matches a edge
# label. Labels that are present in the reject set but not in the edge label
# set do not lead to an rejected edge.
def is_edge_rejected(edge: Edge, reject_labels: dict[str, SymbolicOperand]):
    for key in reject_labels:
        if key in edge.labels:
            reject_operands: list[SymbolicOperand] = reject_labels[key]
            edge_operands: list[SymbolicOperand] = edge.labels[key]

            for edge_operand in edge_operands:
                match = True
                for reject_operand in reject_operands:
                    intersection : Interval = edge_operand.operand & reject_operand.operand
                    match &= not intersection.empty
                    
                if match:
                    return True
    
    return False

# Returns true iff the given node is accepted by the given reject label set.
# A reject is defined that all accept labels are present in the node and equal
# the defined value.
def is_node_accepted(node: Node, accept_labels: dict[str, SymbolicOperand]):
    for key in accept_labels:
        if key not in node.labels:
            return False

        accept_operands: list[SymbolicOperand] = accept_labels[key]
        node_operands: list[SymbolicOperand] = node.labels[key]

        for node_operand in node_operands:
            for accept_operand in accept_operands:
                intersection : Interval = node_operand.operand & accept_operand.operand
                if intersection.empty: 
                    return False

    return True

# Maps a unique label to a unique sympy integer. Sympy treats strings as
# symbols, which can cause issues when intersecting sets. The simple fix
# is to map strings to integers, then perform the set operations, then
# map them back when printing them out.
def str_const_to_int(label: str):
    if label in codes:
        return codes[label]
    else:
        codes[label] = int(len(codes))
        labels[codes[label]] = label
        return codes[label]

# Returns true if the given string is a valid IP address. Both
# IPv4 and IPv6 address strings may be passed.
def is_ip(ip_string: str) -> bool:
    # https://www.plaintextnerds.com/articles/networks-validating-ips-python/
    try:
        ipaddress.ip_address(ip_string)
        return True
    except ValueError:
        return False

# Returns true if the given string is a valid EUI48 MAC address.
def is_mac(mac_string: str) -> bool:
    try:
        macaddress.EUI48(mac_string)
        return True
    except ValueError:
        return False

# Returns true if the given string is a valid IPv4 or IPv6 subnet
# string.
def is_cidr(cidr_string: str):
    try:
        ipaddress.ip_network(cidr_string, strict=False)
        return True
    except ValueError:
        return False

# Prints out the given paths to stdout. The printout includes the index
# of the path, the nodes, edges, and final state of the path.
def print_paths(paths: list[tuple[SymbolicState, list[Edge]]]):
    for i in range(0, len(paths)):
        path = paths[i]
        print(f"  Path {i+1}:")
        node_names = [path[1][0].src.name]
        for edge in path[1]:
            node_names.append(edge.dst.name)
        print(f"    Nodes: {str(node_names)}")
        print(f"    Edges: {str(path[1])}")
        print(f"    State: {str(path[0])}")
        
        if i < len(paths) - 1:
            print()

# Formats the given symbolic state into a dictionary of string key-value
# pairs. Each state variable maps to its name as key, and a string representation
# of its symbolic operand.
def state_to_dict(state: SymbolicState) -> dict[str, str]:
    state_dict: dict = {}
    for key in state.state:
        state_dict[key] = str(state.state[key])
    return state_dict

# Formats the given match/action dict to a dictionary of string ke-value
# pairs. This function works both for match-guards as well for actions, as both
# define a state variable and a corresponding symbolic operand. The resulting
# dict maps each variable name to a key and its operand to its string representation.
def match_action_to_dict(match_action_dict: dict[str, SymbolicOperand]) -> dict[str, str]:
    output: dict = {}
    for key in match_action_dict:
        output[key] = str(match_action_dict[key])
    return output

# Converts the given path set to a dictionary to emit as json. The resulting dict
# has the format:
#
# {
#   path_count: <number of paths>,
#   initial_state: {
#     <key>: <value>
#   },
#   paths: [
#     {
#       nodes: [<names of nodes on path>],
#       edges: [<names of edges on path>],
#       final_state: {
#         <key>: <value>
#       },
#       start_labels: { // labels of start node
#         <key>: <value>
#       },
#       hops: [
#         {
#           edge: {
#             id: <name of edge>,
#             src: <name of src node>,
#             dst: <name of dst node>,
#             labels: <labels of edge>,
#             match: { // match guard of the edge
#               <key>: <value>
#             },
#             actions: { // actions of the edge
#               <key>: <value>
#             }
#           },
#           state_before: {
#             <key>: <value>
#           },
#           state_after: {
#             <key>: <value>
#           },
#           dst_labels: {
#             <key>: <value>
#           }
#         }
#       ]
#     }
#   ]
# }
#
def paths_to_dict(graph: NetworkGraph, start_node: Node, initial_state: SymbolicState, paths: list[tuple[SymbolicState, list[Edge]]]):
    output: dict = {}

    output["path_count"] = len(paths)
    output["initial_state"] = {}
    output["paths"] = []

    for path in paths:
        path_dict: dict = {}

        state, edges = path

        nodes: list = [start_node.name]
        for edge in edges:
            nodes.append(edge.dst.name)
        path_dict["nodes"] = nodes

        edge_names = []
        for edge in edges:
            edge_names.append(str(edge))
        path_dict["edges"] = None if not edges else edge_names

        path_dict["final_state"] = state_to_dict(state)
        path_dict["start_labels"] = {}
        labels = graph.nodes[start_node.name].labels
        for key in labels:
            path_dict["start_labels"] [key] = ", ".join(map(str, labels [key]))

        working_state = initial_state.copy()

        hops: list = []
        for edge in edges:
            edge_dict = {}
            edge_dict["id"] = edge.name
            edge_dict["src"] = edge.src.name
            edge_dict["dst"] = edge.dst.name
            edge_dict["labels"] = {}
            for key in edge.labels:
                edge_dict["labels"] [key] = ", ".join(map(str, edge.labels [key]))
            edge_dict["match"] = match_action_to_dict(edge.match_guard)
            edge_dict["actions"] = match_action_to_dict(edge.actions)

            hop_dict = {}
            hop_dict["edge"] = edge_dict
            
            hop_dict["state_before"] = state_to_dict(working_state)
            working_state.narrow_state(edge.match_guard)
            working_state.apply_actions(edge.actions)
            hop_dict["state_after"] = state_to_dict(working_state)
            
            hop_dict["dst_labels"] = {}
            for key in edge.dst.labels:
                hop_dict["dst_labels"] [key] = ", ".join(map(str, edge.dst.labels [key]))

            hops.append(hop_dict)

        path_dict["hops"] = None if not edges else hops

        output["paths"].append(path_dict)

    return output

# Formats the given network graph to a dict to dump as json. The dict has
# the following format:
#
# {
#   nodes: [
#     {
#       id: <node name>,
#       labels: {
#         <key>: <value>
#       }
#     },
#     ...
#   ],
#   edges: [
#     {
#       id: <name of the edge>,
#       src: <name of the src node>,
#       dst: <name of the dst node>,
#       match: {
#         <key>: <value>
#       },
#       actions: {
#         <key>: <value>
#       },
#       labels: {
#         <key>: <value>
#       }
#     },
#     ...
#   ]
# }
#
def graph_to_dict(graph: NetworkGraph):
    output: dict = {}

    nodes_list: list = []
    for node_name in graph.nodes:
        node = graph.nodes[node_name]

        nodes_list.append({
            "id": node.name,
            "labels": node.labels,
        })

    output["nodes"] = nodes_list

    edges_list: list = []
    for edge_name in graph.edges:
        edge = graph.edges[edge_name]

        edges_list.append({
            "id": edge_name,
            "src": edge.src.name,
            "dst": edge.dst.name,
            "match": edge.match_guard_str,
            "actions": edge.actions_str,
            "labels": edge.labels
        })

    output["edges"] = edges_list

    return output

