import pytest

from jobalert.poster.layout import fit_text, wrap_text


def fixed_width(char_width: float):
    """A measure function where every character is the same width."""
    return lambda text: len(text) * char_width


class TestWrapText:
    def test_wraps_on_word_boundaries(self):
        lines = wrap_text("one two three four", max_width=80, measure=fixed_width(10))
        assert lines == ["one two", "three", "four"]

    def test_returns_empty_list_for_blank_input(self):
        assert wrap_text("   ", max_width=100, measure=fixed_width(10)) == []

    def test_collapses_internal_whitespace(self):
        assert wrap_text("a\n\tb", max_width=1000, measure=fixed_width(10)) == ["a b"]

    def test_hard_breaks_a_word_too_long_to_fit(self):
        # No amount of wrapping helps here, so it must break mid-word rather than
        # silently overflow the poster.
        lines = wrap_text("abcdefghij", max_width=30, measure=fixed_width(10))
        assert lines == ["abc", "def", "ghi", "j"]

    def test_never_exceeds_max_width_for_breakable_text(self):
        text = "recruitment notification for assistant section officer"
        lines = wrap_text(text, max_width=200, measure=fixed_width(10))
        assert all(len(line) * 10 <= 200 for line in lines)

    def test_degenerate_max_width_does_not_hang(self):
        assert wrap_text("ab", max_width=0, measure=fixed_width(10)) == ["a", "b"]


class TestFitText:
    def measure_for(self, size: int):
        # Character width scales with the font size, as with a real font.
        return fixed_width(size)

    def test_picks_the_largest_size_that_fits(self):
        fitted = fit_text(
            "abcd",
            max_width=40,
            max_lines=1,
            sizes=range(1, 21),
            measure_for=self.measure_for,
        )
        assert fitted.size == 10
        assert fitted.lines == ["abcd"]
        assert fitted.truncated is False

    def test_uses_extra_lines_to_keep_a_bigger_size(self):
        fitted = fit_text(
            "abcd efgh",
            max_width=40,
            max_lines=2,
            sizes=range(1, 21),
            measure_for=self.measure_for,
        )
        assert fitted.size == 10
        assert fitted.lines == ["abcd", "efgh"]

    def test_falls_back_to_smallest_size_and_truncates_when_nothing_fits(self):
        fitted = fit_text(
            "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            max_width=10,
            max_lines=1,
            sizes=range(5, 21),
            measure_for=self.measure_for,
        )
        assert fitted.size == 5
        assert len(fitted.lines) == 1
        assert fitted.truncated is True
        assert fitted.lines[0].endswith("...")

    def test_blank_text_yields_no_lines(self):
        fitted = fit_text("", max_width=100, max_lines=2, sizes=range(5, 20), measure_for=self.measure_for)
        assert fitted.lines == []
        assert fitted.truncated is False

    def test_rejects_an_empty_size_range(self):
        with pytest.raises(ValueError):
            fit_text("x", max_width=10, max_lines=1, sizes=[], measure_for=self.measure_for)
