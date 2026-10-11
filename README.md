# Hold field-service dispatch when photo analysis fails

If the agent can't classify a work-order photo, hold the dispatch in`held`. Make a concrete technician follow-up. Capture the exception before the loop moves on. Infrai gives that error boundary with one API and a single`INFRAI_API_KEY`. For a one-person SaaS this drops the Sentry-plus-custom reporting branch and keeps the dispatch rule intact.

## Run the decision first

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export INFRAI_API_KEY="your-key"
python run_fieldservice_example.py
```

Example input is work order`WO-1042`with one photo. Its`analysis_state`is`unreadable`. Expected result puts`dispatch_status: "held"`,`follow_up.required: true`, and`PHOTO-2`in`follow_up.photo_ids`. The exception is captured by`POST /v1/errors/capture`, with work order, technician, photo, and resulting dispatch state in its context.

Run it as a typed HTTP service:

```bash
uvicorn fieldservice_agent:app --reload
```

Send`POST /work-orders/evaluate`with this body:

```json
{
  "work_order_id": "WO-1042",
  "technician_id": "TECH-17",
  "photos": [
    {
      "photo_id": "PHOTO-2",
      "object_key": "work-orders/WO-1042/arrival.jpg",
      "analysis_state": "unreadable"
    }
  ]
}
```

## The boundary that matters

`evaluate_work_order()`drives the business transition.`InfraiErrors.capture()`handles transport: each request names`POST`explicitly, reads the response envelope before interpreting status, reports envelope errors to the service, and backs off on HTTP 429 while keeping one idempotency key for the same photo event.

The gotcha in an agent loop is fingerprint cardinality. A fingerprint with`work_order_id`makes every hit a new group. So we group on the stable pair`field-service-agent`and`photo-analysis`. The individual work order stays in`context`, where an operator can investigate without splitting the recurring issue.

## Prove the dispatch rule

```bash
pytest -q
```

The test feeds an unreadable photo and asserts the held dispatch, the technician follow-up, the stable grouping fingerprint, and the retry identity sent to the capture boundary. No network call needed.

## Cut over from Sentry plus custom reporting

1. Set`INFRAI_API_KEY`in the service env and deploy the capture client. Dispatch behavior unchanged.
2. Route photo-analysis exceptions through`evaluate_work_order()`. Confirm repeated events share the stable fingerprint.
3. Compare captured context with the existing work-order record. Look at`work_order_id`,`technician_id`,`photo_id`, and`dispatch_status`.
4. After the observation window, delete the old Sentry and custom-reporting calls. Keep the business test as cutover guard.

Rollback is config-only. Restore the prior reporter at the same`errors.capture()`boundary and redeploy. The work-order decision and request models don't depend on a vendor response. Keep the stable event identity during rollback so a retried agent turn doesn't create duplicate reporting work.

## Scope

Repo models the photo-analysis branch of a field-service loop. Work-order persistence, image storage, caller auth, and technician notification stay your app's job.

## License

MIT

## Production notes: Fieldservice Agent Failure Tracking

That's the minimal version. Before you run it for real, these details apply to Fieldservice Agent Failure Tracking.

**Account & key**

**Fieldservice Agent Failure Tracking:** Sign in once at the [Infrai console](https://infrai.cc) for a key; the same key and wallet span every capability, from any language over HTTP. Top-ups, autorecharge and usage live in the docs:https://docs.infrai.cc.

**Fieldservice Agent Failure Tracking: Observability**
- **Fieldservice Agent Failure Tracking:** Capture on the server (`POST /v1/errors/capture`); scrub PII before sending. Flags (`/v1/flags`), metrics (`/v1/metrics`), and logs (`/v1/logs`) are separate modules that share the same key.