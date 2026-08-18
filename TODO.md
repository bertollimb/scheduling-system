# TODO

Known scope gaps, not bugs — documented deliberately rather than implemented immediately.

## Pagination
`GET /clients`, `GET /services` and `GET /schedulings` return the full list with no limit.
Fine for the current volume; add `skip`/`limit` query params once the dataset grows enough
to matter.

## Password recovery
No self-service password reset flow. Currently, resetting the account password requires
manually running a script against the database. Acceptable for a single-user system, but
worth a proper flow (e.g. email-based reset) if more users are added later.

## Token revocation
JWTs are stateless — a leaked refresh token remains valid for up to 7 days with no way to
invalidate it early. Would require a server-side denylist (e.g. in Redis) to support real
logout/revocation.

## Scheduling completion status
`AppointmentStatus.COMPLETED` exists in the model but nothing transitions a scheduling into
it once its time has passed. Every non-cancelled scheduling stays `CONFIRMED` indefinitely.
Doesn't affect any current business rule (overlap checks rely on time comparison, not
status), but the lifecycle is incomplete.