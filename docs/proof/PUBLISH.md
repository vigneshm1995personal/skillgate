# Publish checklist (repo stays PRIVATE until Cal/Vignesh flip it)

Do **not** change GitHub visibility in automation. Flip **this** repo public only after the boxes below. Never flip `vigneshm1995personal/skillgate-ai`.

Live scan of `main` @ `e65dbaf`: **PASS**. See [15-scan-verdict.log](15-scan-verdict.log).

## 0. What this agent could and could not do

| Step | This run |
| --- | --- |
| Secret scan of `main` (gitleaks, trufflehog, `git grep`) | **PASS** — [15-gitleaks.log](15-gitleaks.log), [15-trufflehog.log](15-trufflehog.log), [15-git-grep.log](15-git-grep.log), [15-targeted-grep.log](15-targeted-grep.log) |
| Enable GitHub secret scanning + push protection via API | **Could not.** `gh` token has `admin: false`; `security_and_analysis` is `null`; `GET /secret-scanning/alerts` → **403**. Evidence: [15-github-secret-scanning-api.log](15-github-secret-scanning-api.log). Owner must use the UI (below). |
| Annotated tag `v0.3.0` on `main` | **Pushed.** Tag object `ef131b38` → commit `e65dbaf`. Evidence: [16-tag.log](16-tag.log). |
| PyPI Trusted Publisher | **Owner UI.** Workflow is `.github/workflows/release.yml`. No long-lived PyPI password. **Do not publish from this agent.** |
| Flip repo public | **Stop.** Owner only, after this checklist. |

---

## 1. GitHub secret scanning + push protection (owner UI)

Private repositories need a **GitHub Secret Protection** license for repo-level secret scanning and push protection. Public repositories get those features free. This agent cannot click Enable (no admin on the token).

### While the repo is still PRIVATE

1. Open https://github.com/vigneshm1995personal/skillgate
2. Click **Settings**.
3. Sidebar: **Security and quality** → **Advanced Security**  
   (older layout: **Code security** / **Code security and analysis**).
4. If **Secret Protection** is shown and **Enable** is available, click **Enable**.  
   If Enable is greyed out, the account has no Secret Protection license — skip until the repo is public, or buy the license.
5. Under Secret Protection, click **Enable** next to **Push protection**.
6. Confirm: Settings still shows Secret Protection = on, Push protection = on.

### After the repo is PUBLIC (later)

Same path. On a public repo, Secret Protection / secret scanning and push protection do not require a paid license.

Docs: [Enabling push protection](https://docs.github.com/en/code-security/secret-scanning/enabling-secret-scanning-features/enabling-push-protection-for-your-repository), [Managing security and analysis settings](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/enabling-features-for-your-repository/managing-security-and-analysis-settings-for-your-repository).

---

## 2. Secret scan of `main` (done)

Commanded needles: `sk-`, `postgres://`, `SKILLGATE_SECRETS_KEY=`, `VERCEL_APP_CLIENT`, `neon.tech`.

| Tool | Result |
| --- | --- |
| `gitleaks detect` 8.30.1 on `e65dbaf` (2 commits) | **PASS** exit 0, `no leaks found`, report `[]` |
| `gitleaks detect --log-opts=--all` (local refs) | **PASS** exit 0 |
| `trufflehog git file://… --fail --results=verified,unknown` 3.97.9 | **PASS** exit 0, verified=0 unverified=0 |
| `git grep` | **PASS** — remaining hits are deny-list / “scan for these names” docs, not values. No `sk-[A-Za-z0-9]{20,}`, no `postgresql://`. |

---

## 3. Tag `v0.3.0`

If this run’s tag push succeeded:

```text
git rev-parse v0.3.0^{}
# expected: e65dbaf804beacf4faa9e0354077e97d8c53b717
```

The tag points at squash-merged extract `main`, **not** at this docs/release-CI commit. That is intentional: first public bits are the already-scanned tree.

---

## 4. GitHub Environment `pypi` (owner UI — do this before the first publish)

The workflow job uses `environment: pypi`. Create it so a required reviewer must approve deploys:

1. https://github.com/vigneshm1995personal/skillgate/settings/environments
2. **New environment**
3. Name: `pypi` (exactly)
4. **Required reviewers**: add Cal and/or Vignesh
5. Optional: limit to tags `v*.*.*`
6. **Save protection rules**
7. Do **not** add a `PYPI_API_TOKEN` secret. Trusted Publishing uses OIDC (`id-token: write`) only.

---

## 5. PyPI Trusted Publisher (owner UI — stop before publish)

Project name on PyPI is **`skillgate-ai`** (`skillgate` is a different product). There is no project yet, so register a **pending** publisher. The first successful OIDC upload creates the project.

Exact steps ([PyPI docs](https://docs.pypi.org/trusted-publishers/adding-a-publisher/), [pending/OIDC project](https://docs.pypi.org/trusted-publishers/creating-a-project-through-oidc/)):

1. Sign in at https://pypi.org as the account that should **own** `skillgate-ai`.
2. Open **Account settings** → **Publishing**: https://pypi.org/manage/account/publishing/
3. Under **Add a new pending publisher**:
   - **PyPI Project Name:** `skillgate-ai`
   - **Owner:** `vigneshm1995personal`
   - **Repository name:** `skillgate`
   - **Workflow name:** `release.yml` (filename only, not `.github/workflows/release.yml`)
   - **Environment name:** `pypi`
4. Click **Add**.
5. Confirm the pending publisher row shows those five fields.

Do **not** create a PyPI API token. Do **not** put a password in GitHub secrets. Do **not** run `twine upload` by hand.

---

## 6. First publish (owner, after this PR is merged)

`v0.3.0` was tagged on a commit that does **not** contain `release.yml`. A tag push of that commit will not start this workflow. After merge:

1. Confirm `main` has `.github/workflows/release.yml`.
2. Confirm §4 environment and §5 pending publisher exist.
3. GitHub → **Actions** → **release** → **Run workflow**.
4. Tag input: `v0.3.0`
5. Approve the `pypi` environment if reviewers are required.
6. Wait for:
   - `build` (sdist + wheel)
   - `pypi` (OIDC upload to https://pypi.org/p/skillgate-ai)
   - `ghcr` (`ghcr.io/vigneshm1995personal/skillgate:v0.3.0`)

Until the GitHub repo is public, the GHCR package stays private (inherited). After the public flip, set the GHCR package visibility to public if you want `docker pull` without auth:  
https://github.com/users/vigneshm1995personal/packages/container/skillgate/settings

---

## 7. Flip visibility (Cal / Vignesh only — not this agent)

Only after:

- [ ] §2 scan **PASS** (already)
- [ ] §3 tag `v0.3.0` exists on `e65dbaf`
- [ ] §1 secret scanning + push protection enabled (or accepted “enable after public”)
- [ ] No live secret values in git (confirmed by gitleaks/trufflehog)

Then: **Settings** → **General** → **Danger Zone** → **Change repository visibility** → **Public** on **`skillgate` only**.

Never change visibility on `skillgate-ai`.
