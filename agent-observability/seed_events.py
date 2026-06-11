import os, time, uuid, sys
sys.path.insert(0, "backend")

import grpc
from app.generated import agent_events_pb2, agent_events_pb2_grpc

channel = grpc.insecure_channel("localhost:50051")
stub = agent_events_pb2_grpc.AgentEventServiceStub(channel)
METADATA = (("x-api-key", os.getenv("EMIT_API_KEY", "dev-emit-key")),)

agents = ["recruiter-agent", "cv-screener", "jd-matcher"]

for agent in agents:
    trace_id = str(uuid.uuid4())
    task_id  = str(uuid.uuid4())

    for event_type, sensitivity, tokens_in, tokens_out, dur in [
        ("span_start", "public",       0,   0,  10),
        ("llm_call",   "internal",   512, 128, 340),
        ("tool_call",  "internal",    64,  32,  80),
        ("span_end",   "confidential", 0,   0,  12),
    ]:
        resp = stub.EmitEvent(agent_events_pb2.AgentEvent(
            trace_id      = trace_id,
            span_id       = str(uuid.uuid4()),
            agent_name    = agent,
            task_id       = task_id,
            event_type    = event_type,
            timestamp_ms  = int(time.time() * 1000),
            duration_ms   = dur,
            input_tokens  = tokens_in,
            output_tokens = tokens_out,
            model         = "claude-sonnet-4-6",
            outcome       = "success",
            status        = "ok",
            attributes    = {"data_sensitivity": sensitivity},
        ), metadata=METADATA)
        print(f"{'OK' if resp.accepted else 'FAIL'}  {agent:20s}  {event_type}")

channel.close()
print("\nDone — refresh the Traces tab.")
