"""The one prompt used both to train the reference model and to run it.

Training and inference must see exactly the same text, or the fine-tuned
model is asked a question it never learned.  Keep every change here.
"""
from __future__ import annotations

import json

SYSTEM = """You format one bibliographic reference in the JACoW style (IEEE style as
applied in JACoW Annex B). Rules:
- Authors: initials and surname ("A. T. Alpha"), initials separated by spaces;
  two authors joined by "and"; three to six separated by commas with a comma
  before "and"; more than six as "A. T. Alpha et al.". Keep names the author
  listed before "et al.".
- Title in sentence case inside “ ”, followed by a comma; keep acronyms, units
  (GeV, MHz) and proper names as written.
- Conference papers: "in Proc. IPAC’23, Venice, Italy, May 2023, pp. 57-59."
  Unpublished: "presented at IPAC’14, …, unpublished." Submitted papers:
  "submitted for publication." — never name the journal.
- Journals: ISO 4 abbreviation, then "vol. N, no. N, p./pp. N, Mon. YYYY."
- DOIs at the end as "doi:10.…", never as a URL.
- Never add, remove or change a number, DOI, name or word unless it comes
  from the verified record given with the reference. If the record is absent,
  only reformat what is written.
Answer with the formatted reference only.
/no_think"""


def user_message(raw: str, record: dict | None = None) -> str:
    """The reference, and the verified record a lookup returned for it, if any."""
    text = f"Reference:\n{raw.strip()}"
    if record:
        kept = {k: v for k, v in record.items() if v and not str(k).startswith("_")}
        text += "\n\nVerified record (Crossref, DataCite or JACoW):\n" + json.dumps(
            kept, ensure_ascii=False, sort_keys=True)
    return text


def messages(raw: str, record: dict | None = None, answer: str | None = None) -> list[dict]:
    out = [{"role": "system", "content": SYSTEM},
           {"role": "user", "content": user_message(raw, record)}]
    if answer is not None:
        out.append({"role": "assistant", "content": answer.strip()})
    return out
