# Morning Brief

A small demo of an AI team that does the first pass of a business owner's morning, and a reviewer that checks every output before a human sees it.

The business is fictional (Hartwell Roofing & Gutters, Dallas). All data is mock. No client information is used anywhere.

## The problem

An owner starts the day with new leads to sort, yesterday's calls to remember, and follow-ups to write. Agents can do the first pass in minutes. Someone still has to check every output before it reaches a customer, because an email with the wrong price costs more than the time it saved.

## What it does

Three agents run overnight:

| Agent | Job |
| --- | --- |
| Lead sorter | Sorts inquiries into urgent, quote request, not ready, not a fit, or spam |
| Call summarizer | Summarizes each call, records quoted prices and the promises the rep made |
| Follow-up drafter | Drafts a reply to every urgent and quote-request lead, with a proposed visit time |

Then a reviewer checks all ten outputs (6 drafts, 4 call summaries) and writes a plain-English update for the owner: what is done, what is next, what needs a decision.

The reviewer checks:

- Every dollar amount against the current price list
- No template fields left in the text (`{first_name}`)
- Proposed visits fall inside business hours
- No promises the business has not approved
- The greeting and address match the lead record
- No credentials in any output
- For call summaries: every amount was actually said, and quoted prices match the price list

When a fix is safe, it proposes one and checks the fixed version again. When the right answer is a business decision, it asks the owner instead.

## Try it

Open `docs/index.html` in a browser, or publish the `docs` folder with GitHub Pages. In the page you can read each agent's output, see what the reviewer caught, apply a fix, make a decision, and approve. Nothing is sent anywhere.

To run the pipeline yourself (Python 3.10 or newer, standard library only):

```bash
python3 run_brief.py                     # run the brief, write output/
python3 run_brief.py --no-seeded-faults  # same agents without the planted mistakes
python3 -m unittest discover -v          # run the tests
python3 build_page.py                    # rebuild docs/index.html from output/brief.json
```

## What is real and what is simulated

- The agents are plain scripts so the demo runs offline with no API key. In a real client build, a model call goes where the templates are.
- Four agent mistakes are planted on purpose, each one a failure real agents make:
  1. A stale cached price (gutter guards at $1,650 instead of $1,850)
  2. A `{first_name}` placeholder left in when a lead has no personal name
  3. A Sunday visit offered to someone who said "weekend", when the business is closed Sundays
  4. A promise of same-day repair that the business does not make
- The reviewer is independent code. It checks against the business's own price list and hours (`data/business.json`), never against the agent's cache.
- One flag comes from the data, not from a planted fault: on Monday's call the rep quoted the old gutter guard price. The reviewer cannot decide whether to honor it, so it asks the owner.
- With `--no-seeded-faults`, the drafts produce zero findings. That guards against a reviewer that flags everything.

## Credential habits

- No keys, passwords or tokens in code, data or the page.
- `.env` is git-ignored. `.env.example` lists variable names with empty values.
- The reviewer blocks any output containing something shaped like a key or password.
- `tests/test_repo_hygiene.py` scans every file in the repository for secret-shaped strings.

## How this would be measured at a real client

- Drafts approved with no edits, as a share of all drafts
- Errors caught before send, and errors that got through
- Minutes from a new lead to the first reply
- Minutes the owner spends reviewing each morning

## Turning it into a real build

1. Replace the templates in `brief/followups.py` and the extraction in `brief/calls.py` with model calls. Keep the prompts in files, and load the API key from the environment.
2. Keep `brief/reviewer.py` as it is. Its checks do not depend on which model wrote the text.
3. Feed each caught problem back into the agent instructions. `output/lessons.md` is the proposed list, and the owner approves it.
4. Read leads and calls from the client's CRM and phone system instead of `data/*.json`.

## Folder map

```
run_brief.py          run the pipeline, write output/
build_page.py         build docs/index.html from output/brief.json
brief/                the agents, the reviewer, the owner update
data/                 mock business, leads, calls, and the stale price cache
tests/                unit tests for every rule, plus a repository secret scan
output/               sample run: brief.json, owner_update.md, lessons.md
page/template.html    page source
docs/index.html       the built, shareable page
```

Built by Rorisang Ndah.
