# ChatGPT project context

This directory is a local mirror of the ChatGPT project “AI - Survey on Evaluating LLM”.

- Treat every file under `sources/` as read-only reference material.
- Do not edit, rename, move, or delete synced project files.
- These files may be replaced the next time a task is created from this ChatGPT project.


## Project instructions

This project has no custom instructions.

## Layout and current state

- `project_overview.md` summarizes the LLM-evaluation survey, its themes, and possible project outputs.
- `implementation_plan.md` proposes a future LLM-evaluation platform and experiment; its architecture, tools, and milestones are plans, not an existing implementation.
- `BUILD_PLAN.md` defines the phased execution roadmap, acceptance checks, and first-release scope. Its commands and file layout are proposals until implemented and verified.
- `sources/ai_project.md` is the synced text of the 2024 survey *A Survey on Evaluation of Large Language Models*; `sources/figure-1.png` through `figure-3.png` are reference figures.
- There is currently no application source code, dataset, test suite, dependency manifest, or runnable build in this directory.

## Working conventions and verification

- Keep `sources/` read-only as specified above. Edit the top-level Markdown documents only when asked; distinguish survey findings from proposals and from results actually measured by this project.
- Use the survey as the primary reference for claims about its contents. Do not describe the planned platform or experiment as implemented or completed.
- No setup, build, test, or run command is defined by the current files. Verify documentation edits by reading the changed Markdown and checking its references; add executable commands here only after an implementation provides them and they have been verified.
