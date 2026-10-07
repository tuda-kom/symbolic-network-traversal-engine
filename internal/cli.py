import argparse
from internal.loader import load_from_file, parse_labels, mark_accepts_and_rejects, parse_labels, parse_initial_state
from internal.graph import NetworkGraph
from internal.search_bfs import search_bfs
from internal.state import SymbolicState, SymbolicOperand
from internal.explain import explain_path
import logging
import json
from internal.util import paths_to_dict, print_paths, prune_paths

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--schema", required=True, metavar="FILE")
    parser.add_argument("start", help="ID of start node for the search")
    
    # Optional Parameters
    parser.add_argument("--state", nargs="*", default=[], metavar="k:v", help="initial state for the search pass values in format <key>:<value> <key>:<value>. Use quotes for entire argument to prevent errors during argument parsing in some scenarios")
    parser.add_argument("--accept", nargs="*", default=[], metavar="k:v", help="key-value labels that identify target nodes in format <key>:<value> <key>:<value>. Use quotes for entire argument to prevent errors during argument parsing in some scenarios")
    parser.add_argument("--reject", nargs="*", default=[], metavar="k:v", help="reject labels that define which nodes and edges are rejected during the search in format <key>:<value> <key>:<value>. Use quotes for entire argument to prevent errors during argument parsing in some scenarios")
    parser.add_argument("--continue", dest="do_continue", action="store_true", help="set this flag to continue the search after the search encountered a node that is an accepted node")
    parser.add_argument("--step", dest="do_step", action="store_true", help="single-step the search. Useful in combination with debug logging to step through the search manually")
    parser.add_argument("--prune-paths", dest="prune_paths", action="store_true", help="prune the resulting path set. A path is pruned if it is a prefix of another path in the path set.")
    parser.add_argument("--explain", type=int, default=None, help="this option prints out all hops of a single path, including intermediate states and state transitions. Set this option with a number that is in the range [0, N-1], where N is the number of paths found by the current search query")
    
    parser.add_argument("--output", "-o", choices=["text", "json"], default="text", help="set the output format on stdout, text prints out a pretty-printed version, while json prints machine-readable data")

    parser.add_argument("--log-level", type=str, default="INFO", choices=["DEBUG", "INFO", "WARN", "ERROR"])
    
    args = parser.parse_args()

    # Configure log level
    logging.basicConfig(level=getattr(logging, args.log_level))
    logger = logging.getLogger(__name__)

    # Load schema
    schema: str = args.schema
    graph: NetworkGraph = load_from_file(schema)

    # Parse accept / reject label sets
    accept_labels: dict[str, list[SymbolicOperand]] = {}
    if args.accept:
        accept_labels = parse_labels(" ".join(args.accept))

    reject_labels: dict[str, list[SymbolicOperand]] = {}
    if args.reject:
        reject_labels = parse_labels(" ".join(args.reject))

    # Pre-compute accepted and rejected nodes/edges for faster lookups during search
    mark_accepts_and_rejects(graph, accept_labels, reject_labels)

    # Locate Start Node
    start_node: str = args.start
    if not start_node in graph.nodes:
        print(f"Error: start node {start_node} is not in graph!")
        exit(1)

    # Parse initial state variables if given
    initial_state_map: dict[str, SymbolicOperand] = None
    if args.state:
        initial_state_map = parse_initial_state(args.state)
        if initial_state_map is None:
            print(f"Error: failed to parse initial state: {args.state}")
            exit(1)
    initial_state: SymbolicState = SymbolicState(state=initial_state_map)

    # Run the actual search algorithm
    paths, num_steps = search_bfs(graph, graph.nodes[start_node], initial_state, args.do_continue, args.do_step)

    # Prune the path set if desired
    if args.prune_paths:
        paths = prune_paths(paths)

    # The CLI has two output three output modes: either a path is explained, or the paths are dumped as text or JSON.
    if args.explain is not None:
        # Explain path
        explain_index = args.explain
        if len(paths) < args.explain:
            logger.error(f"Cannot explain path {explain_index}, only {len(paths)} paths found.")
            exit(1)

        explain_path(explain_index, initial_state, paths[explain_index - 1])
        exit(0)
    else:
        if args.output == "text":
            # Dump paths as text to stdout
            print_paths(paths)
            print()
            print(f"{len(paths)} path(s) found. ({num_steps} steps)")
        else:
            # Dump paths as json to stdout
            output_dict = paths_to_dict(graph, graph.nodes[start_node], initial_state, paths)
            print(json.dumps(output_dict, indent=2))

if __name__ == "__main__":
    main()