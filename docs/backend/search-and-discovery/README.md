# Search and discovery

Search and discovery turn a query, a course pair, or a chosen course set into ordered course results.

## Query search

One query runs every match method a site serves: Exact code, Substring, Fuzzy search, and, on a site that serves the embedding features, Semantic. A site that serves no embedding features runs the three lexical methods. The merge keeps one entry per course with the methods that matched it. Merged results follow the configured tier order, with active courses before inactive ones. The same package answers the minimal catalogue the narrowing boxes filter locally and the id-or-code resolver that the other tabs use to turn a stored identity into a course. [Search](/docs/backend/search-and-discovery/search.md) describes the methods, their cutoffs, and the tier order.

## Comparing two courses

A comparison resolves two known inputs to exactly one represented course each and measures their stored chunk vectors. It reports five percentages and one verdict, and no language model runs for the request. A meter with no value is shown as Not available. [Comparison](/docs/backend/search-and-discovery/comparison.md) describes the meters, the overlap calibration, and the verdict order.

## Discovery from a course set

A discovery request carries a selected and a completed course set and chooses one of them as the basis. The next courses are the courses whose prerequisites that basis covers, and the prerequisite mode decides eligibility. On a site that serves the embedding features, the recommendations are the courses whose teaching text is closest to the basis, with near-duplicates of a basis course left out. [Next courses](/docs/backend/search-and-discovery/next-courses.md) and [Recommendations](/docs/backend/search-and-discovery/recommendations.md) describe the two lists, their coverage and relatedness values, and the recommendation configuration keys.

The match methods and the merge, the comparison arithmetic, and the candidate reads and ranking keys are described in [Search queries and merge](/docs/backend/search-and-discovery/search-queries.md), [Comparison arithmetic](/docs/backend/search-and-discovery/comparison-arithmetic.md), and [Coverage and ranking](/docs/backend/search-and-discovery/coverage-and-ranking.md).

The measurements behind the discovery and semantic paths are collected in [Recommendation experiments](/docs/experiments/recommendations/README.md) and [Search and translation experiments](/docs/experiments/search-and-translation/README.md).
