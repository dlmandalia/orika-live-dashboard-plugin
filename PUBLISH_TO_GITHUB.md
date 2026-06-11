# Publish to GitHub

Recommended repository name:

```text
orika-live-dashboard-plugin
```

## Option A: GitHub CLI

Install/authenticate GitHub CLI first:

```bash
gh auth login
```

From this folder:

```bash
cd C:/Hermes/Oreka/orika-live-dashboard-plugin
gh repo create orika-live-dashboard-plugin --private --source . --push
```

If you want it public instead:

```bash
gh repo create orika-live-dashboard-plugin --public --source . --push
```

Then other Hermes CLIs can install it with:

```bash
hermes plugins install YOUR_GITHUB_USERNAME/orika-live-dashboard-plugin --enable
```

## Option B: GitHub website + git

1. Create an empty repo on GitHub named `orika-live-dashboard-plugin`.
2. Do not add README/license/gitignore on GitHub because this local repo already has them.
3. From this folder, run:

```bash
cd C:/Hermes/Oreka/orika-live-dashboard-plugin
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/orika-live-dashboard-plugin.git
git push -u origin main
```

Then install with:

```bash
hermes plugins install YOUR_GITHUB_USERNAME/orika-live-dashboard-plugin --enable
```

## Keep credentials out

Do not commit `.env` or real Orika credentials. This repository is already configured to ignore them.
