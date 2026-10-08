"""Building the BM25 query, for whichever index is being searched."""

from dataclasses import dataclass, replace
from typing import Any, Dict, List, Optional, Sequence, Tuple

from src.search.indices import CHUNK_ALIAS, PAPER_ALIAS

_HIGHLIGHT_TAGS = {"pre_tags": ["<mark>"], "post_tags": ["</mark>"]}

# Passages returned per paper. One is too few to ground an answer that needs a claim and
# its evidence; unbounded returns forty pieces of whichever paper repeats the query most,
# which is what this corpus actually did — ten of ten results for "RAG" came from a
# single paper out of 172 matching passages across 34.
MAX_PASSAGES_PER_PAPER = 3


@dataclass(frozen=True)
class QueryProfile:
    """Everything that differs between searching papers and searching passages.

    The query *shape* is the same for both — a fuzzy multi-match, a category filter,
    pagination, highlighting — so it lives in one place and the fields it applies to
    are data.
    """

    alias: str
    # Searched, with boosts.
    fields: Tuple[str, ...]
    # Returned. Never the full document text: papers average 70k characters.
    source: Tuple[str, ...]
    highlight: Dict[str, Any]
    # Group results by this field, returning up to MAX_PASSAGES_PER_PAPER per group.
    # None leaves results flat, which is what one-document-per-paper indices want.
    collapse_field: Optional[str] = None
    # The fields each grouped passage carries, when collapsing.
    passage_source: Tuple[str, ...] = ()


# Boosts in the order a reader of a result cares about them. A title match is the
# strongest signal a paper is *about* the query; the abstract is the author's own
# summary; an author match is usually someone searching by name, which the fuzzy
# text query would otherwise rank below an incidental abstract mention.
PAPER_PROFILE = QueryProfile(
    alias=PAPER_ALIAS,
    fields=("title^3", "abstract^2", "authors^1"),
    source=("arxiv_id", "title", "authors", "abstract", "categories", "published_date", "pdf_url"),
    highlight={
        # Whole field for title and authors: a truncated title is worse than no
        # highlight at all. The abstract gets fragments because it is long.
        "title": {"number_of_fragments": 0, **_HIGHLIGHT_TAGS},
        "authors": {"number_of_fragments": 0, **_HIGHLIGHT_TAGS},
        "abstract": {"fragment_size": 150, "number_of_fragments": 3, **_HIGHLIGHT_TAGS},
    },
)

# The paper title is deliberately absent. Measured on this corpus, boosting it floods
# the results with a single paper — six hits collapsed to one distinct paper, because
# every one of its forty-odd chunks carries the same matching title. section_title
# earns its ^2: it lifts "F LIMITATIONS AND FUTURE WORK" into the top three for
# "limitations and future work", which content alone ranked fifth.
CHUNK_PROFILE = QueryProfile(
    alias=CHUNK_ALIAS,
    fields=("content^3", "section_title^2"),
    source=("arxiv_id", "title", "section_title", "section_index", "chunk_index", "content", "categories", "published_date"),
    highlight={"content": {"fragment_size": 200, "number_of_fragments": 3, **_HIGHLIGHT_TAGS}},
    collapse_field="arxiv_id",
    passage_source=("section_title", "section_index", "chunk_index", "content"),
)

# Hybrid fuses two rankings, and fusion needs a flat list of passages to rank: collapsed
# results are already grouped, and grouping before fusing would mean reconciling two
# different choices of which passages represent each paper. Hybrid therefore fetches flat
# candidates and groups once, after fusing.
CHUNK_CANDIDATE_PROFILE = replace(CHUNK_PROFILE, collapse_field=None)


class SearchQuery:
    """One search request, as the body OpenSearch expects.

    Kept apart from the service that runs it so the query can be asserted on
    directly — a boost or a filter that silently stopped being applied is invisible
    in a result list but obvious in the body.
    """

    def __init__(
        self,
        profile: QueryProfile,
        query: str,
        *,
        size: int = 10,
        offset: int = 0,
        categories: Optional[Sequence[str]] = None,
        newest_first: bool = False,
    ):
        self.profile = profile
        self.query = query
        self.size = size
        self.offset = offset
        self.categories = list(categories) if categories else []
        self.newest_first = newest_first

    def build(self) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "query": self._match(),
            "size": self.size,
            "from": self.offset,
            # Without this OpenSearch stops counting at 10,000 and the last page of a
            # paginated result set reports a total it cannot reach.
            "track_total_hits": True,
            "_source": list(self.profile.source),
            "highlight": {
                "fields": dict(self.profile.highlight),
                # require_field_match would drop a highlight whenever the match came
                # from a different field than the one being highlighted.
                "require_field_match": False,
            },
        }
        if self.profile.collapse_field:
            body["collapse"] = self._collapse()
        sort = self._sort()
        if sort:
            body["sort"] = sort
        return body

    def _collapse(self) -> Dict[str, Any]:
        """Group hits by the profile's field, carrying the best passages of each group.

        ``size`` then counts groups rather than documents, and ``inner_hits.total`` tells
        the caller how many passages the paper had matching, not just how many came back.
        """
        return {
            "field": self.profile.collapse_field,
            "inner_hits": {
                "name": "passages",
                "size": MAX_PASSAGES_PER_PAPER,
                "_source": list(self.profile.passage_source),
                "highlight": {"fields": dict(self.profile.highlight), "require_field_match": False},
            },
        }

    def _match(self) -> Dict[str, Any]:
        clause: Dict[str, Any] = {"must": [self._text_query()]}
        if self.categories:
            # A filter clause, not a query clause: a category must never contribute
            # to relevance, or filtering turns into searching.
            clause["filter"] = [{"terms": {"categories": self.categories}}]
        return {"bool": clause}

    def _text_query(self) -> Dict[str, Any]:
        """The scoring clause: a fuzzy multi-field match, or everything when the query is blank.

        A blank query is a browse, not a search — the filters and the date sort still
        apply, so it is the natural "latest papers in cs.CL" request.
        """
        if not self.query.strip():
            return {"match_all": {}}
        return {
            "multi_match": {
                "query": self.query,
                "fields": list(self.profile.fields),
                # best_fields, not cross_fields: a document whose strongest field
                # matches the whole query is a better hit than one that spreads the
                # terms across several, and a field boost only means something if the
                # best single field wins.
                "type": "best_fields",
                "operator": "or",
                # Covers the typos and the plural/singular misses a stemmer does not.
                # prefix_length 2 keeps the first two characters exact, which stops
                # short queries from matching most of the vocabulary.
                "fuzziness": "AUTO",
                "prefix_length": 2,
            }
        }

    def _sort(self) -> Optional[List[Any]]:
        """Sort order, or None to let BM25 rank.

        Date-sorted results keep ``_score`` as the tiebreaker so documents published
        the same day still come back most-relevant-first.
        """
        if self.newest_first or not self.query.strip():
            return [{"published_date": {"order": "desc"}}, "_score"]
        return None


def vector_query(profile: QueryProfile, vector: Sequence[float], *, size: int,
                 categories: Optional[Sequence[str]] = None) -> Dict[str, Any]:
    """Approximate-nearest-neighbour search over the embedding field.

    The category filter goes *inside* the knn clause rather than beside it. A filter
    applied afterwards would prune results the ANN search had already committed to,
    so a narrow filter would quietly return far fewer than the requested k; the lucene
    engine applies it during the graph walk instead.
    """
    knn: Dict[str, Any] = {"vector": list(vector), "k": size}
    if categories:
        knn["filter"] = {"terms": {"categories": list(categories)}}
    return {"size": size, "_source": list(profile.source), "query": {"knn": {"embedding": knn}}}
