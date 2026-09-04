# Reviewing papers — a guide for editors

You do not need to know anything about programming, LaTeX or version control to
use this. If something here reads like it needs any of that, it is a bug in the
guide — tell whoever set the tool up.

---

## Starting

**Double-click `Start Review Desk`** — the `.command` file on a Mac, the `.bat`
file on Windows.

Two things happen: a black window appears (leave it alone), and a browser
window opens showing your papers. If the browser does not open by itself, copy
the address from the black window into your browser.

Put your name in the box at the top right. It goes on the letters you send and
tells a colleague who worked on a paper.

When you are done for the day, close the black window. Everything you have done
is saved as you go — there is no "save" button to forget.

---

## The list of papers

Every submission is one line. Six things per line:

| Column | What it means |
|---|---|
| **Paper** | The paper's number |
| **Title** | What it is about |
| **Status** | Not started · In progress · Waiting on author · Finished |
| **To decide** | How many changes are waiting for you |
| **Must fix** | Problems only the author can fix |
| **Your notes** | Things you spotted yourself |

Click a line to open the paper. The buttons above the list filter it — **Still
to do** is the useful one most days.

### "Not prepared yet"

The tool has to read a paper once before you can review it. That takes a few
seconds. Press **Prepare them now** and go and make coffee; you only ever do
this once per paper.

---

## Working on one paper

At the top you see four numbers:

- **already corrected** — the tool fixed these. You do not need to look at
  them, and they are listed under *Your decisions* only for the record. These
  are things like the spacing between a number and its unit: the same
  correction, made the same way, thousands of times, with no judgement
  involved.
- **need your decision** — this is your work.
- **must be fixed** — problems the tool will not touch, because fixing them
  needs something only the author has.
- **your notes & edits** — what you have added.

Then six tabs.

### Your decisions

One card per change. Each card says what would change, why JACoW wants it, and
shows the text before and after.

- **Accept** — make this change.
- **Keep as submitted** — leave the author's text exactly as it is.

Nothing is permanent. Press **change** on any card to think again.

You can also use the keyboard, which is much faster over forty papers:

| Key | Does |
|---|---|
| <kbd>a</kbd> | Accept, and move to the next undecided card |
| <kbd>r</kbd> | Keep as submitted, and move on |
| <kbd>j</kbd> / <kbd>k</kbd> | Move down / up |
| <kbd>n</kbd> | Add a note to this card |

**Add a note** to any decision. This is worth doing whenever you reject
something: in three weeks, when the author writes back to argue, the note is
the only reason you will remember why. Notes stay with the paper and go into
your review summary.

### Problems

Sorted by who has to act, which is the only sorting that matters:

- **Only the author can fix these** — a missing figure file, a bibliography
  file that is not in the submission, a paper that does not compile. These go
  into the letter automatically. Tick one off if you have dealt with it
  yourself and it should not be in the letter.
- **For you to check** — judgement calls, and checks the tool could not
  finish.
- **For the record** — what the tool did, and any check that could not run.
  Nothing to do.

If a problem says **NOT CHECKED**, the tool could not reach the service it
needed (usually because the computer is offline). That is a statement about the
tool, not about the paper. It never means "there is a problem here".

### Your notes

The tool only checks what it knows how to check. Everything else — an
unreadable figure, a claim in the abstract that is not in the paper, a table
that runs off the page — goes here.

Fill in what you found, roughly where, and how serious it is. Leave **Tell the
author** ticked and it appears in the letter; untick it to keep it as an
internal record only.

There is also a box at the bottom for a note about the paper as a whole, which
is added to the end of the letter.

### The paper

The paper as it stands, with your accepted corrections already in it.

- Green line numbers were corrected by the tool.
- Orange line numbers you changed yourself.
- **Click any line to edit it.** Type your version, press *Save this line*.
- The buttons above jump to the **Title**, the **Authors**, the **Body**, the
  **References**, or the **First change** — so you never have to scroll through
  the technical preamble at the top.
- **Only changed lines** hides everything you have not touched.
- The search box finds a word anywhere in the paper.

Your hand edits are listed under *Your notes*, where each has an **undo this
change** link.

For a **Word** submission the text is edited in Word, not here — see below.

### Letter to the author

A letter, written for you from your decisions and your notes. It lists what was
corrected for the author and what they still have to do.

Edit it however you like and press **Save my wording**. **Start again from the
automatic version** throws your edits away and regenerates it — useful after
you have changed a lot of decisions. **Copy to clipboard** puts it in an email.

### Files

Everything the tool wrote, with an **Open** button each. The useful ones:

- **The corrected paper (PDF)** — what the paper looks like with the automatic
  corrections in it.
- **The author's original PDF** — what they sent, for comparison.
- **Word file with tracked changes** — for Word submissions.
- **Letter to the author**, once you have finished the paper.

Nothing the author sent is ever changed. Every file the tool writes sits in a
folder called `aiagent_prescreen` next to their files.

---

## Finishing a paper

Press **Finish this paper** at the bottom right. You are asked which of two
things is true:

- **Finished — ready for the proceedings.** Nothing more is needed from the
  author.
- **Send back to the author.** The letter lists what they must fix.

Then the tool writes your reviewed paper, the letter, and a summary of
everything you decided. You can reopen a finished paper at any time — nothing
is locked.

**Open the next paper** takes you straight to the next one that is not
finished, so you can work down a conference without going back to the list.

---

## Word submissions

Word papers work the same way with one difference: you decide on the
corrections here, but the text itself is edited in Word.

When you finish the paper you get a Word file — `..._reviewed.docx` — that
contains **only the corrections you accepted**, as Word tracked changes. Open
it, and *Review → Accept / Reject* works on each one exactly as you would
expect. Rejecting in Word restores the author's words letter for letter.

The change author is written as `JACoW prescreen (RULE)`, so Word's reviewing
pane groups the changes by rule and you can accept a whole rule at once.

---

## Questions you might have

**Can I break anything?**
No. The tool never writes to the files the author sent. Every decision can be
changed, every hand edit can be undone, and a finished paper can be reopened.

**Two of us are reviewing the same conference. Is that a problem?**
Work on different papers and you are fine — each paper keeps its own record,
including whose name is on it. Two people on the *same* paper at the same time
will overwrite each other's last action, so agree who has which paper.

**I closed the browser by accident.**
Nothing is lost. Double-click the launcher again, or reload the page.

**The tool suggested something wrong.**
Press **Keep as submitted** and add a note saying what was wrong with it. Those
notes are the most useful thing you can give whoever maintains the tool: they
are how a bad rule gets found and switched off.

**Something in the paper is wrong and the tool said nothing.**
That is expected — it only checks a fixed list of things. Put it under *Your
notes* and it goes to the author.

**Why did it not just fix everything?**
Because a wrong automatic change costs you more time than no change at all. The
tool applies only the corrections that are mechanically safe and asks about
everything else. If you find yourself accepting the same kind of suggestion
every single time, say so — that is a candidate for moving into the automatic
list.
