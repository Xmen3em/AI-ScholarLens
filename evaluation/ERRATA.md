# Frozen benchmark v1 review notes

The `undo-results` review note hypothesized a 58-word numeric sentence. Counting
the actual stored sentence gives **50 whitespace-separated words**. It passes the
seven-to-55-word filter and appears in the offered candidates. Literal answers
cover both percentages; paraphrased answers abstain at the lexical gate. This
correction changes no question, expected fact, answerability label, locator, or
scoring formula. The frozen benchmark is retained unchanged for hash verification.

The v1 support locators are non-exhaustive. Post-collection inspection found
additional useful evidence in UndoBench's introduction (section 3, chunk 2),
Kandinsky's introduction (section 3, chunk 1), its overview (section 23, chunk 0),
and the tokenizer paper's abstract/background/conclusion (sections 2/5/16, chunk 0).
These findings are recorded separately in `retrieval_adjudications.v1.json`.
Primary v1 metrics retain the predeclared judgments. Do not interpret every
judged-support miss as absence of relevant evidence or silently replace v1 scores
with scores using judgments expanded after observing retrieval output.
