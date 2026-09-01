# Demo Data Repair Workspace

In this interview, you will build a small local tool for helping a Solution Consultant get messy prospect data ready for a customer-facing demo.

You can use your normal development environment and the tools you are comfortable with. Please think out loud as you work so we can follow your decisions, tradeoffs, and assumptions.

If you use AI, translate the requirements and context in your own words when prompting. Do not point an AI tool at this README and ask it to solve the whole exercise for you.

If your solution has a place where you would reasonably call an LLM or external model, it is acceptable to mock the response and explain your reasoning / approach.

Timebox: 55 minutes. Aim to finish a usable core slice in about 25–30 minutes so you have time for the stretch goal or a design discussion.

## Problem

A Solution Consultant has a demo tomorrow for a retail prospect. The prospect sent over a product feed and asked whether it can be used for a personalized product discovery demo.

The feed is not clean. Some products are missing required fields, some values use inconsistent formats, some categories do not map cleanly, and some products are technically valid but would make for a poor demo.

Build the first useful version of a local workspace that helps the Solution Consultant review the feed, apply obvious cleanup, fix ambiguous fields, decide what belongs in the demo, and export a demo-ready product feed.

## Starting Materials

This repo includes the starter artifacts you should use:

- `data/prospect-products.csv`: messy product feed from the prospect.
- `data/demo-brief.md`: what the Solution Consultant is trying to show.
- `data/target-schema.json`: target shape for demo-ready products.

Optional references if useful:

- `data/category-map.json`: partial category mapping. It is intentionally incomplete.
- `data/previous-demo-products.json`: a small example of products from a prior clean demo.

## Core Requirements

Focus on a working slice, not a polished product. The tool should let a Solution Consultant:

1. Load the product feed and see each product with plain-language validation issues.
2. Apply obvious deterministic fixes, such as price parsing, tag splitting, and boolean normalization.
3. Edit product fields locally when a row is almost usable.
4. Approve or reject products for the demo.
5. Export a demo-ready product feed that matches the target schema.

Build a simple UI for that workflow. You may choose the stack; a small React / Next.js app, a simple Python web app, or a hybrid approach are all fine if the result is understandable and useful.

Keep the original CSV read-only. Treat edits, approvals, rejections, and derived cleanup as separate local state (in memory is fine for the core slice; writing it to a file is a plus).


## Stretch Goal

If you have time, expose the same workflow for agents or automation outside the UI. If not, let's discuss how you would do this and what you would take into consideration.

This could be a CLI, local API, MCP server, code-mode interface, or another structured interface. The important part is that an agent or automation should be able to inspect products, list issues, apply edits or fixes, approve or reject items, and export the final package by operating on the same starting file as the UI.

If you know agent-oriented patterns, this is a good place to showcase them through clear primitives, structured outputs, or a discoverable interface.

## What To Optimize For

We are looking for a working slice, not a fully polished product. Prioritize functionality, clarity, correctness, and explainability over visual polish.

We do not expect the perfect cleanup solution for every messy row. Prefer deterministic fixes for obvious cases, plain-language review flags for ambiguous cases, and explicit explanations for anything rejected or left unresolved.

Good work here usually includes:

- Start with a small plan and narrate important tradeoffs as you work.
- Use AI in short, scoped loops and inspect the code you keep.
- Verify the most important behavior with tests or executable examples.
- Ignore some requirements if you see a better solution — mention your justification. There is no one right answer, and an important part of the role is knowing when to discount certain requirements.

## Constraints

- You may use AI tools, documentation, package managers, and your normal editor.
- We encourage fast, often free-tier models and short feedback loops, such as Composer 2.5, Claude Sonnet, or similar tools. The goal is to keep the session conversational and inspectable, not to wait silently on a single massive model run.
- Ideally use TypeScript, React, Next.js, Node.js, Python, or a combination of those.
- You should narrate important decisions while working.
- You should be able to explain the code you keep.
- The project should be runnable locally without external API keys, paid services, hosted databases, or accounts unless we provide them during the session.
- Do not rely on a hosted database or remote service for product review state. Use local files or in-memory state.
- You do not need authentication, deployment, background jobs, or production-grade storage unless you choose to add them for a clear reason.
