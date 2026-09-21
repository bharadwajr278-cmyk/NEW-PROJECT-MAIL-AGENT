CREATE TABLE `notifications` (
	`id` text PRIMARY KEY NOT NULL,
	`source` text NOT NULL,
	`project_name` text NOT NULL,
	`rera_number` text NOT NULL,
	`portal_project_id` text DEFAULT '' NOT NULL,
	`developer` text DEFAULT '' NOT NULL,
	`location` text DEFAULT '' NOT NULL,
	`city` text DEFAULT '' NOT NULL,
	`registration_date` text DEFAULT 'Not available' NOT NULL,
	`project_type` text DEFAULT 'Not available' NOT NULL,
	`official_url` text DEFAULT '' NOT NULL,
	`email_status` text DEFAULT 'pending' NOT NULL,
	`email_recipient` text DEFAULT '' NOT NULL,
	`first_seen_at` text NOT NULL,
	`notified_at` text,
	`attempts` integer DEFAULT 0 NOT NULL,
	`last_error` text,
	`priority` integer DEFAULT false NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE INDEX `idx_notifications_first_seen` ON `notifications` (`first_seen_at`);--> statement-breakpoint
CREATE INDEX `idx_notifications_source_status` ON `notifications` (`source`,`email_status`);--> statement-breakpoint
CREATE INDEX `idx_notifications_city` ON `notifications` (`city`);