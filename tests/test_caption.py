from datetime import date

from jobalert.caption import MAX_CAPTION_LEN, MAX_HASHTAGS, build_caption, hashtags_for
from jobalert.models import Category
from tests.factories import make_job

TODAY = date(2026, 9, 7)
HANDLE = "@dailyjobalerts"


def caption(**overrides) -> str:
    return build_caption(make_job(**overrides), handle=HANDLE, today=TODAY)


class TestBuildCaption:
    def test_leads_with_the_title_and_organisation(self):
        text = caption()
        assert "Assistant Section Officer" in text
        assert "Staff Selection Commission" in text

    def test_includes_location_salary_and_deadline(self):
        text = caption()
        assert "New Delhi, India" in text
        assert "Rs 44,900 - 1,42,400 per month" in text
        assert "15 Oct 2026" in text

    def test_omits_the_salary_line_entirely_when_unknown(self):
        text = caption(salary=None)
        assert "Salary" not in text

    def test_omits_the_deadline_line_when_unknown(self):
        text = caption(last_date=None)
        assert "Apply by" not in text

    def test_always_credits_the_source(self):
        # Adzuna and RemoteOK both require attribution in their terms.
        assert "Adzuna" in caption(source="adzuna")
        assert "RemoteOK" in caption(source="remoteok")

    def test_points_at_the_bio_because_captions_are_not_clickable(self):
        text = caption()
        assert "link in bio" in text.lower()
        assert HANDLE in text

    def test_never_exceeds_the_instagram_caption_limit(self):
        text = caption(title="Recruitment Notification " * 120, org="Department " * 60)
        assert len(text) <= MAX_CAPTION_LEN

    def test_attribution_and_hashtags_survive_truncation(self):
        text = caption(title="Very Long Title " * 200)
        assert "Adzuna" in text
        assert "#" in text

    def test_reads_the_same_way_for_the_same_job(self):
        assert caption() == caption()


class TestHashtags:
    def test_are_unique_lowercase_and_prefixed(self):
        tags = hashtags_for(make_job())
        assert len(tags) == len(set(tags))
        assert all(tag.startswith("#") and " " not in tag for tag in tags)

    def test_respect_the_instagram_limit(self):
        tags = hashtags_for(make_job(location="New Delhi, Mumbai, Chennai, Kolkata, Bengaluru"))
        assert len(tags) <= MAX_HASHTAGS

    def test_differ_by_category(self):
        gov = set(hashtags_for(make_job(category=Category.GOVERNMENT)))
        private = set(hashtags_for(make_job(category=Category.PRIVATE)))
        assert gov != private
        assert "#governmentjobs" in gov
        assert "#governmentjobs" not in private

    def test_include_a_tag_derived_from_the_location(self):
        assert "#delhijobs" in hashtags_for(make_job(location="New Delhi, Delhi"))

    def test_ignore_punctuation_in_location_names(self):
        tags = hashtags_for(make_job(location="Thiruvananthapuram (Kerala)"))
        assert all(tag.isascii() and tag[1:].isalnum() for tag in tags)


class TestAccentedLocations:
    def test_accents_fold_to_ascii_rather_than_vanishing(self):
        # Naive stripping turns "Dusseldorf" (with an umlaut) into "dsseldorf".
        tags = hashtags_for(make_job(location="Düsseldorf"))
        assert "#dusseldorfjobs" in tags

    def test_non_latin_locations_do_not_produce_empty_tags(self):
        tags = hashtags_for(make_job(location="बेंगलुरु"))
        assert all(len(tag) > 1 for tag in tags)


class TestEstimatedSalaryWording:
    def test_estimates_are_marked_in_the_caption(self):
        text = build_caption(
            make_job(salary="Rs 18.0L - 24.0L per year", salary_is_estimated=True),
            handle=HANDLE, today=TODAY,
        )
        assert "Salary (estimated)" in text

    def test_stated_salaries_are_not_hedged(self):
        text = build_caption(
            make_job(salary="Rs 18.0L - 24.0L per year", salary_is_estimated=False),
            handle=HANDLE, today=TODAY,
        )
        assert "Salary:" in text
        assert "estimated" not in text


class TestSourceNaming:
    def test_acronym_sources_are_not_title_cased(self):
        # A naive title-case turns "ssc" into "Ssc" on every poster footer.
        from jobalert.attribution import label_for

        assert label_for("ssc") == "SSC"
        assert label_for("remoteok") == "RemoteOK"


class TestDescriptionAndWindow:
    def test_includes_the_description_when_there_is_room(self):
        text = caption(description="Applications are invited for 500 posts across India.")
        assert "500 posts across India" in text

    def test_states_the_application_window_when_both_dates_are_known(self):
        from datetime import date as _date

        text = caption(start_date=_date(2026, 9, 2), last_date=_date(2026, 9, 22))
        assert "Apply between: 02 Sep 2026 and 22 Sep 2026" in text

    def test_falls_back_to_apply_by_with_only_a_closing_date(self):
        text = caption(start_date=None)
        assert "Apply by: 15 Oct 2026" in text

    def test_a_long_description_is_dropped_before_the_title_is_trimmed(self):
        # Attribution and hashtags are required; the description is not.
        text = build_caption(
            make_job(title="Assistant Section Officer", description="x " * 1500),
            handle=HANDLE, today=TODAY,
        )
        assert len(text) <= MAX_CAPTION_LEN
        assert "Assistant Section Officer" in text
        assert "Adzuna" in text
        assert "#" in text
