from portion import Interval
from typing import Optional

from internal.state import SymbolicOperand

# Represents a single node in the graph. Contains a unique name, status flags, and labels.
# Nodes are constructed from a JSONC model file. See the individual members for more
# information.
class Node:

    # Name of the node, must be unique in the graph
    name: str

    # Pre-computed status flags: when the graph is loaded, the node labels are evaluated
    # against the passed accept/reject labels. The result is cached since these labels are
    # static.
    is_accepted: bool
    is_rejected: bool

    # Labels of the edge. Each label key can have multiple label values
    labels: dict[str, list[SymbolicOperand]]

    def __init__(self, name: str, labels: Optional[dict[SymbolicOperand]]):
        self.name = name

        self.labels = {}
        if labels is not None:
            self.labels = labels

        self.is_accepted = False
        self.is_rejected = False

    # Function override for converting this object to a string for printing
    def __repr__(self) -> str:
        return self.name

    # Function override for comparing this object to another one. Returns true
    # iff the other object is also a Node and has the exact same name.
    def __eq__(self, other) -> bool:
        if not isinstance(other, Node):
            return NotImplemented
        return self.name == other.name

    # Function override to hash this object. Node objects are hashed by hashing
    # their name string.
    def __hash__(self) -> int:
        return hash(self.name)

    # Nodes should be a singleton, and copies should not be made. For actual copies,
    # use deepcopy.
    def __copy__(self):
        return self


# Represents a single edge in the graph. Contains a unique name, status flags, and labels.
# Additionally references Node objects for the edge source and destination. Also includes
# optional match guard and actions.
# Edges are constructed from a JSONC model file. See the individual members for more
# information.
class Edge:

    # Name/identifier of this edge. Must be unique within the graph.
    name: str

    # Labels of the edge. Each label key can have multiple label values
    labels: dict[str, list[SymbolicOperand]]

    # Reference to the node from where this edge starts from.
    src: Node

    # Reference to the node to which this edge leads to.
    dst: Node

    # Pre-computed status flag: when the graph is loaded, the edge labels are evaluated
    # against the passed reject labels. The result is cached since these labels are
    # static.
    is_rejected: bool

    # Optional match guard of the edge, dictionary maps state variable names
    # to intervals to narrow the state with. The key represents the name of
    # a state variable, the interval the allowed values for the match guard.
    match_guard: dict[str, Interval]

    # Stores unparsed match guards to emit later during printing
    match_guard_str: dict[str, str]

    # Optional actions of the edge, dictionary maps state variable names
    # to intervals to overwrite the state with. The key represents the name
    # of the state variable, the Interval the replacement value.
    actions: dict[str, Interval]

    # Stores unparsed actions to emit later during printing
    actions_str: dict[str, str]

    # Initializes a new Edge instance. Requires a unique name, source and destination node, optional match guard, optional actions and optional labels.
    def __init__(self, name: str, src: Node, dst: Node, match_guard: Optional[dict[str, Interval]], actions: Optional[dict[str, Interval]], labels: Optional[dict[str, list[SymbolicOperand]]]):
        self.name = name
        self.src = src
        self.dst = dst

        self.match_guard = {}
        if match_guard is not None:
            self.match_guard = match_guard
        
        self.actions = {}
        if actions is not None:
            self.actions = actions

        self.labels = {}
        if labels is not None:
            self.labels = labels

        self.is_rejected = False

    # Function override for converting this object to a string for printing
    def __repr__(self) -> str:
        return self.name

    # Function override for comparing this object to another one. Returns true
    # iff the other object is also an Edge and has the exact same name.
    def __eq__(self, other) -> bool:
        if not isinstance(other, Edge):
            return NotImplemented
        return self.name == other.name

    # Function override to hash this object. Edge objects are hashed by hashing
    # their name string.
    def __hash__(self) -> int:
        return hash(self.name)

    # Edges should be a singleton, and copies should not be made. For actual copies,
    # use deepcopy.
    def __copy__(self):
        return self


# Contains all information that can be loaded from a single model file; including all
# nodes and edges.
class NetworkGraph:

    # Maps node names to the respective Node object instances.
    nodes: dict[str, Node]

    # Maps a Node name to all outgoing Edges, i.e. the name of the source node of these edges
    # is the used key. 
    edges: dict[str, list[Edge]]

    # Initializes a new graph instance, requires a map of nodes and edges.
    def __init__(self, nodes: dict[str, Node], edges: dict[str, list[Edge]]):
        self.nodes = nodes
        self.edges = edges