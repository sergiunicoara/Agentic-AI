from linefmt import parse_line


def test_simple_comma_separated_line():
    assert parse_line("a,b,c") == ["a", "b", "c"]
