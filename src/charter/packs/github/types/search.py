"""Request schemas for GitHub's search endpoints.

Search is the one part of the REST API with its own rate limit — 30 requests per
minute for an authenticated caller, against 5,000 per hour for everything else —
and its own response shape, which wraps results in ``items`` rather than
returning a bare array.

It also has its own *depth* limit: only the first 1,000 matches of any query are
retrievable, whatever the ``total_count`` says. That is a rule spanning ``page``
and ``per_page``, so it is enforced here rather than discovered as a 422 on the
eleventh page of a walk.

API Reference: https://docs.github.com/en/rest/search/search
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional

from pydantic import Field, model_validator

from charter.packs.github.types.common import GitHubListRequest
from charter.types import Query

__all__ = [
    "SearchRequest",
    "SearchIssuesRequest",
    "SearchRepositoriesRequest",
    "SearchCodeRequest",
    "SearchCommitsRequest",
    "SearchUsersRequest",
    "CommitSearchSort",
    "UserSearchSort",
]


SearchOrder = Literal["asc", "desc"]

# GitHub serves at most this many matches per query, across all pages.
# https://docs.github.com/en/rest/search/search#about-search
MAX_SEARCH_RESULTS = 1000

IssueSearchSort = Literal[
    "comments",
    "reactions",
    "reactions-+1",
    "reactions--1",
    "reactions-smile",
    "reactions-thinking_face",
    "reactions-heart",
    "reactions-tada",
    "interactions",
    "created",
    "updated",
]

RepoSearchSort = Literal["stars", "forks", "help-wanted-issues", "updated"]


class SearchRequest(GitHubListRequest):
    """What both search endpoints share: the sort direction, and the depth cap.

    API Reference: https://docs.github.com/en/rest/search/search
    """

    order: Annotated[
        Optional[SearchOrder],
        Field(
            # GitHub applies `desc` to a request that omits this, and applying it
            # is the server's job. Carried on the field it went out on every
            # call, including the ones with no `sort` to order — a parameter
            # nobody asked for, on the pack's most-called read.
            None,
            description=(
                "Determines whether the first search result returned is the highest "
                "number of matches (`desc`) or lowest (`asc`). Ignored unless `sort` is "
                "provided. GitHub uses `desc` when this is absent."
            ),
        ),
        Query(),
    ]

    @model_validator(mode="after")
    def _within_the_thousand_result_window(self) -> SearchRequest:
        """Only the first 1,000 matches of a search are retrievable.

        ``total_count`` reports the true size of the match set, so a page-number
        walk over a large search has every reason to think there is more and
        keeps asking; GitHub answers 422 once ``page * per_page`` passes 1,000.
        Checking it here turns the end of the window into a local error that says
        what to do about it.
        """
        page = self.page or 1
        per_page = self.per_page or 30
        if page * per_page > MAX_SEARCH_RESULTS:
            raise ValueError(
                f"GitHub serves at most the first {MAX_SEARCH_RESULTS} matches of a "
                f"search, and page {page} at {per_page} per page is past that. Narrow "
                "the query with qualifiers — a date range, a repository, a label — "
                "rather than paging further."
            )
        return self


class SearchIssuesRequest(SearchRequest):
    """Search issues and pull requests across GitHub.

    API Reference: https://docs.github.com/en/rest/search/search#search-issues-and-pull-requests
    """

    q: Annotated[
        str,
        Field(
            ...,
            description=(
                "The query containing one or more search keywords and qualifiers, e.g. "
                "`repo:octocat/hello-world is:issue is:open label:bug`. Qualifiers "
                "narrow the search: `repo:`, `org:`, `author:`, `assignee:`, `is:open`, "
                "`is:closed`, `is:pr`, `is:issue`, `label:`, `created:>2024-01-01`."
            ),
        ),
        Query(),
    ]
    sort: Annotated[
        Optional[IssueSearchSort],
        Field(
            None,
            description=(
                "Sorts the results by the given field. Default: results are sorted by "
                "best match."
            ),
        ),
        Query(),
    ]
    advanced_search: Annotated[
        Optional[bool],
        Field(
            None,
            description=(
                "Set to true to use advanced search, which adds `AND`/`OR` keywords and "
                "nested parenthesised queries to the qualifier syntax."
            ),
        ),
        Query(),
    ]
    search_type: Annotated[
        Optional[Literal["semantic", "hybrid"]],
        Field(
            None,
            description=(
                "Which search algorithm to apply. `semantic` matches on meaning rather "
                "than keywords, `hybrid` combines both. Omit for a lexical search, "
                "which is the default."
            ),
        ),
        Query(),
    ]


class SearchRepositoriesRequest(SearchRequest):
    """Search repositories across GitHub.

    API Reference: https://docs.github.com/en/rest/search/search#search-repositories
    """

    q: Annotated[
        str,
        Field(
            ...,
            description=(
                "The query containing one or more search keywords and qualifiers, e.g. "
                "`tetris language:assembly stars:>100`. Qualifiers include `language:`, "
                "`stars:`, `forks:`, `topic:`, `org:`, `user:`, `license:`."
            ),
        ),
        Query(),
    ]
    sort: Annotated[
        Optional[RepoSearchSort],
        Field(
            None,
            description=(
                "Sorts the results by number of stars, forks, help-wanted issues, or "
                "how recently the items were updated. Default: best match."
            ),
        ),
        Query(),
    ]


class SearchCodeRequest(GitHubListRequest):
    """Search code across GitHub.

    This endpoint has limits the others do not, and an agent that does not know
    them loops against them:

    * only the **default branch** is indexed, and only files under **384 KB**
    * **10 requests per minute**, against 30 for the other search endpoints
    * at most **1,000 results** per query however large `total_count` reads
    * the query needs a real search term. `language:go` alone is rejected;
      `retry language:go` is not.

    `sort` and `order` are not offered: `sort` has one value, GitHub has marked it
    closing down, and `order` does nothing without it.

    API Reference: https://docs.github.com/en/rest/search/search#search-code
    """

    q: Annotated[
        str,
        Field(
            ...,
            description=(
                "The search query. Combine a term with qualifiers: "
                "'retry in:file language:python repo:owner/name'. Useful qualifiers "
                "are in:file, in:path, language:, repo:, org:, user:, path:, "
                "filename:, extension:, size:."
            ),
        ),
        Query(),
    ]


CommitSearchSort = Literal["author-date", "committer-date"]
"""How commit search orders its results. Absent, GitHub sorts by best match."""

UserSearchSort = Literal["followers", "repositories", "joined"]
"""How user search orders its results. Absent, GitHub sorts by best match."""


class SearchCommitsRequest(SearchRequest):
    """Search commits across GitHub by message, author, or repository.

    The way to find where a change was introduced when the repository is known
    and the commit is not — `repo:owner/name fix flaky test`, or
    `author:octocat merge` with a date qualifier.

    API Reference: https://docs.github.com/en/rest/search/search#search-commits
    """

    q: Annotated[
        str,
        Field(
            ...,
            description=(
                "The search query, with commit qualifiers: `repo:owner/name`, "
                "`author:LOGIN`, `committer-date:>2026-01-01`, `merge:false`. A bare "
                "term searches commit messages."
            ),
        ),
        Query(),
    ]
    sort: Annotated[
        Optional[CommitSearchSort],
        Field(
            None,
            description=(
                "Sorts the results by author or committer date. Absent, results come "
                "back by best match."
            ),
        ),
        Query(),
    ]


class SearchUsersRequest(SearchRequest):
    """Search users and organizations.

    GitHub notes that this endpoint sees only publicly visible users, whatever
    the token: "This endpoint does not accept authentication and will only
    include publicly visible users." Its GraphQL equivalent sees more.

    API Reference: https://docs.github.com/en/rest/search/search#search-users
    """

    q: Annotated[
        str,
        Field(
            ...,
            description=(
                "The search query, with user qualifiers: `type:org`, `location:berlin`, "
                "`language:rust`, `followers:>100`."
            ),
        ),
        Query(),
    ]
    sort: Annotated[
        Optional[UserSearchSort],
        Field(
            None,
            description=(
                "Sorts the results by number of followers or repositories, or by when "
                "the account joined. Absent, results come back by best match."
            ),
        ),
        Query(),
    ]
