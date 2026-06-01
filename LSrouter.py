####################################################
# LSrouter.py
####################################################

from router import Router
from packet import Packet

import json
import heapq


class LSrouter(Router):

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)

        self.heartbeat_time = heartbeat_time
        self.last_time = 0

        # port -> (neighbor, cost)
        self.neighbors = {}

        # LS database
        # router -> {neighbor: cost}
        self.lsdb = {self.addr: {}}

        # latest sequence number seen
        self.seq_nums = {self.addr: 0}

        self.my_seq = 0

        # destination -> output port
        self.forwarding_table = {}

    #################################################
    # Helpers
    #################################################

    def create_lsp(self):
        return {
            "router": self.addr,
            "seq": self.my_seq,
            "links": self.lsdb[self.addr]
        }

    def flood_lsp(self, except_port=None, content=None):

        if content is None:
            content = json.dumps(self.create_lsp())

        pkt = Packet(
            Packet.ROUTING,
            self.addr,
            self.addr,
            content
        )

        for port in self.neighbors:
            if port != except_port:
                self.send(port, pkt)

    def recompute_routes(self):

        graph = {}

        #
        # Build graph from LSDB
        #
        for node, links in self.lsdb.items():

            graph.setdefault(node, {})

            for nbr, cost in links.items():

                graph.setdefault(nbr, {})

                graph[node][nbr] = cost
                graph[nbr][node] = cost

        #
        # Dijkstra
        #
        dist = {self.addr: 0}
        prev = {}

        pq = [(0, self.addr)]

        while pq:

            cost, node = heapq.heappop(pq)

            if cost > dist[node]:
                continue

            for nbr, edge_cost in graph.get(node, {}).items():

                new_cost = cost + edge_cost

                if nbr not in dist or new_cost < dist[nbr]:

                    dist[nbr] = new_cost
                    prev[nbr] = node

                    heapq.heappush(
                        pq,
                        (new_cost, nbr)
                    )

        #
        # Build forwarding table
        #
        self.forwarding_table = {}

        for dst in dist:

            if dst == self.addr:
                continue

            hop = dst

            while hop in prev and prev[hop] != self.addr:
                hop = prev[hop]

            if hop == dst and hop not in prev:
                continue

            for port, (nbr, _) in self.neighbors.items():

                if nbr == hop:
                    self.forwarding_table[dst] = port
                    break

    #################################################
    # Router API
    #################################################

    def handle_packet(self, port, packet):

        #
        # Data packet
        #
        if packet.is_traceroute:

            if packet.dst_addr in self.forwarding_table:

                out_port = self.forwarding_table[
                    packet.dst_addr
                ]

                self.send(out_port, packet)

            return

        #
        # Routing packet
        #
        msg = json.loads(packet.content)

        router = msg["router"]
        seq = msg["seq"]
        links = msg["links"]

        old_seq = self.seq_nums.get(router, -1)

        #
        # Ignore old LSP
        #
        if seq <= old_seq:
            return

        self.seq_nums[router] = seq
        self.lsdb[router] = links

        self.recompute_routes()

        self.flood_lsp(except_port=port, content=packet.content)

    def handle_new_link(self, port, endpoint, cost):

        self.neighbors[port] = (
            endpoint,
            cost
        )

        self.lsdb[self.addr][endpoint] = cost

        self.my_seq += 1
        self.seq_nums[self.addr] = self.my_seq

        self.recompute_routes()

        self.flood_lsp()

    def handle_remove_link(self, port):

        if port not in self.neighbors:
            return

        endpoint, _ = self.neighbors[port]

        del self.neighbors[port]

        if endpoint in self.lsdb[self.addr]:
            del self.lsdb[self.addr][endpoint]

        self.my_seq += 1
        self.seq_nums[self.addr] = self.my_seq

        self.recompute_routes()

        self.flood_lsp()

    def handle_time(self, time_ms):

        if time_ms - self.last_time >= self.heartbeat_time:

            self.last_time = time_ms

            self.flood_lsp()

    def __repr__(self):

        return (
            f"Router={self.addr}\n"
            f"Neighbors={self.neighbors}\n"
            f"Forwarding={self.forwarding_table}\n"
            f"LSDB={self.lsdb}"
        )