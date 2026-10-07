# symbolic-network-traversal-engine

This repository contains the source files for our stateful symbolic search for network verification and analysis for our demo paper: _"Demo: A Symbolic Execution Framework for Network Analysis and Verification"_.

This repository includes:

- a CLI for the search engine itself: [search.py](./search.py)
- a CLI for the throughput analysis demo: [throughput.py](./throughput.py)
- a graph model [syntax guide](#graph-model-files)
- a few [example graph models](schemas/README.md) and queries

## Usage

**Prerequisites**

Python version `>=3.14` is required. You can either use [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Or [pip](https://pypi.org/project/pip/):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### CLI Usage

Use `python3 search.py --help` to get a CLI reference.

To perform a simple search, run for example:

```bash
python3 search.py nginx-svc --schema schemas/mlag.jsonc --accept id:redis-svc
```

## Graph Model Files

### Model File Syntax

Graph model files are JSON files or JSONC files (JSON with comments) that store nodes and edges that make up a graph. They also embed string-based metadata as labels and behavior semantics as constraints on edges. This section will given an overview of the syntax to define custom graph models.

#### Symbolic Operands

Symbolic operands are sets that define value ranges. They can be a continous interval, a union of intervals or a complement. Internally, all value types such as IP addresses and subnet, String constants etc. are mapped to plain numeric values.

Symbolic Operands are defined over the following formal grammar:

```
expr     := <expr>|<expr>      : set union
         := !<expr>            : set complement
         := <atomic>           : atomic symbol

atomic   := [operator]<symbol>
         := [range]

range    := <symbol>-<symbol>  : range from a to b
         := <IP CIDR Range>    : IP CIDR range xx.xx.xx.xx/yy

operator := ">"                : greater than
         := ">="               : greater or equal
         := "<"                : less than
         := "<="               : less or equal

symbol   := <string>           : atomic string value
         := <integer>          : atomic integer value
         := <MAC address>      : MAC address value xx:xx:xx:xx:xx:xx
         := <IP address>       : IP address value xx.xx.xx.xx
```

**Symbols**:

- `<String const>`: a string constant, which is internally mapped to an integer
- `<number>`: a plain number, e.g. `42`
- `<MAC address>`: a single EUI48 MAC address, e.g. `CC:AA:FF:FF:EE:EE`
- `<IP address>`: a single IPv4 or IPv6 address, e.g. `192.168.0.10`

**Operators**:

Operators can be used to define ranges:

- `>=42`: all integer values greater or equal to `42`: [42, 43, ..., +inf]
- `>42`: all integer values greater than `42`: [43, 44, ..., +inf]

**Ranges**:

Ranges can be specified either manually or by using type-specific ranges such as CIDR notation. 

To manually define a range the format `<smaller value>-<larger value>` is used:

- `10-42`
- `192.168.0.10-192.168.0.100`
- `AA:AA:AA:AA:AA:AA-BB:BB:BB:BB:BB:BB`

Please note that ranges are not supported for string values.

IP address ranges can be defined by using CIDR notation:

- `192.168.0.0/24`

**Unions**

Ranges and single values can be combined with the union operator `|`:

- `10|20|30` -> [10, 20, 30]
- `192.168.0.10|192.168.0.100-192.168.0.200` -> [192.168.0.10, 192.168.0.100, 192.168.0.101, ..., 192.168.0.200]

**Complements**

The complement of an operand can be created using the `!` operator:

- `42`: all values excluding this value
- `!192.168.0.0/24`: all IP addresses except this subnet
- `!a|b`: all strings except `a` or `b`

Note that the complement applies to everything behind it: it is currently only possible to negate the entire expression, not parts of it.

#### Label Sets

Label sets are used to identify and group nodes and edges. They are defined with the following JSON syntax:

```json
"labels": {
	"<key>": "<value>"
}
```

Allowed values for the key-value pairs are symbolic operand symbols, i.e. string and integer constants, MAC addresses or IP addresses.

Multi-value labels are also possible, with comma-separated values: `<value>,<value>,...`.

#### Nodes

Nodes are defined with the following syntax:

```json
{
	"id": "<name>",
	"labels": "<label set>"
}
```

The ID of a node must be unique within a graph. The label set is given in the syntax as introduced above.

#### Edges

Edges are defined with the follwing syntax:

```json
{
	"id": "<name>",
	"src": "<id of source node>",
	"dst": "<id of destination node>",
	"labels": "<label set>",
	"match": {
		"<variable name>": "<symbolic operand>"
	},
	"actions": {
		"<variable name>": "<symbolic operand>"
	}
}
```

As for nodes, the IDs of edges must be unique within a graph. The source and destination nodes reference the ID of nodes in the graph. The label set is given in the syntax as introduced above.

Match guards define constraints for this specific edge: before traversing this edge, the current search state must match all constraints in the edge. This means that for all defined variable names, the intersection between the state variable value and the symbolic operand of the match guard must be not empty. The symbolic search state contains all variables as wildcards by default, unless otherwise specified.

If the state matches the guards, the state is narrowed to the guard, i.e., for all match guards, the state values are set to the intersection between the current value and symbolic operand value.

Afterwards, actions can overwrite individual state variables: the given state variable names are set to the specified symbolic operand values. 

#### Graph

The entire graph is defined with the following syntax:

```json
{
	"nodes": [
		// node definitions
	],
	"edges": [
		// edge definitions
	]
}
```

The node and edge syntax is as given above.

### When to use Actions

Actions are destructive, whereas match guards are not: a match guard can only narrow the existing state. Actions are useful to expand or shift the search state, for example during NAT, where the source IP address may shift from an internal subnet to an external WAN IP address.

Because they are destructive and can expand the search space, actions can potentially cause a drastic increase in search runtime. While the model itself is static and finite, and thus bounded, actions can exponentially multiply the possible search paths and thus required search steps, leading to a state explosion. It is thus best to use them with care and rarely, and if the model semantics do require them.

For normal assignment purposes where the value domain is either not set or a superset of the new value, e.g. a single IP address within a currently set IP subnet, use normal match guards.

### How to label Node and Edges

Labels serve two purposes:

- they can identify and group nodes and edges
- they embed metadata for specialized analysis tools, such as the throughput analysis

To group nodes and edges, labels should be ideally chosen such that groups of intereset can be easily addresses. For example, a `role` label could be chosen to address all devices with a specific role such as `client` or `server`. 

Labels can also encode network-specific information such as a hosts IP address or MAC address. Metadata such as a devices manufacturer, operating system name and version, or link-speeds on edges can be encoded as well.

Ideally, for all queries that need to identify a set of nodes, a label set can be formulated that selects this specific set of nodes / edges. For more information, see the accept/reject labels in the CLI reference.

**Please note**: if not set manually, the parser of the search engine creates a label `id` for both edges and nodes, which contain their name from the graph model. This can be used to manually target nodes, rather than using label selection.

## Throughput Analysis

The [throughput analysis](./throughput.py) tool can be used to compute the aggregate throughput between two groups of nodes, sources and sinks. The groups are determined through label matching.

Use `python3 throughput.py --help` to print a CLI reference.

The throughput analysis sets the link speed of edges based on a `speed` label, with values in the format `<number>[K, M, G, T]`, for example `2.5G` or `100M`. Edges that do not carry the label have unlimited capacity.

## License

This code in this repository is licensed under the [MIT license](./LICENSE).

## Acknowledging this work

If you use the code contained in this repository in a publication, please use the following citation:

```BibTeX
@inproceedings{franz2026,
    title        = {Demo: A Symbolic Execution Framework for Network Analysis and Verification},
    author       = {Franz, Philip Jonas and Altenhofen, Konrad and Schoenen, Jonas and Abboud, Osama and Meuser, Tobias and Scheuermann, Björn},
    booktitle    = {2026 IEEE 51st Conference on Local Computer Networks (LCN)},
    year         = 2026,
    organization = {IEEE}
}
