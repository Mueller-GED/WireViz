# -*- coding: utf-8 -*-

import re
from typing import Any, List, Optional, Union

from wireviz import APP_NAME, APP_URL, __version__
from wireviz.wv_colors import MultiColor, SingleColor
from wireviz.wv_dataclasses import (
    ArrowDirection,
    ArrowWeight,
    Cable,
    Component,
    Connector,
    MateComponent,
    MatePin,
    ShieldClass,
    WireClass,
)
from wireviz.wv_html import Img, Table, Td, Tr
from wireviz.wv_templates import get_template
from wireviz.wv_utils import html_line_breaks, remove_links


def gv_node_connector(connector: Connector) -> Table:
    # TODO: extend connector style support
    params = {"component": connector}
    is_simple_connector = connector.style == "simple"
    template_name = "connector.html"
    if is_simple_connector:
        template_name = "simple-connector.html"

    rendered = get_template(template_name).render(params)
    cleaned_render = "\n".join([l.rstrip() for l in rendered.split("\n") if l.strip()])
    return cleaned_render


def gv_node_cable(cable: Cable) -> Table:
    # TODO: add support for row below the wire
    #    # row below the wire
    #    if wire.partnumbers:
    #        cells_below = wire.partnumbers.as_list(parent_partnumbers=cable.partnumbers)
    #        if cells_below is not None and len(cells_below) > 0:
    #            table_below = (
    #                Table(
    #                    Tr([Td(cell) for cell in cells_below]),
    #                    border=0,
    #                    cellborder=0,
    #                    cellspacing=0,
    #                ),
    #            )
    #            rows.append(Tr(Td(table_below, colspan=len(cells_above))))
    # TODO: support multicolor cables
    line_wires = []
    params = {
        "component": cable,
        "line_wires": line_wires,
        "image": cable.image,
        "line_notes": html_line_breaks(cable.notes),
        "additional_components": cable.additional_components,
    }
    # TODO: extend cable style support
    template_name = "cable.html"
    rendered = get_template(template_name).render(params)
    cleaned_render = "\n".join([l.rstrip() for l in rendered.split("\n") if l.strip()])
    return cleaned_render


def gv_connector_loops(connector: Connector) -> List:
    loop_edges = []
    if connector.ports_left:
        loop_side = "l"
        loop_dir = "w"
    elif connector.ports_right:
        loop_side = "r"
        loop_dir = "e"
    else:
        raise Exception("No side for loops")
    for loop in connector.loops:
        head = f"{connector.designator}:p{loop[0]}{loop_side}:{loop_dir}"
        tail = f"{connector.designator}:p{loop[1]}{loop_side}:{loop_dir}"
        loop_edges.append((head, tail))
    return loop_edges


def gv_edge_wire(harness, cable, connection) -> (str, str, str):
    if connection.via.color:
        # check if it's an actual wire and not a shield
        color = f"#000000:{connection.via.color.html_padded}:#000000"
    else:  # it's a shield connection
        color = "#000000"

    if connection.from_ is not None:  # connect to left
        from_port_str = (
            f":p{connection.from_.index+1}r"
            if harness.connectors[str(connection.from_.parent)].style != "simple"
            else ""
        )
        code_left_1 = f"{str(connection.from_.parent)}{from_port_str}:e"
        code_left_2 = f"{str(connection.via.parent)}:w{connection.via.index+1}:w"
        # ports in GraphViz are 1-indexed for more natural maping to pin/wire numbers
    else:
        code_left_1, code_left_2 = None, None

    if connection.to is not None:  # connect to right
        to_port_str = (
            f":p{connection.to.index+1}l"
            if harness.connectors[str(connection.to.parent)].style != "simple"
            else ""
        )
        code_right_1 = f"{str(connection.via.parent)}:w{connection.via.index+1}:e"
        code_right_2 = f"{str(connection.to.parent)}{to_port_str}:w"
    else:
        code_right_1, code_right_2 = None, None

    return color, code_left_1, code_left_2, code_right_1, code_right_2


def parse_arrow_str(inp: str) -> ArrowDirection:
    if inp[0] == "<" and inp[-1] == ">":
        return ArrowDirection.BOTH
    elif inp[0] == "<":
        return ArrowDirection.BACK
    elif inp[-1] == ">":
        return ArrowDirection.FORWARD
    else:
        return ArrowDirection.NONE


def gv_edge_mate(mate) -> (str, str, str, str):
    if mate.arrow.weight == ArrowWeight.SINGLE:
        color = "#000000"
    elif mate.arrow.weight == ArrowWeight.DOUBLE:
        color = "#000000:#000000"

    dir = mate.arrow.direction.name.lower()

    if isinstance(mate, MatePin):
        from_pin_index = mate.from_.index
        from_port_str = f":p{from_pin_index+1}r"
        from_designator = str(mate.from_.parent)
        to_pin_index = mate.to.index
        to_port_str = f":p{to_pin_index+1}l"
        to_designator = str(mate.to.parent)
    elif isinstance(mate, MateComponent):
        from_designator = mate.from_
        from_port_str = ""
        to_designator = mate.to
        to_port_str = ""
    else:
        raise Exception(f"Unknown type of mate:\n{mate}")

    code_from = f"{from_designator}{from_port_str}:e"
    code_to = f"{to_designator}{to_port_str}:w"

    return color, dir, code_from, code_to


def set_dot_basics(dot, options):
    dot.body.append(f"// Graph generated by {APP_NAME} {__version__}\n")
    dot.body.append(f"// {APP_URL}\n")
    dot.attr(
        "graph",
        rankdir="LR",
        ranksep="3", # TODO: make conditional on the number of components/connections
        bgcolor=options.bgcolor.html,
        nodesep="0.33",
        fontname=options.fontname,
        splines="polyline",
    )
    dot.attr(
        "node",
        shape="none",
        width="0",
        height="0",
        margin="0",  # Actual size of the node is entirely determined by the label.
        style="filled",
        fillcolor=options.bgcolor_node.html,
        fontname=options.fontname,
    )
    dot.attr("edge", style="bold", fontname=options.fontname)
