from linefmt import parse_line


def test_field_with_an_escaped_quote_keeps_the_embedded_quote_mark():
    line = '"She said ""hi"" to the customer",42'

    fields = parse_line(line)

    assert fields[0] == 'She said "hi" to the customer'
