import pyladoc


def test_inject_to_template():
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
    assert "<title>Test Title</title>" in result
