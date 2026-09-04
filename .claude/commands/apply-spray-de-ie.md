# /apply-spray-de-ie - Spray-Apply the Germany/Ireland Backlog

Preset wrapper around `/apply`'s spray mode, scoped to the two markets where the candidate's domain-openness override applies (see CLAUDE.md's Deal-breakers section — Germany and Ireland accept Moderate/Weak Fit roles outside payments, as long as location/sponsorship gates are clean).

Run `/apply` with the following arguments, exactly as if the user had typed them:

```
--spray --from-rank --market germany,ireland
```

Any extra text the user passed to this command (e.g. `/apply-spray-de-ie --top 15` or `/apply-spray-de-ie --min-score 50`) is additional flags — append it after the arguments above rather than replacing them.
