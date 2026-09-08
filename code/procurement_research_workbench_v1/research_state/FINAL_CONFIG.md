# Operator's final experiment record

Status: NOT FROZEN. Fill this from actual execution, not proposed settings.

Record the external repository commit, SQLite backup hash, Qdrant snapshot/collection, embedding model version, actual production priors, static/adaptive configurations, prompt/code hashes, judge and generator resolved model IDs, request parameters, candidate/final budgets, scenario/requirement hashes, date and development selection criterion.

The supplied configs are runnable starting values, not experimentally selected winners. Model environment-variable names alone do not identify the model that answered. Model event logs record returned model IDs where the endpoint supplies them.

After this record is complete, execute `prw freeze`. Preserve it with the corresponding run outputs.
