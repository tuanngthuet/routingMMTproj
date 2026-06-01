####################################################
# LSrouter.py
# Name:
# HUID:
#####################################################

from router import Router
from packet import Packet

import json
import heapq


class LSrouter(Router):

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)

        self.heartbeat_time = heartbeat_time
        self.last_time = 0

        self.neighbors = {}

        self.lsdb = {}

        self.seq_nums = {}

        self.my_seq = 0

        self.forwarding_table = {}

        self.lsdb[self.addr] = {}

    def create_lsp(self):
        return {
            "router": self.addr,
            "seq": self.my_seq,
            "links": self.lsdb[self.addr]
        }

    def flood_lsp(self, except_port=None):

        packet = Packet(
            Packet.ROUTING,
            self.addr,
            self.addr,
            json.dumps(self.create_lsp())
        )

        for port in self.neighbors:
            if port != except_port:
                self.send(port, packet)

    def recompute_routes(self):

        graph = {}

        for node, nbrs in self.lsdb.items():

            graph.setdefault(node, {})

            for nbr, cost in nbrs.items():

                graph[node][nbr] = cost

                graph.setdefault(nbr, {})
                graph[nbr][node] = cost

        dist = {self.addr: 0}
        prev = {}

        pq = [(0, self.addr)]

        while pq:

            cur_cost, node = heapq.heappop(pq)

            if cur_cost > dist[node]:
                continue

            for nbr, edge_cost in graph.get(node, {}).items():

                new_cost = cur_cost + edge_cost

                if nbr not in dist or new_cost < dist[nbr]:

                    dist[nbr] = new_cost
                    prev[nbr] = node

                    heapq.heappush(
                        pq,
                        (new_cost, nbr)
                    )

        self.forwarding_table = {}

        for dst in dist:

            if dst == self.addr:
                continue

            cur = dst

            while cur in prev and prev[cur] != self.addr:
                cur = prev[cur]

            if cur in prev and prev[cur] == self.addr:

                for port, (nbr, _) in self.neighbors.items():

                    if nbr == cur:
                        self.forwarding_table[dst] = port
                        break

    def handle_packet(self, port, packet):

        if packet.is_traceroute:

            if packet.dst_addr in self.forwarding_table:

                out_port = self.forwarding_table[
                    packet.dst_addr
                ]

                self.send(out_port, packet)

            return

        msg = json.loads(packet.content)

        router = msg["router"]
        seq = msg["seq"]
        links = msg["links"]

        old_seq = self.seq_nums.get(router, -1)

        if seq < old_seq:
            return

        changed = (
            router not in self.lsdb
            or self.lsdb[router] != links
            or seq > old_seq
        )

        if not changed:
            return

        self.seq_nums[router] = seq
        self.lsdb[router] = links

        self.recompute_routes()

        self.flood_lsp(except_port=port)

    def handle_new_link(self, port, endpoint, cost):

        self.neighbors[port] = (endpoint, cost)

        self.lsdb[self.addr][endpoint] = cost

        self.my_seq += 1

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

        self.recompute_routes()

        self.flood_lsp()

    def handle_time(self, time_ms):

        if time_ms - self.last_time >= self.heartbeat_time:

            self.last_time = time_ms

            self.flood_lsp()

    def __repr__(self):

        return (
            f"LSrouter({self.addr})\n"
            f"Neighbors={self.neighbors}\n"
            f"Forwarding={self.forwarding_table}"
        )
