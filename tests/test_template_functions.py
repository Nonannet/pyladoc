import pyladoc


def test_inject_to_template_html():
    template = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title><!--TITLE--></title>
    </head>
    <!-- some comment -->
    <body>
        <!--CONTENT-->
    </body>
    </html>
    """

    content = "Hello, World!"
    title = "Test Title"

    result = pyladoc.inject_to_template({'CONTENT': content, 'TITLE': title}, template_string=template)

    print(result)

    assert "Hello, World!" in result
    assert "<!-- some comment -->" in result  # Keep unrelated HTML comments
    assert "<title>Test Title</title>" in result


def test_inject_to_template_latex():
    template = """
\\documentclass[a4paper,12pt]{article}

% Packages
\\usepackage[utf8]{inputenc}
\\usepackage[T1]{fontenc}
\\usepackage{lmodern}  % Load Latin Modern font
\\usepackage{graphicx} % For including images
\\usepackage{amsmath}  % For mathematical symbols
\\usepackage{amssymb}  % For additional symbols
\\usepackage{hyperref} % For hyperlinks
\\usepackage{caption}  % For customizing captions
\\usepackage{geometry} % To set margins
\\usepackage{natbib}   % For citations
\\usepackage{float}    % For fixing figure positions
\\usepackage{siunitx}  % For scientific units
\\usepackage{booktabs} % For professional-looking tables
\\usepackage{pgf} % For using pgf grafics
\\usepackage{textcomp, gensymb} % provides \\degree symbol

\\sisetup{
  table-align-text-post = false
}

% Geometry Settings
\\geometry{margin=1in} % 1-inch margins

% Title and Author Information
\\title{<!--PROJECT-->}
<!--AUTHOR-->
\\date{\\today}

\begin{document}

% Title Page
\\maketitle

% <!--CONTENT-->
\\end{document}
    """

    content = "Hello, World!"
    project_name = "Test Project"
    author_name = "Otto"

    result = pyladoc.inject_to_template(
        {'CONTENT': content, 'PROJECT': project_name, 'AUTHOR': author_name},
        template_string=template)

    print(result)

    assert "\nOtto\n" in result
    assert "\\title{Test Project}\n" in result
    assert "Hello, World!" in result
