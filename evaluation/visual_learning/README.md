# Reviewed RAG method fixture

`rag-method.v1.json` is a curated offline teaching fixture for arXiv
[2005.11401v4](https://arxiv.org/abs/2005.11401v4), not model output and not an
independent human scientific evaluation. Source checked against the local
native extraction/PDF during implementation. The PDF SHA256 is
`23e3249e9a1e75418d82efecab0ea8c4d033b89c93742f63208d47ce01f21233`;
parser revision is `pdfium-5.14.0-v1`. CI needs only this small fixture.

Page2 Figure1 and page3 section2.1 describe retrieval/marginalization. Section2.4
continues onto page4 block `p4b0`: query encoder and BART generator update;
document encoder/index remain fixed. Page4 block `p4b1` describes precomputed
index construction. The preparation arrow is not a gradient/update arrow.
Training arrows describe affected parameters, not differentiability of top-K.

Short exact excerpts are **locators**, not a substitute for their full original
context; source links/pages remain available. The fixture has 25 quoted words
in total. No full PDF/extracted paper is committed. Arabic descriptions are
teaching paraphrases, not quotations. The diagram omits detailed beam decoding.

The three reviewed negative claims preserve observed failure modes: document
encoder updates, token/paragraph confusion and the wrong TQA-Wiki best-result
claim (Table1, page6; Sequence68.0 versus Token66.1, EM). Those table facts are
regression metadata, not a new general-purpose numeric parser/validator.

The first visual contract only renders source-checked catalog content. It does
not accept new free-form scientific wording or assert general-paper support.
Later model planning needs its own source/fact catalog and semantic review.

Run the focused fixture/contract tests with the Windows interpreter and a fresh
basetemp as documented in the visual specification. No inference is needed.
