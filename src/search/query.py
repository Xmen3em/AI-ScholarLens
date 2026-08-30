"""Building the BM25 query for the paper index."""

from typing import Any, Dict, List, Optional, Sequence

# Boosts, in the order a reader of a search result cares about them. A title match
# is the strongest signal a paper is about the query; the abstract is the author's
# own summary; an author match is usually someone searching by name, which the
# fuzzy text query would otherwise score below an incidental abstract mention.
DEFAULT_SEARCH_FIELDS: Sequence[str] = ("title^3", "abstract^2", "authors^1")

# Returned to the caller. raw_text is deliberately absent: the documents average
# 70k characters, and nothing in a result list displays them.
SOURCE_FIELDS: Sequence[str] = ("arxiv_id", "title", "authors", "abstract", "categories", "published_date", "pdf_url")

_HIGHLIGHT_TAGS = {"pre_tags": ["<mark>"], "post_tags": ["</mark>"]}


class PaperQuery:
    """One search request, as the body OpenSearch expects.

    Kept apart from the service that runs it so the query can be asserted on
    directly — a boost or a filter that silently stopped being applied is
    invisible in a result list but obvious in the body.
    """

    def __init__(
        self,
        query: str,
        *,
        size: int = 10,
        offset: int = 0,
        categories: Optional[Sequence[str]] = None,
        newest_first: bool = False,
    ):
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
            # Without this OpenSearch stops counting at 10,000 and the last page of
            # a paginated result set reports a total it cannot reach.
            "track_total_hits": True,
            "_source": list(SOURCE_FIELDS),
            "highlight": self._highlight(),
        }
        sort = self._sort()
        if sort:
            body["sort"] = sort
        return body

    def _match(self) -> Dict[str, Any]:
        clause: Dict[str, Any] = {"must": [self._text_query()]}
        if self.categories:
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
                "fields": list(DEFAULT_SEARCH_FIELDS),
                # best_fields, not cross_fields: a paper whose title alone matches the
                # whole query is a better hit than one that spreads the terms across
                # three fields, and the 3x title boost only means something if the
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

    def _highlight(self) -> Dict[str, Any]:
        return {
            "fields": {
                # Whole field for title and authors: a truncated title is worse than
                # no highlight at all. The abstract gets fragments because it is long.
                "title": {"number_of_fragments": 0, **_HIGHLIGHT_TAGS},
                "authors": {"number_of_fragments": 0, **_HIGHLIGHT_TAGS},
                "abstract": {"fragment_size": 150, "number_of_fragments": 3, **_HIGHLIGHT_TAGS},
            },
            # The boosted field list and the highlighted field list are the same three
            # fields, but require_field_match would drop a highlight whenever the match
            # came from a different one.
            "require_field_match": False,
        }

    def _sort(self) -> Optional[List[Any]]:
        """Sort order, or None to let BM25 rank.

        Date-sorted results keep ``_score`` as the tiebreaker so papers submitted the
        same day still come back most-relevant-first.
        """
        if self.newest_first or not self.query.strip():
            return [{"published_date": {"order": "desc"}}, "_score"]
        return None
