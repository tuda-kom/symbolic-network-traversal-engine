import logging

# Implements Dinic's MaxFlow algorithm, alongside helper functions.
class DinicMaxFlow:

    # Number of nodes in graph
    N: int

    # Index of source and drain nodes
    source: int
    drain: int

    # Maximum flow value on edge from -> to.
    # Access elements with: upper_bounds [from] [to]
    upper_bounds: list[list[int]]

    # Current flow value on edge from -> to.
    # Access elements with: capacities [from] [to]
    capacities: list[list[int]]

    # Adjacency-List of the graph from -> to.
    # Access elements with: adjacency_list [from] [to]
    adjacency_matrix: list[list[bool]]

    # Adjacency-List of the graph from -> to.
    # Access elements with: adjacency_list [from] [to]
    adjacency_list: list[list[bool]]

    def __init__(self, N: int, source: int, drain: int, upper_bounds: list[list[int]], adjacency_matrix: list[list[bool]], adjacency_list: list[list[int]]):
        self.N = N

        self.source = source
        self.drain = drain

        # Capacity matrix initialized with all zero values
        self.capacities = [[0] * self.N for _ in range(self.N)]
        self.upper_bounds = upper_bounds
        self.adjacency_matrix = adjacency_matrix
        self.adjacency_list = adjacency_list

    # Runs Dinics algorithm on this instance. The algorithm iterates as long as the drain
    # can be reached while computing the level mapping. If it can be reached, more flow
    # can be sent from the source. Once this is not the case anymore, the maximum flow
    # has been reached.
    def run(self):
        logger = logging.getLogger(__name__)

        iterations: int = 0

        while True: # O(V*K)
            level_mapping, reached = self.compute_level_mapping() # O(V+A)

            if not reached[self.drain]: # O(1)
                # Drain was not reached, no increasing path is available
                break

            # Increasing paths exist, send more flow
            found_paths: bool = self.compute_blocking_flow(level_mapping) # O(K)
            if not found_paths:
                break

            iterations += 1

        logger.debug(f"Finished after {iterations} iterations.")

    # Computes a level mapping. Starting from the source with level 0,
    # the level mapping measures the distance in hops of a node from
    # the source, such that the hops all have a postitive, non-zero remaining
    # residual capacity. Returns the level mapping and a list of visited
    # nodes as a list of bools.
    def compute_level_mapping(self) -> tuple[list[int], list[bool]]: # O(V+A)
        visited: list[bool] = [False] * self.N # O(V)
        worklist: list[int] = [self.source] # O(1)

        visited [self.source] = True

        level_mapping: list[int] = [0] * self.N # O(V)

        while worklist: # O(A), since only each arc gets processed just once
            visit = worklist.pop(0)
            for child in self.adjacency_list[visit]: # O(A)
                if not visited[child] and self.residual_capacity(visit, child) > 0: # O(1)
                    visited [child] = True
                    worklist.append(child)

                    # Level mapping is mapping of parent + 1
                    level_mapping [child] = level_mapping [visit] + 1

        return level_mapping, visited


    # Computes the remaining capacity between U and V. This also includes
    # capacity on a reverse arc.
    def residual_capacity(self, u: int, v: int) -> int: # O(1)
        return (self.upper_bounds[u] [v] - self.capacities[u] [v]) + self.capacities[v] [u]

    # Computes a blocking flow given a level mapping. A blocking flow is defined
    # as a flow from source to drain such that with the current level mapping, no
    # more flow can be sent. To do this, paths are searched using BFS from source
    # to drain, such that only arcs V -> W are taken where level(V)+1 = level(W), and
    # residual capacity remains. Once the drain is reached, the path is constructed 
    # and flow is increased along the path. Once no path can be found, a blocking
    # flow is reached.
    def compute_blocking_flow(self, level_mapping) -> bool:
        path_map: list[int] = [-1] * self.N
        paths_found = 0

        worklist: list[int] = [self.source]

        while worklist:
            current_node = worklist.pop()

            if current_node == self.drain: # O(V)
                # Drain was reached. This means we have a path from the source to the
                # sink, and now have to manage the increase along the found path. We
                # start by collecting the path into a list: 
                path: list[int] = []
                v: int = current_node
                while v != -1: # O(V)
                    path.insert(0, v)
                    v = path_map [v]

                # Now we can compute the increase along this path:
                increase: int = self.compute_increase_along_path(path) # O(V)

                # With the increase, we now have to adjust the residual graph to ensure
                # subsequent searches along arcs of this path already know that some of
                # the capacity is used by this path:
                for i in range(0, len(path) - 1): # O(V)
                    self.augment_residual_edge(path[i], path[i + 1], increase)

                paths_found += 1

            else:
                for node in self.adjacency_list[current_node]: # O(A)
                    # Only take arc if node a strictly higher level than the current node and has remaining capacity
                    if self.residual_capacity(current_node, node) > 0 and level_mapping [node] == level_mapping[current_node] + 1: # O(1)
                        worklist.append(node)
                        path_map [node] = current_node

        return paths_found > 0

    # Given a path, this function computes the maximum possible increase along this path.
    # The increase on a single edge is defined as the remaining residual capacity.
    def compute_increase_along_path(self, path: list[int]) -> int:
        increase: int = float("inf")

        for i in range(0, len(path) - 1):
            node_from: int = path [i]
            node_to: int = path [i + 1]

            increase = min(increase, self.residual_capacity(node_from, node_to))

        return increase

    # Given an arc by a source and destination node, and an increase value, this
    # function applies the given increase to the arc. Depending on the direction
    # of the arc, flow is added
    def augment_residual_edge(self, src: int, dst: int, increase: int):
        # Case A: the arc we want to push flow is a forwards arc
        if self.adjacency_matrix [src] [dst]: # O(1)
            # Determine how much remaining capacity is on the arc src -> dst
            remaining_capacity: int = self.upper_bounds [src] [dst] - self.capacities [src] [dst]
            remainder: int = remaining_capacity - increase

            # Push the remaining capacity from src -> dst
            self.capacities [src] [dst] += min(increase, remaining_capacity)

            if remainder < 0: # O(1)
                # If the remaining capacity from src -> dst was not enough to push everything,
                # we must get rid of the remaining flow by cancelling flow in the other
                # direction. Note: the value of remainder is negative, hence the +=!
                self.capacities [dst] [src] += remainder

        # Case B: the arc is a reverse arc, and no forwards arc exist
        else:
            # In this case, all of the remaining flow must be pushed over the
            # reverse arc in the reverse direction, hence we subtract the remaining
            # flow from the capacity of the reverse arc.
            self.capacities [dst] [src] -= increase

    # Finds all reachable nodes from the source node. A node is reachable if
    # a path exists from the source to the node such that all arcs on the path
    # have a positive, non-zero remaining residual capacity. The path can include
    # both forwards and backward arcs.
    def find_reachable_nodes(self):
        reachable_nodes: list[bool] = [False] * self.N

        worklist: list[int] = [self.source]
        reachable_nodes[self.source] = True

        while worklist:
            node: int = worklist.pop(0)
            for idx in range(0, self.N):
                # Forwards arc
                if self.adjacency_matrix [node] [idx]:
                    if not reachable_nodes [idx] and self.residual_capacity(node, idx) > 0:
                        reachable_nodes [idx] = True
                        worklist.append(idx)

                # Reverse arc
                if self.adjacency_matrix [idx] [node]:
                    if not reachable_nodes [idx] and self.residual_capacity(idx, node) > 0:
                        reachable_nodes [idx] = True
                        worklist.append(idx)
        
        return reachable_nodes

    # Computes the saturated cuts after the run() function has terminated. The saturated
    # cut is defined as the set of arcs V -> W such that V is reachable, and W is not.
    def find_saturated_cut(self):
        reachable_nodes: list[bool] = self.find_reachable_nodes()
        saturated_cut: list[tuple[int, int]] = []

        for node in range(0, self.N):
            if reachable_nodes [node]:
                for child in self.adjacency_list [node]:
                    if not reachable_nodes [child] and self.residual_capacity(node, child) == 0 and self.capacities [node] [child] > 0:
                        saturated_cut.append((node, child))

        return saturated_cut

    # Computes the capacity of the saturated cut, given as a list of arcs.
    # The capacity is defined of the sum of all upper bounds of the arcs of the cut.
    def saturated_cut_capacity(self, saturated_cut: list[tuple[int, int]]):
        cut_capacity: int = 0

        for src, dst in saturated_cut:
            cut_capacity += self.upper_bounds [src] [dst]

        return cut_capacity

    # Returns the maximum upper bound present in the maxflow instance that is not infinity
    def find_max_upper_bound(self):
        max_upper = 0
        
        for i in range(0, self.N):
            for a in range(0, self.N):
                if self.adjacency_matrix [i] [a] and self.upper_bounds [i] [a] < float("inf"):
                    max_upper = max(max_upper, self.upper_bounds [i] [a])

        return max_upper

    # Computes the flow for a given node. The flow value is defined as the sum of all
    # incoming flow, subtracted by the total sum of outgoing flow. For all nodes that
    # are not the source and drain, this value should be zero, as no flow can be lost.
    def compute_flow_value(self, node):
        flow_value: int = 0

        for i in range(0, self.N):
            if self.adjacency_matrix [i] [node]:
                flow_value += self.capacities [i] [node]

        for i in range(0, self.N):
            if self.adjacency_matrix [node] [i]:
                flow_value -= self.capacities [node] [i]

        return flow_value