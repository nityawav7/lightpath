"""Physical network model: ROADM nodes connected by DWDM fiber links.

Each fiber link carries a fixed grid of wavelength channels (lambdas). A channel
is either free (``None``) or owned by exactly one service. Services are
bidirectional, so a channel is reserved in both directions of the fiber.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

# Light in silica fiber travels at roughly c / 1.468 ~ 204,000 km/s,
# i.e. ~4.9 microseconds of one-way delay per kilometre.
FIBER_DELAY_MS_PER_KM = 0.0049


class LinkStatus(str, Enum):
    UP = "UP"
    DOWN = "DOWN"


@dataclass
class Node:
    id: str
    name: str
    lat: float
    lon: float


@dataclass
class Link:
    id: str
    a: str
    b: str
    length_km: float
    channels: list[str | None]
    status: LinkStatus = LinkStatus.UP

    @property
    def num_channels(self) -> int:
        return len(self.channels)

    @property
    def is_up(self) -> bool:
        return self.status is LinkStatus.UP

    @property
    def used_channels(self) -> int:
        return sum(1 for c in self.channels if c is not None)

    @property
    def utilization(self) -> float:
        return self.used_channels / self.num_channels if self.channels else 0.0

    @property
    def latency_ms(self) -> float:
        return self.length_km * FIBER_DELAY_MS_PER_KM

    def other_end(self, node_id: str) -> str:
        if node_id == self.a:
            return self.b
        if node_id == self.b:
            return self.a
        raise ValueError(f"node {node_id} is not an endpoint of link {self.id}")

    def is_free(self, channel: int) -> bool:
        return self.channels[channel] is None


@dataclass
class Network:
    num_channels: int
    nodes: dict[str, Node] = field(default_factory=dict)
    links: dict[str, Link] = field(default_factory=dict)
    _adjacency: dict[str, list[str]] = field(default_factory=dict)

    def add_node(self, node: Node) -> None:
        if node.id in self.nodes:
            raise ValueError(f"duplicate node {node.id}")
        self.nodes[node.id] = node
        self._adjacency[node.id] = []

    def add_link(self, a: str, b: str, length_km: float | None = None) -> Link:
        if a not in self.nodes or b not in self.nodes:
            raise ValueError(f"unknown endpoint in link {a}-{b}")
        if a == b:
            raise ValueError("self-loops are not allowed")
        link_id = "-".join(sorted((a, b)))
        if link_id in self.links:
            raise ValueError(f"duplicate link {link_id}")
        if length_km is None:
            length_km = estimate_fiber_km(self.nodes[a], self.nodes[b])
        link = Link(
            id=link_id,
            a=a,
            b=b,
            length_km=round(length_km),
            channels=[None] * self.num_channels,
        )
        self.links[link_id] = link
        self._adjacency[a].append(link_id)
        self._adjacency[b].append(link_id)
        return link

    def incident_links(self, node_id: str) -> list[Link]:
        return [self.links[lid] for lid in self._adjacency[node_id]]

    @property
    def utilization(self) -> float:
        total = sum(link.num_channels for link in self.links.values())
        used = sum(link.used_channels for link in self.links.values())
        return used / total if total else 0.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


# Terrestrial fiber rarely follows the great circle; it follows roads and
# railways. A route factor of ~1.25 is a common planning assumption.
ROUTE_FACTOR = 1.25


def estimate_fiber_km(a: Node, b: Node) -> float:
    return haversine_km(a.lat, a.lon, b.lat, b.lon) * ROUTE_FACTOR
