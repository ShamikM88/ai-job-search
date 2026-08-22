"""Guards for the job-posting cache spec.

`/rank` Step 2 and `/apply` Step 0 each independently do a full fetch of a job
posting's text - `/rank` to triage-score it, `/apply` to run the authoritative
Step 1 evaluation - so a job that goes through both commands gets the same URL
fetched twice for no reason (a posting's text is static once published, unlike
company research, which benefits from a refresh window). This cache lets the
second command reuse the first command's fetch instead of repeating it. These
are markdown specs (the spec IS the implementation), so these tests pin the
invariants that would break silently: that `/rank` writes the cache after a
successful fetch, and - the part most likely to be dropped in a future edit,
since it is easy to add the write half and forget the read half - that
`/apply` actually checks the cache before attempting its own fetch.
"""
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EVALUATION = REPO / ".claude" / "skills" / "job-application-assistant" / "04-job-evaluation.md"
RANK = REPO / ".claude" / "commands" / "rank.md"
APPLY = REPO / ".claude" / "commands" / "apply.md"
GITIGNORE = REPO / ".gitignore"


def _sections(text: str, marker: str) -> dict[str, str]:
    """Split a markdown spec into {heading: body} on a given '\\n<marker> ' prefix."""
    parts = text.split(f"\n{marker} ")
    result = {}
    for part in parts[1:]:
        heading, _, body = part.partition("\n")
        result[heading.strip()] = body
    return result


def _rank_step2() -> str:
    sections = _sections(RANK.read_text(encoding="utf-8"), "##")
    for heading, body in sections.items():
        if heading.startswith("Step 2: Batch-Fetch and Score"):
            return body
    return ""


def _apply_step0() -> str:
    sections = _sections(APPLY.read_text(encoding="utf-8"), "##")
    for heading, body in sections.items():
        if heading.startswith("Step 0: Parse Input"):
            return body
    return ""


class TestCacheDefinition(unittest.TestCase):
    def setUp(self):
        self.text = EVALUATION.read_text(encoding="utf-8")
        self.sections = _sections(self.text, "##")

    def test_evaluation_file_defines_the_cache_section(self):
        self.assertIn(
            "Job Posting Cache",
            self.sections,
            "04-job-evaluation.md must define a 'Job Posting Cache' section",
        )

    def test_cache_definition_specifies_location_and_no_ttl(self):
        body = self.sections.get("Job Posting Cache", "")
        self.assertIn("job_postings/", body, "cache section must name the storage directory")
        self.assertIn("fetched_date", body, "cache section must name the freshness field")
        self.assertIn(
            "No TTL",
            body,
            "cache section must explicitly state there is no TTL, unlike the Company Research Cache",
        )

    def test_cache_definition_excludes_scrape_time_caching(self):
        """Caching at /scrape time was considered and rejected - /scrape only
        does lightweight detail-fetches on promising candidates, never full
        posting bodies, and most scraped jobs never reach /rank or /apply."""
        body = self.sections.get("Job Posting Cache", "")
        self.assertRegex(
            body,
            r"not\*\*\s+cache at `/scrape`",
            "cache section must explicitly rule out caching at /scrape time",
        )

    def test_cache_definition_scopes_write_to_first_full_fetch(self):
        body = self.sections.get("Job Posting Cache", "")
        self.assertIn(
            "first full fetch",
            body,
            "cache section must scope the write to whichever command does the first full fetch",
        )

    def test_cache_schema_includes_posting_text(self):
        body = self.sections.get("Job Posting Cache", "")
        self.assertIn('"posting_text"', body, "cache schema must store the fetched posting text")
        self.assertIn('"url"', body, "cache schema must store the posting URL")


class TestRankWiring(unittest.TestCase):
    def test_step2_writes_cache_after_successful_fetch(self):
        step2 = _rank_step2()
        self.assertNotEqual(step2, "", "could not locate rank.md's Step 2")
        self.assertIn("job_postings/", step2, "Step 2 must reference the job posting cache path")
        self.assertRegex(
            step2,
            r"[Ww]rite the Job Posting Cache",
            "Step 2 must instruct agents to write the posting cache after a successful fetch",
        )

    def test_step2_skips_cache_write_for_expired_jobs(self):
        step2 = _rank_step2()
        self.assertIn(
            "expired",
            step2.split("write the Job Posting Cache", 1)[-1][:400]
            if "write the Job Posting Cache" in step2
            else "",
            "Step 2 must clarify the cache write is skipped for jobs marked expired",
        )


class TestApplyWiring(unittest.TestCase):
    def test_step0_checks_cache_before_fetching(self):
        step0 = _apply_step0()
        self.assertNotEqual(step0, "", "could not locate apply.md's Step 0")
        self.assertIn("job_postings/", step0, "Step 0 must reference the job posting cache path")
        self.assertRegex(
            step0,
            r"[Cc]heck the Job Posting Cache",
            "Step 0 must instruct checking the cache before fetching",
        )

    def test_step0_falls_back_to_fetch_only_on_cache_miss(self):
        step0 = _apply_step0()
        self.assertRegex(
            step0,
            r"cache miss|cache is empty",
            "Step 0 must only fetch fresh when the cache is empty for this job",
        )

    def test_step0_writes_cache_after_a_fresh_fetch(self):
        step0 = _apply_step0()
        self.assertRegex(
            step0,
            r"write `job_postings/",
            "Step 0 must write the cache after a fresh fetch, for jobs that skipped /rank",
        )

    def test_step0_still_requires_the_403_escalation_order(self):
        """Pre-existing rule (unrelated to this cache) that must survive."""
        step0 = _apply_step0()
        self.assertIn(
            "09-web-research.md",
            step0,
            "Step 0 must keep its existing escalation-order reference for 403s",
        )


class TestGitignore(unittest.TestCase):
    def test_job_postings_cache_is_gitignored(self):
        text = GITIGNORE.read_text(encoding="utf-8")
        self.assertIn(
            "job_postings/*.json",
            text,
            "job_postings/ cache files are personal search history, like company_research/",
        )


if __name__ == "__main__":
    unittest.main()
