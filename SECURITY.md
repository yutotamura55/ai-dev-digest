# Security policy

## Reporting a vulnerability

Please report a vulnerability in ai-dev-digest privately, not in a public issue or pull request.

1. Open the repository's **Security and quality** tab on GitHub (called **Security** on older pages) and choose **Report a vulnerability** (GitHub private vulnerability reporting).
2. Describe what the problem is, how to reproduce it, and what an attacker could do with it.

The report becomes a private security advisory. People who can read it: you, everyone with admin access to this repository, anyone the maintainer adds to the advisory, and GitHub staff under GitHub's terms. Do not put secrets in the report that you would not share with them.

The maintainer intends to reply in that private advisory, to confirm the problem, to prepare a fix privately, and to publish the fix together with a security advisory that credits you, unless you ask otherwise. ai-dev-digest is maintained by one person in their spare time, so there is no promised response time. When a problem will not be fixed, the maintainer intends to say so in the advisory.

## Scope

ai-dev-digest fetches public feeds, stores articles in Firestore, and serves them through an API and a web page. Reports that matter most:

- a way to make the collector fetch or store something other than the configured feeds (for example a request to an internal address);
- content from a feed that runs as script in the web page;
- a secret (API key, cloud credentials) that the code, the logs, or the CI could expose.

## Supported versions

There are no releases yet. The `main` branch is the supported version.
