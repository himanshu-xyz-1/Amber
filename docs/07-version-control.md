# Version Control Strategy

This document outlines the version control and code lifecycle practices for **Amber**, designed for a small, fast-moving engineering team (<5 engineers) to ensure rapid iteration while maintaining high code quality and security.

## 1. Repository Strategy

Amber uses a **Monorepo** approach for its core components.
- **Why Monorepo?** A single repository (`backend/`, `frontend/`, `infra/`, `docs/`) minimizes overhead for cross-cutting changes, simplifies dependency management, and provides a unified view of the system state. It is highly efficient for a small team compared to managing multiple repositories and syncing versions.

## 2. Branching Strategy

We use **Trunk-Based Development** instead of GitFlow.
- **Why Trunk-Based?** It reduces merge conflicts ("merge hell"), encourages smaller, more frequent commits, and allows for continuous integration and rapid delivery.
- **`main` Branch:** The single source of truth. It is strictly protected and *always deployable* to production.
- **Short-Lived Feature Branches:** Branched from `main`. Formats:
  - `feat/<issue-id-or-name>` for new features.
  - `fix/<issue-id-or-name>` for bug fixes.
  - `refactor/<name>` for code refactoring.
  - `docs/<name>` for documentation updates.
- **Release Branches (As Needed):** `release/v1.x` for staging or stabilizing a major release.
- **Hotfix Branches:** `hotfix/<name>`. Branched from `main` or a `release` branch, merged back to `main`, and backported if necessary.

## 3. Commit Conventions

We enforce **Conventional Commits** to auto-generate changelogs and maintain a readable history.
- `feat:` A new feature.
- `fix:` A bug fix.
- `docs:` Documentation only changes.
- `refactor:` A code change that neither fixes a bug nor adds a feature.
- `test:` Adding missing tests or correcting existing tests.
- `chore:` Changes to the build process or auxiliary tools and libraries.
- `ci:` Changes to our CI configuration files and scripts.

## 4. Pull Request Process

Every change to `main` must go through a Pull Request (PR).
- **PR Template:** A standard template ensures developers provide context, testing details, and link to relevant tickets.
- **Reviewers:** At least one required reviewer.
- **CI Checks:** All CI pipelines (linting, tests, security scans) must pass before a merge is allowed.
- **Merge Strategy:** **Squash and Merge** is preferred to keep `main` history clean and atomic.

## 5. Protected Branch Rules

The `main` branch is configured with strict branch protection rules in GitHub:
- Require a Pull Request before merging.
- Require status checks (CI/CD) to pass before merging.
- Require at least 1 approval from a code reviewer.
- Disable force pushing (`git push -f`).
- Restrict who can push to matching branches (nobody can bypass).

## 6. Code Ownership

We use a `CODEOWNERS` file at the root of the repository to ensure PRs are routed to the right domain experts automatically.
- `/backend/` @backend-team
- `/frontend/` @frontend-team
- `/infra/` @devops
- `/docs/` @all

## 7. Release Management

Amber uses **Semantic Versioning** (`MAJOR.MINOR.PATCH`).
- **Changelog Generation:** Automated based on Conventional Commits.
- **Git Tags:** When a release is cut, a tag (e.g., `v1.2.0`) is created.
- **GitHub Releases:** Automated release notes tied to Git tags for tracking historical changes and artifacts.

## 8. Environment Mapping

- **`main` branch:** Automatically deploys to the **Staging** environment.
- **Git Tags (e.g., `v1.x.x`):** Trigger the pipeline for the **Production** environment, requiring a manual promotion/approval gate.

## 9. Secrets in VCS

Security is paramount.
- **NEVER** commit `.env` files or hardcoded credentials.
- Always provide a `.env.example` file with dummy values to serve as a template for local development.
- Production and staging secrets are injected dynamically via the CI/CD vault (e.g., GitHub Secrets) or a runtime secret manager.
