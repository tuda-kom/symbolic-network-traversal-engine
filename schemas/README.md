# Example Models

This directory contains a set of example graph models:

- [simple](./simple.jsonc): a simple model of multiple hosts connected to a router and switch
- [mlag](./mlag.jsonc): models a redundant MLAG-based network, with hypervisors and VMs connected to it, with services on the VMs
- [firewall](./firewall.jsonc): models a simplified iptables-based firewall, with a WAN, LAN and DMZ interfaces
- [access_net](./access_net.jsonc): models a PON system with multiple downstream subscribers, with clients and port-forwarded private appliances

## Example Queries

### Simple Model

- "How can host-a reach other hosts in the network?"

```bash
python3 search.py host-a --schema schemas/simple.jsonc --continue --prune
```

- "How can host-a reach host-b?"

```bash
python3 search.py host-a --accept id:host-b --schema schemas/simple.jsonc --continue --prune
```

- "How does this specific packet travel through the network?"

```bash
python3 search.py host-a --state sip:10.8.0.10 dip:10.4.0.60 --schema schemas/simple.jsonc --continue --prune
```

### MLAG Model

**Reachability**

- "How many paths exist from nginx to redis replicas?"

```bash
python3 search.py nginx --schema schemas/mlag.jsonc --accept app:redis
```

- "How many paths remain if one of the switches fails?"

```bash
python3 search.py nginx --schema schemas/mlag.jsonc --accept app:redis --reject id:core-1
```

**Throughput**

- "How much capacity is available between nginx and redis replicas?"

```bash
python3 throughput.py --src app:nginx --dst app:redis --schema schemas/mlag.jsonc
```

- "How much capacity remains if a switch fails?"

```bash
python3 throughput.py --src app:nginx --dst app:redis --schema schemas/mlag.jsonc --reject id:core-1
```

### Firewall Model

**Reachability**

- "Which accepting paths exist in the firewall?"

```bash
python3 search.py pkt-in --schema schemas/firewall.jsonc --accept id:accept
```

- "Is it possible to reach the internal network from the DMZ?"

```bash
python3 search.py int-dmz --state l3_dst_ip:10.4.0.0/16 --schema schemas/firewall.jsonc --accept id:accept
```

- "Which new connections are accepted by the firewall from the WAN?"

```bash
python3 search.py int-wan --state ctstate:new --schema schemas/firewall.jsonc --accept id:accept
```

### Access Net Modell

**Reachability**

- "Which servers can client-5 reach?"

```bash
python3 search.py client-5 --schema schemas/access_net.jsonc --accept role:server
```

- "Which devices in internal networks can be reached from the internet?"

```bash
python3 search.py bng-1 --schema schemas/access_net.jsonc --accept l3_ip:192.168.178.0/24 --continue --prune
```

**Throughput**

- "How much throughput between clients and NAS-1 is possible?"

```bash
python3 throughput.py --src role:client --dst id:nas-1 --schema schemas/access_net.jsonc
```