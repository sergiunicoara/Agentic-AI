import { drizzle } from "drizzle-orm/node-postgres";
import { Pool } from "pg";
import * as schema from "../../drizzle/schema.js";
import { config } from "../config.js";

const pool = new Pool({ connectionString: config.databaseUrl, max: 10 });

export const db = drizzle(pool, { schema });
export type DB = typeof db;
