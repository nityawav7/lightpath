"""Path computation: shortest paths, k-shortest paths and wavelength assignment.

Routing and Wavelength Assignment (RWA) is the core problem of an optical
transport network. Without wavelength converters, a lightpath must use the
*same* channel on every fiber it crosses (the wavelength-continuity
constraint). We solve it the way most planning tools do:

1. Route: compute up to K candidate paths with Yen's algorithm (Dijkstra on
   fiber length), skipping failed fibers.
2. Reach check: drop paths longer than the optical reach of the requested
   line rate / modulation format.
3. Wavelength assignment: First-Fit, i.e. the lowest channel index that is
   free on every link of the path. First-Fit packs the spectrum and gives
   low blocking probability while being O(K * L * W).
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable
from dataclasses import dataclass

from .topology import FIBER_DELAY_MS_PER_KM, Network


@dataclass(frozen=True)
class Path:
    nodes: tuple[str, ...]
    links: tuple[str, ...]
    length_km: float

    @property
    def hops(self) -> int:
        return len(self.links)

    @property
    def latency_ms(self) -> float:
        return self.length_km * FIBER_DELAY_MS_PER_KM


@dataclass(frozen=True)
class RateProfile:
    rate_gbps: int
    modulation: str
    max_reach_km: float


# Coherent line-rate profiles: higher-order modulation carries more bits per
# symbol but needs a better OSNR, so it reaches shorter distances.
RATE_PROFILES: dict[int, RateProfile] = {
    100: RateProfile(100, "DP-QPSK 32 GBd", 5000),
    200: RateProfile(200, "DP-QPSK 64 GBd", 3500),
    400: RateProfile(400, "DP-16QAM 64 GBd", 2000),
}


def shortest_path(
    net: Network,
    src: str,
    dst: str,
    excluded_links: Iterable[str] = (),
    excluded_nodes: Iterable[str] = (),
) -> Path | None:
    """Dijkstra on fiber length over UP links. Returns ``None`` if unreachable."""
    if src not in net.nodes or dst not in net.nodes:
        raise KeyError("unknown source or destination node")
    banned_links = set(excluded_links)
    banned_nodes = set(excluded_nodes)
    if src in banned_nodes or dst in banned_nodes:
        return None

    dist: dict[str, float] = {src: 0.0}
    prev: dict[str, tuple[str, str]] = {}  # node -> (previous node, link id)
    heap: list[tuple[float, str]] = [(0.0, src)]
    visited: set[str] = set()

    while heap:
        d, node = heapq.heappop(heap)
        if node in visited:
            continue
        visited.add(node)
        if node == dst:
            break
        for link in net.incident_links(node):
            if not link.is_up or link.id in banned_links:
                continue
            nxt = link.other_end(node)
            if nxt in visited or nxt in banned_nodes:
                continue
            nd = d + link.length_km
            # Tie-break on node id so results are deterministic.
            if nd < dist.get(nxt, float("inf")):
                dist[nxt] = nd
                prev[nxt] = (node, link.id)
                heapq.heappush(heap, (nd, nxt))

    if dst not in visited:
        return None

    nodes = [dst]
    links: list[str] = []
    while nodes[-1] != src:
        p, lid = prev[nodes[-1]]
        links.append(lid)
        nodes.append(p)
    nodes.reverse()
    links.reverse()
    return Path(tuple(nodes), tuple(links), dist[dst])


def _path_length(net: Network, links: Iterable[str]) -> float:
    return sum(net.links[lid].length_km for lid in links)


def k_shortest_paths(
    net: Network,
    src: str,
    dst: str,
    k: int,
    excluded_links: Iterable[str] = (),
) -> list[Path]:
    """Yen's algorithm: the K shortest loop-free paths, in increasing length."""
    if k < 1:
        return []
    base_excluded = set(excluded_links)
    first = shortest_path(net, src, dst, base_excluded)
    if first is None:
        return []

    accepted: list[Path] = [first]
    candidates: list[tuple[float, tuple[str, ...], Path]] = []
    seen: set[tuple[str, ...]] = {first.links}

    while len(accepted) < k:
        last = accepted[-1]
        for i in range(len(last.nodes) - 1):
            spur_node = last.nodes[i]
            root_nodes = last.nodes[: i + 1]
            root_links = last.links[:i]

            removed = set(base_excluded)
            for p in accepted:
                if p.nodes[: i + 1] == root_nodes and len(p.links) > i:
                    removed.add(p.links[i])

            spur = shortest_path(net, spur_node, dst, removed, excluded_nodes=root_nodes[:-1])
            if spur is None:
                continue
            total_links = root_links + spur.links
            if total_links in seen:
                continue
            seen.add(total_links)
            total = Path(
                root_nodes[:-1] + spur.nodes,
                total_links,
                _path_length(net, total_links),
            )
            heapq.heappush(candidates, (total.length_km, total.links, total))

        if not candidates:
            break
        _, _, best = heapq.heappop(candidates)
        accepted.append(best)

    return accepted


def first_fit_channel(net: Network, links: Iterable[str]) -> int | None:
    """Lowest channel index free on every link (wavelength continuity)."""
    link_objs = [net.links[lid] for lid in links]
    for ch in range(net.num_channels):
        if all(link.is_free(ch) for link in link_objs):
            return ch
    return None


def channel_frequency_thz(channel: int) -> float:
    """ITU-T G.694.1 100 GHz grid, starting at 191.30 THz (C-band)."""
    return round(191.30 + channel * 0.1, 2)
