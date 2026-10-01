---
name: web-research
description: Use when you need current information that is not in the workspace. Search, then fetch, then cite.
tags: [research, web]
---

# Web research

You have `web_search` and `web_fetch`. Use them instead of guessing.

## Process
1. **Search** with specific terms. Prefer the technology name plus the version
   and the error text, e.g. `"pydantic v2 model_validator before mode example"`.
2. **Fetch** the two or three most promising results. Titles lie; read the page.
3. **Prefer primary sources**: official docs, the repository, the changelog,
   the RFC, the release notes. Blog posts and Q&A sites are hints, not authority.
4. **Check the date.** APIs change. A 2019 answer about a 2024 library is likely
   wrong. Note the version the source applies to.
5. **Cite what you used** in your answer: the URL and, when it matters, the date.

## Rules
- Never state an API signature or behaviour you did not read somewhere concrete.
- If sources disagree, say so and explain which you trust and why.
- If a page will not load or is paywalled, say that instead of inventing content.
- Do not paste long verbatim excerpts; summarise and link.
