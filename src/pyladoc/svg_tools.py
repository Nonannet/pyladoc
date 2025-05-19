import re
from re import Match


def update_svg_ids(input_svg: str, unique_id: str) -> str:
    """Add a unique ID part to all svg IDs and update references ti these IDs"""
    id_mapping: dict[str, str] = {}

    def update_ids(match: Match[str]) -> str:
        old_id = match.group(1)
        new_id = f"svg-{unique_id}-{old_id}"
        id_mapping[old_id] = new_id
        return f' id="{new_id}"'

    def update_references(match: Match[str]) -> str:
        old_ref = match.group(1)
        new_ref = id_mapping.get(old_ref, old_ref)
        if match.group(0).startswith('xlink:href'):
            return f'xlink:href="#{new_ref}"'
        else:
            return f'url(#{new_ref})'

    # Update IDs
    svg_string = re.sub(r'\sid="(.*?)"', update_ids, input_svg)

    # Update references to IDs
    svg_string = re.sub(r'url\(#([^\)]+)\)', update_references, svg_string)
    svg_string = re.sub(r'xlink:href="#([^\"]+)"', update_references, svg_string)

    return svg_string


def clean_svg(svg_text: str) -> str:
    # remove all tags not alllowd for inline svg from metadata:
    svg_text = re.sub(r'<metadata>.*?</metadata>', '', svg_text, flags=re.DOTALL)

    # remove illegal path-tags without d attribute:
    return re.sub(r'<path(?![^>]*\sd=)\s.*?/>', '', svg_text, flags=re.DOTALL)
