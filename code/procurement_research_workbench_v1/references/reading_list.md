# Primary documentation and source provenance

The original system interface was reconstructed from the user-supplied `_section1_architecture.md` and associated project evidence. No access to the user's local database or Qdrant service is implied.

Official topic guides used in scenario authoring are listed in `source_registry.json`. They orient source selection; they are not an exhaustive legal answer key or proof of corpus availability.

Technical documentation:

- SQLite, FTS5 Extension, including `bm25()` and column weighting: https://www.sqlite.org/fts5.html
- OpenAI, Chat Completions API reference: https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create
- OpenAI, Structured Outputs documentation: https://platform.openai.com/docs/guides/structured-outputs
- SciPy, `scipy.optimize.milp`: https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html

The generic model transport uses JSON-object response mode plus local schema and quote validation. It does not claim every compatible service offers strict provider-enforced schemas. Native APIs need an explicit wrapper. Model availability and prices must be checked at execution time.

Research source for judging caution: Zheng et al. (2023), Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena, arXiv:2306.05685. Multiple judge calls and exact quote checks do not transform machine labels into expert legal ground truth.
