from html.parser import HTMLParser
from typing import Generator, Any, Literal, get_args
from pandas.io.formats.style import Styler
import re
import os
import shutil
import subprocess
import tempfile
from .latex_escaping import unicode_to_latex_dict, latex_escape_dict


LatexEngine = Literal['pdflatex', 'lualatex', 'xelatex', 'tectonic']


def basic_formatter(value: Any) -> str:
    return escape_text(str(value))


def to_ascii(text: str) -> str:
    """
    Replaces/escapes often used unicode characters in LaTeX code or text
    with its LaTeX ascii equivalents.

    Args:
        text: The text to convert.

    Returns:
        The escaped text.
    """
    regex_filter = ('|'.join(unicode_to_latex_dict))

    last_s = 0
    ret: list[str] = []
    for m in re.finditer(regex_filter, text):
        s1, s2 = m.span()
        ret.append(text[last_s:s1])
        ret.append(unicode_to_latex_dict[m.group()])
        last_s = s2
    ret.append(text[last_s:])

    return ''.join(ret)


def normalize_label_text(text: str) -> str:
    """
    Replace any special non-allowed character in the lable text.

    Args:
        text: Input text

    Returns:
        Normalized text
    """
    return re.sub(r"[^a-zA-Z0-9.:]", '-', text)


def escape_text(text: str) -> str:
    """
    Escapes special LaTeX characters and often used unicode characters in a given string.

    Args:
        text: The text to escape

    Returns:
        Escaped text
    """

    latex_translation = latex_escape_dict | unicode_to_latex_dict

    regex_filter = '|'.join(latex_translation)

    last_s = 0
    ret: list[str] = []
    for m in re.finditer(regex_filter, text):
        s1, s2 = m.span()
        ret.append(text[last_s:s1])
        matches = [v for k, v in latex_translation.items() if re.match(k, m.group())]
        if m.group(1):
            ret.append(matches[0].replace(r'\g<1>', normalize_label_text(m.group(1))))
        else:
            ret.append(matches[0])
        last_s = s2
    ret.append(text[last_s:])

    return ''.join(ret)


def get_equation_code(equation: str, reference: str | None, block: bool = False) -> str:
    """
    Converts an equation string to LaTeX code.

    Args:
        equation: The LaTeX equation string.
        reference: The reference type and ID for the equation separated by a ':'.
    """
    if block:
        if reference:
            return '\\begin{equation}\\label{%s}%s\\end{equation}' % (
                normalize_label_text(reference), equation)
        else:
            return '\\[%s\\]' % equation
    else:
        return '\\(%s\\)' % equation


def render_pandas_styler_table(df_style: Styler, caption: str = '', label: str = '', centering: bool = True) -> str:
    """
    Converts a pandas Styler object to LaTeX table.

    Args:
        df_style: The pandas Styler object to convert.
        caption: The caption for the table.
        label: Label for referencing the table.
        centering: Whether to center the table.

    Returns:
        The LaTeX code.
    """
    def iter_table(table: dict[str, Any]) -> Generator[str, None, None]:
        yield '\\begin{table}\n'
        if centering:
            yield '\\centering\n'

        # Guess column type
        numeric = re.compile(r'^[<>]?\s*(?:\d+,?)+(?:\.\d+)?(?:\s\D.*)?$')
        formats = ['S' if all(
            (numeric.match(line[ci]['display_value'].strip()) for line in table['body'])
        ) else 'l' for ci in range(len(table['body'][0])) if table['body'][0][ci]['is_visible']]

        if caption:
            yield f"\\caption{{{escape_text(caption)}}}\n"
        if label:
            yield f"\\label{{{normalize_label_text(label)}}}\n"
        yield f"\\begin{{tabular}}{{{''.join(formats)}}}\n\\toprule\n"

        for head in table['head']:
            yield (' & '.join(f"\\text{{{escape_text(c['display_value'].strip())}}}"
                              for c in head if c['is_visible']))
            yield ' \\\\\n'

        yield '\\midrule\n'

        for body in table['body']:
            yield (' & '.join(escape_text(c['display_value'].strip())
                              for c in body if c['is_visible']))
            yield ' \\\\\n'

        yield '\\bottomrule\n\\end{tabular}\n\\end{table}'

    str_list = iter_table(df_style._translate(False, False, blank=''))  # type: ignore[attr-defined]

    return ''.join(str_list)


def from_html(html_code: str) -> str:
    """
    Converts HTML code to LaTeX code using HTMLParser.

    Args:
        html_code: The HTML code to convert.

    Returns:
        The LaTeX code.
    """
    html_to_latex = {
        'strong': ('\\textbf{', '}'),
        'b': ('\\textbf{', '}'),
        'em': ('\\emph{', '}'),
        'i': ('\\emph{', '}'),
        'p': ('', '\n\n'),
        'h1': ('\\section{', '}\n'),
        'h2': ('\\subsection{', '}\n'),
        'h3': ('\\subsubsection{', '}\n'),
        'ul': ('\\begin{itemize}\n', '\\end{itemize}\n'),
        'ol': ('\\begin{enumerate}\n', '\\end{enumerate}\n'),
        'li': ('\\item ', '\n')
    }

    class LaTeXHTMLParser(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.latex_code: list[str] = []
            self.header_index: int = -1
            self.column_alignment = ''
            self.midrule_flag = False
            self.header_flag = False
            self.attr_dict: dict[str, str] = {}
            self.equation_flag = False

        def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
            self.attr_dict = {k: v if v else '' for k, v in attrs}
            if tag in html_to_latex:
                prefix, _ = html_to_latex[tag]
                self.latex_code.append(prefix)
            elif tag == 'table':
                self.header_index = len(self.latex_code)
                self.latex_code.append('')  # Placeholder for column header
                self.midrule_flag = False
                self.header_flag = False
            elif tag == 'tr':
                self.column_alignment = ''
            elif tag in ['th', 'td']:
                if 'right' in self.attr_dict.get('style', ''):
                    self.column_alignment += 'r'
                else:
                    self.column_alignment += 'l'
            elif tag == 'a':
                href = self.attr_dict.get('href')
                assert href, 'Link href attribute is missing'
                self.latex_code.append(f"\\href{{{href}}}{{")
            elif tag == 'hr':
                self.latex_code.append("\n\n\\noindent\\rule[0.5ex]{\\linewidth}{1pt}\n\n")
            elif tag == 'latex':
                self.equation_flag = True

        def handle_endtag(self, tag: str) -> None:
            if tag in html_to_latex:
                _, postfix = html_to_latex[tag]
                self.latex_code.append(postfix)
            elif tag == 'table':
                self.latex_code.append("\\bottomrule\n\\end{tabular}\n")
            elif tag == 'tr':
                self.latex_code.pop()  # Remove column separator after last entry
                if self.header_index >= 0:
                    self.latex_code[self.header_index] = f"\\begin{{tabular}}{{{self.column_alignment}}}\\toprule\n"
                    self.header_index = -1
                self.latex_code.append(' \\\\\n')
                if self.header_flag and not self.midrule_flag:
                    self.latex_code.append("\\midrule\n")
                    self.midrule_flag = True
            elif tag == 'th':
                self.latex_code.append(" & ")
                self.header_flag = True
            elif tag == 'td':
                self.latex_code.append(" & ")
            elif tag == 'a':
                self.latex_code.append("}")
            elif tag == 'latex':
                self.equation_flag = False

        def handle_data(self, data: str) -> None:
            if self.equation_flag:
                block = self.attr_dict.get('type') == 'block'
                reference = self.attr_dict.get('reference')
                self.latex_code.append(get_equation_code(data, reference, block))
            elif data.strip():
                self.latex_code.append(escape_text(data))

    parser = LaTeXHTMLParser()
    parser.feed(html_code)
    return ''.join(parser.latex_code)


def compile(latex_code: str, output_file: str = '', encoding: str = 'utf-8', engine: LatexEngine = 'pdflatex') -> tuple[bool, list[str], list[str]]:
    """
    Compiles LaTeX code to a PDF file.

    Args:
        latex_code: The LaTeX code to compile.
        output_file: The output file path.
        encoding: The encoding of the LaTeX code.
        engine: LaTeX engine (pdflatex, lualatex, xelatex or tectonic)

    Returns:
        A tuple with three elements:
        - A boolean indicating whether the compilation was successful.
        - A list of errors.
        - A list of warnings.
    """

    assert engine in get_args(LatexEngine), "engine must be pdflatex, lualatex, xelatex or tectonic"

    with tempfile.TemporaryDirectory() as tmp_path:
        if engine == 'tectonic':
            command = ['tectonic', '--outdir', tmp_path, '-']
        else:
            command = [engine, '--halt-on-error', '--output-directory', tmp_path]

        errors: list[str] = []
        warnings: list[str] = []

        for i in range(1, 4):
            rerun_flag = False
            error_flag = False
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
            output, error = process.communicate(input=latex_code.encode(encoding))

            assert not error, 'Compilation error: ' + output.decode(encoding)

            for line in output.decode(encoding).split('\n'):
                if 'Warning' in line:
                    warnings.append(f"Run {i}: " + line)
                    if 'reference' in line:
                        rerun_flag = True
                if line.startswith('!') or line.startswith('*!'):
                    error_flag = True

                if error_flag:
                    errors.append(line)

            if not rerun_flag or errors:
                break

        # Copy pdf file
        file_list = [f for f in os.listdir(tmp_path) if f.lower().endswith('.pdf')]
        if file_list:
            pdf_file = os.path.join(tmp_path, file_list[0])
            if output_file:
                shutil.copyfile(pdf_file, output_file)

    return not errors, errors, warnings


def inject_latex_command(text: str, command: str) -> str:
    lines = text.splitlines()

    last_package_index = -1
    for i, line in enumerate(lines):
        if line.strip().startswith("\\usepackage"):
            last_package_index = i

    if last_package_index != -1:
        lines.insert(last_package_index + 1, f"\n{command}\n")
    else:
        lines.append(f"\n{command}\n")

    return '\n'.join(lines)
