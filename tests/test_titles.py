import pytest

from jobalert.titles import tidy_title


class TestTidyTitle:
    def test_removes_space_before_punctuation(self):
        assert tidy_title("Return defect eliminaiton , RBS") == "Return defect eliminaiton, RBS"

    def test_spaces_a_dash_used_as_a_separator(self):
        # "Manager- Return" has whitespace on one side only: it is a dash, not a hyphen.
        assert tidy_title("Product Manager- Return reduction") == "Product Manager - Return reduction"
        assert tidy_title("Senior Engineer -Water Supply") == "Senior Engineer - Water Supply"

    def test_leaves_compound_hyphens_alone(self):
        assert tidy_title("Full-Stack Developer") == "Full-Stack Developer"
        assert tidy_title("Front-End / Back-End Engineer") == "Front-End / Back-End Engineer"

    def test_collapses_runs_of_whitespace(self):
        assert tidy_title("Data    Engineer\n\tII") == "Data Engineer II"

    def test_strips_a_trailing_full_stop(self):
        assert tidy_title("Water Supply Modelling WSPro.") == "Water Supply Modelling WSPro"

    def test_keeps_an_ellipsis_intact(self):
        assert tidy_title("Engineer and more...") == "Engineer and more..."

    def test_strips_leading_and_trailing_separators(self):
        assert tidy_title("- Data Analyst |") == "Data Analyst"
        assert tidy_title(",Senior Engineer,") == "Senior Engineer"

    def test_never_corrects_spelling(self):
        # Silently rewriting an employer's wording is not ours to do.
        assert "eliminaiton" in tidy_title("Return defect eliminaiton")

    def test_preserves_case_and_content_words(self):
        assert tidy_title("SSC CGL Recruitment 2026") == "SSC CGL Recruitment 2026"

    def test_adds_a_missing_space_after_a_comma(self):
        assert tidy_title("Engineer,Chennai") == "Engineer, Chennai"

    def test_handles_empty_and_whitespace_only_input(self):
        assert tidy_title("") == ""
        assert tidy_title("   ") == ""
        assert tidy_title(None) == ""

    def test_is_idempotent(self):
        messy = "Product Manager- Return defect eliminaiton , RBS Return reduction."
        once = tidy_title(messy)
        assert tidy_title(once) == once

    def test_does_not_touch_decimals_or_versions(self):
        assert tidy_title("Engineer 2.5 Years Experience") == "Engineer 2.5 Years Experience"


class TestJobAppliesTheTidier:
    def test_every_job_gets_a_tidied_title_regardless_of_source(self):
        from tests.factories import make_job

        job = make_job(title="Product Manager- Return defect eliminaiton , RBS Return reduction.")
        assert job.title == "Product Manager - Return defect eliminaiton, RBS Return reduction"

    def test_tidying_does_not_destabilise_the_job_id(self):
        from tests.factories import make_job

        # Ids key off source and external id, so cosmetic changes must not move them.
        messy = make_job(external_id="9", title="Data   Engineer ,  II")
        clean = make_job(external_id="9", title="Data Engineer, II")
        assert messy.job_id == clean.job_id
