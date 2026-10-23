CREATE TABLE `tm_jobs` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`idem` text NOT NULL,
	`et` text NOT NULL,
	`scope` text NOT NULL,
	`as_of` text NOT NULL,
	`state` text NOT NULL,
	`created` integer NOT NULL,
	`updated` integer NOT NULL,
	`run_id` integer,
	`last_poll` integer DEFAULT 0 NOT NULL,
	`error` text,
	`result` text
);
--> statement-breakpoint
CREATE UNIQUE INDEX `tm_owner_idem` ON `tm_jobs` (`owner`,`idem`);--> statement-breakpoint
CREATE INDEX `tm_created` ON `tm_jobs` (`created`);