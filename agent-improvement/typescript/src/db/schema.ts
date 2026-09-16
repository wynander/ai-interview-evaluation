/**
 * Drizzle view of the starter schema (see src/db/schema.sql — same tables).
 *
 * Candidate: when you add a migration in src/db/migrations/, update this file to
 * match so queries keep working. Tables mirror the naive starter: TEXT dates,
 * no FKs, no secondary indexes.
 */
import {
  integer,
  jsonb,
  numeric,
  pgTable,
  primaryKey,
  serial,
  text,
  timestamp,
} from "drizzle-orm/pg-core";

export const customers = pgTable("customers", {
  customerId: text("customer_id").primaryKey(),
  name: text("name").notNull(),
  email: text("email").notNull(),
  planCode: text("plan_code").notNull(),
  accountStatus: text("account_status").notNull(),
  productCode: text("product_code").notNull(),
  regionCode: text("region_code").notNull(),
  subscriptionId: text("subscription_id").notNull(),
  createdAt: text("created_at").notNull().default("Jan 5 2025"),
});

export const subscriptions = pgTable("subscriptions", {
  subscriptionId: text("subscription_id").primaryKey(),
  account: text("account").notNull(),
  startedOn: text("started_on").notNull(),
  cycle: text("cycle").notNull(),
  status: text("status").notNull(),
});

export const orders = pgTable("orders", {
  orderId: text("order_id").primaryKey(),
  customerId: text("customer_id").notNull(),
  item: text("item").notNull(),
  placedOn: text("placed_on").notNull(),
  status: text("status").notNull(),
  totalUsd: numeric("total_usd").notNull(),
});

export const documents = pgTable(
  "documents",
  {
    docId: text("doc_id").notNull(),
    title: text("title").notNull(),
    body: text("body").notNull(),
    status: text("status").notNull().default("current"),
    trust: text("trust").notNull().default("official"),
    effectiveFrom: text("effective_from").notNull().default("2024-01-01"),
    audience: text("audience").notNull().default("customer_facing"),
    version: integer("version").notNull().default(1),
  },
  (t) => [primaryKey({ columns: [t.docId, t.version] })],
);

export const incidents = pgTable("incidents", {
  incidentId: text("incident_id").primaryKey(),
  service: text("service").notNull(),
  region: text("region").notNull(),
  status: text("status").notNull(),
  severity: text("severity").notNull(),
  title: text("title").notNull(),
  startedOn: text("started_on").notNull(),
  summary: text("summary").notNull(),
});

export const tickets = pgTable("tickets", {
  ticketId: text("ticket_id").primaryKey(),
  customerId: text("customer_id").notNull(),
  issue: text("issue").notNull(),
  priority: text("priority").notNull().default("normal"),
  status: text("status").notNull().default("open"),
  relatedOrderId: text("related_order_id"),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});

export const toolAuditLog = pgTable("tool_audit_log", {
  id: serial("id").primaryKey(),
  toolName: text("tool_name").notNull(),
  arguments: jsonb("arguments").notNull().default({}),
  resultSummary: text("result_summary").notNull().default(""),
  createdAt: timestamp("created_at", { withTimezone: true }).notNull().defaultNow(),
});
