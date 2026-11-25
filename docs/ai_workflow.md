# AI workflow

This build was made with an AI coding assistant (Cursor) working as a teammate. This file records how, so a reviewer
can judge where the decisions came from.

## Tools

- **Cursor agent** for planning, code changes, file edits and running checks.
- **Databricks skills** for the CLI, bundles, Lakeflow pipelines, Lakebase synced tables and Apps. The agent read the
  skill guidance before each product step.
- **Plan mode** to agree the scope before any change. The plan covered what to remove, what to rename, and what to
  verify.

## Patterns that worked

1. **Scope first, then edit.** The agent listed every customer reference with a search, then fixed them in groups
   (names, branding, prose), and searched again after each group.
2. **Verify with the real artifact.** The sample packages were regenerated with the generator and compared with the
   committed copies, rather than trusting that the generator still matched the data.
3. **Keep the old repo read-only.** The new repo was created from a tracked-file export with no history, so no
   customer identifiers could come across in git history.
4. **Check the integration, not just the page.** The portfolio page was wired to a new API route, and the job was
   given a task that writes the table the route reads.

## Example prompts

- "Take the Study Hub build, create a new public repo, generalize it, and remove all references to the original
  customer. Do not change the current repo."
- "Add a Lakebase synced table for the portfolio, so the app page is served from Lakebase and the SQL warehouse is
  not on the page-view path."
- "Write the business deck from the value model. Lead with the outcome and state every number as an assumption."

## Where human decisions shaped the build

The assistant proposed options, and the author chose among them. Decisions the author made:

- **Scope.** A separate mapping sub-project was left out of the public repo. It depended on another organization's internal data model,
  and the author chose the option that keeps the public story simple.
- **Persona.** The author chose a fictional contract research organization (Helix Clinical Research) over a
  biopharma sponsor, because it matches the original problem.
- **Lakebase.** The author chose to add a synced table for the portfolio, so the data journey is connected end to end.
- **Workspace.** The author chose to deploy on a fresh FEVM workspace, so the execution evidence is new.

The assistant does not sign the attestation. The author reviews every claim in the submission.
