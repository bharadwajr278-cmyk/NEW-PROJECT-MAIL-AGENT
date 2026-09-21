import { env } from "cloudflare:workers";
import { requireChatGPTUser, chatGPTSignOutPath } from "./chatgpt-auth";
import Dashboard from "./dashboard";

export const dynamic = "force-dynamic";

export type Notification = {
  id: string;
  source: string;
  project_name: string;
  rera_number: string;
  portal_project_id: string;
  developer: string;
  location: string;
  city: string;
  registration_date: string;
  project_type: string;
  official_url: string;
  email_status: "sent" | "pending" | "failed" | "baseline";
  email_recipient: string;
  first_seen_at: string;
  notified_at: string | null;
  attempts: number;
  last_error: string | null;
  priority: number;
};

async function loadNotifications(): Promise<Notification[]> {
  try {
    const result = await env.DB.prepare(
      `SELECT id, source, project_name, rera_number, portal_project_id,
              developer, location, city, registration_date, project_type,
              official_url, email_status, email_recipient, first_seen_at,
              notified_at, attempts, last_error, priority
       FROM notifications
       ORDER BY first_seen_at DESC
       LIMIT 5000`,
    ).all<Notification>();
    return result.results ?? [];
  } catch (error) {
    console.error("Unable to load notification ledger", error);
    return [];
  }
}

export default async function Home() {
  const user = await requireChatGPTUser("/");
  const notifications = await loadNotifications();

  return (
    <Dashboard
      initialNotifications={notifications}
      viewerEmail={user.email}
      signOutPath={chatGPTSignOutPath("/")}
    />
  );
}
