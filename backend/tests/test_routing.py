from __future__ import annotations

import pytest

from app.routing import first_fit_channel, k_shortest_paths, shortest_path
from app.topology import Network, Node


def square() -> Network:
    """A-B-C-D square with a long A-C diagonal.

    A --1-- B
    |       |
    4       1
    |       |
    D --1-- C      plus A-C = 5
    """
    net = Network(num_channels=4)
    for nid in "ABCD":
        net.add_node(Node(nid, nid, 0, 0))
    net.add_link("A", "B", 1)
    net.add_link("B", "C", 1)
    net.add_link("C", "D", 1)
    net.add_link("A", "D", 4)
    net.add_link("A", "C", 5)
    return net


def test_shortest_path_prefers_lowest_length() -> None:
    p = shortest_path(square(), "A", "C")
    assert p is not None
    assert p.nodes == ("A", "B", "C")
    assert p.length_km == 2


def test_shortest_path_skips_failed_links() -> None:
    from app.topology import LinkStatus

    net = square()
    net.links["A-B"].status = LinkStatus.DOWN
    p = shortest_path(net, "A", "C")
    assert p is not None and p.nodes == ("A", "C")


def test_shortest_path_unreachable_returns_none() -> None:
    net = square()
    assert shortest_path(net, "A", "C", excluded_links={"A-B", "A-C", "A-D"}) is None


def test_unknown_node_raises() -> None:
    with pytest.raises(KeyError):
        shortest_path(square(), "A", "Z")


def test_k_shortest_paths_are_sorted_unique_and_loop_free() -> None:
    paths = k_shortest_paths(square(), "A", "C", k=5)
    lengths = [p.length_km for p in paths]
    assert lengths == sorted(lengths)
    assert len({p.links for p in paths}) == len(paths)
    for p in paths:
        assert len(set(p.nodes)) == len(p.nodes)
    # A-B-C (2), A-C (5), A-D-C (5) - exactly three simple paths exist
    assert len(paths) == 3
    assert paths[0].nodes == ("A", "B", "C")


def test_first_fit_respects_wavelength_continuity() -> None:
    net = square()
    net.links["A-B"].channels[0] = "x"
    net.links["B-C"].channels[1] = "y"
    # channel 0 busy on A-B, channel 1 busy on B-C -> first common free is 2
    assert first_fit_channel(net, ["A-B", "B-C"]) == 2


def test_first_fit_none_when_spectrum_full() -> None:
    net = square()
    net.links["A-B"].channels = ["x"] * 4
    assert first_fit_channel(net, ["A-B"]) is None
