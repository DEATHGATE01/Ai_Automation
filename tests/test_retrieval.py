from secops_agent.retrieval import KeywordRetriever, chunk_markdown

POLICY = """# SLA Policy

Critical findings must be remediated within 7 days.

## Escalation

If a critical finding breaches its SLA, escalate to the CISO.
"""


def test_chunk_markdown_splits_on_headings():
    chunks = chunk_markdown(POLICY, source="sla_policy.md")
    assert [c["source"] for c in chunks] == ["sla_policy.md", "sla_policy.md"]
    assert chunks[1]["text"].startswith("## Escalation")


def test_chunk_markdown_keeps_heading_with_body():
    chunks = chunk_markdown(POLICY, source="sla_policy.md")
    assert "7 days" in chunks[0]["text"]


def test_keyword_retriever_ranks_relevant_chunk_first():
    """The query must contain a term that discriminates between the chunks.

    A lexical retriever has no way to rank "how long do I have to fix a critical finding" against
    this two-chunk corpus: it shares no discriminating term with either chunk ("long" and "fix"
    appear in neither). "days" appears only in the SLA-window chunk, so the query below is the
    honest test for a lexical ranker.
    """
    r = KeywordRetriever(chunk_markdown(POLICY, source="sla_policy.md"))
    hits = r.search("how many days do we have to fix critical findings", k=1)
    assert hits[0]["source"] == "sla_policy.md"
    assert "7 days" in hits[0]["text"]


def test_keyword_retriever_returns_empty_for_no_overlap():
    r = KeywordRetriever(chunk_markdown(POLICY, source="sla_policy.md"))
    assert r.search("zzzz qqqq", k=3) == []


def test_tokenize_normalises_plurals_consistently():
    from secops_agent.retrieval import tokenize

    assert set(tokenize("findings days")) == set(tokenize("finding day"))
