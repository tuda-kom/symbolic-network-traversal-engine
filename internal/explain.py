from internal.graph import Edge
from internal.state import SymbolicState

# Formats a label string into a pretty-print format. Sample input:
#
# {'LAYER': '7', 'DEVICE': 'vm-1-pve-1', 'role': 'service'}
#
# is transformed to:
#
# LAYER=7 DEVICE=vm-1-pve-1 role=service
#
def format_edge_labels(label_str: str) -> str:
    return label_str.replace('\'', '').replace(',', '').replace(': ', '=') [1:-1]

# Formats a state string into a pretty-print format. Sample input:
#
# {l4_src_port: 6379, l3_src_ip: 10.1.2.10}
#
# is transformed to:
#
# l4_src_port=6379, l3_src_ip=10.1.2.10
#
def format_state_string(label_str: str) -> str:
    return label_str.replace('\'', '').replace(': ', '=') [1:-1]

# Explains a single path of the result set of the search algorithm. The function re-traces
# each search step for this path to reconstruct the state changes within the search path.
# 
# Parameters:
# - path_idx: the number of this path in the resulting path list of the search
# - initial_state: the initial symbolic state that was passed via the CLI. If no state was passed, this is a wildcard
# - path: the actual path. Contains the final symbolic state, and a list of edges that were taken. The node list can be obtained with edge.src and edge.dst
#
def explain_path(path_idx: int, initial_state: SymbolicState, path: tuple[SymbolicState, list[Edge]]):
    final_state, edges = path
    start_node = edges[0].src

    print("==============================================================")
    print(f"  Explaining Path {path_idx}, length: {len(edges) + 1} hops")
    print("==============================================================")
    
    hop: int = 0
    current_state = initial_state

    for edge in edges:
        if hop == 0:
            print(f"  [ START ] {edge.src.name} [{format_edge_labels(str(edge.src.labels))}]")
        else:
            print(f"  [ {hop} ] {edge.src.name} [{format_edge_labels(str(edge.src.labels))}]")

        state_str = format_state_string(str(current_state))
        if state_str:
            print(f"    state: {format_state_string(str(current_state))}")
        edge_str = f"    edge {edge.name}"
        if edge.match_guard:
            edge_str += f" guard[{format_state_string(str(edge.match_guard))}]"
        if edge.actions:
            edge_str += f" actions[{format_state_string(str(edge.actions))}]"
        print(edge_str)

        # Apply edge to state
        new_state = current_state.copy()
        new_state.narrow_state(edge.match_guard)
        new_state.apply_actions(edge.actions)

        # Added state variables
        for var in new_state.state:
            if var not in current_state.state:
                print(f"    + {var} = {str(new_state.state [var])}")

        # Deleted state variables
        for var in current_state.state:
            if var not in new_state.state:
                print(f"    - {var} (was {str(current_state.state [var])})")

        # Modified state variables
        for var in new_state.state:
            if var in current_state.state:
                if str(new_state.state [var]) != str(current_state.state [var]):
                    print(f"    ~ {var}: {str(current_state.state [var])} -> {str(new_state.state [var])}")

        print()
        current_state = new_state
        hop += 1

    print(f"  [ {hop} ] {edges [-1].dst.name} [{format_edge_labels(str(edge.dst.labels))}]")
    print(f"    state: {format_state_string(str(current_state))}")

    print()
    print(f"-- Final State ----------------------------------------------")
    for key in current_state.state:
        print(f"  {key} = {current_state.state [key]}")