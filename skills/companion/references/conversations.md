Use companion references/context.md: context/status are section directories. Follow collection cursors and conversation descriptors/body pages; an index is not reviewed evidence.

# Bounded conversation previews and complete evidence

`context(section=conversations,limit=25,cursor?)` returns descriptors, not transcript bodies. Follow all section cursors. A missing older promise or cancellation is not evidence that it never existed; use exact original references/native history when relevant.

For each incomplete tracked session call conversation_read with session_id, the exact descriptor revision and offset=next_offset. Read every returned chunk. Pages contain at most12,000 text characters and a bounded serialized payload; long messages retain message_offset/text_chars/truncated. Reading the tail first does not certify the gap: next_offset returns the first missing range when necessary. A changed revision returns current revision/next_offset, preserving only the exact unchanged prefix. You can request a fresh descriptor with session_id alone. Served hash/range metadata is not a copied transcript, semantic review or processing watermark.

Do not approve task-notice relevance from a partial preview. notification_review/preparation/finalization require complete served coverage of the current tracked conversations, then the model's judgment of intent, actual outcomes, later corrections and cancellation. Complete means evidence served, not that a model understood it or a user received/read a result. New messages/edited content invalidate relevance review; only exact unchanged prefixes retain served coverage, and all new/changed text must be read. Operation receipts retain their precise native lookup contracts for scope-specific verification. Missing/pruned history stays a gap.

Original signal batches and operation audit still require their own full frozen-snapshot traversal and continuous successful prefixes. No cap on total work is introduced; save partial progress at host limits and resume without skipping evidence or sources. Feed does not receive raw conversations. Do not add a polling job or replay unknown writes.
