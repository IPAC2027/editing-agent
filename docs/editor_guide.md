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
tells a colleague who worked on a paper. It is kept on your own computer, so
when several editors open the same shared folder each of them is "you" on
their own screen.

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

### Who has each paper in Indico

When the folder was pulled from Indico, a seventh column, **In Indico**, says
who has each paper there: **You**, another editor's name, or **Not taken**.
For the desk to know which papers are yours, type your name at the top exactly
as Indico shows it — the box suggests the names it knows.

Indico gives each paper to one editor, but the desk works on copies, so nothing
here stops you opening a colleague's paper. Their lines are greyed out, the
paper itself says who has it, and **Open the next paper** passes over them.
**Yours** and **Not taken** above the list hide the rest. Take a paper in
Indico before you start on it, so nobody else does.

The list starts out as Indico was when the papers were pulled. **Check Indico
now** asks Indico again — it only reads, and needs the same token as pulling
(`INDICO_TOKEN`).

### Several editors, one folder

The papers can live on the chief editor's computer, shared over the office
network, with every editor running the desk on their own computer. Everyone
then sees the same papers and the same progress.

**Who is editing what.** Your first change to a paper — a decision, a note,
an edit — marks it as yours. The list then shows **You're editing** on that
line, and **Editing: *name*** to everyone else. Just opening a paper to look
at it marks nothing.

If you open a paper a colleague is editing, a yellow box at the top says who
and since when. You can read everything, but your changes are not saved — the
desk says so as soon as you try, and nothing of theirs is touched.

A paper stops being marked as yours when you **finish** it (either choice) or
press **Let it go** in the green box at the top. Nothing expires on its own:
you can keep a paper for days. If a colleague has gone home and left a paper
marked, **Take it over** in the yellow box moves it to you after asking you
to confirm. Their saved work stays; anything they try to change afterwards is
refused. Ask them first.

This is separate from Indico. Indico still decides whose paper it is — take
it there as usual. The marking here only stops two desks writing over each
other.

**Setting it up** (once, by whoever looks after the tool):

1. *On the chief editor's computer:* the papers folder (e.g. `NAPAC2025`) is
   shared — on a Mac, *System Settings → General → Sharing → File Sharing*,
   add the folder, and give the editors read and write access. That computer
   must stay on and awake while others are working, and should be backed up
   (Time Machine is enough): it holds everyone's work.
2. *On each editor's computer:* connect to the share — on a Mac, *Finder → Go
   → Connect to Server*, `smb://<chief's computer>.local`; on Windows, *File
   Explorer → This PC → Map network drive*. Then put the folder's path, as
   that computer sees it, on the first line of a file called
   `papers_folder.txt` next to `Start Review Desk` — for example
   `/Volumes/NAPAC2025` on a Mac or `Z:\` on Windows. The launcher opens that
   folder from then on, and says so plainly if the share is not connected.
3. Each editor's computer needs the tool installed, and TeX if LaTeX papers
   are to get a PDF when finished.

The chief editor can prepare new papers while the others work: preparing
leaves alone any paper someone is editing.

### "Not prepared yet"

The tool has to read a paper once before you can review it. That takes a few
seconds. Press **Prepare them now** and go and make coffee; you only ever do
this once per paper.

---

## Working on one paper

At the top you see four numbers:

- **already corrected** — the tool fixed these. You do not need to look at
  them. These are things like the spacing between a number and its unit: the
  same correction, made the same way, thousands of times, with no judgement
  involved. They are listed at the top of *Your decisions*, folded away, and
  **any one of them can be put back** — see below.
- **need your decision** — this is your work.
- **must be fixed** — problems the tool will not touch, because fixing them
  needs something only the author has.
- **your notes & edits** — what you have added.

Then six tabs.

### Your decisions

At the top is a folded line — *"8 corrections already applied"*. Open it and
you get one card per automatic correction: what it changed, where, and why.
Each has a **Put back as submitted** button.

You will not normally open this. But if the tool has done something that is
wrong for *this* paper — it read a megatesla as a millitesla, say — put it
back, and add a note saying why. The reviewed file, the Word file and the
letter to the author all follow what you choose: a correction you put back is
not mentioned to the author at all, so if they should still be told about it,
add it under *Your notes*. **change** or *apply it again* undoes the undo.

Below that, one card per change the tool wants you to decide. Each card says what would change, why JACoW wants it, and
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

### Title & authors

Only for a conference pulled from Indico. The proceedings' table of contents,
author index and DOI metadata come from Indico, so the paper's title and author
list have to match it. This tab compares them, ignoring capitals and
punctuation and matching "Y. Luo" with "Yun Luo".

Every paper gets a verdict, shown on the paper list, at the top of the paper
and in the tab:

| Label | Means |
|---|---|
| **✓ Author/title check done** | Title and authors match Indico. Nothing to do. |
| **Needs correction: email drafted** | They differ; the email to the author is ready in the tab. |
| **Waiting until …** / **No reply: ready to apply** | You sent the email; the 48 hours are running, or are up. |
| **Corrected; Indico changes to make** | Applied to the paper; tick off the Indico changes as you make them. |
| **✓ Author/title check done (corrected)** | Applied, and every Indico change is ticked off. |
| **Not checked** | The file is not a paper the desk can read (LaTeX pasted into Word, a file of references only). Compare by hand. |

When they differ, two rules decide what happens:

- **The title in the paper is the right one.** Indico's title is changed to it.
- **The author list becomes the combined list.** Anyone in the paper but not in
  Indico is added to Indico; anyone Indico lists as an author but the paper does
  not is added to the paper, with the affiliation Indico gives.

The tab drafts an email to the author saying what does not match, and the title
and author list the paper will be published with if they do not reply within 48
hours. Edit it if you like, paste it into
a comment on the paper in Indico (Indico tells the submitter) or send it by mail,
and press **I've sent it**. The desk sends nothing itself.

Then one of three things happens:

- **The author agrees** — press *The author agreed: apply now*.
- **The author replies otherwise** — press *The author replied otherwise* and
  follow their answer by hand; nothing is changed.
- **No reply** — after the deadline the paper says *No reply about the title and
  authors* and **Apply the changes** appears. The desk never applies anything
  before the time printed in the email.

Applying adds the missing authors to the paper in the reviewed files (a tracked
change in Word) and lists what to change in Indico — the title, and authors to
add there — with boxes to tick, because the desk does not change Indico for
you. **Undo the changes** takes them back out.

Press **Check Indico now** on the paper list before you send anything: it reads
each paper's authors with their roles and affiliations. Without it the tab says
so and compares against the names the pull recorded, which include speakers.
Only when the file itself cannot be read as a paper does it say *Not checked*
rather than guess.

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
everything you decided. Finishing also stops marking the paper as yours, so a
colleague can pick it up. You can reopen a finished paper at any time.

**Open the next paper** takes you straight to the next one that is not
finished, so you can work down a conference without going back to the list.
It skips papers another editor has in Indico.

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
No. Each paper keeps its own record, including whose name is on it. On a
shared folder, the first editor to change a paper has it until they finish or
let it go; anyone else can read it but not change it (see *Several editors,
one folder*). Take your papers in Indico so you do not both start on the same
one.

**My name has gone from the box at the top.**
Since the desk learned to work from a shared folder, your name is kept on your
computer rather than in the papers folder. Type it once more; it stays.

**I closed the browser by accident.**
Nothing is lost. Double-click the launcher again, or reload the page.

**The tool suggested something wrong.**
Press **Keep as submitted** and add a note saying what was wrong with it. Those
notes are the most useful thing you can give whoever maintains the tool: they
are how a bad rule gets found and switched off.

**There is a grey "model:" label at the top of the page. What is that?**
Whoever set the tool up has switched on a language model that runs on this
computer — nothing is sent anywhere. It helps with two things only: deciding
whether an unusual word in a reference title is a name or an ordinary word, and
hiding problems it judges to be false alarms (what it hid is listed under *For
the record*, so you can always see). It is never allowed to supply a fact — a
DOI, a year, a volume, a page range — and it cannot change anything the tool
corrects automatically. If the label is absent, the tool is running without it,
which is the normal setting.

**Something in the paper is wrong and the tool said nothing.**
That is expected — it only checks a fixed list of things. Put it under *Your
notes* and it goes to the author.

**The tool corrected something automatically and it is wrong.**
Open *"corrections already applied"* at the top of *Your decisions* and press
**Put back as submitted** on it. Add a note saying what was wrong — that note
is how a bad rule gets found and moved out of the automatic list.

**Why did it not just fix everything?**
Because a wrong automatic change costs you more time than no change at all. The
tool applies only the corrections that are mechanically safe and asks about
everything else. If you find yourself accepting the same kind of suggestion
every single time, say so — that is a candidate for moving into the automatic
list.
