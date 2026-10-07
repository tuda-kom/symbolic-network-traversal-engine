import sys
import argparse
import logging
import re
import math
import json

from internal.search_bfs import search_bfs
from internal.state import SymbolicState, SymbolicOperand
from internal.util import format_speed, graph_to_dict, str_const_to_int, is_node_accepted, get_flow_capacity
from internal.loader import parse_labels, load_from_file, mark_accepts_and_rejects
from internal.graph import NetworkGraph, Node, Edge
from internal.maxflow import DinicMaxFlow

import portion as P

# Maps formatted node name strings to the corresponding edges. Key format:
# <src node name>,<dst node name>
# For example: node-a,node-b -> Edge
node_name_to_edge_name: dict[str, Edge] = {}

# Default mode for stdout output format.
args_output = "text"

# Verifies the resulting flow values after run() completes. Returns a boolean which
# is true if all checks pass, and false if at least one check fails. Also returns a
# list of strings that contains errors / reasons why the given flow is invalid. This list
# is empty if the flow is valid.
def verify_maxflow_result(result: DinicMaxFlow) -> tuple[bool, list[str]]:
    valid: bool = True

    source: int = result.source
    drain: int = result.drain

    logger = logging.getLogger(__name__)

    errors: list[str] = []

    # 1. No negative flow values
    for i in range(0, result.N):
        for child in result.adjacency_list [i]:
            if result.capacities [i] [child] < 0:
                errors.append(f"Negative flow value between {i} and {child}!")
                valid = False

    # 2. No flow value exceeding the upper bound of an edge
    for i in range(0, result.N):
        for child in result.adjacency_list [i]:
            if result.capacities [i] [child] > result.upper_bounds [i] [child]:
                errors.append(f"Flow value exceeds upper bound between {i} and {child}!")
                valid = False

    # 3. Flow into node is equal to flow out of node, except for source and drain
    for i in range(0, result.N):
        if i == source or i == drain:
            continue

        flow_in: int = 0
        for a in range(0, result.N):
            if i == a:
                continue
            if result.adjacency_matrix [a] [i]:
                flow_in += result.capacities [a] [i]

        flow_out: int = 0
        for a in range(0, result.N):
            if result.adjacency_matrix [i] [a]:
                flow_out += result.capacities [i] [a]

        if flow_in != flow_out:
            errors.append(f"Node {i} has unequal flow in/out: in={flow_in} out={flow_out}")
            valid = False

    # 4. Total flow out from source is total flow in at drain
    if result.compute_flow_value(source) != -result.compute_flow_value(drain):
        errors.append(f"Total flow from source to drain is not equal: source={result.compute_flow_value(source)} drain={-result.compute_flow_value(drain)}")
        valid = False

    return valid, errors

# Pretty-prints a maxflow computation result to stdout, alongside explainations.
# Paramters:
# - node_to_idx_map: map that maps node names to the corresponding indices in the DinicMaxFlow instance
# - result: the max-flow result, after run() was called
def print_maxflow_result(node_to_idx_map: map[str, int], result: DinicMaxFlow):
    idx_to_node_map = {value: key for key, value in node_to_idx_map.items()}

    saturated_cut: list[tuple[int, int]] = result.find_saturated_cut()

    print()
    print("#### Throughput Analysis Results ####")

    print()
    print("~~~ Saturated Cut ~~~")
    print("Explaination: the following edges are part of the saturated cut, i.e. the bottleneck-line through")
    print("the graph. To resolve this bottleneck, the link speed of these edges must be increased, or additional")
    print("paths need to be established. Increasing these edges alone does not guaranteee a throughput increase.")
    print()
    for src, dst in saturated_cut:
        src_node = idx_to_node_map[src]
        dst_node = idx_to_node_map[dst]
        print(f"  {node_name_to_edge_name [f"{src_node},{dst_node}"].name}: {idx_to_node_map [src]} -> {idx_to_node_map [dst]}: {format_speed(result.capacities [src] [dst])}/{format_speed(result.upper_bounds[src] [dst])}")

    print()
    print("~~~ Additional limiting Edges ~~~")
    print("Explaination: additionally to the saturated cut, the following edges were also fully utilized. When")
    print("increasing the capacity of the links part of the saturated cut, these links will likely form a new")
    print("bottleneck, and should also be considered.")
    print()
    for node in range(0, result.N):
        for child in result.adjacency_list [node]:
            if (node, child) not in saturated_cut:
                if result.capacities [node] [child] == result.upper_bounds [node] [child]:
                    src_node = idx_to_node_map[node]
                    dst_node = idx_to_node_map[child]
                    print(f"  {node_name_to_edge_name [f"{src_node},{dst_node}"].name}: {idx_to_node_map [node]} -> {idx_to_node_map [child]}: {format_speed(result.capacities[node][child])}/{format_speed(result.upper_bounds[node][child])}")

    print()
    print("~~~ Aggregate Capacity ~~~")
    print("Explaination: the total theoretical capacity from source to destination nodes. This does not include")
    print("protocol overhead or other losses.")
    print()
    total_capacity = result.saturated_cut_capacity(saturated_cut)
    print(f"  Theoretical Throughput: {format_speed(total_capacity)}")

# Prints a list of strings containing error messages to stdout. If the output mode
# is json, the errors are wrapped in a json object before printing. Otherwise, they
# are printed as plain text.
def emit_errors(error_strs: list[str]):
    global args_output
    if args_output == "json":
        print(json.dumps({"errors": error_strs}))
    else:
        logger = logging.getLogger(__name__)
        for error in error_strs:
            logger.error(error)

# Emits a single error message, see also emit_errors().
def emit_error(error_str: str):
    emit_errors([error_str])

# Formats the results of a max-flow computation into a dictionary for json serialization. See the README for
# the output format.
# Parameters:
# - subgraph_nodes: list of nodes included in the subgraph. The ordering should correspond to the ordering of the node_to_idx_map
def format_maxflow_result_to_dict(subgraph_nodes: list[Node], subgraph_edges: list[Edge], node_to_idx_map: map[str, int], source_nodes: list[Node], sink_nodes: list[Node], result: DinicMaxFlow):
    idx_to_node_map = {value: key for key, value in node_to_idx_map.items()}
    
    # Saturated cut = bottleneck through the entire graph. Its capacity is the maximum
    # possible flow from source -> sink
    saturated_cut: list[tuple[int, int]] = result.find_saturated_cut()
    total_capacity = result.saturated_cut_capacity(saturated_cut)
    
    output: dict = {}

    output["aggregate"] = total_capacity
    
    # List of edges that are part of the saturated cut
    saturated_cut_str: list = []
    for src, dst in saturated_cut:
        src_node = idx_to_node_map [src]
        dst_node = idx_to_node_map [dst]

        edge = node_name_to_edge_name [f"{src_node},{dst_node}"]
        if edge is None:
            logger.warn(f"Attempted non-existent edge from {src_node} to {dst_node}")
            continue

        saturated_cut_str.append(edge.name)
    output["saturated_cut"] = saturated_cut_str

    # Edges not in saturated cut that are also at their limit, which are likely to
    # limit the max flow after the saturated cut bottleneck has been resolved
    limiting_edges_str: list = []
    for node in range(0, result.N):
        for child in result.adjacency_list [node]:
            if (node, child) not in saturated_cut:
                if result.capacities [node] [child] == result.upper_bounds [node] [child]:
                    src_node = idx_to_node_map [node]
                    dst_node = idx_to_node_map [child]
                    
                    edge = node_name_to_edge_name [f"{src_node},{dst_node}"]
                    if edge is None:
                        logger.warn(f"Attempted non-existent edge from {src_node} to {dst_node}")
                        continue

                    limiting_edges_str.append(edge.name)
    output["limiting_edges"] = limiting_edges_str

    # Computed Subgraph
    subgraph_dict = {}

    # Filter out the super_source and super_sink nodes here, since they are max-flow artifacts
    # and are not part of the original graph
    node_list = [str(x) for x in subgraph_nodes]
    if "super_source" in node_list:
        node_list.remove("super_source")
    if "super_sink" in node_list:
        node_list.remove("super_sink")    
    subgraph_dict["nodes"] = node_list
    
    subgraph_dict["source_nodes"] = [str(x) for x in source_nodes]
    subgraph_dict["sink_nodes"] = [str(x) for x in sink_nodes]
    
    # List of edges of subgraph alongside max-flow values. Format:
    # { src: <name>, dst: <name>, upper_bound: <value or "inf">, capacity: <value> }
    edges_list = []
    for edge in subgraph_edges:
        # Skip edges involving super-source/sink, for same reasons as above
        if edge.src.name == "super_source" or edge.dst.name == "super_sink":
            continue
        
        src_idx = node_to_idx_map[edge.src.name]
        dst_idx = node_to_idx_map[edge.dst.name]

        upper_bound = str(result.upper_bounds [src_idx] [dst_idx])

        edges_list.append({
            "src": edge.src.name,
            "dst": edge.dst.name,
            "upper_bound": "inf" if upper_bound == "Infinity" else upper_bound,
            "capacity": result.capacities [src_idx] [dst_idx]
        })
    subgraph_dict["edges"] = edges_list
    output["subgraph"] = subgraph_dict

    return output    

def run_search(graph: NetworkGraph, source_node, sink_node, sink_labels, reject_labels) -> tuple[list[Node], list[Edge]]:
    logger = logging.getLogger(__name__)
    
    # Reject labels are as given, accept labels are the node id of the super sink
    mark_accepts_and_rejects(graph, { "id": [SymbolicOperand(P.singleton(str_const_to_int(sink_node.name)), "code")] }, reject_labels)

    # Perform one search here. Because we already introduced the super source/sink nodes,
    # we can start the search from the super-source node to the super sink. While one call,
    # this effectively bundles N searches, where N is the number of source nodes.
    # Returns list[tuple[SymbolicState, list[edge]]]
    paths, num_steps = search_bfs(graph, source_node, SymbolicState(state=None), True)

    return paths

# Construct a subgraph based on the source and sink nodes identified by the labels.
# Returns two lists; subgraph_nodes and subgraph_edges, containing the union of all
# paths between all sources and sinks.
def build_subgraph(paths, source_node) -> tuple[list[Node], list[Edge]]:
    logger = logging.getLogger(__name__)
    
    subgraph_nodes: list[Node] = []
    subgraph_edges: list[Edge] = []
    subgraph_nodes.append(source_node)    
    
    # Construct the subgraph by adding all nodes and edges
    # of the paths to the node and edge lists without duplicates. 
    # Each individual path produces a valid subgraph, the union 
    # of them is a valid subgraph as well.
    for resulting_state, path in paths:
        nodes = [source_node]
        for edge in path:
            nodes.append(edge.dst)
        if len(set(nodes)) < len(nodes):
            logger.warning(f"Path {str(path)} visits nodes multiple times. This can falsify Max-Flow analysis results, leading to an over-estimation of the throughput!")
            
        for edge in path:
            if edge not in subgraph_edges:
                subgraph_edges.append(edge)
            if edge.dst not in subgraph_nodes:
                subgraph_nodes.append(edge.dst)

    logger.debug(f"Found total of {len(paths)} paths between sources and sinks")
    logger.debug(f"Resulting Subgraph has {len(subgraph_nodes)} nodes and {len(subgraph_edges)} edges")

    return subgraph_nodes, subgraph_edges

def main():
    global args_output

    parser = argparse.ArgumentParser()
    parser.add_argument("--src", type=str, default="", help="source node labels")
    parser.add_argument("--dst", type=str, default="", help="sink node labels")
    parser.add_argument("--reject", type=str, default="", help="reject labels to exclude nodes")
    parser.add_argument("--schema", required=True, metavar="FILE")
    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARN", "ERROR"])
    parser.add_argument("--output", "-o", choices=["text", "json"], default="text")

    args = parser.parse_args()

    args_output = args.output    

    # Configure Log-Level
    logging.basicConfig(level=getattr(logging, args.log_level))
    logger = logging.getLogger(__name__)
    
    # Load Schema from file
    schema: str = args.schema
    graph: NetworkGraph = load_from_file(schema)

    # Map node name pairs to edges
    for node in graph.edges:
        for edge in graph.edges [node]:
            node_name_to_edge_name [f"{node},{edge.dst.name}"] = edge

    # Parse source labels: labels that identify source nodes in the graph
    source_labels: dict[str, list[SymbolicOperand]] = {}
    if args.src != "":
        source_labels = parse_labels(args.src)

    # Parse sink labels: labels that identify sink nodes in the graph
    sink_labels: dict[str, list[SymbolicOperand]] = {}
    if args.dst != "":
        sink_labels = parse_labels(args.dst)

    # Parse reject labels: labels that identify nodes/edges to be rejected during search
    reject_labels: dict[str, list[SymbolicOperand]] = {}
    if args.reject != "":
        reject_labels = parse_labels(args.reject)

    # Extract matching source and sink nodes
    source_nodes: list[Node] = []
    sink_nodes: list[Node] = []
    for node_name in graph.nodes:
        node = graph.nodes[node_name]
        if is_node_accepted(node, source_labels):
            source_nodes.append(node)
        if is_node_accepted(node, sink_labels):
            sink_nodes.append(node)

    # Validate configuration
    if len(source_nodes) == 0:
        emit_error("Labels did not identify any source nodes!")
        exit(1)

    if len(sink_nodes) == 0:
        emit_error("Labels did not identify any sink nodes!")
        exit(1)

    if bool(set(source_nodes) & set(sink_nodes)):
        emit_error(f"Found nodes both in source and sink node set: {set(source_nodes) & set(sink_nodes)}")
        emit_error("Source and sink node sets must be disjunct! Exiting...")
        exit(1)

    # Introduce super-nodes below and use them as source/sink nodes. This makes it simpler
    # to get all paths from source -> sink. Also required for Max-Flow to have one source/sink
    source_node = source_nodes[0]
    sink_node = sink_nodes[0]

    # Introduce Super-Source Node if required
    if len(source_nodes) > 1:
        super_source = Node("super_source", { "id": [SymbolicOperand(P.singleton(str_const_to_int("super_source")), "code")], "speed": ["inf"] })
        graph.nodes["super_source"] = super_source
        graph.edges["super_source"] = []
        source_node = super_source

        for source in source_nodes:
            edge = Edge(f"super_source-to-{source.name}", super_source, source, None, None, None)
            graph.edges["super_source"].append(edge)

    # Introduce Super-Sink Node if required
    if len(sink_nodes) > 1:
        super_sink = Node("super_sink", { "id": [SymbolicOperand(P.singleton(str_const_to_int("super_sink")), "code")], "speed": ["inf"] })
        graph.nodes["super_sink"] = super_sink
        graph.edges["super_sink"] = []
        sink_node = super_sink

        for sink in sink_nodes:
            edge = Edge(f"{sink.name}-to-super_sink", sink, super_sink, None, None, None)
            graph.edges[sink.name].append(edge)

    paths = run_search(graph, source_node, sink_node, sink_labels, reject_labels)

    if len(paths) == 0:
        emit_error("No paths found!")
        exit(0)

    # Build the subgraph: search all paths from source -> sink, combine the resulting
    # paths into the subgraph.
    subgraph_nodes, subgraph_edges = build_subgraph(paths, source_node)

    # Map node names to index
    node_to_idx_map: map[str, int] = {}
    current_index: int = 0
    for node in subgraph_nodes:
        node_to_idx_map[node.name] = current_index
        current_index += 1

    num_nodes: int = len(subgraph_nodes)

    # Initialize MaxFlow algo data structures:
    # Adjacency Matrix: encodes if an edge is present from -> to a node
    # Adjacency List: contains for each node a list of outgoing edges
    # Upper Bounds: encodes the maximum flow values on edge from -> to node
    adjacency_matrix: list[list[bool]] = [[False] * num_nodes for _ in range(num_nodes)]
    adjacency_list: list[list[int]] = [[] * num_nodes for _ in range(num_nodes)]
    upper_bounds: list[list[float]] = [[float("inf")] * num_nodes for _ in range(num_nodes)]
    for edge in subgraph_edges:
        node_src: int = node_to_idx_map[edge.src.name]
        node_dst: int = node_to_idx_map[edge.dst.name]

        if adjacency_matrix [node_src] [node_dst]:
            logger.warn(f"Duplicate edge {edge.name} detected: {edge.src.name} -> {edge.dst.name}")

        adjacency_matrix [node_src] [node_dst] = True
        adjacency_list [node_src].append(node_dst)
        upper_bounds [node_src] [node_dst] = get_flow_capacity(edge)

    source_node_idx: int = node_to_idx_map[source_node.name]
    sink_node_idx: int = node_to_idx_map[sink_node.name]

    # Create the maxflow instance and run the computation
    dinic_max_flow: DinicMaxFlow = DinicMaxFlow(num_nodes, source_node_idx, sink_node_idx, upper_bounds, adjacency_matrix, adjacency_list)
    dinic_max_flow.run()

    # Validate the flow before emitting a result
    valid, errors = verify_maxflow_result(dinic_max_flow)
    if not valid:
        errors.append(f"Flow is not valid!")
        emit_errors(errors)
        exit(1)

    # Emit results based on configured output format
    if args.output == "text":
        print_maxflow_result(node_to_idx_map, dinic_max_flow)
    else:
        output_dict = format_maxflow_result_to_dict(subgraph_nodes, subgraph_edges, node_to_idx_map, source_nodes, sink_nodes, dinic_max_flow)
        print(json.dumps(output_dict, indent=2))

if __name__ == "__main__":
    main()