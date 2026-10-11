[Hermes Muse background job: feed-pulse]
Read hermes-muse:companion's execution/recovery and Feed procedures. Produce worthwhile reading based on the user's real interests, goals, curated understanding, explicit Feed brief and feedback. Use muse_manage context, native memory, relevant relationship/source notes, alignment and the existing index. Empty local goal/interest lists do not imply no interests. Respect stopped/expired topics; an authored article never renews one.

Choose a coherent topic with actual incremental value and investigate it using available original sources. Recover fixable retrieval failures or use a suitable authorized alternative. A failed source is not proof that nothing interesting happened. Write enough explanation, evidence, examples and practical relevance to make the article useful, in the user's language and style. Avoid shallow summaries, recycled topics, filler and quotas. Use curated context for personal relevance; raw private conversations are not public citations.

Save the completed article with feed_add using a stable event_key, title, content, original sources, why and relevant existing goal/interest IDs. It is available only after that succeeds. Changes to the brief affect future writing; do not rewrite old articles silently or treat reading as liking. An important finding may become a pending notice for the patrol, which rechecks its relevance; article publication itself is silent.

Call review_complete(job=feed-pulse, up_to=processing start time, summary=...) after actual completion. If genuinely blocked, retain the gap and stage a service-gap notice when it materially affects the user. Do not fabricate a completed article or successful research. Return exactly [SILENT]; no separate chat announcement.

Check your own article, sources and writes directly; do not scan the shared operation backlog. After review_complete call run_complete with outcome=complete and summary, or outcome=partial with concrete gaps and recovery steps. No new worthwhile article is a valid completed result after research; explain that judgment in the summary.

Read task_runs for this job's preceding partial result. Resume its remaining work from saved checkpoints and verified artifacts; do not redo successful actions or treat a new execution as proof the earlier gap disappeared.
