import { sqliteTable,text,integer,index,uniqueIndex } from 'drizzle-orm/sqlite-core';
export const jobs=sqliteTable('tm_jobs',{
 id:text('id').primaryKey(),owner:text('owner').notNull(),idem:text('idem').notNull(),
 et:text('et').notNull(),scope:text('scope').notNull(),asOf:text('as_of').notNull(),
 state:text('state').notNull(),created:integer('created').notNull(),updated:integer('updated').notNull(),
 runId:integer('run_id'),lastPoll:integer('last_poll').notNull().default(0),
 error:text('error'),result:text('result')
},t=>[uniqueIndex('tm_owner_idem').on(t.owner,t.idem),index('tm_created').on(t.created)]);
