import { index, integer, sqliteTable, text } from "drizzle-orm/sqlite-core";

export const notifications = sqliteTable(
  "notifications",
  {
    id: text("id").primaryKey(),
    source: text("source").notNull(),
    projectName: text("project_name").notNull(),
    reraNumber: text("rera_number").notNull(),
    portalProjectId: text("portal_project_id").notNull().default(""),
    developer: text("developer").notNull().default(""),
    location: text("location").notNull().default(""),
    city: text("city").notNull().default(""),
    registrationDate: text("registration_date").notNull().default("Not available"),
    projectType: text("project_type").notNull().default("Not available"),
    officialUrl: text("official_url").notNull().default(""),
    emailStatus: text("email_status").notNull().default("pending"),
    emailRecipient: text("email_recipient").notNull().default(""),
    firstSeenAt: text("first_seen_at").notNull(),
    notifiedAt: text("notified_at"),
    attempts: integer("attempts").notNull().default(0),
    lastError: text("last_error"),
    priority: integer("priority", { mode: "boolean" }).notNull().default(false),
    updatedAt: text("updated_at").notNull(),
  },
  (table) => [
    index("idx_notifications_first_seen").on(table.firstSeenAt),
    index("idx_notifications_source_status").on(table.source, table.emailStatus),
    index("idx_notifications_city").on(table.city),
  ],
);
