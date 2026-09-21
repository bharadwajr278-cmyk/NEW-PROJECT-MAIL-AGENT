import { env } from "cloudflare:workers";
import { z } from "zod";

export const dynamic = "force-dynamic";

const itemSchema = z.object({
  id: z.string().min(1).max(300),
  source: z.string().min(1).max(80),
  project_name: z.string().min(1).max(500),
  rera_number: z.string().min(1).max(300),
  portal_project_id: z.string().max(300).default(""),
  developer: z.string().max(500).default(""),
  location: z.string().max(1500).default(""),
  city: z.string().max(200).default(""),
  registration_date: z.string().max(200).default("Not available"),
  project_type: z.string().max(200).default("Not available"),
  official_url: z.string().url().max(2000).or(z.literal("")),
  email_status: z.enum(["sent", "pending", "failed", "baseline"]),
  email_recipient: z.string().email().or(z.literal("")),
  first_seen_at: z.string().max(100),
  notified_at: z.string().max(100).nullable(),
  attempts: z.number().int().min(0).max(10000),
  last_error: z.string().max(3000).nullable(),
  priority: z.boolean(),
});

const payloadSchema = z.object({ notifications: z.array(itemSchema).min(1).max(100) });

async function keysEqual(a: string, b: string) {
  const encoder = new TextEncoder();
  const [leftHash, rightHash] = await Promise.all([
    crypto.subtle.digest("SHA-256", encoder.encode(a)),
    crypto.subtle.digest("SHA-256", encoder.encode(b)),
  ]);
  const left = new Uint8Array(leftHash);
  const right = new Uint8Array(rightHash);
  let difference = 0;
  for (let index = 0; index < left.length; index += 1) difference |= left[index] ^ right[index];
  return difference === 0;
}

export async function POST(request: Request) {
  const expectedKey = String((env as unknown as { INGEST_API_KEY?: string }).INGEST_API_KEY ?? "");
  const suppliedKey = request.headers.get("authorization")?.replace(/^Bearer\s+/i, "") ?? "";
  if (!expectedKey || !suppliedKey || !(await keysEqual(suppliedKey, expectedKey))) {
    return Response.json({ error: "Unauthorized" }, { status: 401 });
  }
  if (!request.headers.get("content-type")?.toLowerCase().includes("application/json")) {
    return Response.json({ error: "Content-Type must be application/json" }, { status: 415 });
  }

  let parsed: z.infer<typeof payloadSchema>;
  try {
    parsed = payloadSchema.parse(await request.json());
  } catch {
    return Response.json({ error: "Invalid notification payload" }, { status: 400 });
  }

  const now = new Date().toISOString();
  const statements = parsed.notifications.map((item) =>
    env.DB.prepare(
      `INSERT INTO notifications (
         id, source, project_name, rera_number, portal_project_id, developer,
         location, city, registration_date, project_type, official_url,
         email_status, email_recipient, first_seen_at, notified_at, attempts,
         last_error, priority, updated_at
       ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
       ON CONFLICT(id) DO UPDATE SET
         source=excluded.source, project_name=excluded.project_name,
         rera_number=excluded.rera_number, portal_project_id=excluded.portal_project_id,
         developer=excluded.developer, location=excluded.location, city=excluded.city,
         registration_date=excluded.registration_date, project_type=excluded.project_type,
         official_url=excluded.official_url, email_status=excluded.email_status,
         email_recipient=excluded.email_recipient, notified_at=excluded.notified_at,
         attempts=excluded.attempts, last_error=excluded.last_error,
         priority=excluded.priority, updated_at=excluded.updated_at`,
    ).bind(
      item.id, item.source, item.project_name, item.rera_number,
      item.portal_project_id, item.developer, item.location, item.city,
      item.registration_date, item.project_type, item.official_url,
      item.email_status, item.email_recipient, item.first_seen_at,
      item.notified_at, item.attempts, item.last_error, item.priority ? 1 : 0, now,
    ),
  );

  await env.DB.batch(statements);
  await env.BUCKET.put(
    `ingest/${Date.now()}-${crypto.randomUUID()}.json`,
    JSON.stringify({ received_at: now, count: parsed.notifications.length }),
    { httpMetadata: { contentType: "application/json" } },
  );

  return Response.json({ accepted: parsed.notifications.length }, { status: 202 });
}
