/**
 * Tools exposed to the support agent — now backed by Postgres + external services.
 *
 * Each tool has a CANDIDATE TODO. The starter works but is naive:
 *  - search_docs: uses retrieval.search (which YOU rebuild in retrieval.ts).
 *  - API tools: single GET, no pagination, no retry, no timeout handling,
 *    inconsistent error shapes leak to the model.
 *  - Tickets: direct DB, no list-before-create, no dedup, no confirmation,
 *    no audit. Fix in code + db/migrations/.
 *
 * Keep tool NAMES stable (evals check traces). Improve schemas, descriptions,
 * normalization, retries, and side-effect safety.
 */
import { tool, zodSchema } from "ai";
import { z } from "zod";

import { execute, fetchAll, fetchOne } from "./db";
import { normalizeId, toIso } from "./normalize";
import { search as retrievalSearch } from "./retrieval";
import { asJson } from "./runtime-helpers";
import { logToolCall } from "./tracing";

const SERVICES_API_URL = process.env.SERVICES_API_URL ?? "http://localhost:8001";
const SERVICES_API_KEY = process.env.SERVICES_API_KEY ?? "dev-insecure-key";

/**
 * Payload shapes returned by the external services (see src/app/api/*).
 * Fields beyond these are allowed (external API) but tools only rely on
 * the ones declared here.
 */
export interface CustomerRecord {
  customer_id: string;
  name: string;
  email: string;
  plan_code?: string;
  account_status?: string;
  product_code?: string;
  region_code?: string;
  subscription_id?: string;
  created_at?: string;
  [key: string]: unknown;
}

export interface CustomerList {
  customers: CustomerRecord[];
}

export interface SubscriptionRecord {
  subscription_id: string;
  account?: string;
  started_on?: string;
  cycle?: string;
  status?: string;
  [key: string]: unknown;
}

export interface OrderRecord {
  order_id: string;
  customer_id: string;
  item?: string;
  placed_on?: string;
  status?: string;
  total_usd?: number | string;
  [key: string]: unknown;
}

export interface OrdersPage {
  orders: OrderRecord[];
  total?: number;
  next_cursor?: number | null;
  [key: string]: unknown;
}

export interface IncidentRecord {
  incident_id?: string;
  service?: string;
  region?: string;
  status?: string;
  severity?: string;
  title?: string;
  started_on?: string;
  summary?: string;
  [key: string]: unknown;
}

/**
 * TODO (candidate): retries, timeouts, unified errors.
 * Starter: one attempt, 10s timeout, raw error text on failure.
 * Returns the parsed payload on success, or an error string the model
 * can act on. Callers MUST check `typeof result === "string"` first.
 */
async function apiGet<T>(path: string, params: Record<string, string | number> = {}): Promise<T | string> {
  const started = Date.now();
  const url = new URL(`${SERVICES_API_URL}${path}`);
  for (const [key, value] of Object.entries(params)) url.searchParams.set(key, String(value));
  try {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 10_000);
    let response: Response;
    try {
      response = await fetch(url, {
        headers: {
          "X-API-Key": SERVICES_API_KEY,
          // Propagates CHAOS=1 into the web container (env set on the eval
          // process never reaches it). Keep sending this.
          "X-Chaos": process.env.CHAOS === "1" ? "1" : "0",
        },
        signal: controller.signal,
      });
    } finally {
      clearTimeout(timer);
    }
    const latencyMs = Date.now() - started;
    if (response.status >= 400) {
      const text = await response.text();
      logToolCall("http_get", { path }, latencyMs, false, text.slice(0, 200));
      return `API error ${response.status} on ${path}: ${text.slice(0, 300)}`;
    }
    logToolCall("http_get", { path }, latencyMs, true);
    return (await response.json()) as T;
  } catch (error) {
    const latencyMs = Date.now() - started;
    const message = error instanceof Error ? error.message : String(error);
    logToolCall("http_get", { path }, latencyMs, false, message.slice(0, 200));
    return `API request to ${path} failed: ${message}. You may retry once.`;
  }
}

export const searchDocs = tool({
  description:
    "Search support documentation. Returns top chunks with doc_id citations. " +
    "Prefer results with status=current and trust=official. Never quote " +
    "internal-audience docs to customers. Cite doc_ids you rely on.",
  inputSchema: zodSchema(
    z.object({ query: z.string().describe("Keywords or question to find in support documentation.") }),
  ),
  execute: async ({ query }: { query: string }) => {
    const started = Date.now();
    // Narrow starter window: with lexical ranking, top-3 rarely surfaces the
    // official doc among 3000 distractors. Widen deliberately once ranking and
    // filtering improve (see retrieval.ts).
    const chunks = await retrievalSearch(query, 3);
    logToolCall("search_docs", { query }, Date.now() - started, true, `${chunks.length} chunks`);
    if (chunks.length === 0) return "No documentation matched the query.";
    return asJson(
      chunks.map((c) => ({
        doc_id: c.doc_id,
        title: c.title,
        body: c.body,
        status: c.status,
        trust: c.trust,
        effective_from: c.effective_from,
        audience: c.audience,
      })),
    );
  },
});

export const resolveCustomer = tool({
  description:
    "Resolve a customer reference to account(s). May return multiple matches — " +
    "if ambiguous, ask the user to disambiguate instead of picking one.",
  inputSchema: zodSchema(
    z.object({
      customer_id: z.string().optional().describe("A customer ID like C123."),
      name: z.string().optional().describe("Full or partial customer name."),
      email: z.string().optional().describe("Exact customer email."),
    }),
  ),
  execute: async ({
    customer_id,
    name,
    email,
  }: {
    customer_id?: string;
    name?: string;
    email?: string;
  }) => {
    if (customer_id) {
      const result = await apiGet<CustomerRecord>(`/api/customers/${normalizeId(customer_id)}`);
      if (typeof result !== "string" && result.customer_id) {
        return asJson({
          status: "exact_match",
          customer: { customer_id: result.customer_id, name: result.name, email: result.email },
        });
      }
      return asJson({ status: "not_found", matches: [] });
    }

    const needle = (name ?? email ?? "").trim();
    const result = await apiGet<CustomerList>("/api/customers", { search: needle });
    if (typeof result === "string") return result;
    let matches = result.customers ?? [];
    if (email) {
      const wanted = email.trim().toLowerCase();
      matches = matches.filter((m) => m.email.toLowerCase() === wanted);
    }
    if (matches.length === 1) return asJson({ status: "exact_match", customer: matches[0] });
    if (matches.length > 1) return asJson({ status: "ambiguous", matches });
    return asJson({ status: "not_found", matches: [] });
  },
});

export const getCustomer = tool({
  description: "Look up a full customer account record. IDs are upper-case, dates ISO.",
  inputSchema: zodSchema(z.object({ customer_id: z.string().describe("The customer ID, such as C123.") })),
  execute: async ({ customer_id }: { customer_id: string }) => {
    const result = await apiGet<CustomerRecord>(`/api/customers/${normalizeId(customer_id)}`);
    if (typeof result === "string") return result;
    result.customer_id = normalizeId(result.customer_id ?? "");
    if (result.created_at) result.created_at = toIso(String(result.created_at));
    return asJson(result);
  },
});

export const getSubscription = tool({
  description: "Look up a subscription record by subscription ID (not customer ID).",
  inputSchema: zodSchema(
    z.object({ subscription_id: z.string().describe("The subscription ID, such as SUB-123.") }),
  ),
  execute: async ({ subscription_id }: { subscription_id: string }) => {
    const result = await apiGet<SubscriptionRecord>(`/api/subscriptions/${subscription_id.trim()}`);
    if (typeof result === "string") return result;
    if (result.started_on) result.started_on = toIso(String(result.started_on));
    return asJson(result);
  },
});

export const getOrders = tool({
  description:
    "Get orders for a customer, newest first. " +
    "TODO (candidate): this only fetches page 1 (50 rows). Handle pagination " +
    "(next_cursor) and cap total rows so the 15k-order load customer doesn't " +
    "blow context or time out.",
  inputSchema: zodSchema(z.object({ customer_id: z.string().describe("The customer ID, such as C123.") })),
  execute: async ({ customer_id }: { customer_id: string }) => {
    const payload = await apiGet<OrdersPage>("/api/orders", {
      customer_id: normalizeId(customer_id),
      limit: 50,
      cursor: 0,
    });
    if (typeof payload === "string") return payload;
    const orders = payload.orders ?? [];
    for (const order of orders) {
      order.customer_id = normalizeId(order.customer_id ?? "");
      if (order.placed_on) order.placed_on = toIso(String(order.placed_on));
    }
    if (payload.next_cursor !== null && payload.next_cursor !== undefined) {
      return asJson({
        orders,
        total: payload.total,
        note: `showing 50 of ${payload.total}; pagination not yet implemented — see TODO`,
      });
    }
    return asJson(payload.total === null || payload.total === undefined ? orders : { orders, total: payload.total });
  },
});

export const getOrder = tool({
  description: "Look up a single order by ID.",
  inputSchema: zodSchema(z.object({ order_id: z.string().describe("The order ID, such as O-1042.") })),
  execute: async ({ order_id }: { order_id: string }) => {
    const result = await apiGet<OrderRecord>(`/api/orders/${order_id.trim()}`);
    if (typeof result === "string") return result;
    if (result.placed_on) result.placed_on = toIso(String(result.placed_on));
    return asJson(result);
  },
});

export const getActiveIncident = tool({
  description: "Find an active incident for a service + region. Codes and names both work.",
  inputSchema: zodSchema(
    z.object({
      service: z.string().describe("Service name or code (e.g. collaboration, collab, migration)."),
      region: z.string().describe("Region name or code (e.g. Europe, EU, APAC)."),
    }),
  ),
  execute: async ({ service, region }: { service: string; region: string }) => {
    const result = await apiGet<IncidentRecord>("/api/incidents/active", {
      service: service.trim(),
      region: region.trim(),
    });
    if (typeof result === "string") return result;
    return asJson(result);
  },
});

export const listTickets = tool({
  description: "List support tickets for a customer. Call this before creating a ticket to avoid duplicates.",
  inputSchema: zodSchema(
    z.object({
      customer_id: z.string().describe("The customer ID."),
      order_id: z.string().optional().describe("Optional order ID filter."),
      status: z.enum(["open", "pending", "closed"]).optional().describe("Optional status filter."),
    }),
  ),
  execute: async ({
    customer_id,
    order_id,
    status,
  }: {
    customer_id: string;
    order_id?: string;
    status?: "open" | "pending" | "closed";
  }) => {
    let query =
      "SELECT ticket_id, customer_id, issue, priority, status, related_order_id FROM tickets WHERE upper(customer_id) = upper($1)";
    const params: string[] = [customer_id.trim()];
    if (order_id) {
      query += ` AND related_order_id = $${params.length + 1}`;
      params.push(order_id.trim().toUpperCase());
    }
    if (status) {
      query += ` AND status = $${params.length + 1}`;
      params.push(status);
    }
    query += " ORDER BY created_at DESC LIMIT 50";
    const rows = await fetchAll(query, params);
    return asJson({ status: "ok", tickets: rows });
  },
});

export const createSupportTicket = tool({
  description:
    "Create a support ticket. " +
    "TODO (candidate): don't create duplicates — check list_tickets first, " +
    "and add a DB backstop in src/db/migrations/. " +
    "Write an audit row to tool_audit_log.",
  inputSchema: zodSchema(
    z.object({
      customer_id: z.string().describe("The customer ID, such as C123."),
      issue: z.string().describe("Concise description of the issue."),
      priority: z.enum(["low", "normal", "high", "urgent"]).default("normal").describe("Ticket priority."),
      related_order_id: z
        .string()
        .optional()
        .describe("Order ID to link, e.g. O-2014. Pass it when the user mentions an order."),
    }),
  ),
  execute: async ({
    customer_id,
    issue,
    priority = "normal",
    related_order_id,
  }: {
    customer_id: string;
    issue: string;
    priority?: "low" | "normal" | "high" | "urgent";
    related_order_id?: string;
  }) => {
    const normalizedCustomer = normalizeId(customer_id);
    const cleanedIssue = issue.trim();
    if (!cleanedIssue) return "Cannot create ticket: the issue description is empty.";

    const customer = await fetchOne("SELECT customer_id FROM customers WHERE upper(customer_id) = upper($1)", [
      normalizedCustomer,
    ]);
    if (!customer) return `Cannot create ticket: no customer found for ID '${customer_id.trim()}'.`;

    const seq = await fetchOne<{ n: string }>("SELECT nextval('ticket_seq') AS n");
    const ticketId = seq ? `T-${Number(seq.n)}` : "T-2001";
    await execute(
      "INSERT INTO tickets (ticket_id, customer_id, issue, priority, status, related_order_id) VALUES ($1,$2,$3,$4,'open',$5)",
      [
        ticketId,
        normalizedCustomer,
        cleanedIssue,
        priority,
        related_order_id ? related_order_id.trim().toUpperCase() : null,
      ],
    );
    await execute("INSERT INTO tool_audit_log (tool_name, arguments) VALUES ('create_support_ticket', $1)", [
      asJson({ ticket_id: ticketId, customer_id: normalizedCustomer }),
    ]);
    const created = await fetchOne(
      "SELECT ticket_id, customer_id, issue, priority, status, related_order_id FROM tickets WHERE ticket_id = $1",
      [ticketId],
    );
    return asJson(created);
  },
});

export const TOOLS = {
  search_docs: searchDocs,
  resolve_customer: resolveCustomer,
  get_customer: getCustomer,
  get_subscription: getSubscription,
  get_orders: getOrders,
  get_order: getOrder,
  get_active_incident: getActiveIncident,
  list_tickets: listTickets,
  create_support_ticket: createSupportTicket,
};
