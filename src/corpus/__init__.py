"""Learning from what editors actually did.

A conference pulled from Indico is a set of triples: what the author submitted,
what the editors produced, and the codes the editors chose to describe the
difference. That is the evidence this project has never had for deciding which
checks belong in the automatic tier.

Step one is not measurement — it is knowing what the corpus contains. A
precision figure computed over four comparable papers is worse than no figure,
because it looks like evidence. :mod:`~src.corpus.index` answers "what is
actually in here, and what can honestly be measured with it" before anything
draws a conclusion from it.
"""
