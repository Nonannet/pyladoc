from typing import Callable, Generator, Literal, TYPE_CHECKING
import html
import markdown
from base64 import b64encode
import re
import io
from . import latex
import pkgutil
from html.parser import HTMLParser
from io import StringIO
from . import svg_tools

HTML_OUTPUT = 0
LATEX_OUTPUT = 1

if TYPE_CHECKING:
    from pandas import DataFrame
    from pandas.io.formats.style import Styler
    import matplotlib.pyplot as plt
    from matplotlib.figure import Figure
    from matplotlib.legend import Legend as Mpl_Legend
    from matplotlib.text import Text as Mpl_Text

    Table = DataFrame | Styler
else:
    try:
        from pandas import DataFrame
    except ImportError:
        DataFrame = None

    try:
        from pandas.io.formats.style import Styler
        Table = DataFrame | Styler
    except ImportError:
        Table = DataFrame

    try:
        import matplotlib.pyplot as plt
        from matplotlib.figure import Figure
        from matplotlib.legend import Legend as Mpl_Legend
        from matplotlib.text import Text as Mpl_Text
    except ImportError:
        Figure = None


TRenderer = Literal['pandas', 'simple']
FFormat = Literal['svg', 'png', 'pgf']


def _get_pkgutil_string(path: str) -> str:
    data = pkgutil.get_data(__name__, path)
    assert data is not None
    return data.decode()


def _markdown_to_html(text: str) -> str:
    prep_text = re.sub(r'\u00A0', '&nbsp;', text)  # non-breaking space
    html_text = markdown.markdown(prep_text, extensions=['tables', 'fenced_code', 'def_list', 'abbr', 'sane_lists'])
    return html_text


def _drop_indent(text: str, amount: int) -> str:
    """
    Drops a specific number of indentation spaces from a multiline text.

    Args:
        text: The text to drop indentation from
        amount: The number of indentation space characters to drop

    Returns:
        The text with the specified amount of indentation removed
    """
    return ''.join(' ' * amount + line for line in text.splitlines(True))


def _save_figure(fig: Figure, buff: io.BytesIO, figure_format: FFormat, font_family: str | None, scale: float) -> None:
    """
    Saves a matplotlib figure to a file-like object.

    Args:
        fig: The figure to save
        buff: The file-like object to save the figure to
        figure_format: The format to save the figure in (svg, png or pgf)
        font_family: The font family to use for the figure
    """
    def get_all_elements() -> Generator[Mpl_Text, None, None]:
        for ax in fig.get_axes():
            yield ax.title
            yield ax.xaxis.label
            yield ax.yaxis.label
            yield from ax.get_xticklabels() + ax.get_yticklabels()
            legend: Mpl_Legend = ax.get_legend()
            if legend:
                yield from legend.get_texts()

    # Store current figure settings
    old_state = ((e, e.get_fontfamily()) for e in get_all_elements())
    old_size: tuple[float, float] = tuple(fig.get_size_inches())  # type: ignore[unused-ignore]

    # Adjust figure settings
    if font_family:
        for e, _ in old_state:
            e.set_fontfamily(font_family)

    fig.set_size_inches(old_size[0] * scale, old_size[1] * scale, False)

    # Render figure
    backends = {'png': 'AGG', 'svg': 'SVG', 'pgf': 'PGF'}
    assert figure_format in backends, 'Figure format can be pgf (vector), svg (vector) or png (raster)'
    fig.savefig(buff, format=figure_format, backend=backends[figure_format])  # type: ignore[unused-ignore]

    # Reset figure setting
    for e, s in old_state:
        e.set_fontfamily(s)

    fig.set_size_inches(old_size, None, False)


def escape_html(text: str) -> str:
    """
    Escapes special HTML characters in a given string.

    Args:
        text: The text to escape

    Returns:
        Escaped text save for inserting into HTML code
    """
    ret = re.sub(r'\u00A0', '&nbsp;', text)  # non-breaking space
    ret = html.escape(ret)
    return ' '.join(ret.strip().splitlines())


def figure_to_string(fig: Figure,
                     unique_id: str,
                     figure_format: FFormat = 'svg',
                     font_family: str | None = None,
                     scale: float = 1,
                     alt_text: str = '',
                     base64: bool = False) -> str:
    """
    Converts a matplotlib figure to a ascii-string. For png base64 encoding is
    used in general, for svg base64 encoding can be enabled. For base64 encoded
    figures a img-tag is included in the output.

    Args:
        fig: The figure to convert
        figure_format: The format to save the figure in (svg, png or pgf)
        font_family: The font family to use for the figure
        scale: Scaling factor for the figure size
        alt_text: The alt text for the figure
        base64: If the format is svg this determine if the image is encode in base64

    Returns:
        The figure as ascii-string
    """
    assert fig and isinstance(fig, Figure), 'fig parameter must be a matplotlib figure'
    with io.BytesIO() as buff:
        _save_figure(fig, buff, figure_format, font_family, scale)
        buff.seek(0)
        if figure_format == 'pgf':
            i = buff.read(2028).find(b'\\begingroup%')  # skip comments
            buff.seek(max(i, 0))
            return latex.to_ascii(buff.read().decode('utf-8'))

        elif figure_format == 'svg' and not base64:
            i = buff.read(2028).find(b'<svg')  # skip xml and DOCTYPE header
            buff.seek(max(i, 0))
            return svg_tools.update_svg_ids(svg_tools.clean_svg(buff.read().decode('utf-8')), unique_id)

        else:
            image_mime = {"png": "image/png", "svg": "image/svg+xml"}
            assert figure_format in image_mime, 'Unknown image format'
            return '<img alt="%s" src="data:%s;charset=utf-8;base64,%s">' % \
                (escape_html(alt_text),
                 image_mime[figure_format],
                 b64encode(buff.read()).decode('ascii'))  # base64 assures (7-bit) ascii


def latex_to_figure(latex_code: str) -> Figure:
    assert Figure, 'Matplotlib is required for rendering LaTeX expressions for HTML output.'  # type:ignore[truthy-function]
    fig, ax = plt.subplots()
    ax.set_xticks([])
    ax.set_yticks([])
    ax.axis('off')
    text = plt.text(0.5, 0.5, f'${latex_code}$', horizontalalignment='center',
                    verticalalignment='center', transform=ax.transAxes)
    fig.draw_without_rendering()
    bbox = text.get_window_extent()
    fig.set_size_inches(bbox.width / fig.dpi * 1.2, bbox.height / fig.dpi * 1.2)
    return fig


def _fillin_fields(template: str, fields: dict[str, str]) -> str:
    html_out = template
    for variable_name, value in fields.items():
        # Find indentation depths:
        ret = re.search(f"^(.*?)<!---START {variable_name}--->.*?<!---END {variable_name}--->", html_out, flags=re.MULTILINE)
        if ret:
            indent_depths = len(ret.group(1))
            html_out = html_out[:ret.start(0)] + _drop_indent(value, indent_depths) + html_out[ret.end(0):]
    return html_out


def _fillin_reference_names(input_string: str, item_index: dict[str, int]) -> str:
    replacements = [(*m.span(), m.group()) for m in re.finditer(r'(?<=@)\w+:[\w\_\-]+', input_string)]
    ret: list[str] = []
    current_pos = 0
    for start, end, ref in replacements:
        assert ref in item_index, f"Reference {ref} does not exist in the document"
        ret.append(input_string[current_pos:start - 1])
        ret.append(f'<a href="#pyld-ref-{latex.normalize_label_text(ref)}">{item_index[ref]}</a>')
        current_pos = end
    return ''.join(ret) + input_string[current_pos:]


def _check_latex_references(input_string: str, item_index: dict[str, int]) -> str:
    replacements = [m.group() for m in re.finditer(r'(?<=\\ref\{)\w+:[\w\_\\\-]+(?=\})', input_string)]
    escaped_items = set(latex.normalize_label_text(item) for item in item_index)
    for ref in replacements:
        assert ref in escaped_items, f"Reference {ref} does not exist in the document"
    return input_string


def _normalize_text_indent(text: str) -> str:
    text_lines = text.splitlines()
    if len(text_lines) > 1 and not text_lines[0].strip():
        text_lines = text_lines[1:]

    if not text_lines:
        return ''

    if len(text_lines) > 1 and text_lines[0] and text_lines[0][0] != ' ':
        indent_amount = len(text_lines[1]) - len(text_lines[1].lstrip())
    else:
        indent_amount = len(text_lines[0]) - len(text_lines[0].lstrip())

    return '\n'.join(
        [' ' * max(0, len(line) - len(line.strip()) - indent_amount) + line.strip()
         for line in text_lines])


def _create_document_writer() -> 'DocumentWriter':
    new_dwr = DocumentWriter()
    return new_dwr


def inject_to_template(content: str, template_path: str = '', internal_template: str = '') -> str:
    """
    injects a content string into a template. The placeholder <!--CONTENT-->
    will be replaced by the content. If the placeholder is prefixed with a
    '%' comment character, this character will be replaced as well.

    Args:
        template_path: Path to a template file
        internal_template: Path to a internal default template

    Returns:
        Template with included content
    """
    if template_path:
        with open(template_path, 'r') as f:
            template = f.read()
    elif internal_template:
        template = _get_pkgutil_string(internal_template)
    else:
        raise Exception('No template provided')

    assert '<!--CONTENT-->' in template, 'No <!--CONTENT--> expression in template located'
    prep_template = re.sub(r"\%?\s*<!--CONTENT-->", '<!--CONTENT-->', template)
    return prep_template.replace('<!--CONTENT-->', content)


class DocumentWriter():
    """
    A class to create a document for exporting to HTML or LaTeX.
    """
    def __init__(self) -> None:
        """
        Initializes the DocumentWriter instance.
        """
        self._doc: list[list[Callable[[], str]]] = []
        self._fields: dict[str, DocumentWriter] = dict()
        self._base64_svgs: bool = False
        self._figure_format: FFormat = 'svg'
        self._table_renderer: TRenderer = 'simple'
        self._font_family: str | None = None
        self._item_count: dict[str, int] = {}
        self._item_index: dict[str, int] = {}
        self._fig_scale: float = 1

    def _add_item(self, ref_id: str, ref_type: str, caption_prefix: str) -> tuple[str, str]:
        current_index = self._item_count.get(ref_type, 0) + 1
        if not ref_id:
            ref_id = f"auto{current_index}"
        self._item_index[f"{ref_type}:{ref_id}"] = current_index
        self._item_count[ref_type] = current_index
        return caption_prefix.format(current_index), latex.normalize_label_text(f"{ref_type}:{ref_id}")

    def _equation_embedding_reescaping(self, text: str) -> str:
        """
        Convert $$-escaping of LaTeX blocks and inline expressions
        to a HTML-style format: <latex>...</latex>.
        """
        block_pattern = re.compile(
            r'(^|\n)\s*\$\$\s*\n'         # start delimiter on a line on its own
            r'(?P<content>.*?)'           # capture block content non-greedily
            r'\n\s*\$\$\s*(\n|$)',        # end delimiter on a line on its own
            re.DOTALL | re.MULTILINE
        )

        def block_repl(match: re.Match[str]) -> str:
            content = match.group("content").strip()
            latex_label: str = ''

            label_pattern = re.compile(r'^\\label\{([^}]+)\}\s*\n?')
            label_match = label_pattern.match(content)
            if label_match:
                latex_label = label_match.group(1)
                # Remove the label command from the content.
                content = content[label_match.end():].lstrip()

            if latex_label and ':' in latex_label:
                parts = latex_label.split(':')
                ref_type = parts[0]
                ref_id = parts[1]
                caption, reference = self._add_item(ref_id, ref_type, '({})')
                return (f'<latex type="block" reference="{reference}" caption="{caption}">{content}</latex>')
            else:
                return f'<latex type="block">{content}</latex>'

        result = block_pattern.sub(block_repl, text)

        inline_pattern = re.compile(r'\$\$(.+?)\$\$')

        def inline_repl(match: re.Match[str]) -> str:
            content = match.group(1)
            return f'<latex>{content}</latex>'
        
        return inline_pattern.sub(inline_repl, result)

    def _get_equation_html(self, latex_equation: str, caption: str, reference: str, block: bool = False) -> str:
        fig = latex_to_figure(latex_equation)
        if block:
            fig_str = figure_to_string(fig, reference, self._figure_format, base64=self._base64_svgs)
            ret = ('<div class="equation-container" '
                   f'id="pyld-ref-{reference}">'
                   f'<div class="equation">{fig_str}</div>'
                   f'<div class="equation-number">{caption}</div></div>')
        else:
            ret = '<span class="inline-equation">' + figure_to_string(fig, reference, self._figure_format, base64=self._base64_svgs) + '</span>'

        plt.close(fig)
        return ret

    def _html_post_processing(self, html_code: str) -> str:
        """
        """
        class HTMLPostProcessor(HTMLParser):
            def __init__(self, document_writer: 'DocumentWriter') -> None:
                super().__init__()
                self.modified_html = StringIO()
                self.in_latex: bool = False
                self.eq_caption: str = ''
                self.reference: str = ''
                self.block: bool = False
                self.p_tags: int = 0
                self.dw = document_writer
                self.latex_count = 0
                self.self_closing = False

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                if tag == 'hr':
                    self.modified_html.write(f"<{tag}>")
                    self.self_closing = True
                elif tag == 'latex':
                    self.in_latex = True
                    attr_dict = {k: v if v else '' for k, v in attrs}
                    self.eq_caption = attr_dict.get('caption', '')
                    if 'reference' in attr_dict:
                        self.reference = attr_dict['reference']
                    else:
                        self.latex_count += 1
                        self.reference = f"auto_id_{self.latex_count}"
                    self.block = attr_dict.get('type') == 'block'
                elif not self.in_latex:
                    tag_text = self.get_starttag_text()
                    self.self_closing = tag_text.endswith('/>')
                    if tag_text:
                        self.modified_html.write(tag_text)
                    if tag == 'p':
                        self.p_tags += 1

            def handle_data(self, data: str) -> None:
                if self.in_latex:
                    eq_html = self.dw._get_equation_html(data, self.eq_caption, self.reference, self.block)
                    if self.p_tags > 0 and self.block:
                        # If a block equation (with divs) is inside a p tag: close and reopen it
                        self.modified_html.write(f"</p>{eq_html}<p>")
                    else:
                        self.modified_html.write(eq_html)

                else:
                    self.modified_html.write(data)

            def handle_endtag(self, tag: str) -> None:
                if tag == 'latex':
                    self.in_latex = False
                elif self.self_closing:
                    self.self_closing = False
                else:
                    self.modified_html.write(f"</{tag}>")
                    if tag == 'p' and self.p_tags > 0:
                        self.p_tags -= 1

        parser = HTMLPostProcessor(self)
        parser.feed(html_code)
        return parser.modified_html.getvalue()

    def new_field(self, name: str) -> 'DocumentWriter':
        new_dwr = _create_document_writer()
        self._fields[name] = new_dwr
        return new_dwr

    def add_document(self, doc: 'DocumentWriter') -> None:
        self._doc += doc._doc

    def add_diagram(self, fig: Figure, caption: str = '', ref_id: str = '',
                    prefix_pattern: str = 'Figure {}: ', ref_type: str = 'fig',
                    centered: bool = True) -> None:
        """
        Adds a diagram to the document.

        Args:
            fig: The figure to add (matplotlib figure)
            caption: The caption for the figure
            ref_id: If provided, the figure can be referenced by this string
            prefix_pattern: A custom string for the caption prefix, {} will
                be replaced by the figure number
            ref_type: The type of reference. Each type (e.g., 'fig', 'table')
                has an individual numbering
            centered: Whether to center the figure in LaTeX output
        """

        def render_to_html() -> str:
            caption_prefix, reference = self._add_item(ref_id, ref_type, prefix_pattern)
            return '<div id="pyld-ref-%s" class="figure">%s%s</div>' % (
                reference,
                figure_to_string(fig, reference, self._figure_format, base64=self._base64_svgs, scale=self._fig_scale),
                '<br>' + caption_prefix + escape_html(caption) if caption else '')

        def render_to_latex() -> str:
            _, reference = self._add_item(ref_id, ref_type, prefix_pattern)
            return '\\begin{figure}%s\n%s\n\\caption{%s}\n%s\\end{figure}' % (
                '\n\\centering' if centered else '',
                figure_to_string(fig, reference, 'pgf', self._font_family, scale=self._fig_scale),
                latex.escape_text(caption),
                '\\label{%s}\n' % latex.normalize_label_text(reference) if ref_id else '')

        self._doc.append([render_to_html, render_to_latex])

    def add_table(self, table: Table, caption: str = '', ref_id: str = '',
                  prefix_pattern: str = 'Table {}: ', ref_type: str = 'table', centered: bool = True) -> None:
        """
        Adds a table to the document.

        Args:
            table: The table to add (pandas DataFrame or Styler)
            caption: The caption for the table
            ref_id: If provided, the table can be referenced by this string
            prefix_pattern: A custom string for the caption prefix, {} will
                be replaced by the table number
            ref_type: The type of reference. Each type (e.g., 'fig', 'table')
                has an individual numbering
            centered: Whether to center the table in LaTeX output
        """
        assert Table and isinstance(table, Table), 'Table has to be a pandas DataFrame oder DataFrame Styler'
        styler = table if isinstance(table, Styler) else getattr(table, 'style', None)
        assert isinstance(styler, Styler), 'Jinja2 package is required for rendering tables'

        def render_to_html() -> str:
            caption_prefix, reference = self._add_item(ref_id, ref_type, prefix_pattern)

            html_string = styler.to_html(table_uuid=ref_id, caption=caption_prefix + escape_html(caption))
            return f'<div id="pyld-ref-{reference}">' + re.sub(r'<style.*?>.*?</style>', '', html_string, flags=re.DOTALL) + '</div>'

        def render_to_latex() -> str:
            _, reference = self._add_item(ref_id, ref_type, prefix_pattern)
            if self._table_renderer == 'pandas':
                return styler.to_latex(
                    label=reference,
                    hrules=True,
                    convert_css=True,
                    siunitx=True,
                    caption=latex.escape_text(caption),
                    position_float='centering' if centered else None)
            else:
                return latex.render_pandas_styler_table(styler, caption, reference, centered)

        self._doc.append([render_to_html, render_to_latex])

    def add_text(self, text: str, section_class: str = '') -> None:
        """
        Adds a text paragraph to the document.

        Args:
            text: The text to add
            section_class: The class for the paragraph
        """
        norm_text = _normalize_text_indent(text)

        def render_to_html() -> str:
            html = '<p>' + escape_html(norm_text) + '</p>'
            if section_class:
                return '<div class="' + section_class + '">' + html + '</div>'
            else:
                return html

        def render_to_latex() -> str:
            return latex.from_html(render_to_html())

        self._doc.append([render_to_html, render_to_latex])

    def add_html(self, text: str) -> None:
        """
        Adds HTML formatted text to the document. For the LaTeX
        export only basic HTML for text formatting and tables
        is supported.

        Args:
            text: The HTML to add to the document
        """
        def render_to_html() -> str:
            return text

        def render_to_latex() -> str:
            return latex.from_html(text)

        self._doc.append([render_to_html, render_to_latex])

    def add_h1(self, text: str) -> None:
        """
        Adds a h1 heading to the document.

        Args:
            text: The text of the heading
        """
        def render_to_html() -> str:
            return '<h1>' + escape_html(text) + '</h1>'

        def render_to_latex() -> str:
            return '\\section{' + latex.escape_text(text) + '}\n'

        self._doc.append([render_to_html, render_to_latex])

    def add_h2(self, text: str) -> None:
        """
        Adds a h2 heading to the document.

        Args:
            text: The text of the heading
        """
        def render_to_html() -> str:
            return '<h2>' + escape_html(text) + '</h2>'

        def render_to_latex() -> str:
            return '\\subsection{' + latex.escape_text(text) + '}\n'

        self._doc.append([render_to_html, render_to_latex])

    def add_h3(self, text: str) -> None:
        """
        Adds a h3 heading to the document.

        Args:
            text: The text of the heading
        """
        def render_to_html() -> str:
            return '<h3>' + escape_html(text) + '</h3>'

        def render_to_latex() -> str:
            return '\\subsubsection{' + latex.escape_text(text) + '}\n'

        self._doc.append([render_to_html, render_to_latex])

    def add_equation(self, latex_equation: str, ref_id: str = '', ref_type: str = 'eq') -> None:
        """
        Adds a LaTeX equation to the document.

        Args:
            latex_equation: LaTeX formatted equation
            ref_id: If provided, the equation is displayed with
                a number and can be referenced by the ref_id
        """

        def render_to_html() -> str:
            caption, reference = self._add_item(ref_id, ref_type, '({})')
            return self._get_equation_html(latex_equation, caption, reference, block=True)

        def render_to_latex() -> str:
            _, reference = self._add_item(ref_id, ref_type, '')
            return latex.get_equation_code(latex_equation, reference, block=True)

        self._doc.append([render_to_html, render_to_latex])

    def add_markdown(self, text: str, section_class: str = '') -> None:
        """
        Adds a markdown formatted text to the document.

        Args:
            text: The markdown text to add
            section_class: The class for the text section
        """
        norm_text = _normalize_text_indent(str(text))

        def render_to_html() -> str:
            html = _markdown_to_html(self._equation_embedding_reescaping(norm_text))
            if section_class:
                return '<div class="' + section_class + '">' + html + '</div>'
            else:
                return html

        def render_to_latex() -> str:
            html = _markdown_to_html(
                self._equation_embedding_reescaping(norm_text))
            return latex.from_html(html)

        self._doc.append([render_to_html, render_to_latex])

    def _render_doc(self, doc_type: int) -> str:
        fields = {k: f.to_html() for k, f in self._fields.items()}
        return _fillin_fields(''.join(el[doc_type]() for el in self._doc), fields)

    def to_html(self, figure_format: FFormat = 'svg',
                base64_svgs: bool = False, figure_scale: float = 1) -> str:
        """
        Export the document to HTML. Figures will bew embedded in the HTML code.
        The format can be selected between png in base64, inline svg or svg in base64.

        Args:
            figure_format: The format for embedding the figures in the HTML code (svg or png)
            base64_svgs: Whether to encode svg images in base64

        Returns:
            The HTML code
        """
        self._figure_format = figure_format
        self._base64_svgs = base64_svgs
        self._fig_scale = figure_scale

        return self._html_post_processing(_fillin_reference_names(self._render_doc(HTML_OUTPUT), self._item_index))

    def to_latex(self, font_family: Literal[None, 'serif', 'sans-serif'] = None,
                 table_renderer: TRenderer = 'simple', figure_scale: float = 1) -> str:
        """
        Export the document to LaTeX. Figures will be embedded as pgf graphics.

        Args:
            font_family: Overwrites the front family for figures
            table_renderer: The renderer for tables (simple: renderer with column type
                guessing for text and numbers; pandas: using the internal pandas LaTeX renderer)

        Returns:
            The LaTeX code
        """
        self._font_family = font_family
        assert table_renderer in ['simple', 'pandas'], "table_renderer must be 'simple' or 'pandas'"
        self._table_renderer = table_renderer
        self._fig_scale = figure_scale

        return _check_latex_references(self._render_doc(LATEX_OUTPUT), self._item_index)

    def to_pdf(self, file_path: str,
               font_family: Literal[None, 'serif', 'sans-serif'] = None,
               table_renderer: TRenderer = 'simple',
               latex_template_path: str = '') -> bool:
        """
        Export the document to a PDF file using LaTeX.

        Args:
            file_path: The path to save the PDF file to
            font_family: Overwrites the front family for figures and the template
            latex_template_path: Path to a LaTeX template file. The
                expression <!--CONTENT--> will be replaced by the generated content.
                If no path is provided a default template is used.

        Returns:
            True if the PDF file was successfully created
        """
        latex_code = inject_to_template(self.to_latex(font_family, table_renderer),
                                        latex_template_path,
                                        'templates/default_template.tex')

        if font_family == 'sans-serif':
            latex_code = latex.inject_latex_command(latex_code, '\\renewcommand{\\familydefault}{\\sfdefault}')
        success, errors, warnings = latex.compile(latex_code, file_path)

        if not success:
            print('Errors:')
            print('\n'.join(errors))
            print('Warnings:')
            print('\n'.join(warnings))

        return success

    def _repr_html_(self) -> str:
        return self.to_html()

    def __repr__(self) -> str:
        return self.to_html()
