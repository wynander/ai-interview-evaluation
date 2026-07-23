# Demo Data Repair Workspace

In this interview, you will build a small local tool for helping a Solution Consultant get messy prospect data ready for a customer-facing demo.

You can use your normal development environment and the tools you are comfortable with. Please think out loud as you work so we can follow your decisions, tradeoffs, and assumptions.

If you use AI, translate the requirements and context in your own words when prompting. Do not point an AI tool at this README and ask it to solve the whole exercise for you.

If your solution has a place where you would reasonably call an LLM or external model, it is acceptable to mock the response and explain your reasoning / approach. 



Timebox: 55 minutes.

## Problem

A Solution Consultant has a demo tomorrow for a retail prospect. The prospect sent over a product feed and asked whether it can be used for a personalized product discovery demo.

The feed is not clean. Some products are missing required fields, some values use inconsistent formats, some categories do not map cleanly, and some products are technically valid but would make for a poor demo.

Build the first useful version of a local workspace that helps the Solution Consultant review the feed, fix ambiguous data, approve or reject products, and export a demo-ready product feed.

## Starting Materials

This repo includes the starter artifacts you should use:

- `data/prospect-products.csv`: messy product feed from the prospect.
- `data/demo-brief.md`: what the Solution Consultant is trying to show.
- `data/target-schema.json`: target shape for demo-ready products.
- `data/category-map.json`: partial category mapping. It is intentionally incomplete.
- `data/previous-demo-products.json`: a small example of products from a prior clean demo.

## Core Requirements

The tool should let a Solution Consultant:

1. Load the product feed.
2. See products grouped by status, such as `ready`, `needs review`, and `rejected`.
3. Understand validation issues in plain language.
4. Edit product fields locally.
5. Apply obvious deterministic fixes, such as price parsing, tag splitting, and boolean normalization.
6. Approve or reject products.
7. Export the demo-ready product feed.

Build some sort of UI for the Solution Consultant. The workflow should be backed by local review state that can be saved, reopened, and used for export.

You may choose the UI stack and architecture. If you're familiar with the tools, we encourage creating one of: a small React / Next.js app, a simple Python web app, or a hybrid approach. These can all be valid if the result is understandable and useful.

Treat the original product feed as read-only source data. Edits, approvals, rejections, notes, and suggested fixes should live in separate local review state until the SC saves or exports generated output files.

## Stretch Goal

If you have time, expose the same workflow for agents or automation outside the UI.

This could be a CLI, local API, MCP server, code-mode interface, or another structured interface. The important part is that an agent or automation should be able to inspect products, list issues, apply edits, approve or reject items, and export the final package by operating on the same local files as the UI.

If you know agent-oriented patterns, this is a good place to showcase them through clear primitives, structured outputs, or a discoverable interface. If not, focus on making the SC-facing workflow solid.

## What To Optimize For

We are looking for a working slice, not a polished product. Prioritize functionality, clarity, correctness, and explainability over visual polish.

We do not expect perfect cleanup of every messy row. Prefer deterministic fixes for obvious cases, plain-language review flags for ambiguous cases, and explicit explanations for anything rejected or left unresolved.

Good work here usually includes:

- Start with a small plan and narrate important tradeoffs as you work.
- Use AI in short, scoped loops and inspect the code you keep.
- Verify the most important behavior with tests or executable examples.

## Constraints

- You may use AI tools, documentation, package managers, and your normal editor.
- We encourage fast, often free-tier models and short feedback loops, such as Composer 2.5, Claude Sonnet, or similar tools. The goal is to keep the session conversational and inspectable, not to wait silently on a single massive model run.
- Use TypeScript, React, Next.js, Node.js, Python, or a combination of those.
- You should narrate important decisions while working.
- You should be able to explain the code you keep.
- The project should be runnable locally without external API keys, paid services, hosted databases, or accounts unless we provide them during the session.
- Do not rely on a hosted database or remote service for product review state. Use local files.
- You do not need authentication, deployment, background jobs, or production-grade storage unless you choose to add them for a clear reason.

