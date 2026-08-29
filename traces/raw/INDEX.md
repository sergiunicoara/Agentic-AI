# Raw coding-agent trace index

> These transcripts were recorded under the project's working directory at
> the time, `Micro1 Frontier Engineering Claude`; the project was later named
> **BugProof**. Historical paths inside the raw traces are intentionally left
> unchanged. Case identifiers in each subagent's `.meta.json` map directly to
> `cases/<case_id>/`.

This index is generated from the original `.meta.json` files. It does not
modify or normalize the raw trace contents.

## Coverage summary

- Baseline attempts: **12**
- Candidate-generation invocations: **12**
- Repair invocations: **8**
- Plan / Explore / other invocations: **4**
- Metadata records indexed: **36**

## Index

| Agent/session ID | Type | Recorded task | Case ID | Submission case path | Metadata | Matching raw files |
|---|---|---|---|---|---|---|
| `agent-a00ce18b912c8e37b` | Other | Get Phase 3 prompt templates and runbook | `—` | — | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a00ce18b912c8e37b.meta.json` | `agent-a00ce18b912c8e37b.jsonl` |
| `agent-a018397c4a8664bf3` | Generate | Generate candidate for username_normalization | `username_normalization` | `cases/username_normalization/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a018397c4a8664bf3.meta.json` | `agent-a018397c4a8664bf3.jsonl` |
| `agent-a0b35fff970def217` | Generate | Generate candidate for stale_cache_between_users | `stale_cache_between_users` | `cases/stale_cache_between_users/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a0b35fff970def217.meta.json` | `agent-a0b35fff970def217.jsonl` |
| `agent-a0c081953915544e2` | Repair | Repair candidate for csv_quoted_field_parsing | `csv_quoted_field_parsing` | `cases/csv_quoted_field_parsing/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a0c081953915544e2.meta.json` | `agent-a0c081953915544e2.jsonl` |
| `agent-a0d6fe6f5dbc6c1d4` | Baseline | Baseline attempt: ttl_cache_boundary | `ttl_cache_boundary` | `cases/ttl_cache_boundary/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a0d6fe6f5dbc6c1d4.meta.json` | `agent-a0d6fe6f5dbc6c1d4.jsonl` |
| `agent-a0de6bb2520c547a2` | Generate | Generate candidate for inventory_negative_quantity | `inventory_negative_quantity` | `cases/inventory_negative_quantity/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a0de6bb2520c547a2.meta.json` | `agent-a0de6bb2520c547a2.jsonl` |
| `agent-a142da6378889fe62` | Generate | Generate candidate for contact_dedup_case_sensitivity | `contact_dedup_case_sensitivity` | `cases/contact_dedup_case_sensitivity/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a142da6378889fe62.meta.json` | `agent-a142da6378889fe62.jsonl` |
| `agent-a28a9f6a8ecccc690` | Generate | Generate candidate for discount_unit_mismatch | `discount_unit_mismatch` | `cases/discount_unit_mismatch/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a28a9f6a8ecccc690.meta.json` | `agent-a28a9f6a8ecccc690.jsonl` |
| `agent-a2c8b32b23caba0d0` | Repair | Repair candidate for contact_dedup_case_sensitivity | `contact_dedup_case_sensitivity` | `cases/contact_dedup_case_sensitivity/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a2c8b32b23caba0d0.meta.json` | `agent-a2c8b32b23caba0d0.jsonl` |
| `agent-a354e420305bab2b2` | Generate | Generate candidate for csv_quoted_field_parsing | `csv_quoted_field_parsing` | `cases/csv_quoted_field_parsing/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a354e420305bab2b2.meta.json` | `agent-a354e420305bab2b2.jsonl` |
| `agent-a39fbd8b724dca281` | Repair | Repair candidate for stale_cache_between_users | `stale_cache_between_users` | `cases/stale_cache_between_users/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a39fbd8b724dca281.meta.json` | `agent-a39fbd8b724dca281.jsonl` |
| `agent-a463c7fa93d423de3` | Repair | Repair candidate for ttl_cache_boundary | `ttl_cache_boundary` | `cases/ttl_cache_boundary/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a463c7fa93d423de3.meta.json` | `agent-a463c7fa93d423de3.jsonl` |
| `agent-a4e1b1212003310be` | Baseline | Baseline attempt: off_by_one_pagination | `off_by_one_pagination` | `cases/off_by_one_pagination/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a4e1b1212003310be.meta.json` | `agent-a4e1b1212003310be.jsonl` |
| `agent-a6487b04b3d92fe23` | Baseline | Baseline attempt: contact_dedup_case_sensitivity | `contact_dedup_case_sensitivity` | `cases/contact_dedup_case_sensitivity/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a6487b04b3d92fe23.meta.json` | `agent-a6487b04b3d92fe23.jsonl` |
| `agent-a653e8c03a893ab76` | Baseline | Baseline attempt: empty_list_average_crash | `empty_list_average_crash` | `cases/empty_list_average_crash/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a653e8c03a893ab76.meta.json` | `agent-a653e8c03a893ab76.jsonl` |
| `agent-a66b018b074e36051` | Baseline | Baseline attempt: reminder_lead_time_units | `reminder_lead_time_units` | `cases/reminder_lead_time_units/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a66b018b074e36051.meta.json` | `agent-a66b018b074e36051.jsonl` |
| `agent-a6ebf0d85e34796e8` | Repair | Repair candidate for roster_lookup_wrong_exception | `roster_lookup_wrong_exception` | `cases/roster_lookup_wrong_exception/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a6ebf0d85e34796e8.meta.json` | `agent-a6ebf0d85e34796e8.jsonl` |
| `agent-a6fa3db618f894b58` | Repair | Repair candidate for username_normalization | `username_normalization` | `cases/username_normalization/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a6fa3db618f894b58.meta.json` | `agent-a6fa3db618f894b58.jsonl` |
| `agent-a72f1c9b49c0e48e0` | Other | Explore BugProof Phase 2 infra for Phase 3 reuse | `—` | — | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a72f1c9b49c0e48e0.meta.json` | `agent-a72f1c9b49c0e48e0.jsonl` |
| `agent-a7748758a7ebc7581` | Baseline | Baseline attempt: inventory_negative_quantity | `inventory_negative_quantity` | `cases/inventory_negative_quantity/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a7748758a7ebc7581.meta.json` | `agent-a7748758a7ebc7581.jsonl` |
| `agent-a774ebe2e5d34d308` | Other | Validate Phase 3 architecture design | `—` | — | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a774ebe2e5d34d308.meta.json` | `agent-a774ebe2e5d34d308.jsonl` |
| `agent-a7b00c6f209ea386b` | Baseline | Baseline attempt: stale_cache_between_users | `stale_cache_between_users` | `cases/stale_cache_between_users/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a7b00c6f209ea386b.meta.json` | `agent-a7b00c6f209ea386b.jsonl` |
| `agent-a8499f131897f0e1b` | Baseline | Baseline attempt: roster_lookup_wrong_exception | `roster_lookup_wrong_exception` | `cases/roster_lookup_wrong_exception/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a8499f131897f0e1b.meta.json` | `agent-a8499f131897f0e1b.jsonl` |
| `agent-a8727b254846c27ad` | Baseline | Baseline attempt: username_normalization | `username_normalization` | `cases/username_normalization/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a8727b254846c27ad.meta.json` | `agent-a8727b254846c27ad.jsonl` |
| `agent-a89e1bceae33ed6ca` | Generate | Generate candidate for ttl_cache_boundary | `ttl_cache_boundary` | `cases/ttl_cache_boundary/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a89e1bceae33ed6ca.meta.json` | `agent-a89e1bceae33ed6ca.jsonl` |
| `agent-a8d83e4b5a2bdbf3e` | Baseline | Baseline attempt: csv_quoted_field_parsing | `csv_quoted_field_parsing` | `cases/csv_quoted_field_parsing/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-a8d83e4b5a2bdbf3e.meta.json` | `agent-a8d83e4b5a2bdbf3e.jsonl` |
| `agent-aa94267c827b10c2a` | Other | Validate Phase 3 architecture design | `—` | — | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-aa94267c827b10c2a.meta.json` | `agent-aa94267c827b10c2a.jsonl` |
| `agent-aa9b2cf78fe1ae063` | Generate | Generate candidate for roster_lookup_wrong_exception | `roster_lookup_wrong_exception` | `cases/roster_lookup_wrong_exception/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-aa9b2cf78fe1ae063.meta.json` | `agent-aa9b2cf78fe1ae063.jsonl` |
| `agent-ab8cf22034378f5a2` | Generate | Generate candidate for off_by_one_pagination | `off_by_one_pagination` | `cases/off_by_one_pagination/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-ab8cf22034378f5a2.meta.json` | `agent-ab8cf22034378f5a2.jsonl` |
| `agent-ab99090fb64aee6ec` | Generate | Generate candidate for empty_list_average_crash | `empty_list_average_crash` | `cases/empty_list_average_crash/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-ab99090fb64aee6ec.meta.json` | `agent-ab99090fb64aee6ec.jsonl` |
| `agent-ac2f269e21951ed73` | Baseline | Baseline attempt: cart_coupon_ordering | `cart_coupon_ordering` | `cases/cart_coupon_ordering/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-ac2f269e21951ed73.meta.json` | `agent-ac2f269e21951ed73.jsonl` |
| `agent-ac3cddde6260e4632` | Repair | Repair candidate for off_by_one_pagination | `off_by_one_pagination` | `cases/off_by_one_pagination/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-ac3cddde6260e4632.meta.json` | `agent-ac3cddde6260e4632.jsonl` |
| `agent-ac5c97ee3721eba91` | Baseline | Baseline attempt: discount_unit_mismatch | `discount_unit_mismatch` | `cases/discount_unit_mismatch/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-ac5c97ee3721eba91.meta.json` | `agent-ac5c97ee3721eba91.jsonl` |
| `agent-adc434fe698b5a29b` | Generate | Generate candidate for reminder_lead_time_units | `reminder_lead_time_units` | `cases/reminder_lead_time_units/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-adc434fe698b5a29b.meta.json` | `agent-adc434fe698b5a29b.jsonl` |
| `agent-adf3be4b7c3e6c1ea` | Generate | Generate candidate for cart_coupon_ordering | `cart_coupon_ordering` | `cases/cart_coupon_ordering/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-adf3be4b7c3e6c1ea.meta.json` | `agent-adf3be4b7c3e6c1ea.jsonl` |
| `agent-ae35f1f52233a4dac` | Repair | Repair candidate for empty_list_average_crash | `empty_list_average_crash` | `cases/empty_list_average_crash/` | `traces/raw/04dddc22-ab89-4e81-b948-325767785a17/subagents/agent-ae35f1f52233a4dac.meta.json` | `agent-ae35f1f52233a4dac.jsonl` |

## Verification note

The raw transcripts are preserved as captured. This index exists only to make
opaque session IDs navigable for reviewers. If a historical absolute path
contains `Micro1 Frontier Engineering Claude`, it refers to the same project
that is submitted here as **BugProof**.
