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
tells a colleague who worked on a paper. When you work from the chief editor's
desk there is no name to type: your Indico account says who you are (see
*Joining* below).

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
now** asks Indico again — it only reads, and uses the token pasted into the
desk's Indico box.

### Several editors, one conference

The papers live on the chief editor's computer. Each editor runs the desk on
their own computer and **joins** the chief's desk over the office network. An
editor's desk never opens the chief's folder: it asks the chief's desk for a
paper, works on a copy, and sends the work back.

**Joining.** The chief's page has a box called **Editors on the network**
with an address and a join code. Start your desk with them, e.g.

    uv run python main.py --join 10.9.0.3:8770 --code vyq3-pt4d-8bew

There is no folder to choose: your desk keeps the papers you take by itself.
It remembers the address and code, so next time `uv run python main.py` (or
double-clicking the launcher) is enough.

**Your Indico account (once), instead of a name.** Your page asks for your
Indico token: in Indico, open *My profile → API tokens*, create a token with
the scope *read:everything*, and paste it into the box. The desk checks it
with Indico and keeps it on your computer only. From then on you are known by
your Indico account: the top of your page shows **Indico: *your name***, the
chief's page shows that name next to the papers you take, and they are
assigned to you in Indico. Only your Indico user id and name go to the chief's
desk, never the token. You cannot take a paper until the token is in.

**Only Indico's editors take papers.** Before giving you a paper, to edit or
to QA, the chief's desk checks that your Indico account is one of the
conference's *paper editors* (given the paper-editing permission directly or
through a group) or one of its *editing managers*. Paper editors are looked up
by the chief's desk. Indico shows the editing managers to nobody, so your own
desk asks Indico about your account, with your own token, and tells the
chief's desk the answer. Your token only ever goes to the Indico it was made
on. Event managers count as editing managers, as they do in Indico. If you are
neither, your page says so in red, the papers show *not an editor in Indico*
instead of a Take button, and the chief's page marks your desk the same way.
Ask the chief editor to add you in Indico; you can take papers within a minute
of that, with no restart. Your page says which you are once you are in.

**Taking a paper.** Your page lists the chief's papers under **Papers on the
chief editor's desk**, with what each one needs next:

- **To edit**: papers nobody has edited yet. **Take to edit** downloads a copy
  to your computer and opens it; you become its editor.
- **To QA**: papers another editor has finished, waiting for a second look.
  **Take for QA** opens a copy the same way; it does not make you its editor.
  You never QA a paper you edited (in any round): it shows *you edited it*
  instead, and another editor does its QA. Taking a paper to edit and giving
  it up untouched does not count as editing it.
- A paper whose QA failed is back under **To edit** as **Take to re-edit**,
  with the QA note saying what to fix.

Nobody else can take a paper while you have it, and the chief's page shows
who has it and what for. **Assigned to you** shows the papers the chief has
given you.

**A paper taken in Indico is taken here too.** If an editor assigns a paper to
themselves in Indico (or the chief assigns it there), nobody else can take it
on the desk to edit it. The list says *taken in Indico* and shows who has it;
anyone may still QA it. This holds whether or not the chief's desk writes to
Indico, and the desk reads Indico again just before it hands a paper out, so a
paper taken there a moment ago is not given to you as well. The editor Indico
shows can take it on the desk themselves. If it should be yours, ask the
chief: only the chief frees it. Giving a paper up on the desk gives it up in
Indico too, as far as the desk is concerned.

**Doing a QA.** A paper taken for QA has **QA passed** and **QA failed…** at
the bottom instead of **Finish this paper**. Check the editor's work (you can
fix small things yourself; your changes are sent as usual), then:

- **QA passed**: the paper is done. Nothing more is needed from the editors.
- **QA failed…**: say what needs fixing (required). The paper goes back to the
  editors to re-edit, with your note at the top of the page. Once it is
  finished again it comes back for QA. Every verdict is kept.

Either way the paper is sent to the chief's desk and given back.
**Give up this QA** frees it for someone else without a verdict.

**Your work goes back as you go.** A few seconds after each change, your desk
sends the paper's review files to the chief's desk. A green **Sent** in your
list means the chief has your latest work. **Not sent yet** means the chief's
desk could not be reached. Your work is safe on your computer and is sent
when the chief's desk answers. Only the review files go back; the author's
files are never changed.

**Finishing or giving up.** Finishing a paper (either choice) sends it one
last time and gives it back to the chief. If you cannot finish a paper, use
**Give up this paper** in the green box at the top, and say why if you like
(a conflict of interest, no time). Your work so far is sent first; the paper
is then free for another editor to take, with your work in it, and the
chief's page shows that you gave it up and why. You can still read your copy
until you next start the desk, which clears the papers you have given back:
the chief's desk has them. To change one again, **Take it again**: you get
the chief's latest version. A copy whose last changes never reached the
chief is never cleared.

**If the chief frees a paper you have.** Only the chief can take a paper away
from an editor (**Free** on the managing page). If they do, your desk says so
the next time it sends, and your copy, with any work not sent yet, stays on
your computer.

**You never need to open Indico.** The chief's desk keeps it in step: when
you take a paper, it assigns you in Indico; when you give a paper back
unfinished, it unassigns you; a finished paper stays assigned to you. And a
paper the chief assigns to you in Indico shows up as **Assigned to you** on
your desk within a couple of minutes.

**One desk per person.** An editor's desk never opens the chief's papers
folder: while the chief's desk is sharing it, any other desk started on that
folder stops and says how to join instead.

**The chief edits on an editor's desk too.** The chief's page is a managing
page: Indico, downloading and preparing papers, the sync, the editors' door,
who is editing what, and **Free** to take a paper back from an editor. It does
not edit papers.

**Who has each paper.** The managing page's **Taken by** column shows both ways
of taking a paper: *on this desk* (an editor took it here), *took it in Indico,
not on this desk*, both (the same person), or in red when one editor has it
here and Indico gives it to another. Until it is freed, nobody else can take a
paper either way. **Free** frees it from whoever has it:

- taken on the desk: their desk is told on its next send; their unsent work
  stays on their computer;
- taken in Indico, with *Keep Indico's editor assignments in step* on: they are
  unassigned in Indico (an unfinished paper);
- taken in Indico, with it off: the desk stops holding the paper for them, and
  the page reminds you, in red, that Indico still shows them, so you can
  unassign them there. If Indico later shows someone else, or the same person
  again after it showed nobody, the paper is held again.

The filters **Free to edit** and **Taken** count both kinds. **Edit papers**, at the top, opens the chief's own editing
desk in a new tab: an editor's desk like everyone's, joined to the chief's
desk, with its own settings in `~/.aiagent/editor`. Paste your Indico token
into it once, as any editor does (it never uses the managing page's token, nor
`INDICO_TOKEN` or the keyring on that computer). Like every editor, the chief
must be a paper editor or an editing manager in Indico to take papers there.
It closes when the managing desk closes. Started by hand instead (`uv run python main.py --join 127.0.0.1
--code …` on the chief's computer), it is the same desk, and **Edit papers**
finds it.

**Setting it up** (once):

1. *The chief editor* starts the desk with `--manage` (add `--no-share` to
   keep the door to this computer, i.e. only their own editing desk) and
   connects their Indico account in the managing page (a token with the *full:everything* scope, so
   the desk can assign editors). Then, in the same box, switch on **Keep
   Indico's editor assignments in step** for the conference. It is off until
   switched on, and is remembered per conference. While it is off nothing is
   sent to Indico, and the managing page says so next to papers being
   edited. Switching it on assigns those papers' editors too. Assigning editors sends no
   email; Indico writes each change to the event's log. The desk reads
   Indico's assignments every two minutes. The chief's computer
   must stay on and awake while the others work, and should be backed up
   (Time Machine is enough), because it holds everyone's work. Each time an
   editor's work arrives, the chief's desk keeps a copy of what it replaced
   (`.pool_backups/` in the papers folder, the last five per paper). The
   first time, macOS may ask whether Python may accept incoming connections:
   allow it.
2. *Each editor's computer* needs the tool installed, and TeX if LaTeX papers
   are to get a PDF when finished. Editors must be in the event's paper
   editing team in Indico, or be its editing managers (the chief too, to
   edit): the chief's desk lets nobody else take papers.

The chief editor can prepare new papers on the managing page while the
others work: preparing leaves alone any paper someone has taken.

### "Not prepared yet"

The tool has to read a paper once before you can review it. That takes a few
seconds. Press **Prepare them now** and go and make coffee; you only ever do
this once per paper.

### Preparing again

When the agent has improved (better reference rules, say), papers prepared
earlier do not change by themselves. The list says how many were prepared by an
older version, and **Prepare all again…** reads them again with the agent as it
is now. On the chief editor's desk it is on the managing page; an editor joined
to the chief's desk does not have it, because papers are prepared on the
chief's.

Before anything happens it tells you how many papers it will prepare and which
it leaves alone:

- **papers an editor is working on**, so nobody's files change under them (a
  paper taken while the run is going is left alone too, and nobody can take a
  paper while it is being prepared);
- **finished papers** and papers sent back to the author, whose reviewed files
  and letters are already written.

Your work is kept: decisions, notes, your wording, hand edits, the references
you wrote yourself, the title and author check. A decision follows the
suggestion it was about, even when that suggestion has a new number. If a
suggestion has changed or gone, the decision on it is dropped, and the paper
says so at the top (*Prepared again … 1 earlier decision no longer applies*),
listing what you had decided, so you can look at the new suggestion in its place.

---

## Working on one paper

A paper has four tabs, in the order you work through it. The number on each tab
is what is still waiting for you there; <kbd>1</kbd>–<kbd>4</kbd> switch tabs.
The address in the browser follows you, so reloading the page comes back to the
same paper and tab.

### 1. Title & authors

For a conference pulled from Indico. The proceedings' table of contents,
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

**The email.** The tab drafts an email to the author saying what does not
match, and the title and author list the paper will be published with if they
do not reply within 48 hours. Change anything you like in the box (your wording
is kept with the paper), then:

- **Open in my mail program** opens a new message with the subject and text
  filled in; add the author's address and send it from there. Or **Copy** it
  into a comment on the paper in Indico, which notifies the submitter. The desk
  sends nothing itself.
- Press **I've sent it**.

**Setting the paper aside.** Once the email is sent, the tab asks whether to
**set the paper aside until the author replies**. The paper stays yours (nobody
else can take it), but it leaves *Still to do* on your list and *Open the next
paper* skips it. On the list it shows *Set aside until …*, and the filter
**Set aside** shows all of them. When the deadline passes it says *the wait is
over*. **Take it up again** at the top of the paper brings it back at any time,
and answering for the author (*agreed*, *replied otherwise*, *Apply the
changes*) does so too. Choose **Keep working on it** to go on with the
references and the paper meanwhile.

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

Below that, **Title and author formatting in the paper** lists the changes to
how the title and the names are written in the paper itself (sentence case,
initials), with the same buttons as everywhere else.

### 2. References

Every reference, one row each: **as the author wrote it on the left, and what
it becomes in Appendix B's layout on the right**, with the words that change
marked on both sides. The colour of the row says how sure the desk is:

- **Green** — rewritten in the layout, nothing missing. Accept it, edit it, or
  keep the author's.
- **Red** — something the desk cannot put right by itself: a part Appendix B
  requires that no registry had (it is named, never invented), a reference
  whose kind it could not tell, a DOI that points elsewhere. Edit it yourself,
  or leave it for the author (it goes into the letter).
- **Grey** — already in the layout.

What the right-hand side shows depends on the paper:

- a `\bibitem` paper: the reference as LaTeX, ready to go into the source;
- a Word paper: the reference as text; what you accept becomes a tracked change;
- a `.bib` paper: the entry with the fields the JACoW bibliography style needs,
  and under it **Prints as**, the reference as it will appear in the paper.
  What you accept goes into the reviewed `.bib`.

Under each row: what is missing, any problem found, what was changed, and where
values came from (Crossref, refs.jacow.org, …).

- **Accept** / **Keep as submitted** — as everywhere; **change** thinks again.
- **Edit…** — write the reference yourself (the box starts from the suggestion).
  Your version replaces the whole reference, whatever was suggested; **Drop my
  version** takes it back out.
- **Accept all N green** accepts every green suggestion still to decide.
- The filters show only what is **To decide**, **Fixed**, **Problems** or
  **Already right**.
- Keyboard: <kbd>a</kbd> accept, <kbd>r</kbd> keep, <kbd>e</kbd> edit,
  <kbd>j</kbd>/<kbd>k</kbd> move.

*About the list as a whole* (folded at the top) has what concerns the list
rather than one reference: citation order, citations with no reference, the
bibliography style. If the list is not in the order the paper cites it, a card
there offers to reorder it.

### 3. The paper

Laid out like an online LaTeX editor: **the source on the left, and on the right
the list of changes to review, or the PDF**.

In the source every change is where it is:

- <del>red, struck through</del> followed by **green** — a suggestion still to
  decide. Click it and its card opens on the right.
- green, underlined — a correction that stands (made by the tool, or accepted).
  Hover to see what it was.
- orange — your own text.
- A blue line number has a suggestion to decide; a green one was corrected; an
  orange one you changed yourself; a red mark is a problem on that line.
- **Click any other text to edit its line.** Type your version and press
  *Save this line* (or <kbd>Enter</kbd>; <kbd>Esc</kbd> cancels). A line you
  changed has *Undo my change to this line*.
- The buttons jump to the **Title**, **Authors**, **Abstract**, **Body** or
  **References**; *Go to a section…* to any section. **Only changed lines**
  hides the rest; the search box finds a word.

The **Review** panel on the right:

- **To decide** — one card per suggestion: what would change, why JACoW wants
  it, before and after. **Accept**, **Keep as submitted**, or **Modify…** to
  accept it in your own words. *show in source* scrolls to it.
- **Decided** (folded) — everything you have answered; **change** on any card.
- **Corrected automatically** (folded) — the corrections the tool makes the
  same way every time, with no judgement involved, so it does not ask. If one
  is wrong for *this* paper — a megatesla read as a millitesla, say — press
  **Put back as submitted** and add a note. The reviewed file and the letter
  follow what you choose.
- **Problems**, sorted by who has to act: *only the author can fix these* (they
  go into the letter unless you tick them off), *for you to check*, and *for
  the record* (what the tool did, and checks that could not run — **NOT
  CHECKED** is a statement about the tool, never about the paper).
- **Lines you changed**, each with *undo this change*.

| Key | Does |
|---|---|
| <kbd>a</kbd> | Accept, and move to the next undecided card |
| <kbd>r</kbd> | Keep as submitted, and move on |
| <kbd>j</kbd> / <kbd>k</kbd> | Move down / up |
| <kbd>n</kbd> | Add a note to this card |

**Add a note** to any decision, especially when you reject something: in three
weeks, when the author writes back to argue, the note is the only reason you
will remember why.

The **PDF** panel shows the paper as it stands. **Recompile** builds it again
from your decisions, your wording and your lines (a few seconds); the list
above the PDF also offers the version with only the automatic corrections and
the author's own PDF, for comparison.

For a **Word** submission the text is edited in Word, so this tab lists the
changes beside the author's PDF — see *Word submissions* below.

### 4. Editor's panel

- **JACoW tags** — the editorial tags for this paper (TC12 for units, TC06 for
  references, TC14 for a DOI added, FC03 for `.bib` entries, …), proposed from
  what was actually corrected and what the author must fix, each with the
  reason. Tick or untick any of them, or tick another code. **Copy the codes**
  puts them on the clipboard for Indico — the desk does not write tags to
  Indico itself. The QA tags are the editing service's and are not offered.
- **Letter to the author** — written for you from your decisions, the problems
  only the author can fix and your notes. Edit it and press **Save my
  wording**; **Open in my mail program** or **Copy** to send it; **Start again
  from the automatic version** regenerates it after you have changed a lot.
- **Something you found yourself** — anything the tool does not check (an
  unreadable figure, a table off the page). Leave **Tell the author** ticked
  and it appears in the letter. A box below takes a note about the paper as a
  whole, added to the end of the letter.
- **Files** — everything the tool wrote, with **Open**: the corrected PDF, the
  author's original PDF, the Word file with tracked changes, the letter once
  you have finished. Nothing the author sent is ever changed; every file the
  tool writes sits in a folder called `aiagent_prescreen` next to theirs.

---

## Finishing a paper

Press **Finish this paper** at the bottom right. You are asked which of two
things is true:

- **Finished — ready for the proceedings.** Nothing more is needed from the
  author.
- **Send back to the author.** The letter lists what they must fix.

Then the tool writes your reviewed paper (and, for a `.bib` paper, the reviewed
`.bib` as `..._final.bib`), the letter, and a summary of everything you decided,
with the tags you chose. Finishing also stops marking the paper as yours, so a
colleague can pick it up. You can reopen a finished paper at any time.

**Open the next paper** takes you straight to the next one that is not
finished, so you can work down a conference without going back to the list.
It skips papers another editor has in Indico, and papers you have set aside.

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
No. Each paper keeps its own record, including whose name is on it. A paper
taken from the chief's desk is yours until you finish it or give it back;
nobody else can take it meanwhile (see *Several editors, one conference*).
Take your papers in Indico so you do not both want the same one.

**My name has gone from the box at the top.**
Your name is kept on your computer rather than in the papers folder, so a
desk that joined the chief's for the first time, or a new computer, asks
again. Type it once more; it stays.

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
That is expected — it only checks a fixed list of things. Add it under
*Something you found yourself* on the editor's panel and it goes to the author.

**The tool corrected something automatically and it is wrong.**
Open *Corrected automatically* in the review panel of *The paper* (or find the
reference on *References*) and press **Put back as submitted** on it. Add a note saying what was wrong — that note
is how a bad rule gets found and moved out of the automatic list.

**Why did it not just fix everything?**
Because a wrong automatic change costs you more time than no change at all. The
tool applies only the corrections that are mechanically safe and asks about
everything else. If you find yourself accepting the same kind of suggestion
every single time, say so — that is a candidate for moving into the automatic
list.
