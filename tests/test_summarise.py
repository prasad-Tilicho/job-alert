from jobalert.summarise import MAX_SUMMARY_LEN, summarise


class TestSummarise:
    def test_strips_html_and_entities(self):
        assert summarise("<p>We are <b>hiring</b> a Senior Engineer &amp; a designer today.</p>") == (
            "We are hiring a Senior Engineer & a designer today."
        )

    def test_collapses_whitespace(self):
        assert summarise("Line one.\n\n   Line two follows here for length.") == (
            "Line one. Line two follows here for length."
        )

    def test_returns_none_for_nothing_useful(self):
        assert summarise(None) is None
        assert summarise("") is None
        assert summarise("<p></p>") is None
        assert summarise("Too short") is None

    def test_drops_leading_boilerplate(self):
        text = summarise("Job Description: Build and maintain our payments platform end to end.")
        assert text.startswith("Build and maintain")

    def test_cuts_at_a_sentence_boundary_when_it_can(self):
        body = "First sentence is here. " + "Second sentence rambles on and on. " * 12
        result = summarise(body)
        assert result.endswith(".")
        assert len(result) <= MAX_SUMMARY_LEN + 1

    def test_falls_back_to_a_word_boundary(self):
        result = summarise("word " * 200)
        assert len(result) <= MAX_SUMMARY_LEN + len("...")
        assert result.endswith("...")
        assert not result.endswith(" ...")

    def test_respects_a_custom_limit(self):
        assert len(summarise("word " * 200, limit=60)) <= 63
