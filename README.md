# selective_learn 🎯

Extract a Udemy course curriculum into an AI-ready learn plan, so you can decide which lectures to watch, skim, or skip instead of sitting through the whole course.

Udemy blocks copy/paste on the course page, but its public API serves the full curriculum as JSON. This script pulls it directly from a course URL. No login, no browser, no saved pages.

## What it captures

- Course name, URL, headline, and full course overview
- Every section with its lecture count and total duration
- Every lecture with its duration and description
- A verdict slot per lecture, pre-filled with `TBD`, for an AI to replace with `WATCH`, `SKIM`, or `SKIP`

## Setup (one time)

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## Usage

```
.venv\Scripts\python selective_learn.py <course-url>
```

Example (sample URL, not a real course):

```
.venv\Scripts\python selective_learn.py https://www.udemy.com/course/mastering-underwater-basket-weaving/
```

Multiple URLs in one run are supported. Use `-o <folder>` to write outputs somewhere else.

Console output per course (sample data):

```
https://www.udemy.com/course/mastering-underwater-basket-weaving/ - 200 - OK
Course:  Underwater Basket Weaving Masterclass: From Reeds to Riches
Content: 6 sections • 142 lectures • 21h 08m • 139 lectures with descriptions
Wrote:   mastering-underwater-basket-weaving.learnplan.md
Wrote:   mastering-underwater-basket-weaving.learnplan.csv
```

## Outputs

| File                   | Purpose                                                                                                                                                                        |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `<slug>.learnplan.md`  | Markdown learn plan. Course overview at the top, then each section and lecture with durations, descriptions, and a `[TBD]` verdict slot. This is the file to share with an AI. |
| `<slug>.learnplan.csv` | Same data as a flat table, one row per lecture, with a `verdict` column set to `TBD`. Useful for filtering and progress tracking in Excel.                                     |

## Triage workflow 📝

1. Run the script on a course URL.
2. Give the `.learnplan.md` to an AI along with your goals, project context, and current skills.
3. The file already instructs the AI to replace each `[TBD]` with `[WATCH]`, `[SKIM]`, or `[SKIP]` based on the lecture descriptions.
4. Ask for the total time of the trimmed path versus the full course to see what you save.

## Notes

- Requests send a normal Chrome User-Agent header. Without it, Udemy returns a challenge page instead of JSON.
- Total duration can differ slightly from the number shown on Udemy. Udemy's headline figure counts video content only, while the API also assigns lengths to article items.
- Lecture descriptions are truncated to 250 characters. The first sentence or two carries nearly all the decision signal, and truncation keeps the learn plan around 20K tokens instead of 90K for description-heavy courses.
- Some courses have no lecture descriptions. Descriptions are instructor-provided, and when an instructor skips them, the text shown on the Udemy page is an AI summary that the public API does not expose. For such courses the learn plan notes this, and verdicts rely on section names, lecture titles, and durations, which is usually enough.
- A bad or unknown course URL prints a one-line error and exits with a non-zero code.

## License

[Apache License 2.0](LICENSE)
