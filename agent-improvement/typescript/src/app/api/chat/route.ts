import { type NextRequest, NextResponse } from "next/server";
import type { ModelMessage } from "ai";

import { AgentConfigurationError, runTurn } from "@/src/agent";

export const maxDuration = 120;

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

/**
 * One agent turn over the posted history. Uses the same runTurn() core as
 * the eval harness, so the chat page behaves exactly like a graded case.
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  let body: { messages?: ChatMessage[] };
  try {
    body = (await request.json()) as { messages?: ChatMessage[] };
  } catch {
    return NextResponse.json({ error: "invalid JSON body" }, { status: 400 });
  }
  const messages = body.messages ?? [];
  if (messages.length === 0 || messages[messages.length - 1].role !== "user") {
    return NextResponse.json({ error: "body.messages must end with a user message" }, { status: 400 });
  }
  const history: ModelMessage[] = messages
    .slice(0, -1)
    .map((m) => ({ role: m.role, content: m.content }) as ModelMessage);
  const input = messages[messages.length - 1].content;

  try {
    const outcome = await runTurn(history, input);
    return NextResponse.json({
      response: outcome.response,
      toolCalls: outcome.toolCalls.map((c) => ({ name: c.name, arguments: c.arguments })),
      error: outcome.error,
      latencyMs: Math.round(outcome.latencyMs),
    });
  } catch (error) {
    if (error instanceof AgentConfigurationError) {
      return NextResponse.json({ error: error.message }, { status: 500 });
    }
    const message = error instanceof Error ? error.message : String(error);
    return NextResponse.json({ error: `chat failed: ${message}` }, { status: 500 });
  }
}
