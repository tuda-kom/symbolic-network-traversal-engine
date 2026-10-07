from internal.state import SymbolicState
from internal.graph import NetworkGraph, Node, Edge
from copy import deepcopy
import logging

logger = logging.getLogger(__name__)

# Performs the symbolic stateful search. Parameters:
# - graph: the network graph on which to perform the search
# - initial_node: node from which the search starts from
# - initial_state: state which the search with
# - continue_paths: if set to true, the search continues a path even if an accepted node was encountered
# - do_step: if true, the search is paused after each main-loop iteration, useful for debugging
#
def search_bfs(graph: NetworkGraph, initial_node: Node, initial_state: SymbolicState, continue_paths: bool, do_step: bool = False):
    state_hashes: dict[int, SymbolicState] = {}
    state_hashes [hash(initial_state)] = deepcopy(initial_state)

    working_queue: list = [(initial_node, initial_state, [], {initial_node.name: [hash(initial_state)]})]

    # Result set that collects paths
    result_paths: list[tuple[SymbolicState, list[Edge]]] = []
    num_steps: int = 0

    if do_step:
        logger.info("Single-Stepping active, press [Enter] to single-step forward.")

    while working_queue:
        if do_step:
            # Wait for [ENTER] press
            input()

        # Unpack current step from queue
        node: Node
        state: SymbolicState
        edges: list[Edge]
        visited: dict[str, list[int]]
        node, state, edges, visited = working_queue.pop(0)
        logger.debug("pop %-20s state=%s", node.name, state)

        num_steps += 1
        logger.debug(f"Steps: {num_steps}, backlog: {len(working_queue)}")

        # Check if current node was rejected
        if node.is_rejected:
            logger.debug(f"  Node {node.name} rejected")
            continue

        # Check if current node was accepted
        if node.is_accepted:
            result_paths.append((state.copy(), edges.copy()))
            logger.debug(f"  Node {node.name} accepted")
            if not continue_paths:
                logger.debug(f"   Continuing...")
                continue

        # Keep searching over outgoing edges
        outgoing_edges: list[Edge] = graph.edges[node.name]
        for edge in outgoing_edges:
            logger.debug(f"   Probing outgoing edge from {edge.src} to {edge.dst}")

            # Check if edge is rejected
            if edge.is_rejected:
                logger.debug(f"   Edge {edge.name} rejected")
                continue

            # Ensure current state matches the match guard
            if state.matches(edge.match_guard):
                logger.debug(f"   Edge {edge.name} matched guard {edge.match_guard}")
                
                # Apply matches and actions to state
                new_state = state.copy()
                new_state.narrow_state(edge.match_guard)
                new_state.apply_actions(edge.actions)

                # Check if new state is subsumed by previous states the target node was visited with
                previous_states: list[int] = visited.get(edge.dst.name, [])
                state_subsumed: bool = False
                for previous_state_hash in previous_states:
                    previous_state = state_hashes [previous_state_hash]
                    if previous_state.subsumes(new_state):
                        logger.debug(f"  State {new_state} subsumed by {previous_state}")
                        state_subsumed = True
                        break

                if state_subsumed:
                    continue

                # Add the new state to the visited set and add the step to the worklist
                new_visited: dict[str, list[int]] = deepcopy(visited)
                if edge.dst.name not in new_visited:
                    new_visited[edge.dst.name] = []

                state_hashes [hash(new_state)] = deepcopy(new_state)
                new_visited[edge.dst.name].append(hash(new_state))

                new_edges: list[Edge] = edges.copy()
                new_edges.append(edge)

                logger.debug(f"    -> Added to queue: {edge.dst.name}, {new_state}")
                working_queue.append((edge.dst, new_state, new_edges, new_visited))

    return (result_paths, num_steps)