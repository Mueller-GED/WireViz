# -*- coding: utf-8 -*-

import base64
import re
from pathlib import Path
from typing import List, Union

import jinja2

import wireviz  # for doing wireviz.__file__
from wireviz import APP_NAME, APP_URL, __version__
from wireviz.wv_dataclasses import Metadata, Options
from wireviz.wv_utils import open_file_read, open_file_write

mime_subtype_replacements = {"jpg": "jpeg", "tif": "tiff"}


def embed_svg_images(svg_in: str, base_path: Union[str, Path] = Path.cwd()) -> str:
    images_b64 = {}  # cache of base64-encoded images

    def image_tag(pre: str, url: str, post: str) -> str:
        return f'<image{pre} xlink:href="{url}"{post}>'

    def replace(match: re.Match) -> str:
        imgurl = match["URL"]
        if not imgurl in images_b64:  # only encode/cache every unique URL once
            imgurl_abs = (Path(base_path) / imgurl).resolve()
            image = imgurl_abs.read_bytes()
            images_b64[imgurl] = base64.b64encode(image).decode("utf-8")
        return image_tag(
            match["PRE"] or "",
            f"data:image/{get_mime_subtype(imgurl)};base64, {images_b64[imgurl]}",
            match["POST"] or "",
        )

    pattern = re.compile(
        image_tag(r"(?P<PRE> [^>]*?)?", r'(?P<URL>[^"]*?)', r"(?P<POST> [^>]*?)?"),
        re.IGNORECASE,
    )
    return pattern.sub(replace, svg_in)


def get_mime_subtype(filename: Union[str, Path]) -> str:
    mime_subtype = Path(filename).suffix.lstrip(".").lower()
    if mime_subtype in mime_subtype_replacements:
        mime_subtype = mime_subtype_replacements[mime_subtype]
    return mime_subtype


def embed_svg_images_file(
    filename_in: Union[str, Path], overwrite: bool = True
) -> None:
    filename_in = Path(filename_in).resolve()
    filename_out = filename_in.with_suffix(".b64.svg")
    filename_out.write_text(
        embed_svg_images(filename_in.read_text(), filename_in.parent)
    )
    if overwrite:
        filename_out.replace(filename_in)


def get_template_html(template_name):
    template_file_path = jinja2.FileSystemLoader(
        Path(wireviz.__file__).parent / "templates"
    )
    jinja_env = jinja2.Environment(loader=template_file_path)

    return jinja_env.get_template(template_name + ".html")


def generate_html_output(
    filename: Union[str, Path],
    bom: List[List[str]],
    metadata: Metadata,
    options: Options,
):
    print("Generating html output")
    template_name = metadata.get("template", {}).get("name", "simple")
    page_template = get_template_html(template_name)

    # embed SVG diagram
    with open_file_read(f"{filename}.tmp.svg") as file:
        svgdata = re.sub(
            "^<[?]xml [^?>]*[?]>[^<]*<!DOCTYPE [^>]*>",
            "<!-- XML and DOCTYPE declarations from SVG file removed -->",
            file.read(),
            1,
        )

    # generate BOM table
    # generate BOM header (may be at the top or bottom of the table)
    bom_header_html = "  <tr>\n"
    for item in bom[0]:
        th_class = f"bom_col_{item.lower()}"
        bom_header_html = f'{bom_header_html}    <th class="{th_class}">{item}</th>\n'
    bom_header_html = f"{bom_header_html}  </tr>\n"

    # generate BOM contents
    bom_contents = []
    for row in bom[1:]:
        row_html = "  <tr>\n"
        for i, item in enumerate(row):
            td_class = f"bom_col_{bom[0][i].lower()}"
            row_html = f'{row_html}    <td class="{td_class}">{item if item is not None else ""}</td>\n'
        row_html = f"{row_html}  </tr>\n"
        bom_contents.append(row_html)

    bom_html = (
        '<table class="bom">\n' + bom_header_html + "".join(bom_contents) + "</table>\n"
    )
    bom_html_reversed = (
        '<table class="bom">\n'
        + "".join(list(reversed(bom_contents)))
        + bom_header_html
        + "</table>\n"
    )

    if metadata:
        sheet_current = metadata["sheet_current"]
        sheet_total = metadata["sheet_total"]
    else:
        sheet_current = 1
        sheet_total = 1

    replacements = {
        "generator": f"{APP_NAME} {__version__} - {APP_URL}",
        "fontname": options.fontname,
        "bgcolor": options.bgcolor.html,
        "diagram": svgdata,
        "bom": bom_html,
        "bom_reversed": bom_html_reversed,
        "sheet_current": sheet_current,
        "sheet_total": sheet_total,
        "titleblock_rows": 9,
    }

    # prepare metadata replacements
    added_metadata = {
        "revisions": [],
        "authors": [],
    }
    if metadata:
        for item, contents in metadata.items():
            if item == "revisions":
                added_metadata["revisions"] = [
                    {"rev": rev, **v} for rev, v in contents.items()
                ]
                continue
            if item == "authors":
                added_metadata["authors"] = [
                    {"row": row, **v} for row, v in contents.items()
                ]
                continue
            if item == "pn":
                added_metadata[item] = f'{contents}-{metadata.get("sheet_name")}'
                continue

            added_metadata[item] = contents

        replacements[
            "sheetsize_default"
        ] = f'{metadata.get("template", {}).get("sheetsize", "sheetsize_default")}'
        # include quotes so no replacement happens within <style> definition

    for i in range(
        replacements["titleblock_rows"] - len(added_metadata["revisions"]) - 1
    ):
        added_metadata["revisions"].append({})
    added_metadata["revisions"].reverse()
    for i in range(4 - len(added_metadata["authors"])):
        added_metadata["authors"].append({})
    replacements = {**replacements, **added_metadata}

    # prepare titleblock
    titleblock_template = get_template_html("titleblock")
    replacements["titleblock"] = titleblock_template.render(replacements)

    page_rendered = page_template.render(replacements)
    open_file_write(f"{filename}.html").write(page_rendered)
