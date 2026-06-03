####################################################
# DVrouter.py
# Name:
# HUID:
#####################################################

import json
from router import Router
from packet import Packet

INFINITY = 16


class DVrouter(Router):
    """Distance vector routing protocol implementation."""

    def __init__(self, addr, heartbeat_time):
        Router.__init__(self, addr)
        self.heartbeat_time = heartbeat_time
        self.last_time = 0

        # port -> (neighbor_addr, cost)
        self.neighbors = {}

        # dst -> (cost, port)  — this router's distance vector
        self.dv = {addr: (0, None)}

        # neighbor_addr -> {dst: cost}  — received DVs from neighbors
        self.neighbor_dvs = {}

        # dst -> port  — forwarding table
        self.forwarding_table = {}


    def _recompute(self):
        """Recompute DV and forwarding table using Bellman-Ford. Return True if changed."""
        new_dv = {self.addr: (0, None)}

        for port, (nbr, link_cost) in self.neighbors.items():
            # Direct neighbor is always reachable at link_cost
            if link_cost < new_dv.get(nbr, (INFINITY, None))[0]:
                new_dv[nbr] = (link_cost, port)

            # Routes via this neighbor
            for dst, nbr_cost in self.neighbor_dvs.get(nbr, {}).items():
                total = link_cost + nbr_cost
                if total < new_dv.get(dst, (INFINITY, None))[0]:
                    new_dv[dst] = (total, port)

        changed = new_dv != self.dv
        self.dv = new_dv
        self.forwarding_table = {dst: port for dst, (cost, port) in new_dv.items()
                                 if port is not None and cost < INFINITY}
        return changed

    def _broadcast(self):
        """Send this router's DV to all neighbors (split horizon with poison reverse)."""
        for port, (nbr, _) in self.neighbors.items():
            # Build advertised vector with poison reverse
            adv = {}
            for dst, (cost, via_port) in self.dv.items():
                # Poison reverse: advertise INFINITY back on the port we learned it from
                adv[dst] = INFINITY if via_port == port else cost
            pkt = Packet(Packet.ROUTING, self.addr, nbr, json.dumps(adv))
            self.send(port, pkt)


    def handle_packet(self, port, packet):
        if packet.is_traceroute:
            out_port = self.forwarding_table.get(packet.dst_addr)
            if out_port is not None:
                self.send(out_port, packet)
        else:
            nbr = self.neighbors.get(port, (None,))[0]
            if nbr is None:
                return
            received = json.loads(packet.content)
            if self.neighbor_dvs.get(nbr) == received:
                return
            self.neighbor_dvs[nbr] = received
            if self._recompute():
                self._broadcast()

    def handle_new_link(self, port, endpoint, cost):
        self.neighbors[port] = (endpoint, cost)
        if endpoint not in self.neighbor_dvs:
            self.neighbor_dvs[endpoint] = {}
        if self._recompute():
            pass  # broadcast below regardless
        self._broadcast()

    def handle_remove_link(self, port):
        nbr_info = self.neighbors.pop(port, None)
        if nbr_info:
            nbr = nbr_info[0]
            self.neighbor_dvs.pop(nbr, None)
        self._recompute()
        self._broadcast()

    def handle_time(self, time_ms):
        if time_ms - self.last_time >= self.heartbeat_time:
            self.last_time = time_ms
            self._broadcast()

    def __repr__(self):
        lines = [f"DVrouter(addr={self.addr})"]
        for dst, (cost, port) in sorted(self.dv.items()):
            lines.append(f"  {dst}: cost={cost}, port={port}")
        return "\n".join(lines)
