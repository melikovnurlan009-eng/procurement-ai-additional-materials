# Current implementation

Release 1.0.0. Built around, not instead of, the user's existing procurement retriever.

Implemented here: public/private scenario separation; production-interface adapter; conventional and legal static arms; planned multi-search control; bounded adaptive planner/observer/controller; optional real-edge graph sidecar; bundle/passsage/answer silver judging; adjudication; scoring; cost and checkpoint guards; source-only alias proposals; shadow FTS indexes; reports and plot scripts.

Verified here: offline fixture end-to-end execution, real SQLite FTS5 shadow-index operations, dataset/schema integrity, metric and safety tests. See validation/TEST_REPORT.md.

Not executed here: the user's production SQLite/Qdrant engine, configured remote models, actual scenario retrieval, silver-label creation, independent answer-reference validation, static/adaptive comparisons or a corpus sufficiency audit. No new empirical improvement claim is made.

Integration assumption: the user's supplied architecture describes ChunkRetriever.search, search_two_lanes and load. Those interfaces are checked at runtime. Current live repository changes may require a small adapter adjustment.
