import { buildApp } from "./app.js";
import { config } from "./config.js";
import { db } from "./db/client.js";
import { users } from "../drizzle/schema.js";
import { count } from "drizzle-orm";
import bcrypt from "bcryptjs";

async function seedAdminIfNeeded(): Promise<void> {
  try {
    const [{ value }] = await db.select({ value: count() }).from(users);
    if (value === 0) {
      const hash = await bcrypt.hash("smartops_dev", 10);
      await db.insert(users).values({
        email:        "admin@smartops.local",
        name:         "SmartOps Admin",
        role:         "admin",
        passwordHash: hash,
      });
      console.log("[seed] Created default admin: admin@smartops.local / smartops_dev");
    }
  } catch (err) {
    console.warn("[seed] DB not ready — skipping admin seed:", (err as Error).message);
  }
}

async function main(): Promise<void> {
  const app = await buildApp();

  await seedAdminIfNeeded();

  try {
    await app.listen({ port: config.port, host: config.host });
    app.log.info(`SmartOps API running at http://${config.host}:${config.port}`);
    app.log.info(`Swagger UI: http://localhost:${config.port}/api/docs`);
  } catch (err) {
    app.log.error(err);
    process.exit(1);
  }
}

main();
