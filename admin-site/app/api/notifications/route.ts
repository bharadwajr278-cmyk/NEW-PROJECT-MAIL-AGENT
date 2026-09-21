import { env } from "cloudflare:workers";
import { getChatGPTUser } from "@/app/chatgpt-auth";

export const dynamic = "force-dynamic";

export async function GET() {
  const user = await getChatGPTUser();
  if (!user) return Response.json({ error: "Unauthorized" }, { status: 401 });

  const result = await env.DB.prepare(
    `SELECT id, source, project_name, rera_number, portal_project_id,
            developer, location, city, registration_date, project_type,
            official_url, email_status, email_recipient, first_seen_at,
            notified_at, attempts, last_error, priority
     FROM notifications ORDER BY first_seen_at DESC LIMIT 5000`,
  ).all();

  return Response.json(
    { count: result.results?.length ?? 0, projects: result.results ?? [] },
    { headers: { "Cache-Control": "private, no-store" } },
  );
}
